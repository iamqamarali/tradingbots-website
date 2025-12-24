"""
Trading Bot Script Manager
A Flask web application to manage, run, and monitor Python trading bot scripts.
"""

from dotenv import load_dotenv
load_dotenv()

from flask import Flask, render_template, request, jsonify, redirect, url_for, session, send_from_directory
from functools import wraps
from werkzeug.utils import secure_filename
import os
import subprocess
import signal
import sys
import uuid
import json
import secrets
import base64
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
SETUP_UPLOADS_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static', 'uploads', 'setups')
ALLOWED_IMAGE_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
MAX_IMAGE_SIZE = 10 * 1024 * 1024  # 10MB

# Ensure folders exist
os.makedirs(SCRIPTS_FOLDER, exist_ok=True)
os.makedirs(LOGS_FOLDER, exist_ok=True)
os.makedirs(SETUP_UPLOADS_FOLDER, exist_ok=True)

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


@app.route('/setups')
def setups_page():
    """Render the setups page."""
    return render_template('setups.html', active_page='setups')


@app.route('/charts')
def charts_page():
    """Render the TradingView charts page."""
    return render_template('charts.html', active_page='charts')


@app.route('/quick-trade')
@login_required
def quick_trade_page():
    """Render the quick trade page."""
    return render_template('quick_trade.html', active_page='quick-trade')


# ==================== SETUPS API ====================

@app.route('/api/setup-folders', methods=['GET'])
def api_get_setup_folders():
    """Get all setup folders."""
    folders = db.get_all_setup_folders()
    return jsonify(folders)


@app.route('/api/setup-folders', methods=['POST'])
def api_create_setup_folder():
    """Create a new setup folder."""
    data = request.json
    if not data:
        return jsonify({'error': 'No data provided'}), 400

    name = data.get('name', '').strip()
    if not name:
        return jsonify({'error': 'Folder name is required'}), 400

    description = data.get('description', '').strip() or None
    color = data.get('color', '#fbbf24').strip()

    folder_id = db.create_setup_folder(name, description, color)
    return jsonify({'id': folder_id, 'message': 'Folder created successfully'})


@app.route('/api/setup-folders/<int:folder_id>', methods=['GET'])
def api_get_setup_folder(folder_id):
    """Get a single setup folder."""
    folder = db.get_setup_folder(folder_id)
    if not folder:
        return jsonify({'error': 'Folder not found'}), 404
    return jsonify(folder)


@app.route('/api/setup-folders/<int:folder_id>', methods=['PUT'])
def api_update_setup_folder(folder_id):
    """Update a setup folder."""
    data = request.json
    if not data:
        return jsonify({'error': 'No data provided'}), 400

    name = data.get('name')
    description = data.get('description')
    color = data.get('color')

    db.update_setup_folder(folder_id, name=name, description=description, color=color)
    return jsonify({'message': 'Folder updated successfully'})


@app.route('/api/setup-folders/<int:folder_id>', methods=['DELETE'])
def api_delete_setup_folder(folder_id):
    """Delete a setup folder."""
    deleted = db.delete_setup_folder(folder_id)
    if deleted:
        return jsonify({'message': 'Folder deleted successfully'})
    return jsonify({'error': 'Folder not found'}), 404


@app.route('/api/setups', methods=['GET'])
def api_get_setups():
    """Get all setups with performance stats, optionally filtered by folder."""
    folder_id = request.args.get('folder_id', type=int)
    setups = db.get_all_setups_with_stats(folder_id=folder_id)
    return jsonify(setups)


@app.route('/api/setups/list-simple', methods=['GET'])
def api_get_setups_simple():
    """Get simple list of setups for dropdown selection."""
    setups = db.get_setups_simple_list()
    return jsonify(setups)


@app.route('/api/setups', methods=['POST'])
def api_create_setup():
    """Create a new setup."""
    data = request.json
    if not data:
        return jsonify({'error': 'No data provided'}), 400

    name = data.get('name', '').strip()
    if not name:
        return jsonify({'error': 'Setup name is required'}), 400

    folder_id = data.get('folder_id')
    description = data.get('description', '').strip() or None
    timeframe = data.get('timeframe', '').strip() or None
    image_data = data.get('image_data')
    notes = data.get('notes', '').strip() or None

    setup_id = db.create_setup(
        name=name,
        folder_id=folder_id,
        description=description,
        timeframe=timeframe,
        image_data=image_data,
        notes=notes
    )
    return jsonify({'id': setup_id, 'message': 'Setup created successfully'})


@app.route('/api/setups/<int:setup_id>', methods=['GET'])
def api_get_setup(setup_id):
    """Get a single setup."""
    setup = db.get_setup(setup_id)
    if not setup:
        return jsonify({'error': 'Setup not found'}), 404
    return jsonify(setup)


@app.route('/api/setups/<int:setup_id>', methods=['PUT'])
def api_update_setup(setup_id):
    """Update a setup."""
    data = request.json
    if not data:
        return jsonify({'error': 'No data provided'}), 400

    db.update_setup(
        setup_id,
        name=data.get('name'),
        folder_id=data.get('folder_id'),
        description=data.get('description'),
        timeframe=data.get('timeframe'),
        image_data=data.get('image_data'),
        notes=data.get('notes')
    )
    return jsonify({'message': 'Setup updated successfully'})


@app.route('/api/setups/<int:setup_id>', methods=['DELETE'])
def api_delete_setup(setup_id):
    """Delete a setup."""
    # First delete all associated images
    images = db.get_setup_images(setup_id)
    for img in images:
        image_path = db.delete_setup_image(img['id'])
        if image_path:
            try:
                full_path = os.path.join(SETUP_UPLOADS_FOLDER, os.path.basename(image_path))
                if os.path.exists(full_path):
                    os.remove(full_path)
            except Exception as e:
                print(f"Error deleting image file: {e}")

    deleted = db.delete_setup(setup_id)
    if deleted:
        return jsonify({'message': 'Setup deleted successfully'})
    return jsonify({'error': 'Setup not found'}), 404


# ==================== SETUP IMAGES API ====================

def allowed_image_file(filename):
    """Check if file extension is allowed."""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_IMAGE_EXTENSIONS


def generate_image_filename(setup_id, timeframe, original_filename):
    """Generate unique filename for uploaded image."""
    ext = original_filename.rsplit('.', 1)[1].lower() if '.' in original_filename else 'png'
    unique_id = uuid.uuid4().hex[:12]
    return f"{setup_id}_{timeframe}_{unique_id}.{ext}"


@app.route('/api/setups/<int:setup_id>/images', methods=['GET'])
def api_get_setup_images(setup_id):
    """Get all images for a setup."""
    images = db.get_setup_images(setup_id)
    return jsonify(images)


@app.route('/api/setups/<int:setup_id>/images', methods=['POST'])
def api_upload_setup_image(setup_id):
    """Upload an image for a setup."""
    # Check if setup exists
    setup = db.get_setup(setup_id)
    if not setup:
        return jsonify({'error': 'Setup not found'}), 404

    # Handle both JSON and form data
    if request.is_json:
        data = request.json
        timeframe = data.get('timeframe', '').strip() if data else ''
        notes = data.get('notes', '').strip() or None if data else None
        image_data_field = data.get('image_data') if data else None
    else:
        timeframe = request.form.get('timeframe', '').strip()
        notes = request.form.get('notes', '').strip() or None
        image_data_field = request.form.get('image_data')

    if not timeframe:
        return jsonify({'error': 'Timeframe is required'}), 400

    # Handle file upload (form data only)
    if 'file' in request.files:
        file = request.files['file']
        if file.filename == '':
            return jsonify({'error': 'No file selected'}), 400

        if not allowed_image_file(file.filename):
            return jsonify({'error': 'Invalid file type. Allowed: png, jpg, jpeg, gif, webp'}), 400

        # Generate unique filename
        filename = generate_image_filename(setup_id, timeframe, file.filename)
        filepath = os.path.join(SETUP_UPLOADS_FOLDER, filename)

        # Save file
        file.save(filepath)
        image_path = filename

    # Handle base64 image data (JSON or form data)
    elif image_data_field:
        image_data = image_data_field
        # Parse base64 data URL
        if ',' in image_data:
            header, data = image_data.split(',', 1)
            # Determine extension from header
            if 'png' in header:
                ext = 'png'
            elif 'jpeg' in header or 'jpg' in header:
                ext = 'jpg'
            elif 'gif' in header:
                ext = 'gif'
            elif 'webp' in header:
                ext = 'webp'
            else:
                ext = 'png'
        else:
            data = image_data
            ext = 'png'

        # Decode and save
        filename = f"{setup_id}_{timeframe}_{uuid.uuid4().hex[:12]}.{ext}"
        filepath = os.path.join(SETUP_UPLOADS_FOLDER, filename)

        try:
            image_bytes = base64.b64decode(data)
            with open(filepath, 'wb') as f:
                f.write(image_bytes)
            image_path = filename
        except Exception as e:
            return jsonify({'error': f'Failed to decode image: {str(e)}'}), 400
    else:
        return jsonify({'error': 'No image provided'}), 400

    # Get display order (add at end)
    existing_images = db.get_setup_images(setup_id)
    display_order = len(existing_images)

    # Create database record
    image_id = db.create_setup_image(setup_id, timeframe, image_path, notes, display_order)

    return jsonify({
        'id': image_id,
        'image_path': image_path,
        'message': 'Image uploaded successfully'
    })


@app.route('/api/setup-images/<int:image_id>', methods=['PUT'])
def api_update_setup_image(image_id):
    """Update a setup image (notes, timeframe)."""
    data = request.json
    if not data:
        return jsonify({'error': 'No data provided'}), 400

    image = db.get_setup_image(image_id)
    if not image:
        return jsonify({'error': 'Image not found'}), 404

    db.update_setup_image(
        image_id,
        timeframe=data.get('timeframe'),
        notes=data.get('notes'),
        display_order=data.get('display_order')
    )
    return jsonify({'message': 'Image updated successfully'})


@app.route('/api/setup-images/<int:image_id>', methods=['DELETE'])
def api_delete_setup_image(image_id):
    """Delete a setup image and its file."""
    image_path = db.delete_setup_image(image_id)
    if image_path:
        # Delete the file
        try:
            full_path = os.path.join(SETUP_UPLOADS_FOLDER, os.path.basename(image_path))
            if os.path.exists(full_path):
                os.remove(full_path)
        except Exception as e:
            print(f"Error deleting image file: {e}")
        return jsonify({'message': 'Image deleted successfully'})
    return jsonify({'error': 'Image not found'}), 404


# ==================== TRADE-SETUP LINKING API ====================

@app.route('/api/closed-positions/<int:position_id>/link-setup', methods=['PUT'])
def api_link_position_to_setup(position_id):
    """Link a closed position to a setup."""
    data = request.json
    if not data:
        return jsonify({'error': 'No data provided'}), 400

    setup_id = data.get('setup_id')
    if not setup_id:
        return jsonify({'error': 'setup_id is required'}), 400

    # Verify setup exists
    setup = db.get_setup(setup_id)
    if not setup:
        return jsonify({'error': 'Setup not found'}), 404

    updated = db.link_position_to_setup(position_id, setup_id)
    if updated:
        return jsonify({'message': 'Position linked to setup successfully'})
    return jsonify({'error': 'Position not found'}), 404


@app.route('/api/closed-positions/<int:position_id>/link-setup', methods=['DELETE'])
def api_unlink_position_from_setup(position_id):
    """Unlink a closed position from its setup."""
    updated = db.unlink_position_from_setup(position_id)
    if updated:
        return jsonify({'message': 'Position unlinked from setup successfully'})
    return jsonify({'error': 'Position not found'}), 404


# ==================== STRATEGIES API ====================

def calculate_ema(data, period):
    """Calculate EMA for given data and period."""
    if len(data) < period:
        return data[-1] if data else 0

    multiplier = 2 / (period + 1)
    ema = sum(data[:period]) / period  # Start with SMA

    for price in data[period:]:
        ema = (price * multiplier) + (ema * (1 - multiplier))

    return ema


@app.route('/api/strategies', methods=['GET'])
@login_required
def api_get_strategies():
    """Get all strategies."""
    strategies = db.get_all_strategies()
    return jsonify(strategies)


@app.route('/api/accounts/<int:account_id>/strategies', methods=['GET'])
@login_required
def api_get_account_strategies(account_id):
    """Get strategies for a specific account."""
    account = db.get_account(account_id)
    if not account:
        return jsonify({'error': 'Account not found'}), 404

    strategies = db.get_strategies_by_account(account_id)
    return jsonify(strategies)


@app.route('/api/strategies', methods=['POST'])
@login_required
def api_create_strategy():
    """Create a new strategy."""
    data = request.json
    if not data:
        return jsonify({'error': 'No data provided'}), 400

    name = data.get('name', '').strip()
    account_id = data.get('account_id')

    if not name:
        return jsonify({'error': 'Strategy name is required'}), 400
    if not account_id:
        return jsonify({'error': 'Account is required'}), 400

    # Verify account exists
    account = db.get_account(account_id)
    if not account:
        return jsonify({'error': 'Account not found'}), 404

    strategy_id = db.create_strategy(
        name=name,
        account_id=account_id,
        symbol=data.get('symbol', 'BTCUSDC'),
        fast_ema=data.get('fast_ema', 7),
        slow_ema=data.get('slow_ema', 19),
        risk_percent=data.get('risk_percent', 1.3),
        sl_lookback=data.get('sl_lookback', 4),
        sl_min_percent=data.get('sl_min_percent', 0.25),
        sl_max_percent=data.get('sl_max_percent', 1.81),
        leverage=data.get('leverage', 5),
        timeframe=data.get('timeframe', '30m')
    )

    return jsonify({'id': strategy_id, 'message': 'Strategy created successfully'})


@app.route('/api/strategies/<int:strategy_id>', methods=['GET'])
@login_required
def api_get_strategy(strategy_id):
    """Get a single strategy."""
    strategy = db.get_strategy(strategy_id)
    if not strategy:
        return jsonify({'error': 'Strategy not found'}), 404
    return jsonify(strategy)


@app.route('/api/strategies/<int:strategy_id>', methods=['PUT'])
@login_required
def api_update_strategy(strategy_id):
    """Update a strategy."""
    data = request.json
    if not data:
        return jsonify({'error': 'No data provided'}), 400

    strategy = db.get_strategy(strategy_id)
    if not strategy:
        return jsonify({'error': 'Strategy not found'}), 404

    db.update_strategy(
        strategy_id,
        name=data.get('name'),
        account_id=data.get('account_id'),
        symbol=data.get('symbol'),
        fast_ema=data.get('fast_ema'),
        slow_ema=data.get('slow_ema'),
        risk_percent=data.get('risk_percent'),
        sl_lookback=data.get('sl_lookback'),
        sl_min_percent=data.get('sl_min_percent'),
        sl_max_percent=data.get('sl_max_percent'),
        leverage=data.get('leverage'),
        timeframe=data.get('timeframe'),
        is_active=data.get('is_active')
    )
    return jsonify({'message': 'Strategy updated successfully'})


@app.route('/api/strategies/<int:strategy_id>', methods=['DELETE'])
@login_required
def api_delete_strategy(strategy_id):
    """Delete a strategy."""
    deleted = db.delete_strategy(strategy_id)
    if deleted:
        return jsonify({'message': 'Strategy deleted successfully'})
    return jsonify({'error': 'Strategy not found'}), 404


@app.route('/api/strategies/<int:strategy_id>/data', methods=['GET'])
@login_required
def api_get_strategy_data(strategy_id):
    """
    Get real-time data for a strategy:
    - Current price, EMAs, trend
    - Calculated SL price, position size, risk amount
    """
    if not BINANCE_AVAILABLE:
        return jsonify({'error': 'Binance API not available'}), 500

    strategy = db.get_strategy(strategy_id)
    if not strategy:
        return jsonify({'error': 'Strategy not found'}), 404

    account = db.get_account(strategy['account_id'])
    if not account:
        return jsonify({'error': 'Account not found'}), 404

    try:
        client = BinanceClient(account['api_key'], account['api_secret'], testnet=account['is_testnet'])
        if account['is_testnet']:
            client.FUTURES_URL = 'https://testnet.binancefuture.com/fapi'

        # Get more klines to scan back for crossover (100 candles = ~50 hours on 30m)
        lookback_candles = 100
        limit = max(strategy['slow_ema'] + lookback_candles, strategy['sl_lookback'] + 5)
        klines = client.futures_klines(
            symbol=strategy['symbol'],
            interval=strategy['timeframe'],
            limit=limit
        )

        if not klines or len(klines) < strategy['slow_ema']:
            return jsonify({'error': 'Not enough candle data'}), 400

        # Calculate EMAs from close prices
        closes = [float(k[4]) for k in klines]
        fast_ema = calculate_ema(closes, strategy['fast_ema'])
        slow_ema = calculate_ema(closes, strategy['slow_ema'])

        current_price = closes[-1]
        trend = 'BULLISH' if fast_ema > slow_ema else 'BEARISH'

        # Find actual crossover candle by scanning back through history
        # We need to calculate rolling EMAs to find where the crossover happened
        crossover_candle_idx = None
        crossover_time = ''

        # Need at least slow_ema periods to calculate EMA
        min_periods = strategy['slow_ema']

        # Scan backwards from the most recent candle to find crossover
        for i in range(len(closes) - 1, min_periods, -1):
            # Calculate EMAs up to candle i
            fast_ema_at_i = calculate_ema(closes[:i+1], strategy['fast_ema'])
            slow_ema_at_i = calculate_ema(closes[:i+1], strategy['slow_ema'])
            trend_at_i = 'BULLISH' if fast_ema_at_i > slow_ema_at_i else 'BEARISH'

            # Calculate EMAs for previous candle
            fast_ema_prev = calculate_ema(closes[:i], strategy['fast_ema'])
            slow_ema_prev = calculate_ema(closes[:i], strategy['slow_ema'])
            trend_prev = 'BULLISH' if fast_ema_prev > slow_ema_prev else 'BEARISH'

            # Found crossover if trend changed
            if trend_at_i != trend_prev:
                crossover_candle_idx = i
                # Get timestamp from kline (k[0] is open time in ms)
                crossover_timestamp = int(klines[i][0]) / 1000
                crossover_time = datetime.fromtimestamp(crossover_timestamp).isoformat()
                break

        # Calculate SL based on candles at crossover time (or current if no crossover found)
        if crossover_candle_idx is not None:
            # Get sl_lookback candles from the crossover point
            sl_start = max(0, crossover_candle_idx - strategy['sl_lookback'])
            sl_end = crossover_candle_idx
            sl_candles = klines[sl_start:sl_end] if sl_end > sl_start else klines[crossover_candle_idx:crossover_candle_idx+1]
        else:
            # No crossover found in range, use current candles
            sl_candles = klines[-(strategy['sl_lookback'] + 1):-1]
            if len(sl_candles) < strategy['sl_lookback']:
                sl_candles = klines[-strategy['sl_lookback']:]

        # For LONG: SL = lowest low, For SHORT: SL = highest high
        if sl_candles:
            long_sl = min(float(k[3]) for k in sl_candles)  # k[3] = low
            short_sl = max(float(k[2]) for k in sl_candles)  # k[2] = high
        else:
            # Fallback to current price with buffer
            long_sl = current_price * 0.98
            short_sl = current_price * 1.02

        # Check if trend has changed from stored (new crossover just happened)
        stored_direction = strategy.get('crossover_direction')
        crossover_just_happened = stored_direction is not None and stored_direction != trend

        if stored_direction is None or stored_direction != trend:
            # Update stored crossover data
            db.update_strategy_crossover(strategy_id, trend, long_sl, short_sl)

        # Calculate SL percentages based on locked crossover SL
        long_sl_percent = abs(current_price - long_sl) / current_price * 100
        short_sl_percent = abs(short_sl - current_price) / current_price * 100

        # Get account balance - use correct quote currency based on symbol
        balances = client.futures_account_balance()
        symbol = strategy['symbol'].upper()
        if symbol.endswith('USDC'):
            quote_asset = 'USDC'
        elif symbol.endswith('USDT'):
            quote_asset = 'USDT'
        else:
            quote_asset = 'USDT'  # Default fallback

        total_balance = 0
        for b in balances:
            if b['asset'] == quote_asset:
                total_balance = float(b['balance'])
                break

        # Calculate risk amount
        risk_amount = total_balance * (strategy['risk_percent'] / 100)

        # Calculate position sizes based on locked crossover SL
        long_position_size = risk_amount / (long_sl_percent / 100) if long_sl_percent > 0 else 0
        short_position_size = risk_amount / (short_sl_percent / 100) if short_sl_percent > 0 else 0

        # Check validity for both directions
        long_valid = strategy['sl_min_percent'] <= long_sl_percent <= strategy['sl_max_percent']
        short_valid = strategy['sl_min_percent'] <= short_sl_percent <= strategy['sl_max_percent']

        return jsonify({
            'current_price': round(current_price, 4),
            'fast_ema': round(fast_ema, 4),
            'slow_ema': round(slow_ema, 4),
            'trend': trend,
            'crossover_time': crossover_time,
            'crossover_just_happened': crossover_just_happened,
            'long': {
                'sl_price': round(long_sl, 4),
                'sl_percent': round(long_sl_percent, 4),
                'position_size': round(long_position_size, 2),
                'is_valid': long_valid,
                'invalid_reason': None if long_valid else f'SL {long_sl_percent:.2f}% outside range ({strategy["sl_min_percent"]}-{strategy["sl_max_percent"]}%)'
            },
            'short': {
                'sl_price': round(short_sl, 4),
                'sl_percent': round(short_sl_percent, 4),
                'position_size': round(short_position_size, 2),
                'is_valid': short_valid,
                'invalid_reason': None if short_valid else f'SL {short_sl_percent:.2f}% outside range ({strategy["sl_min_percent"]}-{strategy["sl_max_percent"]}%)'
            },
            'balance': round(total_balance, 2),
            'risk_amount': round(risk_amount, 2)
        })

    except BinanceAPIException as e:
        return jsonify({'error': f'Binance error: {e.message}'}), 500
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/strategies/<int:strategy_id>/trade', methods=['POST'])
@login_required
def api_execute_strategy_trade(strategy_id):
    """
    Execute a trade based on strategy parameters.
    Request body: {
        "direction": "LONG" | "SHORT",
        "order_type": "MARKET" | "LIMIT" (optional, default MARKET),
        "limit_price": float (required if order_type is LIMIT)
    }
    """
    if not BINANCE_AVAILABLE:
        return jsonify({'error': 'Binance API not available'}), 500

    strategy = db.get_strategy(strategy_id)
    if not strategy:
        return jsonify({'error': 'Strategy not found'}), 404

    data = request.get_json()
    direction = data.get('direction')
    order_type = data.get('order_type', 'MARKET').upper()
    limit_price = data.get('limit_price')

    if direction not in ['LONG', 'SHORT']:
        return jsonify({'error': 'Invalid direction. Must be LONG or SHORT'}), 400

    if order_type not in ['MARKET', 'LIMIT']:
        return jsonify({'error': 'Invalid order_type. Must be MARKET or LIMIT'}), 400

    if order_type == 'LIMIT' and not limit_price:
        return jsonify({'error': 'limit_price is required for LIMIT orders'}), 400

    account = db.get_account(strategy['account_id'])
    if not account:
        return jsonify({'error': 'Account not found'}), 404

    try:
        client = BinanceClient(account['api_key'], account['api_secret'], testnet=account['is_testnet'])
        if account['is_testnet']:
            client.FUTURES_URL = 'https://testnet.binancefuture.com/fapi'

        # Get current price
        ticker = client.futures_symbol_ticker(symbol=strategy['symbol'])
        current_price = float(ticker['price'])

        # For LIMIT orders, use limit_price as entry; for MARKET, use current_price
        entry_price = float(limit_price) if order_type == 'LIMIT' else current_price

        # Use locked crossover SL from strategy (not recalculated)
        if direction == 'LONG':
            sl_price = strategy.get('crossover_sl_long')
        else:
            sl_price = strategy.get('crossover_sl_short')

        if not sl_price:
            return jsonify({'error': 'No crossover detected yet. Wait for EMA crossover.'}), 400

        # Calculate SL percent based on entry price (limit or current)
        sl_percent = abs(entry_price - sl_price) / entry_price * 100

        # Validate SL range
        if not (strategy['sl_min_percent'] <= sl_percent <= strategy['sl_max_percent']):
            return jsonify({
                'error': f'SL {sl_percent:.2f}% outside allowed range ({strategy["sl_min_percent"]}-{strategy["sl_max_percent"]}%)'
            }), 400

        # Get balance and calculate position size - use correct quote currency
        balances = client.futures_account_balance()
        symbol = strategy['symbol'].upper()
        if symbol.endswith('USDC'):
            quote_asset = 'USDC'
        elif symbol.endswith('USDT'):
            quote_asset = 'USDT'
        else:
            quote_asset = 'USDT'  # Default fallback

        total_balance = 0
        for b in balances:
            if b['asset'] == quote_asset:
                total_balance = float(b['balance'])
                break

        risk_amount = total_balance * (strategy['risk_percent'] / 100)
        position_size_usd = risk_amount / (sl_percent / 100)

        # Get symbol precision
        exchange_info = client.futures_exchange_info()
        symbol_info = next((s for s in exchange_info['symbols']
                           if s['symbol'] == strategy['symbol']), None)

        if not symbol_info:
            return jsonify({'error': f'Symbol {strategy["symbol"]} not found'}), 400

        qty_precision = 3
        price_precision = 2
        for f in symbol_info.get('filters', []):
            if f['filterType'] == 'LOT_SIZE':
                step_size = float(f['stepSize'])
                qty_precision = int(round(-math.log10(step_size))) if step_size < 1 else 0
            if f['filterType'] == 'PRICE_FILTER':
                tick_size = float(f['tickSize'])
                price_precision = int(round(-math.log10(tick_size))) if tick_size < 1 else 0

        # Calculate quantity in contracts (use entry_price for calculation)
        qty_in_contracts = round(position_size_usd / entry_price, qty_precision)

        if qty_in_contracts <= 0:
            return jsonify({'error': 'Position size too small'}), 400

        # Set leverage
        try:
            client.futures_change_leverage(
                symbol=strategy['symbol'],
                leverage=strategy['leverage']
            )
        except:
            pass  # Leverage may already be set

        # Execute order (MARKET or LIMIT)
        side = 'BUY' if direction == 'LONG' else 'SELL'
        limit_price_formatted = None

        if order_type == 'LIMIT':
            # Format limit price with proper precision
            limit_price_formatted = round(float(limit_price), price_precision)
            order = client.futures_create_order(
                symbol=strategy['symbol'],
                side=side,
                type='LIMIT',
                quantity=qty_in_contracts,
                price=str(limit_price_formatted),
                timeInForce='GTC'
            )
        else:
            order = client.futures_create_order(
                symbol=strategy['symbol'],
                side=side,
                type='MARKET',
                quantity=qty_in_contracts
            )

        # For MARKET orders, wait and place SL immediately
        # For LIMIT orders, place SL order (it will be ready when limit fills)
        if order_type == 'MARKET':
            time.sleep(0.3)  # Wait for position to settle

        # Place stop loss with retry logic
        sl_side = 'SELL' if direction == 'LONG' else 'BUY'
        sl_price_formatted = round(sl_price, price_precision)

        sl_order = None
        max_retries = 3
        last_error = None

        for attempt in range(max_retries):
            try:
                sl_order = client.futures_create_order(
                    symbol=strategy['symbol'],
                    side=sl_side,
                    type='STOP_MARKET',
                    stopPrice=str(sl_price_formatted),
                    closePosition='true',
                    workingType='MARK_PRICE'
                )
                break  # Success, exit retry loop
            except BinanceAPIException as e:
                last_error = e
                if attempt < max_retries - 1:
                    time.sleep(1)  # Wait before retry
                else:
                    # All retries failed - return partial success with warning
                    return jsonify({
                        'success': True,
                        'warning': f'Order placed but SL failed after {max_retries} attempts: {e.message}',
                        'order': {
                            'orderId': order.get('orderId'),
                            'symbol': strategy['symbol'],
                            'side': side,
                            'type': order_type,
                            'quantity': qty_in_contracts,
                            'price': limit_price_formatted if order_type == 'LIMIT' else None,
                            'status': order.get('status')
                        },
                        'sl_order': None,
                        'details': {
                            'entry_price': entry_price,
                            'sl_percent': round(sl_percent, 2),
                            'position_size_usd': round(position_size_usd, 2),
                            'risk_amount': round(risk_amount, 2)
                        }
                    })

        return jsonify({
            'success': True,
            'order': {
                'orderId': order.get('orderId'),
                'symbol': strategy['symbol'],
                'side': side,
                'type': order_type,
                'quantity': qty_in_contracts,
                'price': limit_price_formatted if order_type == 'LIMIT' else None,
                'status': order.get('status')
            },
            'sl_order': {
                'orderId': sl_order.get('orderId') or sl_order.get('algoId'),
                'stop_price': sl_price_formatted
            },
            'details': {
                'entry_price': entry_price,
                'sl_percent': round(sl_percent, 2),
                'position_size_usd': round(position_size_usd, 2),
                'risk_amount': round(risk_amount, 2)
            }
        })

    except BinanceAPIException as e:
        return jsonify({'error': f'Binance error: {e.message}'}), 500
    except Exception as e:
        return jsonify({'error': str(e)}), 500


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
                'close_position': order.get('closePosition') == 'true' or order.get('closePosition') == True,
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
        debug_log.append(f"TP price (rounded): {tp_price}")

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

        # Create new take-profit as LIMIT order with reduceOnly=true
        # This places the order directly in the order book at the exact TP price
        print(f"  Creating LIMIT TP order: {order_side} {position_qty} @ {tp_price} (reduceOnly=true)")
        debug_log.append(f"Creating LIMIT {order_side} {position_qty} @ {tp_price} with reduceOnly=true")
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
    price_match = data.get('price_match')  # For BBO orders: OPPONENT, QUEUE, etc.

    print(f"  Symbol: {symbol}, Side: {side}, Type: {order_type}")
    print(f"  Price: {price}, Quantity (USDC): {quantity}, Leverage: {leverage}x")
    if price_match:
        print(f"  PriceMatch (BBO): {price_match}")

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

        # Set margin type FIRST (must be done before leverage)
        debug_log.append(f"Setting margin type to {margin_type}")
        try:
            client.futures_change_margin_type(symbol=symbol, marginType=margin_type)
            debug_log.append(f"Margin type set to {margin_type} successfully")
        except Exception as e:
            error_msg = str(e)
            # "No need to change margin type" means it's already set - this is fine
            if "No need to change margin type" in error_msg:
                debug_log.append(f"Margin type already set to {margin_type}")
            # Position exists - can't change margin type
            elif "position" in error_msg.lower() or "order" in error_msg.lower():
                debug_log.append(f"Cannot change margin type: {error_msg}")
                # Continue anyway - will use current margin type
            else:
                debug_log.append(f"Margin type warning: {error_msg}")

        # Set leverage
        debug_log.append(f"Setting leverage to {leverage}x")
        try:
            client.futures_change_leverage(symbol=symbol, leverage=leverage)
            debug_log.append(f"Leverage set to {leverage}x successfully")
        except Exception as e:
            debug_log.append(f"Leverage change warning: {str(e)}")

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

        debug_log.append(f"Order type received: '{order_type}'")

        if order_type == 'MARKET':
            order_params['type'] = 'MARKET'
            debug_log.append("Creating MARKET order (executes immediately at market price)")
        elif order_type == 'LIMIT':
            # Check if using priceMatch for BBO orders
            if price_match:
                # BBO order - use priceMatch instead of fixed price
                order_params['type'] = 'LIMIT'
                order_params['timeInForce'] = time_in_force
                order_params['priceMatch'] = price_match
                debug_log.append(f"Creating BBO LIMIT order with priceMatch={price_match}")
            elif not price or float(price) <= 0:
                return jsonify({'error': 'Limit order requires a valid price', '_debug': debug_log}), 400
            else:
                order_params['type'] = 'LIMIT'
                order_params['price'] = str(round(float(price), price_precision))
                order_params['timeInForce'] = time_in_force
                debug_log.append(f"Creating LIMIT order at price {order_params['price']} with TIF={time_in_force}")
        elif order_type == 'STOP':
            if not price or float(price) <= 0:
                return jsonify({'error': 'Stop order requires a valid limit price', '_debug': debug_log}), 400
            if not stop_price or float(stop_price) <= 0:
                return jsonify({'error': 'Stop order requires a valid stop/trigger price', '_debug': debug_log}), 400
            order_params['type'] = 'STOP'
            order_params['price'] = str(round(float(price), price_precision))
            order_params['stopPrice'] = str(round(float(stop_price), price_precision))
            order_params['timeInForce'] = time_in_force
            debug_log.append(f"Creating STOP order: trigger at {order_params['stopPrice']}, limit at {order_params['price']}")
        else:
            debug_log.append(f"Unknown order type: {order_type}, defaulting to LIMIT")
            order_params['type'] = 'LIMIT'
            if price and float(price) > 0:
                order_params['price'] = str(round(float(price), price_precision))
                order_params['timeInForce'] = time_in_force

        if reduce_only:
            order_params['reduceOnly'] = 'true'
            debug_log.append("Reduce-only mode enabled")

        debug_log.append(f"Final order params: {order_params}")

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
    """Sync trades and balance from Binance.

    Query Parameters:
        weeks: Number of weeks to fetch (default: 1, max: 26)
               Binance API limit is 7 days per request, so we loop through weeks.
    """
    # Get weeks parameter (default 1, max 26 = ~6 months which is Binance's history limit)
    weeks = request.args.get('weeks', 1, type=int)
    weeks = min(max(weeks, 1), 26)  # Clamp between 1 and 26

    print(f"=== SYNC TRADES CALLED for account_id: {account_id}, weeks: {weeks} ===")

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

        print(f"Will sync {len(symbols_to_sync)} symbols for {weeks} week(s)")

        # Loop through each week (Binance API limit is 7 days per request)
        # Start from oldest week and work towards present
        now = datetime.now()
        weeks_processed = 0

        for week_num in range(weeks - 1, -1, -1):  # Go from oldest to newest
            week_end = now - timedelta(days=week_num * 7)
            week_start = week_end - timedelta(days=7)

            end_time = int(week_end.timestamp() * 1000)
            start_time = int(week_start.timestamp() * 1000)

            print(f"  Fetching week {weeks - week_num}/{weeks}: {week_start.strftime('%Y-%m-%d')} to {week_end.strftime('%Y-%m-%d')}")

            for symbol in symbols_to_sync:
                if symbol not in all_symbols:
                    continue

                try:
                    # Binance API: GET /fapi/v1/userTrades
                    # Max limit is 1000 per request, 7 days max range
                    trades = client.futures_account_trades(
                        symbol=symbol,
                        startTime=start_time,
                        endTime=end_time,
                        limit=1000  # Max allowed by Binance API
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

            weeks_processed += 1

        # Update account stats in database (including balance)
        print("Updating account stats...")
        db.update_account_stats(account_id, current_balance=current_balance)

        # Process trades into closed positions
        print("Processing trades into closed positions...")
        db.process_trades_into_closed_positions(account_id)

        # Get closed positions count
        closed_positions_count = db.get_closed_positions_count(account_id)

        # Get updated stats to return
        stats = db.get_trade_stats(account_id)

        # Add additional info to stats
        if stats:
            stats['unrealized_pnl'] = round(unrealized_pnl, 2)

        print(f"=== SYNC COMPLETE: {new_trades} new trades, {total_checked} total checked, {weeks_processed} weeks processed ===")
        return jsonify({
            'success': True,
            'new_trades': new_trades,
            'total_checked': total_checked,
            'weeks_processed': weeks_processed,
            'closed_positions': closed_positions_count,
            'message': f'Synced {new_trades} new trades from {weeks_processed} week(s)',
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


@app.route('/api/accounts/<int:account_id>/trades', methods=['DELETE'])
def api_delete_account_trades(account_id):
    """Delete all trades and closed positions for an account."""
    account = db.get_account(account_id)
    if not account:
        return jsonify({'error': 'Account not found'}), 404

    trades_deleted, positions_deleted = db.delete_account_trades(account_id)

    return jsonify({
        'success': True,
        'trades_deleted': trades_deleted,
        'positions_deleted': positions_deleted,
        'message': f'Deleted {trades_deleted} trades and {positions_deleted} closed positions'
    })


# ==================== TRADES API ====================

@app.route('/api/trades', methods=['GET'])
def api_get_trades():
    """Get all trades with optional filters."""
    account_id = request.args.get('account_id', None, type=int)
    symbol = request.args.get('symbol', None)
    limit = request.args.get('limit', 40, type=int)
    offset = request.args.get('offset', 0, type=int)

    trades = db.get_trades(account_id=account_id, symbol=symbol, limit=limit, offset=offset)
    total = db.get_trades_count(account_id=account_id, symbol=symbol)

    return jsonify({
        'trades': trades,
        'total': total,
        'limit': limit,
        'offset': offset
    })


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


# ==================== CLOSED POSITIONS API ====================

@app.route('/api/closed-positions', methods=['GET'])
def api_get_closed_positions():
    """Get closed positions with optional filters."""
    account_id = request.args.get('account_id', None, type=int)
    symbol = request.args.get('symbol', None)
    limit = request.args.get('limit', 40, type=int)
    offset = request.args.get('offset', 0, type=int)

    positions = db.get_closed_positions(account_id=account_id, symbol=symbol, limit=limit, offset=offset)
    total = db.get_closed_positions_count(account_id=account_id, symbol=symbol)

    return jsonify({
        'positions': positions,
        'total': total,
        'limit': limit,
        'offset': offset
    })


@app.route('/api/closed-positions/<int:position_id>', methods=['DELETE'])
def api_delete_closed_position(position_id):
    """Delete a closed position."""
    if db.delete_closed_position(position_id):
        return jsonify({'success': True})
    return jsonify({'error': 'Position not found'}), 404


@app.route('/api/closed-positions/<int:position_id>/journal', methods=['GET'])
def api_get_position_journal(position_id):
    """Get journal data for a closed position."""
    journal = db.get_closed_position_journal(position_id)
    if journal:
        return jsonify(journal)
    return jsonify({'error': 'Position not found'}), 404


@app.route('/api/closed-positions/<int:position_id>/journal', methods=['PUT'])
def api_update_position_journal(position_id):
    """Update journal data for a closed position."""
    data = request.get_json()

    try:
        db.update_closed_position_journal(
            position_id,
            journal_notes=data.get('journal_notes'),
            emotion_tags=data.get('emotion_tags'),
            mistake_tags=data.get('mistake_tags'),
            rating=data.get('rating')
        )
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ==================== TRADE NOTIFICATIONS API ====================

@app.route('/api/notifications', methods=['GET'])
def api_get_notifications():
    """Get trade notifications history."""
    notifications = db.get_trade_notifications(limit=50)
    enabled = db.get_trade_notifications_enabled()
    return jsonify({'notifications': notifications, 'enabled': enabled})


@app.route('/api/notifications/toggle', methods=['POST'])
def api_toggle_notifications():
    """Toggle trade notifications on/off."""
    data = request.get_json()
    enabled = data.get('enabled', True)
    db.set_trade_notifications_enabled(enabled)
    return jsonify({'enabled': enabled, 'success': True})


@app.route('/api/notifications/clear', methods=['POST'])
def api_clear_notifications():
    """Clear trade notifications history."""
    db.clear_trade_notifications()
    return jsonify({'success': True})


@app.route('/api/push/subscribe', methods=['POST'])
def api_push_subscribe():
    """Subscribe to push notifications."""
    data = request.get_json()

    if not data or 'endpoint' not in data:
        return jsonify({'error': 'Invalid subscription data'}), 400

    try:
        endpoint = data['endpoint']
        keys = data.get('keys', {})
        p256dh = keys.get('p256dh', '')
        auth = keys.get('auth', '')

        db.save_push_subscription(endpoint, p256dh, auth)
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/push/vapid-key', methods=['GET'])
def api_get_vapid_key():
    """Get VAPID public key for push subscription."""
    public_key = os.environ.get('VAPID_PUBLIC_KEY', '')
    return jsonify({'publicKey': public_key})


@app.route('/api/accounts/<int:account_id>/closed-positions/stats', methods=['GET'])
def api_get_closed_positions_stats(account_id):
    """Get statistics for closed positions."""
    account = db.get_account(account_id)
    if not account:
        return jsonify({'error': 'Account not found'}), 404

    stats = db.get_closed_positions_stats(account_id)
    if stats:
        return jsonify(stats)

    return jsonify({
        'total_positions': 0,
        'total_pnl': 0,
        'total_commission': 0,
        'winning_positions': 0,
        'losing_positions': 0,
        'win_rate': 0
    })


@app.route('/api/accounts/<int:account_id>/process-closed-positions', methods=['POST'])
def api_process_closed_positions(account_id):
    """Process trades into closed positions for an account."""
    account = db.get_account(account_id)
    if not account:
        return jsonify({'error': 'Account not found'}), 404

    try:
        db.process_trades_into_closed_positions(account_id)
        stats = db.get_closed_positions_stats(account_id)
        return jsonify({
            'success': True,
            'message': 'Closed positions processed successfully',
            'stats': stats
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/accounts/<int:account_id>/stats', methods=['GET'])
def api_get_account_stats(account_id):
    """Get trade statistics for a specific account."""
    account = db.get_account(account_id)
    if not account:
        return jsonify({'error': 'Account not found'}), 404

    stats = db.get_trade_stats(account_id=account_id)
    if stats:
        # Add streak information
        trades = db.get_trades(account_id=account_id, limit=10000)
        if trades:
            # Sort by trade time
            trades.sort(key=lambda t: t.get('trade_time', ''))

            # Calculate streaks
            current_streak = 0
            max_win_streak = 0
            max_loss_streak = 0
            temp_win_streak = 0
            temp_loss_streak = 0

            for trade in trades:
                pnl = trade.get('realized_pnl', 0) or 0
                if pnl > 0:
                    temp_win_streak += 1
                    temp_loss_streak = 0
                    if temp_win_streak > max_win_streak:
                        max_win_streak = temp_win_streak
                elif pnl < 0:
                    temp_loss_streak += 1
                    temp_win_streak = 0
                    if temp_loss_streak > max_loss_streak:
                        max_loss_streak = temp_loss_streak

            # Current streak (positive for wins, negative for losses)
            if temp_win_streak > 0:
                current_streak = temp_win_streak
            elif temp_loss_streak > 0:
                current_streak = -temp_loss_streak

            stats['current_streak'] = current_streak
            stats['max_win_streak'] = max_win_streak
            stats['max_loss_streak'] = max_loss_streak
        else:
            stats['current_streak'] = 0
            stats['max_win_streak'] = 0
            stats['max_loss_streak'] = 0

        # Add total fees as alias for total_commission
        stats['total_fees'] = stats.get('total_commission', 0)

        return jsonify(stats)

    return jsonify({
        'total_trades': 0,
        'symbols_traded': 0,
        'winning_trades': 0,
        'losing_trades': 0,
        'breakeven_trades': 0,
        'win_rate': 0,
        'total_pnl': 0,
        'total_commission': 0,
        'total_fees': 0,
        'total_volume': 0,
        'avg_win': 0,
        'avg_loss': 0,
        'largest_win': 0,
        'largest_loss': 0,
        'profit_factor': 0,
        'current_streak': 0,
        'max_win_streak': 0,
        'max_loss_streak': 0
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
    dates = []
    values = []
    cumulative_pnl = 0

    for trade in trades:
        pnl = trade.get('realized_pnl', 0) or 0
        commission = trade.get('commission', 0) or 0
        net_pnl = pnl - commission
        cumulative_pnl += net_pnl

        trade_time = trade.get('trade_time', '')
        balance = round(starting_balance + cumulative_pnl, 2)

        equity_data.append({
            'timestamp': trade_time,
            'pnl': round(cumulative_pnl, 2),
            'balance': balance,
            'trade_pnl': round(net_pnl, 2),
            'symbol': trade.get('symbol', '')
        })

        # Format date for chart display
        if trade_time:
            try:
                from datetime import datetime
                dt = datetime.fromisoformat(trade_time.replace('Z', '+00:00'))
                dates.append(dt.strftime('%m/%d %H:%M'))
            except:
                dates.append(trade_time[:10] if len(trade_time) >= 10 else trade_time)
        else:
            dates.append('')
        values.append(balance)

    return jsonify({
        'data_points': equity_data,
        'dates': dates,
        'values': values,
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


# ==================== TRADE NOTIFICATIONS BACKGROUND CHECKER ====================

# Try to import pywebpush for push notifications
try:
    from pywebpush import webpush, WebPushException
    WEBPUSH_AVAILABLE = True
except ImportError:
    WEBPUSH_AVAILABLE = False
    print("[NOTIFICATIONS] pywebpush not installed - push notifications disabled")

notification_check_running = True


def send_push_notification(title, body, symbol, event_type='trade'):
    """Send push notification to all subscribers."""
    if not WEBPUSH_AVAILABLE:
        return

    vapid_private_key = os.environ.get('VAPID_PRIVATE_KEY', '')
    vapid_claims = {"sub": "mailto:alerts@tradingbot.local"}

    if not vapid_private_key:
        print("[NOTIFICATIONS] VAPID_PRIVATE_KEY not set - cannot send push notifications")
        return

    subscriptions = db.get_all_push_subscriptions()
    for sub in subscriptions:
        try:
            webpush(
                subscription_info=sub,
                data=json.dumps({
                    'title': title,
                    'body': body,
                    'symbol': symbol,
                    'event_type': event_type
                }),
                vapid_private_key=vapid_private_key,
                vapid_claims=vapid_claims
            )
        except WebPushException as e:
            print(f"[NOTIFICATIONS] Push notification failed: {e}")
            # Remove invalid subscription
            if e.response and e.response.status_code in [404, 410]:
                db.delete_push_subscription(sub['endpoint'])
        except Exception as e:
            print(f"[NOTIFICATIONS] Push error: {e}")


def check_trade_positions():
    """Background thread to check for new/closed positions."""
    global notification_check_running

    print("[NOTIFICATIONS] Starting trade position checker...")

    while notification_check_running:
        try:
            # Check if notifications are enabled
            if not db.get_trade_notifications_enabled():
                time.sleep(15)
                continue

            if not BINANCE_AVAILABLE:
                time.sleep(15)
                continue

            # Get all accounts
            accounts = db.get_all_accounts()

            for account in accounts:
                try:
                    account_id = account['id']
                    account_name = account['name']

                    # Get current positions from Binance
                    if account['is_testnet']:
                        client = BinanceClient(
                            api_key=account['api_key'],
                            api_secret=account['api_secret'],
                            testnet=True
                        )
                    else:
                        client = BinanceClient(
                            api_key=account['api_key'],
                            api_secret=account['api_secret']
                        )

                    positions = client.futures_position_information()
                    current_positions = {}

                    for pos in positions:
                        amt = float(pos.get('positionAmt', 0))
                        if amt != 0:
                            symbol = pos['symbol']
                            side = 'LONG' if amt > 0 else 'SHORT'
                            entry_price = float(pos.get('entryPrice', 0))
                            current_positions[symbol] = {
                                'side': side,
                                'entry_price': entry_price,
                                'quantity': abs(amt)
                            }

                    # Get previous snapshots
                    prev_snapshots = db.get_position_snapshots(account_id)

                    # Check for new positions (opened)
                    for symbol, pos in current_positions.items():
                        if symbol not in prev_snapshots:
                            # New position opened
                            db.add_trade_notification(
                                account_id, symbol, pos['side'], 'opened',
                                entry_price=pos['entry_price']
                            )
                            print(f"[NOTIFICATIONS] {account_name}: {symbol} {pos['side']} opened @ ${pos['entry_price']:.4f}")

                            title = f"Trade Opened: {symbol}"
                            body = f"{account_name}: {pos['side']} @ ${pos['entry_price']:.4f}"
                            send_push_notification(title, body, symbol, 'opened')

                        # Update snapshot
                        db.update_position_snapshot(
                            account_id, symbol, pos['side'],
                            pos['entry_price'], pos['quantity']
                        )

                    # Check for closed positions
                    for symbol, prev_pos in prev_snapshots.items():
                        if symbol not in current_positions:
                            # Position closed
                            db.add_trade_notification(
                                account_id, symbol, prev_pos['side'], 'closed',
                                entry_price=prev_pos['entry_price']
                            )
                            db.delete_position_snapshot(account_id, symbol)
                            print(f"[NOTIFICATIONS] {account_name}: {symbol} {prev_pos['side']} closed")

                            title = f"Trade Closed: {symbol}"
                            body = f"{account_name}: {prev_pos['side']} closed (Entry: ${prev_pos['entry_price']:.4f})"
                            send_push_notification(title, body, symbol, 'closed')

                except Exception as e:
                    print(f"[NOTIFICATIONS] Error checking account {account.get('name', account_id)}: {e}")

        except Exception as e:
            print(f"[NOTIFICATIONS] Position check error: {e}")

        # Check every 15 seconds
        time.sleep(15)


def stop_notification_checker():
    """Stop the notification checking thread."""
    global notification_check_running
    notification_check_running = False


# Start notification checking thread
notification_thread = Thread(target=check_trade_positions, daemon=True)
notification_thread.start()

# Register cleanup for notification checker
atexit.register(stop_notification_checker)


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
