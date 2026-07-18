from flask import Flask, render_template, request, redirect, url_for, session, jsonify, Response
from dotenv import load_dotenv
load_dotenv()
import cv2
import numpy as np
import os
import threading
from werkzeug.utils import secure_filename
import csv
import io
from datetime import datetime, date
from functools import wraps

from database import (init_db, verify_user, create_user, save_attendance, get_user_attendance,
                     get_today_attendance, get_pending_students, get_approved_students,
                     get_rejected_students, approve_student, reject_student,
                     get_student_by_id, search_students, get_dashboard_stats,
                     get_recent_attendance_details, delete_student, get_user_face_image_path,
                     get_today_user_attendance, get_attendance_settings,
                     get_user_attendance_summary, get_monthly_attendance_report,
                     get_low_attendance_students, update_attendance_settings,
                     get_pending_face_requests, get_pending_face_request_for_user,
                     count_pending_face_requests, approve_face_request, reject_face_request,
                     create_parent_user, link_parent_to_student, get_parent_accounts,
                     get_parent_students, parent_can_access_student, get_parent_links,
                     update_parent_user, delete_parent_user, update_parent_student_link,
                     unlink_parent_student, create_attendance_session, close_attendance_session,
                     get_active_session_for_subject, get_lecturer_sessions, get_session_attendance_details, get_connection, get_current_month_working_days,
                     get_lecturers, create_lecturer_user, update_lecturer_user, delete_lecturer_user,
                     get_subjects, create_subject, update_subject, delete_subject)
from face_utils import (submit_face_approval_request, recognize_faces_in_frame,
                        has_face_registered, allowed_file, clear_face_encoding_cache,
                        calculate_ear, calculate_distance, recognize_multiple_faces)

app = Flask(__name__)
app.secret_key = os.environ.get('FLASK_SECRET_KEY', 'your-secret-key-change-this')
camera = None

@app.before_request
def force_https():
    # If the request comes from a reverse proxy like Railway/Render and is HTTP, redirect to HTTPS
    if not request.is_secure and request.headers.get('X-Forwarded-Proto', 'http') == 'http':
        url = request.url.replace('http://', 'https://', 1)
        return redirect(url, code=301)


# ─── Jinja2 type-safe date/time filters ───────────────────────────────────────
def fmt_date(value, fmt='%Y-%m-%d'):
    """Format a date/datetime value safely for both SQLite strings and PG objects."""
    if value is None:
        return ''
    if isinstance(value, str):
        return value[:10]
    return value.strftime(fmt)

def fmt_time(value, fmt='%H:%M:%S'):
    """Format a time/datetime value safely for both SQLite strings and PG objects."""
    if value is None:
        return ''
    if isinstance(value, str):
        return value[11:19]
    return value.strftime(fmt)

app.jinja_env.filters['fmt_date'] = fmt_date
app.jinja_env.filters['fmt_time'] = fmt_time
# ──────────────────────────────────────────────────────────────────────────────


# Configuration
UPLOAD_FOLDER = 'static/uploads'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# Ensure upload directory exists
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# Initialize database
init_db()

@app.route('/favicon.ico')
def favicon():
    return redirect(url_for('static', filename='favicon.svg'))

# Camera lock globals removed since capture occurs client-side
liveness_tracker = {}


def build_face_image_url(image_path):
    """Convert stored image path or URL to a browser-safe URL."""
    if not image_path:
        return None
    from storage_utils import get_face_image_url
    return get_face_image_url(image_path)

def append_face_image_urls(records, image_index):
    """Append face image URL as an extra field to tuple records."""
    output = []
    for record in records:
        face_image_path = record[image_index] if len(record) > image_index else None
        output.append(tuple(list(record) + [build_face_image_url(face_image_path)]))
    return output



# Role-based access control decorators
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session or session.get('role') != 'admin':
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def student_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session or session.get('role') != 'student':
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def parent_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session or session.get('role') != 'parent':
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def lecturer_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session or session.get('role') != 'lecturer':
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

@app.route('/')
def index():
    return render_template('landing.html')

@app.route('/portal')
def portal():
    if 'user_id' in session:
        if session.get('role') == 'admin':
            return redirect(url_for('admin_dashboard'))
        if session.get('role') == 'parent':
            return redirect(url_for('parent_dashboard'))
        if session.get('role') == 'lecturer':
            return redirect(url_for('lecturer_dashboard'))
        return redirect(url_for('dashboard'))
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username'].strip()
        password = request.form['password']
        login_type = request.form.get('login_type', 'student')
        is_student_login = login_type == 'student'
        is_parent_login = login_type == 'parent'
        is_lecturer_login = login_type == 'lecturer'
        error_key = f'{login_type}_error' if login_type in ('student', 'admin', 'parent', 'lecturer') else 'student_error'
        
        user = verify_user(username, password)
        if user:
            # Check if login type matches user role
            if login_type == 'admin' and user['role'] != 'admin':
                return render_template('login.html', **{error_key: 'Invalid admin credentials. Please use the correct login panel.'})
            if is_parent_login and user['role'] != 'parent':
                return render_template('login.html', **{error_key: 'Invalid parent credentials. Please use the correct login panel.'})
            if is_student_login and user['role'] != 'student':
                return render_template('login.html', **{error_key: 'Invalid student credentials. Please use the correct login panel.'})
            if is_lecturer_login and user['role'] != 'lecturer':
                return render_template('login.html', **{error_key: 'Invalid lecturer credentials. Please use the correct login panel.'})
            
            if is_student_login or is_parent_login:
                # Check approval status for student and parent accounts.
                if user['status'] == 'pending':
                    return render_template('login.html', **{error_key: 'Your account is waiting for admin approval. Please try again later.'})
                elif user['status'] == 'rejected':
                    return render_template('login.html', **{error_key: 'Your account has been rejected by admin. Please contact support.'})
                elif user['status'] != 'approved':
                    return render_template('login.html', **{error_key: 'Your account status is invalid.'})
            
            # Login successful
            session['user_id'] = user['id']
            session['username'] = user['username']
            session['full_name'] = user['full_name']
            session['role'] = user['role']
            session['status'] = user['status']
            
            if user['role'] == 'admin':
                return redirect(url_for('admin_dashboard'))
            if user['role'] == 'parent':
                return redirect(url_for('parent_dashboard'))
            if user['role'] == 'lecturer':
                return redirect(url_for('lecturer_dashboard'))
            return redirect(url_for('dashboard'))
        else:
            return render_template('login.html', **{error_key: 'Invalid credentials'})
    
    return render_template('login.html')

@app.route('/registration', methods=['GET'])
def registration():
    """Display registration page"""
    return render_template('registration.html')

@app.route('/register', methods=['POST'])
def register():
    username = request.form['username']
    password = request.form['password']
    full_name = request.form['full_name']
    email = request.form['email']
    
    user_id = create_user(username, password, full_name, email)
    if user_id:
        return jsonify({'success': True, 'message': 'Registration successful! Your account is pending admin approval. You will be able to login once approved.'})
    else:
        return jsonify({'success': False, 'message': 'Username or email already exists'})

@app.route('/dashboard')
@student_required
def dashboard():
    user_id = session['user_id']
    
    # Check if user has registered face
    face_registered = has_face_registered(user_id)
    
    # Get user's attendance records
    attendance_records = get_user_attendance(user_id)
    
    # Get today's attendance
    today_attendance = get_today_attendance()

    profile_image_url = build_face_image_url(get_user_face_image_path(user_id))
    pending_face_request = get_pending_face_request_for_user(user_id)
    today_record = get_today_user_attendance(user_id)
    attendance_summary = get_user_attendance_summary(user_id)
    attendance_settings = get_attendance_settings()
    
    return render_template('dashboard.html', 
                         face_registered=face_registered,
                         attendance_records=attendance_records,
                         today_attendance=today_attendance,
                         profile_image_url=profile_image_url,
                         pending_face_request=pending_face_request,
                         today_record=today_record,
                         attendance_summary=attendance_summary,
                         attendance_settings=attendance_settings)

@app.route('/student_export_attendance')
@student_required
def student_export_attendance():
    """Export logged-in student's own attendance history as CSV."""
    user_id = session['user_id']
    month = request.args.get('month') or date.today().strftime('%Y-%m')
    records = get_user_attendance(user_id, date=None)
    summary = get_user_attendance_summary(user_id, month)

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['Student', session.get('full_name', ''), 'Month', month])
    writer.writerow(['Working Days', summary['working_days'], 'Present', summary['present_days'],
                     'Late', summary['late_days'], 'Absent', summary['absent_days'],
                     'Percentage', f"{summary['percentage']}%"])
    writer.writerow([])
    writer.writerow(['Date', 'Subject', 'Check-in', 'Check-out', 'Status', 'Confidence'])
    for r in records:
        att_date = r[0]
        check_in  = r[1].strftime('%H:%M:%S') if hasattr(r[1], 'strftime') else (r[1][11:19] if r[1] else '-')
        check_out = r[2].strftime('%H:%M:%S') if hasattr(r[2], 'strftime') else (r[2][11:19] if r[2] else 'Pending')
        writer.writerow([att_date, r[6] if len(r) > 6 else 'General', check_in, check_out, r[3], f"{r[4] or 0:.2f}"])

    filename = f'my_attendance_{session.get("username", "student")}_{month}.csv'
    return Response(output.getvalue(), mimetype='text/csv',
                    headers={'Content-Disposition': f'attachment; filename={filename}'})

# ==================== ADMIN ROUTES ====================

@app.route('/admin_dashboard')
@admin_required
def admin_dashboard():
    stats = get_dashboard_stats()
    pending_students = append_face_image_urls(get_pending_students(), 5)
    attendance_details = append_face_image_urls(get_recent_attendance_details(), 11)
    monthly_report = get_monthly_attendance_report()
    low_attendance_students = get_low_attendance_students()
    for row in monthly_report:
        row['face_image_url'] = build_face_image_url(row.get('face_image_path'))
    for row in low_attendance_students:
        row['face_image_url'] = build_face_image_url(row.get('face_image_path'))
    
    return render_template('admin_dashboard.html',
                         stats=stats,
                         pending_students=pending_students,
                         attendance_details=attendance_details,
                         monthly_report=monthly_report,
                         low_attendance_students=low_attendance_students,
                         pending_face_request_count=count_pending_face_requests(),
                         attendance_settings=get_attendance_settings(),
                         calculated_working_days=get_current_month_working_days())

@app.route('/admin_face_requests')
@admin_required
def admin_face_requests():
    requests = append_face_image_urls(get_pending_face_requests(), 5)
    return render_template('admin_face_requests.html', face_requests=requests)

@app.route('/admin_approve_face_request/<int:request_id>', methods=['POST'])
@admin_required
def admin_approve_face_request(request_id):
    success, message = approve_face_request(request_id, session['user_id'])
    if success:
        clear_face_encoding_cache()
    status_code = 200 if success else 404
    return jsonify({'success': success, 'message': message}), status_code

@app.route('/admin_reject_face_request/<int:request_id>', methods=['POST'])
@admin_required
def admin_reject_face_request(request_id):
    success, message = reject_face_request(request_id, session['user_id'])
    status_code = 200 if success else 404
    return jsonify({'success': success, 'message': message}), status_code

@app.route('/admin_pending_approvals')
@admin_required
def admin_pending_approvals():
    pending_students = append_face_image_urls(get_pending_students(), 5)
    return render_template('admin_students.html',
                         students=pending_students,
                         page_title='Pending Approvals',
                         page_description='Review and manage new student registrations.',
                         list_status='pending')

@app.route('/admin_approved_students')
@admin_required
def admin_approved_students():
    approved_students = append_face_image_urls(get_approved_students(), 5)
    return render_template('admin_students.html',
                         students=approved_students,
                         page_title='Approved Students',
                         page_description='Students who can access face attendance.',
                         list_status='approved')

@app.route('/admin_rejected_students')
@admin_required
def admin_rejected_students():
    rejected_students = append_face_image_urls(get_rejected_students(), 5)
    return render_template('admin_students.html',
                         students=rejected_students,
                         page_title='Rejected Students',
                         page_description='Registrations that were not approved.',
                         list_status='rejected')

@app.route('/admin_student_details/<int:student_id>')
@admin_required
def admin_student_details(student_id):
    student = get_student_by_id(student_id)
    if not student:
        return redirect(url_for('admin_dashboard'))

    student['face_image_url'] = build_face_image_url(student.get('face_image_path'))
    pending_face_request = get_pending_face_request_for_user(student_id)
    if pending_face_request:
        pending_face_request['face_image_url'] = build_face_image_url(pending_face_request.get('image_path'))
    attendance_summary = get_user_attendance_summary(student_id)
    attendance_records = get_user_attendance(student_id)
    return render_template('admin_student_details.html',
                           student=student,
                           pending_face_request=pending_face_request,
                           attendance_summary=attendance_summary,
                           attendance_records=attendance_records)

@app.route('/admin_approve_student/<int:student_id>', methods=['POST'])
@admin_required
def admin_approve_student(student_id):
    approve_student(student_id)
    return jsonify({'success': True, 'message': 'Student approved successfully'})

@app.route('/admin_reject_student/<int:student_id>', methods=['POST'])
@admin_required
def admin_reject_student(student_id):
    reject_student(student_id)
    return jsonify({'success': True, 'message': 'Student rejected successfully'})

@app.route('/admin_search_students', methods=['GET'])
@admin_required
def admin_search_students():
    search_term = request.args.get('q', '')
    if search_term:
        students = append_face_image_urls(search_students(search_term), 6)
    else:
        students = []
    return render_template('admin_search_results.html', students=students, search_term=search_term)

@app.route('/admin_parents', methods=['GET', 'POST'])
@admin_required
def admin_parents():
    message = None
    error = None

    if request.method == 'POST':
        action = request.form.get('action')
        try:
            if action == 'create_parent':
                username = request.form.get('username', '').strip()
                password = request.form.get('password', '')
                full_name = request.form.get('full_name', '').strip()
                email = request.form.get('email', '').strip()
                student_id = request.form.get('student_id', '').strip()
                relationship = request.form.get('relationship', 'Parent').strip() or 'Parent'

                if not username or not password or not full_name or not email:
                    error = 'Enter parent name, email, username, and password.'
                else:
                    parent_id = create_parent_user(username, password, full_name, email)
                    if not parent_id:
                        error = 'Username or email already exists.'
                    elif student_id:
                        success, link_message = link_parent_to_student(parent_id, int(student_id), relationship)
                        message = link_message if success else 'Parent created, but student link failed: ' + link_message
                    else:
                        message = 'Parent account created successfully.'
            elif action == 'update_parent':
                parent_id = int(request.form.get('parent_id', '0'))
                username = request.form.get('username', '').strip()
                full_name = request.form.get('full_name', '').strip()
                email = request.form.get('email', '').strip()
                password = request.form.get('password', '')

                if not username or not full_name or not email:
                    error = 'Parent name, email, and username are required.'
                else:
                    success, result_message = update_parent_user(parent_id, username, full_name, email, password or None)
                    message = result_message if success else None
                    error = result_message if not success else None
            elif action == 'delete_parent':
                parent_id = int(request.form.get('parent_id', '0'))
                success, result_message = delete_parent_user(parent_id)
                message = result_message if success else None
                error = result_message if not success else None
            elif action == 'link_parent':
                parent_id = request.form.get('parent_id', '').strip()
                student_id = request.form.get('student_id', '').strip()
                relationship = request.form.get('relationship', 'Parent').strip() or 'Parent'

                if not parent_id or not student_id:
                    error = 'Choose both a parent and a student.'
                else:
                    success, link_message = link_parent_to_student(int(parent_id), int(student_id), relationship)
                    message = link_message if success else None
                    error = link_message if not success else None
            elif action == 'update_link':
                link_id = int(request.form.get('link_id', '0'))
                relationship = request.form.get('relationship', 'Parent').strip() or 'Parent'
                success, result_message = update_parent_student_link(link_id, relationship)
                message = result_message if success else None
                error = result_message if not success else None
            elif action == 'unlink_student':
                link_id = int(request.form.get('link_id', '0'))
                success, result_message = unlink_parent_student(link_id)
                message = result_message if success else None
                error = result_message if not success else None
        except ValueError:
            error = 'Invalid parent or student selection.'

    parents = get_parent_accounts()
    parent_links = get_parent_links()
    students = get_approved_students()
    return render_template('admin_parents.html',
                           parents=parents,
                           parent_links=parent_links,
                           students=students,
                           message=message,
                           error=error)

@app.route('/admin_lecturers', methods=['GET', 'POST'])
@admin_required
def admin_lecturers():
    message = None
    error = None

    if request.method == 'POST':
        action = request.form.get('action')
        if action == 'create_lecturer':
            username = request.form.get('username', '').strip()
            password = request.form.get('password', '')
            full_name = request.form.get('full_name', '').strip()
            email = request.form.get('email', '').strip()

            if not username or not password or not full_name or not email:
                error = 'Enter lecturer username, password, name, and email.'
            else:
                lecturer_id = create_lecturer_user(username, password, full_name, email)
                if lecturer_id:
                    message = 'Lecturer account created successfully.'
                else:
                    error = 'Username or email already exists.'
        elif action == 'update_lecturer':
            lecturer_id = request.form.get('lecturer_id', '').strip()
            username = request.form.get('username', '').strip()
            full_name = request.form.get('full_name', '').strip()
            email = request.form.get('email', '').strip()
            password = request.form.get('password', '')

            if not lecturer_id or not username or not full_name or not email:
                error = 'Lecturer ID, name, email, and username are required.'
            else:
                success, result_message = update_lecturer_user(int(lecturer_id), username, full_name, email, password or None)
                if success:
                    message = result_message
                else:
                    error = result_message
        elif action == 'delete_lecturer':
            lecturer_id = request.form.get('lecturer_id', '').strip()
            if not lecturer_id:
                error = 'Lecturer ID is required.'
            else:
                success, result_message = delete_lecturer_user(int(lecturer_id))
                if success:
                    message = result_message
                else:
                    error = result_message

    lecturers = get_lecturers()
    return render_template('admin_lecturers.html',
                           lecturers=lecturers,
                           message=message,
                           error=error)

@app.route('/admin_subjects', methods=['GET', 'POST'])
@admin_required
def admin_subjects():
    message = None
    error = None

    if request.method == 'POST':
        action = request.form.get('action')
        if action == 'create_subject':
            name = request.form.get('name', '').strip()
            if not name:
                error = 'Subject name is required.'
            else:
                success = create_subject(name)
                if success:
                    message = 'Subject created successfully.'
                else:
                    error = 'Subject already exists.'
        elif action == 'update_subject':
            subject_id = request.form.get('subject_id', '').strip()
            name = request.form.get('name', '').strip()
            if not subject_id or not name:
                error = 'Subject ID and name are required.'
            else:
                success = update_subject(int(subject_id), name)
                if success:
                    message = 'Subject updated successfully.'
                else:
                    error = 'Subject name already exists.'
        elif action == 'delete_subject':
            subject_id = request.form.get('subject_id', '').strip()
            if not subject_id:
                error = 'Subject ID is required.'
            else:
                delete_subject(int(subject_id))
                message = 'Subject deleted successfully.'

    subjects = get_subjects()
    return render_template('admin_subjects.html',
                           subjects=subjects,
                           message=message,
                           error=error)

# ==================== PARENT ROUTES ====================

@app.route('/parent_dashboard')
@parent_required
def parent_dashboard():
    students = get_parent_students(session['user_id'])
    for student in students:
        student['face_image_url'] = build_face_image_url(student.get('face_image_path'))
    return render_template('parent_dashboard.html', students=students)

@app.route('/parent_student/<int:student_id>')
@parent_required
def parent_student_details(student_id):
    if not parent_can_access_student(session['user_id'], student_id):
        return redirect(url_for('parent_dashboard'))

    student = get_student_by_id(student_id)
    if not student:
        return redirect(url_for('parent_dashboard'))

    student['face_image_url'] = build_face_image_url(student.get('face_image_path'))
    pending_face_request = get_pending_face_request_for_user(student_id)
    attendance_summary = get_user_attendance_summary(student_id)
    attendance_records = get_user_attendance(student_id)
    today_record = get_today_user_attendance(student_id)
    return render_template('parent_student_details.html',
                           student=student,
                           pending_face_request=pending_face_request,
                           attendance_summary=attendance_summary,
                           attendance_records=attendance_records,
                           today_record=today_record,
                           attendance_settings=get_attendance_settings())

@app.route('/parent_export_attendance/<int:student_id>')
@parent_required
def parent_export_attendance(student_id):
    """Export a linked student's attendance history as CSV (parent view)."""
    if not parent_can_access_student(session['user_id'], student_id):
        return redirect(url_for('parent_dashboard'))
    student = get_student_by_id(student_id)
    if not student:
        return redirect(url_for('parent_dashboard'))

    month = request.args.get('month') or date.today().strftime('%Y-%m')
    records = get_user_attendance(student_id)
    summary = get_user_attendance_summary(student_id, month)

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['Student', student['full_name'], 'Month', month])
    writer.writerow(['Working Days', summary['working_days'], 'Present', summary['present_days'],
                     'Late', summary['late_days'], 'Absent', summary['absent_days'],
                     'Percentage', f"{summary['percentage']}%"])
    writer.writerow([])
    writer.writerow(['Date', 'Subject', 'Check-in', 'Check-out', 'Status', 'Confidence'])
    for r in records:
        att_date = r[0]
        check_in  = r[1].strftime('%H:%M:%S') if hasattr(r[1], 'strftime') else (r[1][11:19] if r[1] else '-')
        check_out = r[2].strftime('%H:%M:%S') if hasattr(r[2], 'strftime') else (r[2][11:19] if r[2] else 'Pending')
        writer.writerow([att_date, r[6] if len(r) > 6 else 'General', check_in, check_out, r[3], f"{r[4] or 0:.2f}"])

    filename = f'attendance_{student["username"]}_{month}.csv'
    return Response(output.getvalue(), mimetype='text/csv',
                    headers={'Content-Disposition': f'attachment; filename={filename}'})

# ==================== END PARENT ROUTES ====================

# ==================== LECTURER ROUTES ====================

@app.route('/lecturer_dashboard')
@lecturer_required
def lecturer_dashboard():
    lecturer_id = session['user_id']
    sessions = get_lecturer_sessions(lecturer_id)
    active_session = None
    for s in sessions:
        if s['status'] == 'open':
            active_session = s
            break
    subjects = get_subjects()
    monthly_report = get_monthly_attendance_report()
    for row in monthly_report:
        row['face_image_url'] = build_face_image_url(row.get('face_image_path'))
    return render_template('lecturer_dashboard.html', sessions=sessions, active_session=active_session, subjects=subjects, monthly_report=monthly_report)

@app.route('/lecturer_open_session', methods=['POST'])
@lecturer_required
def lecturer_open_session():
    lecturer_id = session['user_id']
    subject = request.form.get('subject', '').strip()
    if not subject:
        return jsonify({'success': False, 'message': 'Subject is required.'}), 400
        
    lat_str = request.form.get('latitude')
    lon_str = request.form.get('longitude')
    lat = None
    lon = None
    if lat_str and lon_str:
        try:
            lat = float(lat_str)
            lon = float(lon_str)
        except ValueError:
            pass
            
    session_id = create_attendance_session(lecturer_id, subject, lat, lon)
    return jsonify({'success': True, 'message': f'Attendance session for {subject} opened successfully!', 'session_id': session_id})

@app.route('/lecturer_close_session/<int:session_id>', methods=['POST'])
@lecturer_required
def lecturer_close_session(session_id):
    close_attendance_session(session_id)
    return jsonify({'success': True, 'message': 'Session closed. All students who had not checked out have been automatically checked out.'})

@app.route('/lecturer_session_details/<int:session_id>')
@lecturer_required
def lecturer_session_details(session_id):
    attendance = get_session_attendance_details(session_id)
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT subject, status, created_at, closed_at FROM attendance_sessions WHERE id = ?', (session_id,))
    s_info = cursor.fetchone()
    conn.close()
    
    if not s_info:
        return redirect(url_for('lecturer_dashboard'))
        
    session_details = {
        'id': session_id,
        'subject': s_info[0],
        'status': s_info[1],
        'created_at': s_info[2],
        'closed_at': s_info[3]
    }
    
    return render_template('lecturer_session_details.html', session_details=session_details, attendance=attendance)

@app.route('/lecturer_export_session/<int:session_id>')
@lecturer_required
def lecturer_export_session(session_id):
    attendance = get_session_attendance_details(session_id)
    
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT subject, created_at FROM attendance_sessions WHERE id = ?', (session_id,))
    s_info = cursor.fetchone()
    conn.close()
    
    subject = s_info[0] if s_info else "Session"
    raw_date = s_info[1] if s_info else None
    if raw_date is None:
        date_str = "Export"
    elif isinstance(raw_date, str):
        date_str = raw_date[:10]
    else:
        date_str = raw_date.strftime('%Y-%m-%d')
    
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        'Student ID', 'Full Name', 'Username', 'Email', 'Check-in Time', 'Status', 'Confidence'
    ])
    
    for row in attendance:
        writer.writerow([
            row['student_id'], row['full_name'], row['username'], row['email'],
            row['check_in_time'], row['status'], f"{row['confidence']:.2f}"
        ])
        
    csv_data = output.getvalue()
    filename = f'attendance_{subject.replace(" ", "_")}_{date_str}.csv'
    return Response(
        csv_data,
        mimetype='text/csv',
        headers={'Content-Disposition': f'attachment; filename={filename}'}
    )

# ==================== END LECTURER ROUTES ====================

@app.route('/admin_delete_student/<int:student_id>', methods=['POST'])
@admin_required
def admin_delete_student(student_id):
    success, message = delete_student(student_id)
    if success:
        clear_face_encoding_cache()
    status_code = 200 if success else 404
    return jsonify({'success': success, 'message': message}), status_code

@app.route('/admin_attendance_settings', methods=['POST'])
@admin_required
def admin_attendance_settings():
    reporting_time = request.form.get('reporting_time', '').strip()
    threshold_text = request.form.get('low_attendance_threshold', '').strip()
    working_days_text = request.form.get('working_days_per_month', '').strip()

    try:
        datetime.strptime(reporting_time, '%H:%M')
        threshold = int(threshold_text)
        working_days = int(working_days_text)
    except (TypeError, ValueError):
        return jsonify({'success': False, 'message': 'Enter valid attendance policy values.'}), 400

    if not 1 <= threshold <= 100:
        return jsonify({'success': False, 'message': 'Attendance threshold must be between 1 and 100.'}), 400
    if not 1 <= working_days <= 31:
        return jsonify({'success': False, 'message': 'Working days must be between 1 and 31.'}), 400

    try:
        college_lat = float(request.form.get('college_lat', 0.0))
        college_lon = float(request.form.get('college_lon', 0.0))
        geofencing_radius = float(request.form.get('geofencing_radius', 150.0))
        geofencing_enabled = 1 if request.form.get('geofencing_enabled') in ('1', 'on', True) else 0
        
        smtp_host = request.form.get('smtp_host', 'smtp.gmail.com').strip()
        smtp_port = int(request.form.get('smtp_port', 587))
        smtp_user = request.form.get('smtp_user', '').strip()
        smtp_password = request.form.get('smtp_password', '').strip()
        smtp_sender = request.form.get('smtp_sender', '').strip()
    except (TypeError, ValueError):
        return jsonify({'success': False, 'message': 'Invalid geofencing or SMTP numerical values.'}), 400

    update_attendance_settings(
        reporting_time, threshold, working_days,
        college_lat=college_lat, college_lon=college_lon,
        geofencing_radius=geofencing_radius, geofencing_enabled=geofencing_enabled,
        smtp_host=smtp_host, smtp_port=smtp_port,
        smtp_user=smtp_user, smtp_password=smtp_password, smtp_sender=smtp_sender
    )
    return jsonify({'success': True, 'message': 'Attendance policy and configurations updated successfully.'})

@app.route('/lecturer_export_monthly')
@lecturer_required
def lecturer_export_monthly():
    """Export all students' monthly attendance report as CSV (lecturer view)."""
    month = request.args.get('month') or date.today().strftime('%Y-%m')
    report = get_monthly_attendance_report(month)

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['Student ID', 'Full Name', 'Username', 'Email', 'Month',
                     'Working Days', 'Present Days', 'Late Days', 'Absent Days',
                     'Completed Checkouts', 'Attendance %', 'Low Attendance'])
    for row in report:
        writer.writerow([
            row['id'], row['full_name'], row['username'], row['email'], month,
            row['working_days'], row['present_days'], row['late_days'],
            row['absent_days'], row['completed_days'], row['percentage'],
            'Yes' if row['is_low'] else 'No'
        ])

    filename = f'monthly_report_{month}.csv'
    return Response(output.getvalue(), mimetype='text/csv',
                    headers={'Content-Disposition': f'attachment; filename={filename}'})

@app.route('/admin_export_attendance')
@admin_required
def admin_export_attendance():
    month = request.args.get('month') or date.today().strftime('%Y-%m')
    report = get_monthly_attendance_report(month)

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        'Student ID', 'Full Name', 'Username', 'Email', 'Month',
        'Working Days', 'Present Days', 'Late Days', 'Absent Days',
        'Completed Checkouts', 'Attendance Percentage', 'Low Attendance'
    ])

    for row in report:
        writer.writerow([
            row['id'], row['full_name'], row['username'], row['email'], month,
            row['working_days'], row['present_days'], row['late_days'],
            row['absent_days'], row['completed_days'], row['percentage'],
            'Yes' if row['is_low'] else 'No'
        ])

    csv_data = output.getvalue()
    filename = f'attendance_report_{month}.csv'
    return Response(
        csv_data,
        mimetype='text/csv',
        headers={'Content-Disposition': f'attachment; filename={filename}'}
    )

@app.route('/admin_notify_low_attendance', methods=['POST'])
@admin_required
def admin_notify_low_attendance():
    student_id = request.form.get('student_id')
    settings = get_attendance_settings()
    
    students_to_notify = []
    if student_id:
        s = get_student_by_id(int(student_id))
        if s:
            students_to_notify.append(s)
    else:
        for s in get_approved_students():
            summary = get_user_attendance_summary(s[0])
            if summary['is_low']:
                students_to_notify.append({
                    'id': s[0],
                    'full_name': s[2],
                    'email': s[3]
                })
                
    if not students_to_notify:
        return jsonify({'success': False, 'message': 'No students found below the low attendance threshold.'})
        
    import smtplib
    from email.mime.text import MIMEText
    
    success_count = 0
    log_lines = []
    smtp_configured = bool(settings['smtp_user'] and settings['smtp_password'])
    
    for student in students_to_notify:
        summary = get_user_attendance_summary(student['id'])
        percentage = summary['percentage']
        
        subject = "Low Attendance Alert - FaceTrack"
        body = f"Dear {student['full_name']},\n\nYour attendance for this month is {percentage}%, which is below the college policy threshold of {settings['low_attendance_threshold']}%.\n\nPlease attend classes regularly to avoid academic penalties.\n\nBest regards,\nCollege Administration"
        
        message_sent = False
        error_details = ""
        
        if smtp_configured:
            try:
                msg = MIMEText(body)
                msg['Subject'] = subject
                msg['From'] = settings['smtp_sender'] or settings['smtp_user']
                msg['To'] = student['email']
                
                with smtplib.SMTP(settings['smtp_host'], settings['smtp_port']) as server:
                    server.starttls()
                    server.login(settings['smtp_user'], settings['smtp_password'])
                    server.send_message(msg)
                message_sent = True
            except Exception as e:
                error_details = str(e)
                
        log_entry = f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] To: {student['full_name']} ({student['email']}) | Attendance: {percentage}% | Sent: {'Yes (SMTP)' if message_sent else 'Yes (Simulation)'} | Error: {error_details}\n"
        log_lines.append(log_entry)
        
        try:
            log_dir = 'static/logs'
            os.makedirs(log_dir, exist_ok=True)
            with open(os.path.join(log_dir, 'notifications.log'), 'a') as f:
                f.write(log_entry)
        except Exception:
            pass
            
        success_count += 1
        
    status_msg = f"Successfully notified {success_count} students."
    if not smtp_configured:
        status_msg += " (Simulation mode active: logged to static/logs/notifications.log)"
        
    return jsonify({'success': True, 'message': status_msg})

@app.route('/admin_bulk_attendance', methods=['GET', 'POST'])
@admin_required
def admin_bulk_attendance():
    if request.method == 'POST':
        if 'bulk_image' not in request.files:
            return jsonify({'success': False, 'message': 'No image provided.'})
        file = request.files['bulk_image']
        if file.filename == '':
            return jsonify({'success': False, 'message': 'No image selected.'})
            
        if file and allowed_file(file.filename):
            filename = secure_filename(f"bulk_{datetime.now().strftime('%Y%m%d%H%M%S')}_{file.filename}")
            file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(file_path)
            
            frame = cv2.imread(file_path)
            if frame is None:
                if os.path.exists(file_path):
                    os.remove(file_path)
                return jsonify({'success': False, 'message': 'Failed to read image.'})
                
            recognized = recognize_multiple_faces(frame)
            if os.path.exists(file_path):
                os.remove(file_path)
                
            if not recognized:
                return jsonify({'success': False, 'message': 'No approved students recognized in the uploaded photo.'})
                
            return jsonify({'success': True, 'recognized': recognized})
            
        return jsonify({'success': False, 'message': 'Invalid file format.'})
        
    return render_template('admin_bulk_attendance.html', attendance_settings=get_attendance_settings())

@app.route('/admin_confirm_bulk_attendance', methods=['POST'])
@admin_required
def admin_confirm_bulk_attendance():
    student_ids = request.json.get('student_ids', [])
    subject = request.json.get('subject', 'General')
    
    if not student_ids:
        return jsonify({'success': False, 'message': 'No students selected.'})
        
    marked = []
    for sid in student_ids:
        res = save_attendance(int(sid), 0.90, subject)
        if res['success']:
            marked.append(sid)
            
    return jsonify({'success': True, 'message': f'Successfully marked check-in for {len(marked)} students in {subject}.'})

# ==================== END ADMIN ROUTES ====================

@app.route('/register_face', methods=['GET', 'POST'])
@student_required
def register_face():
    if request.method == 'POST':
        if 'face_image' not in request.files:
            return jsonify({'success': False, 'message': 'No image uploaded'})
        
        file = request.files['face_image']
        if file.filename == '':
            return jsonify({'success': False, 'message': 'No image selected'})
        
        if file and allowed_file(file.filename):
            file_bytes = file.read()
            request_type = 'update' if has_face_registered(session['user_id']) else 'initial'
            success, message = submit_face_approval_request(session['user_id'], file_bytes, request_type)
            return jsonify({'success': success, 'message': message})
        
        return jsonify({'success': False, 'message': 'Invalid file format'})
    
    return render_template('register_face.html')

@app.route('/attendance')
@student_required
def attendance():
    if not has_face_registered(session['user_id']):
        return redirect(url_for('register_face'))
    
    selected_subject = request.args.get('subject')
    subjects = get_subjects()
    if not selected_subject and subjects:
        selected_subject = subjects[0]['name']

    today_record = get_today_user_attendance(session['user_id'], subject=selected_subject)
    
    return render_template(
        'attendance.html',
        today_record=today_record,
        attendance_settings=get_attendance_settings(),
        subjects=subjects,
        selected_subject=selected_subject
    )

# Server-side camera and feed generation removed. Camera is now captured client-side via WebRTC.

@app.route('/recognize_frame', methods=['POST'])
@student_required
def recognize_frame():
    user_id = session['user_id']
    data = request.json
    if not data or 'image' not in data:
        return jsonify({'success': False, 'message': 'No image data sent'})
    
    import base64
    try:
        img_data = data['image'].split(',')[1] if ',' in data['image'] else data['image']
        img_bytes = base64.b64decode(img_data)
        nparr = np.frombuffer(img_bytes, np.uint8)
        frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    except Exception:
        return jsonify({'success': False, 'message': 'Failed to decode image'})
        
    face_locations, face_data = recognize_faces_in_frame(frame)
    user_recognized = False
    confidence = 0
    
    for (name, user_data) in face_data:
        if user_data[0] == user_id:
            user_recognized = True
            confidence = user_data[1]
            break
            
    if user_recognized:
        liveness_tracker[user_id] = {'verified': True}
        return jsonify({'success': True, 'verified': True, 'confidence': confidence})
    else:
        return jsonify({'success': False, 'verified': False})

@app.route('/mark_attendance', methods=['POST'])
@student_required
def mark_attendance():
    user_id = session['user_id']
    subject = request.form.get('subject', 'General')
    
    # Check if active session exists
    active_session = get_active_session_for_subject(subject)
    if not active_session:
        return jsonify({'success': False, 'message': f'Attendance is blocked. There is no active session open for subject "{subject}". Please wait for your lecturer to open the session.'})
    
    # 1. Presence / verification check
    tracker = liveness_tracker.get(user_id)
    if not tracker or not tracker.get('verified'):
        return jsonify({'success': False, 'message': 'Face verification not complete. Please look at the camera first.'})

    # 2. Geofencing check
    settings = get_attendance_settings()
    if settings.get('geofencing_enabled'):
        lat_str = request.form.get('latitude')
        lon_str = request.form.get('longitude')
        if not lat_str or not lon_str:
            return jsonify({'success': False, 'message': 'Location access is required by college attendance policy.'})
        try:
            student_lat = float(lat_str)
            student_lon = float(lon_str)
        except ValueError:
            return jsonify({'success': False, 'message': 'Invalid location coordinates received.'})
            
        # Classroom-level check if the active session has coordinates
        if active_session.get('latitude') is not None and active_session.get('longitude') is not None:
            dist = calculate_distance(student_lat, student_lon, active_session['latitude'], active_session['longitude'])
            if dist > 10.0:  # Enforce strict 10 meters classroom boundary
                return jsonify({'success': False, 'message': f'Attendance rejected. You must strictly mark attendance inside the classroom (Distance to class: {dist:.1f}m, Max allowed: 10m).'})
        else:
            dist = calculate_distance(student_lat, student_lon, settings['college_lat'], settings['college_lon'])
            if dist > settings['geofencing_radius']:
                return jsonify({'success': False, 'message': f'You are outside the campus boundary. Distance: {dist:.1f}m (Max: {settings["geofencing_radius"]}m)'})

    # 3. Save attendance
    result = save_attendance(user_id, 0.95, subject)
    if user_id in liveness_tracker:
        liveness_tracker[user_id] = {'verified': False}
    return jsonify(result)

@app.route('/mark_attendance_with_photo', methods=['POST'])
@student_required
def mark_attendance_with_photo():
    subject = request.form.get('subject', 'General')
    
    # Check if active session exists
    active_session = get_active_session_for_subject(subject)
    if not active_session:
        return jsonify({'success': False, 'message': f'Attendance is blocked. There is no active session open for subject "{subject}". Please wait for your lecturer to open the session.'})

    # 1. Geofencing check
    settings = get_attendance_settings()
    if settings.get('geofencing_enabled'):
        lat_str = request.form.get('latitude')
        lon_str = request.form.get('longitude')
        if not lat_str or not lon_str:
            return jsonify({'success': False, 'message': 'Location access is required by college attendance policy.'})
        try:
            student_lat = float(lat_str)
            student_lon = float(lon_str)
        except ValueError:
            return jsonify({'success': False, 'message': 'Invalid location coordinates received.'})
            
        # Classroom-level check if the active session has coordinates
        if active_session.get('latitude') is not None and active_session.get('longitude') is not None:
            dist = calculate_distance(student_lat, student_lon, active_session['latitude'], active_session['longitude'])
            if dist > 10.0:  # Enforce strict 10 meters classroom boundary
                return jsonify({'success': False, 'message': f'Attendance rejected. You must strictly mark attendance inside the classroom (Distance to class: {dist:.1f}m, Max allowed: 10m).'})
        else:
            dist = calculate_distance(student_lat, student_lon, settings['college_lat'], settings['college_lon'])
            if dist > settings['geofencing_radius']:
                return jsonify({'success': False, 'message': f'You are outside the campus boundary. Distance: {dist:.1f}m (Max: {settings["geofencing_radius"]}m)'})

    if 'face_image' not in request.files:
        return jsonify({'success': False, 'message': 'No image provided'})
    
    file = request.files['face_image']
    
    if file.filename == '':
        return jsonify({'success': False, 'message': 'No image selected'})
    
    if file and allowed_file(file.filename):
        # Save the file temporarily
        temp_filename = secure_filename(f"temp_{session['user_id']}_{file.filename}")
        temp_path = os.path.join(app.config['UPLOAD_FOLDER'], temp_filename)
        file.save(temp_path)
        
        # Load the image and recognize faces
        frame = cv2.imread(temp_path)
        if frame is None:
            os.remove(temp_path)  # Clean up
            return jsonify({'success': False, 'message': 'Failed to process image'})
        
        # Recognize faces
        face_locations, face_data = recognize_faces_in_frame(frame)
        
        # Clean up the temporary file
        os.remove(temp_path)
        
        user_id = session['user_id']
        user_recognized = False
        confidence = 0
        
        for (name, user_data) in face_data:
            if user_data[0] == user_id:  # Check if current user is recognized
                user_recognized = True
                confidence = user_data[1]
                break
        
        if user_recognized:
            subject = request.form.get('subject', 'General')
            result = save_attendance(user_id, confidence, subject)
            return jsonify(result)
        else:
            return jsonify({'success': False, 'message': 'Face not recognized. Please ensure your face is clearly visible.'})
    
    return jsonify({'success': False, 'message': 'Invalid file format'})

@app.route('/get_attendance_stats')
@student_required
def get_attendance_stats():
    user_id = session['user_id']
    
    # Get attendance for last 7 days
    records = get_user_attendance(user_id)
    
    # Process data for charts
    daily_attendance = {}
    for record in records:
        raw_date = record[0]
        if isinstance(raw_date, str):
            date_str = raw_date.split()[0]  # "YYYY-MM-DD HH:MM:SS" or "YYYY-MM-DD"
        else:
            date_str = raw_date.strftime('%Y-%m-%d')  # native date/datetime object
        if date_str not in daily_attendance:
            daily_attendance[date_str] = 0
        daily_attendance[date_str] += 1
    
    return jsonify({
        'daily_attendance': daily_attendance,
        'total_records': len(records),
        'summary': get_user_attendance_summary(user_id),
        'today_record': get_today_user_attendance(user_id)
    })

@app.route('/logout')
def logout():
    global camera
    if camera:
        camera.release()
        camera = None
    
    # Sign out of Supabase session if active
    from database import supabase_client
    if supabase_client:
        try:
            supabase_client.auth.sign_out()
        except Exception:
            pass
            
    session.clear()
    return redirect(url_for('login'))

if __name__ == '__main__':
    app.run(
        host=os.environ.get('FLASK_RUN_HOST', '127.0.0.1'),
        port=int(os.environ.get('PORT', 5000)),
        debug=os.environ.get('FLASK_DEBUG') == '1',
        threaded=True
    )
