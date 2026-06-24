# Survey and Feature Enhancement Proposal

## Project Title

Smart Facial Attendance Management System with Admin Approval, Attendance Policy, and Analytics

## Existing System Overview

Many existing attendance systems use one of these approaches:

- Manual attendance registers
- RFID or barcode based attendance
- Biometric fingerprint attendance
- Basic face recognition attendance
- Google Form or LMS based self-attendance

The current project already implements a basic facial attendance workflow:

- Student registration
- Admin approval or rejection
- Face registration
- Face based attendance marking
- Admin dashboard
- Attendance records

However, a basic face attendance system is now common. To make it stronger as a major project, the system should solve practical problems found in real college attendance workflows.

## Problems in Existing Attendance Systems

### 1. Manual Attendance Is Slow and Error-Prone

In classrooms, teachers spend time calling names or passing sheets. This causes loss of lecture time and can introduce human errors.

### 2. Proxy Attendance Is a Common Issue

Manual registers, shared login systems, and simple attendance forms can be misused by another student.

### 3. Basic Face Attendance Can Be Spoofed

Some simple facial attendance systems only compare a face image. If no additional verification exists, a photo or previously captured image may be misused.

### 4. No Proper Attendance Policy

Many systems only store "present" records. They do not clearly classify:

- On time
- Late
- Absent
- Partial day
- Early checkout

This makes the system less useful for real administration.

### 5. Duplicate Attendance Records

If the user marks attendance multiple times in one day, the system may create repeated records instead of maintaining one proper daily attendance lifecycle.

### 6. Weak Reporting

A simple attendance table is not enough for academic or administrative use. Guides, HODs, or admins need:

- Date-wise reports
- Student-wise reports
- Monthly percentage
- Low attendance alerts
- Exportable summaries

### 7. Limited Audit Trail

Existing systems often do not clearly show when attendance was marked, with what confidence score, and whether the record needs review.

### 8. Camera and Lighting Limitations

Face recognition can fail in poor lighting, low camera quality, side pose, mask usage, or multiple faces in one frame.

## Proposed Feature Enhancement

### Feature Name

Attendance Policy and Analytics Module

### Why This Feature?

Instead of only marking attendance, the system will behave like a real institutional attendance management platform. It will classify attendance based on college timing rules, prevent duplicate records, and provide useful analytics to admin.

This directly addresses the guide's concern that the project looks like a mini project.

## Feature Scope

### 1. Check-In and Check-Out Attendance

The user can mark:

- Check-in when arriving
- Check-out when leaving

This creates a proper daily attendance cycle instead of only storing random face recognition entries.

### 2. Duplicate Attendance Prevention

The system should allow only one active attendance record per user per day.

Example:

- If user already checked in today, another check-in should not create a duplicate.
- The system should ask the user to check out instead.

### 3. Late and On-Time Classification

Admin can define a reporting time, for example:

- On time: before 09:15 AM
- Late: after 09:15 AM

The system automatically marks the attendance status.

### 4. Monthly Attendance Percentage

Admin dashboard should show:

- Total working days
- Present days
- Late days
- Absent days
- Attendance percentage

### 5. Low Attendance Alert

If a student's monthly attendance is below a threshold such as 75%, the system should highlight them in the admin dashboard.

### 6. Attendance Report Export

Admin should be able to export attendance reports as CSV for academic records.

## Survey Questions

Use these questions to collect feedback from students, faculty, or admin staff.

### For Students

1. Which attendance method is currently used in your class or department?
2. How much time is usually spent on attendance in one lecture?
3. Have you faced incorrect attendance marking?
4. Do you think face recognition attendance can reduce proxy attendance?
5. What problem do you expect in face based attendance?
6. Would you prefer check-in/check-out based attendance?
7. Should the system show your monthly attendance percentage?
8. Should the system notify students when attendance goes below 75%?

### For Faculty

1. What is the biggest issue in the current attendance process?
2. How often do proxy attendance cases happen?
3. Is manual attendance difficult to manage for large classes?
4. What reports are required at department level?
5. Should late attendance be tracked separately?
6. Should admins be able to approve or reject student registrations?
7. Is CSV or Excel export useful for official records?
8. What security concern do you see in facial attendance?

### For Admin or HOD

1. What attendance percentage rule is followed in the institution?
2. How often are attendance reports required?
3. Do you need student-wise and date-wise reports?
4. Should low attendance students be highlighted automatically?
5. Should the system store audit details such as time and confidence score?
6. What data should be visible on the admin dashboard?

## Sample Survey Findings

After collecting responses, the findings can be written like this:

- Most users find manual attendance time-consuming.
- Faculty members need monthly attendance reports.
- Students want visibility of their own attendance percentage.
- Admin staff need exportable reports for official records.
- Duplicate attendance and proxy attendance are major concerns.
- A basic face recognition system is useful, but it needs policy-based reporting to be practical.

## Proposed System Advantages

- Reduces manual attendance effort
- Reduces proxy attendance
- Stores structured check-in and check-out records
- Automatically identifies late attendance
- Prevents duplicate daily attendance
- Provides admin-level attendance analytics
- Helps identify low attendance students early
- Makes the project more useful for real college deployment

## Future Scope

- Liveness detection to reduce photo spoofing
- Location based attendance inside campus
- Email or SMS alerts for low attendance
- Subject-wise attendance
- Timetable integration
- Mobile app support
- QR plus face based two-factor attendance

## Recommended Major Project Upgrade

The most suitable feature to add now is:

**Attendance Policy and Analytics Module with check-in/check-out, late marking, duplicate prevention, percentage calculation, low attendance alert, and CSV report export.**

This feature is practical, easy to explain in viva, and clearly shows the difference between a mini project and a major project.
