from flask import Blueprint, request, jsonify
import os
import sqlite3
from datetime import datetime
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import pytz  # For timezone handling

from database import DATABASE
from face_service import recognize_face

attendance_bp = Blueprint("attendance", __name__)

# Helper to get current Indian Time
def get_india_now():
    return datetime.now(pytz.timezone('Asia/Kolkata'))

def send_notification_email(employee_name, employee_id, department, date, late_minutes):
    sender_email = os.getenv("ATTENDANCE_SMTP_USER", "").strip()
    sender_password = os.getenv("ATTENDANCE_SMTP_PASSWORD", "").strip()
    receiver_email = os.getenv("ATTENDANCE_NOTIFY_EMAIL", "").strip()

    if not sender_email or not sender_password or not receiver_email:
        return

    subject = "New Attendance Marked"
    body = f"""
    Attendance has been marked for:
    Name: {employee_name}
    Employee ID: {employee_id}
    Department: {department}
    Date: {date}
    Late by: {late_minutes} minutes
    """

    msg = MIMEMultipart()
    msg['From'] = sender_email
    msg['To'] = receiver_email
    msg['Subject'] = subject

    msg.attach(MIMEText(body, 'plain'))

    try:
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(sender_email, sender_password)
        text = msg.as_string()
        server.sendmail(sender_email, receiver_email, text)
        server.quit()
        print("Email sent successfully")
    except Exception as e:
        print(f"Failed to send email: {e}")

@attendance_bp.route("/attendance/mark", methods=["POST"])
def mark_attendance():
    data = request.json
    employee_id = data.get("employee_id") or data.get("student_id")
    face_image = data.get("face_image")

    if not employee_id or not face_image:
        return jsonify({"message": "employee_id and face_image are required"}), 400

    recognition = recognize_face(face_image, source="mobile_capture")
    if recognition.get("status") != "matched":
        return jsonify({"message": recognition.get("reason", "Face did not match any employee")})
    matched_employee_id = str(recognition.get("employee_id", "")).strip().lower()
    selected_employee_id = str(employee_id).strip().lower()
    if matched_employee_id != selected_employee_id:
        return jsonify({"message": "Face does not match the selected employee"})

    conn = sqlite3.connect(DATABASE)
    c = conn.cursor()

    c.execute("SELECT * FROM employees WHERE employee_id=?", (employee_id,))
    employee = c.fetchone()

    if employee:
        # Get India Time
        india_now = get_india_now()
        today = india_now.strftime("%Y-%m-%d")

        # Check if already marked today
        c.execute("SELECT * FROM attendance WHERE employee_id=? AND date=?", (employee[2], today))
        existing = c.fetchone()

        if existing:
            conn.close()
            return jsonify({"message": "Attendance already marked for today"})

        login_time = india_now.strftime("%H:%M")
        official_start = datetime.strptime("10:00", "%H:%M").replace(year=india_now.year, month=india_now.month, day=india_now.day)

        # Calculate late minutes based on India time
        actual_login = india_now.replace(tzinfo=None)
        official_start_naive = official_start.replace(tzinfo=None)

        late_minutes = max(0, int((actual_login - official_start_naive).total_seconds() // 60))

        c.execute("""
        INSERT INTO attendance(employee_id,name,department,date,login_time,late_minutes)
        VALUES (?,?,?,?,?,?)
        """,(
            employee[2],
            employee[1],
            employee[3],
            today,
            login_time,
            late_minutes
        ))

        # Store notification for admin
        notification_msg = f"Attendance marked: {employee[1]}, Employee ID: {employee[2]}, Dept: {employee[3]}, Late by {late_minutes}m"
        c.execute("""
        INSERT INTO notifications(employee_name, employee_id, department, date, message)
        VALUES (?, ?, ?, ?, ?)
        """, (
            employee[1],
            employee[2],
            employee[3],
            today,
            notification_msg
        ))

        conn.commit()
        conn.close()

        # Send email notification
        send_notification_email(employee[1], employee[2], employee[3], today, late_minutes)

        return jsonify({"message":"Attendance marked successfully"})
    else:
        conn.close()
        return jsonify({"message":"Invalid employee"})


@attendance_bp.route("/attendance/logout", methods=["POST"])
def logout_attendance():
    data = request.json
    employee_id = data.get("employee_id")

    if not employee_id:
        return jsonify({"message": "employee_id required"}), 400

    india_now = get_india_now()
    conn = sqlite3.connect(DATABASE)
    c = conn.cursor()
    today = india_now.strftime("%Y-%m-%d")

    c.execute(
        "SELECT id FROM attendance WHERE employee_id=? AND date=?",
        (employee_id, today),
    )
    row = c.fetchone()
    if not row:
        conn.close()
        return jsonify({"message": "No login found for today"}), 404

    # get employee details for notification
    c.execute("SELECT name, department FROM employees WHERE employee_id=?", (employee_id,))
    emp = c.fetchone()
    if not emp:
        conn.close()
        return jsonify({"message": "Employee not found"}), 404

    logout_time = india_now.strftime("%H:%M")
    c.execute(
        "UPDATE attendance SET logout_time=? WHERE id=?",
        (logout_time, row[0]),
    )

    notification_msg = f"Logout recorded: {emp[0]}, ID: {employee_id}, Dept: {emp[1]}"
    c.execute(
        """
        INSERT INTO notifications(employee_name, employee_id, department, date, message)
        VALUES (?, ?, ?, ?, ?)
        """,
        (emp[0], employee_id, emp[1], today, notification_msg),
    )

    conn.commit()
    conn.close()
    pretty = datetime.strptime(logout_time, "%H:%M").strftime("%I:%M %p").lstrip("0")
    return jsonify({"message": "Logout time recorded", "logout_time": pretty})

@attendance_bp.route("/attendance/history/<employee_id>", methods=["GET"])
def get_attendance_history(employee_id):
    conn = sqlite3.connect(DATABASE)
    c = conn.cursor()
    c.execute("SELECT * FROM employees WHERE employee_id=?", (employee_id,))
    employee = c.fetchone()
    if not employee:
        conn.close()
        return jsonify({"message": "Employee not found"})

    c.execute("SELECT * FROM attendance WHERE employee_id=? ORDER BY date DESC", (employee_id,))
    records = c.fetchall()
    conn.close()
    def fmt(t):
        if not t:
            return None
        try:
            return datetime.strptime(t, "%H:%M").strftime("%I:%M %p").lstrip("0")
        except Exception:
            return t

    def late_label(minutes):
        m = minutes or 0
        if m < 60:
            return f"{m} mins late" if m > 0 else "On time"
        h = m // 60
        rem = m % 60
        suffix = f" {rem} mins" if rem else ""
        hour_word = "hour" if h == 1 else "hours"
        return f"{h} {hour_word}{suffix} late"

    return jsonify([{
        "id": r[0],
        "employee_id": r[1],
        "name": r[2],
        "department": r[3],
        "date": r[4],
        "login_time": fmt(r[5]),
        "logout_time": fmt(r[6]),
        "late_minutes": r[7],
        "late_label": late_label(r[7]),
    } for r in records])

attendance_routes = attendance_bp
