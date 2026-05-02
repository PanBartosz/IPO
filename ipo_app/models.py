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
    sex_document = db.Column(db.String(10), nullable=True)
    accommodation_room_sharing = db.Column(db.String(32), nullable=True)
    date_of_birth = db.Column(db.Date, nullable=False)
    essay_language = db.Column(db.String(20), nullable=False)
    keyboard_preference = db.Column(db.String(20), nullable=False)
    meal_preference = db.Column(db.String(30), nullable=False)
    special_needs = db.Column(db.Text, nullable=True)
    is_absent = db.Column(db.Boolean, nullable=False, default=False)

    accepted_ethics = db.Column(db.Boolean, nullable=False, default=False)
    accepted_ethics_at = db.Column(db.DateTime, nullable=True)
    gdpr_acknowledged = db.Column(db.Boolean, nullable=False, default=False)
    gdpr_acknowledged_at = db.Column(db.DateTime, nullable=True)
    photo_consent = db.Column(db.Boolean, nullable=False, default=False)
    photo_consent_at = db.Column(db.DateTime, nullable=True)

    upload_username = db.Column(db.String(64), nullable=True, unique=True)
    upload_password_hash = db.Column(db.String(255), nullable=True)
    upload_token = db.Column(db.String(64), nullable=True, unique=True)
    temporary_access_code = db.Column(db.String(64), nullable=True, unique=True)
    uploaded_filename = db.Column(db.String(255), nullable=True)
    uploaded_at = db.Column(db.DateTime, nullable=True)
    essay_word_count = db.Column(db.Integer, nullable=True)
    essay_word_counted_at = db.Column(db.DateTime, nullable=True)
    essay_finalized = db.Column(db.Boolean, nullable=False, default=False)
    essay_finalized_at = db.Column(db.DateTime, nullable=True)

    scores = db.relationship("EssayScore", back_populates="student", cascade="all, delete-orphan")
    survey_assignments = db.relationship(
        "SurveyAssignment",
        back_populates="student",
        cascade="all, delete-orphan",
    )
    essay_uploads = db.relationship(
        "EssayUpload",
        back_populates="student",
        cascade="all, delete-orphan",
    )


class EssayUpload(db.Model, TimestampMixin):
    __tablename__ = "essay_uploads"

    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey("students.id", ondelete="CASCADE"), nullable=False)
    filename = db.Column(db.String(255), nullable=False)
    word_count = db.Column(db.Integer, nullable=True)
    word_counted_at = db.Column(db.DateTime, nullable=True)
    finalized_at = db.Column(db.DateTime, nullable=True)

    student = db.relationship("Student", back_populates="essay_uploads")

    __table_args__ = (
        db.Index("ix_essay_upload_student_id", "student_id"),
        db.Index("ix_essay_upload_filename", "filename"),
    )


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


class StaticPage(db.Model, TimestampMixin):
    __tablename__ = "static_pages"

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    slug = db.Column(db.String(160), nullable=False, unique=True)
    html_body = db.Column(db.Text, nullable=False)
    created_by = db.Column(db.String(120), nullable=True)
    updated_by = db.Column(db.String(120), nullable=True)

    attachments = db.relationship(
        "StaticPageAttachment",
        back_populates="page",
        cascade="all, delete-orphan",
        order_by="StaticPageAttachment.created_at.asc()",
    )


class StaticPageAttachment(db.Model, TimestampMixin):
    __tablename__ = "static_page_attachments"

    id = db.Column(db.Integer, primary_key=True)
    page_id = db.Column(db.Integer, db.ForeignKey("static_pages.id", ondelete="CASCADE"), nullable=False)
    original_filename = db.Column(db.String(255), nullable=False)
    stored_filename = db.Column(db.String(255), nullable=False, unique=True)
    content_type = db.Column(db.String(120), nullable=True)
    file_size = db.Column(db.Integer, nullable=True)
    uploaded_by = db.Column(db.String(120), nullable=True)

    page = db.relationship("StaticPage", back_populates="attachments")

    __table_args__ = (
        db.Index("ix_static_page_attachment_page_id", "page_id"),
        db.Index("ix_static_page_attachment_stored_filename", "stored_filename"),
    )


class SurveyStatus(enum.StrEnum):
    DRAFT = "draft"
    PUBLISHED = "published"
    CLOSED = "closed"


class SurveyAudience(enum.StrEnum):
    TEACHER = "teacher"
    STUDENT = "student"
    MIXED = "mixed"


class SurveyQuestionType(enum.StrEnum):
    SHORT_TEXT = "short_text"
    LONG_TEXT = "long_text"
    RADIO = "radio"
    SELECT = "select"
    DATE = "date"


class SurveyAssignmentStatus(enum.StrEnum):
    PENDING = "pending"
    COMPLETED = "completed"


class PasswordResetAudience(enum.StrEnum):
    STUDENT = "student"
    TEACHER = "teacher"


class Teacher(db.Model, TimestampMixin):
    __tablename__ = "teachers"

    id = db.Column(db.Integer, primary_key=True)
    country = db.Column(db.String(100), nullable=False)
    first_name = db.Column(db.String(80), nullable=False)
    last_name = db.Column(db.String(80), nullable=False)
    email = db.Column(db.String(255), nullable=False, unique=True)
    school = db.Column(db.String(120), nullable=False)
    sex_document = db.Column(db.String(10), nullable=True)
    accommodation_room_sharing = db.Column(db.String(32), nullable=True)
    languages = db.Column(db.String(120), nullable=False)
    prior_ipo_assessor = db.Column(db.Boolean, nullable=False, default=False)
    prior_ipo_assessor_level = db.Column(db.Integer, nullable=False, default=0)
    meal_preference = db.Column(db.String(30), nullable=False)
    special_needs = db.Column(db.Text, nullable=True)
    tshirt_size = db.Column(db.String(5), nullable=False)
    delegation_leader = db.Column(db.Boolean, nullable=False, default=False)
    is_absent = db.Column(db.Boolean, nullable=False, default=False)

    accepted_ethics = db.Column(db.Boolean, nullable=False, default=False)
    accepted_ethics_at = db.Column(db.DateTime, nullable=True)
    declared_assessor_competence = db.Column(db.Boolean, nullable=False, default=False)
    declared_assessor_competence_at = db.Column(db.DateTime, nullable=True)
    gdpr_acknowledged = db.Column(db.Boolean, nullable=False, default=False)
    gdpr_acknowledged_at = db.Column(db.DateTime, nullable=True)
    photo_consent = db.Column(db.Boolean, nullable=False, default=False)
    photo_consent_at = db.Column(db.DateTime, nullable=True)

    portal_username = db.Column(db.String(64), unique=True)
    portal_password_hash = db.Column(db.String(255))
    portal_token = db.Column(db.String(64), unique=True)
    temporary_access_code = db.Column(db.String(64), unique=True)
    portal_last_login = db.Column(db.DateTime)

    language_entries = db.relationship("TeacherLanguage", back_populates="teacher", cascade="all, delete-orphan")
    assignments = db.relationship(
        "ReadingGroupMember",
        back_populates="teacher",
        cascade="all, delete-orphan",
    )
    scores = db.relationship("EssayScore", back_populates="teacher", cascade="all, delete-orphan")
    messages = db.relationship("TeacherMessage", back_populates="teacher", cascade="all, delete-orphan")
    survey_assignments = db.relationship(
        "SurveyAssignment",
        back_populates="teacher",
        cascade="all, delete-orphan",
    )

    @property
    def veteran_level(self) -> int:
        return self.prior_ipo_assessor_level or 0

    @property
    def veteran_level_label(self) -> str | None:
        level = self.veteran_level
        return f"Level {level}" if level else None


class PasswordResetToken(db.Model, TimestampMixin):
    __tablename__ = "password_reset_tokens"

    id = db.Column(db.Integer, primary_key=True)
    audience = db.Column(db.Enum(PasswordResetAudience), nullable=False)
    student_id = db.Column(
        db.Integer,
        db.ForeignKey("students.id", ondelete="CASCADE"),
        nullable=True,
    )
    teacher_id = db.Column(
        db.Integer,
        db.ForeignKey("teachers.id", ondelete="CASCADE"),
        nullable=True,
    )
    token = db.Column(db.String(64), nullable=False, unique=True)
    expires_at = db.Column(db.DateTime, nullable=False)
    used_at = db.Column(db.DateTime, nullable=True)

    student = db.relationship("Student")
    teacher = db.relationship("Teacher")

    __table_args__ = (
        db.CheckConstraint(
            "(student_id IS NOT NULL AND teacher_id IS NULL) OR "
            "(student_id IS NULL AND teacher_id IS NOT NULL)",
            name="ck_password_reset_token_audience_target",
        ),
    )


class DelegationInviteRole(enum.StrEnum):
    STUDENT = "student"
    TEACHER = "teacher"


class DelegationInvite(db.Model, TimestampMixin):
    __tablename__ = "delegation_invites"

    id = db.Column(db.Integer, primary_key=True)
    token = db.Column(db.String(64), nullable=False, unique=True)
    role = db.Column(db.Enum(DelegationInviteRole), nullable=False)
    delegation_leader = db.Column(db.Boolean, nullable=False, default=False)
    country = db.Column(db.String(100), nullable=False)
    first_name = db.Column(db.String(80), nullable=True)
    last_name = db.Column(db.String(80), nullable=True)
    email = db.Column(db.String(255), nullable=False)
    invited_by_id = db.Column(db.Integer, db.ForeignKey("teachers.id", ondelete="SET NULL"), nullable=True)
    student_id = db.Column(db.Integer, db.ForeignKey("students.id", ondelete="SET NULL"), nullable=True)
    teacher_id = db.Column(db.Integer, db.ForeignKey("teachers.id", ondelete="SET NULL"), nullable=True)
    opened_at = db.Column(db.DateTime, nullable=True)
    accepted_at = db.Column(db.DateTime, nullable=True)
    revoked_at = db.Column(db.DateTime, nullable=True)
    email_sent_at = db.Column(db.DateTime, nullable=True)
    email_error = db.Column(db.Text, nullable=True)

    invited_by = db.relationship("Teacher", foreign_keys=[invited_by_id])
    student = db.relationship("Student")
    teacher = db.relationship("Teacher", foreign_keys=[teacher_id])

    __table_args__ = (
        db.Index("ix_delegation_invite_token", "token"),
        db.Index("ix_delegation_invite_country_role", "country", "role"),
    )


class InvitationBatchDraft(db.Model, TimestampMixin):
    __tablename__ = "invitation_batch_drafts"

    id = db.Column(db.Integer, primary_key=True)
    created_by = db.Column(db.String(120), nullable=False)
    batch_type = db.Column(db.String(32), nullable=False)
    source_filename = db.Column(db.String(255), nullable=False)
    file_sha256 = db.Column(db.String(64), nullable=False)
    status = db.Column(db.String(20), nullable=False, default="preview")
    total_rows = db.Column(db.Integer, nullable=False, default=0)
    ready_rows = db.Column(db.Integer, nullable=False, default=0)
    skip_rows = db.Column(db.Integer, nullable=False, default=0)
    error_rows = db.Column(db.Integer, nullable=False, default=0)
    executed_at = db.Column(db.DateTime, nullable=True)
    result_payload = db.Column(db.JSON, nullable=True)

    __table_args__ = (
        db.Index("ix_invitation_batch_draft_created_by", "created_by"),
        db.Index("ix_invitation_batch_draft_status", "status"),
        db.Index("ix_invitation_batch_draft_created_at", "created_at"),
    )


class CommunicationStatus(enum.StrEnum):
    DRAFT = "draft"
    QUEUED = "queued"
    SENDING = "sending"
    SENT = "sent"
    FAILED = "failed"


class CommunicationAudience(enum.StrEnum):
    TEACHER = "teacher"
    STUDENT = "student"
    BOTH = "both"


class CommunicationRecipientRole(enum.StrEnum):
    TEACHER = "teacher"
    STUDENT = "student"


class CommunicationRecipientStatus(enum.StrEnum):
    PENDING = "pending"
    SENT = "sent"
    FAILED = "failed"


class CommunicationCampaign(db.Model, TimestampMixin):
    __tablename__ = "communication_campaigns"

    id = db.Column(db.Integer, primary_key=True)
    subject = db.Column(db.String(255), nullable=False)
    html_body = db.Column(db.Text, nullable=False)
    text_body = db.Column(db.Text, nullable=False)
    audience = db.Column(db.Enum(CommunicationAudience), nullable=False, default=CommunicationAudience.BOTH)
    country_filter = db.Column(db.JSON, nullable=True)
    include_absent = db.Column(db.Boolean, nullable=False, default=False)
    status = db.Column(db.Enum(CommunicationStatus), nullable=False, default=CommunicationStatus.DRAFT)
    total_recipients = db.Column(db.Integer, nullable=False, default=0)
    sent_count = db.Column(db.Integer, nullable=False, default=0)
    failed_count = db.Column(db.Integer, nullable=False, default=0)
    created_by = db.Column(db.String(120), nullable=True)
    sent_by = db.Column(db.String(120), nullable=True)
    sent_at = db.Column(db.DateTime, nullable=True)

    recipients = db.relationship(
        "CommunicationRecipient",
        back_populates="campaign",
        cascade="all, delete-orphan",
        order_by="CommunicationRecipient.id",
    )

    __table_args__ = (
        db.Index("ix_communication_campaign_status", "status"),
    )


class CommunicationRecipient(db.Model, TimestampMixin):
    __tablename__ = "communication_recipients"

    id = db.Column(db.Integer, primary_key=True)
    campaign_id = db.Column(
        db.Integer,
        db.ForeignKey("communication_campaigns.id", ondelete="CASCADE"),
        nullable=False,
    )
    role = db.Column(db.Enum(CommunicationRecipientRole), nullable=False)
    student_id = db.Column(
        db.Integer,
        db.ForeignKey("students.id", ondelete="SET NULL"),
        nullable=True,
    )
    teacher_id = db.Column(
        db.Integer,
        db.ForeignKey("teachers.id", ondelete="SET NULL"),
        nullable=True,
    )
    email = db.Column(db.String(255), nullable=False)
    first_name = db.Column(db.String(80), nullable=True)
    last_name = db.Column(db.String(80), nullable=True)
    country = db.Column(db.String(100), nullable=True)
    status = db.Column(
        db.Enum(CommunicationRecipientStatus),
        nullable=False,
        default=CommunicationRecipientStatus.PENDING,
    )
    message_id = db.Column(db.String(120), nullable=True)
    error = db.Column(db.Text, nullable=True)
    sent_at = db.Column(db.DateTime, nullable=True)

    campaign = db.relationship("CommunicationCampaign", back_populates="recipients")
    student = db.relationship("Student")
    teacher = db.relationship("Teacher")

    __table_args__ = (
        db.UniqueConstraint(
            "campaign_id",
            "role",
            "student_id",
            "teacher_id",
            name="uq_communication_recipient_target",
        ),
        db.UniqueConstraint("campaign_id", "email", name="uq_communication_recipient_email"),
        db.Index("ix_communication_recipient_campaign_status", "campaign_id", "status"),
    )


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


class PlannerAlgorithm(enum.StrEnum):
    STRICT_FOUR_WITH_BACKUPS = "strict_four_with_backups"
    ALL_ASSESSORS_NO_BACKUPS = "all_assessors_no_backups"


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
    planner_algorithm = db.Column(
        db.Enum(PlannerAlgorithm),
        nullable=False,
        default=PlannerAlgorithm.STRICT_FOUR_WITH_BACKUPS,
    )
    planner_group_soft_max = db.Column(db.Integer, nullable=False, default=5)
    planner_allow_cross_language_assignments = db.Column(db.Boolean, nullable=False, default=False)
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


class Survey(db.Model, TimestampMixin):
    __tablename__ = "surveys"

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, nullable=True)
    status = db.Column(db.Enum(SurveyStatus), nullable=False, default=SurveyStatus.DRAFT)
    audience = db.Column(db.Enum(SurveyAudience), nullable=False, default=SurveyAudience.MIXED)
    allow_edit = db.Column(db.Boolean, nullable=False, default=False)
    open_at = db.Column(db.DateTime, nullable=True)
    close_at = db.Column(db.DateTime, nullable=True)
    created_by = db.Column(db.String(120), nullable=True)

    questions = db.relationship(
        "SurveyQuestion",
        back_populates="survey",
        cascade="all, delete-orphan",
        order_by="SurveyQuestion.position",
    )
    assignments = db.relationship(
        "SurveyAssignment",
        back_populates="survey",
        cascade="all, delete-orphan",
    )


class SurveyQuestion(db.Model, TimestampMixin):
    __tablename__ = "survey_questions"

    id = db.Column(db.Integer, primary_key=True)
    survey_id = db.Column(db.Integer, db.ForeignKey("surveys.id", ondelete="CASCADE"), nullable=False)
    prompt = db.Column(db.String(500), nullable=False)
    help_text = db.Column(db.Text, nullable=True)
    type = db.Column(db.Enum(SurveyQuestionType), nullable=False, default=SurveyQuestionType.SHORT_TEXT)
    required = db.Column(db.Boolean, nullable=False, default=True)
    options = db.Column(db.JSON, nullable=True)
    position = db.Column(db.Integer, nullable=False, default=0)

    survey = db.relationship("Survey", back_populates="questions")


class SurveyAssignment(db.Model, TimestampMixin):
    __tablename__ = "survey_assignments"

    id = db.Column(db.Integer, primary_key=True)
    survey_id = db.Column(db.Integer, db.ForeignKey("surveys.id", ondelete="CASCADE"), nullable=False)
    status = db.Column(db.Enum(SurveyAssignmentStatus), nullable=False, default=SurveyAssignmentStatus.PENDING)
    completed_at = db.Column(db.DateTime, nullable=True)
    delivery_token = db.Column(db.String(64), unique=True, nullable=True)
    teacher_id = db.Column(db.Integer, db.ForeignKey("teachers.id", ondelete="CASCADE"), nullable=True)
    student_id = db.Column(db.Integer, db.ForeignKey("students.id", ondelete="CASCADE"), nullable=True)

    survey = db.relationship("Survey", back_populates="assignments")
    teacher = db.relationship("Teacher", back_populates="survey_assignments")
    student = db.relationship("Student", back_populates="survey_assignments")
    response = db.relationship(
        "SurveyResponse",
        back_populates="assignment",
        cascade="all, delete-orphan",
        uselist=False,
    )

    __table_args__ = (
        db.CheckConstraint(
            "(teacher_id IS NOT NULL AND student_id IS NULL) OR (teacher_id IS NULL AND student_id IS NOT NULL)",
            name="ck_survey_assignment_recipient",
        ),
        db.UniqueConstraint("survey_id", "teacher_id", name="uq_survey_assignment_teacher"),
        db.UniqueConstraint("survey_id", "student_id", name="uq_survey_assignment_student"),
    )


class SurveyResponse(db.Model, TimestampMixin):
    __tablename__ = "survey_responses"

    id = db.Column(db.Integer, primary_key=True)
    survey_id = db.Column(db.Integer, db.ForeignKey("surveys.id", ondelete="CASCADE"), nullable=False)
    assignment_id = db.Column(db.Integer, db.ForeignKey("survey_assignments.id", ondelete="CASCADE"), nullable=False)
    response_data = db.Column(db.JSON, nullable=False)

    survey = db.relationship("Survey")
    assignment = db.relationship("SurveyAssignment", back_populates="response")

    __table_args__ = (
        db.UniqueConstraint("assignment_id", name="uq_survey_response_assignment"),
    )
