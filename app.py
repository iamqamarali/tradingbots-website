"""
Trading Bot Script Manager
A Flask web application to manage, run, and monitor Python trading bot scripts.
"""

from flask import Flask, render_template, request, jsonify
import os
import subprocess
import signal
import sys
import uuid
import json
from datetime import datetime, timedelta
from threading import Thread, Lock
import time
import atexit

# Import database module for trade tracking
import database as db

# Binance API for account sync
try:
    from binance.client import Client as BinanceClient
    from binance.exceptions import BinanceAPIException
    BINANCE_AVAILABLE = True
except ImportError:
    BINANCE_AVAILABLE = False
    print("[WARNING] binance-python not installed. Account sync disabled.")

app = Flask(__name__)

# Configuration
SCRIPTS_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'scripts')
METADATA_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'scripts_metadata.json')
LOGS_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'logs')

# Ensure folders exist
os.makedirs(SCRIPTS_FOLDER, exist_ok=True)
os.makedirs(LOGS_FOLDER, exist_ok=True)

# Store running processes
running_processes = {}
process_lock = Lock()

# Store script output logs (in-memory buffer, also written to files)
script_logs = {}
logs_lock = Lock()

# Last log clear date
last_clear_date = datetime.now().date()


def get_log_file_path(script_id):
    """Get the log file path for a script."""
    return os.path.join(LOGS_FOLDER, f"{script_id}.log")


def write_log_to_file(script_id, message):
    """Write a log message to the script's log file."""
    log_file = get_log_file_path(script_id)
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    with open(log_file, 'a', encoding='utf-8') as f:
        f.write(f"[{timestamp}] {message}\n")


def load_logs_from_file(script_id, limit=500):
    """Load logs from file for a script."""
    log_file = get_log_file_path(script_id)
    if os.path.exists(log_file):
        try:
            with open(log_file, 'r', encoding='utf-8') as f:
                lines = f.readlines()
                return [line.strip() for line in lines[-limit:]]
        except:
            return []
    return []


def clear_old_logs():
    """Clear all logs older than a day."""
    global last_clear_date
    
    today = datetime.now().date()
    if today > last_clear_date:
        # Delete all log files (they're from yesterday or older)
        for filename in os.listdir(LOGS_FOLDER):
            if filename.endswith('.log'):
                filepath = os.path.join(LOGS_FOLDER, filename)
                try:
                    os.remove(filepath)
                except:
                    pass
        
        # Clear in-memory logs
        with logs_lock:
            script_logs.clear()
        
        last_clear_date = today
        print(f"[{datetime.now()}] Daily log cleanup completed - old logs deleted")


def log_cleanup_scheduler():
    """Background thread to check and clear logs daily."""
    while True:
        try:
            clear_old_logs()
        except Exception as e:
            print(f"Log cleanup error: {e}")
        time.sleep(3600)  # Check every hour


# Start the cleanup scheduler
cleanup_thread = Thread(target=log_cleanup_scheduler, daemon=True)
cleanup_thread.start()


def load_metadata():
    """Load scripts metadata from JSON file."""
    if os.path.exists(METADATA_FILE):
        try:
            with open(METADATA_FILE, 'r') as f:
                return json.load(f)
        except:
            return {}
    return {}


def save_metadata(metadata):
    """Save scripts metadata to JSON file."""
    with open(METADATA_FILE, 'w') as f:
        json.dump(metadata, f, indent=2)


def get_all_scripts():
    """Get all scripts with their metadata and running status."""
    metadata = load_metadata()
    scripts = []
    
    for filename in os.listdir(SCRIPTS_FOLDER):
        if filename.endswith('.py'):
            script_id = filename[:-3]  # Remove .py extension
            script_info = metadata.get(script_id, {})
            
            with process_lock:
                is_running = script_id in running_processes and running_processes[script_id].poll() is None
            
            scripts.append({
                'id': script_id,
                'name': script_info.get('name', filename),
                'filename': filename,
                'status': 'running' if is_running else 'stopped',
                'created': script_info.get('created', 'Unknown'),
                'description': script_info.get('description', ''),
                'auto_restart': script_info.get('auto_restart', False)
            })
    
    return scripts


def read_output(process, script_id):
    """Read process output in a separate thread and log indefinitely."""
    try:
        for line in iter(process.stdout.readline, ''):
            if not line:
                break
                
            message = line.strip()
            if message:
                with logs_lock:
                    if script_id not in script_logs:
                        script_logs[script_id] = []
                    
                    timestamp = datetime.now().strftime('%H:%M:%S')
                    log_entry = f"[{timestamp}] {message}"
                    script_logs[script_id].append(log_entry)
                    
                    # Keep only last 500 lines in memory
                    if len(script_logs[script_id]) > 500:
                        script_logs[script_id] = script_logs[script_id][-500:]
                
                # Also write to file
                write_log_to_file(script_id, message)
                
    except Exception as e:
        write_log_to_file(script_id, f"[ERROR] Output reading error: {e}")
    finally:
        # Log when process ends
        with process_lock:
            if script_id in running_processes:
                exit_code = process.poll()
                write_log_to_file(script_id, f"[SYSTEM] Process ended with exit code: {exit_code}")


def start_script_process(script_id):
    """Start a script process. Returns True if successful, False otherwise."""
    filename = f"{script_id}.py"
    filepath = os.path.join(SCRIPTS_FOLDER, filename)
    
    if not os.path.exists(filepath):
        return False
    
    with process_lock:
        # Check if already running
        if script_id in running_processes:
            if running_processes[script_id].poll() is None:
                return True  # Already running
            else:
                del running_processes[script_id]
    
    try:
        # Create startup info for Windows to run without console window
        startupinfo = None
        creationflags = 0
        
        if sys.platform == 'win32':
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = subprocess.SW_HIDE
            creationflags = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW
        
        # Start the process
        process = subprocess.Popen(
            [sys.executable, '-u', filepath],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            startupinfo=startupinfo,
            creationflags=creationflags,
            cwd=SCRIPTS_FOLDER
        )
        
        with process_lock:
            running_processes[script_id] = process
        
        with logs_lock:
            script_logs[script_id] = []
        
        # Start output reading thread
        thread = Thread(target=read_output, args=(process, script_id), daemon=True)
        thread.start()
        
        return True
        
    except Exception as e:
        write_log_to_file(script_id, f"[ERROR] Failed to start script: {e}")
        return False


def restart_persistent_scripts():
    """Restart scripts that were running before or have auto_restart enabled."""
    metadata = load_metadata()
    restarted = []
    
    for script_id, script_info in metadata.items():
        # Check if script file exists
        filepath = os.path.join(SCRIPTS_FOLDER, f"{script_id}.py")
        if not os.path.exists(filepath):
            continue
        
        # Check if should restart (was_running OR auto_restart)
        was_running = script_info.get('was_running', False)
        auto_restart = script_info.get('auto_restart', False)
        
        if was_running or auto_restart:
            if start_script_process(script_id):
                write_log_to_file(script_id, "[SYSTEM] Script auto-restarted on server startup")
                restarted.append(script_info.get('name', script_id))
                # Update was_running state
                metadata[script_id]['was_running'] = True
    
    if restarted:
        save_metadata(metadata)
        print(f"  Auto-restarted scripts: {', '.join(restarted)}")
    
    return restarted


@app.route('/')
def index():
    """Render the main page."""
    return render_template('index.html')


@app.route('/logs')
def logs_page():
    """Render the logs page."""
    return render_template('logs.html')


@app.route('/api/scripts', methods=['GET'])
def get_scripts():
    """Get all scripts."""
    return jsonify(get_all_scripts())


@app.route('/api/scripts', methods=['POST'])
def upload_script():
    """Upload a new script."""
    data = request.json
    
    if not data:
        return jsonify({'error': 'No data provided'}), 400
    
    script_name = data.get('name', 'Untitled Script')
    script_content = data.get('content', '')
    description = data.get('description', '')
    
    if not script_content.strip():
        return jsonify({'error': 'Script content is empty'}), 400
    
    # Generate unique ID
    script_id = str(uuid.uuid4())[:8]
    filename = f"{script_id}.py"
    filepath = os.path.join(SCRIPTS_FOLDER, filename)
    
    # Save script file
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(script_content)
    
    # Update metadata
    metadata = load_metadata()
    metadata[script_id] = {
        'name': script_name,
        'description': description,
        'created': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    }
    save_metadata(metadata)
    
    # Create bot record in database (symbol will be set when script calls register_bot)
    db.create_bot(script_id, script_name, symbol='')
    
    return jsonify({
        'success': True,
        'script': {
            'id': script_id,
            'name': script_name,
            'filename': filename,
            'status': 'stopped',
            'created': metadata[script_id]['created'],
            'description': description
        }
    })


@app.route('/api/scripts/<script_id>', methods=['GET'])
def get_script(script_id):
    """Get a specific script's content."""
    filename = f"{script_id}.py"
    filepath = os.path.join(SCRIPTS_FOLDER, filename)
    
    if not os.path.exists(filepath):
        return jsonify({'error': 'Script not found'}), 404
    
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    
    metadata = load_metadata()
    script_info = metadata.get(script_id, {})
    
    with process_lock:
        is_running = script_id in running_processes and running_processes[script_id].poll() is None
    
    return jsonify({
        'id': script_id,
        'name': script_info.get('name', filename),
        'content': content,
        'description': script_info.get('description', ''),
        'status': 'running' if is_running else 'stopped',
        'auto_restart': script_info.get('auto_restart', False)
    })


@app.route('/api/scripts/<script_id>', methods=['PUT'])
def update_script(script_id):
    """Update a script's content or metadata."""
    data = request.json
    filename = f"{script_id}.py"
    filepath = os.path.join(SCRIPTS_FOLDER, filename)
    
    if not os.path.exists(filepath):
        return jsonify({'error': 'Script not found'}), 404
    
    # Update content if provided
    if 'content' in data:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(data['content'])
    
    # Update metadata
    metadata = load_metadata()
    if script_id not in metadata:
        metadata[script_id] = {}
    
    if 'name' in data:
        metadata[script_id]['name'] = data['name']
    if 'description' in data:
        metadata[script_id]['description'] = data['description']
    
    save_metadata(metadata)
    
    return jsonify({'success': True})


@app.route('/api/scripts/<script_id>', methods=['DELETE'])
def delete_script(script_id):
    """Delete a script file and metadata (keeps database record for trade history)."""
    filename = f"{script_id}.py"
    filepath = os.path.join(SCRIPTS_FOLDER, filename)
    
    if not os.path.exists(filepath):
        return jsonify({'error': 'Script not found'}), 404
    
    # Stop if running
    stop_script_process(script_id)
    
    # Delete file
    os.remove(filepath)
    
    # Delete log file if exists
    log_file = get_log_file_path(script_id)
    if os.path.exists(log_file):
        os.remove(log_file)
    
    # Remove metadata (JSON file only)
    metadata = load_metadata()
    if script_id in metadata:
        del metadata[script_id]
        save_metadata(metadata)
    
    # Clear in-memory logs
    with logs_lock:
        if script_id in script_logs:
            del script_logs[script_id]
    
    # NOTE: Database record (bot + trades) is intentionally kept for historical tracking
    # Use the Bots page (/bots) to delete a bot and all its trade history
    
    return jsonify({'success': True})


@app.route('/api/scripts/<script_id>/run', methods=['POST'])
def run_script(script_id):
    """Run a script in the background indefinitely."""
    filename = f"{script_id}.py"
    filepath = os.path.join(SCRIPTS_FOLDER, filename)
    
    if not os.path.exists(filepath):
        return jsonify({'error': 'Script not found'}), 404
    
    with process_lock:
        # Check if already running
        if script_id in running_processes:
            if running_processes[script_id].poll() is None:
                return jsonify({'error': 'Script is already running'}), 400
            else:
                # Process ended, clean up
                del running_processes[script_id]
    
    try:
        # Create startup info for Windows to run without console window
        startupinfo = None
        creationflags = 0
        
        if sys.platform == 'win32':
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = subprocess.SW_HIDE
            creationflags = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW
        
        # Start the process - runs indefinitely in background
        process = subprocess.Popen(
            [sys.executable, '-u', filepath],  # -u for unbuffered output
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            startupinfo=startupinfo,
            creationflags=creationflags,
            cwd=SCRIPTS_FOLDER
        )
        
        with process_lock:
            running_processes[script_id] = process
        
        with logs_lock:
            script_logs[script_id] = []
        
        # Log start
        write_log_to_file(script_id, "[SYSTEM] Script started")
        
        # Save was_running state to metadata
        metadata = load_metadata()
        if script_id not in metadata:
            metadata[script_id] = {}
        metadata[script_id]['was_running'] = True
        save_metadata(metadata)
        
        # Start output reading thread (daemon so it doesn't block shutdown)
        thread = Thread(target=read_output, args=(process, script_id), daemon=True)
        thread.start()
        
        return jsonify({'success': True, 'status': 'running', 'pid': process.pid})
    
    except Exception as e:
        return jsonify({'error': str(e)}), 500


def stop_script_process(script_id):
    """Stop a running script process."""
    with process_lock:
        if script_id in running_processes:
            process = running_processes[script_id]
            try:
                if process.poll() is None:  # Still running
                    if sys.platform == 'win32':
                        # On Windows, terminate the process tree
                        subprocess.run(['taskkill', '/F', '/T', '/PID', str(process.pid)], 
                                      capture_output=True)
                    else:
                        process.terminate()
                        try:
                            process.wait(timeout=5)
                        except subprocess.TimeoutExpired:
                            process.kill()
                    
                    write_log_to_file(script_id, "[SYSTEM] Script stopped by user")
            except Exception as e:
                write_log_to_file(script_id, f"[SYSTEM] Error stopping script: {e}")
            finally:
                del running_processes[script_id]


@app.route('/api/scripts/<script_id>/stop', methods=['POST'])
def stop_script(script_id):
    """Stop a running script."""
    with process_lock:
        if script_id not in running_processes:
            return jsonify({'error': 'Script is not running'}), 400
        
        if running_processes[script_id].poll() is not None:
            # Already stopped
            del running_processes[script_id]
            # Update was_running in metadata
            metadata = load_metadata()
            if script_id in metadata:
                metadata[script_id]['was_running'] = False
                save_metadata(metadata)
            return jsonify({'success': True, 'status': 'stopped'})
    
    try:
        stop_script_process(script_id)
        # Update was_running in metadata
        metadata = load_metadata()
        if script_id in metadata:
            metadata[script_id]['was_running'] = False
            save_metadata(metadata)
        return jsonify({'success': True, 'status': 'stopped'})
    
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/scripts/<script_id>/auto-restart', methods=['PUT'])
def toggle_auto_restart(script_id):
    """Toggle auto-restart setting for a script."""
    filename = f"{script_id}.py"
    filepath = os.path.join(SCRIPTS_FOLDER, filename)
    
    if not os.path.exists(filepath):
        return jsonify({'error': 'Script not found'}), 404
    
    metadata = load_metadata()
    if script_id not in metadata:
        metadata[script_id] = {}
    
    # Toggle the auto_restart value
    current_value = metadata[script_id].get('auto_restart', False)
    metadata[script_id]['auto_restart'] = not current_value
    save_metadata(metadata)
    
    return jsonify({
        'success': True,
        'auto_restart': metadata[script_id]['auto_restart']
    })


@app.route('/api/scripts/<script_id>/logs', methods=['GET'])
def get_logs(script_id):
    """Get script logs."""
    # First check in-memory logs
    with logs_lock:
        memory_logs = script_logs.get(script_id, [])
    
    # If empty, try loading from file
    if not memory_logs:
        memory_logs = load_logs_from_file(script_id)
    
    return jsonify({'logs': memory_logs})


@app.route('/api/scripts/<script_id>/logs', methods=['DELETE'])
def clear_script_logs(script_id):
    """Clear logs for a specific script."""
    # Clear in-memory logs
    with logs_lock:
        if script_id in script_logs:
            script_logs[script_id] = []
    
    # Clear log file
    log_file = get_log_file_path(script_id)
    if os.path.exists(log_file):
        open(log_file, 'w').close()  # Truncate file
    
    return jsonify({'success': True})


@app.route('/api/logs', methods=['GET'])
def get_all_logs():
    """Get logs for all scripts."""
    all_logs = {}
    metadata = load_metadata()
    
    for filename in os.listdir(SCRIPTS_FOLDER):
        if filename.endswith('.py'):
            script_id = filename[:-3]
            script_info = metadata.get(script_id, {})
            
            # Get logs
            with logs_lock:
                logs = script_logs.get(script_id, [])
            
            if not logs:
                logs = load_logs_from_file(script_id, limit=100)
            
            with process_lock:
                is_running = script_id in running_processes and running_processes[script_id].poll() is None
            
            all_logs[script_id] = {
                'name': script_info.get('name', filename),
                'status': 'running' if is_running else 'stopped',
                'logs': logs[-100:]  # Last 100 entries
            }
    
    return jsonify(all_logs)


@app.route('/api/logs', methods=['DELETE'])
def clear_all_logs():
    """Clear all logs."""
    # Clear in-memory logs
    with logs_lock:
        script_logs.clear()
    
    # Clear all log files
    for filename in os.listdir(LOGS_FOLDER):
        if filename.endswith('.log'):
            filepath = os.path.join(LOGS_FOLDER, filename)
            try:
                open(filepath, 'w').close()
            except:
                pass
    
    return jsonify({'success': True, 'message': 'All logs cleared'})


@app.route('/api/status', methods=['GET'])
def get_status():
    """Get overall system status."""
    scripts = get_all_scripts()
    running = sum(1 for s in scripts if s['status'] == 'running')
    
    return jsonify({
        'total_scripts': len(scripts),
        'running_scripts': running,
        'stopped_scripts': len(scripts) - running,
        'server_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'next_log_clear': (datetime.now().date() + timedelta(days=1)).strftime('%Y-%m-%d 00:00:00')
    })


# ==================== PAGES ====================

@app.route('/accounts')
def accounts_page():
    """Render the accounts page."""
    return render_template('accounts.html')


@app.route('/accounts/<int:account_id>')
def account_detail_page(account_id):
    """Render the account detail page."""
    account = db.get_account(account_id)
    if not account:
        return "Account not found", 404
    return render_template('account_detail.html', account_id=account_id)


@app.route('/bots')
def bots_page():
    """Render the bots page."""
    return render_template('bots.html')


# ==================== ACCOUNTS API ====================

@app.route('/api/accounts', methods=['GET'])
def api_get_accounts():
    """Get all accounts."""
    accounts = db.get_all_accounts()
    # Don't expose full API keys/secrets in list view
    for acc in accounts:
        del acc['api_key_full']
        del acc['api_secret']
    return jsonify(accounts)


@app.route('/api/accounts', methods=['POST'])
def api_create_account():
    """Create a new account."""
    data = request.json
    if not data:
        return jsonify({'error': 'No data provided'}), 400
    
    name = data.get('name', '').strip()
    api_key = data.get('api_key', '').strip()
    api_secret = data.get('api_secret', '').strip()
    is_testnet = data.get('is_testnet', False)
    
    if not name or not api_key or not api_secret:
        return jsonify({'error': 'Name, API key, and API secret are required'}), 400
    
    # Test the API connection
    if BINANCE_AVAILABLE:
        try:
            client = BinanceClient(api_key, api_secret, testnet=is_testnet)
            if is_testnet:
                client.FUTURES_URL = 'https://testnet.binancefuture.com/fapi'
            # Test connection
            client.futures_account_balance()
        except BinanceAPIException as e:
            return jsonify({'error': f'Invalid API credentials: {e.message}'}), 400
        except Exception as e:
            return jsonify({'error': f'Connection failed: {str(e)}'}), 400
    
    account_id = db.create_account(name, api_key, api_secret, is_testnet)
    
    return jsonify({
        'success': True,
        'account_id': account_id,
        'message': f'Account "{name}" created successfully'
    })


@app.route('/api/accounts/<int:account_id>', methods=['GET'])
def api_get_account(account_id):
    """Get a specific account."""
    account = db.get_account(account_id)
    if account:
        # Mask the secrets
        account['api_key'] = account['api_key'][:8] + '...' if account['api_key'] else ''
        del account['api_secret']
        return jsonify(account)
    return jsonify({'error': 'Account not found'}), 404


@app.route('/api/accounts/<int:account_id>', methods=['DELETE'])
def api_delete_account(account_id):
    """Delete an account and all its trades."""
    if db.delete_account(account_id):
        return jsonify({'success': True})
    return jsonify({'error': 'Account not found'}), 404


@app.route('/api/accounts/<int:account_id>/balance', methods=['GET'])
def api_get_account_balance(account_id):
    """Get account balance from Binance."""
    print(f"=== GET BALANCE for account_id: {account_id} ===")

    if not BINANCE_AVAILABLE:
        print("ERROR: Binance API not available")
        return jsonify({'error': 'Binance API not available'}), 500

    account = db.get_account(account_id)
    if not account:
        print(f"ERROR: Account {account_id} not found")
        return jsonify({'error': 'Account not found'}), 404

    print(f"Account: {account['name']}, is_testnet: {account['is_testnet']}")

    try:
        client = BinanceClient(account['api_key'], account['api_secret'], testnet=account['is_testnet'])
        if account['is_testnet']:
            client.FUTURES_URL = 'https://testnet.binancefuture.com/fapi'
            print(f"Using testnet URL: {client.FUTURES_URL}")

        print("Fetching futures account balance...")
        balances = client.futures_account_balance()
        print(f"Got {len(balances)} balance entries")

        usdt_balance = 0
        for bal in balances:
            if bal['asset'] == 'USDT':
                usdt_balance = float(bal['balance'])
                print(f"USDT balance found: {usdt_balance}")
                break

        return jsonify({
            'balance': round(usdt_balance, 2),
            'asset': 'USDT'
        })
    except BinanceAPIException as e:
        print(f"BinanceAPIException: {e}")
        return jsonify({'error': f'Binance error: {e.message}'}), 500
    except Exception as e:
        print(f"Exception: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@app.route('/api/accounts/<int:account_id>/positions', methods=['GET'])
def api_get_account_positions(account_id):
    """Get open positions from Binance."""
    print(f"=== GET POSITIONS for account_id: {account_id} ===")

    if not BINANCE_AVAILABLE:
        print("ERROR: Binance API not available")
        return jsonify({'error': 'Binance API not available'}), 500

    account = db.get_account(account_id)
    if not account:
        print(f"ERROR: Account {account_id} not found")
        return jsonify({'error': 'Account not found'}), 404

    print(f"Account: {account['name']}, is_testnet: {account['is_testnet']}")

    try:
        client = BinanceClient(account['api_key'], account['api_secret'], testnet=account['is_testnet'])
        if account['is_testnet']:
            client.FUTURES_URL = 'https://testnet.binancefuture.com/fapi'
            print(f"Using testnet URL: {client.FUTURES_URL}")

        print("Fetching futures position information...")
        positions = client.futures_position_information()
        print(f"Got {len(positions)} position entries")

        open_positions = []

        for pos in positions:
            amt = float(pos['positionAmt'])
            if amt != 0:
                entry_price = float(pos['entryPrice'])
                mark_price = float(pos['markPrice'])
                unrealized_pnl = float(pos['unRealizedProfit'])

                print(f"  Open position: {pos['symbol']} amt={amt} pnl={unrealized_pnl}")
                open_positions.append({
                    'symbol': pos['symbol'],
                    'side': 'LONG' if amt > 0 else 'SHORT',
                    'quantity': abs(amt),
                    'entry_price': entry_price,
                    'mark_price': mark_price,
                    'unrealized_pnl': round(unrealized_pnl, 2),
                    'leverage': int(pos.get('leverage', 5))
                })

        print(f"Returning {len(open_positions)} open positions")
        return jsonify(open_positions)
    except BinanceAPIException as e:
        print(f"BinanceAPIException: {e}")
        return jsonify({'error': f'Binance error: {e.message}'}), 500
    except Exception as e:
        print(f"Exception: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@app.route('/api/accounts/<int:account_id>/close-all', methods=['POST'])
def api_close_all_positions(account_id):
    """Close all open positions for an account."""
    if not BINANCE_AVAILABLE:
        return jsonify({'error': 'Binance API not available'}), 500
    
    account = db.get_account(account_id)
    if not account:
        return jsonify({'error': 'Account not found'}), 404
    
    try:
        client = BinanceClient(account['api_key'], account['api_secret'], testnet=account['is_testnet'])
        if account['is_testnet']:
            client.FUTURES_URL = 'https://testnet.binancefuture.com/fapi'
        
        positions = client.futures_position_information()
        closed = []
        errors = []
        
        for pos in positions:
            amt = float(pos['positionAmt'])
            if amt != 0:
                symbol = pos['symbol']
                try:
                    # Close by placing opposite market order
                    side = 'SELL' if amt > 0 else 'BUY'
                    client.futures_create_order(
                        symbol=symbol,
                        side=side,
                        type='MARKET',
                        quantity=abs(amt),
                        reduceOnly='true'
                    )
                    closed.append(symbol)
                except Exception as e:
                    errors.append(f'{symbol}: {str(e)}')
        
        return jsonify({
            'success': True,
            'closed': closed,
            'errors': errors
        })
    except BinanceAPIException as e:
        return jsonify({'error': f'Binance error: {e.message}'}), 500
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/accounts/<int:account_id>/sync', methods=['POST'])
def api_sync_account_trades(account_id):
    """Sync ALL historical trades from Binance."""
    print(f"=== SYNC TRADES CALLED for account_id: {account_id} ===")

    if not BINANCE_AVAILABLE:
        print("ERROR: Binance API not available")
        return jsonify({'error': 'Binance API not available'}), 500

    account = db.get_account(account_id)
    if not account:
        print(f"ERROR: Account {account_id} not found")
        return jsonify({'error': 'Account not found'}), 404

    print(f"Account found: {account['name']}, is_testnet: {account['is_testnet']}")
    print(f"API Key (first 10 chars): {account['api_key'][:10]}...")

    try:
        print("Creating Binance client...")
        client = BinanceClient(account['api_key'], account['api_secret'], testnet=account['is_testnet'])
        if account['is_testnet']:
            # Correct testnet futures URL
            client.FUTURES_URL = 'https://testnet.binancefuture.com/fapi'
            print(f"Using testnet URL: {client.FUTURES_URL}")
        else:
            print(f"Using mainnet URL: {client.FUTURES_URL}")

        # Get trades from last 7 days
        end_time = int(datetime.now().timestamp() * 1000)
        start_time = int((datetime.now() - timedelta(days=7)).timestamp() * 1000)
        print(f"Time range: last 7 days")

        # Get all symbols with positions or recent activity
        print("Fetching exchange info...")
        exchange_info = client.futures_exchange_info()
        all_symbols = [s['symbol'] for s in exchange_info['symbols'] if s['status'] == 'TRADING']
        print(f"Found {len(all_symbols)} trading symbols on exchange")

        new_trades = 0
        total_checked = 0

        # Get symbols from current positions
        print("Fetching current positions to find active symbols...")
        symbols_to_sync = set()
        try:
            positions = client.futures_position_information()
            for pos in positions:
                amt = float(pos['positionAmt'])
                if amt != 0:
                    symbols_to_sync.add(pos['symbol'])
                    print(f"  Found open position in {pos['symbol']}")
        except Exception as e:
            print(f"Warning: Could not fetch positions: {e}")

        # Check BTC, ETH, SOL, DOGE pairs (USDT and USDC)
        priority_symbols = ['BTCUSDT', 'ETHUSDT', 'SOLUSDT', 'DOGEUSDT',
                          'BTCUSDC', 'ETHUSDC', 'SOLUSDC', 'DOGEUSDC']
        symbols_to_sync.update(priority_symbols)

        print(f"Will sync {len(symbols_to_sync)} symbols: {symbols_to_sync}")

        for symbol in symbols_to_sync:
            if symbol not in all_symbols:
                print(f"Skipping {symbol} - not in exchange symbols")
                continue

            try:
                print(f"Fetching trades for {symbol}...")
                trades = client.futures_account_trades(
                    symbol=symbol,
                    startTime=start_time,
                    endTime=end_time,
                    limit=1000
                )
                print(f"  Found {len(trades)} trades for {symbol}")

                for trade in trades:
                    total_checked += 1

                    # Insert trade (will skip if already exists based on exchange_trade_id)
                    inserted = db.insert_trade(
                        account_id=account_id,
                        exchange_trade_id=trade['id'],
                        order_id=trade['orderId'],
                        symbol=trade['symbol'],
                        side=trade['side'],
                        quantity=float(trade['qty']),
                        price=float(trade['price']),
                        realized_pnl=float(trade['realizedPnl']),
                        commission=float(trade['commission']),
                        commission_asset=trade['commissionAsset'],
                        trade_time=datetime.fromtimestamp(trade['time'] / 1000).isoformat()
                    )

                    if inserted:
                        new_trades += 1

            except BinanceAPIException as e:
                if 'Invalid symbol' not in str(e):
                    print(f"BinanceAPIException syncing {symbol}: {e}")
            except Exception as e:
                print(f"Exception syncing {symbol}: {e}")

        # Update account stats in database
        print("Updating account stats...")
        db.update_account_stats(account_id)

        # Get updated stats to return
        stats = db.get_trade_stats(account_id)

        print(f"=== SYNC COMPLETE: {new_trades} new trades, {total_checked} total checked ===")
        return jsonify({
            'success': True,
            'new_trades': new_trades,
            'total_checked': total_checked,
            'message': f'Synced {new_trades} new trades',
            'stats': stats
        })
    except BinanceAPIException as e:
        print(f"BinanceAPIException: {e}")
        return jsonify({'error': f'Binance error: {e.message}'}), 500
    except Exception as e:
        print(f"Exception: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


# ==================== BOTS API ====================

@app.route('/api/bots', methods=['GET'])
def api_get_bots():
    """Get all bots."""
    bots = db.get_all_bots()
    return jsonify(bots)


@app.route('/api/bots/<int:bot_id>', methods=['GET'])
def api_get_bot(bot_id):
    """Get a specific bot."""
    bot = db.get_bot(bot_id)
    if bot:
        return jsonify(bot)
    return jsonify({'error': 'Bot not found'}), 404


@app.route('/api/bots/<int:bot_id>', methods=['PUT'])
def api_update_bot(bot_id):
    """Update a bot (e.g., link to account)."""
    data = request.json
    if not data:
        return jsonify({'error': 'No data provided'}), 400
    
    bot = db.get_bot(bot_id)
    if not bot:
        return jsonify({'error': 'Bot not found'}), 404
    
    account_id = data.get('account_id')
    
    # Validate account exists if provided
    if account_id is not None and account_id != '':
        account = db.get_account(int(account_id))
        if not account:
            return jsonify({'error': 'Account not found'}), 404
    
    if db.update_bot(bot_id, account_id=account_id if account_id else None):
        return jsonify({'success': True})
    return jsonify({'error': 'Failed to update bot'}), 500


@app.route('/api/bots/<int:bot_id>', methods=['DELETE'])
def api_delete_bot(bot_id):
    """Delete a bot and the script file if it exists."""
    bot = db.get_bot(bot_id)
    if not bot:
        return jsonify({'error': 'Bot not found'}), 404
    
    script_id = bot.get('script_id')
    
    if not db.delete_bot(bot_id):
        return jsonify({'error': 'Failed to delete bot'}), 500
    
    # Also delete the script file if it exists
    if script_id:
        filename = f"{script_id}.py"
        filepath = os.path.join(SCRIPTS_FOLDER, filename)
        
        if os.path.exists(filepath):
            stop_script_process(script_id)
            os.remove(filepath)
            
            log_file = get_log_file_path(script_id)
            if os.path.exists(log_file):
                os.remove(log_file)
            
            metadata = load_metadata()
            if script_id in metadata:
                del metadata[script_id]
                save_metadata(metadata)
            
            with logs_lock:
                if script_id in script_logs:
                    del script_logs[script_id]
    
    return jsonify({'success': True})


# ==================== TRADES API ====================

@app.route('/api/trades', methods=['GET'])
def api_get_trades():
    """Get all trades with optional filters."""
    account_id = request.args.get('account_id', None, type=int)
    symbol = request.args.get('symbol', None)
    limit = request.args.get('limit', 100, type=int)
    offset = request.args.get('offset', 0, type=int)
    
    trades = db.get_trades(account_id=account_id, symbol=symbol, limit=limit, offset=offset)
    return jsonify(trades)


@app.route('/api/trades/<int:trade_id>', methods=['DELETE'])
def api_delete_trade(trade_id):
    """Delete a trade."""
    if db.delete_trade(trade_id):
        return jsonify({'success': True})
    return jsonify({'error': 'Trade not found'}), 404


@app.route('/api/trades/stats', methods=['GET'])
def api_get_trade_stats():
    """Get overall trade statistics."""
    account_id = request.args.get('account_id', None, type=int)
    stats = db.get_trade_stats(account_id=account_id)
    if stats:
        return jsonify(stats)
    return jsonify({
        'total_trades': 0,
        'symbols_traded': 0,
        'winning_trades': 0,
        'losing_trades': 0,
        'breakeven_trades': 0,
        'win_rate': 0,
        'total_pnl': 0,
        'total_commission': 0
    })


def cleanup_on_exit():
    """Clean up all running processes on application exit."""
    print("\nShutting down... stopping all running scripts")
    with process_lock:
        for script_id in list(running_processes.keys()):
            try:
                stop_script_process(script_id)
            except:
                pass


# Register cleanup function
atexit.register(cleanup_on_exit)


# Restart scripts on module load (works with gunicorn/production)
# This runs when the module is imported, not just when run directly
print("[STARTUP] Checking for scripts to auto-restart...")
restart_persistent_scripts()


if __name__ == '__main__':
    print("=" * 60)
    print("  Trading Bot Script Manager")
    print("  Dashboard: http://localhost:5000")
    print("  Accounts: http://localhost:5000/accounts")
    print("  Logs Page: http://localhost:5000/logs")
    print("  Bots Page: http://localhost:5000/bots")
    print("  Trades Page: http://localhost:5000/trades")
    print("=" * 60)
    print(f"  Scripts folder: {SCRIPTS_FOLDER}")
    print(f"  Logs folder: {LOGS_FOLDER}")
    print("  Logs are automatically cleared daily at midnight")
    print("=" * 60)
    
    app.run(debug=False, host='0.0.0.0', port=5000, threaded=True)
