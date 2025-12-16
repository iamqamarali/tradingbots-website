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
    conn = sqlite3.connect(DB_PATH, timeout=30, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA busy_timeout=30000")  # 30 second busy timeout
    return conn


def close_all_connections():
    """Close all database connections and checkpoint WAL file."""
    try:
        conn = sqlite3.connect(DB_PATH, timeout=5)
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        conn.close()
    except Exception:
        pass


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

        # Accounts table
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
                current_balance REAL DEFAULT 0,
                starting_balance REAL DEFAULT 0,
                avg_win REAL DEFAULT 0,
                avg_loss REAL DEFAULT 0,
                largest_win REAL DEFAULT 0,
                largest_loss REAL DEFAULT 0,
                profit_factor REAL DEFAULT 0,
                total_volume REAL DEFAULT 0,
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
            ('current_balance', 'REAL', 0),
            ('starting_balance', 'REAL', 0),
            ('avg_win', 'REAL', 0),
            ('avg_loss', 'REAL', 0),
            ('largest_win', 'REAL', 0),
            ('largest_loss', 'REAL', 0),
            ('profit_factor', 'REAL', 0),
            ('total_volume', 'REAL', 0),
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

        # Open positions table (cached from Binance)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS open_positions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                account_id INTEGER NOT NULL,
                symbol TEXT NOT NULL,
                side TEXT NOT NULL,
                quantity REAL NOT NULL,
                entry_price REAL NOT NULL,
                mark_price REAL NOT NULL,
                unrealized_pnl REAL DEFAULT 0,
                leverage INTEGER DEFAULT 1,
                stop_price REAL,
                stop_order_id INTEGER,
                stop_type TEXT,
                tp_price REAL,
                tp_order_id INTEGER,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (account_id) REFERENCES accounts(id) ON DELETE CASCADE,
                UNIQUE(account_id, symbol)
            )
        ''')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_positions_account_id ON open_positions(account_id)')

        # Cache metadata table (stores last update timestamps)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS cache_meta (
                key TEXT PRIMARY KEY,
                value TEXT,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # Closed positions table - complete trade cycles from open to close
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS closed_positions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                account_id INTEGER NOT NULL,
                symbol TEXT NOT NULL,
                side TEXT NOT NULL,
                quantity REAL NOT NULL,
                entry_price REAL NOT NULL,
                exit_price REAL NOT NULL,
                size_usd REAL NOT NULL,
                realized_pnl REAL NOT NULL,
                commission REAL DEFAULT 0,
                entry_time TIMESTAMP,
                exit_time TIMESTAMP,
                duration_seconds INTEGER,
                trade_ids TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (account_id) REFERENCES accounts(id) ON DELETE CASCADE
            )
        ''')

        # Add size_usd column if it doesn't exist (migration)
        try:
            cursor.execute('ALTER TABLE closed_positions ADD COLUMN size_usd REAL DEFAULT 0')
        except sqlite3.OperationalError:
            pass  # Column already exists
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_closed_positions_account_id ON closed_positions(account_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_closed_positions_exit_time ON closed_positions(exit_time)')

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
                winning_trades, losing_trades, last_sync_time,
                current_balance, starting_balance, avg_win, avg_loss,
                largest_win, largest_loss, profit_factor, total_volume
            FROM accounts
            ORDER BY created_at DESC
        ''')

        accounts = []
        for row in cursor.fetchall():
            total_trades = row['total_trades'] or 0
            winning = row['winning_trades'] or 0
            losing = row['losing_trades'] or 0
            win_rate = round(winning / (winning + losing) * 100, 1) if (winning + losing) > 0 else 0
            
            current_balance = row['current_balance'] or 0
            starting_balance = row['starting_balance'] or 0
            # Net profit is realized PnL from trades (not balance difference)
            net_profit = row['total_pnl'] or 0
            net_profit_pct = round((net_profit / starting_balance) * 100, 2) if starting_balance > 0 else 0

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
                'last_sync_time': row['last_sync_time'],
                'current_balance': round(current_balance, 2),
                'starting_balance': round(starting_balance, 2),
                'net_profit': round(net_profit, 2),
                'net_profit_pct': net_profit_pct,
                'avg_win': round(row['avg_win'] or 0, 2),
                'avg_loss': round(row['avg_loss'] or 0, 2),
                'largest_win': round(row['largest_win'] or 0, 2),
                'largest_loss': round(row['largest_loss'] or 0, 2),
                'profit_factor': round(row['profit_factor'] or 0, 2),
                'total_volume': round(row['total_volume'] or 0, 2)
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


def update_account_stats(account_id, current_balance=None):
    """Recalculate and update account stats from trades table."""
    with db_lock:
        conn = get_connection()
        cursor = conn.cursor()

        # Calculate comprehensive stats from trades
        cursor.execute('''
            SELECT
                COUNT(*) as total_trades,
                COALESCE(SUM(realized_pnl), 0) as total_pnl,
                COALESCE(SUM(commission), 0) as total_commission,
                COALESCE(SUM(quantity * price), 0) as total_volume,
                SUM(CASE WHEN realized_pnl > 0 THEN 1 ELSE 0 END) as winning_trades,
                SUM(CASE WHEN realized_pnl < 0 THEN 1 ELSE 0 END) as losing_trades,
                COALESCE(AVG(CASE WHEN realized_pnl > 0 THEN realized_pnl END), 0) as avg_win,
                COALESCE(AVG(CASE WHEN realized_pnl < 0 THEN realized_pnl END), 0) as avg_loss,
                COALESCE(MAX(realized_pnl), 0) as largest_win,
                COALESCE(MIN(realized_pnl), 0) as largest_loss,
                COALESCE(SUM(CASE WHEN realized_pnl > 0 THEN realized_pnl ELSE 0 END), 0) as gross_profit,
                COALESCE(ABS(SUM(CASE WHEN realized_pnl < 0 THEN realized_pnl ELSE 0 END)), 0) as gross_loss
            FROM trades
            WHERE account_id = ?
        ''', (account_id,))

        row = cursor.fetchone()

        if row:
            # Calculate profit factor (gross profit / gross loss)
            gross_profit = row['gross_profit'] or 0
            gross_loss = row['gross_loss'] or 0
            profit_factor = round(gross_profit / gross_loss, 2) if gross_loss > 0 else (999.99 if gross_profit > 0 else 0)
            
            # Build update query
            update_fields = '''
                total_trades = ?,
                total_pnl = ?,
                total_commission = ?,
                total_volume = ?,
                winning_trades = ?,
                losing_trades = ?,
                avg_win = ?,
                avg_loss = ?,
                largest_win = ?,
                largest_loss = ?,
                profit_factor = ?,
                last_sync_time = CURRENT_TIMESTAMP
            '''
            params = [
                row['total_trades'] or 0,
                round(row['total_pnl'] or 0, 4),
                round(row['total_commission'] or 0, 4),
                round(row['total_volume'] or 0, 2),
                row['winning_trades'] or 0,
                row['losing_trades'] or 0,
                round(row['avg_win'] or 0, 4),
                round(row['avg_loss'] or 0, 4),
                round(row['largest_win'] or 0, 4),
                round(row['largest_loss'] or 0, 4),
                profit_factor
            ]
            
            # Also update current balance if provided
            if current_balance is not None:
                update_fields += ', current_balance = ?'
                params.append(round(current_balance, 2))
                
                # Set starting balance if not set yet
                cursor.execute('SELECT starting_balance FROM accounts WHERE id = ?', (account_id,))
                acc_row = cursor.fetchone()
                if acc_row and (acc_row['starting_balance'] is None or acc_row['starting_balance'] == 0):
                    update_fields += ', starting_balance = ?'
                    params.append(round(current_balance, 2))
            
            params.append(account_id)
            cursor.execute(f'UPDATE accounts SET {update_fields} WHERE id = ?', params)

        conn.commit()
        conn.close()
        return True


def update_account_balance(account_id, balance):
    """Update just the current balance for an account."""
    with db_lock:
        conn = get_connection()
        cursor = conn.cursor()
        
        # Check if starting balance is set
        cursor.execute('SELECT starting_balance FROM accounts WHERE id = ?', (account_id,))
        row = cursor.fetchone()
        
        if row and (row['starting_balance'] is None or row['starting_balance'] == 0):
            # Set both starting and current balance
            cursor.execute('''
                UPDATE accounts SET current_balance = ?, starting_balance = ? WHERE id = ?
            ''', (round(balance, 2), round(balance, 2), account_id))
        else:
            # Only update current balance
            cursor.execute('''
                UPDATE accounts SET current_balance = ? WHERE id = ?
            ''', (round(balance, 2), account_id))
        
        conn.commit()
        conn.close()
        return True


def set_starting_balance(account_id, balance):
    """Manually set the starting balance for an account."""
    with db_lock:
        conn = get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            UPDATE accounts SET starting_balance = ? WHERE id = ?
        ''', (round(balance, 2), account_id))
        
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
        try:
            cursor = conn.cursor()

            # Check if trade already exists
            cursor.execute('SELECT id FROM trades WHERE exchange_trade_id = ?', (str(exchange_trade_id),))
            if cursor.fetchone():
                return False  # Already exists

            cursor.execute('''
                INSERT INTO trades (
                    account_id, exchange_trade_id, order_id, symbol, side, quantity,
                    price, realized_pnl, commission, commission_asset, trade_time
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (account_id, str(exchange_trade_id), str(order_id), symbol, side, quantity,
                  price, realized_pnl, commission, commission_asset, trade_time))

            conn.commit()
            return True
        finally:
            conn.close()


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


def get_trades_count(account_id=None, symbol=None):
    """Get total count of trades for pagination."""
    with db_lock:
        conn = get_connection()
        cursor = conn.cursor()

        query = 'SELECT COUNT(*) as count FROM trades WHERE 1=1'
        params = []

        if account_id:
            query += ' AND account_id = ?'
            params.append(account_id)

        if symbol:
            query += ' AND symbol = ?'
            params.append(symbol)

        cursor.execute(query, params)
        row = cursor.fetchone()
        conn.close()

        return row['count'] if row else 0


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
                COALESCE(SUM(quantity * price), 0) as total_volume,
                SUM(CASE WHEN realized_pnl > 0 THEN 1 ELSE 0 END) as winning_trades,
                SUM(CASE WHEN realized_pnl < 0 THEN 1 ELSE 0 END) as losing_trades,
                SUM(CASE WHEN realized_pnl = 0 THEN 1 ELSE 0 END) as breakeven_trades,
                COALESCE(AVG(CASE WHEN realized_pnl > 0 THEN realized_pnl END), 0) as avg_win,
                COALESCE(AVG(CASE WHEN realized_pnl < 0 THEN realized_pnl END), 0) as avg_loss,
                COALESCE(MAX(realized_pnl), 0) as largest_win,
                COALESCE(MIN(realized_pnl), 0) as largest_loss,
                COALESCE(SUM(CASE WHEN realized_pnl > 0 THEN realized_pnl ELSE 0 END), 0) as gross_profit,
                COALESCE(ABS(SUM(CASE WHEN realized_pnl < 0 THEN realized_pnl ELSE 0 END)), 0) as gross_loss
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
            gross_profit = row['gross_profit'] or 0
            gross_loss = row['gross_loss'] or 0
            total_pnl = row['total_pnl'] or 0
            profit_factor = round(gross_profit / gross_loss, 2) if gross_loss > 0 else (999.99 if gross_profit > 0 else 0)
            
            stats = {
                'total_trades': total,
                'symbols_traded': row['symbols_traded'] or 0,
                'total_pnl': round(total_pnl, 2),
                'total_commission': round(row['total_commission'] or 0, 2),
                'total_volume': round(row['total_volume'] or 0, 2),
                'winning_trades': winning,
                'losing_trades': losing,
                'breakeven_trades': row['breakeven_trades'] or 0,
                'win_rate': round(winning / (winning + losing) * 100, 1) if (winning + losing) > 0 else 0,
                'avg_win': round(row['avg_win'] or 0, 2),
                'avg_loss': round(row['avg_loss'] or 0, 2),
                'largest_win': round(row['largest_win'] or 0, 2),
                'largest_loss': round(row['largest_loss'] or 0, 2),
                'profit_factor': profit_factor,
                'gross_profit': round(gross_profit, 2),
                'gross_loss': round(gross_loss, 2)
            }
            
            # Add account balance info if account_id specified
            if account_id:
                conn2 = get_connection()
                cursor2 = conn2.cursor()
                cursor2.execute('''
                    SELECT current_balance, starting_balance FROM accounts WHERE id = ?
                ''', (account_id,))
                acc_row = cursor2.fetchone()
                conn2.close()
                
                if acc_row:
                    current_balance = acc_row['current_balance'] or 0
                    starting_balance = acc_row['starting_balance'] or 0
                    stats['current_balance'] = round(current_balance, 2)
                    stats['starting_balance'] = round(starting_balance, 2)
                    stats['net_profit'] = round(total_pnl, 2)
                    stats['net_profit_pct'] = round((total_pnl / starting_balance) * 100, 2) if starting_balance > 0 else 0
            
            return stats
        
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


def delete_all_trades_and_positions():
    """Delete all trades and closed positions from database. Used for fresh start."""
    with db_lock:
        conn = get_connection()
        cursor = conn.cursor()

        cursor.execute('DELETE FROM trades')
        trades_deleted = cursor.rowcount

        cursor.execute('DELETE FROM closed_positions')
        positions_deleted = cursor.rowcount

        # Reset account stats
        cursor.execute('''
            UPDATE accounts SET
                total_trades = 0,
                total_pnl = 0,
                total_commission = 0,
                winning_trades = 0,
                losing_trades = 0,
                avg_win = 0,
                avg_loss = 0,
                largest_win = 0,
                largest_loss = 0,
                profit_factor = 0,
                total_volume = 0,
                last_sync_time = NULL
        ''')

        conn.commit()
        conn.close()
        print(f"Deleted {trades_deleted} trades and {positions_deleted} closed positions")
        return trades_deleted, positions_deleted


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


# ==================== OPEN POSITIONS CACHE ====================

def get_positions_cache_time():
    """Get the last update time for positions cache."""
    with db_lock:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT value FROM cache_meta WHERE key = ?', ('positions_updated',))
        row = cursor.fetchone()
        conn.close()
        if row:
            try:
                return float(row['value'])
            except:
                return None
        return None


def set_positions_cache_time(timestamp):
    """Set the last update time for positions cache."""
    with db_lock:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(
            'INSERT OR REPLACE INTO cache_meta (key, value, updated_at) VALUES (?, ?, CURRENT_TIMESTAMP)',
            ('positions_updated', str(timestamp))
        )
        conn.commit()
        conn.close()


def save_open_positions(positions):
    """Save open positions to database (replaces all existing)."""
    with db_lock:
        conn = get_connection()
        cursor = conn.cursor()

        # Clear existing positions
        cursor.execute('DELETE FROM open_positions')

        # Insert new positions
        for pos in positions:
            cursor.execute('''
                INSERT INTO open_positions
                (account_id, symbol, side, quantity, entry_price, mark_price,
                 unrealized_pnl, leverage, stop_price, stop_order_id, stop_type, tp_price, tp_order_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                pos['account_id'],
                pos['symbol'],
                pos['side'],
                pos['quantity'],
                pos['entry_price'],
                pos['mark_price'],
                pos['unrealized_pnl'],
                pos['leverage'],
                pos.get('stop_price'),
                pos.get('stop_order_id'),
                pos.get('stop_type'),
                pos.get('tp_price'),
                pos.get('tp_order_id')
            ))

        conn.commit()
        conn.close()


def get_open_positions():
    """Get all open positions from database with account info."""
    with db_lock:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT p.*, a.name as account_name, a.is_testnet
            FROM open_positions p
            JOIN accounts a ON p.account_id = a.id
            ORDER BY a.name, p.symbol
        ''')
        rows = cursor.fetchall()
        conn.close()

        positions = []
        for row in rows:
            positions.append({
                'account_id': row['account_id'],
                'account_name': row['account_name'],
                'is_testnet': bool(row['is_testnet']),
                'symbol': row['symbol'],
                'side': row['side'],
                'quantity': row['quantity'],
                'entry_price': row['entry_price'],
                'mark_price': row['mark_price'],
                'unrealized_pnl': row['unrealized_pnl'],
                'leverage': row['leverage'],
                'stop_price': row['stop_price'],
                'stop_order_id': row['stop_order_id'],
                'stop_type': row['stop_type'],
                'tp_price': row['tp_price'],
                'tp_order_id': row['tp_order_id']
            })
        return positions


def clear_open_positions():
    """Clear all cached open positions."""
    with db_lock:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute('DELETE FROM open_positions')
        cursor.execute('DELETE FROM cache_meta WHERE key = ?', ('positions_updated',))
        conn.commit()
        conn.close()


# ==================== CLOSED POSITIONS OPERATIONS ====================

def insert_closed_position(account_id, symbol, side, quantity, entry_price, exit_price,
                           realized_pnl, commission, entry_time, exit_time, trade_ids=None):
    """Insert a closed position record."""
    with db_lock:
        conn = get_connection()
        cursor = conn.cursor()

        # Calculate position size in USD
        size_usd = quantity * entry_price

        # Calculate duration in seconds
        duration_seconds = None
        if entry_time and exit_time:
            try:
                from datetime import datetime
                entry_dt = datetime.fromisoformat(entry_time.replace('Z', '+00:00')) if isinstance(entry_time, str) else entry_time
                exit_dt = datetime.fromisoformat(exit_time.replace('Z', '+00:00')) if isinstance(exit_time, str) else exit_time
                duration_seconds = int((exit_dt - entry_dt).total_seconds())
            except:
                pass

        # Convert trade_ids list to comma-separated string
        trade_ids_str = ','.join(map(str, trade_ids)) if trade_ids else None

        cursor.execute('''
            INSERT INTO closed_positions (
                account_id, symbol, side, quantity, entry_price, exit_price, size_usd,
                realized_pnl, commission, entry_time, exit_time, duration_seconds, trade_ids
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (account_id, symbol, side, quantity, entry_price, exit_price, size_usd,
              realized_pnl, commission, entry_time, exit_time, duration_seconds, trade_ids_str))

        position_id = cursor.lastrowid
        conn.commit()
        conn.close()
        return position_id


def get_closed_positions(account_id=None, symbol=None, limit=100, offset=0):
    """Get closed positions with optional filters."""
    with db_lock:
        conn = get_connection()
        cursor = conn.cursor()

        query = '''
            SELECT cp.*, a.name as account_name
            FROM closed_positions cp
            JOIN accounts a ON cp.account_id = a.id
            WHERE 1=1
        '''
        params = []

        if account_id:
            query += ' AND cp.account_id = ?'
            params.append(account_id)

        if symbol:
            query += ' AND cp.symbol = ?'
            params.append(symbol)

        query += ' ORDER BY cp.exit_time DESC LIMIT ? OFFSET ?'
        params.extend([limit, offset])

        cursor.execute(query, params)

        positions = []
        for row in cursor.fetchall():
            # Calculate size_usd if not in DB (for backwards compatibility)
            size_usd = row['size_usd'] if 'size_usd' in row.keys() and row['size_usd'] else row['quantity'] * row['entry_price']
            positions.append({
                'id': row['id'],
                'account_id': row['account_id'],
                'account_name': row['account_name'],
                'symbol': row['symbol'],
                'side': row['side'],
                'quantity': row['quantity'],
                'entry_price': row['entry_price'],
                'exit_price': row['exit_price'],
                'size_usd': round(size_usd, 2),
                'realized_pnl': row['realized_pnl'],
                'commission': row['commission'],
                'entry_time': row['entry_time'],
                'exit_time': row['exit_time'],
                'duration_seconds': row['duration_seconds'],
                'trade_ids': row['trade_ids']
            })

        conn.close()
        return positions


def get_closed_positions_count(account_id=None, symbol=None):
    """Get total count of closed positions for pagination."""
    with db_lock:
        conn = get_connection()
        cursor = conn.cursor()

        query = 'SELECT COUNT(*) as count FROM closed_positions WHERE 1=1'
        params = []

        if account_id:
            query += ' AND account_id = ?'
            params.append(account_id)

        if symbol:
            query += ' AND symbol = ?'
            params.append(symbol)

        cursor.execute(query, params)
        row = cursor.fetchone()
        conn.close()

        return row['count'] if row else 0


def delete_closed_position(position_id):
    """Delete a closed position."""
    with db_lock:
        conn = get_connection()
        cursor = conn.cursor()

        cursor.execute('DELETE FROM closed_positions WHERE id = ?', (position_id,))
        deleted = cursor.rowcount > 0

        conn.commit()
        conn.close()
        return deleted


def process_trades_into_closed_positions(account_id):
    """
    Process all trades for an account and generate closed position records.
    This groups trades by symbol and calculates complete position cycles.
    """
    with db_lock:
        conn = get_connection()
        cursor = conn.cursor()

        # Get all trades for the account, ordered by time
        cursor.execute('''
            SELECT * FROM trades
            WHERE account_id = ?
            ORDER BY symbol, trade_time ASC
        ''', (account_id,))

        trades = cursor.fetchall()

        # Clear existing closed positions for this account
        cursor.execute('DELETE FROM closed_positions WHERE account_id = ?', (account_id,))

        # Group trades by symbol
        trades_by_symbol = {}
        for trade in trades:
            symbol = trade['symbol']
            if symbol not in trades_by_symbol:
                trades_by_symbol[symbol] = []
            trades_by_symbol[symbol].append(dict(trade))

        # Process each symbol's trades to find closed positions
        for symbol, symbol_trades in trades_by_symbol.items():
            position_qty = 0
            position_side = None
            entry_trades = []
            total_entry_cost = 0
            total_commission = 0

            for trade in symbol_trades:
                trade_qty = float(trade['quantity'])
                trade_price = float(trade['price'])
                trade_side = trade['side']
                trade_pnl = float(trade['realized_pnl'] or 0)
                trade_commission = float(trade['commission'] or 0)

                # Determine if this is opening or closing a position
                # BUY increases position (opens LONG or closes SHORT)
                # SELL decreases position (opens SHORT or closes LONG)

                if position_qty == 0:
                    # Starting a new position
                    position_side = 'LONG' if trade_side == 'BUY' else 'SHORT'
                    position_qty = trade_qty
                    entry_trades = [trade]
                    total_entry_cost = trade_qty * trade_price
                    total_commission = trade_commission
                elif (position_side == 'LONG' and trade_side == 'BUY') or \
                     (position_side == 'SHORT' and trade_side == 'SELL'):
                    # Adding to position
                    position_qty += trade_qty
                    entry_trades.append(trade)
                    total_entry_cost += trade_qty * trade_price
                    total_commission += trade_commission
                else:
                    # Closing position (partially or fully)
                    close_qty = min(trade_qty, position_qty)
                    total_commission += trade_commission

                    if close_qty > 0:
                        # Calculate weighted average entry price
                        total_entry_qty = sum(float(t['quantity']) for t in entry_trades)
                        avg_entry_price = total_entry_cost / total_entry_qty if total_entry_qty > 0 else 0

                        # Calculate P&L for this close
                        # Use the realized_pnl from Binance if available (it's more accurate)
                        pnl = trade_pnl

                        # If no realized_pnl from trade, calculate it
                        if pnl == 0 and avg_entry_price > 0:
                            if position_side == 'LONG':
                                pnl = (trade_price - avg_entry_price) * close_qty
                            else:
                                pnl = (avg_entry_price - trade_price) * close_qty

                        # Get entry and exit times
                        entry_time = entry_trades[0]['trade_time'] if entry_trades else None
                        exit_time = trade['trade_time']

                        # Calculate duration
                        duration_seconds = None
                        if entry_time and exit_time:
                            try:
                                entry_dt = datetime.fromisoformat(entry_time.replace('Z', '+00:00')) if isinstance(entry_time, str) else entry_time
                                exit_dt = datetime.fromisoformat(exit_time.replace('Z', '+00:00')) if isinstance(exit_time, str) else exit_time
                                if hasattr(entry_dt, 'timestamp') and hasattr(exit_dt, 'timestamp'):
                                    duration_seconds = int(exit_dt.timestamp() - entry_dt.timestamp())
                            except:
                                pass

                        # Get trade IDs
                        trade_ids = [str(t['exchange_trade_id']) for t in entry_trades]
                        trade_ids.append(str(trade['exchange_trade_id']))
                        trade_ids_str = ','.join(trade_ids)

                        # Calculate position size in USD
                        size_usd = close_qty * avg_entry_price

                        # Insert closed position
                        cursor.execute('''
                            INSERT INTO closed_positions (
                                account_id, symbol, side, quantity, entry_price, exit_price, size_usd,
                                realized_pnl, commission, entry_time, exit_time, duration_seconds, trade_ids
                            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        ''', (account_id, symbol, position_side, close_qty, avg_entry_price, trade_price, size_usd,
                              pnl, total_commission, entry_time, exit_time, duration_seconds, trade_ids_str))

                    # Update remaining position
                    position_qty -= close_qty
                    remaining_to_close = trade_qty - close_qty

                    if position_qty <= 0.00001:  # Position fully closed (use small epsilon for float comparison)
                        position_qty = 0

                        # If there's remaining quantity from this trade, it opens a new position
                        if remaining_to_close > 0.00001:
                            position_side = 'LONG' if trade_side == 'BUY' else 'SHORT'
                            position_qty = remaining_to_close
                            entry_trades = [trade]
                            total_entry_cost = remaining_to_close * trade_price
                            total_commission = 0
                        else:
                            position_side = None
                            entry_trades = []
                            total_entry_cost = 0
                            total_commission = 0
                    else:
                        # Position partially closed, adjust entry data proportionally
                        close_ratio = close_qty / (position_qty + close_qty)
                        total_entry_cost *= (1 - close_ratio)

        conn.commit()
        conn.close()
        return True


def get_closed_positions_stats(account_id):
    """Get statistics for closed positions."""
    with db_lock:
        conn = get_connection()
        cursor = conn.cursor()

        cursor.execute('''
            SELECT
                COUNT(*) as total_positions,
                COALESCE(SUM(realized_pnl), 0) as total_pnl,
                COALESCE(SUM(commission), 0) as total_commission,
                COALESCE(SUM(quantity * entry_price), 0) as total_volume,
                SUM(CASE WHEN realized_pnl > 0 THEN 1 ELSE 0 END) as winning_positions,
                SUM(CASE WHEN realized_pnl < 0 THEN 1 ELSE 0 END) as losing_positions,
                SUM(CASE WHEN realized_pnl = 0 THEN 1 ELSE 0 END) as breakeven_positions,
                COALESCE(AVG(CASE WHEN realized_pnl > 0 THEN realized_pnl END), 0) as avg_win,
                COALESCE(AVG(CASE WHEN realized_pnl < 0 THEN realized_pnl END), 0) as avg_loss,
                COALESCE(MAX(realized_pnl), 0) as largest_win,
                COALESCE(MIN(realized_pnl), 0) as largest_loss,
                COALESCE(AVG(duration_seconds), 0) as avg_duration
            FROM closed_positions
            WHERE account_id = ?
        ''', (account_id,))

        row = cursor.fetchone()
        conn.close()

        if row:
            total = row['total_positions'] or 0
            winning = row['winning_positions'] or 0
            losing = row['losing_positions'] or 0

            return {
                'total_positions': total,
                'total_pnl': round(row['total_pnl'] or 0, 2),
                'total_commission': round(row['total_commission'] or 0, 2),
                'total_volume': round(row['total_volume'] or 0, 2),
                'winning_positions': winning,
                'losing_positions': losing,
                'breakeven_positions': row['breakeven_positions'] or 0,
                'win_rate': round(winning / total * 100, 1) if total > 0 else 0,
                'avg_win': round(row['avg_win'] or 0, 2),
                'avg_loss': round(row['avg_loss'] or 0, 2),
                'largest_win': round(row['largest_win'] or 0, 2),
                'largest_loss': round(row['largest_loss'] or 0, 2),
                'avg_duration_seconds': int(row['avg_duration'] or 0)
            }

        return None


# Initialize database on module load
init_db()
