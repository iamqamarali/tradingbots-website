"""
Trading Bot Script Manager
A Flask web application to manage, run, and monitor Python trading bot scripts.
"""

from flask import Flask, render_template, request, jsonify, redirect, url_for, session
from functools import wraps
import os
import subprocess
import signal
import sys
import uuid
import json
import secrets
from datetime import datetime, timedelta
from threading import Thread, Lock
import time
import atexit
import math

# Import database module for trade tracking
import database as db

# Binance API for account sync
try:
    from binance.client import Client as BinanceClient
    from binance.exceptions import BinanceAPIException
    import requests
    import hmac
    import hashlib
    BINANCE_AVAILABLE = True
except ImportError:
    BINANCE_AVAILABLE = False


def fetch_algo_orders(api_key, api_secret, testnet=False):
    """Fetch algo/conditional orders from Binance Futures API."""
    if testnet:
        base_url = 'https://testnet.binancefuture.com'
    else:
        base_url = 'https://fapi.binance.com'

    # After Dec 2024 migration, conditional orders (STOP_MARKET, TAKE_PROFIT_MARKET)
    # are now in the Algo Service and need to be fetched from /fapi/v1/openAlgoOrders
    # See: https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/rest-api/Current-All-Algo-Open-Orders
    endpoints_to_try = [
        '/fapi/v1/openAlgoOrders',  # Correct endpoint for algo/conditional orders
    ]

    all_orders = []

    for endpoint in endpoints_to_try:
        timestamp = int(time.time() * 1000)
        recv_window = 5000
        query_string = f'recvWindow={recv_window}&timestamp={timestamp}'

        # Create signature
        signature = hmac.new(
            api_secret.encode('utf-8'),
            query_string.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()

        url = f'{base_url}{endpoint}?{query_string}&signature={signature}'
        headers = {'X-MBX-APIKEY': api_key}

        print(f"  Fetching algo orders from: {base_url}{endpoint}")

        try:
            response = requests.get(url, headers=headers, timeout=10)
            print(f"  Algo orders response status: {response.status_code}")

            if response.status_code == 200:
                data = response.json()
                print(f"  Algo orders response: {data}")

                # Handle both array and object responses
                if isinstance(data, list):
                    all_orders.extend(data)
                elif isinstance(data, dict):
                    # Some APIs wrap the array in an object
                    if 'orders' in data:
                        all_orders.extend(data['orders'])
                    elif 'data' in data:
                        all_orders.extend(data['data'])
                    else:
                        print(f"  Response format: {data}")
            else:
                print(f"  Algo orders API error: {response.status_code} - {response.text}")
        except Exception as e:
            print(f"  Error fetching algo orders from {endpoint}: {e}")

    return all_orders


def cancel_algo_order(api_key, api_secret, algo_id, testnet=False):
    """Cancel an algo/conditional order using DELETE /fapi/v1/algoOrder.

    See: https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/rest-api/Cancel-Algo-Order
    Note: Parameter is 'algoid' (lowercase), not 'algoId'
    """
    if testnet:
        base_url = 'https://testnet.binancefuture.com'
    else:
        base_url = 'https://fapi.binance.com'

    endpoint = '/fapi/v1/algoOrder'
    timestamp = int(time.time() * 1000)
    recv_window = 5000
    # IMPORTANT: Parameter is 'algoid' (lowercase) per Binance API docs
    query_string = f'algoid={algo_id}&recvWindow={recv_window}&timestamp={timestamp}'

    # Create signature
    signature = hmac.new(
        api_secret.encode('utf-8'),
        query_string.encode('utf-8'),
        hashlib.sha256
    ).hexdigest()

    url = f'{base_url}{endpoint}?{query_string}&signature={signature}'
    headers = {'X-MBX-APIKEY': api_key}

    print(f"  Cancelling algo order {algo_id} via DELETE {base_url}{endpoint}")
    print(f"  Full URL: {url}")

    response = requests.delete(url, headers=headers, timeout=10)
    print(f"  Cancel algo order response: {response.status_code} - {response.text}")

    if response.status_code == 200:
        return response.json()
    else:
        raise Exception(f"Failed to cancel algo order: {response.status_code} - {response.text}")


app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', secrets.token_hex(32))

# Configure session to last 365 days
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=365)
app.config['SESSION_COOKIE_SECURE'] = False  # Set to True if using HTTPS
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'

# Login required decorator
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            if request.is_json:
                return jsonify({'error': 'Authentication required'}), 401
            return redirect(url_for('login_page'))
        return f(*args, **kwargs)
    return decorated_function

# Protect all routes except auth endpoints
@app.before_request
def check_authentication():
    # Public endpoints that don't require auth
    public_endpoints = [
        'login_page', 'register_page', 'api_login', 'api_register',
        'api_registration_status', 'api_restrict_registration', 'static'
    ]

    # Skip auth check for public endpoints
    if request.endpoint in public_endpoints:
        return None

    # Check if user is authenticated
    if 'user_id' not in session:
        if request.is_json or request.path.startswith('/api/'):
            return jsonify({'error': 'Authentication required'}), 401
        return redirect(url_for('login_page'))

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
    """Clear log files older than 7 days."""
    global last_clear_date

    today = datetime.now().date()
    # Only run cleanup once per day
    if today > last_clear_date:
        now = datetime.now()
        deleted_count = 0

        # Delete log files older than 7 days
        for filename in os.listdir(LOGS_FOLDER):
            if filename.endswith('.log'):
                filepath = os.path.join(LOGS_FOLDER, filename)
                try:
                    # Check file modification time
                    file_mtime = datetime.fromtimestamp(os.path.getmtime(filepath))
                    file_age_days = (now - file_mtime).days

                    if file_age_days >= 7:
                        os.remove(filepath)
                        deleted_count += 1
                except:
                    pass

        last_clear_date = today
        if deleted_count > 0:
            print(f"[{datetime.now()}] Log cleanup completed - deleted {deleted_count} log files older than 7 days")


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

    # Get all accounts for name lookup
    all_accounts = {acc['id']: acc['name'] for acc in db.get_all_accounts()}

    for filename in os.listdir(SCRIPTS_FOLDER):
        if filename.endswith('.py'):
            script_id = filename[:-3]  # Remove .py extension
            script_info = metadata.get(script_id, {})

            with process_lock:
                is_running = script_id in running_processes and running_processes[script_id].poll() is None

            # Get account info if connected
            account_id = script_info.get('account_id')
            account_name = all_accounts.get(account_id) if account_id else None

            scripts.append({
                'id': script_id,
                'name': script_info.get('name', filename),
                'filename': filename,
                'status': 'running' if is_running else 'stopped',
                'created': script_info.get('created', 'Unknown'),
                'description': script_info.get('description', ''),
                'auto_restart': script_info.get('auto_restart', False),
                'account_id': account_id,
                'account_name': account_name
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
        preexec_fn = None

        if sys.platform == 'win32':
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = subprocess.SW_HIDE
            creationflags = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW
        else:
            # On Linux, start process in its own process group for clean shutdown
            preexec_fn = os.setsid

        # Start the process
        process = subprocess.Popen(
            [sys.executable, '-u', filepath],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            startupinfo=startupinfo,
            creationflags=creationflags,
            preexec_fn=preexec_fn,
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


# ==================== AUTHENTICATION ROUTES ====================

@app.route('/login')
def login_page():
    """Render the login page."""
    if 'user_id' in session:
        return redirect(url_for('index'))
    return render_template('login.html')


@app.route('/register')
def register_page():
    """Render the register page."""
    if 'user_id' in session:
        return redirect(url_for('index'))
    return render_template('register.html')


@app.route('/logout')
def logout():
    """Log out the user."""
    session.clear()
    return redirect(url_for('login_page'))


@app.route('/settings')
@login_required
def settings_page():
    """Render the settings page."""
    return render_template('settings.html', active_page='settings')


@app.route('/scripts')
@login_required
def scripts_page():
    """Render the scripts management page."""
    return render_template('scripts.html', active_page='scripts')


@app.route('/api/auth/login', methods=['POST'])
def api_login():
    """Authenticate user and create session."""
    data = request.get_json()
    username = data.get('username', '').strip()
    password = data.get('password', '')

    if not username or not password:
        return jsonify({'error': 'Username and password required'}), 400

    user = db.verify_user(username, password)
    if user:
        session.permanent = True  # Make session last 365 days
        session['user_id'] = user['id']
        session['username'] = user['username']
        return jsonify({'success': True, 'username': user['username']})

    return jsonify({'error': 'Invalid username or password'}), 401


@app.route('/api/auth/register', methods=['POST'])
def api_register():
    """Register a new user."""
    # Check if registration is open
    if not db.is_registration_open():
        return jsonify({'error': 'Registration is closed'}), 403

    data = request.get_json()
    username = data.get('username', '').strip()
    password = data.get('password', '')

    if not username or not password:
        return jsonify({'error': 'Username and password required'}), 400

    if len(username) < 3:
        return jsonify({'error': 'Username must be at least 3 characters'}), 400

    if len(password) < 6:
        return jsonify({'error': 'Password must be at least 6 characters'}), 400

    user_id = db.create_user(username, password)
    if user_id:
        return jsonify({'success': True, 'user_id': user_id})

    return jsonify({'error': 'Username already exists'}), 400


@app.route('/api/auth/registration-status')
def api_registration_status():
    """Check if registration is open."""
    is_open = db.is_registration_open()
    return jsonify({'open': is_open, 'locked': not is_open})


@app.route('/api/auth/restrict-registration', methods=['POST'])
def api_restrict_registration():
    """Close registration."""
    db.set_registration_open(False)
    return jsonify({'success': True})


@app.route('/api/auth/toggle-registration-lock', methods=['POST'])
def api_toggle_registration_lock():
    """Toggle registration lock status."""
    is_open = db.is_registration_open()
    db.set_registration_open(not is_open)
    new_locked = not (not is_open)  # After toggle, locked = not new_open
    return jsonify({'success': True, 'locked': new_locked})


@app.route('/api/auth/open-registration', methods=['POST'])
def api_open_registration():
    """Open registration."""
    db.set_registration_open(True)
    return jsonify({'success': True})


# ==================== PAGE ROUTES ====================

@app.route('/')
def index():
    """Render the main dashboard page."""
    return render_template('index.html', active_page='dashboard')


@app.route('/logs')
def logs_page():
    """Render the logs page."""
    return render_template('logs.html', active_page='logs')


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
    account_id = data.get('account_id')  # Optional account connection

    if not script_content.strip():
        return jsonify({'error': 'Script content is empty'}), 400

    # Validate account_id if provided
    account_name = None
    if account_id:
        account_id = int(account_id)
        account = db.get_account(account_id)
        if not account:
            return jsonify({'error': 'Account not found'}), 404
        account_name = account['name']

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
    if account_id:
        metadata[script_id]['account_id'] = account_id
    save_metadata(metadata)

    return jsonify({
        'success': True,
        'script': {
            'id': script_id,
            'name': script_name,
            'filename': filename,
            'status': 'stopped',
            'created': metadata[script_id]['created'],
            'description': description,
            'account_id': account_id,
            'account_name': account_name
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

    # Get account info if connected
    account_id = script_info.get('account_id')
    account_name = None
    if account_id:
        account = db.get_account(account_id)
        if account:
            account_name = account['name']

    return jsonify({
        'id': script_id,
        'name': script_info.get('name', filename),
        'content': content,
        'description': script_info.get('description', ''),
        'status': 'running' if is_running else 'stopped',
        'auto_restart': script_info.get('auto_restart', False),
        'account_id': account_id,
        'account_name': account_name
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

    # Handle account_id update (can be set to null to disconnect)
    if 'account_id' in data:
        account_id = data['account_id']
        if account_id is None:
            # Disconnect from account
            if 'account_id' in metadata[script_id]:
                del metadata[script_id]['account_id']
        else:
            # Connect to account - validate it exists
            account_id = int(account_id)
            account = db.get_account(account_id)
            if not account:
                return jsonify({'error': 'Account not found'}), 404
            metadata[script_id]['account_id'] = account_id

    save_metadata(metadata)

    # Return updated account info
    account_id = metadata[script_id].get('account_id')
    account_name = None
    if account_id:
        account = db.get_account(account_id)
        if account:
            account_name = account['name']

    return jsonify({
        'success': True,
        'account_id': account_id,
        'account_name': account_name
    })


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
    try:
        os.remove(filepath)
    except Exception as e:
        return jsonify({'error': f'Failed to delete script file: {str(e)}'}), 500

    # Delete log file if exists
    log_file = get_log_file_path(script_id)
    if os.path.exists(log_file):
        try:
            os.remove(log_file)
        except:
            pass  # Log file deletion is not critical

    # Remove metadata (JSON file only)
    metadata = load_metadata()
    if script_id in metadata:
        del metadata[script_id]
        save_metadata(metadata)

    # Clear in-memory logs
    with logs_lock:
        if script_id in script_logs:
            del script_logs[script_id]

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
        preexec_fn = None

        if sys.platform == 'win32':
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = subprocess.SW_HIDE
            creationflags = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW
        else:
            # On Linux, start process in its own process group for clean shutdown
            preexec_fn = os.setsid

        # Start the process - runs indefinitely in background
        process = subprocess.Popen(
            [sys.executable, '-u', filepath],  # -u for unbuffered output
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            startupinfo=startupinfo,
            creationflags=creationflags,
            preexec_fn=preexec_fn,
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
                        # On Linux, kill the entire process group
                        import os as os_module
                        try:
                            # Kill entire process group (negative PID)
                            os_module.killpg(os_module.getpgid(process.pid), signal.SIGTERM)
                        except (ProcessLookupError, PermissionError):
                            pass

                        try:
                            process.wait(timeout=3)
                        except subprocess.TimeoutExpired:
                            # Force kill the process group
                            try:
                                os_module.killpg(os_module.getpgid(process.pid), signal.SIGKILL)
                            except (ProcessLookupError, PermissionError):
                                pass
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
    return render_template('accounts.html', active_page='accounts')


@app.route('/accounts/<int:account_id>')
def account_detail_page(account_id):
    """Render the account detail page."""
    account = db.get_account(account_id)
    if not account:
        return "Account not found", 404
    return render_template('account_detail.html', account_id=account_id, active_page='accounts')


@app.route('/accounts/<int:account_id>/stats')
def account_stats_page(account_id):
    """Render the account stats page."""
    account = db.get_account(account_id)
    if not account:
        return "Account not found", 404
    return render_template('account_stats.html', account_id=account_id, active_page='accounts')


# ==================== ACCOUNTS API ====================

@app.route('/api/accounts', methods=['GET'])
def api_get_accounts():
    """Get all accounts."""
    accounts = db.get_all_accounts()

    # Load scripts metadata to get attached scripts for each account
    metadata = load_metadata()
    scripts_by_account = {}
    for script_id, script_info in metadata.items():
        account_id = script_info.get('account_id')
        if account_id:
            if account_id not in scripts_by_account:
                scripts_by_account[account_id] = []

            # Check if script is running
            with process_lock:
                is_running = script_id in running_processes and running_processes[script_id].poll() is None

            scripts_by_account[account_id].append({
                'id': script_id,
                'name': script_info.get('name', script_id),
                'status': 'running' if is_running else 'stopped'
            })

    # Don't expose full API keys/secrets in list view
    for acc in accounts:
        del acc['api_key_full']
        del acc['api_secret']
        # Add attached scripts
        acc['scripts'] = scripts_by_account.get(acc['id'], [])

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
    """Get a specific account with attached scripts."""
    account = db.get_account(account_id)
    if account:
        # Mask the secrets
        account['api_key'] = account['api_key'][:8] + '...' if account['api_key'] else ''
        del account['api_secret']

        # Get attached scripts for this account
        metadata = load_metadata()
        scripts = []
        for script_id, script_info in metadata.items():
            if script_info.get('account_id') == account_id:
                with process_lock:
                    is_running = script_id in running_processes and running_processes[script_id].poll() is None
                scripts.append({
                    'id': script_id,
                    'name': script_info.get('name', script_id),
                    'status': 'running' if is_running else 'stopped'
                })
        account['scripts'] = scripts

        return jsonify(account)
    return jsonify({'error': 'Account not found'}), 404


@app.route('/api/accounts/<int:account_id>', methods=['PUT'])
def api_update_account(account_id):
    """Update an account's name."""
    data = request.json
    if not data:
        return jsonify({'error': 'No data provided'}), 400

    name = data.get('name', '').strip()
    if not name:
        return jsonify({'error': 'Account name is required'}), 400

    account = db.get_account(account_id)
    if not account:
        return jsonify({'error': 'Account not found'}), 404

    db.update_account(account_id, name=name)
    return jsonify({'success': True, 'name': name})


@app.route('/api/accounts/<int:account_id>', methods=['DELETE'])
def api_delete_account(account_id):
    """Delete an account and all its trades."""
    if db.delete_account(account_id):
        return jsonify({'success': True})
    return jsonify({'error': 'Account not found'}), 404


@app.route('/api/accounts/<int:account_id>/balance', methods=['GET'])
def api_get_account_balance(account_id):
    """Get account balance from Binance and update database."""
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

        # Check both USDT and USDC balances
        usdt_balance = 0
        usdc_balance = 0
        usdt_available = 0
        usdc_available = 0
        for bal in balances:
            if bal['asset'] == 'USDT':
                usdt_balance = float(bal['balance'])
                usdt_available = float(bal.get('availableBalance', bal.get('withdrawAvailable', bal['balance'])))
                print(f"USDT balance found: {usdt_balance}, available: {usdt_available}")
            elif bal['asset'] == 'USDC':
                usdc_balance = float(bal['balance'])
                usdc_available = float(bal.get('availableBalance', bal.get('withdrawAvailable', bal['balance'])))
                print(f"USDC balance found: {usdc_balance}, available: {usdc_available}")

        # Combine both balances
        total_balance = usdt_balance + usdc_balance
        total_available = usdt_available + usdc_available
        print(f"Total balance (USDT + USDC): {total_balance}, available: {total_available}")

        # Update balance in database
        db.update_account_balance(account_id, total_balance)

        # Get starting balance from database
        accounts = db.get_all_accounts()
        starting_balance = 0
        for acc in accounts:
            if acc['id'] == account_id:
                starting_balance = acc.get('starting_balance', 0)
                break

        return jsonify({
            'balance': round(total_balance, 2),
            'available_balance': round(total_available, 2),
            'usdt_balance': round(usdt_balance, 2),
            'usdc_balance': round(usdc_balance, 2),
            'starting_balance': round(starting_balance, 2),
            'asset': 'USDT+USDC'
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
    """Get open positions from Binance with stop-loss info."""
    debug_info = []  # Collect debug info for frontend

    if not BINANCE_AVAILABLE:
        return jsonify({'error': 'Binance API not available'}), 500

    account = db.get_account(account_id)
    if not account:
        return jsonify({'error': 'Account not found'}), 404

    debug_info.append(f"Account: {account['name']}, testnet: {account['is_testnet']}")

    try:
        client = BinanceClient(account['api_key'], account['api_secret'], testnet=account['is_testnet'])
        if account['is_testnet']:
            client.FUTURES_URL = 'https://testnet.binancefuture.com/fapi'

        positions = client.futures_position_information()
        debug_info.append(f"Got {len(positions)} position entries")

        # Get all open orders to find stop-loss orders
        all_open_orders = []
        regular_orders_debug = []
        try:
            regular_orders = client.futures_get_open_orders()
            all_open_orders.extend(regular_orders)
            debug_info.append(f"Library returned {len(regular_orders)} regular orders")
            for order in regular_orders:
                regular_orders_debug.append({
                    'type': order.get('type'),
                    'symbol': order.get('symbol'),
                    'orderId': order.get('orderId'),
                    'algoId': order.get('algoId'),
                    'stopPrice': order.get('stopPrice')
                })
        except Exception as e:
            debug_info.append(f"Library error: {str(e)}")

        # Direct API call to /fapi/v1/openOrders
        direct_api_debug = []
        try:
            if account['is_testnet']:
                base_url = 'https://testnet.binancefuture.com'
            else:
                base_url = 'https://fapi.binance.com'

            timestamp = int(time.time() * 1000)
            query_string = f'recvWindow=5000&timestamp={timestamp}'
            signature = hmac.new(
                account['api_secret'].encode('utf-8'),
                query_string.encode('utf-8'),
                hashlib.sha256
            ).hexdigest()

            url = f'{base_url}/fapi/v1/openOrders?{query_string}&signature={signature}'
            headers = {'X-MBX-APIKEY': account['api_key']}
            response = requests.get(url, headers=headers, timeout=10)

            debug_info.append(f"Direct API /fapi/v1/openOrders: status={response.status_code}")
            if response.status_code == 200:
                raw_orders = response.json()
                debug_info.append(f"Direct API returned {len(raw_orders)} orders")
                for order in raw_orders:
                    direct_api_debug.append({
                        'type': order.get('type'),
                        'symbol': order.get('symbol'),
                        'orderId': order.get('orderId'),
                        'algoId': order.get('algoId'),
                        'stopPrice': order.get('stopPrice')
                    })
            else:
                debug_info.append(f"Direct API error: {response.text[:200]}")
        except Exception as e:
            debug_info.append(f"Direct API exception: {str(e)}")

        # Fetch algo/conditional orders
        algo_orders_debug = []
        try:
            algo_orders = fetch_algo_orders(account['api_key'], account['api_secret'], account['is_testnet'])
            if algo_orders and isinstance(algo_orders, list):
                all_open_orders.extend(algo_orders)
                debug_info.append(f"Algo endpoints returned {len(algo_orders)} orders")
                for order in algo_orders:
                    algo_orders_debug.append({
                        'type': order.get('type') or order.get('orderType'),
                        'symbol': order.get('symbol'),
                        'algoId': order.get('algoId'),
                        'triggerPrice': order.get('triggerPrice')
                    })
            else:
                debug_info.append("Algo endpoints returned 0 orders")
        except Exception as e:
            debug_info.append(f"Algo fetch error: {str(e)}")

        print(f"Total open orders: {len(all_open_orders)}")

        # Build a map of symbol -> stop orders
        # Include all conditional/stop order types that Binance Futures supports
        stop_order_types = [
            'STOP_MARKET',           # Standard stop market
            'STOP',                  # Stop limit
            'STOP_LIMIT',            # Stop limit (alias)
            'TRAILING_STOP_MARKET',  # Trailing stop
        ]
        
        stop_orders_map = {}
        tp_orders_map = {}  # Track take-profit orders separately
        
        for order in all_open_orders:
            symbol = order.get('symbol')
            # Binance returns 'algoId' for conditional orders, 'orderId' for regular orders
            order_id = order.get('orderId') or order.get('algoId')
            order_side = order.get('side')
            order_type = order.get('type') or order.get('orderType', '')
            stop_price = float(order.get('stopPrice') or order.get('triggerPrice') or 0)

            print(f"  Processing order: symbol={symbol}, id={order_id}, side={order_side}, type={order_type}, stopPrice={stop_price}")

            # Skip orders with missing required fields
            if not symbol or not order_id or not order_side:
                print(f"  Warning: Skipping order with missing fields: {order}")
                continue

            # Check for stop-loss orders
            if order_type in stop_order_types:
                print(f"    -> Matched as STOP order")
                if symbol not in stop_orders_map:
                    stop_orders_map[symbol] = []
                stop_orders_map[symbol].append({
                    'order_id': order_id,
                    'type': order_type,
                    'side': order_side,
                    'stop_price': stop_price,
                    'quantity': float(order.get('origQty') or order.get('quantity') or 0),
                    'status': order.get('status') or order.get('algoStatus', ''),
                    'activation_price': float(order.get('activatePrice', 0)) if order.get('activatePrice') else None
                })
                print(f"  Found stop order for {symbol}: {order_type} @ {stop_price}")

            # Also track take-profit orders
            elif order_type in ['TAKE_PROFIT_MARKET', 'TAKE_PROFIT']:
                if symbol not in tp_orders_map:
                    tp_orders_map[symbol] = []
                tp_orders_map[symbol].append({
                    'order_id': order_id,
                    'type': order_type,
                    'side': order_side,
                    'stop_price': stop_price,
                    'quantity': float(order.get('origQty') or order.get('quantity') or 0),
                    'status': order.get('status') or order.get('algoStatus', '')
                })
                print(f"  Found TP order for {symbol}: {order_type} @ {stop_price}")

        open_positions = []

        for pos in positions:
            try:
                amt = float(pos.get('positionAmt', 0))
                if amt != 0:
                    symbol = pos.get('symbol')
                    if not symbol:
                        print(f"  Warning: Skipping position with missing symbol: {pos}")
                        continue

                    entry_price = float(pos.get('entryPrice', 0))
                    mark_price = float(pos.get('markPrice', 0))
                    unrealized_pnl = float(pos.get('unRealizedProfit', 0))
                    side = 'LONG' if amt > 0 else 'SHORT'

                    # Find stop-loss for this position
                    # For LONG, stop-loss is a SELL order; for SHORT, it's a BUY order
                    stop_price = None
                    stop_order_id = None
                    stop_type = None
                    stop_orders = stop_orders_map.get(symbol, [])
                    for stop in stop_orders:
                        # LONG position needs SELL stop, SHORT position needs BUY stop
                        if (side == 'LONG' and stop.get('side') == 'SELL') or (side == 'SHORT' and stop.get('side') == 'BUY'):
                            stop_price = stop.get('stop_price')
                            stop_order_id = stop.get('order_id')
                            stop_type = stop.get('type')
                            break

                    # Find take-profit for this position
                    tp_price = None
                    tp_order_id = None
                    tp_orders = tp_orders_map.get(symbol, [])
                    for tp in tp_orders:
                        # LONG position needs SELL TP, SHORT position needs BUY TP
                        if (side == 'LONG' and tp.get('side') == 'SELL') or (side == 'SHORT' and tp.get('side') == 'BUY'):
                            tp_price = tp.get('stop_price')
                            tp_order_id = tp.get('order_id')
                            break

                    print(f"  Open position: {symbol} {side} amt={amt} pnl={unrealized_pnl} SL={stop_price} TP={tp_price}")
                    open_positions.append({
                        'symbol': symbol,
                        'side': side,
                        'quantity': abs(amt),
                        'entry_price': entry_price,
                        'mark_price': mark_price,
                        'unrealized_pnl': round(unrealized_pnl, 2),
                        'leverage': int(pos.get('leverage', 5)),
                        'stop_price': stop_price,
                        'stop_order_id': stop_order_id,
                        'stop_type': stop_type,
                        'tp_price': tp_price,
                        'tp_order_id': tp_order_id
                    })
            except (ValueError, TypeError) as e:
                print(f"  Warning: Error processing position {pos}: {e}")
                continue

        debug_info.append(f"Total orders found: {len(all_open_orders)}")
        debug_info.append(f"Returning {len(open_positions)} open positions")

        # Return positions with debug info
        return jsonify({
            'positions': open_positions,
            '_debug': {
                'messages': debug_info,
                'regular_orders': regular_orders_debug,
                'direct_api_orders': direct_api_debug,
                'algo_orders': algo_orders_debug
            }
        })
    except BinanceAPIException as e:
        return jsonify({'error': f'Binance error: {e.message}', '_debug': {'messages': debug_info}}), 500
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@app.route('/api/accounts/<int:account_id>/orders', methods=['GET'])
def api_get_account_orders(account_id):
    """Get all open orders from Binance."""
    debug_info = []  # Collect debug info for frontend

    if not BINANCE_AVAILABLE:
        return jsonify({'error': 'Binance API not available'}), 500

    account = db.get_account(account_id)
    if not account:
        return jsonify({'error': 'Account not found'}), 404

    debug_info.append(f"Account: {account['name']}, testnet: {account['is_testnet']}")

    try:
        client = BinanceClient(account['api_key'], account['api_secret'], testnet=account['is_testnet'])
        if account['is_testnet']:
            client.FUTURES_URL = 'https://testnet.binancefuture.com/fapi'

        # Fetch regular open orders
        all_orders = []
        regular_orders_debug = []
        try:
            regular_orders = client.futures_get_open_orders()
            all_orders.extend(regular_orders)
            debug_info.append(f"Library returned {len(regular_orders)} regular orders")
            for order in regular_orders:
                regular_orders_debug.append({
                    'type': order.get('type'),
                    'symbol': order.get('symbol'),
                    'orderId': order.get('orderId'),
                    'algoId': order.get('algoId'),
                    'stopPrice': order.get('stopPrice')
                })
        except Exception as e:
            debug_info.append(f"Library error: {str(e)}")

        # Direct API call to /fapi/v1/openOrders
        direct_api_debug = []
        try:
            if account['is_testnet']:
                base_url = 'https://testnet.binancefuture.com'
            else:
                base_url = 'https://fapi.binance.com'

            timestamp = int(time.time() * 1000)
            query_string = f'recvWindow=5000&timestamp={timestamp}'
            signature = hmac.new(
                account['api_secret'].encode('utf-8'),
                query_string.encode('utf-8'),
                hashlib.sha256
            ).hexdigest()

            url = f'{base_url}/fapi/v1/openOrders?{query_string}&signature={signature}'
            headers = {'X-MBX-APIKEY': account['api_key']}
            response = requests.get(url, headers=headers, timeout=10)

            debug_info.append(f"Direct API /fapi/v1/openOrders: status={response.status_code}")
            if response.status_code == 200:
                raw_orders = response.json()
                debug_info.append(f"Direct API returned {len(raw_orders)} orders")
                for order in raw_orders:
                    direct_api_debug.append({
                        'type': order.get('type'),
                        'symbol': order.get('symbol'),
                        'orderId': order.get('orderId'),
                        'algoId': order.get('algoId'),
                        'stopPrice': order.get('stopPrice')
                    })
            else:
                debug_info.append(f"Direct API error: {response.text[:200]}")
        except Exception as e:
            debug_info.append(f"Direct API exception: {str(e)}")

        # Fetch algo/conditional orders
        algo_orders_debug = []
        try:
            algo_orders = fetch_algo_orders(account['api_key'], account['api_secret'], account['is_testnet'])
            if algo_orders and isinstance(algo_orders, list):
                all_orders.extend(algo_orders)
                debug_info.append(f"Algo endpoints returned {len(algo_orders)} orders")
                for order in algo_orders:
                    algo_orders_debug.append({
                        'type': order.get('type') or order.get('orderType'),
                        'symbol': order.get('symbol'),
                        'algoId': order.get('algoId'),
                        'triggerPrice': order.get('triggerPrice')
                    })
            else:
                debug_info.append("Algo endpoints returned 0 orders")
        except Exception as e:
            debug_info.append(f"Algo fetch error: {str(e)}")

        print(f"Total orders: {len(all_orders)}")

        orders = []
        for order in all_orders:
            # Binance returns 'algoId' for conditional orders, 'orderId' for regular orders
            order_id = order.get('orderId') or order.get('algoId')
            symbol = order.get('symbol')
            side = order.get('side')
            order_type = order.get('type') or order.get('orderType')

            # Skip orders with missing required fields
            if not order_id or not symbol or not side or not order_type:
                print(f"  Warning: Skipping order with missing fields: {order}")
                continue

            orders.append({
                'order_id': order_id,
                'symbol': symbol,
                'side': side,
                'type': order_type,
                'quantity': float(order.get('origQty') or order.get('quantity') or 0),
                'price': float(order.get('price', 0)),
                'stop_price': float(order.get('stopPrice') or order.get('triggerPrice') or 0) or None,
                'status': order.get('status') or order.get('algoStatus', ''),
                'time': order.get('time') or order.get('updateTime') or order.get('createTime') or 0,
                'reduce_only': order.get('reduceOnly', False),
                'is_algo': 'algoId' in order  # Flag to identify algo orders
            })

        # Sort by time descending (newest first)
        orders.sort(key=lambda x: x['time'], reverse=True)

        debug_info.append(f"Total orders found: {len(all_orders)}")
        debug_info.append(f"Returning {len(orders)} processed orders")

        # Return orders with debug info
        return jsonify({
            'orders': orders,
            '_debug': {
                'messages': debug_info,
                'regular_orders': regular_orders_debug,
                'direct_api_orders': direct_api_debug,
                'algo_orders': algo_orders_debug
            }
        })
    except BinanceAPIException as e:
        return jsonify({'error': f'Binance error: {e.message}', '_debug': {'messages': debug_info}}), 500
    except KeyError as e:
        return jsonify({'error': f'Missing field in order data: {e}', '_debug': {'messages': debug_info}}), 500
    except Exception as e:
        return jsonify({'error': f'Server error: {str(e)}', '_debug': {'messages': debug_info}}), 500


@app.route('/api/accounts/<int:account_id>/orders/<int:order_id>', methods=['DELETE'])
def api_cancel_order(account_id, order_id):
    """Cancel an open order (supports both regular and algo/conditional orders)."""
    print(f"=== CANCEL ORDER {order_id} for account_id: {account_id} ===")

    if not BINANCE_AVAILABLE:
        return jsonify({'error': 'Binance API not available'}), 500

    account = db.get_account(account_id)
    if not account:
        return jsonify({'error': 'Account not found'}), 404

    data = request.json or {}
    symbol = data.get('symbol')
    is_algo = data.get('is_algo', False)  # Flag to indicate if this is an algo/conditional order

    if not symbol:
        return jsonify({'error': 'Symbol is required'}), 400

    print(f"  Symbol: {symbol}, is_algo: {is_algo}")
    debug_log = []

    try:
        client = BinanceClient(account['api_key'], account['api_secret'], testnet=account['is_testnet'])
        if account['is_testnet']:
            client.FUTURES_URL = 'https://testnet.binancefuture.com/fapi'

        # Try algo cancel first (most SL/TP orders are algo orders with closePosition=true)
        algo_success = False
        regular_success = False
        algo_error = None
        regular_error = None

        debug_log.append(f"Attempting to cancel order {order_id} for {symbol}")

        # Try algo cancel
        try:
            debug_log.append(f"Trying algo cancel for {order_id}...")
            result = cancel_algo_order(
                account['api_key'],
                account['api_secret'],
                order_id,
                account['is_testnet']
            )
            algo_success = True
            debug_log.append(f"Algo cancel SUCCESS for {order_id}")
            print(f"Algo order {order_id} cancelled successfully")
        except Exception as e:
            algo_error = str(e)
            debug_log.append(f"Algo cancel FAILED: {algo_error}")
            print(f"Algo cancel failed: {e}")

        # If algo cancel failed, try regular cancel
        if not algo_success:
            try:
                debug_log.append(f"Trying regular cancel for {order_id}...")
                result = client.futures_cancel_order(symbol=symbol, orderId=order_id)
                regular_success = True
                debug_log.append(f"Regular cancel SUCCESS for {order_id}")
                print(f"Regular order {order_id} cancelled successfully")
            except Exception as e:
                regular_error = str(e)
                debug_log.append(f"Regular cancel FAILED: {regular_error}")
                print(f"Regular cancel failed: {e}")

        if algo_success or regular_success:
            return jsonify({'success': True, 'order_id': order_id, '_debug': debug_log})
        else:
            # Both failed
            error_msg = f"Failed to cancel order. Algo error: {algo_error}. Regular error: {regular_error}"
            debug_log.append(error_msg)
            return jsonify({'error': error_msg, '_debug': debug_log}), 500

    except BinanceAPIException as e:
        print(f"BinanceAPIException: {e}")
        debug_log.append(f"BinanceAPIException: {e.message}")
        return jsonify({'error': f'Binance error: {e.message}', '_debug': debug_log}), 500
    except Exception as e:
        print(f"Exception: {e}")
        debug_log.append(f"Exception: {str(e)}")
        return jsonify({'error': str(e), '_debug': debug_log}), 500


# Cache settings for positions
POSITIONS_CACHE_DURATION = 15 * 60  # 15 minutes in seconds


@app.route('/api/positions/all', methods=['GET'])
def api_get_all_positions():
    """Get open positions from all accounts with caching."""
    force_refresh = request.args.get('force', 'false').lower() == 'true'
    print(f"=== GET ALL POSITIONS (force={force_refresh}) ===")

    # Check cache time from database (unless force refresh)
    if not force_refresh:
        cache_time = db.get_positions_cache_time()
        if cache_time and (time.time() - cache_time) < POSITIONS_CACHE_DURATION:
            age_minutes = (time.time() - cache_time) / 60
            cached_positions = db.get_open_positions()
            print(f"Returning cached positions from DB ({len(cached_positions)} positions, {age_minutes:.1f} min old)")
            return jsonify(cached_positions)

    if not BINANCE_AVAILABLE:
        print("ERROR: Binance API not available")
        return jsonify({'error': 'Binance API not available'}), 500

    accounts = db.get_all_accounts()
    all_positions = []

    for account in accounts:
        account_id = account['id']
        account_name = account['name']
        print(f"Fetching positions for account: {account_name} (id={account_id})")

        try:
            client = BinanceClient(account['api_key_full'], account['api_secret'], testnet=account['is_testnet'])
            if account['is_testnet']:
                client.FUTURES_URL = 'https://testnet.binancefuture.com/fapi'

            positions = client.futures_position_information()

            # Get all open orders for stop-loss/take-profit info
            all_open_orders = []
            try:
                regular_orders = client.futures_get_open_orders()
                all_open_orders.extend(regular_orders)
                print(f"  Got {len(regular_orders)} regular orders for {account_name}")
                for i, order in enumerate(regular_orders):
                    print(f"    Regular order {i}: type={order.get('type')}, symbol={order.get('symbol')}, orderId={order.get('orderId')}, algoId={order.get('algoId')}")
            except Exception as e:
                print(f"Warning: Could not fetch regular orders for {account_name}: {e}")

            # Fetch algo/conditional orders (STOP_MARKET, TAKE_PROFIT_MARKET, etc.)
            try:
                algo_orders = fetch_algo_orders(account['api_key_full'], account['api_secret'], account['is_testnet'])
                if algo_orders and isinstance(algo_orders, list):
                    all_open_orders.extend(algo_orders)
                    print(f"  Got {len(algo_orders)} algo open orders for {account_name}")
                    for i, order in enumerate(algo_orders):
                        print(f"    Algo order {i}: type={order.get('type') or order.get('orderType')}, symbol={order.get('symbol')}, algoId={order.get('algoId')}")
            except Exception as e:
                print(f"Warning: Could not fetch algo orders for {account_name}: {e}")

            # Build stop order maps
            stop_order_types = ['STOP_MARKET', 'STOP', 'STOP_LIMIT', 'TRAILING_STOP_MARKET']
            stop_orders_map = {}
            tp_orders_map = {}

            for order in all_open_orders:
                symbol = order.get('symbol')
                # Binance returns 'algoId' for conditional orders, 'orderId' for regular orders
                order_id = order.get('orderId') or order.get('algoId')
                order_side = order.get('side')
                order_type = order.get('type') or order.get('orderType', '')
                stop_price = float(order.get('stopPrice') or order.get('triggerPrice') or 0)

                # Skip orders with missing required fields
                if not symbol or not order_id or not order_side:
                    print(f"  Warning: Skipping order with missing fields: {order}")
                    continue

                if order_type in stop_order_types:
                    if symbol not in stop_orders_map:
                        stop_orders_map[symbol] = []
                    stop_orders_map[symbol].append({
                        'order_id': order_id,
                        'type': order_type,
                        'side': order_side,
                        'stop_price': stop_price,
                        'quantity': float(order.get('origQty') or order.get('quantity') or 0)
                    })
                elif order_type in ['TAKE_PROFIT_MARKET', 'TAKE_PROFIT']:
                    if symbol not in tp_orders_map:
                        tp_orders_map[symbol] = []
                    tp_orders_map[symbol].append({
                        'order_id': order_id,
                        'type': order_type,
                        'side': order_side,
                        'stop_price': stop_price,
                        'quantity': float(order.get('origQty') or order.get('quantity') or 0)
                    })

            for pos in positions:
                try:
                    amt = float(pos.get('positionAmt', 0))
                    if amt != 0:
                        symbol = pos.get('symbol')
                        if not symbol:
                            print(f"  Warning: Skipping position with missing symbol: {pos}")
                            continue

                        entry_price = float(pos.get('entryPrice', 0))
                        mark_price = float(pos.get('markPrice', 0))
                        unrealized_pnl = float(pos.get('unRealizedProfit', 0))
                        side = 'LONG' if amt > 0 else 'SHORT'

                        # Find stop-loss
                        stop_price = None
                        stop_order_id = None
                        stop_type = None
                        for stop in stop_orders_map.get(symbol, []):
                            if (side == 'LONG' and stop.get('side') == 'SELL') or (side == 'SHORT' and stop.get('side') == 'BUY'):
                                stop_price = stop.get('stop_price')
                                stop_order_id = stop.get('order_id')
                                stop_type = stop.get('type')
                                break

                        # Find take-profit
                        tp_price = None
                        tp_order_id = None
                        for tp in tp_orders_map.get(symbol, []):
                            if (side == 'LONG' and tp.get('side') == 'SELL') or (side == 'SHORT' and tp.get('side') == 'BUY'):
                                tp_price = tp.get('stop_price')
                                tp_order_id = tp.get('order_id')
                                break

                        all_positions.append({
                            'account_id': account_id,
                            'account_name': account_name,
                            'is_testnet': account['is_testnet'],
                            'symbol': symbol,
                            'side': side,
                            'quantity': abs(amt),
                            'entry_price': entry_price,
                            'mark_price': mark_price,
                            'unrealized_pnl': round(unrealized_pnl, 2),
                            'leverage': int(pos.get('leverage', 5)),
                            'stop_price': stop_price,
                            'stop_order_id': stop_order_id,
                            'stop_type': stop_type,
                            'tp_price': tp_price,
                            'tp_order_id': tp_order_id
                        })
                except (ValueError, TypeError) as e:
                    print(f"  Warning: Error processing position {pos}: {e}")
                    continue

        except BinanceAPIException as e:
            print(f"BinanceAPIException for {account_name}: {e}")
            continue
        except Exception as e:
            print(f"Exception for {account_name}: {e}")
            continue

    print(f"Returning {len(all_positions)} total positions from all accounts")

    # Save to database and update cache time
    db.save_open_positions(all_positions)
    db.set_positions_cache_time(time.time())

    return jsonify(all_positions)


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
            try:
                amt = float(pos.get('positionAmt', 0))
                if amt != 0:
                    symbol = pos.get('symbol')
                    if not symbol:
                        print(f"  Warning: Skipping position with missing symbol: {pos}")
                        continue
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
            except (ValueError, TypeError) as e:
                print(f"  Warning: Error processing position {pos}: {e}")
                continue

        return jsonify({
            'success': True,
            'closed': closed,
            'errors': errors
        })
    except BinanceAPIException as e:
        return jsonify({'error': f'Binance error: {e.message}'}), 500
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/accounts/<int:account_id>/close-position', methods=['POST'])
def api_close_position(account_id):
    """Close a specific position (full or partial)."""
    if not BINANCE_AVAILABLE:
        return jsonify({'error': 'Binance API not available'}), 500

    account = db.get_account(account_id)
    if not account:
        return jsonify({'error': 'Account not found'}), 404

    data = request.get_json()
    symbol = data.get('symbol')
    side = data.get('side')  # Current position side (LONG/SHORT)
    quantity = float(data.get('quantity', 0))

    if not symbol or not side or quantity <= 0:
        return jsonify({'error': 'Invalid parameters'}), 400

    try:
        client = BinanceClient(account['api_key'], account['api_secret'], testnet=account['is_testnet'])
        if account['is_testnet']:
            client.FUTURES_URL = 'https://testnet.binancefuture.com/fapi'

        # Get symbol precision info
        exchange_info = client.futures_exchange_info()
        symbol_info = None
        for s in exchange_info['symbols']:
            if s['symbol'] == symbol:
                symbol_info = s
                break

        # Determine quantity precision from symbol info and adjust quantity
        step_size = 0.001  # Default
        if symbol_info:
            # First try to get quantityPrecision directly
            quantity_precision = symbol_info.get('quantityPrecision', 3)

            # Also get step_size from LOT_SIZE filter for proper rounding
            for f in symbol_info.get('filters', []):
                if f['filterType'] == 'LOT_SIZE':
                    step_size = float(f['stepSize'])
                    break

        # Round down to nearest valid step size (floor to avoid exceeding position)
        quantity = math.floor(quantity / step_size) * step_size

        # Calculate decimal precision from step_size to avoid floating point issues
        if step_size >= 1:
            precision = 0
        else:
            precision = int(round(-math.log10(step_size)))
        quantity = round(quantity, precision)

        # Ensure it's not zero after rounding
        if quantity <= 0:
            return jsonify({'error': 'Quantity too small after precision adjustment'}), 400

        # To close a position, place opposite order
        # If LONG (bought), we SELL to close
        # If SHORT (sold), we BUY to close
        close_side = 'SELL' if side == 'LONG' else 'BUY'

        print(f"Closing position: {symbol} {side} qty={quantity} (step_size={step_size}, precision={precision}) -> {close_side}")

        order = client.futures_create_order(
            symbol=symbol,
            side=close_side,
            type='MARKET',
            quantity=quantity,
            reduceOnly='true'
        )

        # Log the full response for debugging
        print(f"  Binance order response: {order}")

        order_id = order.get('orderId')
        if not order_id:
            print(f"  ERROR: No orderId in response. Full response: {order}")
            return jsonify({'error': 'Binance returned order without orderId'}), 500

        return jsonify({
            'success': True,
            'order': {
                'orderId': order_id,
                'symbol': order.get('symbol', symbol),
                'side': order.get('side', close_side),
                'quantity': order.get('origQty', quantity),
                'status': order.get('status', 'NEW')
            }
        })
    except BinanceAPIException as e:
        print(f"BinanceAPIException closing position: {e}")
        return jsonify({'error': f'Binance error: {e.message}'}), 500
    except KeyError as e:
        print(f"KeyError accessing order response: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': f'Missing field in Binance response: {e}'}), 500
    except Exception as e:
        print(f"Exception closing position: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': f'Server error: {str(e)}'}), 500


@app.route('/api/accounts/<int:account_id>/add-to-position', methods=['POST'])
def api_add_to_position(account_id):
    """Add size to an existing position."""
    if not BINANCE_AVAILABLE:
        return jsonify({'error': 'Binance API not available'}), 500

    account = db.get_account(account_id)
    if not account:
        return jsonify({'error': 'Account not found'}), 404

    data = request.get_json()
    symbol = data.get('symbol')
    side = data.get('side')  # Current position side (LONG/SHORT)
    quantity = float(data.get('quantity', 0))

    if not symbol or not side or quantity <= 0:
        return jsonify({'error': 'Invalid parameters'}), 400

    try:
        client = BinanceClient(account['api_key'], account['api_secret'], testnet=account['is_testnet'])
        if account['is_testnet']:
            client.FUTURES_URL = 'https://testnet.binancefuture.com/fapi'

        # Get symbol precision info
        exchange_info = client.futures_exchange_info()
        symbol_info = None
        for s in exchange_info['symbols']:
            if s['symbol'] == symbol:
                symbol_info = s
                break

        # Determine quantity precision from symbol info
        step_size = 0.001  # Default
        if symbol_info:
            for f in symbol_info.get('filters', []):
                if f['filterType'] == 'LOT_SIZE':
                    step_size = float(f['stepSize'])
                    break

        # Round to nearest valid step size
        quantity = math.floor(quantity / step_size) * step_size

        # Calculate decimal precision from step_size
        if step_size >= 1:
            precision = 0
        else:
            precision = int(round(-math.log10(step_size)))
        quantity = round(quantity, precision)

        if quantity <= 0:
            return jsonify({'error': 'Quantity too small after precision adjustment'}), 400

        # To add to position, place order in SAME direction
        # If LONG, we BUY more
        # If SHORT, we SELL more
        add_side = 'BUY' if side == 'LONG' else 'SELL'

        print(f"Adding to position: {symbol} {side} qty={quantity} -> {add_side}")

        order = client.futures_create_order(
            symbol=symbol,
            side=add_side,
            type='MARKET',
            quantity=quantity
        )

        # Log the full response for debugging
        print(f"  Binance order response: {order}")

        order_id = order.get('orderId')
        if not order_id:
            print(f"  ERROR: No orderId in response. Full response: {order}")
            return jsonify({'error': 'Binance returned order without orderId'}), 500

        return jsonify({
            'success': True,
            'order': {
                'orderId': order_id,
                'symbol': order.get('symbol', symbol),
                'side': order.get('side', add_side),
                'quantity': order.get('origQty', quantity),
                'status': order.get('status', 'NEW')
            }
        })
    except BinanceAPIException as e:
        print(f"BinanceAPIException adding to position: {e}")
        return jsonify({'error': f'Binance error: {e.message}'}), 500
    except KeyError as e:
        print(f"KeyError accessing order response: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': f'Missing field in Binance response: {e}'}), 500
    except Exception as e:
        print(f"Exception adding to position: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': f'Server error: {str(e)}'}), 500


@app.route('/api/accounts/<int:account_id>/update-stop-loss', methods=['POST'])
def api_update_stop_loss(account_id):
    """Update or create a stop-loss order for a position (closes entire position)."""
    print(f"=== UPDATE STOP-LOSS for account_id: {account_id} ===")

    if not BINANCE_AVAILABLE:
        return jsonify({'error': 'Binance API not available'}), 500

    account = db.get_account(account_id)
    if not account:
        return jsonify({'error': 'Account not found'}), 404

    data = request.get_json()
    symbol = data.get('symbol')
    position_side = data.get('position_side')  # LONG or SHORT
    stop_price = float(data.get('stop_price', 0))
    old_order_id = data.get('old_order_id')  # Existing stop order to cancel

    print(f"  Symbol: {symbol}, Side: {position_side}, Stop: {stop_price}")

    if not symbol or not position_side or stop_price <= 0:
        return jsonify({'error': 'Invalid parameters'}), 400

    try:
        client = BinanceClient(account['api_key'], account['api_secret'], testnet=account['is_testnet'])
        if account['is_testnet']:
            client.FUTURES_URL = 'https://testnet.binancefuture.com/fapi'

        # Get symbol precision info for price
        exchange_info = client.futures_exchange_info()
        symbol_info = None
        for s in exchange_info['symbols']:
            if s['symbol'] == symbol:
                symbol_info = s
                break

        # Get price tick size
        price_tick = 0.01  # Default
        if symbol_info:
            for f in symbol_info.get('filters', []):
                if f['filterType'] == 'PRICE_FILTER':
                    price_tick = float(f['tickSize'])
                    break

        # Round price to valid tick size
        if price_tick >= 1:
            price_precision = 0
        else:
            price_precision = int(round(-math.log10(price_tick)))
        stop_price = round(stop_price, price_precision)

        # Cancel ALL existing stop orders for this symbol (closePosition only allows one)
        debug_log = []  # Collect debug info for frontend

        # First try to cancel the specific order if provided
        if old_order_id:
            debug_log.append(f"Trying to cancel old_order_id: {old_order_id}")
            try:
                try:
                    cancel_algo_order(account['api_key'], account['api_secret'], old_order_id, account['is_testnet'])
                    debug_log.append(f"Algo cancel succeeded for {old_order_id}")
                except Exception as algo_err:
                    debug_log.append(f"Algo cancel failed: {str(algo_err)}, trying regular...")
                    client.futures_cancel_order(symbol=symbol, orderId=old_order_id)
                    debug_log.append(f"Regular cancel succeeded for {old_order_id}")
            except Exception as e:
                debug_log.append(f"Both cancel methods failed for {old_order_id}: {str(e)}")

        # Also find and cancel any other SL orders for this symbol (to be safe)
        order_side = 'SELL' if position_side == 'LONG' else 'BUY'
        try:
            # Check regular orders
            open_orders = client.futures_get_open_orders(symbol=symbol)
            debug_log.append(f"Found {len(open_orders)} regular open orders for {symbol}")
            for order in open_orders:
                if order.get('type') == 'STOP_MARKET' and order.get('side') == order_side:
                    order_id_to_cancel = order.get('orderId')
                    debug_log.append(f"Found regular STOP_MARKET {order_id_to_cancel}, cancelling...")
                    try:
                        client.futures_cancel_order(symbol=symbol, orderId=order_id_to_cancel)
                        debug_log.append(f"Cancelled regular order {order_id_to_cancel}")
                    except Exception as e:
                        debug_log.append(f"Failed to cancel regular order {order_id_to_cancel}: {str(e)}")

            # Check algo orders
            algo_orders = fetch_algo_orders(account['api_key'], account['api_secret'], account['is_testnet'])
            debug_log.append(f"Found {len(algo_orders)} algo orders total")
            for order in algo_orders:
                order_type = order.get('type') or order.get('orderType', '')
                if order.get('symbol') == symbol and order_type == 'STOP_MARKET' and order.get('side') == order_side:
                    algo_id = order.get('algoId')
                    debug_log.append(f"Found algo STOP_MARKET {algo_id}, cancelling...")
                    try:
                        cancel_algo_order(account['api_key'], account['api_secret'], algo_id, account['is_testnet'])
                        debug_log.append(f"Cancelled algo order {algo_id}")
                    except Exception as e:
                        debug_log.append(f"Failed to cancel algo order {algo_id}: {str(e)}")
        except Exception as e:
            debug_log.append(f"Error checking existing orders: {str(e)}")

        # For LONG position, stop-loss is a SELL; for SHORT, it's a BUY
        order_side = 'SELL' if position_side == 'LONG' else 'BUY'

        # Create new stop-loss order with closePosition=true (Conditional order)
        # This closes the ENTIRE position when triggered, even if position size changed
        # Using MARK_PRICE for more stable triggering (less prone to wicks)
        print(f"  Creating STOP_MARKET order: {order_side} @ stop {stop_price} (closePosition=true, workingType=MARK_PRICE)")
        order = client.futures_create_order(
            symbol=symbol,
            side=order_side,
            type='STOP_MARKET',
            stopPrice=str(stop_price),
            closePosition='true',
            workingType='MARK_PRICE'
        )

        # Log the full response for debugging
        print(f"  Binance order response: {order}")

        # Get orderId safely - Binance returns 'algoId' for conditional orders (STOP_MARKET, etc.)
        order_id = order.get('orderId') or order.get('algoId') or order.get('orderID') or order.get('order_id') or order.get('id')
        if not order_id:
            print(f"  ERROR: No orderId/algoId in response. Full response: {order}")
            return jsonify({'error': f'No orderId in response. Binance returned: {str(order)[:500]}'}), 500

        print(f"  Stop-loss order created: {order_id}")
        debug_log.append(f"New SL order created: {order_id}")
        return jsonify({
            'success': True,
            'order': {
                'orderId': order_id,
                'symbol': order.get('symbol', symbol),
                'side': order.get('side', order_side),
                'stopPrice': stop_price,
                'closePosition': True,
                'status': order.get('status', 'NEW')
            },
            '_debug': debug_log
        })
    except BinanceAPIException as e:
        print(f"BinanceAPIException: {e}")
        debug_log.append(f"BinanceAPIException: {e.message}")
        return jsonify({'error': f'Binance error: {e.message}', '_debug': debug_log}), 500
    except KeyError as e:
        print(f"KeyError accessing order response: {e}")
        import traceback
        traceback.print_exc()
        debug_log.append(f"KeyError: {e}")
        return jsonify({'error': f'Missing field in Binance response: {e}', '_debug': debug_log}), 500
    except Exception as e:
        print(f"Exception: {e}")
        import traceback
        traceback.print_exc()
        debug_log.append(f"Exception: {str(e)}")
        return jsonify({'error': f'Server error: {str(e)}', '_debug': debug_log}), 500


@app.route('/api/accounts/<int:account_id>/cancel-stop-loss', methods=['POST'])
def api_cancel_stop_loss(account_id):
    """Cancel a stop-loss order (supports both regular and algo/conditional orders)."""
    print(f"=== CANCEL STOP-LOSS for account_id: {account_id} ===")

    if not BINANCE_AVAILABLE:
        return jsonify({'error': 'Binance API not available'}), 500

    account = db.get_account(account_id)
    if not account:
        return jsonify({'error': 'Account not found'}), 404

    data = request.get_json()
    symbol = data.get('symbol')
    order_id = data.get('order_id')

    if not symbol or not order_id:
        return jsonify({'error': 'Invalid parameters'}), 400

    print(f"  Cancelling stop order {order_id} for {symbol}")
    debug_log = []
    debug_log.append(f"Attempting to cancel stop order {order_id} for {symbol}")

    # Try algo cancel first (for conditional orders created with closePosition=true)
    # If that fails, fall back to regular cancel
    algo_error_msg = None
    try:
        debug_log.append(f"Trying algo cancel for {order_id}...")
        result = cancel_algo_order(
            account['api_key'],
            account['api_secret'],
            order_id,
            account['is_testnet']
        )
        debug_log.append(f"Algo cancel SUCCESS for {order_id}")
        print(f"  Algo stop order {order_id} cancelled successfully")
        return jsonify({
            'success': True,
            'cancelled_order_id': order_id,
            '_debug': debug_log
        })
    except Exception as algo_error:
        algo_error_msg = str(algo_error)
        debug_log.append(f"Algo cancel FAILED: {algo_error_msg}")
        print(f"  Algo cancel failed: {algo_error}, trying regular cancel...")

    # Fall back to regular cancel
    try:
        debug_log.append(f"Trying regular cancel for {order_id}...")
        client = BinanceClient(account['api_key'], account['api_secret'], testnet=account['is_testnet'])
        if account['is_testnet']:
            client.FUTURES_URL = 'https://testnet.binancefuture.com/fapi'

        result = client.futures_cancel_order(symbol=symbol, orderId=order_id)
        debug_log.append(f"Regular cancel SUCCESS for {order_id}")
        print(f"  Regular stop order {order_id} cancelled successfully")
        return jsonify({
            'success': True,
            'cancelled_order_id': order_id,
            '_debug': debug_log
        })
    except BinanceAPIException as e:
        debug_log.append(f"Regular cancel FAILED (BinanceAPIException): {e.message}")
        print(f"BinanceAPIException: {e}")
        error_msg = f"Failed to cancel. Algo error: {algo_error_msg}. Regular error: {e.message}"
        return jsonify({'error': error_msg, '_debug': debug_log}), 500
    except Exception as e:
        debug_log.append(f"Regular cancel FAILED (Exception): {str(e)}")
        print(f"Exception: {e}")
        error_msg = f"Failed to cancel. Algo error: {algo_error_msg}. Regular error: {str(e)}"
        return jsonify({'error': error_msg, '_debug': debug_log}), 500


@app.route('/api/accounts/<int:account_id>/update-take-profit', methods=['POST'])
def api_update_take_profit(account_id):
    """Update or create a take-profit LIMIT order with reduceOnly for a position."""
    print(f"=== UPDATE TAKE-PROFIT for account_id: {account_id} ===")

    if not BINANCE_AVAILABLE:
        return jsonify({'error': 'Binance API not available'}), 500

    account = db.get_account(account_id)
    if not account:
        return jsonify({'error': 'Account not found'}), 404

    data = request.get_json()
    symbol = data.get('symbol')
    position_side = data.get('position_side')  # LONG or SHORT
    tp_price = float(data.get('tp_price', 0))
    old_order_id = data.get('old_order_id')  # Existing TP order to cancel

    print(f"  Symbol: {symbol}, Side: {position_side}, TP: {tp_price}")

    if not symbol or not position_side or tp_price <= 0:
        return jsonify({'error': 'Invalid parameters'}), 400

    debug_log = []  # Collect debug info for frontend

    try:
        client = BinanceClient(account['api_key'], account['api_secret'], testnet=account['is_testnet'])
        if account['is_testnet']:
            client.FUTURES_URL = 'https://testnet.binancefuture.com/fapi'

        # Get symbol precision info for price and quantity
        exchange_info = client.futures_exchange_info()
        symbol_info = None
        for s in exchange_info['symbols']:
            if s['symbol'] == symbol:
                symbol_info = s
                break

        # Get price tick size and quantity step size
        price_precision = 2
        qty_precision = 3
        if symbol_info:
            for f in symbol_info.get('filters', []):
                if f['filterType'] == 'PRICE_FILTER':
                    tick_size = float(f['tickSize'])
                    if tick_size >= 1:
                        price_precision = 0
                    else:
                        price_precision = int(round(-math.log10(tick_size)))
                if f['filterType'] == 'LOT_SIZE':
                    step_size = float(f['stepSize'])
                    if step_size >= 1:
                        qty_precision = 0
                    else:
                        qty_precision = int(round(-math.log10(step_size)))

        tp_price = round(tp_price, price_precision)

        # Get current position to determine quantity
        positions = client.futures_position_information(symbol=symbol)
        position_qty = 0
        for pos in positions:
            pos_amt = float(pos.get('positionAmt', 0))
            if pos_amt != 0:
                position_qty = abs(pos_amt)
                break

        if position_qty == 0:
            return jsonify({'error': 'No open position found for this symbol'}), 400

        position_qty = round(position_qty, qty_precision)
        debug_log.append(f"Position quantity: {position_qty}")

        # Cancel ALL existing TP orders for this symbol
        # First try to cancel the specific order if provided
        if old_order_id:
            debug_log.append(f"Trying to cancel old_order_id: {old_order_id}")
            try:
                print(f"  Cancelling old TP order: {old_order_id}")
                try:
                    cancel_algo_order(account['api_key'], account['api_secret'], old_order_id, account['is_testnet'])
                    debug_log.append(f"Algo cancel succeeded for {old_order_id}")
                    print(f"  Old algo TP order cancelled")
                except Exception as algo_err:
                    debug_log.append(f"Algo cancel failed: {str(algo_err)}, trying regular...")
                    client.futures_cancel_order(symbol=symbol, orderId=old_order_id)
                    debug_log.append(f"Regular cancel succeeded for {old_order_id}")
                    print(f"  Old regular TP order cancelled")
            except Exception as e:
                debug_log.append(f"Both cancel methods failed for {old_order_id}: {str(e)}")
                print(f"  Warning: Could not cancel old TP order: {e}")

        # Also find and cancel any other TP orders for this symbol (TAKE_PROFIT_MARKET or LIMIT reduceOnly)
        order_side = 'SELL' if position_side == 'LONG' else 'BUY'
        try:
            # Check regular orders - cancel TAKE_PROFIT_MARKET and LIMIT with reduceOnly
            open_orders = client.futures_get_open_orders(symbol=symbol)
            debug_log.append(f"Found {len(open_orders)} regular open orders for {symbol}")
            for order in open_orders:
                order_type = order.get('type')
                is_reduce_only = order.get('reduceOnly', False)
                # Cancel old TAKE_PROFIT_MARKET orders or LIMIT orders that are reduceOnly (old TPs)
                if order.get('side') == order_side:
                    if order_type == 'TAKE_PROFIT_MARKET' or (order_type == 'LIMIT' and is_reduce_only):
                        order_id_to_cancel = order.get('orderId')
                        debug_log.append(f"Found regular {order_type} (reduceOnly={is_reduce_only}) {order_id_to_cancel}, cancelling...")
                        try:
                            client.futures_cancel_order(symbol=symbol, orderId=order_id_to_cancel)
                            debug_log.append(f"Cancelled regular order {order_id_to_cancel}")
                        except Exception as e:
                            debug_log.append(f"Failed to cancel regular order {order_id_to_cancel}: {str(e)}")

            # Check algo orders
            algo_orders = fetch_algo_orders(account['api_key'], account['api_secret'], account['is_testnet'])
            debug_log.append(f"Found {len(algo_orders)} algo orders total")
            for order in algo_orders:
                order_type = order.get('type') or order.get('orderType', '')
                if order.get('symbol') == symbol and order_type == 'TAKE_PROFIT_MARKET' and order.get('side') == order_side:
                    algo_id = order.get('algoId')
                    debug_log.append(f"Found algo TAKE_PROFIT_MARKET {algo_id}, cancelling...")
                    try:
                        cancel_algo_order(account['api_key'], account['api_secret'], algo_id, account['is_testnet'])
                        debug_log.append(f"Cancelled algo order {algo_id}")
                    except Exception as e:
                        debug_log.append(f"Failed to cancel algo order {algo_id}: {str(e)}")
        except Exception as e:
            debug_log.append(f"Error checking existing orders: {str(e)}")
            print(f"  Warning: Could not check for existing orders: {e}")

        # For LONG position, take-profit is a SELL; for SHORT, it's a BUY
        order_side = 'SELL' if position_side == 'LONG' else 'BUY'

        # Create new take-profit as LIMIT order with reduceOnly
        # This places the order directly in the order book at the exact TP price
        print(f"  Creating LIMIT TP order: {order_side} {position_qty} @ {tp_price} (reduceOnly=true)")
        order = client.futures_create_order(
            symbol=symbol,
            side=order_side,
            type='LIMIT',
            price=str(tp_price),
            quantity=position_qty,
            reduceOnly='true',
            timeInForce='GTC'
        )

        # Log the full response for debugging
        print(f"  Binance order response: {order}")

        order_id = order.get('orderId')
        if not order_id:
            print(f"  ERROR: No orderId in response. Full response: {order}")
            return jsonify({'error': f'No orderId in response. Binance returned: {str(order)[:500]}'}), 500

        print(f"  Take-profit LIMIT order created: {order_id}")
        debug_log.append(f"New TP LIMIT order created: {order_id}")
        return jsonify({
            'success': True,
            'order': {
                'orderId': order_id,
                'symbol': order.get('symbol', symbol),
                'side': order.get('side', order_side),
                'price': tp_price,
                'quantity': position_qty,
                'reduceOnly': True,
                'status': order.get('status', 'NEW')
            },
            '_debug': debug_log
        })
    except BinanceAPIException as e:
        print(f"BinanceAPIException: {e}")
        debug_log.append(f"BinanceAPIException: {e.message}")
        return jsonify({'error': f'Binance error: {e.message}', '_debug': debug_log}), 500
    except KeyError as e:
        print(f"KeyError accessing order response: {e}")
        import traceback
        traceback.print_exc()
        debug_log.append(f"KeyError: {e}")
        return jsonify({'error': f'Missing field in Binance response: {e}', '_debug': debug_log}), 500
    except Exception as e:
        print(f"Exception: {e}")
        import traceback
        traceback.print_exc()
        debug_log.append(f"Exception: {str(e)}")
        return jsonify({'error': f'Server error: {str(e)}', '_debug': debug_log}), 500


@app.route('/api/accounts/<int:account_id>/cancel-take-profit', methods=['POST'])
def api_cancel_take_profit(account_id):
    """Cancel a take-profit order (supports both regular and algo/conditional orders)."""
    print(f"=== CANCEL TAKE-PROFIT for account_id: {account_id} ===")

    if not BINANCE_AVAILABLE:
        return jsonify({'error': 'Binance API not available'}), 500

    account = db.get_account(account_id)
    if not account:
        return jsonify({'error': 'Account not found'}), 404

    data = request.get_json()
    symbol = data.get('symbol')
    order_id = data.get('order_id')

    if not symbol or not order_id:
        return jsonify({'error': 'Invalid parameters'}), 400

    print(f"  Cancelling TP order {order_id} for {symbol}")
    debug_log = []
    debug_log.append(f"Attempting to cancel TP order {order_id} for {symbol}")

    # Try algo cancel first (for conditional orders created with closePosition=true)
    # If that fails, fall back to regular cancel
    algo_error_msg = None
    try:
        debug_log.append(f"Trying algo cancel for {order_id}...")
        result = cancel_algo_order(
            account['api_key'],
            account['api_secret'],
            order_id,
            account['is_testnet']
        )
        debug_log.append(f"Algo cancel SUCCESS for {order_id}")
        print(f"  Algo TP order {order_id} cancelled successfully")
        return jsonify({
            'success': True,
            'cancelled_order_id': order_id,
            '_debug': debug_log
        })
    except Exception as algo_error:
        algo_error_msg = str(algo_error)
        debug_log.append(f"Algo cancel FAILED: {algo_error_msg}")
        print(f"  Algo cancel failed: {algo_error}, trying regular cancel...")

    # Fall back to regular cancel
    try:
        debug_log.append(f"Trying regular cancel for {order_id}...")
        client = BinanceClient(account['api_key'], account['api_secret'], testnet=account['is_testnet'])
        if account['is_testnet']:
            client.FUTURES_URL = 'https://testnet.binancefuture.com/fapi'

        result = client.futures_cancel_order(symbol=symbol, orderId=order_id)
        debug_log.append(f"Regular cancel SUCCESS for {order_id}")
        print(f"  Regular TP order {order_id} cancelled successfully")
        return jsonify({
            'success': True,
            'cancelled_order_id': order_id,
            '_debug': debug_log
        })
    except BinanceAPIException as e:
        debug_log.append(f"Regular cancel FAILED (BinanceAPIException): {e.message}")
        print(f"BinanceAPIException: {e}")
        error_msg = f"Failed to cancel. Algo error: {algo_error_msg}. Regular error: {e.message}"
        return jsonify({'error': error_msg, '_debug': debug_log}), 500
    except Exception as e:
        debug_log.append(f"Regular cancel FAILED (Exception): {str(e)}")
        print(f"Exception: {e}")
        error_msg = f"Failed to cancel. Algo error: {algo_error_msg}. Regular error: {str(e)}"
        return jsonify({'error': error_msg, '_debug': debug_log}), 500


@app.route('/api/ticker/<symbol>', methods=['GET'])
def api_get_ticker(symbol):
    """Get current price for a symbol."""
    if not BINANCE_AVAILABLE:
        return jsonify({'error': 'Binance API not available'}), 500

    try:
        # Use testnet or mainnet based on first account (or default to mainnet)
        accounts = db.get_all_accounts()
        use_testnet = accounts[0]['is_testnet'] if accounts else False

        if use_testnet:
            base_url = 'https://testnet.binancefuture.com'
        else:
            base_url = 'https://fapi.binance.com'

        # Get ticker price
        response = requests.get(f'{base_url}/fapi/v1/ticker/price', params={'symbol': symbol}, timeout=5)
        if response.status_code == 200:
            data = response.json()
            return jsonify({'symbol': symbol, 'price': data.get('price', '0')})
        else:
            return jsonify({'error': f'Failed to get price: {response.text}'}), 500
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/accounts/<int:account_id>/trade', methods=['POST'])
def api_execute_trade(account_id):
    """Execute a new trade (market/limit/stop order)."""
    print(f"=== EXECUTE TRADE for account_id: {account_id} ===")

    if not BINANCE_AVAILABLE:
        return jsonify({'error': 'Binance API not available'}), 500

    account = db.get_account(account_id)
    if not account:
        return jsonify({'error': 'Account not found'}), 404

    data = request.get_json()
    symbol = data.get('symbol')
    side = data.get('side')  # BUY or SELL
    order_type = data.get('order_type', 'LIMIT')  # LIMIT, MARKET, STOP
    price = data.get('price')
    stop_price = data.get('stop_price')
    quantity = data.get('quantity')  # In USDC (notional value)
    leverage = data.get('leverage', 5)
    margin_type = data.get('margin_type', 'CROSSED')
    reduce_only = data.get('reduce_only', False)
    time_in_force = data.get('time_in_force', 'GTC')
    tp_price = data.get('tp_price')
    sl_price = data.get('sl_price')

    print(f"  Symbol: {symbol}, Side: {side}, Type: {order_type}")
    print(f"  Price: {price}, Quantity (USDC): {quantity}, Leverage: {leverage}x")

    debug_log = []

    if not symbol or not side or not quantity:
        return jsonify({'error': 'Missing required parameters'}), 400

    try:
        client = BinanceClient(account['api_key'], account['api_secret'], testnet=account['is_testnet'])
        if account['is_testnet']:
            client.FUTURES_URL = 'https://testnet.binancefuture.com/fapi'

        # Get symbol info for precision
        exchange_info = client.futures_exchange_info()
        symbol_info = None
        for s in exchange_info['symbols']:
            if s['symbol'] == symbol:
                symbol_info = s
                break

        if not symbol_info:
            return jsonify({'error': f'Symbol {symbol} not found'}), 400

        # Get price and quantity precision
        price_precision = 2
        qty_precision = 3
        for f in symbol_info.get('filters', []):
            if f['filterType'] == 'PRICE_FILTER':
                tick_size = float(f['tickSize'])
                if tick_size >= 1:
                    price_precision = 0
                else:
                    price_precision = int(round(-math.log10(tick_size)))
            if f['filterType'] == 'LOT_SIZE':
                step_size = float(f['stepSize'])
                if step_size >= 1:
                    qty_precision = 0
                else:
                    qty_precision = int(round(-math.log10(step_size)))

        debug_log.append(f"Symbol info: price_precision={price_precision}, qty_precision={qty_precision}")

        # Set leverage
        debug_log.append(f"Setting leverage to {leverage}x")
        try:
            client.futures_change_leverage(symbol=symbol, leverage=leverage)
        except Exception as e:
            debug_log.append(f"Leverage change warning: {str(e)}")

        # Set margin type
        debug_log.append(f"Setting margin type to {margin_type}")
        try:
            client.futures_change_margin_type(symbol=symbol, marginType=margin_type)
        except Exception as e:
            # Margin type might already be set
            debug_log.append(f"Margin type warning: {str(e)}")

        # Get current price to calculate quantity
        ticker = client.futures_symbol_ticker(symbol=symbol)
        current_price = float(ticker['price'])
        debug_log.append(f"Current price: {current_price}")

        # Convert USDC notional to quantity (contracts)
        # quantity_in_contracts = notional_value / price
        use_price = float(price) if price and order_type != 'MARKET' else current_price
        qty_in_contracts = float(quantity) / use_price
        qty_in_contracts = round(qty_in_contracts, qty_precision)

        debug_log.append(f"Quantity in contracts: {qty_in_contracts}")

        # Build order parameters
        order_params = {
            'symbol': symbol,
            'side': side,
            'quantity': qty_in_contracts,
        }

        if order_type == 'MARKET':
            order_params['type'] = 'MARKET'
        elif order_type == 'LIMIT':
            order_params['type'] = 'LIMIT'
            order_params['price'] = round(float(price), price_precision)
            order_params['timeInForce'] = time_in_force
        elif order_type == 'STOP':
            order_params['type'] = 'STOP'
            order_params['price'] = round(float(price), price_precision)
            order_params['stopPrice'] = round(float(stop_price), price_precision)
            order_params['timeInForce'] = time_in_force

        if reduce_only:
            order_params['reduceOnly'] = 'true'

        debug_log.append(f"Order params: {order_params}")

        # Execute order
        print(f"  Executing order: {order_params}")
        order = client.futures_create_order(**order_params)

        order_id = order.get('orderId') or order.get('algoId')
        debug_log.append(f"Order created: {order_id}")
        print(f"  Order created: {order_id}")

        # Create TP/SL if specified
        # TP uses LIMIT order with reduceOnly (sits in order book, executes at exact price)
        if tp_price and float(tp_price) > 0:
            try:
                tp_side = 'SELL' if side == 'BUY' else 'BUY'
                tp_order = client.futures_create_order(
                    symbol=symbol,
                    side=tp_side,
                    type='LIMIT',
                    price=str(round(float(tp_price), price_precision)),
                    quantity=qty_in_contracts,
                    reduceOnly='true',
                    timeInForce='GTC'
                )
                debug_log.append(f"TP LIMIT order created: {tp_order.get('orderId')}")
            except Exception as e:
                debug_log.append(f"TP creation failed: {str(e)}")

        if sl_price and float(sl_price) > 0:
            try:
                sl_side = 'SELL' if side == 'BUY' else 'BUY'
                sl_order = client.futures_create_order(
                    symbol=symbol,
                    side=sl_side,
                    type='STOP_MARKET',
                    stopPrice=str(round(float(sl_price), price_precision)),
                    closePosition='true',
                    workingType='MARK_PRICE'
                )
                debug_log.append(f"SL order created: {sl_order.get('orderId') or sl_order.get('algoId')}")
            except Exception as e:
                debug_log.append(f"SL creation failed: {str(e)}")

        return jsonify({
            'success': True,
            'order': {
                'orderId': order_id,
                'symbol': symbol,
                'side': side,
                'type': order_type,
                'quantity': qty_in_contracts,
                'price': price,
                'status': order.get('status', 'NEW')
            },
            '_debug': debug_log
        })

    except BinanceAPIException as e:
        print(f"BinanceAPIException: {e}")
        debug_log.append(f"BinanceAPIException: {e.message}")
        return jsonify({'error': f'Binance error: {e.message}', '_debug': debug_log}), 500
    except Exception as e:
        print(f"Exception: {e}")
        import traceback
        traceback.print_exc()
        debug_log.append(f"Exception: {str(e)}")
        return jsonify({'error': f'Server error: {str(e)}', '_debug': debug_log}), 500


@app.route('/api/accounts/<int:account_id>/sync', methods=['POST'])
def api_sync_account_trades(account_id):
    """Sync trades and balance from Binance."""
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
            client.FUTURES_URL = 'https://testnet.binancefuture.com/fapi'
            print(f"Using testnet URL: {client.FUTURES_URL}")
        else:
            print(f"Using mainnet URL: {client.FUTURES_URL}")

        # First, fetch and update account balance (check both USDT and USDC)
        print("Fetching account balance...")
        current_balance = 0
        usdt_balance = 0
        usdc_balance = 0
        try:
            balances = client.futures_account_balance()
            for bal in balances:
                if bal['asset'] == 'USDT':
                    usdt_balance = float(bal['balance'])
                    print(f"  USDT Balance: ${usdt_balance:.2f}")
                elif bal['asset'] == 'USDC':
                    usdc_balance = float(bal['balance'])
                    print(f"  USDC Balance: ${usdc_balance:.2f}")
            current_balance = usdt_balance + usdc_balance
            print(f"  Total Balance (USDT + USDC): ${current_balance:.2f}")
        except Exception as e:
            print(f"Warning: Could not fetch balance: {e}")

        # Get trades from last 7 days (Binance API limit is 7 days per request)
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
        unrealized_pnl = 0
        try:
            positions = client.futures_position_information()
            for pos in positions:
                try:
                    amt = float(pos.get('positionAmt', 0))
                    if amt != 0:
                        symbol = pos.get('symbol')
                        if symbol:
                            symbols_to_sync.add(symbol)
                            unrealized_pnl += float(pos.get('unRealizedProfit', 0))
                            print(f"  Found open position in {symbol}")
                except (ValueError, TypeError) as e:
                    print(f"  Warning: Error processing position {pos}: {e}")
                    continue
        except Exception as e:
            print(f"Warning: Could not fetch positions: {e}")

        # Check common trading pairs (both USDT and USDC pairs)
        priority_symbols = [
            # USDT pairs
            'BTCUSDT', 'ETHUSDT', 'SOLUSDT', 'DOGEUSDT',
            # USDC pairs
            'BTCUSDC', 'ETHUSDC', 'SOLUSDC', 'DOGEUSDC'
        ]
        symbols_to_sync.update(priority_symbols)

        print(f"Will sync {len(symbols_to_sync)} symbols")

        for symbol in symbols_to_sync:
            if symbol not in all_symbols:
                continue

            try:
                trades = client.futures_account_trades(
                    symbol=symbol,
                    startTime=start_time,
                    endTime=end_time,
                    limit=1000
                )

                for trade in trades:
                    total_checked += 1

                    try:
                        # Get required fields safely
                        trade_id = trade.get('id')
                        order_id = trade.get('orderId')
                        trade_symbol = trade.get('symbol')
                        trade_side = trade.get('side')

                        if not trade_id or not trade_symbol:
                            print(f"  Warning: Skipping trade with missing fields: {trade}")
                            continue

                        # Insert trade (will skip if already exists based on exchange_trade_id)
                        inserted = db.insert_trade(
                            account_id=account_id,
                            exchange_trade_id=trade_id,
                            order_id=order_id,
                            symbol=trade_symbol,
                            side=trade_side or 'UNKNOWN',
                            quantity=float(trade.get('qty', 0)),
                            price=float(trade.get('price', 0)),
                            realized_pnl=float(trade.get('realizedPnl', 0)),
                            commission=float(trade.get('commission', 0)),
                            commission_asset=trade.get('commissionAsset', ''),
                            trade_time=datetime.fromtimestamp(trade.get('time', 0) / 1000).isoformat() if trade.get('time') else None
                        )

                        if inserted:
                            new_trades += 1
                    except (ValueError, TypeError, KeyError) as e:
                        print(f"  Warning: Error processing trade {trade}: {e}")
                        continue

            except BinanceAPIException as e:
                if 'Invalid symbol' not in str(e):
                    print(f"BinanceAPIException syncing {symbol}: {e}")
            except Exception as e:
                print(f"Exception syncing {symbol}: {e}")

        # Update account stats in database (including balance)
        print("Updating account stats...")
        db.update_account_stats(account_id, current_balance=current_balance)

        # Get updated stats to return
        stats = db.get_trade_stats(account_id)
        
        # Add additional info to stats
        if stats:
            stats['unrealized_pnl'] = round(unrealized_pnl, 2)

        print(f"=== SYNC COMPLETE: {new_trades} new trades, {total_checked} total checked ===")
        return jsonify({
            'success': True,
            'new_trades': new_trades,
            'total_checked': total_checked,
            'message': f'Synced {new_trades} new trades',
            'stats': stats,
            'balance': round(current_balance, 2)
        })
    except BinanceAPIException as e:
        print(f"BinanceAPIException: {e}")
        return jsonify({'error': f'Binance error: {e.message}'}), 500
    except Exception as e:
        print(f"Exception: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


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


@app.route('/api/accounts/<int:account_id>/equity-curve', methods=['GET'])
def api_get_equity_curve(account_id):
    """Get equity curve data for an account based on trade history."""
    account = db.get_account(account_id)
    if not account:
        return jsonify({'error': 'Account not found'}), 404

    # Get starting balance
    starting_balance = account.get('starting_balance', 0) or 0

    # Get all trades for this account ordered by time
    trades = db.get_trades(account_id=account_id, limit=10000)

    if not trades:
        return jsonify({
            'data_points': [],
            'starting_balance': starting_balance,
            'current_balance': account.get('current_balance', starting_balance)
        })

    # Sort trades by trade_time
    trades.sort(key=lambda t: t.get('trade_time', ''))

    # Build equity curve - cumulative PnL over time
    equity_data = []
    cumulative_pnl = 0

    for trade in trades:
        pnl = trade.get('realized_pnl', 0) or 0
        commission = trade.get('commission', 0) or 0
        net_pnl = pnl - commission
        cumulative_pnl += net_pnl

        equity_data.append({
            'timestamp': trade.get('trade_time'),
            'pnl': round(cumulative_pnl, 2),
            'balance': round(starting_balance + cumulative_pnl, 2),
            'trade_pnl': round(net_pnl, 2),
            'symbol': trade.get('symbol', '')
        })

    return jsonify({
        'data_points': equity_data,
        'starting_balance': starting_balance,
        'current_balance': account.get('current_balance', starting_balance + cumulative_pnl)
    })


@app.route('/api/accounts/<int:account_id>/symbol-pnl', methods=['GET'])
def api_get_symbol_pnl(account_id):
    """Get PnL breakdown by symbol for an account."""
    account = db.get_account(account_id)
    if not account:
        return jsonify({'error': 'Account not found'}), 404

    # Get all trades for this account
    trades = db.get_trades(account_id=account_id, limit=10000)

    if not trades:
        return jsonify({'symbols': []})

    # Aggregate PnL by symbol
    symbol_data = {}
    for trade in trades:
        symbol = trade.get('symbol', 'UNKNOWN')
        pnl = trade.get('realized_pnl', 0) or 0
        commission = trade.get('commission', 0) or 0
        net_pnl = pnl - commission

        if symbol not in symbol_data:
            symbol_data[symbol] = {'pnl': 0, 'trades': 0, 'volume': 0}

        symbol_data[symbol]['pnl'] += net_pnl
        symbol_data[symbol]['trades'] += 1
        symbol_data[symbol]['volume'] += abs(trade.get('qty', 0) * trade.get('price', 0))

    # Convert to list
    symbols = [
        {
            'symbol': symbol,
            'pnl': round(data['pnl'], 2),
            'trades': data['trades'],
            'volume': round(data['volume'], 2)
        }
        for symbol, data in symbol_data.items()
    ]

    return jsonify({'symbols': symbols})


_cleanup_done = False

def cleanup_on_exit():
    """Clean up all running processes and database connections on application exit."""
    global _cleanup_done
    if _cleanup_done:
        return
    _cleanup_done = True

    print("\n[SHUTDOWN] Stopping all running scripts...")
    with process_lock:
        for script_id in list(running_processes.keys()):
            try:
                print(f"[SHUTDOWN] Stopping: {script_id}")
                stop_script_process(script_id)
            except Exception as e:
                print(f"[SHUTDOWN] Error stopping {script_id}: {e}")
    print("[SHUTDOWN] All scripts stopped.")

    # Close database connections and checkpoint WAL
    print("[SHUTDOWN] Closing database connections...")
    try:
        db.close_all_connections()
    except Exception as e:
        print(f"[SHUTDOWN] Error closing database: {e}")
    print("[SHUTDOWN] Cleanup complete.")


def handle_shutdown(signum, frame):
    """Handle SIGTERM/SIGINT/SIGQUIT for graceful shutdown (works with gunicorn/supervisor)."""
    sig_names = {2: 'SIGINT', 3: 'SIGQUIT', 15: 'SIGTERM'}
    sig_name = sig_names.get(signum, str(signum))
    print(f"\n[SHUTDOWN] Received {sig_name}")
    cleanup_on_exit()
    sys.exit(0)


# Register cleanup function for normal exit
atexit.register(cleanup_on_exit)

# Handle signals for gunicorn/supervisor graceful shutdown
# SIGTERM: sent by supervisor/gunicorn master
# SIGINT: Ctrl+C
# SIGQUIT: gunicorn graceful shutdown
signal.signal(signal.SIGTERM, handle_shutdown)
signal.signal(signal.SIGINT, handle_shutdown)
try:
    signal.signal(signal.SIGQUIT, handle_shutdown)  # Unix only, gunicorn uses this
except AttributeError:
    pass  # SIGQUIT not available on Windows


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
    print("=" * 60)
    print(f"  Scripts folder: {SCRIPTS_FOLDER}")
    print(f"  Logs folder: {LOGS_FOLDER}")
    print("  Logs are automatically cleared daily at midnight")
    print("=" * 60)

    # Use socketserver options to allow port reuse
    from werkzeug.serving import run_simple
    run_simple(
        '0.0.0.0', 5000, app,
        threaded=True,
        use_reloader=False,
        use_debugger=False,
        passthrough_errors=True
    )
