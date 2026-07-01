# Smart Facial Attendance Management System

A Flask-based facial attendance platform for colleges with student approval, face verification, policy-driven check-in/check-out, late classification, attendance analytics, low-attendance alerts, and CSV reporting.

## Features

- Student registration and admin approval
- Face registration (image upload) and face encoding storage
- Real-time webcam face verification
- One daily attendance lifecycle per student
- Automatic check-in and check-out
- Duplicate attendance prevention
- Automatic on-time or late classification
- Monthly attendance percentage and absence calculation
- Low-attendance alerts based on an admin-defined threshold
- Parent portal for read-only linked student tracking
- Admin-defined reporting time and monthly working days
- CSV attendance report export
- Redesigned student, parent, and admin interfaces

## Requirements

- Python 3.8+
- See requirements.txt for Python packages
- sqlite3 is part of Python standard library and should not be installed separately
- On Windows, dlib installation may require Visual C++ Build Tools; prebuilt wheels are recommended when available

## Quick Setup (Windows PowerShell)

1. Open terminal in this project folder.
2. Create and activate a virtual environment:

```powershell
python -m venv .venv
& 
.venv\Scripts\Activate.ps1
```

3. Install dependencies:

```powershell
pip install -r requirements.txt
```

4. Run the app:

```powershell
& .venv\Scripts\python.exe app.py
```

5. Open in browser:

http://127.0.0.1:5000

## Default Admin Account

The app creates a default admin user on first run:

- Username: admin
- Password: admin123

Use this account to approve pending students in the Admin Dashboard.

## Default Parent Account

The app also creates a demo parent user on first run:

- Username: parent
- Password: parent123

Admins can create, edit, delete, link, and unlink parent accounts from **Admin Console > Parents**.

## Typical Workflow

1. Student registers on the Registration page.
2. Admin approves the student in the Admin Dashboard.
3. Admin creates or links a parent account from the Parents page when parent tracking is needed.
4. Student logs in and uploads a clear front-facing photo in Register Face.
5. Student checks in using live face verification.
6. The system classifies the check-in as on time or late.
7. The next successful scan records check-out.
8. Parent logs in to view linked student profile details, today's attendance, monthly summary, and attendance history.
9. Additional scans on the same day are blocked as duplicates.

## Attendance Policy

The admin dashboard allows administrators to configure:

- Reporting time, such as `09:15`
- Low-attendance threshold, such as `75%`
- Number of working days in the current month

Monthly reports include present days, late days, absent days, completed check-outs, and attendance percentage.

## CSV Reports

Administrators can use **Export CSV** on the admin dashboard to download the current monthly attendance report.

## Files and Storage

- Database: attendance.db (SQLite) in project root
- Face encodings: stored as pickled blobs in face_encodings table
- Uploaded images: static/uploads

## Troubleshooting

- If face-recognition or dlib install fails on Windows, install Visual C++ Build Tools or use a compatible prebuilt wheel for dlib
- Ensure webcam access is available and not locked by another application
- If Python command is not found, install Python and re-open terminal

## Notes

- This project runs with Flask development server
- Do not use this setup directly in production without security hardening (secret key, WSGI server, HTTPS, etc.)
