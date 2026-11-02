import os
import datetime
from dotenv import load_dotenv
load_dotenv()
from werkzeug.utils import secure_filename
from flask import Flask, render_template, request, redirect, url_for, session, g, flash
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from flask import send_file
import io

def format_time_value(val):
    if val is None:
        return ""
    if isinstance(val, datetime.timedelta):
        total_seconds = int(val.total_seconds())
        hours = (total_seconds // 3600) % 24
        minutes = (total_seconds % 3600) // 60
        period = "AM" if hours < 12 else "PM"
        display_hour = hours % 12
        if display_hour == 0:
            display_hour = 12
        return f"{display_hour:02d}:{minutes:02d} {period}"
    if isinstance(val, datetime.time):
        period = "AM" if val.hour < 12 else "PM"
        display_hour = val.hour % 12
        if display_hour == 0:
            display_hour = 12
        return f"{display_hour:02d}:{val.minute:02d} {period}"
    return str(val)

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY")

import mysql.connector

# Database Configuration
DB_HOST = os.environ.get("DB_HOST", "localhost")
DB_USER = os.environ.get("DB_USER", "root")
DB_PASSWORD = os.environ.get("DB_PASSWORD")
DB_NAME = os.environ.get("DB_NAME", "erp")
def ensure_columns():
    try:
        conn = mysql.connector.connect(
            host=DB_HOST,
            user=DB_USER,
            password=DB_PASSWORD,
            database=DB_NAME,
            charset='utf8mb4'
        )
        cur = conn.cursor()
        cur.execute("SHOW COLUMNS FROM certificate_request LIKE 'rejection_reason'")
        if not cur.fetchone():
            cur.execute("ALTER TABLE certificate_request ADD COLUMN rejection_reason TEXT DEFAULT NULL")
            conn.commit()

        cur.execute("SHOW COLUMNS FROM scholarship LIKE 'community_cert'")
        if not cur.fetchone():
            cur.execute("ALTER TABLE scholarship ADD COLUMN community_cert VARCHAR(255) DEFAULT NULL")
            conn.commit()

        cur.execute("SHOW COLUMNS FROM scholarship LIKE 'income_cert'")
        if not cur.fetchone():
            cur.execute("ALTER TABLE scholarship ADD COLUMN income_cert VARCHAR(255) DEFAULT NULL")
            conn.commit()
        cur.close()
        conn.close()
    except Exception as e:
        print("[DB INIT CHECK]", e)

ensure_columns()

def get_db():
    if 'db' not in g:
        g.db = mysql.connector.connect(
            host=DB_HOST,
            user=DB_USER,
            password=DB_PASSWORD,
            database=DB_NAME,
            charset='utf8mb4'
        )
    return g.db

def get_cursor():
    if 'cursor' not in g:
        g.cursor = get_db().cursor(dictionary=True)
    return g.cursor

@app.teardown_appcontext
def teardown_db(exception):
    db = g.pop('db', None)
    cursor = g.pop('cursor', None)
    if cursor is not None:
        try:
            cursor.close()
        except Exception:
            pass
    if db is not None:
        try:
            db.close()
        except Exception:
            pass

def create_system_notification(title, message, target_role="ALL", target_regno=None, recipient_email=None):
    try:
        cursor = get_cursor()
        cursor.execute("""
            INSERT INTO notifications (title, message, notification_date, target_role, target_regno)
            VALUES (%s, %s, CURDATE(), %s, %s)
        """, (title, message, target_role, target_regno))
        get_db().commit()
        safe_title = title.encode('ascii', 'replace').decode('ascii')
        print(f"[NOTIFICATION CREATED] {safe_title} (Role: {target_role}, RegNo: {target_regno})")
    except Exception as e:
        print(f"[NOTIFICATION ERROR] {e}")

    # Simulated / configured email notification
    if recipient_email:
        safe_title = title.encode('ascii', 'replace').decode('ascii')
        print(f"[EMAIL ALERT] Sent to: {recipient_email} | Subject: {safe_title}")

@app.route("/")
def home():
    return render_template("index.html")


@app.before_request
def restrict_access():

    print("PATH =", request.path)

    # Allow static assets and public pages
    if request.path.startswith('/static') or request.path in ['/', '/login', '/student-login', '/staff-login', '/logout', '/student-logout', '/staff-logout','/gps-test']:
        return None

    student_routes = [
    '/student-dashboard',
    '/apply-certificate',
    '/my-certificate-requests',
    '/apply-scholarship',
    '/submit-scholarship',
    '/my-scholarship',
    '/student-timetable',
    '/student-attendance',
    '/student-exam-timetable',
    '/student-circular',
    '/student-events',
    '/student-profile',
    '/student-notification',
    '/submit-certificate',
    '/digital-locker',
    '/download-certificate',
    '/upload-document',
]
    # Staff routes
    staff_routes = [
    '/staff-dashboard',
    '/staff-students',
    '/staff-timetable',
    '/staff-exam-timetable',
    '/staff-attendance',
    '/save-attendance',
    '/staff-view-attendance',
    '/staff-circulars',
    '/staff-notifications',
    '/staff-profile',
    '/staff-logout'
]

    is_student_route = any(request.path.startswith(r) for r in student_routes)
    is_staff_route = any(request.path.startswith(r) for r in staff_routes)

    if is_student_route:
        if 'reg_no' not in session:
            flash("Please login as a student first.", "warning")
            return redirect(url_for('student_login'))
    elif is_staff_route:
        if 'staff_id' not in session:
            flash("Please login as a staff member first.", "warning")
            return redirect(url_for('staff_login'))
    else:
        # Admin routes
        if not session.get('admin_logged_in'):
            flash("Please login as administrator first.", "warning")
            return redirect(url_for('login'))

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]

        if username == "admin" and password == "1234":
            session["admin_logged_in"] = True
            flash("Welcome, Administrator!", "success")
            return redirect(url_for("dashboard"))
        else:
            flash("Invalid Username or Password.", "danger")
            return redirect(url_for("login"))

    return render_template("admin_login.html")

@app.route("/logout")
def logout():
    session.clear()
    flash("Admin logged out successfully.", "info")
    return redirect(url_for("home"))

@app.route("/student-login", methods=["GET", "POST"])
def student_login():
    if request.method == "POST":
        reg_no = request.form["reg_no"]
        password = request.form["password"]

        cursor = get_cursor()
        cursor.execute(
            "SELECT * FROM student WHERE reg_no=%s AND password=%s",
            (reg_no, password)
        )
        student = cursor.fetchone()

        if student:
            session["reg_no"] = student["reg_no"]
            session["student_name"] = student["student_name"]
            session["department"] = student["department"]
            print("Department =", session["department"])
            flash(f"Welcome back, {student['student_name']}!", "success")
            return redirect("/student-dashboard")
        else:
            flash("Invalid Register Number or Password.", "danger")
            return redirect(url_for("student_login"))

    return render_template("student_login.html")

@app.route("/student-logout")
def student_logout():
    session.clear()
    flash("Student logged out successfully.", "info")
    return redirect(url_for("home"))
        

@app.route("/student-dashboard")
def student_dashboard():
    cursor = get_cursor()
    reg_no = session.get("reg_no")

    # Check for approved certificate for THIS student ONLY
    cursor.execute("""
        SELECT * FROM certificate_request
        WHERE student_regno = %s AND status = 'Approved'
        ORDER BY request_id DESC LIMIT 1
    """, (reg_no,))
    approved_cert = cursor.fetchone()

    # Check for rejected certificate for THIS student ONLY
    cursor.execute("""
        SELECT * FROM certificate_request
        WHERE student_regno = %s AND status = 'Rejected'
        ORDER BY request_id DESC LIMIT 1
    """, (reg_no,))
    rejected_cert = cursor.fetchone()

    # If both exist, show the one with the higher request_id (most recent decision)
    if approved_cert and rejected_cert:
        if approved_cert["request_id"] > rejected_cert["request_id"]:
            rejected_cert = None
        else:
            approved_cert = None

    # Get notification count for THIS student ONLY
    cursor.execute("""
        SELECT COUNT(*) AS total FROM notifications
        WHERE (target_role IN ('ALL', 'STUDENT') AND target_regno IS NULL)
           OR (target_regno = %s)
    """, (reg_no,))
    notif_row = cursor.fetchone()
    notif_count = notif_row["total"] if notif_row else 0

    return render_template(
        "student_dashboard.html",
        student_name=session.get("student_name", "Student"),
        approved_cert=approved_cert,
        rejected_cert=rejected_cert,
        notif_count=notif_count
    )
@app.route("/student-timetable")
def student_timetable():

    if "reg_no" not in session:
        return redirect(url_for("student_login"))

    cursor = get_cursor()

    cursor.execute("""
        SELECT
            st.student_id,
            st.department,
            st.course_code,
            st.semester,
            st.section,
            st.student_name
        FROM student st
        WHERE st.reg_no = %s
    """, (session["reg_no"],))

    student = cursor.fetchone()

    if not student:
        flash("Student details not found.", "danger")
        return redirect(url_for("student_dashboard"))

    # Determine today's day order from calendar
    cursor.execute("""
        SELECT day_order
        FROM day_order_calendar
        WHERE timetable_date = CURDATE()
    """)

    today = cursor.fetchone()

    if today and today.get("day_order"):
        today_day_order = today["day_order"]
    else:
        # Fallback / Auto-assignment: determine by weekday (Monday=1 .. Friday=5)
        weekday = datetime.date.today().weekday()
        if weekday == 6:  # Sunday
            today_day_order = 1
        else:
            today_day_order = (weekday % 5) + 1

        try:
            cursor.execute("""
                INSERT INTO day_order_calendar (timetable_date, day_order)
                VALUES (CURDATE(), %s)
                ON DUPLICATE KEY UPDATE day_order = %s
            """, (today_day_order, today_day_order))
            get_db().commit()
        except Exception:
            pass

    # Allow student to view any Day Order via ?day_order=1..6
    req_day_order = request.args.get("day_order", type=int)
    if req_day_order and req_day_order in [1, 2, 3, 4, 5, 6]:
        active_day_order = req_day_order
    else:
        active_day_order = today_day_order

    dept = student["department"] or ""
    course = student["course_code"] or dept
    semester = student["semester"] or 3
    section = student["section"] or "A"

    # Fetch available day orders for student's class
    cursor.execute("""
        SELECT DISTINCT day_order
        FROM day_order_timetable
        WHERE (dept_code = %s OR course_code = %s)
          AND semester = %s
          AND section = %s
        ORDER BY day_order
    """, (dept, course, semester, section))
    order_rows = cursor.fetchall()
    available_day_orders = [r["day_order"] for r in order_rows] if order_rows else [1, 2, 3, 4, 5]

    cursor.execute("""
        SELECT 
            dt.day_order, 
            dt.period_no, 
            dt.start_time, 
            dt.end_time, 
            dt.subject_code, 
            s.subject_name, 
            stf.staff_name,
            a.status AS attendance_status
        FROM day_order_timetable dt

        LEFT JOIN subject s
            ON dt.subject_code = s.subject_code

        LEFT JOIN staff stf
            ON dt.staff_id = stf.staff_id

        LEFT JOIN attendance a
            ON a.student_id = %s
           AND a.attendance_date = CURDATE()
           AND a.period_no = dt.period_no

        WHERE (dt.dept_code = %s OR dt.course_code = %s)
          AND dt.semester = %s
          AND dt.section = %s
          AND dt.day_order = %s

        ORDER BY dt.period_no
    """, (student["student_id"], dept, course, semester, section, active_day_order))

    raw_timetable = cursor.fetchall()

    timetable = []
    for row in raw_timetable:
        r = dict(row)
        r["start_time_fmt"] = format_time_value(row["start_time"])
        r["end_time_fmt"] = format_time_value(row["end_time"])
        timetable.append(r)

    today_str = datetime.date.today().strftime("%A, %d %B %Y")

    return render_template(
        "student_timetable.html",
        timetable=timetable,
        today_day_order=today_day_order,
        active_day_order=active_day_order,
        available_day_orders=available_day_orders,
        day_order=active_day_order,
        today_str=today_str,
        student=student
    )

@app.route("/student-attendance")
def student_attendance():
    if "reg_no" not in session:
        return redirect(url_for("student_login"))

    cursor = get_cursor()

    cursor.execute("""
        SELECT
            st.student_id,
            st.reg_no,
            st.student_name,
            st.department,
            st.course_code,
            st.semester,
            st.section
        FROM student st
        WHERE st.reg_no = %s
    """, (session["reg_no"],))

    student = cursor.fetchone()
    if not student:
        flash("Student record not found.", "danger")
        return redirect(url_for("student_dashboard"))

    # Fetch all attendance records for this student
    cursor.execute("""
        SELECT
            a.attendance_id,
            a.attendance_date,
            a.period_no,
            a.status,
            a.subject_code,
            COALESCE(s.subject_name, a.subject_code) AS subject_name,
            COALESCE(stf.staff_name, 'Faculty') AS staff_name
        FROM attendance a
        LEFT JOIN subject s ON a.subject_code = s.subject_code
        LEFT JOIN staff stf ON a.staff_id = stf.staff_id
        WHERE a.student_id = %s
        ORDER BY a.attendance_date DESC, a.period_no DESC
    """, (student["student_id"],))

    records = cursor.fetchall()

    total_classes = len(records)
    total_present = sum(1 for r in records if r["status"] == "Present")
    total_absent = sum(1 for r in records if r["status"] == "Absent")
    overall_percentage = round((total_present / total_classes * 100), 1) if total_classes > 0 else 0.0

    # Month-wise breakdown
    from collections import defaultdict
    month_data = defaultdict(lambda: {"total": 0, "present": 0, "absent": 0, "month_name": "", "year": 0, "month": 0})

    for r in records:
        ad = r["attendance_date"]
        if ad:
            key = (ad.year, ad.month)
            month_data[key]["total"] += 1
            if r["status"] == "Present":
                month_data[key]["present"] += 1
            else:
                month_data[key]["absent"] += 1
            m_name = ad.strftime("%B %Y")
            if ad.month == 6 and ad.year == 2026:
                m_name = "June 2026 (College Reopened June 25)"
            month_data[key]["month_name"] = m_name
            month_data[key]["year"] = ad.year
            month_data[key]["month"] = ad.month

    # Sort months descending
    sorted_months = sorted(month_data.keys(), reverse=True)
    monthly_breakdown = []
    for k in sorted_months:
        m = month_data[k]
        pct = round((m["present"] / m["total"] * 100), 1) if m["total"] > 0 else 0.0
        monthly_breakdown.append({
            "month_name": m["month_name"],
            "total": m["total"],
            "present": m["present"],
            "absent": m["absent"],
            "percentage": pct
        })

    # Subject-wise breakdown
    sub_data = defaultdict(lambda: {"total": 0, "present": 0, "absent": 0, "subject_name": ""})
    for r in records:
        sc = r["subject_code"] or "General"
        sub_data[sc]["total"] += 1
        sub_data[sc]["subject_name"] = r["subject_name"]
        if r["status"] == "Present":
            sub_data[sc]["present"] += 1
        else:
            sub_data[sc]["absent"] += 1

    subject_breakdown = []
    for sc, data in sorted(sub_data.items()):
        pct = round((data["present"] / data["total"] * 100), 1) if data["total"] > 0 else 0.0
        subject_breakdown.append({
            "subject_code": sc,
            "subject_name": data["subject_name"],
            "total": data["total"],
            "present": data["present"],
            "absent": data["absent"],
            "percentage": pct
        })

    return render_template(
        "student_attendance.html",
        student=student,
        total_classes=total_classes,
        total_present=total_present,
        total_absent=total_absent,
        overall_percentage=overall_percentage,
        monthly_breakdown=monthly_breakdown,
        subject_breakdown=subject_breakdown,
        records=records
    )

@app.route("/staff-exam-timetable")
def staff_exam_timetable():
    if "staff_id" not in session:
        return redirect(url_for("staff_login"))

    cursor = get_cursor()

    selected_class = request.args.get("class_code", "BCA")
    if selected_class not in ["BCA", "MCA", "ALL"]:
        selected_class = "BCA"

    # Count badges
    cursor.execute("""
        SELECT
            COUNT(CASE WHEN dept_code = 'BCA' OR course_code = 'BCA' THEN 1 END) AS bca_count,
            COUNT(CASE WHEN dept_code = 'MCA' OR course_code = 'MCA' THEN 1 END) AS mca_count,
            COUNT(*) AS all_count
        FROM exam_timetable
    """)
    counts = cursor.fetchone() or {"bca_count": 0, "mca_count": 0, "all_count": 0}

    if selected_class == "BCA":
        query = """
            SELECT e.exam_id, e.exam_date, e.session, e.hall, e.course_code, e.semester,
                   e.subject_code, COALESCE(s.subject_name, e.subject_code) AS subject_name
            FROM exam_timetable e
            LEFT JOIN subject s ON e.subject_code = s.subject_code
            WHERE e.dept_code = 'BCA' OR e.course_code = 'BCA'
            ORDER BY e.semester, e.exam_date, e.session
        """
        cursor.execute(query)
    elif selected_class == "MCA":
        query = """
            SELECT e.exam_id, e.exam_date, e.session, e.hall, e.course_code, e.semester,
                   e.subject_code, COALESCE(s.subject_name, e.subject_code) AS subject_name
            FROM exam_timetable e
            LEFT JOIN subject s ON e.subject_code = s.subject_code
            WHERE e.dept_code = 'MCA' OR e.course_code = 'MCA'
            ORDER BY e.semester, e.exam_date, e.session
        """
        cursor.execute(query)
    else:
        query = """
            SELECT e.exam_id, e.exam_date, e.session, e.hall, e.course_code, e.semester,
                   e.subject_code, COALESCE(s.subject_name, e.subject_code) AS subject_name
            FROM exam_timetable e
            LEFT JOIN subject s ON e.subject_code = s.subject_code
            ORDER BY e.course_code, e.semester, e.exam_date, e.session
        """
        cursor.execute(query)

    exams = cursor.fetchall()

    return render_template(
        "staff_exam_timetable.html",
        exams=exams,
        selected_class=selected_class,
        counts=counts
    )
@app.route("/department")
def department_list():
    cursor = get_cursor()
    cursor.execute("SELECT * FROM department")

    departments = cursor.fetchall()

    return render_template(
        "department_list.html",
        departments=departments
    )
@app.route("/apply-certificate")
def apply_certificate():

    if "reg_no" not in session:
        return redirect(url_for("student_login"))

    cursor = get_cursor()

    cursor.execute("""
        SELECT reg_no, student_name, department
        FROM student
        WHERE reg_no=%s
    """, (session["reg_no"],))

    student = cursor.fetchone()

    return render_template(
        "apply_certificate.html",
        student=student
    )
@app.route("/my-certificate-requests")
def my_certificate_requests():

    cursor = get_cursor()

    reg_no = session["reg_no"]

    cursor.execute("""
        SELECT *
        FROM certificate_request
        WHERE student_regno=%s
        ORDER BY request_id DESC
    """, (reg_no,))

    requests = cursor.fetchall()

    return render_template(
        "my_certificate_requests.html",
        requests=requests
    )
@app.route("/apply-scholarship")
def apply_scholarship():
    if "reg_no" not in session:
        return redirect(url_for("student_login"))

    cursor = get_cursor()
    reg_no = session.get("reg_no")

    cursor.execute("""
        SELECT reg_no, student_name, department
        FROM student
        WHERE reg_no=%s
    """, (reg_no,))
    student = cursor.fetchone()

    cursor.execute("""
        SELECT id, document_name, file_name, upload_date
        FROM digital_locker
        WHERE student_regno=%s
        ORDER BY id DESC
    """, (reg_no,))
    locker_documents = cursor.fetchall()

    return render_template(
        "apply_scholarship.html",
        student=student,
        locker_documents=locker_documents
    )

@app.route("/submit-scholarship", methods=["POST"])
def submit_scholarship():
    if "reg_no" not in session:
        return redirect(url_for("student_login"))

    reg_no = request.form.get("student_regno") or session.get("reg_no")
    student_name = request.form.get("student_name") or session.get("student_name")
    department = request.form.get("department") or session.get("department")
    scholarship_type = request.form.get("scholarship_type")
    amount = request.form.get("amount")

    cursor = get_cursor()
    cursor.execute(
        "SELECT * FROM scholarship WHERE student_regno=%s",
        (reg_no,)
    )

    already = cursor.fetchone()

    if already:
        flash("You have already applied for a Scholarship.", "warning")
        return redirect(url_for("my_scholarship"))

    # Community Certificate - Locker vs Upload
    community_source = request.form.get("community_cert_source", "locker")
    community_cert_file = None

    if community_source == "locker":
        community_cert_file = request.form.get("community_cert_locker")
    else:
        file = request.files.get("community_cert_upload")
        if file and file.filename != "":
            filename = f"{reg_no}_Community_{secure_filename(file.filename)}"
            upload_path = os.path.join("static", "uploads", filename)
            file.save(upload_path)
            community_cert_file = filename
            cursor.execute("""
                INSERT INTO digital_locker
                (student_regno, student_name, department, document_name, file_name, upload_date)
                VALUES (%s, %s, %s, 'Community Certificate', %s, CURDATE())
            """, (reg_no, student_name, department, filename))

    # Income Certificate - Locker vs Upload
    income_source = request.form.get("income_cert_source", "locker")
    income_cert_file = None

    if income_source == "locker":
        income_cert_file = request.form.get("income_cert_locker")
    else:
        file = request.files.get("income_cert_upload")
        if file and file.filename != "":
            filename = f"{reg_no}_Income_{secure_filename(file.filename)}"
            upload_path = os.path.join("static", "uploads", filename)
            file.save(upload_path)
            income_cert_file = filename
            cursor.execute("""
                INSERT INTO digital_locker
                (student_regno, student_name, department, document_name, file_name, upload_date)
                VALUES (%s, %s, %s, 'Income Certificate', %s, CURDATE())
            """, (reg_no, student_name, department, filename))

    cursor.execute("""
        INSERT INTO scholarship
        (student_regno, student_name, department, scholarship_type, amount, community_cert, income_cert, apply_date, status)
        VALUES (%s,%s,%s,%s,%s,%s,%s,CURDATE(),'Pending')
    """, (reg_no, student_name, department, scholarship_type, amount, community_cert_file, income_cert_file))

    get_db().commit()

    flash("Scholarship Application Submitted Successfully with Attached Certificates!", "success")
    return redirect(url_for("my_scholarship"))

@app.route("/add-department", methods=["GET", "POST"])
def add_department():
    if request.method == "POST":
        dept_code = request.form["dept_code"]
        dept_name = request.form["dept_name"]
        description = request.form["description"]

        sql = "INSERT INTO department (dept_code, dept_name, description) VALUES (%s, %s, %s)"
        values = (dept_code, dept_name, description)

        cursor = get_cursor()
        cursor.execute(sql, values)
        get_db().commit()

        return redirect(url_for("department_list"))

    return render_template("add_department.html")


@app.route("/edit-department/<int:id>", methods=["GET", "POST"])
def edit_department(id):
    cursor = get_cursor()
    cursor.execute("SELECT * FROM department ORDER BY dept_code")
    departments = cursor.fetchall()

    if id < 1 or id > len(departments):
        return redirect(url_for("department_list"))

    department = departments[id - 1]

    if request.method == "POST":
        dept_code = request.form["dept_code"]
        dept_name = request.form["dept_name"]
        description = request.form["description"]

        sql = "UPDATE department SET dept_code=%s, dept_name=%s, description=%s WHERE dept_code=%s"
        values = (dept_code, dept_name, description, department["dept_code"])
        cursor = get_cursor()
        cursor.execute(sql, values)
        get_db().commit()

        return redirect(url_for("department_list"))

    return render_template("edit_department.html", department=department)


@app.route("/delete-department/<int:id>")
def delete_department(id):
    cursor = get_cursor()
    cursor.execute("SELECT * FROM department ORDER BY dept_code")
    departments = cursor.fetchall()

    if id < 1 or id > len(departments):
        return redirect(url_for("department_list"))

    department = departments[id - 1]

    sql = "DELETE FROM department WHERE dept_code=%s"
    cursor.execute(sql, (department["dept_code"],))
    get_db().commit()

    return redirect(url_for("department_list"))


@app.route("/course")
def course_list():
    cursor = get_cursor()
    cursor.execute("SELECT * FROM course")

    courses = cursor.fetchall()

    return render_template(
        "course_list.html",
        courses=courses
    )

@app.route("/add-course", methods=["GET", "POST"])
def add_course():
    cursor = get_cursor()
    cursor.execute("SELECT dept_code FROM department")
    departments = cursor.fetchall()

    if request.method == "POST":

        course_code = request.form["course_code"]
        course_name = request.form["course_name"]
        dept_code = request.form["dept_code"]
        duration = request.form["duration"]

        sql = """
        INSERT INTO course
        (course_code, course_name, dept_code, duration)
        VALUES (%s,%s,%s,%s)
        """

        values = (
            course_code,
            course_name,
            dept_code,
            duration
        )

        cursor = get_cursor()
        cursor.execute(sql, values)
        get_db().commit()

        return redirect(url_for("course_list"))


    return render_template(
        "add_course.html",
        departments=departments
    )


@app.route("/edit-course/<int:id>", methods=["GET", "POST"])
def edit_course(id):
    cursor = get_cursor()
    cursor.execute("SELECT * FROM course ORDER BY course_code")
    courses = cursor.fetchall()

    if id < 1 or id > len(courses):
        return redirect(url_for("course_list"))

    course = courses[id - 1]

    cursor.execute("SELECT dept_code FROM department")
    departments = cursor.fetchall()

    if request.method == "POST":
        course_code = request.form["course_code"]
        course_name = request.form["course_name"]
        dept_code = request.form["dept_code"]
        duration = request.form["duration"]

        sql = """
        UPDATE course
        SET course_code=%s, course_name=%s, dept_code=%s, duration=%s
        WHERE course_code=%s
        """
        values = (course_code, course_name, dept_code, duration, course["course_code"])

        cursor.execute(sql, values)
        get_db().commit()

        return redirect(url_for("course_list"))

    return render_template("edit_course.html", course=course, departments=departments)


@app.route("/delete-course/<int:id>")
def delete_course(id):
    cursor = get_cursor()
    cursor.execute("SELECT * FROM course ORDER BY course_code")
    courses = cursor.fetchall()

    if id < 1 or id > len(courses):
        return redirect(url_for("course_list"))

    course = courses[id - 1]

    sql = "DELETE FROM course WHERE course_code=%s"
    cursor.execute(sql, (course["course_code"],))
    get_db().commit()

    return redirect(url_for("course_list"))


@app.route("/dashboard")
def dashboard():

    cursor = get_cursor()
    cursor.execute("SELECT COUNT(*) AS total FROM department")
    dept_count = cursor.fetchone()["total"]

    cursor.execute("SELECT COUNT(*) AS total FROM course")
    course_count = cursor.fetchone()["total"]

    cursor.execute("SELECT COUNT(*) AS total FROM subject")
    subject_count = cursor.fetchone()["total"]

    cursor.execute("SELECT COUNT(*) AS total FROM staff")
    staff_count = cursor.fetchone()["total"]

    cursor.execute("SELECT COUNT(*) AS total FROM staff_class_mapping")
    mapping_count = cursor.fetchone()["total"]

    cursor.execute("SELECT COUNT(*) AS total FROM exam_timetable")
    exam_count = cursor.fetchone()["total"]

    cursor.execute("SELECT COUNT(*) AS total FROM circular")
    circular_count = cursor.fetchone()["total"]

    cursor.execute("SELECT COUNT(*) AS total FROM events")
    event_count = cursor.fetchone()["total"]

    cursor.execute("SELECT COUNT(*) AS total FROM scholarship")
    scholarship_count = cursor.fetchone()["total"]

    return render_template(
        "dashboard.html",
        dept_count=dept_count,
        course_count=course_count,
        subject_count=subject_count,
        staff_count=staff_count,
        mapping_count=mapping_count,
        exam_count=exam_count,
        circular_count=circular_count,
        event_count=event_count,
        scholarship_count=scholarship_count
    )
@app.route("/staff-mapping")
def staff_mapping_list():
    
    cursor = get_cursor()
    cursor = get_cursor()
    cursor.execute("""
    SELECT
    scm.mapping_id,
    s.staff_id,
    s.staff_name,
    d.dept_name,
    c.course_name,
    sub.subject_name,
    scm.semester,
    scm.section

    FROM staff_class_mapping scm

    JOIN staff s
    ON scm.staff_id = s.staff_id

    JOIN department d
    ON scm.dept_code = d.dept_code

    JOIN course c
    ON scm.course_code = c.course_code

    JOIN subject sub
    ON scm.subject_code = sub.subject_code
    """)

    mappings = cursor.fetchall()

    return render_template(
        "staff_mapping_list.html",
        mappings=mappings
    )
@app.route("/add-staff-mapping", methods=["GET", "POST"])
def add_staff_mapping():
    cursor = get_cursor()
    cursor.execute("SELECT staff_id FROM staff")
    staffs = cursor.fetchall()

    cursor.execute("SELECT dept_code FROM department")
    departments = cursor.fetchall()

    cursor.execute("SELECT course_code FROM course")
    courses = cursor.fetchall()

    cursor.execute("SELECT subject_code FROM subject")
    subjects = cursor.fetchall()

    if request.method == "POST":

        staff_id = request.form["staff_id"]
        dept_code = request.form["dept_code"]
        course_code = request.form["course_code"]
        subject_code = request.form["subject_code"]
        semester = request.form["semester"]
        section = request.form["section"]

        sql = """
        INSERT INTO staff_class_mapping
        (staff_id, dept_code, course_code, subject_code, semester, section)
        VALUES (%s,%s,%s,%s,%s,%s)
        """
        cursor = get_cursor()
        cursor.execute(sql, (
            staff_id,
            dept_code,
            course_code,
            subject_code,
            semester,
            section
        ))
        get_db().commit()

        return redirect(url_for("staff_mapping_list"))

    return render_template(
        "add_staff_mapping.html",
        staffs=staffs,
        departments=departments,
        courses=courses,
        subjects=subjects
    )

@app.route("/student")
def student():

    cursor = get_cursor()
    cursor.execute("SELECT * FROM student")
    students = cursor.fetchall()

    return render_template(
        "student.html",
        students=students
    )
@app.route("/add-student", methods=["GET","POST"])
def add_student():
    cursor = get_cursor()
    cursor.execute("SELECT dept_name FROM department")
    departments = cursor.fetchall()  
    if request.method == "POST":

        reg_no = request.form["reg_no"]
        student_name = request.form["student_name"]
        department = request.form["department"]
        password = request.form["password"]

        cursor.execute("""
        INSERT INTO student
        (reg_no, student_name, department, password)
        VALUES(%s,%s,%s,%s)
        """,(reg_no,student_name,department,password))

        get_db().commit()

        return redirect(url_for("student"))

    return render_template("add_student.html",departments=departments)
@app.route("/edit-student/<int:id>", methods=["GET", "POST"])
def edit_student(id):

    cursor = get_cursor()

    # Current student
    cursor.execute(
        "SELECT * FROM student WHERE student_id=%s",
        (id,)
    )
    student = cursor.fetchone()

    # Department list
    cursor.execute("SELECT dept_name FROM department")
    departments = cursor.fetchall()

    if request.method == "POST":

        student_name = request.form["student_name"]
        department = request.form["department"]
        password = request.form["password"]

        cursor.execute("""
            UPDATE student
            SET
                student_name=%s,
                department=%s,
                password=%s
            WHERE student_id=%s
        """,
        (
            student_name,
            department,
            password,
            id
        ))

        get_db().commit()

        return redirect(url_for("student"))

    return render_template(
        "edit_student.html",
        student=student,
        departments=departments
    )   
@app.route("/delete-student/<reg_no>")
def delete_student(reg_no):

    cursor = get_cursor()

    cursor.execute(
        "DELETE FROM student WHERE reg_no=%s",
        (reg_no,)
    )

    get_db().commit()

    return redirect(url_for("student"))

@app.route("/staff")
def staff_list():


    cursor = get_cursor()
    cursor.execute("SELECT * FROM staff")
    staffs = cursor.fetchall()

    return render_template(
        "staff_list.html",
        staffs=staffs
    )
@app.route("/add-staff", methods=["GET","POST"])
def add_staff():
    cursor = get_cursor()
    if request.method == "POST":

        staff_id = request.form["staff_id"]
        staff_name = request.form["staff_name"]
        department = request.form["department"]
        designation = request.form["designation"]
        mobile = request.form["mobile"]
        password = request.form.get("password", "12345")

        sql = """
        INSERT INTO staff
        (staff_id, staff_name, department, designation, mobile, password)
        VALUES (%s,%s,%s,%s,%s,%s)
        """

        cursor.execute(sql, (staff_id, staff_name, department, designation, mobile, password))
        get_db().commit()

        return redirect(url_for("staff_list"))

    cursor.execute("SELECT dept_code FROM department")
    departments = cursor.fetchall()

    return render_template("add_staff.html", departments=departments)


@app.route("/edit-staff/<int:id>", methods=["GET", "POST"])
def edit_staff(id):
    cursor = get_cursor()
    cursor.execute("SELECT * FROM staff ORDER BY staff_id")
    staffs = cursor.fetchall()

    if id < 1 or id > len(staffs):
        return redirect(url_for("staff_list"))

    staff = staffs[id - 1]

    cursor.execute("SELECT dept_code FROM department")
    departments = cursor.fetchall()

    if request.method == "POST":
        staff_id = request.form["staff_id"]
        staff_name = request.form["staff_name"]
        department = request.form["department"]
        designation = request.form["designation"]
        mobile = request.form["mobile"]
        password = request.form.get("password", "12345")

        sql = """
        UPDATE staff
        SET staff_id=%s, staff_name=%s, department=%s, designation=%s, mobile=%s, password=%s
        WHERE staff_id=%s
        """

        cursor.execute(sql, (staff_id, staff_name, department, designation, mobile, password, staff["staff_id"]))
        get_db().commit()

        return redirect(url_for("staff_list"))

    return render_template("edit_staff.html", staff=staff, departments=departments)


@app.route("/delete-staff/<int:id>")
def delete_staff(id):
    cursor = get_cursor()
    cursor.execute("SELECT * FROM staff ORDER BY staff_id")
    staffs = cursor.fetchall()

    if id < 1 or id > len(staffs):
        return redirect(url_for("staff_list"))

    staff = staffs[id - 1]

    sql = "DELETE FROM staff WHERE staff_id=%s"
    cursor.execute(sql, (staff["staff_id"],))
    get_db().commit()

    return redirect(url_for("staff_list"))


@app.route("/subject")
def subject_list():
    cursor = get_cursor()
    cursor.execute("SELECT * FROM subject")
    subjects = cursor.fetchall()
    return render_template("subject_list.html", subjects=subjects)


@app.route("/add-subject", methods=["GET", "POST"])
def add_subject():
    cursor = get_cursor()
    if request.method == "POST":

        subject_code = request.form["subject_code"]
        subject_name = request.form["subject_name"]
        dept_code = request.form["dept_code"]
        semester = request.form["semester"]

        sql = """
        INSERT INTO subject
        (subject_code, subject_name, dept_code, semester)
        VALUES (%s,%s,%s,%s)
        """

        cursor.execute(sql, (subject_code, subject_name, dept_code, semester))
        get_db().commit()

        return redirect(url_for("subject_list"))

    cursor.execute("SELECT dept_code FROM department")
    departments = cursor.fetchall()

    return render_template("add_subject.html", departments=departments)


@app.route("/edit-subject/<int:id>", methods=["GET", "POST"])
def edit_subject(id):
    cursor = get_cursor()
    cursor.execute("SELECT * FROM subject ORDER BY subject_code")
    subjects = cursor.fetchall()

    if id < 1 or id > len(subjects):
        return redirect(url_for("subject_list"))

    subject = subjects[id - 1]

    cursor.execute("SELECT dept_code FROM department")
    departments = cursor.fetchall()

    if request.method == "POST":
        subject_code = request.form["subject_code"]
        subject_name = request.form["subject_name"]
        dept_code = request.form["dept_code"]
        semester = request.form["semester"]

        sql = """
        UPDATE subject
        SET subject_code=%s, subject_name=%s, dept_code=%s, semester=%s
        WHERE subject_code=%s
        """
        values = (subject_code, subject_name, dept_code, semester, subject["subject_code"])

        cursor.execute(sql, values)
        get_db().commit()

        return redirect(url_for("subject_list"))

    return render_template("edit_subject.html", subject=subject, departments=departments)


@app.route("/delete-subject/<int:id>")
def delete_subject(id):
    cursor = get_cursor()
    cursor.execute("SELECT * FROM subject ORDER BY subject_code")
    subjects = cursor.fetchall()

    if id < 1 or id > len(subjects):
        return redirect(url_for("subject_list"))

    subject = subjects[id - 1]

    sql = "DELETE FROM subject WHERE subject_code=%s"
    cursor.execute(sql, (subject["subject_code"],))
    get_db().commit()

    return redirect(url_for("subject_list"))

@app.route("/exam-timetable")
def exam_timetable_list():
    cursor = get_cursor()
    cursor.execute("""
    SELECT
        et.exam_id,
        d.dept_name,
        c.course_name,
        et.semester,
        s.subject_name,
        et.exam_date,
        et.session,
        et.hall

    FROM exam_timetable et

    JOIN department d
    ON et.dept_code = d.dept_code

    JOIN course c
    ON et.course_code = c.course_code

    JOIN subject s
    ON et.subject_code = s.subject_code
    """)

    timetables = cursor.fetchall()

    return render_template(
        "exam_timetable_list.html",
        timetables=timetables
    )

@app.route("/add-exam-timetable", methods=["GET", "POST"])
def add_exam_timetable():
    cursor = get_cursor()
    cursor.execute("SELECT dept_code, dept_name FROM department")
    departments = cursor.fetchall()

    cursor.execute("SELECT course_code, course_name FROM course")
    courses = cursor.fetchall()

    cursor.execute("SELECT subject_code, subject_name FROM subject")
    subjects = cursor.fetchall()

    if request.method == "POST":

        dept_code = request.form["dept_code"]
        course_code = request.form["course_code"]
        semester = request.form["semester"]
        subject_code = request.form["subject_code"]
        exam_date = request.form["exam_date"]
        session = request.form["session"]
        hall = request.form["hall"]
        cursor = get_cursor()
        cursor.execute("""
        INSERT INTO exam_timetable
        (dept_code, course_code, semester,
        subject_code, exam_date, session, hall)
        VALUES (%s,%s,%s,%s,%s,%s,%s)
        """, (
            dept_code,
            course_code,
            semester,
            subject_code,
            exam_date,
            session,
            hall
        ))

        get_db().commit()

        create_system_notification(
            f"📝 Exam Schedule Published: {course_code} Sem {semester}",
            f"Exam announced for subject code {subject_code} on {exam_date} ({session}) in Hall {hall}."
        )

        return redirect(url_for("exam_timetable_list"))

    return render_template(
        "add_exam_timetable.html",
        departments=departments,
        courses=courses,
        subjects=subjects 
    )

@app.route("/edit-exam-timetable/<int:id>", methods=["GET","POST"])
def edit_exam_timetable(id):

    cursor = get_cursor()
    cursor.execute(
        "SELECT * FROM exam_timetable WHERE exam_id=%s",
        (id,)
    )

    exam = cursor.fetchone()

    if request.method=="POST":

        exam_date=request.form["exam_date"]
        session=request.form["session"]
        hall=request.form["hall"]
        cursor = get_cursor()
        cursor.execute("""

        UPDATE exam_timetable

        SET
        exam_date=%s,
        session=%s,
        hall=%s

        WHERE exam_id=%s

        """,

        (
            exam_date,
            session,
            hall,
            id
        ))

        get_db().commit()

        return redirect(url_for("exam_timetable_list"))

    return render_template(
        "edit_exam_timetable.html",
        exam=exam
    )

@app.route("/delete-exam-timetable/<int:id>")
def delete_exam_timetable(id):

    cursor = get_cursor()
    cursor.execute(
        "DELETE FROM exam_timetable WHERE exam_id=%s",
        (id,)
    )

    get_db().commit()

    return redirect(url_for("exam_timetable_list"))

@app.route("/delete-staff-mapping/<int:id>")
def delete_staff_mapping(id):

    cursor = get_cursor()
    sql = "DELETE FROM staff_class_mapping WHERE mapping_id=%s"
    cursor.execute(sql, (id,))
    db.commit()

    return redirect(url_for("staff_mapping_list"))
@app.route("/edit-staff-mapping/<int:id>", methods=["GET","POST"])
def edit_staff_mapping(id):

    cursor = get_cursor()
    cursor.execute("SELECT * FROM staff_class_mapping WHERE mapping_id=%s", (id,))
    mapping = cursor.fetchone()

    cursor.execute("SELECT staff_id FROM staff")
    staffs = cursor.fetchall()

    cursor.execute("SELECT dept_code FROM department")
    departments = cursor.fetchall()

    cursor.execute("SELECT course_code FROM course")
    courses = cursor.fetchall()

    cursor.execute("SELECT subject_code FROM subject")
    subjects = cursor.fetchall()

    if request.method == "POST":

        staff_id = request.form["staff_id"]
        dept_code = request.form["dept_code"]
        course_code = request.form["course_code"]
        subject_code = request.form["subject_code"]
        semester = request.form["semester"]
        section = request.form["section"]

        sql = """
        UPDATE staff_class_mapping
        SET staff_id=%s,
            dept_code=%s,
            course_code=%s,
            subject_code=%s,
            semester=%s,
            section=%s
        WHERE mapping_id=%s
        """

        cursor.execute(sql, (
            staff_id,
            dept_code,
            course_code,
            subject_code,
            semester,
            section,
            id
        ))

        get_db().commit()

        return redirect(url_for("staff_mapping_list"))

    return render_template(
        "edit_staff_mapping.html",
        mapping=mapping,
        staffs=staffs,
        departments=departments,
        courses=courses,
        subjects=subjects
    )
@app.route("/timetable")
def timetable_list():
    if not session.get("admin_logged_in"):
        return redirect(url_for("login"))

    cursor = get_cursor()
    cursor.execute("""
    SELECT
        t.timetable_id,
        COALESCE(d.dept_name, t.dept_code) AS dept_name,
        COALESCE(c.course_name, t.course_code) AS course_name,
        t.semester,
        t.section,
        sub.subject_name,
        s.staff_name,
        t.day_order,
        t.period_no,
        t.start_time,
        t.end_time
    FROM day_order_timetable t
    LEFT JOIN department d ON t.dept_code = d.dept_code
    LEFT JOIN course c ON t.course_code = c.course_code
    LEFT JOIN subject sub ON t.subject_code = sub.subject_code
    LEFT JOIN staff s ON t.staff_id = s.staff_id
    ORDER BY t.course_code, t.semester, t.section, t.day_order, t.period_no
    """)

    timetables = cursor.fetchall()

    for row in timetables:
        row["start_time_fmt"] = format_time_value(row["start_time"])
        row["end_time_fmt"] = format_time_value(row["end_time"])

    return render_template(
        "timetable_list.html",
        timetables=timetables
    )

@app.route("/add-timetable", methods=["GET", "POST"])
def add_timetable():
    if not session.get("admin_logged_in"):
        return redirect(url_for("login"))

    cursor = get_cursor()
    cursor.execute("SELECT dept_code, dept_name FROM department")
    departments = cursor.fetchall()

    cursor.execute("SELECT course_code, course_name FROM course")
    courses = cursor.fetchall()

    cursor.execute("SELECT subject_code, subject_name FROM subject")
    subjects = cursor.fetchall()

    cursor.execute("SELECT staff_id, staff_name FROM staff")
    staffs = cursor.fetchall()

    if request.method == "POST":
        dept_code = request.form["dept_code"]
        course_code = request.form["course_code"]
        semester = request.form["semester"]
        section = request.form["section"]
        subject_code = request.form["subject_code"]
        staff_id = request.form["staff_id"]
        day_order = request.form.get("day_order", type=int)
        period_no = request.form["period_no"]
        start_time = request.form.get("start_time") or "09:00:00"
        end_time = request.form.get("end_time") or "09:50:00"

        sql = """
        INSERT INTO day_order_timetable
        (dept_code, course_code, semester, section,
        subject_code, staff_id, day_order, period_no, start_time, end_time)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        """

        cursor.execute(sql, (
            dept_code,
            course_code,
            semester,
            section,
            subject_code,
            staff_id,
            day_order,
            period_no,
            start_time,
            end_time
        ))

        get_db().commit()
        flash("Timetable entry added successfully.", "success")
        return redirect(url_for("timetable_list"))

    return render_template(
        "add_timetable.html",
        departments=departments,
        courses=courses,
        subjects=subjects,
        staffs=staffs
    )

@app.route("/delete-timetable/<int:id>")
def delete_timetable(id):
    if not session.get("admin_logged_in"):
        return redirect(url_for("login"))

    cursor = get_cursor()
    cursor.execute("DELETE FROM day_order_timetable WHERE timetable_id = %s", (id,))
    get_db().commit()
    flash("Timetable period deleted successfully.", "success")
    return redirect(url_for("timetable_list"))

@app.route("/day-order-calendar", methods=["GET", "POST"])
def day_order_calendar_view():
    if not session.get("admin_logged_in"):
        return redirect(url_for("login"))

    cursor = get_cursor()

    if request.method == "POST":
        timetable_date = request.form.get("timetable_date")
        day_order = request.form.get("day_order", type=int)

        if timetable_date and day_order:
            cursor.execute("""
                INSERT INTO day_order_calendar (timetable_date, day_order)
                VALUES (%s, %s)
                ON DUPLICATE KEY UPDATE day_order = %s
            """, (timetable_date, day_order, day_order))
            get_db().commit()
            flash("Day order updated successfully.", "success")
            return redirect(url_for("day_order_calendar_view"))

    cursor.execute("""
        SELECT calendar_id, timetable_date, day_order
        FROM day_order_calendar
        ORDER BY timetable_date DESC
        LIMIT 60
    """)
    calendar_entries = cursor.fetchall()

    cursor.execute("SELECT day_order FROM day_order_calendar WHERE timetable_date = CURDATE()")
    today_row = cursor.fetchone()
    today_day_order = today_row["day_order"] if today_row else 1

    return render_template(
        "day_order_calendar.html",
        calendar_entries=calendar_entries,
        today_day_order=today_day_order
    )

@app.route("/set-today-day-order", methods=["POST"])
def set_today_day_order():
    if not session.get("admin_logged_in"):
        return redirect(url_for("login"))

    day_order = request.form.get("day_order", type=int)
    if day_order and day_order in [1, 2, 3, 4, 5, 6]:
        cursor = get_cursor()
        cursor.execute("""
            INSERT INTO day_order_calendar (timetable_date, day_order)
            VALUES (CURDATE(), %s)
            ON DUPLICATE KEY UPDATE day_order = %s
        """, (day_order, day_order))
        get_db().commit()
        flash(f"Today's Day Order successfully set to Day Order {day_order}!", "success")

    return redirect(url_for("day_order_calendar_view"))

@app.route("/circular")
def circular_list():
    cursor = get_cursor()
    cursor.execute("SELECT * FROM circular ORDER BY circular_date DESC")
    circulars = cursor.fetchall()

    return render_template(
        "circular_list.html",
        circulars=circulars
    )
@app.route("/add-circular", methods=["GET", "POST"])
def add_circular():
    cursor = get_cursor()
    if request.method == "POST":

        title = request.form["title"]
        description = request.form["description"]
        circular_date = request.form["circular_date"]

        cursor.execute("""
        INSERT INTO circular
        (title, description, circular_date)
        VALUES (%s,%s,%s)
        """,
        (
            title,
            description,
            circular_date
        ))

        get_db().commit()

        create_system_notification(
            f"📢 New Circular: {title}",
            f"{description[:150]}... Published on {circular_date}."
        )

        return redirect(url_for("circular_list"))

    return render_template("add_circular.html")

@app.route("/edit-circular/<int:id>", methods=["GET","POST"])
def edit_circular(id):

    cursor = get_cursor()
    cursor.execute(
        "SELECT * FROM circular WHERE circular_id=%s",
        (id,)
    )

    circular = cursor.fetchone()

    if request.method == "POST":

        title = request.form["title"]
        description = request.form["description"]
        circular_date = request.form["circular_date"]

        cursor.execute("""
        UPDATE circular
        SET
        title=%s,
        description=%s,
        circular_date=%s
        WHERE circular_id=%s
        """,
        (
            title,
            description,
            circular_date,
            id
        ))

        get_db().commit()

        return redirect(url_for("circular_list"))

    return render_template(
        "edit_circular.html",
        circular=circular
    )
@app.route("/delete-circular/<int:id>")
def delete_circular(id):

    cursor = get_cursor()
    cursor.execute(
        "DELETE FROM circular WHERE circular_id=%s",
        (id,)
    )

    get_db().commit()

    return redirect(url_for("circular_list"))

@app.route("/events")
def events_list():

    cursor = get_cursor()
    cursor.execute("""
    SELECT *
    FROM events
    ORDER BY event_date DESC
    """)

    events = cursor.fetchall()

    return render_template(
        "events_list.html",
        events=events
    )

@app.route("/add-event", methods=["GET","POST"])
def add_event():
    cursor = get_cursor()
    if request.method=="POST":

        title=request.form["title"]
        description=request.form["description"]
        event_date=request.form["event_date"]
        venue=request.form["venue"]

        cursor.execute("""
        INSERT INTO events
        (title,description,event_date,venue)
        VALUES(%s,%s,%s,%s)
        """,(title,description,event_date,venue))

        get_db().commit()

        create_system_notification(
            f"🎉 New Event: {title}",
            f"{description[:150]}... Scheduled on {event_date} at {venue}."
        )

        return redirect(url_for("events_list"))

    return render_template("add_event.html")

@app.route("/edit-event/<int:id>", methods=["GET","POST"])
def edit_event(id):
    cursor = get_cursor()
    cursor.execute("SELECT * FROM events WHERE event_id=%s",(id,))
    event=cursor.fetchone()

    if request.method=="POST":

        title=request.form["title"]
        description=request.form["description"]
        event_date=request.form["event_date"]
        venue=request.form["venue"]

        cursor.execute("""
        UPDATE events
        SET title=%s,
        description=%s,
        event_date=%s,
        venue=%s
        WHERE event_id=%s
        """,(title,description,event_date,venue,id))

        get_db().commit()

        return redirect(url_for("events_list"))

    return render_template("edit_event.html",event=event)

@app.route("/delete-event/<int:id>")
def delete_event(id):

    cursor = get_cursor()
    cursor.execute(
        "DELETE FROM events WHERE event_id=%s",
        (id,)
    )

    get_db().commit()

    return redirect(url_for("events_list"))

@app.route("/submit-certificate", methods=["POST"])
def submit_certificate():

    print("SUBMIT ROUTE HIT")
    print(request.form)

    reg_no = request.form.get("student_regno")
    student_name = request.form.get("student_name")
    department = request.form.get("department")

    father_name = request.form.get("father_name")
    mobile_no = request.form.get("mobile_no")
    academic_year = request.form.get("academic_year")

    certificate_type = request.form.get("certificate_type")
    purpose = request.form.get("purpose")

    payment_status = request.form.get("payment_status")
    transaction_id = request.form.get("transaction_id")

    cursor = get_cursor()

    cursor.execute("""
    INSERT INTO certificate_request
    (
        student_regno,
        student_name,
        department,
        father_name,
        mobile_no,
        academic_year,
        certificate_type,
        purpose,
        payment_status,
        transaction_id,
        request_date,
        status
    )
    VALUES
    (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,CURDATE(),'Pending')
    """,
    (
        reg_no,
        student_name,
        department,
        father_name,
        mobile_no,
        academic_year,
        certificate_type,
        purpose,
        payment_status,
        transaction_id
    ))

    get_db().commit()

    flash("Certificate Request Submitted Successfully!", "success")

    return redirect(url_for("student_dashboard"))

@app.route("/certificate-request")
def certificate_request_list():
    cursor = get_cursor()
    cursor.execute("""
    SELECT *
    FROM certificate_request
    ORDER BY request_id DESC
    """)

    requests = cursor.fetchall()

    return render_template(
        "certificate_request_list.html",
        requests=requests
    )

@app.route("/approve-request/<int:id>")
def approve_request(id):
    cursor = get_cursor()

    cursor.execute("SELECT * FROM certificate_request WHERE request_id=%s", (id,))
    req = cursor.fetchone()

    cursor.execute(
        "UPDATE certificate_request SET status='Approved' WHERE request_id=%s",
        (id,)
    )
    get_db().commit()

    if req:
        # Fetch student email if exists
        cursor.execute("SELECT email FROM student WHERE reg_no = %s", (req.get("student_regno"),))
        st_row = cursor.fetchone()
        student_email = st_row.get("email") if st_row and st_row.get("email") else f"{req.get('student_regno', '').lower()}@student.sxc.edu"

        cert_type = req.get("certificate_type") or "Certificate"
        st_name = req.get("student_name") or "Student"
        reg_no = req.get("student_regno") or ""

        title = f"📜 Certificate Approved: {cert_type}"
        message = f"Dear {st_name} ({reg_no}), your request for {cert_type} has been APPROVED by the Principal! Your digitally signed certificate is ready for download in 'My Certificate Requests'. You may also collect a physical sealed copy from College Office Room 102."
        create_system_notification(title, message, target_role="STUDENT", target_regno=reg_no, recipient_email=student_email)

    flash("Certificate request approved and notification sent to student!", "success")
    return redirect(url_for("certificate_request_list"))

@app.route("/reject-request/<int:id>", methods=["GET", "POST"])
def reject_request(id):
    cursor = get_cursor()

    reason = request.form.get("rejection_reason") or request.args.get("rejection_reason")
    if not reason or not reason.strip():
        reason = "College / Semester tuition fee dues pending. Please contact College Office."
    reason = reason.strip()

    cursor.execute("SELECT * FROM certificate_request WHERE request_id=%s", (id,))
    req = cursor.fetchone()

    cursor.execute(
        "UPDATE certificate_request SET status='Rejected', rejection_reason=%s WHERE request_id=%s",
        (reason, id)
    )
    get_db().commit()

    if req:
        # Fetch student email if exists
        cursor.execute("SELECT email FROM student WHERE reg_no = %s", (req.get("student_regno"),))
        st_row = cursor.fetchone()
        student_email = st_row.get("email") if st_row and st_row.get("email") else f"{req.get('student_regno', '').lower()}@student.sxc.edu"

        cert_type = req.get("certificate_type") or "Certificate"
        st_name = req.get("student_name") or "Student"
        reg_no = req.get("student_regno") or ""

        title = f"❌ Certificate Request Rejected: {cert_type}"
        message = f"Dear {st_name} ({reg_no}), your application for {cert_type} has been REJECTED. Reason: {reason}. Please contact the College Office for clarification."
        create_system_notification(title, message, target_role="STUDENT", target_regno=reg_no, recipient_email=student_email)

    flash(f"Certificate request rejected. Reason: {reason}", "warning")
    return redirect(url_for("certificate_request_list"))

@app.route("/digital-locker")
def digital_locker():

    cursor = get_cursor()

    cursor.execute("""
        SELECT *
        FROM digital_locker
        WHERE student_regno=%s
        ORDER BY id DESC
    """, (session["reg_no"],))

    documents = cursor.fetchall()

    return render_template(
        "digital_locker.html",
        documents=documents
    )

@app.route("/upload-document", methods=["GET", "POST"])
def upload_document():

    if request.method == "POST":

        document_name = request.form["document_name"]
        file = request.files["document_file"]

        if file:

            filename = f"{session['reg_no']}_{secure_filename(file.filename)}"

            upload_path = os.path.join(
                "static",
                "uploads",
                filename
            )

            file.save(upload_path)

            cursor = get_cursor()

            cursor.execute("""
            INSERT INTO digital_locker
            (
                student_regno,
                student_name,
                department,
                document_name,
                file_name,
                upload_date
            )
            VALUES
            (%s,%s,%s,%s,%s,CURDATE())
            """,
            (
                session["reg_no"],
                session["student_name"],
                session["department"],
                document_name,
                filename
            ))

            get_db().commit()

            flash("Document Uploaded Successfully!", "success")

            return redirect("/digital-locker")

    return render_template("upload_document.html")
 
@app.route("/delete-document/<int:id>")
def delete_document(id):

    cursor = get_cursor()

    cursor.execute(
        "SELECT file_name FROM digital_locker WHERE id=%s",
        (id,)
    )

    file = cursor.fetchone()

    if file:

        path = os.path.join(
            "static",
            "uploads",
            file["file_name"]
        )

        if os.path.exists(path):
            os.remove(path)

    cursor.execute(
        "DELETE FROM digital_locker WHERE id=%s",
        (id,)
    )

    get_db().commit()

    return redirect("/digital-locker")

@app.route("/scholarship")
def scholarship():
    cursor = get_cursor()
    cursor.execute("SELECT scholarship_id, status FROM scholarship")
    print(cursor.fetchall())   # <-- indha line add pannu

    cursor.execute("SELECT * FROM scholarship")
    scholarships = cursor.fetchall()

    return render_template(
        "scholarship_list.html",
        scholarships=scholarships
    )
@app.route("/approve-scholarship/<int:id>")
def approve_scholarship(id):

    cursor = get_cursor()
    cursor.execute(
        "UPDATE scholarship SET status='Approved' WHERE scholarship_id=%s",
        (id,)
    )

    get_db().commit()

    return redirect(url_for("scholarship"))


@app.route("/reject-scholarship/<int:id>")
def reject_scholarship(id):

    cursor = get_cursor()
    cursor.execute(
        "UPDATE scholarship SET status='Rejected' WHERE scholarship_id=%s",
        (id,)
    )

    get_db().commit()

    return redirect(url_for("scholarship"))

@app.route("/my-scholarship")
def my_scholarship():
    cursor = get_cursor()
    reg_no = session["reg_no"]

    cursor.execute(
        "SELECT * FROM scholarship WHERE student_regno=%s",
        (reg_no,)
    )

    scholarships = cursor.fetchall()

    return render_template(
        "my_scholarship.html",
        scholarships=scholarships
    )
@app.route("/download-certificate/<int:id>")
def download_certificate(id):

    cursor = get_cursor()

    cursor.execute("""
        SELECT *
        FROM certificate_request
        WHERE request_id=%s
    """, (id,))

    certificate = cursor.fetchone()

    if not certificate:
        flash("Certificate request not found.", "danger")
        return redirect(url_for("my_certificate_requests"))

    from reportlab.lib import colors
    buffer = io.BytesIO()

    pdf = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4

    # 1. Double Border Frame
    pdf.setStrokeColor(colors.HexColor("#800000"))
    pdf.setLineWidth(3)
    pdf.rect(30, 30, width - 60, height - 60)
    pdf.setLineWidth(1)
    pdf.rect(35, 35, width - 70, height - 70)

    # 2. College Header
    pdf.setFont("Helvetica-Bold", 19)
    pdf.setFillColor(colors.HexColor("#800000"))
    pdf.drawCentredString(width/2, height - 75, "ST. XAVIER'S COLLEGE (AUTONOMOUS)")

    pdf.setFont("Helvetica", 9)
    pdf.setFillColor(colors.HexColor("#555555"))
    pdf.drawCentredString(width/2, height - 90, "(Affiliated to Manonmaniam Sundaranar University, Re-accredited with 'A++' Grade by NAAC)")

    pdf.setFont("Helvetica-Bold", 11)
    pdf.setFillColor(colors.HexColor("#222222"))
    pdf.drawCentredString(width/2, height - 105, "Palayamkottai - 627 002, Tamil Nadu, India")

    # Header Separator
    pdf.setStrokeColor(colors.HexColor("#800000"))
    pdf.setLineWidth(1.5)
    pdf.line(50, height - 118, width - 50, height - 118)

    # Reference & Date
    req_date = certificate.get("request_date") or datetime.date.today()
    req_date_str = req_date.strftime("%d-%m-%Y") if hasattr(req_date, 'strftime') else str(req_date)
    ref_no = f"SXC/ERP/CERT/{certificate['request_id']:04d}/{certificate.get('academic_year') or '2026'}"

    pdf.setFont("Helvetica", 10)
    pdf.setFillColor(colors.HexColor("#333333"))
    pdf.drawString(60, height - 140, f"Ref: {ref_no}")
    pdf.drawRightString(width - 60, height - 140, f"Date: {req_date_str}")

    # Title Ribbon
    cert_title = (certificate.get("certificate_type") or "BONAFIDE CERTIFICATE").upper()
    pdf.setFillColor(colors.HexColor("#800000"))
    pdf.setFont("Helvetica-Bold", 16)
    pdf.drawCentredString(width/2, height - 180, cert_title)

    pdf.setLineWidth(1)
    pdf.setStrokeColor(colors.HexColor("#800000"))
    pdf.line(width/2 - 140, height - 186, width/2 + 140, height - 186)

    # Certificate Body Text
    st_name = certificate.get("student_name") or ""
    reg_no = certificate.get("student_regno") or ""
    dept = certificate.get("department") or ""
    acad_yr = certificate.get("academic_year") or "2026-2027"
    purpose = certificate.get("purpose") or "Official Educational Purpose"

    pdf.setFont("Helvetica", 13)
    pdf.setFillColor(colors.HexColor("#1a1a1a"))

    text_y = height - 235
    pdf.drawString(70, text_y, "This is to certify that")
    pdf.setFont("Helvetica-Bold", 14)
    pdf.drawString(205, text_y, f"Mr. / Ms. {st_name}")

    text_y -= 30
    pdf.setFont("Helvetica", 13)
    pdf.drawString(70, text_y, "bearing Register Number:")
    pdf.setFont("Helvetica-Bold", 13)
    pdf.drawString(235, text_y, f"{reg_no}")

    text_y -= 30
    pdf.setFont("Helvetica", 13)
    pdf.drawString(70, text_y, "is a bonafide student of this Institution studying in the Department of")

    text_y -= 25
    pdf.setFont("Helvetica-Bold", 13)
    pdf.drawString(70, text_y, f"{dept}")
    pdf.setFont("Helvetica", 13)
    pdf.drawString(70 + pdf.stringWidth(f"{dept}  ", "Helvetica-Bold", 13), text_y, f"during the academic year {acad_yr}.")

    text_y -= 35
    pdf.drawString(70, text_y, "This certificate is issued on the student's request for the purpose of:")

    text_y -= 25
    pdf.setFont("Helvetica-Oblique", 13)
    pdf.setFillColor(colors.HexColor("#333333"))
    pdf.drawString(90, text_y, f"\"{purpose}\"")

    text_y -= 35
    pdf.setFont("Helvetica", 12)
    pdf.setFillColor(colors.HexColor("#1a1a1a"))
    pdf.drawString(70, text_y, "His / Her conduct and character during the period of study have been GOOD.")

    # 3. Official College Seal Stamp (Circular Stamp drawing)
    seal_x = 130
    seal_y = 130
    pdf.setStrokeColor(colors.HexColor("#1a237e"))  # Deep indigo ink
    pdf.setFillColor(colors.HexColor("#1a237e"))
    pdf.setLineWidth(2)
    pdf.circle(seal_x, seal_y, 45, fill=0, stroke=1)
    pdf.setLineWidth(1)
    pdf.circle(seal_x, seal_y, 41, fill=0, stroke=1)

    pdf.setFont("Helvetica-Bold", 6.5)
    pdf.drawCentredString(seal_x, seal_y + 24, "ST. XAVIER'S COLLEGE")
    pdf.drawCentredString(seal_x, seal_y + 14, "(AUTONOMOUS)")
    pdf.setFont("Helvetica-Bold", 8)
    pdf.drawCentredString(seal_x, seal_y, "★ SEAL ★")
    pdf.setFont("Helvetica", 6.5)
    pdf.drawCentredString(seal_x, seal_y - 14, "PALAYAMKOTTAI")
    pdf.drawCentredString(seal_x, seal_y - 24, "ESTD. 1923")

    # 4. Principal Digital Signature Block
    sig_x = width - 180
    sig_y = 120

    # Cursive signature simulation
    pdf.setFont("Times-BoldItalic", 15)
    pdf.setFillColor(colors.HexColor("#0d47a1"))
    pdf.drawCentredString(sig_x, sig_y + 40, "Rev. Dr. S. Mariadoss, S.J.")

    # Verified badge box
    pdf.setStrokeColor(colors.HexColor("#2e7d32"))
    pdf.setFillColor(colors.HexColor("#e8f5e9"))
    pdf.setLineWidth(1)
    pdf.roundRect(sig_x - 75, sig_y + 18, 150, 16, 3, fill=1, stroke=1)
    pdf.setFont("Helvetica-Bold", 7.5)
    pdf.setFillColor(colors.HexColor("#2e7d32"))
    pdf.drawCentredString(sig_x, sig_y + 23, "✓ DIGITALLY SIGNED & VERIFIED")

    pdf.setFont("Helvetica-Bold", 12)
    pdf.setFillColor(colors.HexColor("#800000"))
    pdf.drawCentredString(sig_x, sig_y + 4, "PRINCIPAL")

    pdf.setFont("Helvetica", 8.5)
    pdf.setFillColor(colors.HexColor("#555555"))
    pdf.drawCentredString(sig_x, sig_y - 8, "St. Xavier's College (Autonomous)")
    pdf.drawCentredString(sig_x, sig_y - 18, "Palayamkottai - 627 002")

    # 5. Bottom Verification Note
    pdf.setStrokeColor(colors.HexColor("#cccccc"))
    pdf.setLineWidth(0.5)
    pdf.line(50, 62, width - 50, 62)

    pdf.setFont("Helvetica", 7.5)
    pdf.setFillColor(colors.HexColor("#777777"))
    pdf.drawCentredString(width/2, 50, "Note: This is an electronically generated and digitally authenticated certificate issued by SXC ERP System.")
    pdf.drawCentredString(width/2, 40, "For official verification, contact: office@stxavierstn.edu.in | Physical copy with embossed seal available at Room 102.")

    pdf.save()

    buffer.seek(0)

    filename = f"{certificate.get('certificate_type', 'Certificate').replace(' ', '_')}_{reg_no}.pdf"
    return send_file(
        buffer,
        as_attachment=True,
        download_name=filename,
        mimetype="application/pdf"
    )

@app.route("/admin-digital-locker")
def admin_digital_locker():

    cursor = get_cursor()

    cursor.execute("""
        SELECT *
        FROM digital_locker
        ORDER BY upload_date DESC
    """)

    documents = cursor.fetchall()

    return render_template(
        "admin_digital_locker.html",
        documents=documents
    )
@app.route("/student-notification")
def student_notification():
    if "reg_no" not in session:
        return redirect(url_for("student_login"))

    cursor = get_cursor()
    reg_no = session.get("reg_no")

    cursor.execute("""
        SELECT * FROM notifications
        WHERE (target_role IN ('ALL', 'STUDENT') AND target_regno IS NULL)
           OR (target_regno = %s)
        ORDER BY notification_date DESC, notification_id DESC
    """, (reg_no,))
    notifications = cursor.fetchall()

    return render_template(
        "student_notification.html",
        notifications=notifications
    )

@app.route("/student-profile")
def student_profile():

    cursor = get_cursor()

    cursor.execute("""
        SELECT *
        FROM student
        WHERE reg_no=%s
    """, (session["reg_no"],))

    student = cursor.fetchone()

    return render_template(
        "student_profile.html",
        student=student
    )
@app.route("/student-circular")
def student_circular():

    cursor = get_cursor()

    cursor.execute("""
        SELECT *
        FROM circular
        ORDER BY circular_date DESC
    """)

    circulars = cursor.fetchall()

    return render_template(
        "student_circular.html",
        circulars=circulars
    )
@app.route("/student-events")
def student_events():

    cursor = get_cursor()

    cursor.execute("""
        SELECT *
        FROM events
        ORDER BY event_date DESC
    """)

    events = cursor.fetchall()

    return render_template(
        "student_events.html",
        events=events
    )
@app.route("/gps-test")
def gps_test():
    return render_template("gps_test.html")


@app.route("/staff-attendance")
def staff_attendance():

    if "staff_id" not in session:
        return redirect(url_for("staff_login"))

    cursor = get_cursor()

    staff_id = session.get("staff_id")

    # Available classes (e.g. BCA, MCA)
    classes = ["BCA", "MCA"]
    selected_class = request.args.get("class_code", "BCA")
    if selected_class not in classes:
        selected_class = "BCA"

    # All subjects for classes
    cursor.execute("""
        SELECT
            subject_code,
            subject_name,
            dept_code AS class_code
        FROM subject
        WHERE dept_code IN ('BCA', 'MCA')
        ORDER BY dept_code, subject_code
    """)
    subjects = cursor.fetchall()

    # All students categorized by class
    cursor.execute("""
        SELECT
            student_id,
            reg_no,
            student_name,
            COALESCE(course_code, department) AS class_code,
            semester,
            section
        FROM student
        WHERE course_code IN ('BCA', 'MCA')
           OR department IN ('BCA', 'MCA')
        ORDER BY class_code, reg_no
    """)
    students = cursor.fetchall()

    today_str = datetime.date.today().strftime("%Y-%m-%d")

    return render_template(
        "staff_attendance.html",
        classes=classes,
        selected_class=selected_class,
        subjects=subjects,
        students=students,
        today_str=today_str
    )

@app.route("/staff-students")
def staff_students():

    if "staff_id" not in session:
        return redirect(url_for("staff_login"))

    cursor = get_cursor()

    staff_id = session.get("staff_id")

    cursor.execute("""
        SELECT DISTINCT
            st.student_id,
            st.reg_no,
            st.student_name,
            st.course_code,
            st.department,
            st.semester,
            st.section
        FROM student st
        JOIN staff_class_mapping scm
            ON st.department = scm.dept_code
           AND st.course_code = scm.course_code
           AND st.semester = scm.semester
           AND st.section = scm.section
        WHERE scm.staff_id = %s
        ORDER BY st.reg_no
    """, (staff_id,))

    students = cursor.fetchall()

    return render_template(
        "staff_students.html",
        students=students
    )
@app.route("/staff-circulars")
def staff_circulars():
    if "staff_id" not in session:
        return redirect(url_for("staff_login"))

    cursor = get_cursor()

    cursor.execute("""
        SELECT circular_id, title, description, circular_date
        FROM circular
        ORDER BY circular_date DESC, circular_id DESC
    """)

    circulars = cursor.fetchall()

    return render_template(
        "staff_circulars.html",
        circulars=circulars
    )
@app.route("/staff-notifications")
def staff_notifications():
    if "staff_id" not in session:
        return redirect(url_for("staff_login"))

    cursor = get_cursor()

    cursor.execute("""
        SELECT notification_id, title, message, notification_date
        FROM notifications
        WHERE target_role IN ('ALL', 'STAFF') AND target_regno IS NULL
        ORDER BY notification_date DESC, notification_id DESC
    """)

    notifications = cursor.fetchall()

    return render_template(
        "staff_notifications.html",
        notifications=notifications
    )
@app.route("/staff-view-attendance")
def staff_view_attendance():

    if "staff_id" not in session:
        return redirect(url_for("staff_login"))

    cursor = get_cursor()

    staff_id = session.get("staff_id")
    selected_class = request.args.get("class_code", "BCA")
    date_filter = request.args.get("date", "")

    # Query counts for badges
    cursor.execute("""
        SELECT
            COUNT(CASE WHEN st.course_code = 'BCA' OR st.department LIKE '%BCA%' OR st.reg_no LIKE '%UCA%' THEN 1 END) AS bca_count,
            COUNT(CASE WHEN st.course_code = 'MCA' OR st.department LIKE '%MCA%' OR st.reg_no LIKE '%PCA%' THEN 1 END) AS mca_count,
            COUNT(*) AS all_count
        FROM attendance a
        JOIN student st ON a.student_id = st.student_id
    """)
    counts = cursor.fetchone() or {"bca_count": 0, "mca_count": 0, "all_count": 0}

    params = []
    where_clauses = []

    if selected_class == "BCA":
        where_clauses.append("(st.course_code = 'BCA' OR st.department LIKE '%BCA%' OR st.reg_no LIKE '%UCA%')")
    elif selected_class == "MCA":
        where_clauses.append("(st.course_code = 'MCA' OR st.department LIKE '%MCA%' OR st.reg_no LIKE '%PCA%')")

    if date_filter:
        where_clauses.append("a.attendance_date = %s")
        params.append(date_filter)

    where_sql = ("WHERE " + " AND ".join(where_clauses)) if where_clauses else ""

    query = f"""
        SELECT
            a.attendance_date,
            a.period_no,
            a.subject_code,
            s.subject_name,
            st.reg_no,
            st.student_name,
            COALESCE(st.course_code, st.department, 'BCA') AS class_code,
            a.status
        FROM attendance a
        JOIN student st
            ON a.student_id = st.student_id
        LEFT JOIN subject s
            ON a.subject_code = s.subject_code
        {where_sql}
        ORDER BY a.attendance_date DESC, a.period_no DESC, st.reg_no
    """
    cursor.execute(query, tuple(params))
    attendance = cursor.fetchall()

    return render_template(
        "staff_view_attendance.html",
        attendance=attendance,
        selected_class=selected_class,
        date_filter=date_filter,
        counts=counts
    )

@app.route("/staff-timetable")
def staff_timetable():

    if "staff_id" not in session:
        return redirect(url_for("staff_login"))

    cursor = get_cursor()
    staff_id = session.get("staff_id")

    # Today's Day Order from calendar
    cursor.execute("""
        SELECT day_order
        FROM day_order_calendar
        WHERE timetable_date = CURDATE()
    """)

    today = cursor.fetchone()

    if today and today.get("day_order"):
        today_day_order = today["day_order"]
    else:
        weekday = datetime.date.today().weekday()
        today_day_order = 1 if weekday == 6 else (weekday % 5) + 1

    req_day_order = request.args.get("day_order", type=int)
    active_day_order = req_day_order if req_day_order and req_day_order in [1, 2, 3, 4, 5, 6] else today_day_order

    cursor.execute("""
        SELECT
            dt.day_order,
            dt.period_no,
            dt.start_time,
            dt.end_time,
            dt.subject_code,
            s.subject_name,
            dt.course_code,
            dt.semester,
            dt.section
        FROM day_order_timetable dt
        LEFT JOIN subject s
            ON dt.subject_code = s.subject_code
        WHERE dt.staff_id = %s
          AND dt.day_order = %s
        ORDER BY dt.period_no
    """, (staff_id, active_day_order))

    raw_timetable = cursor.fetchall()
    timetable = []
    for row in raw_timetable:
        r = dict(row)
        r["start_time_fmt"] = format_time_value(row["start_time"])
        r["end_time_fmt"] = format_time_value(row["end_time"])
        timetable.append(r)

    today_str = datetime.date.today().strftime("%A, %d %B %Y")

    return render_template(
        "staff_timetable.html",
        timetable=timetable,
        today_day_order=today_day_order,
        active_day_order=active_day_order,
        day_order=active_day_order,
        today_str=today_str
    )
@app.route("/staff-dashboard")
def staff_dashboard():
    if "staff_id" not in session:
        return redirect(url_for("staff_login"))

    return render_template("staff_dashboard.html")
    
@app.route("/staff-login", methods=["GET", "POST"])
def staff_login():

    if request.method == "POST":

        staff_id = request.form["staff_id"]
        password = request.form["password"]

        cursor = get_cursor()

        cursor.execute("""
            SELECT staff_id, staff_name
            FROM staff
            WHERE staff_id = %s AND password = %s
        """, (staff_id, password))

        staff = cursor.fetchone()

        if staff:
            session["staff_id"] = staff["staff_id"]
            session["staff_name"] = staff["staff_name"]

            return redirect(url_for("staff_dashboard"))

        flash("Invalid Staff ID or Password.", "danger")

    return render_template("staff_login.html")

@app.route("/save-attendance", methods=["POST"])
def save_attendance():

    if "staff_id" not in session:
        return redirect(url_for("staff_login"))

    cursor = get_cursor()

    staff_id = session.get("staff_id")
    subject_code = request.form.get("subject_code")
    attendance_date = request.form.get("attendance_date")
    period_no = request.form.get("period_no")

    student_ids = request.form.getlist("student_id")

    for student_id in student_ids:
        status = request.form.get(f"status_{student_id}", "Present")

        cursor.execute("""
            SELECT attendance_id FROM attendance
            WHERE student_id = %s AND attendance_date = %s AND period_no = %s
        """, (student_id, attendance_date, period_no))
        existing = cursor.fetchone()

        if existing:
            cursor.execute("""
                UPDATE attendance
                SET staff_id = %s, subject_code = %s, status = %s
                WHERE attendance_id = %s
            """, (staff_id, subject_code, status, existing["attendance_id"]))
        else:
            cursor.execute("""
                INSERT INTO attendance
                (student_id, staff_id, subject_code, attendance_date, period_no, status)
                VALUES (%s, %s, %s, %s, %s, %s)
            """, (student_id, staff_id, subject_code, attendance_date, period_no, status))

    get_db().commit()

    flash("Attendance saved successfully!", "success")

    return redirect(url_for("staff_view_attendance"))
@app.route("/student-exam-timetable")
def student_exam_timetable():
    if "reg_no" not in session:
        return redirect(url_for("student_login"))

    cursor = get_cursor()

    cursor.execute("""
        SELECT student_id, reg_no, student_name, department, course_code, semester
        FROM student
        WHERE reg_no = %s
    """, (session["reg_no"],))
    student = cursor.fetchone()

    if not student:
        flash("Student details not found.", "danger")
        return redirect(url_for("student_dashboard"))

    dept = student.get("department") or ""
    course = student.get("course_code") or dept
    reg_no = session["reg_no"]

    # Detect class code (BCA vs MCA)
    if "BCA" in dept or "BCA" in course or "UCA" in reg_no:
        class_filter = "BCA"
    elif "MCA" in dept or "MCA" in course or "PCA" in reg_no:
        class_filter = "MCA"
    else:
        class_filter = dept or course

    cursor.execute("""
        SELECT
            e.exam_id,
            e.exam_date,
            e.session,
            e.hall,
            e.subject_code,
            e.semester,
            COALESCE(s.subject_name, e.subject_code) AS subject_name,
            e.course_code,
            e.dept_code
        FROM exam_timetable e
        LEFT JOIN subject s
            ON e.subject_code = s.subject_code
        WHERE e.course_code = %s OR e.dept_code = %s OR e.course_code LIKE %s OR e.dept_code LIKE %s
        ORDER BY e.exam_date, e.session
    """, (class_filter, class_filter, f"%{class_filter}%", f"%{class_filter}%"))

    exams = cursor.fetchall()

    return render_template(
        "student_exam_timetable.html",
        exams=exams,
        student=student,
        class_filter=class_filter
    )
@app.route("/staff-logout")
def staff_logout():
    session.clear()
    flash("Staff logged out successfully.", "info")
    return redirect(url_for("home"))

@app.route("/staff-profile")
def staff_profile():

    if "staff_id" not in session:
        return redirect(url_for("staff_login"))

    cursor = get_cursor()

    cursor.execute("""
        SELECT
            staff_id,
            staff_name,
            department,
            designation,
            mobile
        FROM staff
        WHERE staff_id = %s
    """, (session["staff_id"],))

    staff = cursor.fetchone()

    if not staff:
        flash("Staff details not found.", "danger")
        return redirect(url_for("staff_dashboard"))

    return render_template(
        "staff_profile.html",
        staff=staff
    )
if __name__ == "__main__":
    app.run(debug=True)