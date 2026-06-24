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
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

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

def get_attendance_settings():
    """Get attendance policy settings."""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute('''
        SELECT reporting_time, low_attendance_threshold, working_days_per_month
        FROM attendance_settings
        WHERE id = 1
    ''')
    row = cursor.fetchone()
    conn.close()

    if not row:
        return DEFAULT_SETTINGS.copy()

    return {
        'reporting_time': row[0],
        'low_attendance_threshold': row[1],
        'working_days_per_month': row[2],
    }

def update_attendance_settings(reporting_time, low_attendance_threshold, working_days_per_month):
    """Update the single attendance policy settings row."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('''
        UPDATE attendance_settings
        SET reporting_time = ?,
            low_attendance_threshold = ?,
            working_days_per_month = ?,
            updated_at = CURRENT_TIMESTAMP
        WHERE id = 1
    ''', (reporting_time, low_attendance_threshold, working_days_per_month))
    conn.commit()
    conn.close()

def classify_attendance(now=None):
    """Classify check-in as on-time or late using configured reporting time."""
    now = now or datetime.now()
    settings = get_attendance_settings()
    reporting_hour, reporting_minute = [int(part) for part in settings['reporting_time'].split(':')]
    reporting_time = now.replace(hour=reporting_hour, minute=reporting_minute, second=0, microsecond=0)
    return 'on_time' if now <= reporting_time else 'late'

def get_today_user_attendance(user_id):
    """Get today's attendance lifecycle row for a user."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT id, attendance_date, datetime(check_in_time, 'localtime'), datetime(check_out_time, 'localtime'),
               status, check_in_confidence, check_out_confidence
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
    }

def save_attendance(user_id, confidence):
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
        WHERE user_id = ? AND attendance_date = ?
        ORDER BY id DESC
        LIMIT 1
    ''', (user_id, today_text))
    existing = cursor.fetchone()

    if existing and existing[1]:
        conn.close()
        return {
            'success': False,
            'action': 'complete',
            'message': 'Attendance already completed for today. Check-in and check-out are both recorded.'
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
            'message': f'Check-out recorded successfully. Confidence: {confidence:.2f}'
        }

    status = classify_attendance(local_now)
    cursor.execute('''
        INSERT INTO attendance (
            user_id, timestamp, attendance_date, check_in_time, status,
            confidence, check_in_confidence, remarks
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        user_id, now_text, today_text, now_text, status, confidence, confidence,
        'Checked in successfully'
    ))

    conn.commit()
    conn.close()
    status_label = 'On time' if status == 'on_time' else 'Late'
    return {
        'success': True,
        'action': 'check_in',
        'status': status,
        'message': f'Check-in recorded successfully as {status_label}. Confidence: {confidence:.2f}'
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
                   check_out_confidence
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
                   check_out_confidence
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
               a.check_in_confidence
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
               lf.image_path
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
    absent_days = max(working_days - present_days, 0)
    percentage = round((present_days / working_days) * 100, 1) if working_days else 0

    return {
        'month': month,
        'working_days': working_days,
        'present_days': present_days,
        'late_days': late_days,
        'completed_days': completed_days,
        'absent_days': absent_days,
        'percentage': percentage,
        'threshold': settings['low_attendance_threshold'],
        'is_low': percentage < settings['low_attendance_threshold'],
    }

def get_monthly_attendance_report(month=None):
    """Return per-student monthly attendance report rows."""
    month = month or date.today().strftime('%Y-%m')
    settings = get_attendance_settings()
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
            'absent_days': max(working_days - present_days, 0),
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

    cursor.execute('DELETE FROM attendance WHERE user_id = ?', (user_id,))
    cursor.execute('DELETE FROM face_encodings WHERE user_id = ?', (user_id,))
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
