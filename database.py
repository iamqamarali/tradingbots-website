"""
SQLite Database for Account-Based Trade Tracking
=================================================
Stores accounts and trades synced from Binance.
"""

import sqlite3
import os
import hashlib
import secrets
from datetime import datetime, timedelta
from threading import Lock

# Database path
DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'trades.db')

# Thread-safe lock for database operations
db_lock = Lock()


def get_connection():
    """Get a database connection with WAL mode for concurrent access."""
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db():
    """Initialize the database with tables."""
    with db_lock:
        conn = get_connection()
        cursor = conn.cursor()

        # Users table for authentication
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                salt TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # App settings table (for registration restriction)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS app_settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
        ''')

        # Initialize registration_open setting if not exists
        cursor.execute('INSERT OR IGNORE INTO app_settings (key, value) VALUES (?, ?)',
                      ('registration_open', 'true'))

        # Accounts table (NEW)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS accounts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                api_key TEXT NOT NULL,
                api_secret TEXT NOT NULL,
                is_testnet INTEGER DEFAULT 0,
                total_trades INTEGER DEFAULT 0,
                total_pnl REAL DEFAULT 0,
                total_commission REAL DEFAULT 0,
                winning_trades INTEGER DEFAULT 0,
                losing_trades INTEGER DEFAULT 0,
                last_sync_time TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # Add new columns if they don't exist (migration for existing databases)
        for col, col_type, default in [
            ('total_trades', 'INTEGER', 0),
            ('total_pnl', 'REAL', 0),
            ('total_commission', 'REAL', 0),
            ('winning_trades', 'INTEGER', 0),
            ('losing_trades', 'INTEGER', 0),
            ('last_sync_time', 'TIMESTAMP', None)
        ]:
            try:
                cursor.execute(f'ALTER TABLE accounts ADD COLUMN {col} {col_type} DEFAULT {default if default is not None else "NULL"}')
            except sqlite3.OperationalError:
                pass  # Column already exists
        
        # Trades table (linked to accounts, with exchange_trade_id for deduplication)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS trades (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                account_id INTEGER NOT NULL,
                exchange_trade_id TEXT UNIQUE,
                order_id TEXT,
                symbol TEXT NOT NULL,
                side TEXT NOT NULL CHECK(side IN ('LONG', 'SHORT', 'BUY', 'SELL')),
                quantity REAL NOT NULL,
                price REAL NOT NULL,
                realized_pnl REAL DEFAULT 0,
                commission REAL DEFAULT 0,
                commission_asset TEXT,
                trade_time TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (account_id) REFERENCES accounts(id) ON DELETE CASCADE
            )
        ''')
        
        # Add account_id column to trades if it doesn't exist (migration for existing databases)
        try:
            cursor.execute('ALTER TABLE trades ADD COLUMN account_id INTEGER REFERENCES accounts(id) ON DELETE CASCADE')
        except sqlite3.OperationalError:
            pass  # Column already exists

        # Create indexes
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_trades_account_id ON trades(account_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_trades_symbol ON trades(symbol)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_trades_trade_time ON trades(trade_time)')
        cursor.execute('CREATE UNIQUE INDEX IF NOT EXISTS idx_trades_exchange_id ON trades(exchange_trade_id)')
        
        conn.commit()
        conn.close()


# ==================== ACCOUNT OPERATIONS ====================

def create_account(name, api_key, api_secret, is_testnet=False):
    """Create a new account. Returns account id."""
    with db_lock:
        conn = get_connection()
        cursor = conn.cursor()
        
        cursor.execute(
            'INSERT INTO accounts (name, api_key, api_secret, is_testnet) VALUES (?, ?, ?, ?)',
            (name, api_key, api_secret, 1 if is_testnet else 0)
        )
        account_id = cursor.lastrowid
        
        conn.commit()
        conn.close()
        return account_id


def get_all_accounts():
    """Get all accounts with trade statistics."""
    with db_lock:
        conn = get_connection()
        cursor = conn.cursor()

        cursor.execute('''
            SELECT
                id, name, api_key, api_secret, is_testnet, created_at,
                total_trades, total_pnl, total_commission,
                winning_trades, losing_trades, last_sync_time
            FROM accounts
            ORDER BY created_at DESC
        ''')

        accounts = []
        for row in cursor.fetchall():
            total_trades = row['total_trades'] or 0
            winning = row['winning_trades'] or 0
            losing = row['losing_trades'] or 0
            win_rate = round(winning / (winning + losing) * 100, 1) if (winning + losing) > 0 else 0

            accounts.append({
                'id': row['id'],
                'name': row['name'],
                'api_key': row['api_key'][:8] + '...' if row['api_key'] else '',  # Mask key
                'api_key_full': row['api_key'],
                'api_secret': row['api_secret'],
                'is_testnet': bool(row['is_testnet']),
                'created_at': row['created_at'],
                'total_trades': total_trades,
                'total_pnl': round(row['total_pnl'] or 0, 2),
                'total_commission': round(row['total_commission'] or 0, 2),
                'winning_trades': winning,
                'losing_trades': losing,
                'win_rate': win_rate,
                'last_sync_time': row['last_sync_time']
            })

        conn.close()
        return accounts


def get_account(account_id):
    """Get a single account by ID."""
    with db_lock:
        conn = get_connection()
        cursor = conn.cursor()
        
        cursor.execute('SELECT * FROM accounts WHERE id = ?', (account_id,))
        row = cursor.fetchone()
        
        conn.close()
        
        if row:
            return {
                'id': row['id'],
                'name': row['name'],
                'api_key': row['api_key'],
                'api_secret': row['api_secret'],
                'is_testnet': bool(row['is_testnet']),
                'created_at': row['created_at']
            }
        return None


def update_account(account_id, name=None, api_key=None, api_secret=None, is_testnet=None):
    """Update an account."""
    with db_lock:
        conn = get_connection()
        cursor = conn.cursor()
        
        updates = []
        params = []
        
        if name is not None:
            updates.append('name = ?')
            params.append(name)
        if api_key is not None:
            updates.append('api_key = ?')
            params.append(api_key)
        if api_secret is not None:
            updates.append('api_secret = ?')
            params.append(api_secret)
        if is_testnet is not None:
            updates.append('is_testnet = ?')
            params.append(1 if is_testnet else 0)
        
        if updates:
            params.append(account_id)
            cursor.execute(f'UPDATE accounts SET {", ".join(updates)} WHERE id = ?', params)
        
        conn.commit()
        conn.close()
        return True


def update_account_stats(account_id):
    """Recalculate and update account stats from trades table."""
    with db_lock:
        conn = get_connection()
        cursor = conn.cursor()

        # Calculate stats from trades
        cursor.execute('''
            SELECT
                COUNT(*) as total_trades,
                COALESCE(SUM(realized_pnl), 0) as total_pnl,
                COALESCE(SUM(commission), 0) as total_commission,
                SUM(CASE WHEN realized_pnl > 0 THEN 1 ELSE 0 END) as winning_trades,
                SUM(CASE WHEN realized_pnl < 0 THEN 1 ELSE 0 END) as losing_trades
            FROM trades
            WHERE account_id = ?
        ''', (account_id,))

        row = cursor.fetchone()

        if row:
            cursor.execute('''
                UPDATE accounts SET
                    total_trades = ?,
                    total_pnl = ?,
                    total_commission = ?,
                    winning_trades = ?,
                    losing_trades = ?,
                    last_sync_time = CURRENT_TIMESTAMP
                WHERE id = ?
            ''', (
                row['total_trades'] or 0,
                round(row['total_pnl'] or 0, 4),
                round(row['total_commission'] or 0, 4),
                row['winning_trades'] or 0,
                row['losing_trades'] or 0,
                account_id
            ))

        conn.commit()
        conn.close()
        return True


def delete_account(account_id):
    """Delete an account and all its trades."""
    with db_lock:
        conn = get_connection()
        cursor = conn.cursor()

        cursor.execute('DELETE FROM accounts WHERE id = ?', (account_id,))
        deleted = cursor.rowcount > 0
        
        conn.commit()
        conn.close()
        return deleted


# ==================== TRADE OPERATIONS ====================

def insert_trade(account_id, exchange_trade_id, order_id, symbol, side, quantity, 
                 price, realized_pnl, commission, commission_asset, trade_time):
    """Insert a trade if it doesn't already exist. Returns True if inserted."""
    with db_lock:
        conn = get_connection()
        cursor = conn.cursor()
        
        # Check if trade already exists
        cursor.execute('SELECT id FROM trades WHERE exchange_trade_id = ?', (str(exchange_trade_id),))
        if cursor.fetchone():
            conn.close()
            return False  # Already exists
        
        cursor.execute('''
            INSERT INTO trades (
                account_id, exchange_trade_id, order_id, symbol, side, quantity,
                price, realized_pnl, commission, commission_asset, trade_time
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (account_id, str(exchange_trade_id), str(order_id), symbol, side, quantity,
              price, realized_pnl, commission, commission_asset, trade_time))
        
        conn.commit()
        conn.close()
        return True


def get_trades(account_id=None, symbol=None, limit=100, offset=0):
    """Get trades with optional filters."""
    with db_lock:
        conn = get_connection()
        cursor = conn.cursor()
        
        query = '''
            SELECT t.*, a.name as account_name
            FROM trades t
            JOIN accounts a ON t.account_id = a.id
            WHERE 1=1
        '''
        params = []
        
        if account_id:
            query += ' AND t.account_id = ?'
            params.append(account_id)
        
        if symbol:
            query += ' AND t.symbol = ?'
            params.append(symbol)
        
        query += ' ORDER BY t.trade_time DESC LIMIT ? OFFSET ?'
        params.extend([limit, offset])
        
        cursor.execute(query, params)
        
        trades = []
        for row in cursor.fetchall():
            trade = dict(row)
            trades.append(trade)
        
        conn.close()
        return trades


def get_trade_stats(account_id=None):
    """Get aggregated trade statistics."""
    with db_lock:
        conn = get_connection()
        cursor = conn.cursor()
        
        query = '''
            SELECT 
                COUNT(*) as total_trades,
                COUNT(DISTINCT symbol) as symbols_traded,
                COALESCE(SUM(realized_pnl), 0) as total_pnl,
                COALESCE(SUM(commission), 0) as total_commission,
                SUM(CASE WHEN realized_pnl > 0 THEN 1 ELSE 0 END) as winning_trades,
                SUM(CASE WHEN realized_pnl < 0 THEN 1 ELSE 0 END) as losing_trades,
                SUM(CASE WHEN realized_pnl = 0 THEN 1 ELSE 0 END) as breakeven_trades
            FROM trades
        '''
        
        if account_id:
            query += ' WHERE account_id = ?'
            cursor.execute(query, (account_id,))
        else:
            cursor.execute(query)
        
        row = cursor.fetchone()
        conn.close()
        
        if row:
            total = row['total_trades'] or 0
            winning = row['winning_trades'] or 0
            losing = row['losing_trades'] or 0
            
            return {
                'total_trades': total,
                'symbols_traded': row['symbols_traded'] or 0,
                'total_pnl': round(row['total_pnl'] or 0, 2),
                'total_commission': round(row['total_commission'] or 0, 2),
                'winning_trades': winning,
                'losing_trades': losing,
                'breakeven_trades': row['breakeven_trades'] or 0,
                'win_rate': round(winning / (winning + losing) * 100, 1) if (winning + losing) > 0 else 0
            }
        
        return None


def delete_trade(trade_id):
    """Delete a trade."""
    with db_lock:
        conn = get_connection()
        cursor = conn.cursor()
        
        cursor.execute('DELETE FROM trades WHERE id = ?', (trade_id,))
        deleted = cursor.rowcount > 0
        
        conn.commit()
        conn.close()
        return deleted


def get_last_sync_time(account_id):
    """Get the most recent trade time for an account."""
    with db_lock:
        conn = get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT MAX(trade_time) as last_time
            FROM trades
            WHERE account_id = ?
        ''', (account_id,))
        
        row = cursor.fetchone()
        conn.close()
        
        if row and row['last_time']:
            return row['last_time']
        return None


# ==================== USER AUTHENTICATION ====================

def hash_password(password, salt=None):
    """Hash a password with salt."""
    if salt is None:
        salt = secrets.token_hex(32)
    password_hash = hashlib.pbkdf2_hmac(
        'sha256',
        password.encode('utf-8'),
        salt.encode('utf-8'),
        100000
    ).hex()
    return password_hash, salt


def create_user(username, password):
    """Create a new user. Returns user id or None if username exists."""
    with db_lock:
        conn = get_connection()
        cursor = conn.cursor()

        # Check if username exists
        cursor.execute('SELECT id FROM users WHERE username = ?', (username,))
        if cursor.fetchone():
            conn.close()
            return None

        password_hash, salt = hash_password(password)

        cursor.execute(
            'INSERT INTO users (username, password_hash, salt) VALUES (?, ?, ?)',
            (username, password_hash, salt)
        )
        user_id = cursor.lastrowid

        conn.commit()
        conn.close()
        return user_id


def verify_user(username, password):
    """Verify user credentials. Returns user dict or None."""
    with db_lock:
        conn = get_connection()
        cursor = conn.cursor()

        cursor.execute('SELECT * FROM users WHERE username = ?', (username,))
        row = cursor.fetchone()
        conn.close()

        if not row:
            return None

        password_hash, _ = hash_password(password, row['salt'])

        if password_hash == row['password_hash']:
            return {
                'id': row['id'],
                'username': row['username'],
                'created_at': row['created_at']
            }
        return None


def get_user_count():
    """Get the number of registered users."""
    with db_lock:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT COUNT(*) as count FROM users')
        row = cursor.fetchone()
        conn.close()
        return row['count'] if row else 0


def is_registration_open():
    """Check if registration is open."""
    with db_lock:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT value FROM app_settings WHERE key = ?', ('registration_open',))
        row = cursor.fetchone()
        conn.close()
        return row['value'] == 'true' if row else True


def set_registration_open(is_open):
    """Set registration open/closed."""
    with db_lock:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(
            'INSERT OR REPLACE INTO app_settings (key, value) VALUES (?, ?)',
            ('registration_open', 'true' if is_open else 'false')
        )
        conn.commit()
        conn.close()
        return True


# Initialize database on module load
init_db()
