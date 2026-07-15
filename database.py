import sqlite3
import hashlib
from datetime import datetime, date, timedelta
import os

DEFAULT_SETTINGS = {
    'reporting_time': '09:15',
    'low_attendance_threshold': 75,
    'working_days_per_month': 22,
}

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, 'attendance.db')

def get_connection():
    """Create a SQLite connection with row access enabled where needed."""
    return sqlite3.connect(DB_PATH)

def column_exists(cursor, table_name, column_name):
    cursor.execute(f"PRAGMA table_info({table_name})")
    return any(row[1] == column_name for row in cursor.fetchall())

def ensure_column(cursor, table_name, column_name, column_definition):
    if not column_exists(cursor, table_name, column_name):
        cursor.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_definition}")

def init_db():
    """Initialize the database with required tables"""
    conn = get_connection()
    cursor = conn.cursor()
    
    # Users table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            full_name TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            role TEXT DEFAULT 'student',
            status TEXT DEFAULT 'pending',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    legacy_role = 'em' + 'ployee'
    cursor.execute('UPDATE users SET role = ? WHERE role = ?', ('student', legacy_role))
    
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

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS face_approval_requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            encoding BLOB NOT NULL,
            image_path TEXT NOT NULL,
            request_type TEXT NOT NULL,
            status TEXT DEFAULT 'pending',
            requested_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            reviewed_at TIMESTAMP,
            reviewed_by INTEGER,
            FOREIGN KEY (user_id) REFERENCES users (id),
            FOREIGN KEY (reviewed_by) REFERENCES users (id)
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

    ensure_column(cursor, 'attendance', 'attendance_date', 'TEXT')
    ensure_column(cursor, 'attendance', 'check_in_time', 'TIMESTAMP')
    ensure_column(cursor, 'attendance', 'check_out_time', 'TIMESTAMP')
    ensure_column(cursor, 'attendance', 'check_in_confidence', 'REAL')
    ensure_column(cursor, 'attendance', 'check_out_confidence', 'REAL')
    ensure_column(cursor, 'attendance', 'remarks', 'TEXT')
    ensure_column(cursor, 'attendance', 'subject', "TEXT DEFAULT 'General'")

    cursor.execute('''
        UPDATE attendance
        SET attendance_date = DATE(timestamp, 'localtime')
        WHERE attendance_date IS NULL
    ''')
    cursor.execute('''
        UPDATE attendance
        SET check_in_time = timestamp
        WHERE check_in_time IS NULL
    ''')
    cursor.execute('''
        UPDATE attendance
        SET check_in_confidence = confidence
        WHERE check_in_confidence IS NULL
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS attendance_settings (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            reporting_time TEXT NOT NULL DEFAULT '09:15',
            low_attendance_threshold INTEGER NOT NULL DEFAULT 75,
            working_days_per_month INTEGER NOT NULL DEFAULT 22,
            college_lat REAL DEFAULT 0.0,
            college_lon REAL DEFAULT 0.0,
            geofencing_radius REAL DEFAULT 150.0,
            geofencing_enabled INTEGER DEFAULT 0,
            smtp_host TEXT DEFAULT 'smtp.gmail.com',
            smtp_port INTEGER DEFAULT 587,
            smtp_user TEXT DEFAULT '',
            smtp_password TEXT DEFAULT '',
            smtp_sender TEXT DEFAULT '',
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # Add settings columns to existing attendance_settings if they aren't present
    ensure_column(cursor, 'attendance_settings', 'college_lat', 'REAL DEFAULT 0.0')
    ensure_column(cursor, 'attendance_settings', 'college_lon', 'REAL DEFAULT 0.0')
    ensure_column(cursor, 'attendance_settings', 'geofencing_radius', 'REAL DEFAULT 150.0')
    ensure_column(cursor, 'attendance_settings', 'geofencing_enabled', 'INTEGER DEFAULT 0')
    ensure_column(cursor, 'attendance_settings', 'smtp_host', "TEXT DEFAULT 'smtp.gmail.com'")
    ensure_column(cursor, 'attendance_settings', 'smtp_port', 'INTEGER DEFAULT 587')
    ensure_column(cursor, 'attendance_settings', 'smtp_user', "TEXT DEFAULT ''")
    ensure_column(cursor, 'attendance_settings', 'smtp_password', "TEXT DEFAULT ''")
    ensure_column(cursor, 'attendance_settings', 'smtp_sender', "TEXT DEFAULT ''")

    cursor.execute('SELECT COUNT(*) FROM attendance_settings WHERE id = 1')
    if cursor.fetchone()[0] == 0:
        cursor.execute('''
            INSERT INTO attendance_settings (id, reporting_time, low_attendance_threshold, working_days_per_month)
            VALUES (1, ?, ?, ?)
        ''', (
            DEFAULT_SETTINGS['reporting_time'],
            DEFAULT_SETTINGS['low_attendance_threshold'],
            DEFAULT_SETTINGS['working_days_per_month'],
        ))

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS parent_students (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            parent_id INTEGER NOT NULL,
            student_id INTEGER NOT NULL,
            relationship TEXT DEFAULT 'Parent',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(parent_id, student_id),
            FOREIGN KEY (parent_id) REFERENCES users (id),
            FOREIGN KEY (student_id) REFERENCES users (id)
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

    cursor.execute('SELECT COUNT(*) FROM users WHERE role = ?', ('parent',))
    if cursor.fetchone()[0] == 0:
        parent_password_hash = hash_password('parent123')
        cursor.execute('''
            INSERT INTO users (username, password_hash, full_name, email, role, status)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', ('parent', parent_password_hash, 'Demo Parent', 'parent@attendance.system', 'parent', 'approved'))
        conn.commit()

    # Create attendance_sessions table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS attendance_sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            lecturer_id INTEGER NOT NULL,
            subject TEXT NOT NULL,
            status TEXT DEFAULT 'open',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            closed_at TIMESTAMP,
            FOREIGN KEY (lecturer_id) REFERENCES users (id)
        )
    ''')

    # Seed 4 lecturer accounts if not exists
    for i in range(1, 5):
        username = f"lecturer{i}"
        cursor.execute('SELECT COUNT(*) FROM users WHERE username = ?', (username,))
        if cursor.fetchone()[0] == 0:
            pw_hash = hash_password('lecturer123')
            cursor.execute('''
                INSERT INTO users (username, password_hash, full_name, email, role, status)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (username, pw_hash, f"Lecturer {chr(64 + i)}", f"lecturer{i}@attendance.system", 'lecturer', 'approved'))
            conn.commit()
    
    conn.close()

def hash_password(password):
    """Hash password using SHA-256"""
    return hashlib.sha256(password.encode()).hexdigest()

def verify_user(username, password):
    """Verify user credentials"""
    conn = get_connection()
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
    """Create a new student user with pending approval status."""
    conn = get_connection()
    cursor = conn.cursor()
    
    password_hash = hash_password(password)
    
    try:
        cursor.execute('''
            INSERT INTO users (username, password_hash, full_name, email, role, status)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (username, password_hash, full_name, email, 'student', 'pending'))
        
        user_id = cursor.lastrowid
        conn.commit()
        conn.close()
        return user_id
    except sqlite3.IntegrityError:
        conn.close()
        return None

def create_parent_user(username, password, full_name, email):
    """Create an approved parent account."""
    conn = get_connection()
    cursor = conn.cursor()
    password_hash = hash_password(password)

    try:
        cursor.execute('''
            INSERT INTO users (username, password_hash, full_name, email, role, status)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (username, password_hash, full_name, email, 'parent', 'approved'))
        parent_id = cursor.lastrowid
        conn.commit()
        conn.close()
        return parent_id
    except sqlite3.IntegrityError:
        conn.close()
        return None

def update_parent_user(parent_id, username, full_name, email, password=None):
    """Update parent account details, optionally changing the password."""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute('SELECT role FROM users WHERE id = ?', (parent_id,))
    parent = cursor.fetchone()
    if not parent or parent[0] != 'parent':
        conn.close()
        return False, 'Parent account not found'

    try:
        if password:
            cursor.execute('''
                UPDATE users
                SET username = ?, full_name = ?, email = ?, password_hash = ?
                WHERE id = ? AND role = 'parent'
            ''', (username, full_name, email, hash_password(password), parent_id))
        else:
            cursor.execute('''
                UPDATE users
                SET username = ?, full_name = ?, email = ?
                WHERE id = ? AND role = 'parent'
            ''', (username, full_name, email, parent_id))
        conn.commit()
        conn.close()
        return True, 'Parent account updated successfully'
    except sqlite3.IntegrityError:
        conn.close()
        return False, 'Username or email already exists'

def delete_parent_user(parent_id):
    """Delete a parent account and its student links."""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute('SELECT role FROM users WHERE id = ?', (parent_id,))
    parent = cursor.fetchone()
    if not parent or parent[0] != 'parent':
        conn.close()
        return False, 'Parent account not found'

    cursor.execute('DELETE FROM parent_students WHERE parent_id = ?', (parent_id,))
    cursor.execute('DELETE FROM users WHERE id = ? AND role = ?', (parent_id, 'parent'))
    conn.commit()
    conn.close()
    return True, 'Parent account deleted successfully'

def link_parent_to_student(parent_id, student_id, relationship='Parent'):
    """Link one parent account to one approved student."""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute('SELECT role, status FROM users WHERE id = ?', (parent_id,))
    parent = cursor.fetchone()
    cursor.execute('SELECT role, status FROM users WHERE id = ?', (student_id,))
    student = cursor.fetchone()

    if not parent or parent[0] != 'parent':
        conn.close()
        return False, 'Parent account not found'
    if not student or student[0] != 'student' or student[1] != 'approved':
        conn.close()
        return False, 'Approved student not found'

    try:
        cursor.execute('''
            INSERT INTO parent_students (parent_id, student_id, relationship)
            VALUES (?, ?, ?)
        ''', (parent_id, student_id, relationship or 'Parent'))
        conn.commit()
        conn.close()
        return True, 'Parent linked to student successfully'
    except sqlite3.IntegrityError:
        conn.close()
        return False, 'This parent is already linked to that student'

def update_parent_student_link(link_id, relationship):
    """Update the relationship label for a parent-student link."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('''
        UPDATE parent_students
        SET relationship = ?
        WHERE id = ?
    ''', (relationship or 'Parent', link_id))
    changed = cursor.rowcount
    conn.commit()
    conn.close()
    return (True, 'Relationship updated successfully') if changed else (False, 'Parent-student link not found')

def unlink_parent_student(link_id):
    """Remove a student from a parent account."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('DELETE FROM parent_students WHERE id = ?', (link_id,))
    changed = cursor.rowcount
    conn.commit()
    conn.close()
    return (True, 'Student unlinked successfully') if changed else (False, 'Parent-student link not found')

def get_parent_accounts():
    """Return parent accounts with linked student counts."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT u.id, u.username, u.full_name, u.email, u.created_at,
               COUNT(ps.student_id) AS student_count
        FROM users u
        LEFT JOIN parent_students ps ON ps.parent_id = u.id
        WHERE u.role = 'parent'
        GROUP BY u.id
        ORDER BY u.created_at DESC
    ''')
    records = cursor.fetchall()
    conn.close()
    return records

def get_parent_links():
    """Return parent-student links for admin management."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT ps.id, ps.parent_id, p.full_name, p.username,
               ps.student_id, s.full_name, s.username,
               ps.relationship, ps.created_at
        FROM parent_students ps
        JOIN users p ON p.id = ps.parent_id
        JOIN users s ON s.id = ps.student_id
        WHERE p.role = 'parent' AND s.role = 'student'
        ORDER BY p.full_name, s.full_name
    ''')
    records = cursor.fetchall()
    conn.close()
    return records

def get_parent_students(parent_id):
    """Return students linked to one parent account."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT u.id, u.username, u.full_name, u.email, u.status, ps.relationship,
               lf.image_path
        FROM parent_students ps
        JOIN users u ON u.id = ps.student_id
        LEFT JOIN (
            SELECT f.user_id, f.image_path
            FROM face_encodings f
            INNER JOIN (
                SELECT user_id, MAX(id) AS max_id
                FROM face_encodings
                GROUP BY user_id
            ) latest ON latest.max_id = f.id
        ) lf ON lf.user_id = u.id
        WHERE ps.parent_id = ? AND u.role = 'student'
        ORDER BY u.full_name
    ''', (parent_id,))
    rows = cursor.fetchall()
    conn.close()

    students = []
    for row in rows:
        summary = get_user_attendance_summary(row[0])
        today_record = get_today_user_attendance(row[0])
        students.append({
            'id': row[0],
            'username': row[1],
            'full_name': row[2],
            'email': row[3],
            'status': row[4],
            'relationship': row[5],
            'face_image_path': row[6],
            'summary': summary,
            'today_record': today_record,
        })
    return students

def parent_can_access_student(parent_id, student_id):
    """Check whether a parent is linked to a student."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT COUNT(*)
        FROM parent_students ps
        JOIN users s ON s.id = ps.student_id
        WHERE ps.parent_id = ? AND ps.student_id = ? AND s.role = 'student'
    ''', (parent_id, student_id))
    can_access = cursor.fetchone()[0] > 0
    conn.close()
    return can_access

def get_attendance_settings():
    """Get attendance policy settings."""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute('''
        SELECT reporting_time, low_attendance_threshold, working_days_per_month,
               college_lat, college_lon, geofencing_radius, geofencing_enabled,
               smtp_host, smtp_port, smtp_user, smtp_password, smtp_sender
        FROM attendance_settings
        WHERE id = 1
    ''')
    row = cursor.fetchone()
    conn.close()

    if not row:
        return {
            'reporting_time': '09:15',
            'low_attendance_threshold': 75,
            'working_days_per_month': 22,
            'college_lat': 0.0,
            'college_lon': 0.0,
            'geofencing_radius': 150.0,
            'geofencing_enabled': 0,
            'smtp_host': 'smtp.gmail.com',
            'smtp_port': 587,
            'smtp_user': '',
            'smtp_password': '',
            'smtp_sender': ''
        }

    return {
        'reporting_time': row[0],
        'low_attendance_threshold': row[1],
        'working_days_per_month': row[2],
        'college_lat': row[3] if len(row) > 3 and row[3] is not None else 0.0,
        'college_lon': row[4] if len(row) > 4 and row[4] is not None else 0.0,
        'geofencing_radius': row[5] if len(row) > 5 and row[5] is not None else 150.0,
        'geofencing_enabled': row[6] if len(row) > 6 and row[6] is not None else 0,
        'smtp_host': row[7] if len(row) > 7 and row[7] is not None else 'smtp.gmail.com',
        'smtp_port': row[8] if len(row) > 8 and row[8] is not None else 587,
        'smtp_user': row[9] if len(row) > 9 and row[9] is not None else '',
        'smtp_password': row[10] if len(row) > 10 and row[10] is not None else '',
        'smtp_sender': row[11] if len(row) > 11 and row[11] is not None else '',
    }

def update_attendance_settings(reporting_time, low_attendance_threshold, working_days_per_month,
                               college_lat=None, college_lon=None, geofencing_radius=None, geofencing_enabled=None,
                               smtp_host=None, smtp_port=None, smtp_user=None, smtp_password=None, smtp_sender=None):
    """Update the single attendance policy settings row."""
    conn = get_connection()
    cursor = conn.cursor()
    
    # Retrieve current settings to fallback
    current = get_attendance_settings()
    
    c_lat = college_lat if college_lat is not None else current['college_lat']
    c_lon = college_lon if college_lon is not None else current['college_lon']
    g_rad = geofencing_radius if geofencing_radius is not None else current['geofencing_radius']
    g_enb = geofencing_enabled if geofencing_enabled is not None else current['geofencing_enabled']
    s_host = smtp_host if smtp_host is not None else current['smtp_host']
    s_port = smtp_port if smtp_port is not None else current['smtp_port']
    s_user = smtp_user if smtp_user is not None else current['smtp_user']
    s_pass = smtp_password if smtp_password is not None else current['smtp_password']
    s_send = smtp_sender if smtp_sender is not None else current['smtp_sender']

    cursor.execute('''
        UPDATE attendance_settings
        SET reporting_time = ?,
            low_attendance_threshold = ?,
            working_days_per_month = ?,
            college_lat = ?,
            college_lon = ?,
            geofencing_radius = ?,
            geofencing_enabled = ?,
            smtp_host = ?,
            smtp_port = ?,
            smtp_user = ?,
            smtp_password = ?,
            smtp_sender = ?,
            updated_at = CURRENT_TIMESTAMP
        WHERE id = 1
    ''', (reporting_time, low_attendance_threshold, working_days_per_month,
          c_lat, c_lon, g_rad, g_enb, s_host, s_port, s_user, s_pass, s_send))
    conn.commit()
    conn.close()

def classify_attendance(now=None):
    """Classify check-in as on-time or late using configured reporting time."""
    now = now or datetime.now()
    settings = get_attendance_settings()
    reporting_hour, reporting_minute = [int(part) for part in settings['reporting_time'].split(':')]
    reporting_time = now.replace(hour=reporting_hour, minute=reporting_minute, second=0, microsecond=0)
    return 'on_time' if now <= reporting_time else 'late'

def get_today_user_attendance(user_id, subject=None):
    """Get today's attendance lifecycle row for a user."""
    conn = get_connection()
    cursor = conn.cursor()
    if subject:
        cursor.execute('''
            SELECT id, attendance_date, datetime(check_in_time, 'localtime'), datetime(check_out_time, 'localtime'),
                   status, check_in_confidence, check_out_confidence, subject
            FROM attendance
            WHERE user_id = ? AND attendance_date = DATE('now', 'localtime') AND subject = ?
            ORDER BY id DESC
            LIMIT 1
        ''', (user_id, subject))
    else:
        cursor.execute('''
            SELECT id, attendance_date, datetime(check_in_time, 'localtime'), datetime(check_out_time, 'localtime'),
                   status, check_in_confidence, check_out_confidence, subject
            FROM attendance
            WHERE user_id = ? AND attendance_date = DATE('now', 'localtime')
            ORDER BY id DESC
            LIMIT 1
        ''', (user_id,))
    row = cursor.fetchone()
    conn.close()

    if not row:
        return None

    return {
        'id': row[0],
        'attendance_date': row[1],
        'check_in_time': row[2],
        'check_out_time': row[3],
        'status': row[4],
        'check_in_confidence': row[5],
        'check_out_confidence': row[6],
        'subject': row[7] if len(row) > 7 else 'General',
    }

def save_attendance(user_id, confidence, subject="General"):
    """Save a policy-aware check-in or check-out attendance record."""
    conn = get_connection()
    cursor = conn.cursor()
    local_now = datetime.now()
    utc_now = datetime.utcnow()
    now_text = utc_now.strftime('%Y-%m-%d %H:%M:%S')
    today_text = local_now.strftime('%Y-%m-%d')

    cursor.execute('''
        SELECT id, check_out_time, status
        FROM attendance
        WHERE user_id = ? AND attendance_date = ? AND subject = ?
        ORDER BY id DESC
        LIMIT 1
    ''', (user_id, today_text, subject))
    existing = cursor.fetchone()

    if existing and existing[1]:
        conn.close()
        return {
            'success': False,
            'action': 'complete',
            'message': f'Attendance already completed for today for subject {subject}. Check-in and check-out are both recorded.'
        }

    if existing:
        cursor.execute('''
            UPDATE attendance
            SET check_out_time = ?, check_out_confidence = ?, timestamp = ?, remarks = ?
            WHERE id = ?
        ''', (now_text, confidence, now_text, 'Checked out successfully', existing[0]))
        conn.commit()
        conn.close()
        return {
            'success': True,
            'action': 'check_out',
            'status': existing[2],
            'message': f'Check-out recorded successfully for {subject}. Confidence: {confidence:.2f}'
        }

    status = classify_attendance(local_now)
    cursor.execute('''
        INSERT INTO attendance (
            user_id, timestamp, attendance_date, check_in_time, status,
            confidence, check_in_confidence, remarks, subject
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        user_id, now_text, today_text, now_text, status, confidence, confidence,
        'Checked in successfully', subject
    ))

    conn.commit()
    conn.close()
    status_label = 'On time' if status == 'on_time' else 'Late'
    return {
        'success': True,
        'action': 'check_in',
        'status': status,
        'message': f'Check-in recorded successfully for {subject} as {status_label}. Confidence: {confidence:.2f}'
    }

def get_user_attendance(user_id, date=None):
    """Get attendance records for a user"""
    conn = get_connection()
    cursor = conn.cursor()
    
    if date:
        cursor.execute('''
            SELECT attendance_date,
                   datetime(check_in_time, 'localtime'),
                   datetime(check_out_time, 'localtime'),
                   status,
                   check_in_confidence,
                   check_out_confidence,
                   subject
            FROM attendance
            WHERE user_id = ? AND attendance_date = ?
            ORDER BY attendance_date DESC, check_in_time DESC
        ''', (user_id, date))
    else:
        cursor.execute('''
            SELECT attendance_date,
                   datetime(check_in_time, 'localtime'),
                   datetime(check_out_time, 'localtime'),
                   status,
                   check_in_confidence,
                   check_out_confidence,
                   subject
            FROM attendance
            WHERE user_id = ?
            ORDER BY attendance_date DESC, check_in_time DESC
        ''', (user_id,))
    
    records = cursor.fetchall()
    conn.close()
    return records

def get_today_attendance():
    """Get today's attendance for all users"""
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT u.full_name,
               datetime(a.check_in_time, 'localtime'),
               datetime(a.check_out_time, 'localtime'),
               a.status,
               a.check_in_confidence,
               a.subject
        FROM attendance a
        JOIN users u ON a.user_id = u.id
        WHERE a.attendance_date = DATE('now', 'localtime')
        ORDER BY a.check_in_time DESC
    ''', )
    
    records = cursor.fetchall()
    conn.close()
    return records

def get_pending_students():
    """Get all pending students waiting for approval."""
    conn = get_connection()
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
        WHERE u.role = 'student' AND u.status = 'pending'
        ORDER BY created_at DESC
    ''')
    
    records = cursor.fetchall()
    conn.close()
    return records

def get_approved_students():
    """Get all approved students."""
    conn = get_connection()
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
        WHERE u.role = 'student' AND u.status = 'approved'
        ORDER BY created_at DESC
    ''')
    
    records = cursor.fetchall()
    conn.close()
    return records

def get_rejected_students():
    """Get all rejected students."""
    conn = get_connection()
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
        WHERE u.role = 'student' AND u.status = 'rejected'
        ORDER BY created_at DESC
    ''')
    
    records = cursor.fetchall()
    conn.close()
    return records

def approve_student(user_id):
    """Approve a pending student."""
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        UPDATE users SET status = 'approved'
        WHERE id = ? AND role = 'student'
    ''', (user_id,))
    
    conn.commit()
    conn.close()
    return True

def reject_student(user_id):
    """Reject a pending student."""
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        UPDATE users SET status = 'rejected'
        WHERE id = ? AND role = 'student'
    ''', (user_id,))
    
    conn.commit()
    conn.close()
    return True

def get_pending_face_requests():
    """Get face registration/update requests waiting for admin approval."""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute('''
        SELECT fr.id, fr.user_id, u.full_name, u.username, u.email,
               fr.image_path, fr.request_type, fr.requested_at
        FROM face_approval_requests fr
        JOIN users u ON fr.user_id = u.id
        WHERE fr.status = 'pending'
        ORDER BY fr.requested_at ASC
    ''')

    records = cursor.fetchall()
    conn.close()
    return records

def get_pending_face_request_for_user(user_id):
    """Return the newest pending face request for one student."""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute('''
        SELECT id, request_type, image_path, requested_at
        FROM face_approval_requests
        WHERE user_id = ? AND status = 'pending'
        ORDER BY requested_at DESC, id DESC
        LIMIT 1
    ''', (user_id,))

    row = cursor.fetchone()
    conn.close()
    if not row:
        return None
    return {
        'id': row[0],
        'request_type': row[1],
        'image_path': row[2],
        'requested_at': row[3],
    }

def count_pending_face_requests():
    """Count pending face approval requests."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM face_approval_requests WHERE status = 'pending'")
    count = cursor.fetchone()[0]
    conn.close()
    return count

def approve_face_request(request_id, admin_user_id):
    """Approve a pending face request and make it the student's active face."""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute('''
        SELECT user_id, encoding, image_path
        FROM face_approval_requests
        WHERE id = ? AND status = 'pending'
    ''', (request_id,))
    request_row = cursor.fetchone()

    if not request_row:
        conn.close()
        return False, 'Face request not found'

    user_id, encoding, image_path = request_row
    cursor.execute('SELECT image_path FROM face_encodings WHERE user_id = ?', (user_id,))
    old_active_paths = [row[0] for row in cursor.fetchall()]

    cursor.execute('DELETE FROM face_encodings WHERE user_id = ?', (user_id,))
    cursor.execute('''
        INSERT INTO face_encodings (user_id, encoding, image_path)
        VALUES (?, ?, ?)
    ''', (user_id, encoding, image_path))
    cursor.execute('''
        UPDATE face_approval_requests
        SET status = 'approved', reviewed_at = CURRENT_TIMESTAMP, reviewed_by = ?
        WHERE id = ?
    ''', (admin_user_id, request_id))
    cursor.execute('''
        UPDATE face_approval_requests
        SET status = 'superseded', reviewed_at = CURRENT_TIMESTAMP, reviewed_by = ?
        WHERE user_id = ? AND status = 'pending' AND id != ?
    ''', (admin_user_id, user_id, request_id))

    conn.commit()
    conn.close()

    for old_path in old_active_paths:
        if old_path and old_path != image_path and os.path.exists(old_path):
            try:
                os.remove(old_path)
            except OSError:
                pass

    return True, 'Face request approved successfully'

def reject_face_request(request_id, admin_user_id):
    """Reject a pending face request without changing the active face."""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute('''
        SELECT image_path
        FROM face_approval_requests
        WHERE id = ? AND status = 'pending'
    ''', (request_id,))
    row = cursor.fetchone()

    if not row:
        conn.close()
        return False, 'Face request not found'

    image_path = row[0]
    cursor.execute('''
        UPDATE face_approval_requests
        SET status = 'rejected', reviewed_at = CURRENT_TIMESTAMP, reviewed_by = ?
        WHERE id = ?
    ''', (admin_user_id, request_id))

    conn.commit()
    conn.close()

    if image_path and os.path.exists(image_path):
        try:
            os.remove(image_path)
        except OSError:
            pass

    return True, 'Face request rejected'

def get_student_by_id(user_id):
    """Get student details by ID."""
    conn = get_connection()
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
    conn = get_connection()
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

def search_students(search_term):
    """Search students by username, full_name, or email."""
    conn = get_connection()
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
        WHERE u.role = 'student' AND (u.username LIKE ? OR u.full_name LIKE ? OR u.email LIKE ?)
        ORDER BY u.created_at DESC
    ''', (search_pattern, search_pattern, search_pattern))
    
    records = cursor.fetchall()
    conn.close()
    return records

def get_dashboard_stats():
    """Get dashboard statistics for admin"""
    conn = get_connection()
    cursor = conn.cursor()
    
    # Total students
    cursor.execute('SELECT COUNT(*) FROM users WHERE role = "student"')
    total_students = cursor.fetchone()[0]
    
    # Pending approvals
    cursor.execute('SELECT COUNT(*) FROM users WHERE role = "student" AND status = "pending"')
    pending_count = cursor.fetchone()[0]
    
    # Approved students
    cursor.execute('SELECT COUNT(*) FROM users WHERE role = "student" AND status = "approved"')
    approved_count = cursor.fetchone()[0]
    
    # Today's attendance
    cursor.execute('''
        SELECT COUNT(DISTINCT user_id) FROM attendance
        WHERE attendance_date = DATE('now', 'localtime') AND user_id IN (
            SELECT id FROM users WHERE role = 'student' AND status = 'approved'
        )
    ''')
    today_attendance = cursor.fetchone()[0]

    cursor.execute('''
        SELECT COUNT(*) FROM attendance
        WHERE attendance_date = DATE('now', 'localtime') AND status = 'late'
    ''')
    late_today = cursor.fetchone()[0]

    cursor.execute('''
        SELECT COUNT(*) FROM attendance
        WHERE attendance_date = DATE('now', 'localtime') AND check_out_time IS NOT NULL
    ''')
    checked_out_today = cursor.fetchone()[0]
    
    conn.close()
    
    return {
        'total_students': total_students,
        'pending_count': pending_count,
        'approved_count': approved_count,
        'today_attendance': today_attendance,
        'late_today': late_today,
        'checked_out_today': checked_out_today
    }

def get_recent_attendance_details(limit=50):
    """Get recent attendance records joined with student details."""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute('''
        SELECT a.id, u.id, u.full_name, u.username, u.email,
               a.attendance_date,
               datetime(a.check_in_time, 'localtime'),
               datetime(a.check_out_time, 'localtime'),
               a.status,
               a.check_in_confidence,
               a.check_out_confidence,
               lf.image_path,
               a.subject
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
        WHERE u.role = 'student'
        ORDER BY a.attendance_date DESC, a.check_in_time DESC
        LIMIT ?
    ''', (limit,))

    records = cursor.fetchall()
    conn.close()
    return records

def get_user_attendance_summary(user_id, month=None):
    """Return monthly attendance policy summary for one user."""
    month = month or date.today().strftime('%Y-%m')
    settings = get_attendance_settings()
    import calendar
    try:
        y, m = [int(p) for p in month.split('-')]
        working_days = calendar.monthrange(y, m)[1]
    except Exception:
        working_days = settings['working_days_per_month']

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT
            COUNT(DISTINCT attendance_date),
            SUM(CASE WHEN status = 'late' THEN 1 ELSE 0 END),
            SUM(CASE WHEN check_out_time IS NOT NULL THEN 1 ELSE 0 END)
        FROM attendance
        WHERE user_id = ? AND substr(attendance_date, 1, 7) = ?
    ''', (user_id, month))
    row = cursor.fetchone()
    conn.close()

    present_days = row[0] or 0
    late_days = row[1] or 0
    completed_days = row[2] or 0
    percentage = round((present_days / working_days) * 100, 1) if working_days else 0

    return {
        'month': month,
        'working_days': working_days,
        'present_days': present_days,
        'late_days': late_days,
        'completed_days': completed_days,
        'absent_days': max(0, working_days - present_days),
        'percentage': percentage,
        'threshold': settings['low_attendance_threshold'],
        'is_low': percentage < settings['low_attendance_threshold'],
    }

def get_monthly_attendance_report(month=None):
    """Return per-student monthly attendance report rows."""
    month = month or date.today().strftime('%Y-%m')
    settings = get_attendance_settings()
    import calendar
    try:
        y, m = [int(p) for p in month.split('-')]
        working_days = calendar.monthrange(y, m)[1]
    except Exception:
        working_days = settings['working_days_per_month']

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT
            u.id,
            u.full_name,
            u.username,
            u.email,
            COUNT(DISTINCT a.attendance_date) AS present_days,
            SUM(CASE WHEN a.status = 'late' THEN 1 ELSE 0 END) AS late_days,
            SUM(CASE WHEN a.check_out_time IS NOT NULL THEN 1 ELSE 0 END) AS completed_days,
            lf.image_path
        FROM users u
        LEFT JOIN attendance a
            ON a.user_id = u.id AND substr(a.attendance_date, 1, 7) = ?
        LEFT JOIN (
            SELECT f.user_id, f.image_path
            FROM face_encodings f
            INNER JOIN (
                SELECT user_id, MAX(id) AS max_id
                FROM face_encodings
                GROUP BY user_id
            ) latest ON latest.max_id = f.id
        ) lf ON lf.user_id = u.id
        WHERE u.role = 'student' AND u.status = 'approved'
        GROUP BY u.id
        ORDER BY u.full_name
    ''', (month,))
    rows = cursor.fetchall()
    conn.close()

    report = []
    for row in rows:
        present_days = row[4] or 0
        late_days = row[5] or 0
        completed_days = row[6] or 0
        percentage = round((present_days / working_days) * 100, 1) if working_days else 0
        report.append({
            'id': row[0],
            'full_name': row[1],
            'username': row[2],
            'email': row[3],
            'present_days': present_days,
            'late_days': late_days,
            'completed_days': completed_days,
            'absent_days': max(0, working_days - present_days),
            'working_days': working_days,
            'percentage': percentage,
            'is_low': percentage < settings['low_attendance_threshold'],
            'face_image_path': row[7],
        })

    return report

def get_low_attendance_students(month=None, limit=10):
    """Return approved students below the attendance threshold."""
    report = get_monthly_attendance_report(month)
    low_rows = [row for row in report if row['is_low']]
    low_rows.sort(key=lambda item: item['percentage'])
    return low_rows[:limit]

def delete_student(user_id):
    """Delete a student and related attendance and face encoding records."""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute('SELECT role FROM users WHERE id = ?', (user_id,))
    user = cursor.fetchone()
    if not user or user[0] != 'student':
        conn.close()
        return False, 'Student not found'

    cursor.execute('SELECT image_path FROM face_encodings WHERE user_id = ?', (user_id,))
    image_paths = [row[0] for row in cursor.fetchall()]
    cursor.execute('SELECT image_path FROM face_approval_requests WHERE user_id = ?', (user_id,))
    image_paths.extend(row[0] for row in cursor.fetchall())

    cursor.execute('DELETE FROM attendance WHERE user_id = ?', (user_id,))
    cursor.execute('DELETE FROM face_encodings WHERE user_id = ?', (user_id,))
    cursor.execute('DELETE FROM face_approval_requests WHERE user_id = ?', (user_id,))
    cursor.execute('DELETE FROM parent_students WHERE student_id = ?', (user_id,))
    cursor.execute('DELETE FROM users WHERE id = ? AND role = ?', (user_id, 'student'))
    conn.commit()
    conn.close()

    for image_path in image_paths:
        if image_path and os.path.exists(image_path):
            try:
                os.remove(image_path)
            except OSError:
                pass

    return True, 'Student deleted successfully'

def create_attendance_session(lecturer_id, subject):
    """Open a new attendance session for a subject."""
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        UPDATE attendance_sessions
        SET status = 'closed', closed_at = CURRENT_TIMESTAMP
        WHERE subject = ? AND status = 'open'
    ''', (subject,))
    
    cursor.execute('''
        INSERT INTO attendance_sessions (lecturer_id, subject, status)
        VALUES (?, ?, 'open')
    ''', (lecturer_id, subject))
    
    session_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return session_id

def close_attendance_session(session_id):
    """Close an active attendance session."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('''
        UPDATE attendance_sessions
        SET status = 'closed', closed_at = CURRENT_TIMESTAMP
        WHERE id = ?
    ''', (session_id,))
    conn.commit()
    conn.close()
    return True

def get_active_session_for_subject(subject):
    """Check if there is an active session for the given subject."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT id, lecturer_id, subject, created_at
        FROM attendance_sessions
        WHERE subject = ? AND status = 'open'
        ORDER BY id DESC
        LIMIT 1
    ''', (subject,))
    row = cursor.fetchone()
    conn.close()
    if row:
        return {
            'id': row[0],
            'lecturer_id': row[1],
            'subject': row[2],
            'created_at': row[3]
        }
    return None

def get_lecturer_sessions(lecturer_id):
    """Get all sessions created by a lecturer."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT id, subject, status, created_at, closed_at
        FROM attendance_sessions
        WHERE lecturer_id = ?
        ORDER BY id DESC
    ''', (lecturer_id,))
    rows = cursor.fetchall()
    conn.close()
    
    sessions = []
    for r in rows:
        sessions.append({
            'id': r[0],
            'subject': r[1],
            'status': r[2],
            'created_at': r[3],
            'closed_at': r[4]
        })
    return sessions

def get_session_attendance_details(session_id):
    """Get list of student attendance marked during a specific session's open duration."""
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT created_at, closed_at, subject
        FROM attendance_sessions
        WHERE id = ?
    ''', (session_id,))
    session_info = cursor.fetchone()
    if not session_info:
        conn.close()
        return []
        
    start_time, end_time, subject = session_info
    
    query = '''
        SELECT u.id, u.full_name, u.username, u.email,
               datetime(a.check_in_time, 'localtime'),
               a.status,
               a.check_in_confidence
        FROM attendance a
        JOIN users u ON a.user_id = u.id
        WHERE a.subject = ? AND a.check_in_time >= ?
    '''
    params = [subject, start_time]
    
    if end_time:
        query += ' AND a.check_in_time <= ?'
        params.append(end_time)
        
    query += ' ORDER BY a.check_in_time DESC'
    
    cursor.execute(query, tuple(params))
    rows = cursor.fetchall()
    conn.close()
    
    attendance = []
    for r in rows:
        attendance.append({
            'student_id': r[0],
            'full_name': r[1],
            'username': r[2],
            'email': r[3],
            'check_in_time': r[4],
            'status': r[5],
            'confidence': r[6]
        })
    return attendance
