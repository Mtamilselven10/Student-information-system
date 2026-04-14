import os
import uuid
import random
from flask import Flask, render_template, request, redirect, url_for, flash, session, Response
from flask_mail import Mail, Message
from controller.database import db
from controller.config import Config
from controller.models import (
    User, Role, UserRole,
    StudentProfile, StaffProfile,
    Result, Marks, Attendance, AdminProfile, StudentAttachment
)
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from sqlalchemy import text

app = Flask(__name__)
app.config.from_object(Config)
app.config["UPLOAD_FOLDER"] = os.path.join("static", "uploads")
app.config.setdefault("MAIL_SERVER", "smtp.gmail.com")
app.config.setdefault("MAIL_PORT", 587)
app.config.setdefault("MAIL_USE_TLS", True)
app.config.setdefault("MAIL_USE_SSL", False)
mail_username = (
    os.getenv("MAIL_USERNAME")
    or os.getenv("GMAIL_USER")
    or os.getenv("EMAIL_USER")
    or ""
)
mail_password = (
    os.getenv("MAIL_PASSWORD")
    or os.getenv("GMAIL_APP_PASSWORD")
    or os.getenv("EMAIL_PASSWORD")
    or ""
)
app.config.setdefault("MAIL_USERNAME", mail_username)
app.config.setdefault("MAIL_PASSWORD", mail_password)
app.config.setdefault("MAIL_DEFAULT_SENDER", os.getenv("MAIL_DEFAULT_SENDER", mail_username))

db.init_app(app)
mail = Mail(app)

ALLOWED_IMAGE_EXTENSIONS = {"png", "jpg", "jpeg", "gif", "webp"}
ALLOWED_ATTACHMENT_EXTENSIONS = {
    "png", "jpg", "jpeg", "gif", "webp",
    "pdf", "doc", "docx", "xls", "xlsx",
    "ppt", "pptx", "txt", "zip", "rar"
}


def generate_otp():
    return f"{random.randint(100000, 999999)}"


def send_otp_email(recipient_email, otp):
    username = app.config.get("MAIL_USERNAME", "").strip()
    password = app.config.get("MAIL_PASSWORD", "").strip()
    if not username or not password:
        raise ValueError("Gmail SMTP is not configured. Set MAIL_USERNAME and MAIL_PASSWORD (Gmail App Password).")

    sender_email = (
        app.config.get("MAIL_DEFAULT_SENDER")
        or app.config.get("MAIL_USERNAME")
    )
    message = Message(
        subject="Your OTP for Registration",
        recipients=[recipient_email],
        sender=sender_email,
        body=f"Your OTP is {otp}. Please enter this OTP to complete your registration."
    )
    mail.send(message)


def allowed_image_file(filename):
    if "." not in filename:
        return False
    ext = filename.rsplit(".", 1)[1].lower()
    return ext in ALLOWED_IMAGE_EXTENSIONS


def allowed_attachment_file(filename):
    if "." not in filename:
        return False
    ext = filename.rsplit(".", 1)[1].lower()
    return ext in ALLOWED_ATTACHMENT_EXTENSIONS


def is_image_attachment(filename):
    if "." not in filename:
        return False
    ext = filename.rsplit(".", 1)[1].lower()
    return ext in ALLOWED_IMAGE_EXTENSIONS


def get_current_student(user_id):
    student = StudentProfile.query.filter_by(user_id=user_id).first()
    if not student:
        student = StudentProfile(user_id=user_id)
        db.session.add(student)
        db.session.commit()
    return student


def get_current_staff_profile(user_id):
    staff = StaffProfile.query.filter_by(user_id=user_id).first()
    if not staff:
        staff = StaffProfile(user_id=user_id)
        db.session.add(staff)
        db.session.commit()
    return staff


def is_student_profile_complete(student):
    required_fields = [
        student.register_number,
        student.batch,
        student.course,
        student.branch,
        student.gender,
        student.dob,
        student.personal_email,
        student.mobile,
        student.address,
    ]
    return all(value is not None and str(value).strip() for value in required_fields)


def save_student_photo(student, file):
    original_name = secure_filename(file.filename)
    ext = original_name.rsplit(".", 1)[1].lower()
    saved_name = f"user_{student.user_id}_{uuid.uuid4().hex[:8]}.{ext}"
    save_path = os.path.join(app.config["UPLOAD_FOLDER"], saved_name)
    file.save(save_path)
    student.photo = os.path.join("uploads", saved_name).replace("\\", "/")
    db.session.commit()


def _pdf_safe_text(value):
    text = "" if value is None else str(value)
    text = text.encode("latin-1", "replace").decode("latin-1")
    return text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def _build_simple_pdf(title, lines):
    page_width = 595
    page_height = 842
    margin = 42
    line_height = 14
    max_lines = 52

    chunks = [lines[i:i + max_lines] for i in range(0, len(lines), max_lines)] or [[]]
    page_count = len(chunks)
    objects = {}

    # Base objects: 1 Catalog, 2 Pages, 3 Font
    objects[3] = b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"

    page_refs = []
    for idx, chunk in enumerate(chunks, start=1):
        page_obj = 4 + (idx - 1) * 2
        content_obj = page_obj + 1

        content_lines = [
            "BT",
            "/F1 11 Tf",
            f"{margin} {page_height - margin} Td",
            f"{line_height} TL",
            f"({_pdf_safe_text(title)} - Page {idx}/{page_count}) Tj",
            "T*",
            "T*",
        ]
        for line in chunk:
            content_lines.append(f"({_pdf_safe_text(line)}) Tj")
            content_lines.append("T*")
        content_lines.append("ET")
        content_stream = "\n".join(content_lines).encode("latin-1", "replace")
        objects[content_obj] = (
            f"<< /Length {len(content_stream)} >>\nstream\n".encode("latin-1")
            + content_stream
            + b"\nendstream"
        )

        objects[page_obj] = (
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {page_width} {page_height}] "
            f"/Resources << /Font << /F1 3 0 R >> >> /Contents {content_obj} 0 R >>"
        ).encode("latin-1")
        page_refs.append(f"{page_obj} 0 R")

    objects[2] = f"<< /Type /Pages /Kids [{' '.join(page_refs)}] /Count {page_count} >>".encode("latin-1")
    objects[1] = b"<< /Type /Catalog /Pages 2 0 R >>"

    max_obj = max(objects)
    pdf = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = [0] * (max_obj + 1)

    for obj_num in range(1, max_obj + 1):
        offsets[obj_num] = len(pdf)
        pdf.extend(f"{obj_num} 0 obj\n".encode("latin-1"))
        pdf.extend(objects[obj_num])
        pdf.extend(b"\nendobj\n")

    xref_start = len(pdf)
    pdf.extend(f"xref\n0 {max_obj + 1}\n".encode("latin-1"))
    pdf.extend(b"0000000000 65535 f \n")
    for obj_num in range(1, max_obj + 1):
        pdf.extend(f"{offsets[obj_num]:010d} 00000 n \n".encode("latin-1"))

    pdf.extend(
        f"trailer\n<< /Size {max_obj + 1} /Root 1 0 R >>\nstartxref\n{xref_start}\n%%EOF".encode("latin-1")
    )
    return bytes(pdf)


def _student_pdf_file_path(student):
    pdf_dir = os.path.join(app.config["UPLOAD_FOLDER"], "student_pdfs")
    os.makedirs(pdf_dir, exist_ok=True)
    return os.path.join(pdf_dir, f"student_{student.user_id}_total_details.pdf")


def _student_export_payload(student):
    attachments = (
        StudentAttachment.query
        .filter_by(student_id=student.id)
        .order_by(StudentAttachment.id.desc())
        .all()
    )

    name = student.user.username if getattr(student, "user", None) else (session.get("username") or "-")
    scholarship_text = (
        getattr(student, "scholarship_category", None)
        or getattr(student, "scholarship_details", None)
        or "-"
    )

    lines = [
        "STUDENT PROFILE",
        "",
        f"Name: {name}",
        f"Register Number: {student.register_number or '-'}",
        f"Batch: {student.batch or '-'}",
        f"Course: {student.course or '-'}",
        f"Branch: {student.branch or '-'}",
        f"Gender: {student.gender or '-'}",
        f"Date of Birth: {student.dob or '-'}",
        f"Blood Group: {student.blood_group or '-'}",
        f"Nationality: {student.nationality or '-'}",
        f"Hostel: {student.hostel or '-'}",
        f"Bus: {student.bus or '-'}",
        f"Admission Quota: {student.admission_quota or '-'}",
        f"First Graduate: {student.first_graduate or '-'}",
        f"Personal Email: {student.personal_email or '-'}",
        f"College Email: {student.college_email or '-'}",
        f"Email ID: {student.email_id or '-'}",
        f"Mobile Number (Student): {student.mobile or '-'}",
        f"Address: {student.address or '-'}",
        "",
        "FAMILY DETAILS",
        f"Father Name: {student.father_name or '-'}",
        f"Mother Name: {student.mother_name or '-'}",
        f"Parent Occupation: {student.parent_occupation or '-'}",
        f"Mobile Number (Parent): {student.parent_mobile or '-'}",
        "",
        "ACADEMIC INFORMATION",
        f"Semester: {student.semester or '-'}",
        f"Admission Year: {student.admission_year or '-'}",
        f"Previous School / College: {student.previous_institution or '-'}",
        f"Internal Marks: {student.internal_marks or '-'}",
        f"Semester Exam Marks: {student.semester_exam_marks or '-'}",
        f"CGPA / GPA: {student.cgpa_gpa or '-'}",
        f"Arrears / Backlogs: {student.arrears_backlogs or '-'}",
        "",
        "FEE & SCHOLARSHIP DETAILS",
        f"Tuition Fee: {student.tuition_fee or '-'}",
        f"Bus Fee / Hostel Fee: {student.bus_hostel_fee or '-'}",
        f"Scholarship Details: {scholarship_text}",
        f"Scholarship Amount: {student.scholarship_amount or '-'}",
        "",
        "HOSTEL DETAILS",
        f"Hostel Name: {student.hostel_name or '-'}",
        f"Room Number: {student.room_number or '-'}",
        f"Roommates Count: {student.roommates_count or '-'}",
        f"Warden Name: {student.warden_name or '-'}",
        f"Warden Mobile Number: {student.warden_mobile or '-'}",
        "",
        "EXTRA-CURRICULAR ACTIVITIES",
        f"Sports Participation: {student.sports_participation or '-'}",
        f"Club Memberships: {student.club_memberships or '-'}",
        f"Achievements / Awards: {student.achievements_awards or '-'}",
        f"Events Participated: {student.events_participated or '-'}",
        "",
        "PROFESSIONAL / CAREER DETAILS",
        f"Projects Done: {student.projects_done or '-'}",
        f"Internships: {student.internships or '-'}",
        f"Certifications: {student.certifications or '-'}",
        f"Skills: {student.skills or '-'}",
        f"Project Details: {student.project_details or '-'}",
        "",
        "DISCIPLINARY RECORDS",
        f"Warnings: {student.warnings or '-'}",
        f"Complaints: {student.complaints or '-'}",
        f"Actions Taken: {student.actions_taken or '-'}",
        "",
        "RESULT DETAILS",
    ]

    if student.results:
        for idx, item in enumerate(student.results, start=1):
            lines.append(
                f"{idx}. Sem {item.semester or '-'} | {item.subject_code or '-'} | {item.subject_name or '-'} | {item.grade or '-'} | {item.result_status or '-'} | {item.month_year or '-'}"
            )
    else:
        lines.append("No result details available")

    lines.extend(["", "MARKS"])
    if student.marks:
        for idx, item in enumerate(student.marks, start=1):
            lines.append(f"{idx}. {item.subject or '-'} - {item.marks if item.marks is not None else '-'}")
    else:
        lines.append("No marks available")

    lines.extend(["", "ATTENDANCE"])
    if student.attendance:
        for idx, item in enumerate(student.attendance, start=1):
            lines.append(f"{idx}. {item.subject or '-'} - {item.attendance_percentage if item.attendance_percentage is not None else '-'}%")
    else:
        lines.append("No attendance available")

    lines.extend(["", "ATTACHMENTS"])
    if attachments:
        for idx, item in enumerate(attachments, start=1):
            lines.append(f"{idx}. {item.file_name} ({item.file_path})")
    else:
        lines.append("No attachments uploaded")

    rows = [
        ("Basic Profile Details", "Name", name),
        ("Basic Profile Details", "Register Number", student.register_number or "-"),
        ("Basic Profile Details", "Batch", student.batch or "-"),
        ("Basic Profile Details", "Course", student.course or "-"),
        ("Basic Profile Details", "Branch", student.branch or "-"),
        ("Basic Profile Details", "Gender", student.gender or "-"),
        ("Basic Profile Details", "Date of Birth", student.dob or "-"),
        ("Basic Profile Details", "Blood Group", student.blood_group or "-"),
        ("Basic Profile Details", "Nationality", student.nationality or "-"),
        ("Contact Information", "Personal Email", student.personal_email or "-"),
        ("Contact Information", "College Email", student.college_email or "-"),
        ("Contact Information", "Mobile", student.mobile or "-"),
        ("Contact Information", "Address", student.address or "-"),
        ("Family Details", "Father Name", student.father_name or "-"),
        ("Family Details", "Mother Name", student.mother_name or "-"),
        ("Family Details", "Parent Occupation", student.parent_occupation or "-"),
        ("Family Details", "Parent Mobile Number", student.parent_mobile or "-"),
        ("Family Details", "Parent Email", student.email_id or "-"),
        ("Academic Information", "Semester", student.semester or "-"),
        ("Academic Information", "Admission Year", student.admission_year or "-"),
        ("Academic Information", "Previous School / College", student.previous_institution or "-"),
        ("Academic Information", "Internal Marks", student.internal_marks or "-"),
        ("Academic Information", "Semester Exam Marks", student.semester_exam_marks or "-"),
        ("Academic Information", "CGPA / GPA", student.cgpa_gpa or "-"),
        ("Academic Information", "Arrears / Backlogs", student.arrears_backlogs or "-"),
        ("Hostel & Transport", "Hostel", student.hostel or "-"),
        ("Hostel & Transport", "Hostel Name", student.hostel_name or "-"),
        ("Hostel & Transport", "Room Number", student.room_number or "-"),
        ("Hostel & Transport", "Roommates Count", student.roommates_count or "-"),
        ("Hostel & Transport", "Warden Name", student.warden_name or "-"),
        ("Hostel & Transport", "Warden Mobile", student.warden_mobile or "-"),
        ("Hostel & Transport", "Bus", student.bus or "-"),
        ("Fees & Scholarship", "Tuition Fee", student.tuition_fee or "-"),
        ("Fees & Scholarship", "Bus / Hostel Fee", student.bus_hostel_fee or "-"),
        ("Fees & Scholarship", "Scholarship Details", scholarship_text),
        ("Fees & Scholarship", "Scholarship Amount", student.scholarship_amount or "-"),
        ("Professional Details", "Projects Done", student.projects_done or "-"),
        ("Professional Details", "Internships", student.internships or "-"),
        ("Professional Details", "Certifications", student.certifications or "-"),
        ("Professional Details", "Skills", student.skills or "-"),
        ("Professional Details", "Project Details", student.project_details or "-"),
        ("Disciplinary Record", "Warnings", student.warnings or "-"),
        ("Disciplinary Record", "Complaints", student.complaints or "-"),
        ("Disciplinary Record", "Actions Taken", student.actions_taken or "-"),
    ]

    if student.results:
        for item in student.results:
            rows.append(("Result Details", f"{item.subject_code or '-'} - {item.subject_name or '-'}", f"Sem {item.semester or '-'} | Grade {item.grade or '-'} | {item.result_status or '-'} | {item.month_year or '-'}"))
    if student.marks:
        for item in student.marks:
            rows.append(("Marks Details", item.subject or "-", item.marks if item.marks is not None else "-"))
    if student.attendance:
        for item in student.attendance:
            rows.append(("Attendance Details", item.subject or "-", f"{item.attendance_percentage if item.attendance_percentage is not None else '-'}%"))
    if attachments:
        for item in attachments:
            rows.append(("Attachments", item.file_name or "-", item.file_path or "-"))

    return lines, rows


# ---------------- CREATE TABLES ----------------

with app.app_context():
    os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)
    db.create_all()
    staff_columns = [row[1] for row in db.session.execute(text("PRAGMA table_info(staff_profile)")).all()]
    if "photo" not in staff_columns:
        db.session.execute(text("ALTER TABLE staff_profile ADD COLUMN photo VARCHAR(200)"))
        db.session.commit()
    if "approval_status" not in staff_columns:
        db.session.execute(text("ALTER TABLE staff_profile ADD COLUMN approval_status VARCHAR(20)"))
        db.session.execute(text("UPDATE staff_profile SET approval_status = 'Approved' WHERE approval_status IS NULL OR approval_status = ''"))
        db.session.commit()
    student_columns = {row[1] for row in db.session.execute(text("PRAGMA table_info(student_profile)")).all()}
    student_extra_columns = {
        "blood_group": "VARCHAR(20)",
        "nationality": "VARCHAR(50)",
        "father_name": "VARCHAR(100)",
        "mother_name": "VARCHAR(100)",
        "parent_occupation": "VARCHAR(100)",
        "parent_mobile": "VARCHAR(20)",
        "email_id": "VARCHAR(100)",
        "semester": "VARCHAR(20)",
        "admission_year": "VARCHAR(20)",
        "previous_institution": "VARCHAR(150)",
        "internal_marks": "VARCHAR(50)",
        "semester_exam_marks": "VARCHAR(50)",
        "cgpa_gpa": "VARCHAR(20)",
        "arrears_backlogs": "VARCHAR(100)",
        "tuition_fee": "VARCHAR(50)",
        "bus_hostel_fee": "VARCHAR(50)",
        "scholarship_category": "VARCHAR(200)",
        "scholarship_amount": "VARCHAR(50)",
        "hostel_name": "VARCHAR(100)",
        "room_number": "VARCHAR(20)",
        "roommates_count": "VARCHAR(20)",
        "warden_name": "VARCHAR(100)",
        "warden_mobile": "VARCHAR(20)",
        "sports_participation": "VARCHAR(200)",
        "club_memberships": "VARCHAR(200)",
        "achievements_awards": "VARCHAR(200)",
        "events_participated": "VARCHAR(200)",
        "project_details": "TEXT",
        "projects_done": "VARCHAR(200)",
        "internships": "VARCHAR(200)",
        "certifications": "VARCHAR(200)",
        "skills": "VARCHAR(200)",
        "warnings": "VARCHAR(200)",
        "complaints": "VARCHAR(200)",
        "actions_taken": "VARCHAR(200)",
    }
    for column_name, column_type in student_extra_columns.items():
        if column_name not in student_columns:
            db.session.execute(text(f"ALTER TABLE student_profile ADD COLUMN {column_name} {column_type}"))
    db.session.commit()
    admin_role = Role.query.filter_by(name="Admin").first()
    if not admin_role:
        admin_role = Role(name="Admin")
        db.session.add(admin_role)
        db.session.flush()

    admins = [
        {"email": "tamil1@gmail.com", "password": "1234567890"},
        {"email": "praveen@gmail.com", "password": "123456789"},
        {"email": "gopi@gmail.com", "password": "12345678"},
    ]

    for admin in admins:
        existing_user = User.query.filter_by(email=admin["email"]).first()

        if not existing_user:
            new_admin = User(
                username=admin["email"],   # just store email as username
                email=admin["email"],
                password=generate_password_hash(admin["password"])
            )
            db.session.add(new_admin)
            db.session.flush()
            existing_user = new_admin

        existing_admin_role = UserRole.query.filter_by(
            user_id=existing_user.user_id,
            role_id=admin_role.role_id
        ).first()
        if not existing_admin_role:
            db.session.add(UserRole(user_id=existing_user.user_id, role_id=admin_role.role_id))

    db.session.commit()

    # Create default roles if not exists
    default_roles = ["Staff", "Student"]
    for role_name in default_roles:
        if not Role.query.filter_by(name=role_name).first():
            db.session.add(Role(name=role_name))
    db.session.commit()


# ================= HOME =================
@app.route("/")
def index():
    if "role" in session:
        if session["role"] == "Admin":
            return redirect(url_for("admin_dashboard"))
        elif session["role"] == "Staff":
            return redirect(url_for("staff_dashboard"))
        elif session["role"] == "Student":
            student = get_current_student(session.get("user_id"))
            if not is_student_profile_complete(student):
                return redirect(url_for("student_profile", setup=1))
            return redirect(url_for("student_dashboard"))
    return redirect(url_for("login"))


# ================= REGISTER =================
@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = (request.form.get("username") or "").strip()
        email = (request.form.get("email") or "").strip().lower()
        password = request.form.get("password") or ""
        role_name = (request.form.get("role") or "").strip()
        allowed_roles = {"Student", "Staff"}

        if role_name not in allowed_roles:
            flash("Admin account can be created only by system")
            return redirect(url_for("register"))

        if not username or not email or not password:
            flash("All fields are required")
            return redirect(url_for("register"))

        existing_user = User.query.filter_by(email=email).first()
        if existing_user:
            flash("Email already registered")
            return redirect(url_for("register"))

        try:
            otp = generate_otp()
            send_otp_email(email, otp)

            session["pending_user"] = {
                "username": username,
                "email": email,
                "password": generate_password_hash(password),
                "role": role_name
            }
            session["registration_otp"] = otp
            flash("OTP sent to your email")
            return redirect(url_for("verify_otp"))

        except Exception as e:
            error_text = str(e)
            if "Authentication Required" in error_text:
                flash("Gmail authentication failed. Use your Gmail address in MAIL_USERNAME and 16-digit App Password in MAIL_PASSWORD.")
            else:
                flash(error_text)
            return redirect(url_for("register"))

    return render_template("register.html")


@app.route("/verify_otp", methods=["GET", "POST"])
def verify_otp():
    pending_user = session.get("pending_user")
    pending_otp = session.get("registration_otp")

    if not pending_user or not pending_otp:
        flash("Please register first")
        return redirect(url_for("register"))

    if request.method == "POST":
        entered_otp = (request.form.get("otp") or "").strip()
        if entered_otp != str(pending_otp):
            flash("Invalid OTP")
            return render_template("verify_otp.html")

        try:
            role_name = pending_user.get("role")
            role = Role.query.filter_by(name=role_name).first()
            if not role:
                flash("Role not found")
                return redirect(url_for("register"))

            existing_user = User.query.filter_by(email=pending_user.get("email")).first()
            if existing_user:
                flash("Email already registered")
                session.pop("pending_user", None)
                session.pop("registration_otp", None)
                return redirect(url_for("login"))

            new_user = User(
                username=pending_user.get("username"),
                email=pending_user.get("email"),
                password=pending_user.get("password")
            )
            db.session.add(new_user)
            db.session.flush()

            db.session.add(UserRole(user_id=new_user.user_id, role_id=role.role_id))

            if role_name == "Student":
                db.session.add(StudentProfile(user_id=new_user.user_id))
            elif role_name == "Staff":
                db.session.add(StaffProfile(user_id=new_user.user_id, approval_status="Pending"))

            db.session.commit()
            session.pop("pending_user", None)
            session.pop("registration_otp", None)
            flash("Registration Successful!")
            return redirect(url_for("login"))
        except Exception as e:
            db.session.rollback()
            flash(str(e))
            return render_template("verify_otp.html")

    return render_template("verify_otp.html")


# ================= LOGIN =================
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email")
        password = request.form.get("password")

        user = User.query.filter_by(email=email).first()

        if user:
            if check_password_hash(user.password, password):
                session["user_id"] = user.user_id
                session["username"] = user.username

                user_roles = (
                    db.session.query(Role.name)
                    .join(UserRole, UserRole.role_id == Role.role_id)
                    .filter(UserRole.user_id == user.user_id)
                    .all()
                )
                role_names = {row[0] for row in user_roles}

                if "Admin" in role_names:
                    session["role"] = "Admin"
                    return redirect(url_for("index"))
                if "Staff" in role_names:
                    staff_profile = StaffProfile.query.filter_by(user_id=user.user_id).first()
                    status = (staff_profile.approval_status if staff_profile and staff_profile.approval_status else "Approved")
                    if status != "Approved":
                        flash("Admin approval pending for staff account")
                        return render_template("login.html", show_forgot=False)
                    session["role"] = "Staff"
                    return redirect(url_for("index"))
                if "Student" in role_names:
                    session["role"] = "Student"
                    student = StudentProfile.query.filter_by(user_id=user.user_id).first()
                    if not student:
                        student = StudentProfile(user_id=user.user_id)
                        db.session.add(student)
                        db.session.commit()

                    if not is_student_profile_complete(student):
                        return redirect(url_for("student_profile", setup=1))
                    return redirect(url_for("student_dashboard"))

            flash("Invalid password")
            return render_template("login.html", show_forgot=True, forgot_email=email)

        flash("Invalid Credentials")
        return render_template("login.html", show_forgot=False)

    return render_template("login.html", show_forgot=False)


@app.route("/forgot_password", methods=["POST"])
def forgot_password():
    email = (request.form.get("email") or "").strip().lower()
    new_password = request.form.get("new_password") or ""
    confirm_password = request.form.get("confirm_password") or ""

    if not email or not new_password or not confirm_password:
        flash("All forgot password fields are required")
        return render_template("login.html", show_forgot=True, forgot_email=email)

    if new_password != confirm_password:
        flash("New password and confirm password must match")
        return render_template("login.html", show_forgot=True, forgot_email=email)

    if len(new_password) < 6:
        flash("New password must be at least 6 characters")
        return render_template("login.html", show_forgot=True, forgot_email=email)

    user = User.query.filter_by(email=email).first()
    if not user:
        flash("Email not found")
        return render_template("login.html", show_forgot=True, forgot_email=email)

    user.password = generate_password_hash(new_password)
    db.session.commit()
    flash("Password updated successfully. Please login.")
    return redirect(url_for("login"))


# ================= STUDENT DASHBOARD =================
@app.route("/student_dashboard")
def student_dashboard():
    if session.get("role") != "Student":
        return redirect(url_for("login"))

    student = get_current_student(session.get("user_id"))
    profile_complete = is_student_profile_complete(student)
    if not profile_complete:
        flash("Please complete your profile first")
        return redirect(url_for("student_profile", setup=1))

    return render_template(
        "student_dashboard.html",
        student=student,
        profile_complete=profile_complete,
        current_page="dashboard"
    )


# ================= STUDENT PROFILE VIEW =================
@app.route("/student_profile_view")
def student_profile_view():
    if session.get("role") != "Student":
        return redirect(url_for("login"))

    student = get_current_student(session.get("user_id"))
    return render_template(
        "student_profile_view.html",
        student=student,
        profile_complete=is_student_profile_complete(student),
        current_page="profile"
    )


@app.route("/student_download_profile_pdf")
def student_download_profile_pdf():
    if session.get("role") != "Student":
        return redirect(url_for("login"))

    student = get_current_student(session.get("user_id"))
    lines, _ = _student_export_payload(student)

    pdf_bytes = _build_simple_pdf("Student Total Details", lines)
    saved_pdf_path = _student_pdf_file_path(student)
    with open(saved_pdf_path, "wb") as pdf_file:
        pdf_file.write(pdf_bytes)

    filename = os.path.basename(saved_pdf_path)
    return Response(
        pdf_bytes,
        mimetype="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'}
    )


@app.route("/student_download_profile_excel")
def student_download_profile_excel():
    if session.get("role") != "Student":
        return redirect(url_for("login"))

    student = get_current_student(session.get("user_id"))
    _, rows = _student_export_payload(student)

    def _clean_cell(value):
        return str(value).replace("\t", " ").replace("\r", " ").replace("\n", " ").strip()

    tsv_lines = ["Section\tField\tValue"]
    for section, field, value in rows:
        tsv_lines.append(f"{_clean_cell(section)}\t{_clean_cell(field)}\t{_clean_cell(value)}")
    content = "\n".join(tsv_lines)

    return Response(
        content,
        mimetype="application/vnd.ms-excel",
        headers={"Content-Disposition": f'attachment; filename="student_{student.user_id}_total_details.xls"'}
    )


@app.route("/student_download_profile_word")
def student_download_profile_word():
    if session.get("role") != "Student":
        return redirect(url_for("login"))

    student = get_current_student(session.get("user_id"))
    lines, _ = _student_export_payload(student)
    doc_content = "\r\n".join(lines)

    return Response(
        doc_content.encode("utf-8"),
        mimetype="application/msword",
        headers={"Content-Disposition": f'attachment; filename="student_{student.user_id}_total_details.doc"'}
    )


@app.route("/student_pdf_options")
def student_pdf_options():
    if session.get("role") != "Student":
        return redirect(url_for("login"))

    student = get_current_student(session.get("user_id"))
    pdf_exists = os.path.exists(_student_pdf_file_path(student))
    return render_template(
        "student_pdf_actions.html",
        student=student,
        pdf_exists=pdf_exists,
        current_page="pdf"
    )


@app.route("/student_remove_profile_pdf", methods=["POST"])
def student_remove_profile_pdf():
    if session.get("role") != "Student":
        return redirect(url_for("login"))

    student = get_current_student(session.get("user_id"))
    pdf_path = _student_pdf_file_path(student)
    if os.path.exists(pdf_path):
        os.remove(pdf_path)
        flash("PDF removed successfully")
    else:
        flash("No PDF file found to remove")

    return redirect(url_for("student_pdf_options"))


# ================= STUDENT RESULTS =================
@app.route("/student_results")
def student_results():
    if session.get("role") != "Student":
        return redirect(url_for("login"))

    student = get_current_student(session.get("user_id"))
    return render_template(
        "student_results.html",
        student=student,
        results=student.results,
        marks=student.marks,
        attendance=student.attendance,
        profile_complete=is_student_profile_complete(student),
        current_page="results"
    )


# ================= STUDENT ATTACHMENT =================
@app.route("/student_attachment", methods=["GET", "POST"])
def student_attachment():
    if session.get("role") != "Student":
        return redirect(url_for("login"))

    student = get_current_student(session.get("user_id"))
    if request.method == "POST":
        files = request.files.getlist("photo_files")
        files = [f for f in files if f and f.filename]
        if not files:
            flash("Please choose one or more files")
            return redirect(url_for("student_attachment"))

        uploaded_count = 0
        for file in files:
            if not allowed_attachment_file(file.filename):
                continue

            original_name = secure_filename(file.filename)
            ext = original_name.rsplit(".", 1)[1].lower()
            saved_name = f"att_{student.user_id}_{uuid.uuid4().hex[:10]}.{ext}"
            save_path = os.path.join(app.config["UPLOAD_FOLDER"], saved_name)
            file.save(save_path)
            relative_path = os.path.join("uploads", saved_name).replace("\\", "/")

            db.session.add(StudentAttachment(
                student_id=student.id,
                file_name=original_name,
                file_path=relative_path
            ))

            if is_image_attachment(original_name):
                student.photo = relative_path
            uploaded_count += 1

        if uploaded_count == 0:
            flash("No valid files selected. Allowed: images, pdf, doc, xls, ppt, txt, zip, rar")
            return redirect(url_for("student_attachment"))

        db.session.commit()
        flash(f"{uploaded_count} file(s) uploaded successfully")
        return redirect(url_for("student_attachment"))

    attachments = (
        StudentAttachment.query
        .filter_by(student_id=student.id)
        .order_by(StudentAttachment.id.desc())
        .all()
    )

    return render_template(
        "student_attachment.html",
        student=student,
        attachments=attachments,
        is_image_attachment=is_image_attachment,
        profile_complete=is_student_profile_complete(student),
        current_page="attachment"
    )


@app.route("/student_attachment/delete/<int:attachment_id>", methods=["POST"])
def delete_student_attachment(attachment_id):
    if session.get("role") != "Student":
        return redirect(url_for("login"))

    student = get_current_student(session.get("user_id"))
    attachment = StudentAttachment.query.filter_by(id=attachment_id, student_id=student.id).first()
    if not attachment:
        flash("Attachment not found")
        return redirect(url_for("student_attachment"))

    removed_path = attachment.file_path
    upload_root = os.path.abspath(os.path.join(app.root_path, app.config["UPLOAD_FOLDER"]))
    target_path = os.path.abspath(os.path.join(app.static_folder, removed_path.replace("/", os.sep)))
    if target_path.startswith(upload_root) and os.path.exists(target_path):
        os.remove(target_path)

    db.session.delete(attachment)
    db.session.flush()

    if student.photo == removed_path:
        student.photo = None
        remaining = (
            StudentAttachment.query
            .filter_by(student_id=student.id)
            .order_by(StudentAttachment.id.desc())
            .all()
        )
        for item in remaining:
            if is_image_attachment(item.file_name):
                student.photo = item.file_path
                break

    db.session.commit()
    flash("Attachment removed successfully")
    return redirect(url_for("student_attachment"))


@app.route("/student_dashboard/upload_photo", methods=["POST"])
def student_dashboard_upload_photo():
    if session.get("role") != "Student":
        return redirect(url_for("login"))

    student = get_current_student(session.get("user_id"))
    file = request.files.get("photo_file")
    if not file or file.filename == "":
        flash("Please choose a passport photo file")
        return redirect(url_for("student_dashboard"))

    if not allowed_image_file(file.filename):
        flash("Only PNG, JPG, JPEG, GIF, WEBP files are allowed")
        return redirect(url_for("student_dashboard"))

    save_student_photo(student, file)
    flash("Passport photo uploaded successfully")
    return redirect(url_for("student_dashboard"))


# ================= STUDENT PROFILE EDIT =================
@app.route("/student_profile", methods=["GET", "POST"])
def student_profile():
    if session.get("role") != "Student":
        return redirect(url_for("login"))

    student = get_current_student(session.get("user_id"))
    current_user = User.query.get(session.get("user_id"))

    is_setup_mode = request.args.get("setup") == "1" or not is_student_profile_complete(student)

    if request.method == "POST":
        username = (request.form.get("username") or "").strip()
        if not username:
            flash("Name is required")
            return redirect(url_for("student_profile", setup=1 if is_setup_mode else None))

        if current_user:
            current_user.username = username
            session["username"] = username

        student.register_number = request.form.get("register_number")
        student.batch = request.form.get("batch") 
        student.course = request.form.get("course")
        student.branch = request.form.get("branch")
        student.gender = request.form.get("gender")
        student.dob = request.form.get("dob")
        student.hostel = request.form.get("hostel")
        student.bus = request.form.get("bus")
        student.admission_quota = request.form.get("admission_quota")
        student.first_graduate = request.form.get("first_graduate")
        student.personal_email = request.form.get("personal_email")
        student.college_email = request.form.get("college_email")
        student.mobile = request.form.get("mobile")
        student.address = request.form.get("address")
        student.blood_group = request.form.get("blood_group")
        student.nationality = request.form.get("nationality")
        student.father_name = request.form.get("father_name")
        student.mother_name = request.form.get("mother_name")
        student.parent_occupation = request.form.get("parent_occupation")
        student.parent_mobile = request.form.get("parent_mobile")
        student.email_id = request.form.get("email_id")
        student.semester = request.form.get("semester")
        student.admission_year = request.form.get("admission_year")
        student.previous_institution = request.form.get("previous_institution")
        student.internal_marks = request.form.get("internal_marks")
        student.semester_exam_marks = request.form.get("semester_exam_marks")
        student.cgpa_gpa = request.form.get("cgpa_gpa")
        student.arrears_backlogs = request.form.get("arrears_backlogs")
        student.tuition_fee = request.form.get("tuition_fee")
        student.bus_hostel_fee = request.form.get("bus_hostel_fee")
        student.scholarship_details = request.form.get("scholarship_details")
        student.scholarship_amount = request.form.get("scholarship_amount")
        student.hostel_name = request.form.get("hostel_name")
        student.room_number = request.form.get("room_number")
        student.roommates_count = request.form.get("roommates_count")
        student.warden_name = request.form.get("warden_name")
        student.warden_mobile = request.form.get("warden_mobile")
        student.sports_participation = request.form.get("sports_participation")
        student.club_memberships = request.form.get("club_memberships")
        student.achievements_awards = request.form.get("achievements_awards")
        student.events_participated = request.form.get("events_participated")
        student.project_details = request.form.get("project_details")
        student.projects_done = request.form.get("projects_done")
        student.internships = request.form.get("internships")
        student.certifications = request.form.get("certifications")
        student.skills = request.form.get("skills")
        student.warnings = request.form.get("warnings")
        student.complaints = request.form.get("complaints")
        student.actions_taken = request.form.get("actions_taken")

        db.session.commit()
        if is_setup_mode:
            flash("Profile saved successfully")
        else:
            flash("Student profile updated successfully")
        return redirect(url_for("student_profile_view"))

    return render_template(
        "student.html",
        student=student,
        is_setup_mode=is_setup_mode,
        results=student.results,
        marks=student.marks,
        attendance=student.attendance
    )


# ================= UPDATE RESULT =================
@app.route("/update_result/<int:result_id>", methods=["POST"])
def update_result(result_id):
    if session.get("role") != "Student":
        return redirect(url_for("login"))

    student = get_current_student(session.get("user_id"))
    result = Result.query.filter_by(id=result_id, student_id=student.id).first()
    if not result:
        flash("Result record not found")
        return redirect(url_for("student_profile"))

    result.semester = request.form.get("semester")
    result.subject_code = request.form.get("subject_code")
    result.subject_name = request.form.get("subject_name")
    result.grade = request.form.get("grade")
    result.result_status = request.form.get("result_status")
    result.month_year = request.form.get("month_year")
    db.session.commit()
    flash("Result updated successfully")
    return redirect(url_for("student_profile"))


# ================= UPDATE MARKS =================
@app.route("/update_marks/<int:marks_id>", methods=["POST"])
def update_marks(marks_id):
    if session.get("role") != "Student":
        return redirect(url_for("login"))

    student = get_current_student(session.get("user_id"))
    marks = Marks.query.filter_by(id=marks_id, student_id=student.id).first()
    if not marks:
        flash("Marks record not found")
        return redirect(url_for("student_profile"))

    subject = request.form.get("subject")
    marks_value = request.form.get("marks")
    try:
        marks_value = int(marks_value)
    except (TypeError, ValueError):
        flash("Marks must be a number")
        return redirect(url_for("student_profile"))

    marks.subject = subject
    marks.marks = marks_value
    db.session.commit()
    flash("Marks updated successfully")
    return redirect(url_for("student_profile"))


# ================= UPDATE ATTENDANCE =================
@app.route("/update_attendance/<int:attendance_id>", methods=["POST"])
def update_attendance(attendance_id):
    if session.get("role") != "Student":
        return redirect(url_for("login"))

    student = get_current_student(session.get("user_id"))
    attendance = Attendance.query.filter_by(id=attendance_id, student_id=student.id).first()
    if not attendance:
        flash("Attendance record not found")
        return redirect(url_for("student_profile"))

    subject = request.form.get("subject")
    percentage = request.form.get("attendance_percentage")
    try:
        percentage = float(percentage)
    except (TypeError, ValueError):
        flash("Attendance must be a number")
        return redirect(url_for("student_profile"))

    attendance.subject = subject
    attendance.attendance_percentage = percentage
    db.session.commit()
    flash("Attendance updated successfully")
    return redirect(url_for("student_profile"))


# ================= ADD RESULT =================
@app.route("/add_result", methods=["POST"])
def add_result():
    if session.get("role") != "Student":
        return redirect(url_for("login"))

    student = get_current_student(session.get("user_id"))

    if not student:
        flash("Student profile not found")
        return redirect(url_for("student_results"))

    new_result = Result(
        semester=request.form.get("semester"),
        subject_code=request.form.get("subject_code"),
        subject_name=request.form.get("subject_name"),
        grade=request.form.get("grade"),
        result_status=request.form.get("result_status"),
        month_year=request.form.get("month_year"),
        student_id=student.id
    )

    db.session.add(new_result)
    db.session.commit()

    flash("Result Added Successfully")
    return redirect(url_for("student_results"))


# ================= ADD MARKS =================
@app.route("/add_marks", methods=["POST"])
def add_marks():
    if session.get("role") != "Student":
        return redirect(url_for("login"))

    student = get_current_student(session.get("user_id"))
    if not student:
        flash("Student profile not found")
        return redirect(url_for("student_results"))

    subject = request.form.get("subject")
    marks_value = request.form.get("marks")

    if not subject or marks_value is None:
        flash("Subject and marks are required")
        return redirect(url_for("student_results"))

    try:
        marks_value = int(marks_value)
    except ValueError:
        flash("Marks must be a number")
        return redirect(url_for("student_results"))

    db.session.add(Marks(student_id=student.id, subject=subject, marks=marks_value))
    db.session.commit()
    flash("Marks added successfully")
    return redirect(url_for("student_results"))


# ================= ADD ATTENDANCE =================
@app.route("/add_attendance", methods=["POST"])
def add_attendance():
    if session.get("role") != "Student":
        return redirect(url_for("login"))

    student = get_current_student(session.get("user_id"))
    if not student:
        flash("Student profile not found")
        return redirect(url_for("student_results"))

    subject = request.form.get("subject")
    percentage = request.form.get("attendance_percentage")

    if not subject or percentage is None:
        flash("Subject and attendance are required")
        return redirect(url_for("student_results"))

    try:
        percentage = float(percentage)
    except ValueError:
        flash("Attendance must be a number")
        return redirect(url_for("student_results"))

    db.session.add(Attendance(student_id=student.id, subject=subject, attendance_percentage=percentage))
    db.session.commit()
    flash("Attendance added successfully")
    return redirect(url_for("student_results"))


# ================= STAFF DASHBOARD =================
@app.route("/staff_dashboard")
def staff_dashboard():
    if session.get("role") != "Staff":
        return redirect(url_for("login"))

    register_query = (request.args.get("register_number") or "").strip()
    students_query = StudentProfile.query
    if register_query:
        students_query = students_query.filter(StudentProfile.register_number.ilike(f"%{register_query}%"))
    students = students_query.all()

    current_staff = User.query.get(session.get("user_id"))
    staff_profile = get_current_staff_profile(session.get("user_id"))
    return render_template(
        "staff_dashboard.html",
        students=students,
        staff_email=current_staff.email if current_staff else "-",
        staff_profile=staff_profile,
        register_query=register_query
    )


# ================= STAFF PROFILE PHOTO =================
@app.route("/staff/upload_photo", methods=["POST"])
def staff_upload_photo():
    if session.get("role") != "Staff":
        return redirect(url_for("login"))

    staff_profile = get_current_staff_profile(session.get("user_id"))
    file = request.files.get("photo_file")
    if not file or file.filename == "":
        flash("Please choose a photo")
        return redirect(url_for("staff_dashboard"))

    if not allowed_image_file(file.filename):
        flash("Only PNG, JPG, JPEG, GIF, WEBP files are allowed")
        return redirect(url_for("staff_dashboard"))

    original_name = secure_filename(file.filename)
    ext = original_name.rsplit(".", 1)[1].lower()
    saved_name = f"staff_{staff_profile.user_id}_{uuid.uuid4().hex[:8]}.{ext}"
    save_path = os.path.join(app.config["UPLOAD_FOLDER"], saved_name)
    file.save(save_path)

    staff_profile.photo = os.path.join("uploads", saved_name).replace("\\", "/")
    db.session.commit()
    flash("Staff photo updated")
    return redirect(url_for("staff_dashboard"))


# ================= STAFF REMOVE PHOTO =================
@app.route("/staff/remove_photo", methods=["POST"])
def staff_remove_photo():
    if session.get("role") != "Staff":
        return redirect(url_for("login"))

    staff_profile = get_current_staff_profile(session.get("user_id"))
    staff_profile.photo = None
    db.session.commit()
    flash("Staff photo removed")
    return redirect(url_for("staff_dashboard"))


# ================= STAFF DELETE STUDENT =================
@app.route("/staff/delete_student/<int:student_id>", methods=["POST"])
def staff_delete_student(student_id):
    if session.get("role") != "Staff":
        return redirect(url_for("login"))

    student = StudentProfile.query.get(student_id)
    if not student:
        flash("Student not found")
        return redirect(url_for("staff_dashboard"))

    target_user_id = student.user_id
    db.session.delete(student)

    student_role = Role.query.filter_by(name="Student").first()
    if student_role:
        UserRole.query.filter_by(user_id=target_user_id, role_id=student_role.role_id).delete()

    if UserRole.query.filter_by(user_id=target_user_id).count() == 0:
        user = User.query.get(target_user_id)
        if user:
            db.session.delete(user)

    db.session.commit()
    flash("Student removed successfully")
    return redirect(url_for("staff_dashboard"))


# ================= STAFF STUDENT DETAIL =================
@app.route("/staff/student/<int:student_id>")
def staff_student_detail(student_id):
    if session.get("role") != "Staff":
        return redirect(url_for("login"))

    student = StudentProfile.query.get_or_404(student_id)
    return render_template(
        "staff_student_detail.html",
        student=student,
        results=student.results,
        marks=student.marks,
        attendance=student.attendance
    )


# ================= STAFF ADD RESULT =================
@app.route("/staff/student/<int:student_id>/add_result", methods=["POST"])
def staff_add_result(student_id):
    if session.get("role") != "Staff":
        return redirect(url_for("login"))

    student = StudentProfile.query.get_or_404(student_id)
    db.session.add(Result(
        semester=request.form.get("semester"),
        subject_code=request.form.get("subject_code"),
        subject_name=request.form.get("subject_name"),
        grade=request.form.get("grade"),
        result_status=request.form.get("result_status"),
        month_year=request.form.get("month_year"),
        student_id=student.id
    ))
    db.session.commit()
    flash("Result added by staff")
    return redirect(url_for("staff_student_detail", student_id=student_id))


# ================= STAFF ADD MARKS =================
@app.route("/staff/student/<int:student_id>/add_marks", methods=["POST"])
def staff_add_marks(student_id):
    if session.get("role") != "Staff":
        return redirect(url_for("login"))

    student = StudentProfile.query.get_or_404(student_id)
    try:
        marks_value = int(request.form.get("marks"))
    except (TypeError, ValueError):
        flash("Marks must be a number")
        return redirect(url_for("staff_student_detail", student_id=student_id))

    db.session.add(Marks(
        student_id=student.id,
        subject=request.form.get("subject"),
        marks=marks_value
    ))
    db.session.commit()
    flash("Marks added by staff")
    return redirect(url_for("staff_student_detail", student_id=student_id))


# ================= STAFF ADD ATTENDANCE =================
@app.route("/staff/student/<int:student_id>/add_attendance", methods=["POST"])
def staff_add_attendance(student_id):
    if session.get("role") != "Staff":
        return redirect(url_for("login"))

    student = StudentProfile.query.get_or_404(student_id)
    try:
        percentage = float(request.form.get("attendance_percentage"))
    except (TypeError, ValueError):
        flash("Attendance must be a number")
        return redirect(url_for("staff_student_detail", student_id=student_id))

    db.session.add(Attendance(
        student_id=student.id,
        subject=request.form.get("subject"),
        attendance_percentage=percentage
    ))
    db.session.commit()
    flash("Attendance added by staff")
    return redirect(url_for("staff_student_detail", student_id=student_id))


# ================= ADMIN DASHBOARD =================
@app.route("/admin_dashboard")
def admin_dashboard():
    if session.get("role") != "Admin":
        return redirect(url_for("login"))

    admin_user = User.query.get(session.get("user_id"))
    total_students = StudentProfile.query.count()
    total_staff = StaffProfile.query.count()
    total_users = User.query.count()
    total_results = Result.query.count()
    total_marks = Marks.query.count()
    total_attendance = Attendance.query.count()
    recent_users = User.query.order_by(User.user_id.desc()).limit(8).all()
    admin_members = (
        db.session.query(User)
        .join(UserRole, UserRole.user_id == User.user_id)
        .join(Role, Role.role_id == UserRole.role_id)
        .filter(Role.name == "Admin")
        .order_by(User.user_id.desc())
        .all()
    )

    return render_template(
        "admin.html",
        total_students=total_students,
        total_staff=total_staff,
        total_users=total_users,
        total_results=total_results,
        total_marks=total_marks,
        total_attendance=total_attendance,
        recent_users=recent_users,
        admin_email=admin_user.email if admin_user else "-",
        admin_members=admin_members
    )


# ================= ADMIN ADD ADMIN MEMBER =================
@app.route("/admin/add_admin", methods=["POST"])
def admin_add_member():
    if session.get("role") != "Admin":
        return redirect(url_for("login"))

    username = (request.form.get("username") or "").strip()
    email = (request.form.get("email") or "").strip().lower()
    password = request.form.get("password") or ""

    if not username or not email or not password:
        flash("Username, email, and password are required")
        return redirect(url_for("admin_dashboard"))

    if len(password) < 6:
        flash("Password must be at least 6 characters")
        return redirect(url_for("admin_dashboard"))

    if User.query.filter_by(email=email).first():
        flash("Email already exists")
        return redirect(url_for("admin_dashboard"))

    admin_role = Role.query.filter_by(name="Admin").first()
    if not admin_role:
        flash("Admin role not found")
        return redirect(url_for("admin_dashboard"))

    try:
        new_user = User(
            username=username,
            email=email,
            password=generate_password_hash(password)
        )
        db.session.add(new_user)
        db.session.flush()
        db.session.add(UserRole(user_id=new_user.user_id, role_id=admin_role.role_id))
        db.session.commit()
        flash("New admin member added successfully")
    except Exception:
        db.session.rollback()
        flash("Unable to add admin member")

    return redirect(url_for("admin_dashboard"))


# ================= ADMIN REMOVE ADMIN MEMBER =================
@app.route("/admin/remove_admin/<int:user_id>", methods=["POST"])
def admin_remove_member(user_id):
    if session.get("role") != "Admin":
        return redirect(url_for("login"))

    if user_id == session.get("user_id"):
        flash("You cannot remove your current admin account")
        return redirect(url_for("admin_dashboard"))

    target_admin = User.query.get(user_id)
    if not target_admin:
        flash("Admin user not found")
        return redirect(url_for("admin_dashboard"))

    admin_role = Role.query.filter_by(name="Admin").first()
    if not admin_role:
        flash("Admin role not found")
        return redirect(url_for("admin_dashboard"))

    has_admin_role = UserRole.query.filter_by(user_id=target_admin.user_id, role_id=admin_role.role_id).first()
    if not has_admin_role:
        flash("Selected user is not an admin")
        return redirect(url_for("admin_dashboard"))

    password = request.form.get("password") or ""
    if not password:
        flash("Password is required to remove admin")
        return redirect(url_for("admin_dashboard"))

    if not check_password_hash(target_admin.password, password):
        flash("Invalid password for selected admin email")
        return redirect(url_for("admin_dashboard"))

    try:
        admin_profile = AdminProfile.query.filter_by(user_id=target_admin.user_id).first()
        if admin_profile:
            db.session.delete(admin_profile)

        # Remove only Admin role mapping. Keep user account and other roles intact.
        UserRole.query.filter_by(user_id=target_admin.user_id, role_id=admin_role.role_id).delete()
        db.session.commit()
        flash("Admin role removed successfully")
    except Exception:
        db.session.rollback()
        flash("Unable to remove admin role")

    return redirect(url_for("admin_dashboard"))


# ================= ADMIN VIEW STUDENTS =================
@app.route("/admin/students")
def admin_students():
    if session.get("role") != "Admin":
        return redirect(url_for("login"))

    register_query = (request.args.get("register_number") or "").strip()
    students_query = StudentProfile.query
    if register_query:
        students_query = students_query.filter(StudentProfile.register_number.ilike(f"%{register_query}%"))
    students = students_query.order_by(StudentProfile.id.desc()).all()
    return render_template("admin_students.html", students=students, register_query=register_query)


# ================= ADMIN VIEW STAFF =================
@app.route("/admin/staff")
def admin_staff():
    if session.get("role") != "Admin":
        return redirect(url_for("login"))

    email_query = (request.args.get("email") or "").strip()
    status_query = (request.args.get("status") or "").strip()
    staff_query = db.session.query(StaffProfile).join(User, User.user_id == StaffProfile.user_id)
    if email_query:
        staff_query = staff_query.filter(User.email.ilike(f"%{email_query}%"))
    if status_query in {"Pending", "Approved", "Rejected"}:
        staff_query = staff_query.filter(StaffProfile.approval_status == status_query)
    staff_members = staff_query.order_by(StaffProfile.id.desc()).all()
    return render_template(
        "admin_staff.html",
        staff_members=staff_members,
        email_query=email_query,
        status_query=status_query
    )


@app.route("/admin/approve_staff/<int:staff_id>", methods=["POST"])
def admin_approve_staff(staff_id):
    if session.get("role") != "Admin":
        return redirect(url_for("login"))

    staff_profile = StaffProfile.query.get(staff_id)
    if not staff_profile:
        flash("Staff record not found")
        return redirect(url_for("admin_staff"))

    staff_profile.approval_status = "Approved"
    db.session.commit()
    flash("Staff request approved")
    return redirect(url_for("admin_staff"))


@app.route("/admin/reject_staff/<int:staff_id>", methods=["POST"])
def admin_reject_staff(staff_id):
    if session.get("role") != "Admin":
        return redirect(url_for("login"))

    staff_profile = StaffProfile.query.get(staff_id)
    if not staff_profile:
        flash("Staff record not found")
        return redirect(url_for("admin_staff"))

    staff_profile.approval_status = "Rejected"
    db.session.commit()
    flash("Staff request rejected")
    return redirect(url_for("admin_staff"))


# ================= DELETE USER =================
@app.route("/admin/delete_user/<int:user_id>", methods=["POST"])
def delete_user(user_id):
    if session.get("role") != "Admin":
        return redirect(url_for("login"))

    if user_id == session.get("user_id"):
        flash("You cannot delete your current admin account")
        return redirect(url_for("admin_dashboard"))

    user = User.query.get(user_id)
    if not user:
        flash("User not found")
        return redirect(url_for("admin_dashboard"))

    try:
        # Delete dependent profile data first to avoid FK errors.
        student = StudentProfile.query.filter_by(user_id=user.user_id).first()
        if student:
            db.session.delete(student)

        staff = StaffProfile.query.filter_by(user_id=user.user_id).first()
        if staff:
            db.session.delete(staff)

        admin_profile = AdminProfile.query.filter_by(user_id=user.user_id).first()
        if admin_profile:
            db.session.delete(admin_profile)

        UserRole.query.filter_by(user_id=user.user_id).delete()

        db.session.delete(user)
        db.session.commit()
        flash("User deleted successfully")
    except Exception:
        db.session.rollback()
        flash("Unable to delete user due to linked records")

    return redirect(url_for("admin_dashboard"))


# ================= LOGOUT =================
@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


# ================= RUN =================
if __name__ == "__main__":
    app.run(debug=True, port=5001)
