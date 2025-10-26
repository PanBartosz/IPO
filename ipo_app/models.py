from datetime import datetime
import enum

from .extensions import db


class TimestampMixin:
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)


class Student(db.Model, TimestampMixin):
    __tablename__ = "students"

    id = db.Column(db.Integer, primary_key=True)
    country = db.Column(db.String(100), nullable=False)
    first_name = db.Column(db.String(80), nullable=False)
    last_name = db.Column(db.String(80), nullable=False)
    email = db.Column(db.String(255), nullable=False, unique=True)
    school = db.Column(db.String(120), nullable=False)
    gender = db.Column(db.String(10), nullable=False)
    date_of_birth = db.Column(db.Date, nullable=False)
    essay_language = db.Column(db.String(20), nullable=False)
    keyboard_preference = db.Column(db.String(20), nullable=False)
    meal_preference = db.Column(db.String(30), nullable=False)
    special_needs = db.Column(db.Text, nullable=True)
    is_absent = db.Column(db.Boolean, nullable=False, default=False)

    upload_username = db.Column(db.String(64), nullable=True, unique=True)
    upload_password_hash = db.Column(db.String(255), nullable=True)
    upload_token = db.Column(db.String(64), nullable=True, unique=True)
    uploaded_filename = db.Column(db.String(255), nullable=True)
    uploaded_at = db.Column(db.DateTime, nullable=True)
    essay_finalized = db.Column(db.Boolean, nullable=False, default=False)
    essay_finalized_at = db.Column(db.DateTime, nullable=True)

    scores = db.relationship("EssayScore", back_populates="student", cascade="all, delete-orphan")


class TeacherMessageStatus(enum.StrEnum):
    ACTIVE = "active"
    ARCHIVED = "archived"


class TeacherMessagePriority(enum.StrEnum):
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"


class TeacherMessage(db.Model, TimestampMixin):
    __tablename__ = "teacher_messages"

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    body = db.Column(db.Text, nullable=False)
    priority = db.Column(db.Enum(TeacherMessagePriority), nullable=False, default=TeacherMessagePriority.NORMAL)
    status = db.Column(db.Enum(TeacherMessageStatus), nullable=False, default=TeacherMessageStatus.ACTIVE)
    deliver_to_all = db.Column(db.Boolean, nullable=False, default=True)
    teacher_id = db.Column(db.Integer, db.ForeignKey("teachers.id", ondelete="SET NULL"), nullable=True)
    category = db.Column(db.String(80), nullable=True)

    creator_id = db.Column(db.String(120), nullable=True)
    updater_id = db.Column(db.String(120), nullable=True)

    teacher = db.relationship("Teacher", back_populates="messages")


class TeacherMessageTemplate(db.Model, TimestampMixin):
    __tablename__ = "teacher_message_templates"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False, unique=True)
    title = db.Column(db.String(200), nullable=False)
    body = db.Column(db.Text, nullable=False)
    category = db.Column(db.String(80), nullable=True)


class AppSetting(db.Model, TimestampMixin):
    __tablename__ = "app_settings"

    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(120), unique=True, nullable=False)
    value = db.Column(db.Text, nullable=True)


class Teacher(db.Model, TimestampMixin):
    __tablename__ = "teachers"

    id = db.Column(db.Integer, primary_key=True)
    country = db.Column(db.String(100), nullable=False)
    first_name = db.Column(db.String(80), nullable=False)
    last_name = db.Column(db.String(80), nullable=False)
    email = db.Column(db.String(255), nullable=False, unique=True)
    school = db.Column(db.String(120), nullable=False)
    gender = db.Column(db.String(10), nullable=False)
    languages = db.Column(db.String(120), nullable=False)
    prior_ipo_assessor = db.Column(db.Boolean, nullable=False, default=False)
    meal_preference = db.Column(db.String(30), nullable=False)
    special_needs = db.Column(db.Text, nullable=True)
    tshirt_size = db.Column(db.String(5), nullable=False)
    delegation_leader = db.Column(db.Boolean, nullable=False, default=False)
    is_absent = db.Column(db.Boolean, nullable=False, default=False)
    portal_username = db.Column(db.String(64), unique=True)
    portal_password_hash = db.Column(db.String(255))
    portal_token = db.Column(db.String(64), unique=True)
    portal_last_login = db.Column(db.DateTime)

    language_entries = db.relationship("TeacherLanguage", back_populates="teacher", cascade="all, delete-orphan")
    assignments = db.relationship(
        "ReadingGroupMember",
        back_populates="teacher",
        cascade="all, delete-orphan",
    )
    scores = db.relationship("EssayScore", back_populates="teacher", cascade="all, delete-orphan")
    messages = db.relationship("TeacherMessage", back_populates="teacher", cascade="all, delete-orphan")


class TeacherLanguage(db.Model, TimestampMixin):
    __tablename__ = "teacher_languages"

    id = db.Column(db.Integer, primary_key=True)
    teacher_id = db.Column(db.Integer, db.ForeignKey("teachers.id", ondelete="CASCADE"), nullable=False)
    language = db.Column(db.String(20), nullable=False)

    teacher = db.relationship("Teacher", back_populates="language_entries")

    __table_args__ = (db.UniqueConstraint("teacher_id", "language", name="uq_teacher_language"),)


class Stage(enum.StrEnum):
    STAGE_1 = "stage_1"
    STAGE_2 = "stage_2"


class PlannerStatus(enum.StrEnum):
    DRAFT = "draft"
    PUBLISHED = "published"


class GroupMemberRole(enum.StrEnum):
    READER = "reader"
    BACKUP = "backup"
    LEADER = "leader"


class ReadingGroup(db.Model, TimestampMixin):
    __tablename__ = "reading_groups"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    stage = db.Column(db.Enum(Stage), nullable=False, default=Stage.STAGE_1)
    language = db.Column(db.String(20), nullable=False)
    target_essay_load = db.Column(db.Integer, nullable=False, default=5)
    status = db.Column(db.Enum(PlannerStatus), nullable=False, default=PlannerStatus.DRAFT)
    auto_generated = db.Column(db.Boolean, nullable=False, default=True)
    locked = db.Column(db.Boolean, nullable=False, default=False)
    allow_same_country = db.Column(db.Boolean, nullable=False, default=False)
    notes = db.Column(db.Text)
    batch_id = db.Column(db.Integer, db.ForeignKey("assignment_batches.id", ondelete="CASCADE"), nullable=False)

    members = db.relationship(
        "ReadingGroupMember",
        back_populates="group",
        cascade="all, delete-orphan",
        order_by="ReadingGroupMember.id",
    )
    assignments = db.relationship("EssayAssignment", back_populates="group")
    batch = db.relationship("AssignmentBatch", back_populates="groups")


class ReadingGroupMember(db.Model, TimestampMixin):
    __tablename__ = "reading_group_members"

    id = db.Column(db.Integer, primary_key=True)
    group_id = db.Column(db.Integer, db.ForeignKey("reading_groups.id", ondelete="CASCADE"), nullable=False)
    teacher_id = db.Column(db.Integer, db.ForeignKey("teachers.id", ondelete="CASCADE"), nullable=False)
    role = db.Column(db.Enum(GroupMemberRole), nullable=False, default=GroupMemberRole.READER)
    active = db.Column(db.Boolean, nullable=False, default=True)

    group = db.relationship("ReadingGroup", back_populates="members")
    teacher = db.relationship("Teacher", back_populates="assignments")

    __table_args__ = (db.UniqueConstraint("group_id", "teacher_id", name="uq_group_member"),)


class AssignmentBatch(db.Model, TimestampMixin):
    __tablename__ = "assignment_batches"

    id = db.Column(db.Integer, primary_key=True)
    stage = db.Column(db.Enum(Stage), nullable=False, default=Stage.STAGE_1)
    status = db.Column(db.Enum(PlannerStatus), nullable=False, default=PlannerStatus.DRAFT)
    name = db.Column(db.String(120), nullable=False)
    notes = db.Column(db.Text)
    created_by = db.Column(db.String(120))
    published_at = db.Column(db.DateTime)

    assignments = db.relationship("EssayAssignment", back_populates="batch", cascade="all, delete-orphan")
    groups = db.relationship("ReadingGroup", back_populates="batch", cascade="all, delete-orphan")


class EssayAssignment(db.Model, TimestampMixin):
    __tablename__ = "essay_assignments"

    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey("students.id", ondelete="CASCADE"), nullable=False)
    group_id = db.Column(db.Integer, db.ForeignKey("reading_groups.id", ondelete="SET NULL"))
    batch_id = db.Column(db.Integer, db.ForeignKey("assignment_batches.id", ondelete="CASCADE"), nullable=False)
    stage = db.Column(db.Enum(Stage), nullable=False, default=Stage.STAGE_1)
    manual_override = db.Column(db.Boolean, nullable=False, default=False)
    status = db.Column(db.Enum(PlannerStatus), nullable=False, default=PlannerStatus.DRAFT)
    needs_additional_reading = db.Column(db.Boolean, nullable=False, default=False)
    stage_two_candidate = db.Column(db.Boolean, nullable=False, default=False)
    stage_three_recommended = db.Column(db.Boolean, nullable=False, default=False)
    stage1_locked = db.Column(db.Boolean, nullable=False, default=False)
    stage2_locked = db.Column(db.Boolean, nullable=False, default=False)

    student = db.relationship("Student")
    group = db.relationship("ReadingGroup", back_populates="assignments")
    batch = db.relationship("AssignmentBatch", back_populates="assignments")
    scores = db.relationship("EssayScore", back_populates="assignment", cascade="all, delete-orphan")
    extra_readers = db.relationship(
        "EssayAssignmentExtraReader",
        back_populates="assignment",
        cascade="all, delete-orphan",
    )

    __table_args__ = (db.UniqueConstraint("student_id", "batch_id", name="uq_assignment_student_batch"),)


class ActivityLog(db.Model, TimestampMixin):
    __tablename__ = "activity_logs"

    id = db.Column(db.Integer, primary_key=True)
    actor = db.Column(db.String(120), nullable=False, default="system")
    action = db.Column(db.String(120), nullable=False)
    object_type = db.Column(db.String(120))
    object_id = db.Column(db.String(120))
    description = db.Column(db.Text)
    details = db.Column(db.JSON)


class EssayScore(db.Model, TimestampMixin):
    __tablename__ = "essay_scores"

    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey("students.id", ondelete="CASCADE"), nullable=False)
    teacher_id = db.Column(db.Integer, db.ForeignKey("teachers.id", ondelete="CASCADE"), nullable=False)
    assignment_id = db.Column(db.Integer, db.ForeignKey("essay_assignments.id", ondelete="SET NULL"))
    stage = db.Column(db.Enum(Stage), nullable=False, default=Stage.STAGE_1)
    score = db.Column(db.Float, nullable=True)
    comments = db.Column(db.Text)
    submitted_at = db.Column(db.DateTime, nullable=True)
    teacher_finalized = db.Column(db.Boolean, nullable=False, default=False)
    teacher_finalized_at = db.Column(db.DateTime, nullable=True)
    admin_entered = db.Column(db.Boolean, nullable=False, default=False)
    admin_override = db.Column(db.Boolean, nullable=False, default=False)
    admin_updated_at = db.Column(db.DateTime, nullable=True)
    locked_by_admin = db.Column(db.Boolean, nullable=False, default=False)
    student = db.relationship("Student", back_populates="scores")
    teacher = db.relationship("Teacher", back_populates="scores")
    assignment = db.relationship("EssayAssignment", back_populates="scores")

    __table_args__ = (db.UniqueConstraint("student_id", "teacher_id", "stage", name="uq_score_student_teacher_stage"),)


class EssayAssignmentExtraReader(db.Model, TimestampMixin):
    __tablename__ = "essay_assignment_extra_readers"

    id = db.Column(db.Integer, primary_key=True)
    assignment_id = db.Column(db.Integer, db.ForeignKey("essay_assignments.id", ondelete="CASCADE"), nullable=False)
    teacher_id = db.Column(db.Integer, db.ForeignKey("teachers.id", ondelete="CASCADE"), nullable=False)
    stage = db.Column(db.String(16), nullable=False, default=Stage.STAGE_1.value)

    assignment = db.relationship("EssayAssignment", back_populates="extra_readers")
    teacher = db.relationship("Teacher")

    __table_args__ = (
        db.UniqueConstraint("assignment_id", "teacher_id", "stage", name="uq_extra_reader_assignment_teacher_stage"),
    )
