import sqlite3
import os
from flask import Flask, request, jsonify, render_template

app = Flask(__name__)
DB_FILE = 'tracker.db'
SECRET_TOKEN = 'your_api_secret_here'

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
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                gate TEXT,
                company TEXT,
                action TEXT
            )
        ''')
        # Initialize companies if not exist
        c.execute('INSERT OR IGNORE INTO counts (company, count) VALUES ("A", 0)')
        c.execute('INSERT OR IGNORE INTO counts (company, count) VALUES ("B", 0)')
        conn.commit()

init_db()

@app.route('/')
def index():
    with sqlite3.connect(DB_FILE) as conn:
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        
        c.execute('SELECT company, count FROM counts')
        counts = {row['company']: row['count'] for row in c.fetchall()}
        
        c.execute('SELECT timestamp, gate, company, action FROM events ORDER BY timestamp DESC LIMIT 20')
        events = c.fetchall()
        
    return render_template('index.html', counts=counts, events=events)

@app.route('/api/event', methods=['POST'])
def handle_event():
    auth_header = request.headers.get('Authorization')
    if auth_header != f"Bearer {SECRET_TOKEN}":
        return jsonify({"error": "Unauthorized"}), 401

    data = request.json
    gate = data.get('gate')
    company = data.get('company')
    action = data.get('action') # "enter" or "exit"

    if not all([gate, company, action]):
        return jsonify({"error": "Missing data"}), 400

    with sqlite3.connect(DB_FILE) as conn:
        c = conn.cursor()
        
        # Log event
        c.execute('INSERT INTO events (gate, company, action) VALUES (?, ?, ?)', (gate, company, action))
        
        # Update count
        delta = 1 if action == "enter" else -1
        c.execute('UPDATE counts SET count = count + ? WHERE company = ?', (delta, company))
        
        # Ensure count doesn't go below 0 (optional but good practice)
        c.execute('UPDATE counts SET count = 0 WHERE count < 0')
        
        conn.commit()
        
        # Get updated count
        c.execute('SELECT count FROM counts WHERE company = ?', (company,))
        new_count = c.fetchone()[0]

    return jsonify({"success": True, "company": company, "new_count": new_count})

if __name__ == '__main__':
    # Run the server on all available interfaces (0.0.0.0)
    app.run(host='0.0.0.0', port=5000)