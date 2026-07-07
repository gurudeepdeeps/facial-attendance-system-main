# Deeps Institute of Technology - Smart Facial Attendance System

A Flask-based college attendance platform for **Deeps Institute of Technology**. The project includes a professional college landing page, role-based login for students, parents, and administrators, face-based attendance, student approval workflows, parent tracking, attendance policy settings, analytics, and CSV reporting.

## Overview

This system is designed for a college environment where:

- Students register, get approved by an admin, upload a face image, and mark attendance.
- Admins manage students, face approval requests, attendance policy, reports, and parent accounts.
- Parents get read-only access to linked student details, attendance status, monthly summary, and attendance history.
- The public home page presents the college brand and links users into the attendance portal.

## Main Features

- Creative college landing page for Deeps Institute of Technology
- Student registration with admin approval
- Separate student, parent, and admin login panels
- Face image submission and admin face approval workflow
- Live webcam face recognition attendance
- Photo upload fallback for attendance marking
- One daily attendance lifecycle per student
- Check-in and check-out tracking
- Duplicate attendance prevention
- On-time or late classification based on reporting time
- Monthly attendance summary
- Low-attendance highlighting
- Admin-configurable reporting time, working days, and threshold
- Admin student search and student detail view
- Parent portal with linked student tracking
- Parent CRUD from admin console
- CSV attendance report export

## Roles

### Student

Students can:

- Register for an account
- Login after admin approval
- Submit or update a face image for admin review
- Mark attendance with live camera verification
- Mark attendance with an uploaded photo
- View today's attendance lifecycle
- View monthly attendance summary
- View attendance history

### Parent

Parents can:

- Login through the parent panel
- View linked students only
- See student profile details
- See today's attendance
- See monthly attendance percentage
- See present, late, absent, and completed day counts
- View attendance history

Parents cannot modify attendance, students, policy settings, or admin data.

### Admin

Admins can:

- Approve or reject student registrations
- View approved, pending, and rejected students
- View student details and attendance history
- Delete students and related attendance/face data
- Approve or reject face image requests
- Search students
- Configure attendance policy
- Export attendance reports as CSV
- Create, update, delete, link, and unlink parent accounts

## Default Accounts

The database creates default accounts on first run.

### Admin

- Username: `admin`
- Password: `admin123`

### Demo Parent

- Username: `parent`
- Password: `parent123`

The demo parent is created automatically, but it must be linked to an approved student from **Admin Console > Parents** before it can show student data.

## Important Pages

| Page | URL |
| --- | --- |
| College landing page | `http://127.0.0.1:5000/` |
| Role login page | `http://127.0.0.1:5000/login` |
| Portal redirect | `http://127.0.0.1:5000/portal` |
| Student registration | `http://127.0.0.1:5000/registration` |
| Student dashboard | `http://127.0.0.1:5000/dashboard` |
| Attendance page | `http://127.0.0.1:5000/attendance` |
| Face registration | `http://127.0.0.1:5000/register_face` |
| Admin dashboard | `http://127.0.0.1:5000/admin_dashboard` |
| Parent management | `http://127.0.0.1:5000/admin_parents` |
| Parent dashboard | `http://127.0.0.1:5000/parent_dashboard` |

## Requirements

- Python 3.8 or newer
- Webcam for live face attendance
- SQLite, included with Python
- Python packages listed in `requirements.txt`

On Windows, `dlib` and `face_recognition` can require Visual C++ Build Tools. If normal installation fails, use a compatible prebuilt wheel for your Python version.

## Setup on Windows PowerShell

Open PowerShell inside this project folder:

```powershell
cd C:\Users\gurud\Downloads\facial-attendance-system-main
```

Create a virtual environment:

```powershell
python -m venv .venv
```

Activate it:

```powershell
.\.venv\Scripts\Activate.ps1
```

Install dependencies:

```powershell
pip install -r requirements.txt
```

Run the app:

```powershell
.\.venv\Scripts\python.exe app.py
```

Open the site:

```text
http://127.0.0.1:5000/
```

## Running Without Activating the Virtual Environment

You can run the app directly with:

```powershell
.\.venv\Scripts\python.exe app.py
```

If you are already inside the virtual environment, this also works:

```powershell
python app.py
```

## Typical Workflow

1. Student opens the registration page and creates an account.
2. Admin logs in with `admin / admin123`.
3. Admin approves the student from the admin dashboard.
4. Student logs in and submits a clear face image.
5. Admin approves the face image request.
6. Student opens the attendance page and marks check-in with face verification.
7. The system classifies attendance as on time or late.
8. Student scans again later to mark check-out.
9. Admin creates or updates parent accounts from **Parents**.
10. Admin links parents to approved students.
11. Parent logs in and tracks linked student details.

## Parent CRUD

Open:

```text
http://127.0.0.1:5000/admin_parents
```

From this page, admins can:

- Create a parent account
- Create a parent with or without an initial student link
- Edit parent name, email, username, and password
- Delete a parent account
- Link a parent to an approved student
- Update the relationship label, such as `Parent`, `Mother`, `Father`, or `Guardian`
- Unlink a student from a parent account

Deleting a parent removes only the parent account and parent-student links. It does not delete students or attendance records.

## Attendance Policy

Admins can configure:

- Reporting time, for example `09:15`
- Low-attendance threshold, for example `75`
- Working days per month, for example `22`

These settings affect:

- On-time or late classification
- Monthly attendance percentage
- Low-attendance warnings
- Admin reports

## Face Registration and Approval

Students do not become immediately face-enabled after uploading an image.

Flow:

1. Student uploads a face image.
2. The system extracts the face encoding.
3. A face approval request is created.
4. Admin reviews the request.
5. If approved, the face becomes active for attendance.
6. If rejected, the uploaded image is removed and not used.

Submitting a new face image creates another approval request. The existing approved face remains active until the new request is approved.

## CSV Reports

Admins can export the current monthly attendance report from the admin dashboard.

The CSV includes:

- Student ID
- Full name
- Username
- Email
- Month
- Working days
- Present days
- Late days
- Absent days
- Completed check-outs
- Attendance percentage
- Low-attendance status

## Project Structure

```text
.
├── app.py                         Flask routes and application entry point
├── database.py                    SQLite schema and data helpers
├── face_utils.py                  Face encoding and recognition helpers
├── requirements.txt               Python dependencies
├── README.md                      Project documentation
├── attendance.db                  SQLite database, created at runtime
├── static/
│   ├── css/style.css              Main styling
│   ├── js/main.js                 Frontend interactions
│   ├── favicon.svg                Site icon
│   ├── images/                    Landing page images
│   └── uploads/                   Uploaded face images
└── templates/
    ├── landing.html               College landing page
    ├── login.html                 Student, parent, and admin login
    ├── registration.html          Student registration
    ├── dashboard.html             Student dashboard
    ├── attendance.html            Attendance marking page
    ├── register_face.html         Face upload page
    ├── parent_dashboard.html      Parent dashboard
    ├── parent_student_details.html Parent student details
    ├── admin_dashboard.html       Admin dashboard
    ├── admin_parents.html         Parent CRUD
    ├── admin_students.html        Student lists
    ├── admin_student_details.html Student details
    ├── admin_face_requests.html   Face approval requests
    └── admin_search_results.html  Student search
```

## Database Tables

The app uses SQLite and creates the needed tables automatically.

Main tables:

- `users`
- `attendance`
- `face_encodings`
- `face_approval_requests`
- `attendance_settings`
- `parent_students`

The `users` table stores admins, students, and parents using the `role` column.

## File Storage

- Database: `attendance.db`
- Uploaded face images: `static/uploads`
- Landing page hero image: `static/images/deeps-campus-hero.png`
- CSS: `static/css/style.css`
- JavaScript: `static/js/main.js`

## Troubleshooting

### Site does not open

Make sure the Flask server is running:

```powershell
.\.venv\Scripts\python.exe app.py
```

Then open:

```text
http://127.0.0.1:5000/
```

### Changes are not showing

Stop old Python processes and restart the app:

```powershell
Get-Process python
Stop-Process -Id <PID> -Force
.\.venv\Scripts\python.exe app.py
```

Then hard refresh the browser with `Ctrl + F5`.

### Port 5000 is already in use

Find the process:

```powershell
netstat -ano | Select-String ":5000"
```

Stop the process by PID:

```powershell
Stop-Process -Id <PID> -Force
```

Start the app again.

### Webcam does not work

- Close other apps that may be using the camera.
- Allow camera permission in Windows privacy settings.
- Try restarting the Flask server.
- Make sure the webcam is connected and working in another app.

### Face recognition dependencies fail to install

On Windows, install Visual C++ Build Tools or use a prebuilt wheel for `dlib`. Make sure your Python version matches the wheel.

### Parent can log in but sees no students

The parent account is not linked to an approved student yet.

Admin steps:

1. Login as admin.
2. Open **Parents**.
3. Use **Link student**.
4. Choose a parent and an approved student.

## Development Notes

- This app uses Flask's development server.
- It is intended for local development and college project demonstration.
- Do not deploy it to production without hardening security.
- Use a strong `FLASK_SECRET_KEY` in production.
- Use HTTPS in production.
- Replace SHA-256 password hashing with a password hashing algorithm such as bcrypt or Argon2 before production use.
- Review file upload, camera, and face recognition security before real deployment.

## Current Status

Implemented modules:

- College landing page
- Student registration and approval
- Student dashboard
- Face approval workflow
- Face attendance marking
- Admin dashboard
- Admin reporting and CSV export
- Parent portal
- Parent CRUD and parent-student linking

The system is ready for local demonstration and further refinement.
