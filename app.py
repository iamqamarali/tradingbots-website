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
    BINANCE_AVAILABLE = True
except ImportError:
    BINANCE_AVAILABLE = False
    print("[WARNING] binance-python not installed. Account sync disabled.")

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
        for bal in balances:
            if bal['asset'] == 'USDT':
                usdt_balance = float(bal['balance'])
                print(f"USDT balance found: {usdt_balance}")
            elif bal['asset'] == 'USDC':
                usdc_balance = float(bal['balance'])
                print(f"USDC balance found: {usdc_balance}")
        
        # Combine both balances
        total_balance = usdt_balance + usdc_balance
        print(f"Total balance (USDT + USDC): {total_balance}")

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

        # Get all open orders to find stop-loss orders
        print("Fetching open orders for stop-loss info...")
        all_open_orders = []
        try:
            all_open_orders = client.futures_get_open_orders()
            print(f"Got {len(all_open_orders)} open orders")
        except Exception as e:
            print(f"Warning: Could not fetch open orders: {e}")

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
            symbol = order['symbol']
            order_type = order.get('type', '')
            stop_price = float(order.get('stopPrice', 0)) if order.get('stopPrice') else 0
            
            # Check for stop-loss orders
            if order_type in stop_order_types:
                if symbol not in stop_orders_map:
                    stop_orders_map[symbol] = []
                stop_orders_map[symbol].append({
                    'order_id': order['orderId'],
                    'type': order_type,
                    'side': order['side'],
                    'stop_price': stop_price,
                    'quantity': float(order.get('origQty', 0)),
                    'status': order.get('status', ''),
                    'activation_price': float(order.get('activatePrice', 0)) if order.get('activatePrice') else None
                })
                print(f"  Found stop order for {symbol}: {order_type} @ {stop_price}")
            
            # Also track take-profit orders
            elif order_type in ['TAKE_PROFIT_MARKET', 'TAKE_PROFIT']:
                if symbol not in tp_orders_map:
                    tp_orders_map[symbol] = []
                tp_orders_map[symbol].append({
                    'order_id': order['orderId'],
                    'type': order_type,
                    'side': order['side'],
                    'stop_price': stop_price,
                    'quantity': float(order.get('origQty', 0)),
                    'status': order.get('status', '')
                })
                print(f"  Found TP order for {symbol}: {order_type} @ {stop_price}")

        open_positions = []

        for pos in positions:
            amt = float(pos['positionAmt'])
            if amt != 0:
                entry_price = float(pos['entryPrice'])
                mark_price = float(pos['markPrice'])
                unrealized_pnl = float(pos['unRealizedProfit'])
                symbol = pos['symbol']
                side = 'LONG' if amt > 0 else 'SHORT'

                # Find stop-loss for this position
                # For LONG, stop-loss is a SELL order; for SHORT, it's a BUY order
                stop_price = None
                stop_order_id = None
                stop_type = None
                stop_orders = stop_orders_map.get(symbol, [])
                for stop in stop_orders:
                    # LONG position needs SELL stop, SHORT position needs BUY stop
                    if (side == 'LONG' and stop['side'] == 'SELL') or (side == 'SHORT' and stop['side'] == 'BUY'):
                        stop_price = stop['stop_price']
                        stop_order_id = stop['order_id']
                        stop_type = stop['type']
                        break
                
                # Find take-profit for this position
                tp_price = None
                tp_order_id = None
                tp_orders = tp_orders_map.get(symbol, [])
                for tp in tp_orders:
                    # LONG position needs SELL TP, SHORT position needs BUY TP
                    if (side == 'LONG' and tp['side'] == 'SELL') or (side == 'SHORT' and tp['side'] == 'BUY'):
                        tp_price = tp['stop_price']
                        tp_order_id = tp['order_id']
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
                all_open_orders = client.futures_get_open_orders()
            except Exception as e:
                print(f"Warning: Could not fetch open orders for {account_name}: {e}")

            # Build stop order maps
            stop_order_types = ['STOP_MARKET', 'STOP', 'STOP_LIMIT', 'TRAILING_STOP_MARKET']
            stop_orders_map = {}
            tp_orders_map = {}

            for order in all_open_orders:
                symbol = order['symbol']
                order_type = order.get('type', '')
                stop_price = float(order.get('stopPrice', 0)) if order.get('stopPrice') else 0

                if order_type in stop_order_types:
                    if symbol not in stop_orders_map:
                        stop_orders_map[symbol] = []
                    stop_orders_map[symbol].append({
                        'order_id': order['orderId'],
                        'type': order_type,
                        'side': order['side'],
                        'stop_price': stop_price,
                        'quantity': float(order.get('origQty', 0))
                    })
                elif order_type in ['TAKE_PROFIT_MARKET', 'TAKE_PROFIT']:
                    if symbol not in tp_orders_map:
                        tp_orders_map[symbol] = []
                    tp_orders_map[symbol].append({
                        'order_id': order['orderId'],
                        'type': order_type,
                        'side': order['side'],
                        'stop_price': stop_price,
                        'quantity': float(order.get('origQty', 0))
                    })

            for pos in positions:
                amt = float(pos['positionAmt'])
                if amt != 0:
                    entry_price = float(pos['entryPrice'])
                    mark_price = float(pos['markPrice'])
                    unrealized_pnl = float(pos['unRealizedProfit'])
                    symbol = pos['symbol']
                    side = 'LONG' if amt > 0 else 'SHORT'

                    # Find stop-loss
                    stop_price = None
                    stop_order_id = None
                    stop_type = None
                    for stop in stop_orders_map.get(symbol, []):
                        if (side == 'LONG' and stop['side'] == 'SELL') or (side == 'SHORT' and stop['side'] == 'BUY'):
                            stop_price = stop['stop_price']
                            stop_order_id = stop['order_id']
                            stop_type = stop['type']
                            break

                    # Find take-profit
                    tp_price = None
                    tp_order_id = None
                    for tp in tp_orders_map.get(symbol, []):
                        if (side == 'LONG' and tp['side'] == 'SELL') or (side == 'SHORT' and tp['side'] == 'BUY'):
                            tp_price = tp['stop_price']
                            tp_order_id = tp['order_id']
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

        return jsonify({
            'success': True,
            'order': {
                'orderId': order['orderId'],
                'symbol': order['symbol'],
                'side': order['side'],
                'quantity': order['origQty'],
                'status': order['status']
            }
        })
    except BinanceAPIException as e:
        print(f"BinanceAPIException closing position: {e}")
        return jsonify({'error': f'Binance error: {e.message}'}), 500
    except Exception as e:
        print(f"Exception closing position: {e}")
        return jsonify({'error': str(e)}), 500


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

        return jsonify({
            'success': True,
            'order': {
                'orderId': order['orderId'],
                'symbol': order['symbol'],
                'side': order['side'],
                'quantity': order['origQty'],
                'status': order['status']
            }
        })
    except BinanceAPIException as e:
        print(f"BinanceAPIException adding to position: {e}")
        return jsonify({'error': f'Binance error: {e.message}'}), 500
    except Exception as e:
        print(f"Exception adding to position: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/accounts/<int:account_id>/update-stop-loss', methods=['POST'])
def api_update_stop_loss(account_id):
    """Update or create a stop-loss order for a position."""
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
    quantity = float(data.get('quantity', 0))
    old_order_id = data.get('old_order_id')  # Existing stop order to cancel

    print(f"  Symbol: {symbol}, Side: {position_side}, Stop: {stop_price}, Qty: {quantity}")

    if not symbol or not position_side or stop_price <= 0 or quantity <= 0:
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

        # Adjust quantity precision
        step_size = 0.001  # Default
        price_tick = 0.01  # Default
        if symbol_info:
            for f in symbol_info.get('filters', []):
                if f['filterType'] == 'LOT_SIZE':
                    step_size = float(f['stepSize'])
                elif f['filterType'] == 'PRICE_FILTER':
                    price_tick = float(f['tickSize'])

        # Round quantity down to nearest valid step size
        quantity = math.floor(quantity / step_size) * step_size
        if step_size >= 1:
            qty_precision = 0
        else:
            qty_precision = int(round(-math.log10(step_size)))
        quantity = round(quantity, qty_precision)

        # Round price to valid tick size
        if price_tick >= 1:
            price_precision = 0
        else:
            price_precision = int(round(-math.log10(price_tick)))
        stop_price = round(stop_price, price_precision)

        if quantity <= 0:
            return jsonify({'error': 'Quantity too small after precision adjustment'}), 400

        # Cancel existing stop order if provided
        if old_order_id:
            try:
                print(f"  Cancelling old stop order: {old_order_id}")
                client.futures_cancel_order(symbol=symbol, orderId=old_order_id)
            except Exception as e:
                print(f"  Warning: Could not cancel old stop order: {e}")

        # For LONG position, stop-loss is a SELL; for SHORT, it's a BUY
        order_side = 'SELL' if position_side == 'LONG' else 'BUY'

        # Create new stop-loss order
        print(f"  Creating STOP_MARKET order: {order_side} {quantity} @ stop {stop_price} (step={step_size}, tick={price_tick})")
        order = client.futures_create_order(
            symbol=symbol,
            side=order_side,
            type='STOP_MARKET',
            stopPrice=str(stop_price),
            quantity=quantity,
            reduceOnly='true'
        )

        print(f"  Stop-loss order created: {order['orderId']}")
        return jsonify({
            'success': True,
            'order': {
                'orderId': order['orderId'],
                'symbol': order['symbol'],
                'side': order['side'],
                'stopPrice': stop_price,
                'quantity': order['origQty'],
                'status': order['status']
            }
        })
    except BinanceAPIException as e:
        print(f"BinanceAPIException: {e}")
        return jsonify({'error': f'Binance error: {e.message}'}), 500
    except Exception as e:
        print(f"Exception: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@app.route('/api/accounts/<int:account_id>/cancel-stop-loss', methods=['POST'])
def api_cancel_stop_loss(account_id):
    """Cancel a stop-loss order."""
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

    try:
        client = BinanceClient(account['api_key'], account['api_secret'], testnet=account['is_testnet'])
        if account['is_testnet']:
            client.FUTURES_URL = 'https://testnet.binancefuture.com/fapi'

        print(f"  Cancelling stop order {order_id} for {symbol}")
        result = client.futures_cancel_order(symbol=symbol, orderId=order_id)

        return jsonify({
            'success': True,
            'cancelled_order_id': order_id
        })
    except BinanceAPIException as e:
        print(f"BinanceAPIException: {e}")
        return jsonify({'error': f'Binance error: {e.message}'}), 500
    except Exception as e:
        print(f"Exception: {e}")
        return jsonify({'error': str(e)}), 500


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
                amt = float(pos['positionAmt'])
                if amt != 0:
                    symbols_to_sync.add(pos['symbol'])
                    unrealized_pnl += float(pos['unRealizedProfit'])
                    print(f"  Found open position in {pos['symbol']}")
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
    trades.sort(key=lambda t: t['trade_time'])

    # Build equity curve - cumulative PnL over time
    equity_data = []
    cumulative_pnl = 0

    for trade in trades:
        pnl = trade.get('realized_pnl', 0) or 0
        commission = trade.get('commission', 0) or 0
        net_pnl = pnl - commission
        cumulative_pnl += net_pnl

        equity_data.append({
            'timestamp': trade['trade_time'],
            'pnl': round(cumulative_pnl, 2),
            'balance': round(starting_balance + cumulative_pnl, 2),
            'trade_pnl': round(net_pnl, 2),
            'symbol': trade['symbol']
        })

    return jsonify({
        'data_points': equity_data,
        'starting_balance': starting_balance,
        'current_balance': account.get('current_balance', starting_balance + cumulative_pnl)
    })


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
