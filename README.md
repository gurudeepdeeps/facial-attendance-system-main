# Facial Attendance System

A simple Flask-based facial recognition attendance system that lets employees register, upload a face image, and mark attendance via webcam or photo upload. Includes an admin dashboard to approve or reject employees and view attendance.

## Features

- Employee registration and admin approval
- Face registration (image upload) and face encoding storage
- Real-time webcam attendance (MJPEG video feed)
- Photo-based attendance marking
- Admin dashboard with approve or reject actions, search, and stats

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

Use this account to approve pending users in the Admin Dashboard.

## Typical Workflow

1. User registers on the Registration page.
2. Admin approves the user in the Admin Dashboard.
3. User logs in and uploads a clear front-facing photo in Register Face.
4. User marks attendance from Attendance page using webcam or photo upload.

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
