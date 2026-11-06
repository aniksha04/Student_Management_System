import os
import sqlite3
from flask import Flask, render_template, request, jsonify
from werkzeug.utils import secure_filename

app = Flask(__name__)

# --- Configuration & Storage Initialization ---
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
UPLOAD_FOLDER = os.path.join(BASE_DIR, 'uploads')
DATABASE_FILE = os.path.join(BASE_DIR, 'tracker.db')
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024 

if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

# Helper function to open secure context connections with the database
def get_db_connection():
    conn = sqlite3.connect(DATABASE_FILE)
    conn.row_factory = sqlite3.Row  # Enables access via dictionary keys instead of indices
    return conn

# --- Initialize Database Schema ---
def init_db():
    conn = get_db_connection()
    # Create Users Table
    conn.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            role TEXT NOT NULL
        )
    ''')
    # Create Activities Table (Updated to include student metrics and custom attendance)
    conn.execute('''
        CREATE TABLE IF NOT EXISTS activities (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student TEXT NOT NULL,
            roll_no TEXT,
            gr_no TEXT,
            year TEXT,
            department TEXT,
            name TEXT NOT NULL,
            type TEXT NOT NULL,
            date TEXT NOT NULL,
            attendance TEXT NOT NULL,
            status TEXT DEFAULT 'Pending',
            file TEXT DEFAULT 'default_placeholder.pdf'
        )
    ''')
    conn.commit()
    conn.close()

# Run database setup on launch
init_db()

@app.route('/')
def index():
    return render_template('index.html')

# --- API Authentication Endpoints ---
@app.route('/api/auth/register', methods=['POST'])
def register():
    data = request.get_json() or {}
    username = data.get('username', '').strip()
    password = data.get('password', '')
    role = data.get('role', 'student')

    if not username or not password:
        return jsonify({"error": "Missing credentials"}), 400

    conn = get_db_connection()
    try:
        conn.execute('INSERT INTO users (username, password, role) VALUES (?, ?, ?)', 
                     (username, password, role))
        conn.commit()
    except sqlite3.IntegrityError:
        return jsonify({"error": "Username already exists"}), 400
    finally:
        conn.close()

    return jsonify({"message": "Registration successful"}), 201

@app.route('/api/auth/login', methods=['POST'])
def login():
    data = request.get_json() or {}
    username = data.get('username', '').strip()
    password = data.get('password', '')

    conn = get_db_connection()
    user = conn.execute('SELECT * FROM users WHERE LOWER(username) = LOWER(?) AND password = ?', 
                        (username, password)).fetchone()
    conn.close()

    if user:
        return jsonify({"username": user['username'], "role": user['role']}), 200
    return jsonify({"error": "Invalid username or password"}), 401

# --- API Activity Management Endpoints ---
@app.route('/api/activities', methods=['GET'])
def get_activities():
    status_filter = request.args.get('status')
    conn = get_db_connection()
    
    if status_filter:
        rows = conn.execute('SELECT * FROM activities WHERE LOWER(status) = LOWER(?)', (status_filter,)).fetchall()
    else:
        rows = conn.execute('SELECT * FROM activities').fetchall()
    conn.close()

    # Convert native database rows into list dictionaries for our frontend
    activities_list = [dict(row) for row in rows]
    return jsonify(activities_list), 200

@app.route('/api/activities', methods=['POST'])
def add_activity():
    name = request.form.get('name')
    activity_type = request.form.get('type')
    date = request.form.get('date')
    student = request.form.get('student', 'Anonymous Submitter')
    
    # New student identifiers extracted from the form request
    roll_no = request.form.get('roll_no', '')
    gr_no = request.form.get('gr_no', '')
    year = request.form.get('year', '')
    department = request.form.get('department', '')
    
    # Custom attendance input directly from user form data instead of hardcoded 'Present'
    attendance = request.form.get('attendance', 'Present')
    
    file = request.files.get('file')
    filename = "default_placeholder.pdf"

    if file and file.filename != '':
        safe_name = secure_filename(file.filename)
        filename = f"{secure_filename(student)}_{safe_name}"
        file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO activities (student, roll_no, gr_no, year, department, name, type, date, attendance, status, file) 
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (student, roll_no, gr_no, year, department, name, activity_type, date, attendance, 'Pending', filename))
    conn.commit()
    new_id = cursor.lastrowid
    conn.close()

    return jsonify({
        "id": new_id, 
        "student": student, 
        "roll_no": roll_no,
        "gr_no": gr_no,
        "year": year,
        "department": department,
        "name": name, 
        "type": activity_type, 
        "date": date, 
        "attendance": attendance, 
        "status": "Pending", 
        "file": filename
    }), 201

@app.route('/api/activities/approve/<int:activity_id>', methods=['POST'])
def approve_activity(activity_id):
    data = request.get_json() or {}
    action = data.get('action')
    
    if action not in ['approve', 'reject']:
        return jsonify({"error": "Invalid action value context"}), 400

    new_status = "Approved" if action == "approve" else "Rejected"

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('UPDATE activities SET status = ? WHERE id = ?', (new_status, activity_id))
    conn.commit()
    changes = cursor.rowcount
    conn.close()

    if changes == 0:
        return jsonify({"error": "Activity record not found"}), 404

    return jsonify({"message": f"Activity successfully {action}d"}), 200

if __name__ == '__main__':
    app.run(debug=True, port=5000)