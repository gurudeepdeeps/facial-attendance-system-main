-- ============================================================
-- SJB Institute of Technology — Attendance System
-- Supabase / PostgreSQL Schema
--
-- Run this once in the Supabase SQL Editor:
-- Project → SQL Editor → New query → paste → Run
-- ============================================================

-- Users (students, lecturers, parents, admin)
CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    username TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    full_name TEXT NOT NULL,
    email TEXT UNIQUE NOT NULL,
    role TEXT DEFAULT 'student',
    status TEXT DEFAULT 'pending',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Approved face encodings
CREATE TABLE IF NOT EXISTS face_encodings (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    encoding BYTEA NOT NULL,
    image_path TEXT NOT NULL,   -- Supabase Storage public URL
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Face registration approval queue
CREATE TABLE IF NOT EXISTS face_approval_requests (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    encoding BYTEA NOT NULL,
    image_path TEXT NOT NULL,   -- Supabase Storage public URL
    request_type TEXT NOT NULL, -- 'initial' | 'update'
    status TEXT DEFAULT 'pending',
    requested_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    reviewed_at TIMESTAMP,
    reviewed_by INTEGER REFERENCES users(id)
);

-- Daily attendance records (check-in / check-out per subject)
CREATE TABLE IF NOT EXISTS attendance (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    status TEXT DEFAULT 'present',
    confidence REAL,
    attendance_date TEXT,
    check_in_time TIMESTAMP,
    check_out_time TIMESTAMP,
    check_in_confidence REAL,
    check_out_confidence REAL,
    remarks TEXT,
    subject TEXT DEFAULT 'General'
);

-- Global attendance policy settings (singleton row id=1)
CREATE TABLE IF NOT EXISTS attendance_settings (
    id INTEGER PRIMARY KEY,
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
);

INSERT INTO attendance_settings
    (id, reporting_time, low_attendance_threshold, working_days_per_month)
VALUES (1, '09:15', 75, 22)
ON CONFLICT (id) DO NOTHING;

-- Parent ↔ Student links
CREATE TABLE IF NOT EXISTS parent_students (
    id SERIAL PRIMARY KEY,
    parent_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    student_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    relationship TEXT DEFAULT 'Parent',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(parent_id, student_id)
);

-- Lecturer attendance sessions (open / closed per subject)
CREATE TABLE IF NOT EXISTS attendance_sessions (
    id SERIAL PRIMARY KEY,
    lecturer_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    subject TEXT NOT NULL,
    status TEXT DEFAULT 'open',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    closed_at TIMESTAMP,
    latitude REAL,
    longitude REAL
);

-- Subjects catalogue
CREATE TABLE IF NOT EXISTS subjects (
    id SERIAL PRIMARY KEY,
    name TEXT UNIQUE NOT NULL
);

-- ============================================================
-- IMPORTANT: The default admin account is created automatically
-- by the Flask app on first startup (via init_db()).
-- You do NOT need to insert it manually here.
-- ============================================================
