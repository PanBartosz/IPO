from __future__ import annotations

import re

from flask_wtf import FlaskForm
from wtforms import (
    BooleanField,
    DateField,
    DateTimeField,
    DecimalField,
    EmailField,
    IntegerField,
    PasswordField,
    RadioField,
    SelectField,
    SelectMultipleField,
    StringField,
    SubmitField,
    TextAreaField,
    HiddenField,
)
from wtforms.validators import DataRequired, Email, Length, Optional, ValidationError, NumberRange, InputRequired
from wtforms.widgets import CheckboxInput, ListWidget

from flask_wtf.file import FileAllowed, FileField, FileRequired

from wtforms.validators import AnyOf

from .models import (
    CommunicationAudience,
    GroupMemberRole,
    Stage,
    SurveyAudience,
    SurveyQuestionType,
)

LANGUAGE_CHOICES = [
    ("English", "English"),
    ("French", "French"),
    ("German", "German"),
    ("Spanish", "Spanish"),
]

MEAL_CHOICES = [
    ("No preference", "No preference"),
    ("Vegetarian", "Vegetarian"),
    ("Vegan", "Vegan"),
]

SEX_DOCUMENT_CHOICES = [
    ("female", "female"),
    ("male", "male"),
]

ACCOMMODATION_ROOM_SHARING_CHOICES = [
    (
        "same_sex",
        "a room only with persons of this same sex as in official documents",
    ),
    ("any_sex", "a room with persons of any sex"),
]

KEYBOARD_CHOICES = [
    ("QWERTY", "QWERTY"),
    ("AZERTY", "AZERTY"),
]

TSHIRT_CHOICES = [
    ("S", "S"),
    ("M", "M"),
    ("L", "L"),
    ("XL", "XL"),
    ("XXL", "XXL"),
]

PHOTO_CONSENT_CHOICES = [
    ("", "Select an option"),
    ("yes", "I consent to image publication"),
    ("no", "I do not consent to image publication"),
]

VETERAN_LEVEL_CHOICES = [
    (0, "Never assessed essays in previous IPO editions"),
    (1, "Assessed once"),
    (2, "Assessed twice"),
    (3, "Assessed three or more times"),
]

TEACHER_MESSAGE_PRIORITY_CHOICES = [
    ("low", "Low"),
    ("normal", "Normal"),
    ("high", "High"),
]

SURVEY_AUDIENCE_CHOICES = [
    (SurveyAudience.TEACHER.value, "Teachers"),
    (SurveyAudience.STUDENT.value, "Students"),
    (SurveyAudience.MIXED.value, "Teachers and students"),
]

SURVEY_QUESTION_TYPE_CHOICES = [
    (SurveyQuestionType.SHORT_TEXT.value, "Short text"),
    (SurveyQuestionType.LONG_TEXT.value, "Long text"),
    (SurveyQuestionType.RADIO.value, "Radio buttons"),
    (SurveyQuestionType.SELECT.value, "Dropdown list"),
    (SurveyQuestionType.DATE.value, "Date"),
]

COMMUNICATION_AUDIENCE_CHOICES = [
    (CommunicationAudience.TEACHER.value, "Teachers"),
    (CommunicationAudience.STUDENT.value, "Students"),
    (CommunicationAudience.BOTH.value, "Teachers and students"),
]


class StudentRegistrationForm(FlaskForm):
    first_name = StringField("First name", validators=[DataRequired(), Length(max=80)])
    last_name = StringField("Last name", validators=[DataRequired(), Length(max=80)])
    email = EmailField("Email", validators=[DataRequired(), Email(check_deliverability=False), Length(max=255)])
    country = StringField("Country", validators=[DataRequired(), Length(max=100)])
    school = StringField("School", validators=[DataRequired(), Length(max=120)])
    sex_document = RadioField(
        "Sex according to your official identity document",
        validators=[InputRequired()],
        choices=SEX_DOCUMENT_CHOICES,
    )
    accommodation_room_sharing = RadioField(
        "Regarding accommodation, I feel safe staying in",
        validators=[InputRequired()],
        choices=ACCOMMODATION_ROOM_SHARING_CHOICES,
    )
    date_of_birth = DateField("Date of birth", validators=[DataRequired()], format="%Y-%m-%d")
    essay_language = SelectField(
        "Essay language", validators=[DataRequired()], choices=LANGUAGE_CHOICES
    )
    keyboard_preference = SelectField(
        "Keyboard preference", validators=[DataRequired()], choices=KEYBOARD_CHOICES
    )
    meal_preference = SelectField(
        "Meal preference", validators=[DataRequired()], choices=MEAL_CHOICES
    )
    special_needs = TextAreaField(
        "Special dietary, health, or religious needs", validators=[Optional(), Length(max=5000)]
    )
    gdpr_acknowledged = BooleanField(
        "I confirm I have read the data processing information",
        validators=[InputRequired()],
    )
    photo_consent = SelectField(
        "Photo publication consent",
        validators=[DataRequired()],
        choices=PHOTO_CONSENT_CHOICES,
    )
    accepted_ethics = BooleanField(
        "I confirm I have read and accept the IPO Statute and Code of Ethics",
        validators=[InputRequired()],
    )
    is_absent = BooleanField("Marked absent")
    submit = SubmitField("Submit registration")


class TeacherRegistrationForm(FlaskForm):
    first_name = StringField("First name", validators=[DataRequired(), Length(max=80)])
    last_name = StringField("Last name", validators=[DataRequired(), Length(max=80)])
    email = EmailField("Email", validators=[DataRequired(), Email(check_deliverability=False), Length(max=255)])
    country = StringField("Country", validators=[DataRequired(), Length(max=100)])
    school = StringField("School", validators=[DataRequired(), Length(max=120)])
    sex_document = RadioField(
        "Sex according to your official identity document",
        validators=[InputRequired()],
        choices=SEX_DOCUMENT_CHOICES,
    )
    accommodation_room_sharing = RadioField(
        "Regarding accommodation, I feel safe staying in",
        validators=[InputRequired()],
        choices=ACCOMMODATION_ROOM_SHARING_CHOICES,
    )
    languages = SelectMultipleField(
        "Languages",
        validators=[Optional()],
        choices=LANGUAGE_CHOICES,
        widget=ListWidget(prefix_label=False),
        option_widget=CheckboxInput(),
        default=["English"],
    )
    meal_preference = SelectField(
        "Meal preference", validators=[DataRequired()], choices=MEAL_CHOICES
    )
    tshirt_size = SelectField(
        "T-shirt size", validators=[DataRequired()], choices=TSHIRT_CHOICES
    )
    prior_ipo_assessor_level = SelectField(
        "IPO assessing experience",
        validators=[InputRequired()],
        choices=VETERAN_LEVEL_CHOICES,
        coerce=int,
        default=0,
    )
    special_needs = TextAreaField(
        "Special dietary, health, or religious needs", validators=[Optional(), Length(max=5000)]
    )
    gdpr_acknowledged = BooleanField(
        "I confirm I have read the data processing information",
        validators=[InputRequired()],
    )
    photo_consent = SelectField(
        "Photo publication consent",
        validators=[DataRequired()],
        choices=PHOTO_CONSENT_CHOICES,
    )
    non_assessor = BooleanField(
        "I am registering as a non-assessing member (I will not assess essays).",
        default=False,
    )
    declared_assessor_competence = BooleanField(
        "I confirm I am qualified and competent to assess philosophical essays",
        validators=[Optional()],
    )
    accepted_ethics = BooleanField(
        "I confirm I have read and accept the IPO Statute and Code of Ethics",
        validators=[InputRequired()],
    )
    delegation_leader = BooleanField("Delegation leader")
    is_absent = BooleanField("Marked absent")
    submit = SubmitField("Submit registration")

    def validate_languages(self, field: SelectMultipleField) -> None:
        available = {choice[0] for choice in LANGUAGE_CHOICES}
        selected = set(field.data or [])
        if "English" not in selected:
            raise ValidationError("English must be selected.")
        invalid = selected - available
        if invalid:
            raise ValidationError("Invalid language selection detected.")


class DelegationInviteForm(FlaskForm):
    first_name = StringField("First name", validators=[DataRequired(), Length(max=80)])
    last_name = StringField("Last name", validators=[DataRequired(), Length(max=80)])
    email = EmailField("Email", validators=[DataRequired(), Email(check_deliverability=False), Length(max=255)])
    submit = SubmitField("Send invite")


class DelegationLeaderInviteForm(FlaskForm):
    first_name = StringField("First name", validators=[DataRequired(), Length(max=80)])
    last_name = StringField("Last name", validators=[DataRequired(), Length(max=80)])
    email = EmailField("Email", validators=[DataRequired(), Email(check_deliverability=False), Length(max=255)])
    country = StringField("Country", validators=[DataRequired(), Length(max=100)])
    submit = SubmitField("Create invite")


INVITE_ROLE_CHOICES = [
    ("student", "Student"),
    ("teacher", "Teacher"),
]

INVITATION_BATCH_TYPE_CHOICES = [
    ("delegation_leader", "Delegation leader invites"),
    ("delegation", "Delegation invites"),
    ("normal", "Normal invites"),
]


class AdminDelegationInvitationForm(FlaskForm):
    delegation_leader_id = SelectField("Delegation leader", validators=[DataRequired()], coerce=int)
    role = SelectField("Role", validators=[DataRequired()], choices=INVITE_ROLE_CHOICES)
    first_name = StringField("First name", validators=[DataRequired(), Length(max=80)])
    last_name = StringField("Last name", validators=[DataRequired(), Length(max=80)])
    email = EmailField("Email", validators=[DataRequired(), Email(check_deliverability=False), Length(max=255)])
    submit = SubmitField("Send delegation invite")


class AdminInvitationForm(FlaskForm):
    role = SelectField("Role", validators=[DataRequired()], choices=INVITE_ROLE_CHOICES)
    first_name = StringField("First name", validators=[DataRequired(), Length(max=80)])
    last_name = StringField("Last name", validators=[DataRequired(), Length(max=80)])
    email = EmailField("Email", validators=[DataRequired(), Email(check_deliverability=False), Length(max=255)])
    country = StringField("Country", validators=[DataRequired(), Length(max=100)])
    submit = SubmitField("Send invite")


class AdminInvitationBatchUploadForm(FlaskForm):
    batch_type = SelectField(
        "Batch type",
        validators=[DataRequired()],
        choices=INVITATION_BATCH_TYPE_CHOICES,
    )
    invite_file = FileField(
        "CSV/XLSX file",
        validators=[FileRequired(message="Please select a CSV or XLSX file."), FileAllowed(["csv", "xlsx"], "CSV/XLSX only")],
    )
    submit_preview = SubmitField("Validate and preview")


class AdminInvitationBatchExecuteForm(FlaskForm):
    draft_id = HiddenField(validators=[DataRequired()])
    confirm = BooleanField(
        "I confirm I want to create invites from this preview.",
        validators=[DataRequired()],
    )
    submit_execute = SubmitField("Execute batch")


class AdminInvitationBatchDiscardForm(FlaskForm):
    draft_id = HiddenField(validators=[DataRequired()])
    submit_discard = SubmitField("Discard preview")


class AdminLoginForm(FlaskForm):
    username = StringField("Username", validators=[DataRequired(), Length(max=120)])
    password = PasswordField("Password", validators=[DataRequired(), Length(max=256)])
    submit = SubmitField("Sign in")


class AssignmentBatchForm(FlaskForm):
    name = StringField("Batch name", validators=[DataRequired(), Length(max=120)])
    stage = SelectField(
        "Stage",
        validators=[DataRequired()],
        choices=[(Stage.STAGE_1.value, "Stage 1"), (Stage.STAGE_2.value, "Stage 2")],
    )
    notes = TextAreaField("Notes", validators=[Optional(), Length(max=2000)])
    submit = SubmitField("Create batch")


class ReadingGroupForm(FlaskForm):
    name = StringField("Group name", validators=[DataRequired(), Length(max=120)])
    language = SelectField("Language", validators=[DataRequired()], choices=LANGUAGE_CHOICES)
    target_essay_load = IntegerField("Target essays", validators=[Optional()])
    allow_same_country = BooleanField("Allow same-country readers")
    auto_generated = BooleanField("Mark as auto-generated", default=True)
    submit = SubmitField("Save group")


class ReadingGroupMemberForm(FlaskForm):
    teacher_id = SelectField("Teacher", validators=[DataRequired()], coerce=int)
    role = SelectField(
        "Role",
        validators=[DataRequired()],
        choices=[(role.value, role.name.title()) for role in GroupMemberRole],
    )
    active = BooleanField("Active", default=True)
    submit = SubmitField("Add member")


class StudentLoginForm(FlaskForm):
    username = StringField("Username", validators=[DataRequired(), Length(max=64)])
    password = PasswordField("Password", validators=[DataRequired(), Length(max=64)])
    submit = SubmitField("Sign in")


class StudentUploadForm(FlaskForm):
    essay = FileField(
        "Essay PDF",
        validators=[FileRequired(message="Please select a PDF file."), FileAllowed(["pdf"], "PDF only")],
    )
    submit = SubmitField("Upload essay")


class DashboardSettingsForm(FlaskForm):
    upload_deadline = DateTimeField(
        "Essay upload deadline", format="%Y-%m-%dT%H:%M", validators=[Optional()]
    )
    stage2_deadline = DateTimeField(
        "Stage 2 deadline", format="%Y-%m-%dT%H:%M", validators=[Optional()]
    )
    event_end = DateTimeField(
        "Event end (essay access unlock)", format="%Y-%m-%dT%H:%M", validators=[Optional()]
    )
    event_end_override = SelectField(
        "Event access override",
        choices=[
            ("auto", "Auto (use event end time)"),
            ("force_end", "Force end (unlock downloads now)"),
            ("force_open", "Force open (keep downloads locked)"),
        ],
        validators=[DataRequired(), AnyOf(["auto", "force_end", "force_open"])],
        default="auto",
    )
    stage1_sla = IntegerField(
        "Stage 1 score SLA (hours)", validators=[Optional()]
    )
    stage2_sla = IntegerField(
        "Stage 2 score SLA (hours)", validators=[Optional()]
    )
    packet_print_mode = SelectField(
        "Packet print mode",
        choices=[("single", "Single-sided"), ("double", "Double-sided")],
        validators=[DataRequired(), AnyOf(["single", "double"])],
        default="single",
    )
    essay_word_limit = IntegerField(
        "Essay word limit",
        validators=[Optional(), NumberRange(min=1, max=100000)],
    )
    essay_word_limit_mode = SelectField(
        "Essay word limit mode",
        choices=[("off", "Off"), ("soft", "Soft warning"), ("hard", "Hard block finalization")],
        validators=[DataRequired(), AnyOf(["off", "soft", "hard"])],
        default="soft",
    )
    ethics_consent_html = TextAreaField(
        "Code of Ethics consent text (HTML)",
        validators=[Optional()],
        render_kw={"rows": 6},
    )
    gdpr_notice_html = TextAreaField(
        "GDPR data processing information (HTML)",
        validators=[Optional()],
        render_kw={"rows": 6},
    )
    photo_consent_html = TextAreaField(
        "Photo publication consent text (HTML)",
        validators=[Optional()],
        render_kw={"rows": 6},
    )
    assessor_competence_html = TextAreaField(
        "Assessor competence statement text (HTML)",
        validators=[Optional()],
        render_kw={"rows": 6},
    )
    accommodation_info_html = TextAreaField(
        "Accommodation important information block (HTML)",
        validators=[Optional()],
        render_kw={"rows": 6},
    )
    essay_upload_enabled = BooleanField("Enable essay upload module")
    teacher_portal_enabled = BooleanField("Enable teacher portal (individual login & online grading)")
    registration_invite_only = BooleanField("Require invite link for registrations")
    email_auto_enabled = BooleanField("Enable automatic emails")
    email_student_subject = StringField("Student confirmation subject", validators=[Optional(), Length(max=200)])
    email_student_body = TextAreaField("Student confirmation body", validators=[Optional()], render_kw={"rows": 6})
    email_teacher_subject = StringField("Teacher confirmation subject", validators=[Optional(), Length(max=200)])
    email_teacher_body = TextAreaField("Teacher confirmation body", validators=[Optional()], render_kw={"rows": 6})
    email_student_invite_subject = StringField("Student invite subject", validators=[Optional(), Length(max=200)])
    email_student_invite_body = TextAreaField("Student invite body", validators=[Optional()], render_kw={"rows": 6})
    email_teacher_invite_subject = StringField("Teacher invite subject", validators=[Optional(), Length(max=200)])
    email_teacher_invite_body = TextAreaField("Teacher invite body", validators=[Optional()], render_kw={"rows": 6})
    email_message_subject = StringField("Teacher message email subject", validators=[Optional(), Length(max=200)])
    email_message_body = TextAreaField("Teacher message email body", validators=[Optional()], render_kw={"rows": 6})
    email_survey_publish_subject = StringField("Survey publish email subject", validators=[Optional(), Length(max=200)])
    email_survey_publish_body = TextAreaField("Survey publish email body", validators=[Optional()], render_kw={"rows": 6})
    email_survey_reminder_subject = StringField("Survey reminder email subject", validators=[Optional(), Length(max=200)])
    email_survey_reminder_body = TextAreaField("Survey reminder email body", validators=[Optional()], render_kw={"rows": 6})
    email_student_reset_link_subject = StringField(
        "Student password reset link subject",
        validators=[Optional(), Length(max=200)],
    )
    email_student_reset_link_body = TextAreaField(
        "Student password reset link body",
        validators=[Optional()],
        render_kw={"rows": 6},
    )
    email_student_reset_subject = StringField("Student password reset subject", validators=[Optional(), Length(max=200)])
    email_student_reset_body = TextAreaField("Student password reset body", validators=[Optional()], render_kw={"rows": 6})
    email_teacher_reset_link_subject = StringField(
        "Teacher password reset link subject",
        validators=[Optional(), Length(max=200)],
    )
    email_teacher_reset_link_body = TextAreaField(
        "Teacher password reset link body",
        validators=[Optional()],
        render_kw={"rows": 6},
    )
    email_teacher_reset_subject = StringField("Teacher password reset subject", validators=[Optional(), Length(max=200)])
    email_teacher_reset_body = TextAreaField("Teacher password reset body", validators=[Optional()], render_kw={"rows": 6})
    submit = SubmitField("Save settings")


class SurveyForm(FlaskForm):
    title = StringField("Title", validators=[DataRequired(), Length(max=200)])
    description = TextAreaField("Description", validators=[Optional(), Length(max=2000)])
    audience = SelectField(
        "Audience",
        choices=SURVEY_AUDIENCE_CHOICES,
        validators=[DataRequired(), AnyOf([choice[0] for choice in SURVEY_AUDIENCE_CHOICES])],
        default=SurveyAudience.MIXED.value,
    )
    allow_edit = BooleanField("Allow respondents to edit after submission")
    open_at = DateTimeField("Open at", format="%Y-%m-%dT%H:%M", validators=[Optional()])
    close_at = DateTimeField("Close at", format="%Y-%m-%dT%H:%M", validators=[Optional()])
    submit = SubmitField("Save survey")

    def validate_close_at(self, field: DateTimeField) -> None:
        if field.data and self.open_at.data and field.data <= self.open_at.data:
            raise ValidationError("Close time must be after the open time.")


class SurveyQuestionForm(FlaskForm):
    prompt = StringField("Question prompt", validators=[DataRequired(), Length(max=500)])
    help_text = TextAreaField("Help text", validators=[Optional(), Length(max=1000)])
    type = SelectField(
        "Question type",
        choices=SURVEY_QUESTION_TYPE_CHOICES,
        validators=[DataRequired(), AnyOf([choice[0] for choice in SURVEY_QUESTION_TYPE_CHOICES])],
        default=SurveyQuestionType.SHORT_TEXT.value,
    )
    required = BooleanField("Required")
    options_text = TextAreaField(
        "Options (one per line)",
        validators=[Optional(), Length(max=2000)],
        description="Provide at least two options for radio buttons or dropdown lists.",
    )
    submit = SubmitField("Add question")

    def validate_options_text(self, field: TextAreaField) -> None:
        question_type = self.type.data
        requires_options = question_type in {SurveyQuestionType.RADIO.value, SurveyQuestionType.SELECT.value}
        options = [line.strip() for line in (field.data or "").splitlines() if line.strip()]
        if requires_options and len(options) < 2:
            raise ValidationError("Provide at least two options for this question type.")


class SurveyPublishForm(FlaskForm):
    send_to_all_students = BooleanField("Assign to all students")
    send_to_all_teachers = BooleanField("Assign to all teachers")
    student_ids = SelectMultipleField("Specific students", coerce=int, validators=[Optional()])
    teacher_ids = SelectMultipleField("Specific teachers", coerce=int, validators=[Optional()])
    notify_recipients = BooleanField("Send notification email", default=True)
    submit = SubmitField("Publish survey")

    def validate(self, extra_validators: dict | None = None) -> bool:
        if not super().validate(extra_validators=extra_validators):
            return False

        selected_students = self.student_ids.data or []
        selected_teachers = self.teacher_ids.data or []
        targets_selected = any(
            [
                self.send_to_all_students.data,
                self.send_to_all_teachers.data,
                selected_students,
                selected_teachers,
            ]
        )
        if not targets_selected:
            error_msg = "Select at least one group or individual recipient."
            self.student_ids.errors.append(error_msg)
            return False
        return True


class SurveyResponseForm(FlaskForm):
    submit = SubmitField("Submit response")


class PasswordResetRequestForm(FlaskForm):
    email = EmailField("Email", validators=[DataRequired(), Email(check_deliverability=False), Length(max=255)])
    submit = SubmitField("Send reset email")


class PasswordResetConfirmForm(FlaskForm):
    submit = SubmitField("Generate new password")


class TeacherMessageForm(FlaskForm):
    title = StringField("Title", validators=[DataRequired(), Length(max=200)])
    body = TextAreaField("Message", validators=[DataRequired(), Length(max=5000)])
    priority = SelectField(
        "Priority",
        choices=TEACHER_MESSAGE_PRIORITY_CHOICES,
        default="normal",
        validators=[DataRequired()],
    )
    teacher_id = SelectField("Target teacher", coerce=int, validators=[Optional()])
    category = StringField("Category", validators=[Optional(), Length(max=80)])
    submit = SubmitField("Post message")


class TeacherBoardLoginForm(FlaskForm):
    password = PasswordField("Board password", validators=[DataRequired(), Length(max=255)])
    submit = SubmitField("Enter message board")


class TeacherMessageTemplateForm(FlaskForm):
    name = StringField("Template name", validators=[DataRequired(), Length(max=120)])
    title = StringField("Default title", validators=[DataRequired(), Length(max=200)])
    body = TextAreaField("Default message", validators=[DataRequired(), Length(max=5000)])
    category = StringField("Default category", validators=[Optional(), Length(max=80)])
    submit = SubmitField("Save template")


class QuickTeacherMessageForm(FlaskForm):
    teacher_id = HiddenField(validators=[DataRequired()])
    title = StringField("Title", validators=[DataRequired(), Length(max=200)])
    body = TextAreaField("Message", validators=[DataRequired(), Length(max=5000)])
    priority = SelectField(
        "Priority",
        choices=TEACHER_MESSAGE_PRIORITY_CHOICES,
        default="normal",
        validators=[DataRequired()],
    )
    category = StringField("Category", validators=[Optional(), Length(max=80)])
    submit = SubmitField("Send message")


class TeacherPortalLoginForm(FlaskForm):
    username = StringField("Username", validators=[DataRequired(), Length(max=64)])
    password = PasswordField("Password", validators=[DataRequired(), Length(max=255)])
    submit = SubmitField("Sign in")


class TeacherScoreForm(FlaskForm):
    score = DecimalField(
        "Score (0-10)",
        places=2,
        validators=[Optional(), NumberRange(min=0, max=10, message="Score must be between 0 and 10.")],
    )
    comments = TextAreaField("Comments", validators=[Optional(), Length(max=5000)])
    save = SubmitField("Save draft")
    finalize = SubmitField("Finalize score")


class CommunicationComposeForm(FlaskForm):
    subject = StringField("Email subject", validators=[DataRequired(), Length(max=255)])
    html_body = TextAreaField("Email content", validators=[DataRequired()])
    audience = SelectField("Audience", validators=[DataRequired()], choices=COMMUNICATION_AUDIENCE_CHOICES)
    countries = SelectMultipleField(
        "Countries",
        validators=[Optional()],
        choices=[],
    )
    include_absent = BooleanField("Include participants marked absent", default=False)
    submit_preview = SubmitField("Preview email")


class CommunicationSendForm(FlaskForm):
    confirm = BooleanField(
        "I confirm that I want to send this email to the selected recipients.",
        validators=[DataRequired()],
    )
    submit_send = SubmitField("Send email")


class CommunicationRetryForm(FlaskForm):
    submit_retry = SubmitField("Retry failed recipients")


class StaticPageForm(FlaskForm):
    title = StringField("Title", validators=[DataRequired(), Length(max=200)])
    slug = StringField("Slug", validators=[DataRequired(), Length(max=160)])
    html_body = TextAreaField("Page content", validators=[DataRequired()])
    attachment = FileField("Attach file", validators=[Optional()])
    submit = SubmitField("Save page")

    def validate_slug(self, field: StringField) -> None:
        normalized = (field.data or "").strip().lower()
        field.data = normalized
        if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", normalized):
            raise ValidationError(
                "Use lowercase letters, numbers, and single hyphens only (example: travel-info-2026)."
            )


class Stage3PacketForm(FlaskForm):
    committee_label = StringField("Committee label", validators=[Optional(), Length(max=120)], default="Steering Committee")
    member_names = TextAreaField(
        "Steering committee members",
        validators=[DataRequired(message="Provide at least one committee member.")],
        description="Enter one name per line.",
    )
    essay_ids = SelectMultipleField("Essays to include", coerce=int, validators=[DataRequired()])
    submit = SubmitField("Generate packets")


class GradesExportForm(FlaskForm):
    countries = SelectMultipleField("Student countries", choices=[], validators=[Optional()])
    stages = SelectMultipleField(
        "Stages",
        choices=[
            ("stage1", "Stage 1"),
            ("stage2", "Stage 2"),
            ("stage3", "Stage 3 recommendations"),
        ],
        validators=[DataRequired(message="Select at least one stage.")],
    )
    anonymize_students = BooleanField("Anonymize students", default=False)
    anonymize_teachers = BooleanField("Anonymize teachers", default=True)
    include_countries = BooleanField("Include countries in output", default=False)
    finalized_only = BooleanField("Only finalized scores", default=False)
    include_absent = BooleanField("Include absent participants", default=False)
    include_timestamps = BooleanField("Include submission timestamps", default=True)
    group_by_country = BooleanField("Create separate sheet per country (XLSX)")
    compact_view = BooleanField("Compact table layout")
    export_type = SelectField(
        "Export format",
        choices=[
            ("xlsx", "Excel workbook (.xlsx)"),
            ("pdf", "PDF summary"),
        ],
        validators=[DataRequired()],
    )
    sort_by = SelectField(
        "Sort students by",
        choices=[
            ("student_id", "Essay ID"),
            ("stage1_avg", "Stage 1 average"),
            ("stage2_avg", "Stage 2 average"),
            ("combined_avg", "Combined average"),
        ],
        default="student_id",
    )
    submit = SubmitField("Download report")
