import sqlite3
import os
import logging
from flask import Flask, request, jsonify, render_template, Response, redirect, url_for
from functools import wraps
import subprocess
import json
import requests
from datetime import datetime, timedelta

app = Flask(__name__)
DB_FILE = 'tracker.db'
# Try to look for config in etc first, fallback to current directory
CONFIG_FILE = '/etc/gate-tracker/config.json'
if not os.path.exists(CONFIG_FILE):
    CONFIG_FILE = 'config.json'
SECRET_TOKEN = 'your_api_secret_here'


logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')


def get_secret_token():
    config = get_config()
    return config.get('secret_token', SECRET_TOKEN)


def get_dashboard_source_url():
    config = get_config()
    return config.get('dashboard_server_url', '').strip()


def fetch_dashboard_snapshot():
    config = get_config()
    expected_devices = config.get('expected_devices', ['pi-entrance', 'pi-exit'])
    source_url = get_dashboard_source_url()

    if source_url:
        try:
            response = requests.get(source_url.rstrip('/') + '/api/status', timeout=5)
            response.raise_for_status()
            snapshot = response.json()
            snapshot.setdefault('devices', [])
            snapshot.setdefault('counts', {})
            snapshot.setdefault('events', [])
            snapshot['source_mode'] = 'remote'
            snapshot['source_url'] = source_url
            snapshot['source_online'] = True
            snapshot['source_error'] = ''
            return snapshot, expected_devices, True
        except Exception as e:
            logging.warning(f"Failed to fetch dashboard snapshot from {source_url}: {e}")

    with sqlite3.connect(DB_FILE) as conn:
        conn.row_factory = sqlite3.Row
        c = conn.cursor()

        c.execute('SELECT company, count FROM counts')
        counts = {row['company']: row['count'] for row in c.fetchall()}

        c.execute('SELECT timestamp, gate, company, action FROM events ORDER BY timestamp DESC LIMIT 100')
        events = [dict(row) for row in c.fetchall()]

        c.execute('SELECT device, last_seen, status FROM devices')
        seen_devices = {row['device']: dict(row) for row in c.fetchall()}

    devices = []
    for device_name in expected_devices:
        device_data = seen_devices.get(device_name)
        if device_data:
            devices.append({
                "device": device_name,
                "last_seen": device_data.get("last_seen"),
                "status": device_data.get("status", "unknown"),
                "online": is_device_online(device_data.get("last_seen"))
            })
        else:
            devices.append({
                "device": device_name,
                "last_seen": None,
                "status": "missing",
                "online": False
            })

    return {
        "counts": counts,
        "events": events,
        "devices": devices,
        "source_mode": 'local-fallback' if source_url else 'local',
        "source_url": source_url,
        "source_online": False if source_url else True,
        "source_error": f"Unable to reach {source_url}" if source_url else ''
    }, expected_devices, False


def is_device_online(last_seen, timeout_seconds=30):
    if not last_seen:
        return False
    try:
        seen = datetime.strptime(last_seen, "%Y-%m-%d %H:%M:%S")
        return (datetime.now() - seen).total_seconds() <= timeout_seconds
    except ValueError:
        return False

def init_db():
    with sqlite3.connect(DB_FILE) as conn:
        c = conn.cursor()
        c.execute('''
            CREATE TABLE IF NOT EXISTS counts (
                company TEXT PRIMARY KEY,
                count INTEGER DEFAULT 0
            )
        ''')
        c.execute('''
            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp DATETIME DEFAULT (datetime('now', 'localtime')),
                gate TEXT,
                company TEXT,
                action TEXT
            )
        ''')
        c.execute('''
            CREATE TABLE IF NOT EXISTS devices (
                device TEXT PRIMARY KEY,
                last_seen DATETIME,
                status TEXT
            )
        ''')
        # Initialize companies if not exist
        c.execute('INSERT OR IGNORE INTO counts (company, count) VALUES ("Kinrise", 0)')
        c.execute('INSERT OR IGNORE INTO counts (company, count) VALUES ("Muve", 0)')
        conn.commit()

init_db()

def get_config():
    with open(CONFIG_FILE, 'r') as f:
        return json.load(f)

def save_config(config_data):
    with open(CONFIG_FILE, 'w') as f:
        json.dump(config_data, f, indent=4)

def check_auth(username, password):
    config = get_config()
    return username == config.get('admin_username') and password == config.get('admin_password')

def requires_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        auth = request.authorization
        if not auth or not check_auth(auth.username, auth.password):
            return Response(
                'Could not verify your access level for that URL.\n'
                'You have to login with proper credentials', 401,
                {'WWW-Authenticate': 'Basic realm="Login Required"'})
        return f(*args, **kwargs)
    return decorated

@app.route('/')
def index():
    snapshot, expected_devices, _ = fetch_dashboard_snapshot()
    return render_template(
        'index.html',
        counts=snapshot['counts'],
        events=snapshot['events'],
        expected_devices=expected_devices,
    )

@app.route('/api/status', methods=['GET'])
def get_status():
    snapshot, _, _ = fetch_dashboard_snapshot()
    return jsonify(snapshot)

@app.route('/api/event', methods=['POST'])
def handle_event():
    auth_header = request.headers.get('Authorization')
    if auth_header != f"Bearer {get_secret_token()}":
        return jsonify({"error": "Unauthorized"}), 401

    data = request.json
    gate = data.get('gate')
    company = data.get('company')
    action = data.get('action') # "enter" or "exit"

    if not all([gate, company, action]):
        return jsonify({"error": "Missing data"}), 400

    config = get_config()

    with sqlite3.connect(DB_FILE) as conn:
        c = conn.cursor()
        
        # Log event with local timestamp
        local_now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        c.execute('INSERT INTO events (timestamp, gate, company, action) VALUES (?, ?, ?, ?)', (local_now, gate, company, action))
        
        # Delete entries older than 30 days
        # thirty_days_ago = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d %H:%M:%S")
        # c.execute('DELETE FROM events WHERE timestamp < ?', (thirty_days_ago,))
        
        # Update count
        delta = 1 if action == "enter" else -1
        c.execute('UPDATE counts SET count = count + ? WHERE company = ?', (delta, company))
        
        # Ensure count doesn't go below 0 (optional but good practice)
        c.execute('UPDATE counts SET count = 0 WHERE count < 0')
        
        conn.commit()
        
        # Get updated count
        c.execute('SELECT count FROM counts WHERE company = ?', (company,))
        new_count = c.fetchone()[0]

    # Forward to external API if enabled
    forwarding = config.get('forwarding', {})
    if forwarding.get('enabled') and forwarding.get('url'):
        try:
            headers = {"Content-Type": "application/json"}
            if forwarding.get('token'):
                headers["Authorization"] = f"Bearer {forwarding.get('token')}"
            
            requests.post(
                forwarding.get('url'),
                json=data,
                headers=headers,
                timeout=5
            )
        except Exception as e:
            print(f"Failed to forward event: {e}")

    return jsonify({"success": True, "company": company, "new_count": new_count})


@app.route('/api/heartbeat', methods=['POST'])
def handle_heartbeat():
    auth_header = request.headers.get('Authorization')
    if auth_header != f"Bearer {get_secret_token()}":
        return jsonify({"error": "Unauthorized"}), 401

    data = request.json or {}
    device = data.get('device')
    status = data.get('status', 'ok')

    if not device:
        return jsonify({"error": "Missing device"}), 400

    # Record last seen as local time
    local_now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with sqlite3.connect(DB_FILE) as conn:
        c = conn.cursor()
        c.execute('INSERT OR REPLACE INTO devices (device, last_seen, status) VALUES (?, ?, ?)', (device, local_now, status))
        conn.commit()

    return jsonify({"success": True, "device": device, "last_seen": local_now})

@app.route('/admin', methods=['GET', 'POST'])
@requires_auth
def admin():
    config = get_config()
    if 'forwarding' not in config:
        config['forwarding'] = {"enabled": False, "url": "", "token": ""}
    if 'expected_devices' not in config:
        config['expected_devices'] = ['pi-entrance', 'pi-exit']

    with sqlite3.connect(DB_FILE) as conn:
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        c.execute('SELECT company, count FROM counts')
        counts = {row['company']: row['count'] for row in c.fetchall()}

    if request.method == 'POST':
        # Update GPIO pins
        for key in config['buttons']:
            new_pin = request.form.get(f'pin_{key}')
            if new_pin and new_pin.isdigit():
                config['buttons'][key]['gpio_pin'] = int(new_pin)

        # Manual count updates from admin page
        with sqlite3.connect(DB_FILE) as conn:
            c = conn.cursor()
            for company in counts.keys():
                new_count = request.form.get(f'count_{company}')
                if new_count is not None and new_count.strip() != '':
                    try:
                        parsed_count = max(0, int(new_count))
                        c.execute('UPDATE counts SET count = ? WHERE company = ?', (parsed_count, company))
                    except ValueError:
                        pass
            conn.commit()
        
        # Update credentials
        new_user = request.form.get('admin_username')
        new_pass = request.form.get('admin_password')
        if new_user: config['admin_username'] = new_user
        if new_pass: config['admin_password'] = new_pass
        
        # Update forwarding settings
        config['forwarding']['enabled'] = request.form.get('forwarding_enabled') == 'on'
        config['forwarding']['url'] = request.form.get('forwarding_url', '').strip()
        config['forwarding']['token'] = request.form.get('forwarding_token', '').strip()

        # Update local watcher/server auth settings
        new_server_url = request.form.get('server_url', '').strip()
        new_secret_token = request.form.get('secret_token', '').strip()
        dashboard_server_url = request.form.get('dashboard_server_url', '').strip()
        if new_server_url:
            config['server_url'] = new_server_url
        if new_secret_token:
            config['secret_token'] = new_secret_token
        config['dashboard_server_url'] = dashboard_server_url

        # Update expected device IDs for status lights
        expected_device_1 = request.form.get('expected_device_1', '').strip()
        expected_device_2 = request.form.get('expected_device_2', '').strip()
        expected_devices = []
        if expected_device_1:
            expected_devices.append(expected_device_1)
        if expected_device_2:
            expected_devices.append(expected_device_2)
        if expected_devices:
            config['expected_devices'] = expected_devices

        save_config(config)
        
        # Restart the watcher service to apply new GPIO settings
        try:
            subprocess.run(['systemctl', 'restart', 'gate-tracker-watcher.service'], check=True)
            message = "Settings updated and GPIO watcher restarted successfully."
        except Exception as e:
            message = f"Settings updated, but failed to restart watcher service: {str(e)}"

        with sqlite3.connect(DB_FILE) as conn:
            conn.row_factory = sqlite3.Row
            c = conn.cursor()
            c.execute('SELECT company, count FROM counts')
            counts = {row['company']: row['count'] for row in c.fetchall()}
            
        return render_template('admin.html', config=config, counts=counts, message=message)
        
    return render_template('admin.html', config=config, counts=counts)


@app.route('/manual-count', methods=['POST'])
@requires_auth
def manual_count_update():
    company = request.form.get('company')
    value = request.form.get('value', '').strip()

    if not company or value == '':
        return redirect(url_for('index'))

    try:
        count_value = max(0, int(value))
    except ValueError:
        return redirect(url_for('index'))

    with sqlite3.connect(DB_FILE) as conn:
        c = conn.cursor()
        c.execute('UPDATE counts SET count = ? WHERE company = ?', (count_value, company))
        conn.commit()

    return redirect(url_for('index'))

if __name__ == '__main__':
    # Run the server on port 80 (requires root)
    app.run(host='0.0.0.0', port=80)