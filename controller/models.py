from .database import db


# ---------------- USER TABLE ----------------
class User(db.Model):
    __tablename__ = "user"

    user_id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(60), nullable=False)
    email = db.Column(db.String(80), nullable=False, unique=True)
    password = db.Column(db.String(200), nullable=False)

    # Relationships
    student_profile = db.relationship("StudentProfile", backref="user", uselist=False)
    staff_profile = db.relationship("StaffProfile", backref="user", uselist=False)
    admin_profile = db.relationship("AdminProfile", backref="user", uselist=False)


# ---------------- ROLE TABLE ----------------
class Role(db.Model):
    __tablename__ = "role"

    role_id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), nullable=False, unique=True)


# ---------------- USER ROLE TABLE ----------------
class UserRole(db.Model):
    __tablename__ = "user_role"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.user_id"), nullable=False)
    role_id = db.Column(db.Integer, db.ForeignKey("role.role_id"), nullable=False)


# ---------------- STUDENT PROFILE ----------------
class StudentProfile(db.Model):
    __tablename__ = "student_profile"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.user_id"), nullable=False)

    register_number = db.Column(db.String(50))
    batch = db.Column(db.String(20))
    course = db.Column(db.String(50))
    branch = db.Column(db.String(50))
    gender = db.Column(db.String(20))
    dob = db.Column(db.String(20))
    hostel = db.Column(db.String(20))
    bus = db.Column(db.String(20))
    admission_quota = db.Column(db.String(50))
    first_graduate = db.Column(db.String(20))
    personal_email = db.Column(db.String(100))
    college_email = db.Column(db.String(100))
    mobile = db.Column(db.String(20))
    address = db.Column(db.Text)
    photo = db.Column(db.String(200))
    blood_group = db.Column(db.String(20))
    nationality = db.Column(db.String(50))

    father_name = db.Column(db.String(100))
    mother_name = db.Column(db.String(100))
    parent_occupation = db.Column(db.String(100))
    parent_mobile = db.Column(db.String(20))
    email_id = db.Column(db.String(100))

    semester = db.Column(db.String(20))
    admission_year = db.Column(db.String(20))
    previous_institution = db.Column(db.String(150))
    internal_marks = db.Column(db.String(50))
    semester_exam_marks = db.Column(db.String(50))
    cgpa_gpa = db.Column(db.String(20))
    arrears_backlogs = db.Column(db.String(100))

    tuition_fee = db.Column(db.String(50))
    bus_hostel_fee = db.Column(db.String(50))
    scholarship_category = db.Column(db.String(200))
    scholarship_amount = db.Column(db.String(50))

    hostel_name = db.Column(db.String(100))
    room_number = db.Column(db.String(20))
    roommates_count = db.Column(db.String(20))
    warden_name = db.Column(db.String(100))
    warden_mobile = db.Column(db.String(20))

    sports_participation = db.Column(db.String(200))
    club_memberships = db.Column(db.String(200))
    achievements_awards = db.Column(db.String(200))
    events_participated = db.Column(db.String(200))

    project_details = db.Column(db.Text)
    projects_done = db.Column(db.String(200))
    internships = db.Column(db.String(200))
    certifications = db.Column(db.String(200))
    skills = db.Column(db.String(200))

    warnings = db.Column(db.String(200))
    complaints = db.Column(db.String(200))
    actions_taken = db.Column(db.String(200))

    # Relationships
    results = db.relationship("Result", backref="student", lazy=True, cascade="all, delete")
    marks = db.relationship("Marks", backref="student", lazy=True, cascade="all, delete")
    attendance = db.relationship("Attendance", backref="student", lazy=True, cascade="all, delete")
    attachments = db.relationship("StudentAttachment", backref="student", lazy=True, cascade="all, delete")


# ---------------- RESULT TABLE ----------------
class Result(db.Model):
    __tablename__ = "result"

    id = db.Column(db.Integer, primary_key=True)
    semester = db.Column(db.String(20))
    subject_code = db.Column(db.String(20))
    subject_name = db.Column(db.String(100))
    grade = db.Column(db.String(10))
    result_status = db.Column(db.String(20))
    month_year = db.Column(db.String(20))

    student_id = db.Column(db.Integer, db.ForeignKey("student_profile.id"), nullable=False)


# ---------------- STAFF PROFILE ----------------
class StaffProfile(db.Model):
    __tablename__ = "staff_profile"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.user_id"), nullable=False)

    staff_id = db.Column(db.String(50))
    department = db.Column(db.String(50))
    designation = db.Column(db.String(50))
    subjects = db.Column(db.String(200))
    contact = db.Column(db.String(20))
    photo = db.Column(db.String(200))
    approval_status = db.Column(db.String(20), default="Pending")


# ---------------- MARKS ----------------
class Marks(db.Model):
    __tablename__ = "marks"

    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey("student_profile.id"), nullable=False)
    subject = db.Column(db.String(100))
    marks = db.Column(db.Integer)


# ---------------- ATTENDANCE ----------------
class Attendance(db.Model):
    __tablename__ = "attendance"

    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey("student_profile.id"), nullable=False)
    subject = db.Column(db.String(100))
    attendance_percentage = db.Column(db.Float)


# ---------------- STUDENT ATTACHMENTS ----------------
class StudentAttachment(db.Model):
    __tablename__ = "student_attachment"

    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey("student_profile.id"), nullable=False)
    file_name = db.Column(db.String(255), nullable=False)
    file_path = db.Column(db.String(255), nullable=False)


# ---------------- ADMIN PROFILE ----------------
class AdminProfile(db.Model):
    __tablename__ = "admin_profile"

    id = db.Column(db.Integer, primary_key=True)

    user_id = db.Column(
        db.Integer,
        db.ForeignKey("user.user_id", ondelete="CASCADE"),
        nullable=False
    )

    admin_id = db.Column(db.String(50), unique=True)
    designation = db.Column(db.String(100))
    office_contact = db.Column(db.String(20))
    office_email = db.Column(db.String(100))
    office_address = db.Column(db.Text)

    def __repr__(self):
        return f"<AdminProfile {self.admin_id}>"
