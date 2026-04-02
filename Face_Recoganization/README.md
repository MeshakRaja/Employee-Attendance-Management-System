# Face Attendance Module

This project contains the face-recognition part of the attendance system. It supports:

- live webcam enrollment
- face validation
- one-face-only detection
- embedding extraction
- face matching
- attendance marking
- local data storage in SQLite

## How It Works

### Enrollment flow

1. Open the webcam.
2. Capture 5 face samples for one employee.
3. Validate each sample before accepting it.
4. Generate and store embeddings for all 5 samples.
5. Link the embeddings to the employee record.

### Recognition flow

1. Open the webcam.
2. Detect exactly one face.
3. Extract the face embedding.
4. Compare it against all enrolled embeddings.
5. Return the best match and confidence.
6. If valid, mark attendance.

## Attendance Rules

- First valid recognition of the day becomes `check_in`.
- Second valid recognition of the same day becomes `check_out`.
- Very fast repeated scans are blocked as duplicate attempts.
- By default:
  - duplicate window = `5` minutes
  - minimum gap before checkout = `30` minutes
  - match threshold = `0.82`

### What happened in your test

Your output shows the system is working correctly:

- `camera-enroll` completed and stored 5 valid samples for `EMP001`.
- First `camera-recognize` matched `Alice` and marked `check_in`.
- Second immediate `camera-recognize` matched `Alice` again, but attendance was rejected because it was inside the duplicate window.

That means the recognition is correct and the attendance protection rules are also correct.

## Project Files

### Main files

- `manage_face_attendance.py`: command-line entry point
- `face_attendance/config.py`: thresholds and camera settings
- `face_attendance/engine.py`: detection, validation, embedding extraction
- `face_attendance/service.py`: enrollment, matching, attendance logic
- `face_attendance/camera.py`: live webcam enrollment and live recognition
- `face_attendance/database.py`: SQLite tables and persistence

### Data files created at runtime

- `attendance_face.db`: SQLite database
- `captures/enrollment/<employee_id>/`: saved enrollment photos
- `captures/recognitions/<yyyy-mm-dd>/`: saved recognition snapshots

## Requirements

Install inside a virtual environment:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Current Python dependencies:

- `numpy`
- `opencv-contrib-python`

## Optional Better Face Models

For better landmark-based angle approval, place these files in `models/`:

- `models/face_detection_yunet_2023mar.onnx`
- `models/face_recognition_sface_2021dec.onnx`

If they are not present, the app still works using the OpenCV Haar + HOG fallback. In that fallback mode:

- validation still works
- enrollment still works
- recognition still works
- side-angle approval may need manual capture with `C` or `Space`

## First-Time Setup

Initialize the database:

```bash
python3 manage_face_attendance.py init-db
```

Expected result:

```json
{
  "status": "ok",
  "database": "attendance_face.db"
}
```

## Full Run Instructions

### 1. Enroll an employee from the live camera

```bash
python3 manage_face_attendance.py camera-enroll \
  --employee-id EMP001 \
  --full-name "Alice" \
  --camera-index 0
```

What to do on screen:

- keep only one face visible
- keep the face inside the guide box
- look straight for front capture
- turn slightly left, right, up, and down for the remaining samples
- press `Q` or `Esc` to cancel

### Enrollment controls

- Auto capture happens when the frame is good enough.
- If ONNX models are missing, front capture can still be automatic.
- For other angles in fallback mode, press `C` or `Space` to capture the current valid frame manually.

### Successful enrollment output

You already got a valid result like this:

- 5 images saved in `captures/enrollment/EMP001/`
- 5 embeddings stored in the database
- employee linked as `EMP001`

Example saved files:

- `captures/enrollment/EMP001/01_front.jpg`
- `captures/enrollment/EMP001/02_left.jpg`
- `captures/enrollment/EMP001/03_right.jpg`
- `captures/enrollment/EMP001/04_up.jpg`
- `captures/enrollment/EMP001/05_down.jpg`

### 2. Run live recognition for attendance

```bash
python3 manage_face_attendance.py camera-recognize --camera-index 0
```

What happens:

- webcam opens
- face is scanned
- if a valid match is found, the command closes after saving the result
- a recognition image is stored in `captures/recognitions/<date>/`
- the attendance action is written into the database

Example output:

```json
{
  "status": "completed",
  "message": "Alice: Attendance marked successfully.",
  "image_path": "captures/recognitions/2026-03-17/EMP001_130257.jpg",
  "recognition": {
    "status": "matched",
    "employee_id": "EMP001",
    "full_name": "Alice",
    "similarity": 0.9099,
    "confidence": 0.7497,
    "attendance": {
      "status": "marked",
      "action": "check_in"
    }
  }
}
```

## How To Capture Check-In And Check-Out

### Check-in

Run this once when the employee arrives:

```bash
python3 manage_face_attendance.py camera-recognize --camera-index 0
```

If it is the first valid recognition for that employee on that day, the result will be:

- `attendance.action = "check_in"`

### Check-out

Run the same command again later:

```bash
python3 manage_face_attendance.py camera-recognize --camera-index 0
```

If:

- the employee already has a `check_in` for today
- the duplicate window has passed
- the minimum checkout gap has passed

then the result will be:

- `attendance.action = "check_out"`

### Why your second attempt was blocked

Your second scan returned:

- `Rapid duplicate recognition blocked.`

That means recognition matched the same face correctly, but the attendance logic refused to mark another action too quickly.

## Quick Testing Check-Out

By default, checkout requires a `30` minute gap after check-in. For fast testing, temporarily reduce the timing:

```bash
python3 manage_face_attendance.py update-settings \
  --duplicate-window 0 \
  --min-checkout-gap 0 \
  --match-threshold 0.82
```

Then:

1. run `camera-recognize` once for check-in
2. run `camera-recognize` again for check-out

To restore the normal default rules:

```bash
python3 manage_face_attendance.py update-settings \
  --duplicate-window 5 \
  --min-checkout-gap 30 \
  --match-threshold 0.82
```

## Manual Commands

### Validate a single image

```bash
python3 manage_face_attendance.py validate --image /path/to/photo.jpg
```

### Enroll from 5 already captured images

```bash
python3 manage_face_attendance.py enroll \
  --employee-id EMP001 \
  --full-name "Alice" \
  --sample captures/enrollment/EMP001/01_front.jpg \
  --sample captures/enrollment/EMP001/02_left.jpg \
  --sample captures/enrollment/EMP001/03_right.jpg \
  --sample captures/enrollment/EMP001/04_up.jpg \
  --sample captures/enrollment/EMP001/05_down.jpg
```

### Recognize from a single image

```bash
python3 manage_face_attendance.py recognize --image /path/to/frame.jpg --source webcam
```

## Where Data Is Collected

### Enrollment data

- stored photos: `captures/enrollment/<employee_id>/`
- embeddings: `face_embeddings` table in `attendance_face.db`
- employee details: `employees` table in `attendance_face.db`

### Recognition data

- saved snapshots: `captures/recognitions/<date>/`
- attendance records: `attendance_events` table
- timing rules: `attendance_settings` table

## How To View The Collected Data

If `sqlite3` is available, you can inspect the database:

```bash
sqlite3 attendance_face.db
```

Inside sqlite:

```sql
.tables
SELECT * FROM employees;
SELECT event_id, employee_id, event_date, event_type, confidence, similarity, captured_at FROM attendance_events;
SELECT * FROM attendance_settings;
```

Exit sqlite:

```sql
.quit
```

## Meaning Of Important Output Fields

- `similarity`: how close the live face is to the enrolled data
- `confidence`: normalized score shown for easier understanding
- `threshold`: minimum similarity needed for a valid match
- `attendance.status = marked`: attendance was written
- `attendance.status = rejected`: face matched, but attendance rule blocked the action
- `attendance.action = check_in`: first successful attendance event of the day
- `attendance.action = check_out`: second successful attendance event of the day

## Common Messages

- `Attendance marked successfully.`: valid attendance event saved
- `Rapid duplicate recognition blocked.`: same person scanned too soon
- `Check-out attempted too soon after check-in.`: recognized correctly, but checkout gap not met
- `More than one face detected.`: only one face is allowed
- `No face detected.`: no usable face in frame
- `Face image is too blurry.`: move less or improve focus

## GUI Warning Notes

These messages are usually harmless on Linux desktop setups:

- `Ignoring XDG_SESSION_TYPE=wayland on Gnome`
- `QFontDatabase: Cannot find font directory ...`

They come from OpenCV's Qt window backend. They do not stop enrollment or recognition if the camera window still opens and works.

## Current Verified Result

This module has already been verified with your local run:

- live enrollment completed
- 5 samples accepted
- face matched successfully
- first attendance marked as `check_in`
- duplicate protection blocked the immediate second scan

That means the complete face-recognition attendance flow is working end to end.
