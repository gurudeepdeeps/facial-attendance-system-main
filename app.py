from flask import Flask, render_template, request, redirect, url_for, session, jsonify, Response
import cv2
import os
import threading
from werkzeug.utils import secure_filename
import base64
import numpy as np
from datetime import datetime, date
import json
from functools import wraps

from database import (init_db, verify_user, create_user, save_attendance, get_user_attendance, 
                     get_today_attendance, get_pending_employees, get_approved_employees, 
                     get_rejected_employees, approve_employee, reject_employee, 
                     get_employee_by_id, search_employees, get_dashboard_stats,
                     get_recent_attendance_details, delete_employee, get_user_face_image_path)
from face_utils import save_face_encoding, recognize_faces_in_frame, has_face_registered, allowed_file

app = Flask(__name__)
app.secret_key = 'your-secret-key-change-this'  # Change this in production

# Configuration
UPLOAD_FOLDER = 'static/uploads'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# Ensure upload directory exists
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# Initialize database
init_db()

# Global camera object
camera = None
latest_frame = None
frame_lock = threading.Lock()
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

def employee_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session or session.get('role') != 'employee':
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
        username = request.form['username']
        password = request.form['password']
        login_type = request.form.get('login_type', 'employee')  # 'admin' or 'employee'
        
        user = verify_user(username, password)
        if user:
            # Check if login type matches user role
            if login_type == 'admin' and user['role'] != 'admin':
                return render_template('login.html', error='Invalid admin credentials. Please use employee login.')
            
            if login_type == 'employee':
                # Check employee status
                if user['status'] == 'pending':
                    return render_template('login.html', error='Your account is waiting for admin approval. Please try again later.')
                elif user['status'] == 'rejected':
                    return render_template('login.html', error='Your registration has been rejected by admin. Please contact support.')
                elif user['status'] != 'approved':
                    return render_template('login.html', error='Your account status is invalid.')
            
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
            return render_template('login.html', error='Invalid credentials')
    
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
@employee_required
def dashboard():
    user_id = session['user_id']
    
    # Check if user has registered face
    face_registered = has_face_registered(user_id)
    
    # Get user's attendance records
    attendance_records = get_user_attendance(user_id)
    
    # Get today's attendance
    today_attendance = get_today_attendance()

    profile_image_url = build_face_image_url(get_user_face_image_path(user_id))
    
    return render_template('dashboard.html', 
                         face_registered=face_registered,
                         attendance_records=attendance_records,
                         today_attendance=today_attendance,
                         profile_image_url=profile_image_url)

# ==================== ADMIN ROUTES ====================

@app.route('/admin_dashboard')
@admin_required
def admin_dashboard():
    stats = get_dashboard_stats()
    pending_employees = append_face_image_urls(get_pending_employees(), 5)
    attendance_details = append_face_image_urls(get_recent_attendance_details(), 8)
    
    return render_template('admin_dashboard.html', 
                         stats=stats,
                         pending_employees=pending_employees,
                         attendance_details=attendance_details)

@app.route('/admin_pending_approvals')
@admin_required
def admin_pending_approvals():
    pending_employees = append_face_image_urls(get_pending_employees(), 5)
    return render_template('admin_pending_approvals.html', 
                         employees=pending_employees)

@app.route('/admin_approved_employees')
@admin_required
def admin_approved_employees():
    approved_employees = append_face_image_urls(get_approved_employees(), 5)
    return render_template('admin_approved_employees.html', 
                         employees=approved_employees)

@app.route('/admin_rejected_employees')
@admin_required
def admin_rejected_employees():
    rejected_employees = append_face_image_urls(get_rejected_employees(), 5)
    return render_template('admin_rejected_employees.html', 
                         employees=rejected_employees)

@app.route('/admin_employee_details/<int:employee_id>')
@admin_required
def admin_employee_details(employee_id):
    employee = get_employee_by_id(employee_id)
    if not employee:
        return redirect(url_for('admin_dashboard'))

    employee['face_image_url'] = build_face_image_url(employee.get('face_image_path'))
    return render_template('admin_employee_details.html', employee=employee)

@app.route('/admin_approve_employee/<int:employee_id>', methods=['POST'])
@admin_required
def admin_approve_employee(employee_id):
    approve_employee(employee_id)
    return jsonify({'success': True, 'message': 'Employee approved successfully'})

@app.route('/admin_reject_employee/<int:employee_id>', methods=['POST'])
@admin_required
def admin_reject_employee(employee_id):
    reject_employee(employee_id)
    return jsonify({'success': True, 'message': 'Employee rejected successfully'})

@app.route('/admin_search_employees', methods=['GET'])
@admin_required
def admin_search_employees():
    search_term = request.args.get('q', '')
    if search_term:
        employees = append_face_image_urls(search_employees(search_term), 6)
    else:
        employees = []
    return render_template('admin_search_results.html', employees=employees, search_term=search_term)

@app.route('/admin_delete_employee/<int:employee_id>', methods=['POST'])
@admin_required
def admin_delete_employee(employee_id):
    success, message = delete_employee(employee_id)
    status_code = 200 if success else 404
    return jsonify({'success': success, 'message': message}), status_code

# ==================== END ADMIN ROUTES ====================

@app.route('/register_face', methods=['GET', 'POST'])
@employee_required
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
            
            success, message = save_face_encoding(session['user_id'], file_path)
            return jsonify({'success': success, 'message': message})
        
        return jsonify({'success': False, 'message': 'Invalid file format'})
    
    return render_template('register_face.html')

@app.route('/attendance')
@employee_required
def attendance():
    if not has_face_registered(session['user_id']):
        return redirect(url_for('register_face'))
    
    return render_template('attendance.html')

def generate_frames(mirror_preview=False, recognition_interval=5, jpeg_quality=75):
    global camera, latest_frame
    camera = create_camera_capture()
    if camera is None:
        return

    local_frame_index = 0
    local_face_locations = []
    local_face_data = []
    
    while True:
        success, frame = camera.read()
        if not success:
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
        
        # Draw rectangles and names
        for (top, right, bottom, left), (name, user_data) in zip(face_locations, face_data):
            # Draw rectangle
            cv2.rectangle(frame, (left, top), (right, bottom), (0, 255, 0), 2)
            
            # Draw name
            cv2.rectangle(frame, (left, bottom - 35), (right, bottom), (0, 255, 0), cv2.FILLED)
            font = cv2.FONT_HERSHEY_DUPLEX
            cv2.putText(frame, name, (left + 6, bottom - 6), font, 0.6, (255, 255, 255), 1)
        
        ret, buffer = cv2.imencode('.jpg', frame, [int(cv2.IMWRITE_JPEG_QUALITY), jpeg_quality])
        if not ret:
            continue
        frame = buffer.tobytes()
        
        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n')

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
@employee_required
def video_feed_register():
    return Response(generate_frames(mirror_preview=True, recognition_interval=8, jpeg_quality=70),
                   mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route('/mark_attendance', methods=['POST'])
@login_required
def mark_attendance():
    global camera
    if camera is None:
        return jsonify({'success': False, 'message': 'Camera not initialized'})
    
    # Capture current frame
    success, frame = camera.read()
    if not success:
        return jsonify({'success': False, 'message': 'Failed to capture frame'})
    
    # Recognize faces
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
        save_attendance(user_id, confidence)
        return jsonify({'success': True, 'message': f'Attendance marked successfully! (Confidence: {confidence:.2f})'})
    else:
        return jsonify({'success': False, 'message': 'Face not recognized. Please ensure your face is clearly visible.'})

@app.route('/mark_attendance_with_photo', methods=['POST'])
@login_required
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
            save_attendance(user_id, confidence)
            return jsonify({'success': True, 'message': f'Attendance marked successfully! (Confidence: {confidence:.2f})'})
        else:
            return jsonify({'success': False, 'message': 'Face not recognized. Please ensure your face is clearly visible.'})
    
    return jsonify({'success': False, 'message': 'Invalid file format'})

@app.route('/get_attendance_stats')
@login_required
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
        'total_records': len(records)
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
    app.run(debug=True, threaded=True)