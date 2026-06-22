import sqlite3
import hashlib
from datetime import datetime
import os

def init_db():
    """Initialize the database with required tables"""
    conn = sqlite3.connect('attendance.db')
    cursor = conn.cursor()
    
    # Users table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            full_name TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            role TEXT DEFAULT 'employee',
            status TEXT DEFAULT 'pending',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Face encodings table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS face_encodings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            encoding BLOB NOT NULL,
            image_path TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
    ''')
    
    # Attendance records table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS attendance (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            status TEXT DEFAULT 'present',
            confidence REAL,
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
    ''')
    
    conn.commit()
    
    # Create default admin account if not exists
    cursor.execute('SELECT COUNT(*) FROM users WHERE role = ?', ('admin',))
    if cursor.fetchone()[0] == 0:
        admin_password_hash = hash_password('admin123')
        cursor.execute('''
            INSERT INTO users (username, password_hash, full_name, email, role, status)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', ('admin', admin_password_hash, 'System Administrator', 'admin@attendance.system', 'admin', 'approved'))
        conn.commit()
    
    conn.close()

def hash_password(password):
    """Hash password using SHA-256"""
    return hashlib.sha256(password.encode()).hexdigest()

def verify_user(username, password):
    """Verify user credentials"""
    conn = sqlite3.connect('attendance.db')
    cursor = conn.cursor()
    
    password_hash = hash_password(password)
    cursor.execute('''
        SELECT id, username, full_name, email, role, status FROM users 
        WHERE username = ? AND password_hash = ?
    ''', (username, password_hash))
    
    user = cursor.fetchone()
    conn.close()
    
    if user:
        return {
            'id': user[0],
            'username': user[1],
            'full_name': user[2],
            'email': user[3],
            'role': user[4],
            'status': user[5]
        }
    return None

def create_user(username, password, full_name, email):
    """Create a new user (as employee with pending status)"""
    conn = sqlite3.connect('attendance.db')
    cursor = conn.cursor()
    
    password_hash = hash_password(password)
    
    try:
        cursor.execute('''
            INSERT INTO users (username, password_hash, full_name, email, role, status)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (username, password_hash, full_name, email, 'employee', 'pending'))
        
        user_id = cursor.lastrowid
        conn.commit()
        conn.close()
        return user_id
    except sqlite3.IntegrityError:
        conn.close()
        return None

def save_attendance(user_id, confidence):
    """Save attendance record"""
    conn = sqlite3.connect('attendance.db')
    cursor = conn.cursor()
    
    cursor.execute('''
        INSERT INTO attendance (user_id, confidence)
        VALUES (?, ?)
    ''', (user_id, confidence))
    
    conn.commit()
    conn.close()

def get_user_attendance(user_id, date=None):
    """Get attendance records for a user"""
    conn = sqlite3.connect('attendance.db')
    cursor = conn.cursor()
    
    if date:
        cursor.execute('''
            SELECT datetime(timestamp, 'localtime'), status, confidence FROM attendance
            WHERE user_id = ? AND DATE(timestamp, 'localtime') = ?
            ORDER BY timestamp DESC
        ''', (user_id, date))
    else:
        cursor.execute('''
            SELECT datetime(timestamp, 'localtime'), status, confidence FROM attendance
            WHERE user_id = ?
            ORDER BY timestamp DESC
        ''', (user_id,))
    
    records = cursor.fetchall()
    conn.close()
    return records

def get_today_attendance():
    """Get today's attendance for all users"""
    conn = sqlite3.connect('attendance.db')
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT u.full_name, datetime(a.timestamp, 'localtime'), a.confidence
        FROM attendance a
        JOIN users u ON a.user_id = u.id
        WHERE DATE(a.timestamp, 'localtime') = DATE('now', 'localtime')
        ORDER BY a.timestamp DESC
    ''', )
    
    records = cursor.fetchall()
    conn.close()
    return records

def get_pending_employees():
    """Get all pending employees waiting for approval"""
    conn = sqlite3.connect('attendance.db')
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT u.id, u.username, u.full_name, u.email, u.created_at, lf.image_path
        FROM users u
        LEFT JOIN (
            SELECT f.user_id, f.image_path
            FROM face_encodings f
            INNER JOIN (
                SELECT user_id, MAX(id) AS max_id
                FROM face_encodings
                GROUP BY user_id
            ) latest ON latest.max_id = f.id
        ) lf ON lf.user_id = u.id
        WHERE u.role = 'employee' AND u.status = 'pending'
        ORDER BY created_at DESC
    ''')
    
    records = cursor.fetchall()
    conn.close()
    return records

def get_approved_employees():
    """Get all approved employees"""
    conn = sqlite3.connect('attendance.db')
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT u.id, u.username, u.full_name, u.email, u.created_at, lf.image_path
        FROM users u
        LEFT JOIN (
            SELECT f.user_id, f.image_path
            FROM face_encodings f
            INNER JOIN (
                SELECT user_id, MAX(id) AS max_id
                FROM face_encodings
                GROUP BY user_id
            ) latest ON latest.max_id = f.id
        ) lf ON lf.user_id = u.id
        WHERE u.role = 'employee' AND u.status = 'approved'
        ORDER BY created_at DESC
    ''')
    
    records = cursor.fetchall()
    conn.close()
    return records

def get_rejected_employees():
    """Get all rejected employees"""
    conn = sqlite3.connect('attendance.db')
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT u.id, u.username, u.full_name, u.email, u.created_at, lf.image_path
        FROM users u
        LEFT JOIN (
            SELECT f.user_id, f.image_path
            FROM face_encodings f
            INNER JOIN (
                SELECT user_id, MAX(id) AS max_id
                FROM face_encodings
                GROUP BY user_id
            ) latest ON latest.max_id = f.id
        ) lf ON lf.user_id = u.id
        WHERE u.role = 'employee' AND u.status = 'rejected'
        ORDER BY created_at DESC
    ''')
    
    records = cursor.fetchall()
    conn.close()
    return records

def approve_employee(user_id):
    """Approve a pending employee"""
    conn = sqlite3.connect('attendance.db')
    cursor = conn.cursor()
    
    cursor.execute('''
        UPDATE users SET status = 'approved'
        WHERE id = ? AND role = 'employee'
    ''', (user_id,))
    
    conn.commit()
    conn.close()
    return True

def reject_employee(user_id):
    """Reject a pending employee"""
    conn = sqlite3.connect('attendance.db')
    cursor = conn.cursor()
    
    cursor.execute('''
        UPDATE users SET status = 'rejected'
        WHERE id = ? AND role = 'employee'
    ''', (user_id,))
    
    conn.commit()
    conn.close()
    return True

def get_employee_by_id(user_id):
    """Get employee details by ID"""
    conn = sqlite3.connect('attendance.db')
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT u.id, u.username, u.full_name, u.email, u.role, u.status, u.created_at, lf.image_path
        FROM users u
        LEFT JOIN (
            SELECT f.user_id, f.image_path
            FROM face_encodings f
            INNER JOIN (
                SELECT user_id, MAX(id) AS max_id
                FROM face_encodings
                GROUP BY user_id
            ) latest ON latest.max_id = f.id
        ) lf ON lf.user_id = u.id
        WHERE u.id = ?
    ''', (user_id,))
    
    record = cursor.fetchone()
    conn.close()
    
    if record:
        return {
            'id': record[0],
            'username': record[1],
            'full_name': record[2],
            'email': record[3],
            'role': record[4],
            'status': record[5],
            'created_at': record[6],
            'face_image_path': record[7]
        }
    return None

def get_user_face_image_path(user_id):
    """Get latest registered face image path for a user"""
    conn = sqlite3.connect('attendance.db')
    cursor = conn.cursor()

    cursor.execute('''
        SELECT image_path FROM face_encodings
        WHERE user_id = ?
        ORDER BY id DESC
        LIMIT 1
    ''', (user_id,))

    row = cursor.fetchone()
    conn.close()
    return row[0] if row else None

def search_employees(search_term):
    """Search employees by username, full_name, or email"""
    conn = sqlite3.connect('attendance.db')
    cursor = conn.cursor()
    
    search_pattern = f"%{search_term}%"
    cursor.execute('''
        SELECT u.id, u.username, u.full_name, u.email, u.status, u.created_at, lf.image_path
        FROM users u
        LEFT JOIN (
            SELECT f.user_id, f.image_path
            FROM face_encodings f
            INNER JOIN (
                SELECT user_id, MAX(id) AS max_id
                FROM face_encodings
                GROUP BY user_id
            ) latest ON latest.max_id = f.id
        ) lf ON lf.user_id = u.id
        WHERE u.role = 'employee' AND (u.username LIKE ? OR u.full_name LIKE ? OR u.email LIKE ?)
        ORDER BY u.created_at DESC
    ''', (search_pattern, search_pattern, search_pattern))
    
    records = cursor.fetchall()
    conn.close()
    return records

def get_dashboard_stats():
    """Get dashboard statistics for admin"""
    conn = sqlite3.connect('attendance.db')
    cursor = conn.cursor()
    
    # Total employees
    cursor.execute('SELECT COUNT(*) FROM users WHERE role = "employee"')
    total_employees = cursor.fetchone()[0]
    
    # Pending approvals
    cursor.execute('SELECT COUNT(*) FROM users WHERE role = "employee" AND status = "pending"')
    pending_count = cursor.fetchone()[0]
    
    # Approved employees
    cursor.execute('SELECT COUNT(*) FROM users WHERE role = "employee" AND status = "approved"')
    approved_count = cursor.fetchone()[0]
    
    # Today's attendance
    cursor.execute('''
        SELECT COUNT(DISTINCT user_id) FROM attendance
        WHERE DATE(timestamp, 'localtime') = DATE('now', 'localtime') AND user_id IN (
            SELECT id FROM users WHERE role = 'employee' AND status = 'approved'
        )
    ''')
    today_attendance = cursor.fetchone()[0]
    
    conn.close()
    
    return {
        'total_employees': total_employees,
        'pending_count': pending_count,
        'approved_count': approved_count,
        'today_attendance': today_attendance
    }

def get_recent_attendance_details(limit=50):
    """Get recent attendance records joined with employee details"""
    conn = sqlite3.connect('attendance.db')
    cursor = conn.cursor()

    cursor.execute('''
        SELECT a.id, u.id, u.full_name, u.username, u.email, datetime(a.timestamp, 'localtime'), a.status, a.confidence, lf.image_path
        FROM attendance a
        JOIN users u ON a.user_id = u.id
        LEFT JOIN (
            SELECT f.user_id, f.image_path
            FROM face_encodings f
            INNER JOIN (
                SELECT user_id, MAX(id) AS max_id
                FROM face_encodings
                GROUP BY user_id
            ) latest ON latest.max_id = f.id
        ) lf ON lf.user_id = u.id
        WHERE u.role = 'employee'
        ORDER BY a.timestamp DESC
        LIMIT ?
    ''', (limit,))

    records = cursor.fetchall()
    conn.close()
    return records

def delete_employee(user_id):
    """Delete an employee and related attendance and face encoding records"""
    conn = sqlite3.connect('attendance.db')
    cursor = conn.cursor()

    cursor.execute('SELECT role FROM users WHERE id = ?', (user_id,))
    user = cursor.fetchone()
    if not user or user[0] != 'employee':
        conn.close()
        return False, 'Employee not found'

    cursor.execute('SELECT image_path FROM face_encodings WHERE user_id = ?', (user_id,))
    image_paths = [row[0] for row in cursor.fetchall()]

    cursor.execute('DELETE FROM attendance WHERE user_id = ?', (user_id,))
    cursor.execute('DELETE FROM face_encodings WHERE user_id = ?', (user_id,))
    cursor.execute('DELETE FROM users WHERE id = ? AND role = ?', (user_id, 'employee'))
    conn.commit()
    conn.close()

    for image_path in image_paths:
        if image_path and os.path.exists(image_path):
            try:
                os.remove(image_path)
            except OSError:
                pass

    return True, 'Employee deleted successfully'