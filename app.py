from flask import Flask, render_template, request, redirect, url_for, session, jsonify, Response
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
                     count_pending_face_requests, approve_face_request, reject_face_request)
from face_utils import (submit_face_approval_request, recognize_faces_in_frame,
                        has_face_registered, allowed_file, clear_face_encoding_cache)

app = Flask(__name__)
app.secret_key = os.environ.get('FLASK_SECRET_KEY', 'your-secret-key-change-this')

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

# Global camera object
camera = None
latest_frame = None
frame_lock = threading.Lock()
camera_lock = threading.Lock()
recognition_frame_index = 0
last_face_locations = []
last_face_data = []

def create_camera_capture():
    """Create a camera capture object configured for the highest practical quality."""
    camera_backends = [
        getattr(cv2, 'CAP_DSHOW', cv2.CAP_ANY),
        getattr(cv2, 'CAP_MSMF', cv2.CAP_ANY),
        cv2.CAP_ANY,
    ]

    capture = None
    for backend in camera_backends:
        capture = cv2.VideoCapture(0, backend)
        if capture.isOpened():
            break

    if capture is None or not capture.isOpened():
        return None

    # Keep camera output moderate for smoother streaming on typical laptops.
    capture.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
    capture.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
    capture.set(cv2.CAP_PROP_FPS, 30)
    capture.set(cv2.CAP_PROP_BUFFERSIZE, 1)

    return capture

def build_face_image_url(image_path):
    """Convert stored image path to a browser-safe static URL."""
    if not image_path:
        return None

    normalized_path = image_path.replace('\\', '/')
    if normalized_path.startswith('static/'):
        normalized_path = normalized_path[len('static/'):]

    return url_for('static', filename=normalized_path)

def append_face_image_urls(records, image_index):
    """Append face image URL as an extra field to tuple records."""
    output = []
    for record in records:
        face_image_path = record[image_index] if len(record) > image_index else None
        output.append(tuple(list(record) + [build_face_image_url(face_image_path)]))
    return output

def encode_status_frame(message):
    """Build a simple MJPEG frame when the camera cannot provide video."""
    frame = np.zeros((480, 640, 3), dtype=np.uint8)
    cv2.putText(frame, message, (42, 235), cv2.FONT_HERSHEY_SIMPLEX, 0.72, (255, 255, 255), 2, cv2.LINE_AA)
    ret, buffer = cv2.imencode('.jpg', frame, [int(cv2.IMWRITE_JPEG_QUALITY), 85])
    return buffer.tobytes() if ret else b''

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

@app.route('/')
def index():
    if 'user_id' in session:
        if session.get('role') == 'admin':
            return redirect(url_for('admin_dashboard'))
        else:
            return redirect(url_for('dashboard'))
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username'].strip()
        password = request.form['password']
        login_type = request.form.get('login_type', 'student')  # 'admin' or student panel
        is_student_login = login_type == 'student'
        error_key = 'student_error' if is_student_login else 'admin_error'
        
        user = verify_user(username, password)
        if user:
            # Check if login type matches user role
            if login_type == 'admin' and user['role'] != 'admin':
                return render_template('login.html', **{error_key: 'Invalid admin credentials. Please use student login.'})
            if is_student_login and user['role'] != 'student':
                return render_template('login.html', **{error_key: 'Invalid student credentials. Please use admin login.'})
            
            if is_student_login:
                # Check student approval status
                if user['status'] == 'pending':
                    return render_template('login.html', **{error_key: 'Your account is waiting for admin approval. Please try again later.'})
                elif user['status'] == 'rejected':
                    return render_template('login.html', **{error_key: 'Your registration has been rejected by admin. Please contact support.'})
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
            else:
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
                         attendance_settings=get_attendance_settings())

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

    update_attendance_settings(reporting_time, threshold, working_days)
    return jsonify({'success': True, 'message': 'Attendance policy updated successfully.'})

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
            filename = secure_filename(f"user_{session['user_id']}_{file.filename}")
            file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(file_path)

            request_type = 'update' if has_face_registered(session['user_id']) else 'initial'
            success, message = submit_face_approval_request(session['user_id'], file_path, request_type)
            if not success and os.path.exists(file_path):
                os.remove(file_path)
            return jsonify({'success': success, 'message': message})
        
        return jsonify({'success': False, 'message': 'Invalid file format'})
    
    return render_template('register_face.html')

@app.route('/attendance')
@student_required
def attendance():
    if not has_face_registered(session['user_id']):
        return redirect(url_for('register_face'))
    
    return render_template(
        'attendance.html',
        today_record=get_today_user_attendance(session['user_id']),
        attendance_settings=get_attendance_settings()
    )

def generate_frames(mirror_preview=False, recognition_interval=5, jpeg_quality=75):
    global camera, latest_frame
    with camera_lock:
        if camera is not None:
            camera.release()
        camera = create_camera_capture()
        latest_frame = None
        local_camera = camera

    if local_camera is None:
        frame = encode_status_frame('Camera not available')
        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n')
        return

    local_frame_index = 0
    local_face_locations = []
    local_face_data = []

    try:
        while True:
            success, frame = local_camera.read()
            if not success:
                fallback = encode_status_frame('Camera frame unavailable')
                yield (b'--frame\r\n'
                       b'Content-Type: image/jpeg\r\n\r\n' + fallback + b'\r\n')
                break

            if mirror_preview:
                frame = cv2.flip(frame, 1)

            with frame_lock:
                latest_frame = frame.copy()

            local_frame_index += 1
            if local_frame_index % recognition_interval == 0 or not local_face_locations:
                local_face_locations, local_face_data = recognize_faces_in_frame(frame)

            face_locations = local_face_locations
            face_data = local_face_data

            for (top, right, bottom, left), (name, user_data) in zip(face_locations, face_data):
                cv2.rectangle(frame, (left, top), (right, bottom), (0, 255, 0), 2)
                cv2.rectangle(frame, (left, bottom - 35), (right, bottom), (0, 255, 0), cv2.FILLED)
                font = cv2.FONT_HERSHEY_DUPLEX
                cv2.putText(frame, name, (left + 6, bottom - 6), font, 0.6, (255, 255, 255), 1)

            ret, buffer = cv2.imencode('.jpg', frame, [int(cv2.IMWRITE_JPEG_QUALITY), jpeg_quality])
            if not ret:
                continue
            frame = buffer.tobytes()

            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n')
    finally:
        with camera_lock:
            if camera is local_camera:
                local_camera.release()
                camera = None

@app.route('/capture_frame')
@login_required
def capture_frame():
    with frame_lock:
        frame = None if latest_frame is None else latest_frame.copy()

    if frame is None:
        return jsonify({'success': False, 'message': 'Camera feed is not ready yet'}), 503

    ret, buffer = cv2.imencode('.jpg', frame, [int(cv2.IMWRITE_JPEG_QUALITY), 90])
    if not ret:
        return jsonify({'success': False, 'message': 'Failed to capture frame'}), 500

    return Response(buffer.tobytes(), mimetype='image/jpeg')

@app.route('/video_feed')
@login_required
def video_feed():
    return Response(generate_frames(mirror_preview=False, recognition_interval=5, jpeg_quality=75),
                   mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route('/video_feed_register')
@student_required
def video_feed_register():
    return Response(generate_frames(mirror_preview=True, recognition_interval=8, jpeg_quality=70),
                   mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route('/mark_attendance', methods=['POST'])
@student_required
def mark_attendance():
    with frame_lock:
        frame = None if latest_frame is None else latest_frame.copy()

    if frame is None:
        return jsonify({'success': False, 'message': 'Camera feed is not ready. Wait for the preview and try again.'})

    face_locations, face_data = recognize_faces_in_frame(frame)
    
    user_id = session['user_id']
    user_recognized = False
    confidence = 0
    
    for (name, user_data) in face_data:
        if user_data[0] == user_id:  # Check if current user is recognized
            user_recognized = True
            confidence = user_data[1]
            break
    
    if user_recognized:
        result = save_attendance(user_id, confidence)
        return jsonify(result)
    else:
        return jsonify({'success': False, 'message': 'Face not recognized. Please ensure your face is clearly visible.'})

@app.route('/mark_attendance_with_photo', methods=['POST'])
@student_required
def mark_attendance_with_photo():
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
            result = save_attendance(user_id, confidence)
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
        date_str = record[0].split()[0]  # Get date part
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
    
    session.clear()
    return redirect(url_for('login'))

if __name__ == '__main__':
    app.run(
        host=os.environ.get('FLASK_RUN_HOST', '127.0.0.1'),
        port=int(os.environ.get('PORT', 5000)),
        debug=os.environ.get('FLASK_DEBUG') == '1',
        threaded=True
    )
