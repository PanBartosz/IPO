from __future__ import annotations

from flask_wtf import FlaskForm
from wtforms import (
    BooleanField,
    DateField,
    DateTimeField,
    DecimalField,
    EmailField,
    IntegerField,
    PasswordField,
    SelectField,
    SelectMultipleField,
    StringField,
    SubmitField,
    TextAreaField,
    HiddenField,
)
from wtforms.validators import DataRequired, Email, Length, Optional, ValidationError, NumberRange
from wtforms.widgets import CheckboxInput, ListWidget

from flask_wtf.file import FileAllowed, FileField, FileRequired

from wtforms.validators import AnyOf

from .models import GroupMemberRole, Stage

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

GENDER_CHOICES = [
    ("Female", "Female"),
    ("Male", "Male"),
    ("Other", "Other"),
    ("Prefer not to say", "Prefer not to say"),
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

TEACHER_MESSAGE_PRIORITY_CHOICES = [
    ("low", "Low"),
    ("normal", "Normal"),
    ("high", "High"),
]


class StudentRegistrationForm(FlaskForm):
    first_name = StringField("First name", validators=[DataRequired(), Length(max=80)])
    last_name = StringField("Last name", validators=[DataRequired(), Length(max=80)])
    email = EmailField("Email", validators=[DataRequired(), Email(check_deliverability=False), Length(max=255)])
    country = StringField("Country", validators=[DataRequired(), Length(max=100)])
    school = StringField("School", validators=[DataRequired(), Length(max=120)])
    gender = SelectField("Gender", validators=[DataRequired()], choices=GENDER_CHOICES)
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
    is_absent = BooleanField("Marked absent")
    submit = SubmitField("Submit registration")


class TeacherRegistrationForm(FlaskForm):
    first_name = StringField("First name", validators=[DataRequired(), Length(max=80)])
    last_name = StringField("Last name", validators=[DataRequired(), Length(max=80)])
    email = EmailField("Email", validators=[DataRequired(), Email(check_deliverability=False), Length(max=255)])
    country = StringField("Country", validators=[DataRequired(), Length(max=100)])
    school = StringField("School", validators=[DataRequired(), Length(max=120)])
    gender = SelectField("Gender", validators=[DataRequired()], choices=GENDER_CHOICES)
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
    delegation_leader = BooleanField("Yes, this teacher is a delegation leader")
    prior_ipo_assessor = BooleanField("Assessed essays in a previous IPO edition")
    special_needs = TextAreaField(
        "Special dietary, health, or religious needs", validators=[Optional(), Length(max=5000)]
    )
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
    teacher_portal_enabled = BooleanField("Enable teacher portal (individual login & online grading)")
    email_auto_enabled = BooleanField("Enable automatic emails")
    email_student_subject = StringField("Student confirmation subject", validators=[Optional(), Length(max=200)])
    email_student_body = TextAreaField("Student confirmation body", validators=[Optional()], render_kw={"rows": 6})
    email_teacher_subject = StringField("Teacher confirmation subject", validators=[Optional(), Length(max=200)])
    email_teacher_body = TextAreaField("Teacher confirmation body", validators=[Optional()], render_kw={"rows": 6})
    email_message_subject = StringField("Teacher message email subject", validators=[Optional(), Length(max=200)])
    email_message_body = TextAreaField("Teacher message email body", validators=[Optional()], render_kw={"rows": 6})
    submit = SubmitField("Save settings")


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
