import csv
import io
import math
import os
import secrets
import json
from collections import defaultdict
from datetime import datetime, timedelta
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace

from flask import (
    Blueprint,
    abort,
    current_app,
    flash,
    make_response,
    redirect,
    render_template,
    render_template_string,
    request,
    send_file,
    send_from_directory,
    session,
    url_for,
)
from sqlalchemy import or_, cast, String
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import joinedload
from sqlalchemy.engine.url import make_url
from openpyxl import Workbook
from PyPDF2 import PdfReader, PdfWriter
from reportlab.pdfgen import canvas
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from weasyprint import HTML
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail

from .extensions import db
from .forms import (
    AssignmentBatchForm,
    AdminLoginForm,
    ReadingGroupForm,
    ReadingGroupMemberForm,
    StudentLoginForm,
    StudentRegistrationForm,
    StudentUploadForm,
    TeacherRegistrationForm,
    DashboardSettingsForm,
    TeacherMessageForm,
   TeacherMessageTemplateForm,
   QuickTeacherMessageForm,
   TeacherBoardLoginForm,
    TeacherPortalLoginForm,
    TeacherScoreForm,
    LANGUAGE_CHOICES,
)
from .models import (
    ActivityLog,
    AssignmentBatch,
    EssayAssignment,
    EssayScore,
    EssayAssignmentExtraReader,
    GroupMemberRole,
    PlannerStatus,
    ReadingGroup,
    ReadingGroupMember,
    Stage,
    Student,
    Teacher,
    TeacherLanguage,
    AppSetting,
    TeacherMessage,
    TeacherMessagePriority,
    TeacherMessageStatus,
    TeacherMessageTemplate,
)

web_bp = Blueprint("web", __name__)
teacher_portal_bp = Blueprint("teacher_portal", __name__, url_prefix="/teacher")


ADMIN_MODULES = [
    ("Dashboard", "web.admin_dashboard"),
    ("Planner", "web.admin_planner"),
    ("Students", "web.admin_students"),
    ("Teachers", "web.admin_teachers"),
    ("Uploads", "web.admin_uploads"),
    ("Stage 2", "web.admin_stage2_overview"),
    ("Messages", "web.admin_messages"),
    ("Logs", "web.admin_logs"),
    ("Exports", "web.admin_exports"),
    ("Help", "web.admin_help"),
    ("Settings", "web.admin_settings"),
]


LOG_PAGE_SIZE = 100


SETTING_EMAIL_AUTOMATION_ENABLED = "email_auto_enabled"
SETTING_EMAIL_STUDENT_SUBJECT = "email_student_subject"
SETTING_EMAIL_STUDENT_BODY = "email_student_body"
SETTING_EMAIL_TEACHER_SUBJECT = "email_teacher_subject"
SETTING_EMAIL_TEACHER_BODY = "email_teacher_body"
SETTING_EMAIL_MESSAGE_SUBJECT = "email_message_subject"
SETTING_EMAIL_MESSAGE_BODY = "email_message_body"
SETTING_TEACHER_PORTAL_ENABLED = "teacher_portal_enabled"

DEFAULT_EMAIL_SUBJECTS = {
    SETTING_EMAIL_STUDENT_SUBJECT: "IPO registration confirmed for {{ first_name }} {{ last_name }}",
    SETTING_EMAIL_TEACHER_SUBJECT: "IPO teacher registration confirmed for {{ first_name }} {{ last_name }}",
    SETTING_EMAIL_MESSAGE_SUBJECT: "New IPO teacher board message: {{ title }}",
}

DEFAULT_EMAIL_BODIES = {
    SETTING_EMAIL_STUDENT_BODY: """
<p>Hi {{ first_name }} {{ last_name }},</p>
<p>Thank you for registering for the International Philosophy Olympiad. Below is a summary of the details we received:</p>
<ul>
  <li><strong>Country:</strong> {{ country }}</li>
  <li><strong>School:</strong> {{ school }}</li>
  <li><strong>Essay language:</strong> {{ essay_language }}</li>
  <li><strong>Keyboard preference:</strong> {{ keyboard_preference }}</li>
  <li><strong>Meal preference:</strong> {{ meal_preference }}</li>
  {% if special_needs %}<li><strong>Special needs:</strong> {{ special_needs }}</li>{% endif %}
</ul>
<p>If any information changes, please contact the organizing team as soon as possible.</p>
<p>We are looking forward to seeing you at the Olympiad!</p>
""",
    SETTING_EMAIL_TEACHER_BODY: """
<p>Hi {{ first_name }} {{ last_name }},</p>
<p>Your teacher registration for the International Philosophy Olympiad has been received. Here is a summary of your submission:</p>
<ul>
  <li><strong>Country:</strong> {{ country }}</li>
  <li><strong>School:</strong> {{ school }}</li>
  <li><strong>Languages:</strong> {{ languages }}</li>
  <li><strong>Meal preference:</strong> {{ meal_preference }}</li>
  <li><strong>T-shirt size:</strong> {{ tshirt_size }}</li>
  {% if special_needs %}<li><strong>Special needs:</strong> {{ special_needs }}</li>{% endif %}
  <li><strong>Delegation leader:</strong> {{ 'Yes' if delegation_leader else 'No' }}</li>
  <li><strong>Prior IPO assessor:</strong> {{ 'Yes' if prior_ipo_assessor else 'No' }}</li>
</ul>
<p>We appreciate your support and participation. Please reach out if anything needs to be updated.</p>
""",
    SETTING_EMAIL_MESSAGE_BODY: """
<p>Hello {{ teacher_first_name }} {{ teacher_last_name }},</p>
<p>A new message has been posted on the IPO teacher board.</p>
<p><strong>{{ title }}</strong><br>{{ body|replace('\n', '<br>') }}</p>
<p>Priority: {{ priority|title }}</p>
<p>You can also read this message online: <a href="{{ board_url }}">Teacher Board</a>.</p>
""",
}

STAGE_LABELS = {
    Stage.STAGE_1: "Stage 1",
    Stage.STAGE_2: "Stage 2",
}

PORTAL_STATUS_LABELS = {
    "finalized": "Teacher finalized",
    "in_progress": "Draft saved",
    "awaiting_finalization": "Awaiting student finalization",
    "waiting_upload": "Awaiting essay upload",
    "pending": "Not started",
    "admin_entered": "Admin entered",
    "admin_override": "Admin override",
    "locked": "Locked by admin",
}

SETTING_UPLOAD_DEADLINE = "dashboard_upload_deadline"
SETTING_STAGE2_DEADLINE = "dashboard_stage2_deadline"
SETTING_STAGE1_SLA = "dashboard_stage1_sla_hours"
SETTING_STAGE2_SLA = "dashboard_stage2_sla_hours"
SETTING_STAGE1_LOCK = "grading_stage1_locked"
SETTING_STAGE2_LOCK = "grading_stage2_locked"
SETTING_PACKET_PRINT_MODE = "packet_print_mode"

UPLOAD_ALLOWED_EXTENSIONS = {"pdf"}
MAX_UPLOAD_SIZE = 10 * 1024 * 1024


@web_bp.before_app_request
def protect_admin_routes():
    if request.blueprint != "web":
        return
    path = request.path or ""
    if not path.startswith("/admin"):
        return
    allowed_endpoints = {
        "web.admin_login",
        "web.admin_logout",
    }
    if request.endpoint in allowed_endpoints:
        return
    if _current_admin():
        return
    return redirect(url_for("web.admin_login", next=request.full_path))


@web_bp.app_context_processor
def inject_globals():
    return {
        "current_year": datetime.utcnow().year,
        "current_admin": _current_admin(),
        "ADMIN_MODULES": ADMIN_MODULES,
        "admin_modules": ADMIN_MODULES,
        "teacher_portal_enabled": _teacher_portal_enabled(),
    }


def _ensure_language_entries(teacher: Teacher) -> None:
    if teacher.language_entries:
        return
    if not teacher.languages:
        return
    languages = [lang.strip() for lang in teacher.languages.split(",") if lang.strip()]
    existing = {entry.language for entry in teacher.language_entries}
    for lang in languages:
        if lang not in existing:
            teacher.language_entries.append(TeacherLanguage(language=lang))
    db.session.flush()


def _normalize_language(value: str | None) -> str | None:
    if not value:
        return None
    return value.strip().lower()


def _teacher_languages(teacher: Teacher) -> set[str]:
    _ensure_language_entries(teacher)
    languages: set[str] = set()
    for entry in teacher.language_entries:
        if entry.language:
            languages.add(_normalize_language(entry.language))
    if not languages and teacher.languages:
        for lang in teacher.languages.split(","):
            normalized = _normalize_language(lang)
            if normalized:
                languages.add(normalized)
    return languages


def _teacher_board_authorized() -> bool:
    return bool(session.get("teacher_board") or session.get("teacher_portal_id"))


def _prepare_message_form(form: TeacherMessageForm, selected_teacher_id: int | None = None) -> None:
    teachers = Teacher.query.order_by(Teacher.last_name.asc(), Teacher.first_name.asc()).all()
    choices = [(0, "All teachers")]
    choices.extend((teacher.id, f"{teacher.first_name} {teacher.last_name}") for teacher in teachers)
    form.teacher_id.choices = choices
    if form.teacher_id.data is None:
        form.teacher_id.data = 0
    if selected_teacher_id is not None:
        form.teacher_id.data = selected_teacher_id if selected_teacher_id in {choice[0] for choice in choices} else 0


def _quick_message_context() -> dict:
    form = QuickTeacherMessageForm()
    if not form.priority.data:
        form.priority.data = "normal"
    templates = TeacherMessageTemplate.query.order_by(TeacherMessageTemplate.name.asc()).all()
    templates_data = [
        {
            "id": template.id,
            "name": template.name,
            "title": template.title,
            "body": template.body,
            "category": template.category or "",
        }
        for template in templates
    ]
    return {
        "quick_message_form": form,
        "quick_message_templates": templates,
        "quick_message_templates_data": templates_data,
    }


def _parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _log_filters_from_request() -> dict:
    return {
        "actor": request.args.get("actor", "").strip() or None,
        "action": request.args.get("action", "").strip() or None,
        "object_type": request.args.get("object_type", "").strip() or None,
        "q": request.args.get("q", "").strip() or None,
        "start": _parse_datetime(request.args.get("start") or None),
        "end": _parse_datetime(request.args.get("end") or None),
        "page": request.args.get("page", default=1, type=int),
    }


def _filtered_activity_logs(filters: dict):
    query = ActivityLog.query
    if filters.get("actor"):
        query = query.filter(ActivityLog.actor.ilike(f"%{filters['actor']}%"))
    if filters.get("action"):
        query = query.filter(ActivityLog.action == filters["action"])
    if filters.get("object_type"):
        query = query.filter(ActivityLog.object_type == filters["object_type"])
    if filters.get("q"):
        search = f"%{filters['q']}%"
        query = query.filter(
            or_(
                ActivityLog.description.ilike(search),
                cast(ActivityLog.details, String).ilike(search),
            )
        )
    if filters.get("start"):
        query = query.filter(ActivityLog.created_at >= filters["start"])
    if filters.get("end"):
        query = query.filter(ActivityLog.created_at <= filters["end"])
    return query


def _teacher_can_grade(student: Student, teacher: Teacher, language: str | None) -> bool:
    if not teacher or teacher.is_absent:
        return False
    if student and teacher.country == student.country:
        return False
    normalized_language = _normalize_language(language)
    if normalized_language is None:
        return True
    teacher_langs = _teacher_languages(teacher)
    return normalized_language in teacher_langs


def _empty_load_entry() -> SimpleNamespace:
    return SimpleNamespace(
        stage1_expected=0,
        stage1_completed=0,
        stage2_assigned=0,
        stage2_completed=0,
        last_stage2_activity=None,
    )


def _teacher_load_snapshot(assignments: list[EssayAssignment]) -> dict[int, SimpleNamespace]:
    stats: dict[int, SimpleNamespace] = {}
    for assignment in assignments:
        stage1_scores = {
            score.teacher_id: score
            for score in assignment.scores
            if score.stage == Stage.STAGE_1 and score.score is not None
        }
        stage2_scores = {
            score.teacher_id: score
            for score in assignment.scores
            if score.stage == Stage.STAGE_2 and score.score is not None
        }

        for assessor in _stage_assessors(assignment, Stage.STAGE_1, include_group=True):
            teacher = assessor.teacher
            if not teacher:
                continue
            entry = stats.setdefault(teacher.id, _empty_load_entry())
            entry.stage1_expected += 1
            if stage1_scores.get(teacher.id):
                entry.stage1_completed += 1

        for assessor in _stage_assessors(assignment, Stage.STAGE_2, include_group=False):
            teacher = assessor.teacher
            if not teacher:
                continue
            entry = stats.setdefault(teacher.id, _empty_load_entry())
            entry.stage2_assigned += 1
            score = stage2_scores.get(teacher.id)
            if score:
                entry.stage2_completed += 1
                timestamp = score.submitted_at or score.updated_at
                if timestamp and (entry.last_stage2_activity is None or timestamp > entry.last_stage2_activity):
                    entry.last_stage2_activity = timestamp

    return stats


def _random_username(first_name: str, last_name: str, student_id: int | None = None) -> str:
    base = f"{_slugify(first_name[0])}{_slugify(last_name)}"
    suffix = f"{student_id or ''}{secrets.randbelow(1000)}"
    return f"{base}{suffix}"[:30]


def _generate_unique_username(first_name: str | None, last_name: str | None, max_attempts: int = 20) -> str:
    safe_first = (first_name or "student").strip() or "student"
    safe_last = (last_name or "candidate").strip() or "candidate"

    for attempt in range(max_attempts):
        candidate = _random_username(safe_first, safe_last)
        if not Student.query.filter_by(upload_username=candidate).first():
            return candidate

    fallback = f"{_slugify(safe_first[0])}{secrets.token_hex(4)}"
    return fallback[:30]


def _generate_teacher_portal_username(teacher: Teacher, max_attempts: int = 20) -> str:
    safe_first = (teacher.first_name or "teacher").strip() or "teacher"
    safe_last = (teacher.last_name or "mentor").strip() or "mentor"
    base = f"tch{_slugify(safe_last)[:8]}"
    for _ in range(max_attempts):
        suffix = f"{teacher.id or ''}{secrets.randbelow(1000)}"
        candidate = f"{base}{suffix}"[:30]
        exists = Teacher.query.filter(Teacher.portal_username == candidate).first()
        if not exists:
            return candidate
    return f"tch{secrets.token_hex(4)}"[:30]


def _generate_unique_teacher_token(max_attempts: int = 20) -> str:
    for _ in range(max_attempts):
        token = secrets.token_urlsafe(16)
        if not Teacher.query.filter(Teacher.portal_token == token).first():
            return token
    return secrets.token_hex(16)


def _ensure_teacher_portal_credentials(teacher: Teacher, *, reset_password: bool = False) -> tuple[str, str | None]:
    username_generated = False
    if not teacher.portal_username:
        teacher.portal_username = _generate_teacher_portal_username(teacher)
        username_generated = True

    plain_password: str | None = None
    if reset_password or not teacher.portal_password_hash:
        plain_password = secrets.token_urlsafe(8)
        teacher.portal_password_hash = generate_password_hash(plain_password)
        teacher.portal_token = _generate_unique_teacher_token()

    if username_generated or plain_password is not None:
        db.session.flush()

    return teacher.portal_username, plain_password


def _slugify(value: str) -> str:
    return "".join(ch for ch in value.lower() if ch.isalnum())


def _get_upload_folder() -> Path:
    folder = Path(current_app.config.get("UPLOAD_FOLDER", Path(current_app.instance_path) / "uploads"))
    folder.mkdir(parents=True, exist_ok=True)
    return folder



def _get_active_batch(stage: Stage) -> AssignmentBatch | None:
    return (
        AssignmentBatch.query.filter_by(stage=stage, status=PlannerStatus.PUBLISHED)
        .order_by(
            AssignmentBatch.published_at.is_(None),
            AssignmentBatch.published_at.desc(),
            AssignmentBatch.created_at.desc(),
        )
        .first()
    )

def _student_from_session() -> Student | None:
    student_id = session.get("student_upload_id")
    if not student_id:
        return None
    return db.session.get(Student, student_id)


def _teacher_portal_from_session() -> Teacher | None:
    teacher_id = session.get("teacher_portal_id")
    if not teacher_id:
        return None
    return db.session.get(Teacher, teacher_id)


def _portal_next_url(candidate: str | None) -> str | None:
    if not candidate:
        return None
    candidate = candidate.strip()
    if not candidate.startswith("/"):
        return None
    if candidate.startswith("//"):
        return None
    return candidate


def _teacher_portal_assignment_ids(teacher: Teacher, stage: Stage) -> set[int]:
    assignment_ids: set[int] = set()
    if stage == Stage.STAGE_1:
        group_query = (
            db.session.query(EssayAssignment.id)
            .join(ReadingGroup, EssayAssignment.group_id == ReadingGroup.id)
            .join(ReadingGroupMember, ReadingGroupMember.group_id == ReadingGroup.id)
            .join(AssignmentBatch, AssignmentBatch.id == EssayAssignment.batch_id)
            .filter(
                ReadingGroupMember.teacher_id == teacher.id,
                ReadingGroupMember.active.is_(True),
                ReadingGroup.stage == Stage.STAGE_1,
                AssignmentBatch.status == PlannerStatus.PUBLISHED,
            )
        )
        assignment_ids.update(aid for (aid,) in group_query.all())

        extra_query = (
            db.session.query(EssayAssignmentExtraReader.assignment_id)
            .join(EssayAssignment, EssayAssignment.id == EssayAssignmentExtraReader.assignment_id)
            .join(AssignmentBatch, AssignmentBatch.id == EssayAssignment.batch_id)
            .filter(
                EssayAssignmentExtraReader.teacher_id == teacher.id,
                EssayAssignmentExtraReader.stage == Stage.STAGE_1.value,
                AssignmentBatch.status == PlannerStatus.PUBLISHED,
            )
        )
        assignment_ids.update(aid for (aid,) in extra_query.all())
    else:
        extra_query = (
            db.session.query(EssayAssignmentExtraReader.assignment_id)
            .join(EssayAssignment, EssayAssignment.id == EssayAssignmentExtraReader.assignment_id)
            .join(AssignmentBatch, AssignmentBatch.id == EssayAssignment.batch_id)
            .filter(
                EssayAssignmentExtraReader.teacher_id == teacher.id,
                EssayAssignmentExtraReader.stage == Stage.STAGE_2.value,
                AssignmentBatch.status == PlannerStatus.PUBLISHED,
                EssayAssignment.stage_two_candidate.is_(True),
            )
        )
        assignment_ids.update(aid for (aid,) in extra_query.all())
    return assignment_ids


def _compute_teacher_portal_status(student: Student, score_record: EssayScore | None, pdf_available: bool) -> SimpleNamespace:
    if not pdf_available:
        return SimpleNamespace(code="waiting_upload", label="Awaiting essay upload", css="warning", timestamp=None)
    if not student.essay_finalized:
        return SimpleNamespace(code="awaiting_finalization", label="Awaiting student finalization", css="warning", timestamp=None)
    if score_record and score_record.teacher_finalized:
        timestamp = score_record.teacher_finalized_at or score_record.updated_at
        return SimpleNamespace(code="finalized", label="Teacher finalized", css="success", timestamp=timestamp)
    if score_record and score_record.score is not None:
        timestamp = score_record.submitted_at or score_record.updated_at
        return SimpleNamespace(code="in_progress", label="Draft saved", css="", timestamp=timestamp)
    return SimpleNamespace(code="pending", label="Not started", css="", timestamp=None)


def _resolve_portal_status(
    student: Student,
    score_record: EssayScore | None,
    pdf_available: bool,
    *,
    locked: bool = False,
) -> SimpleNamespace:
    status_info = _compute_teacher_portal_status(student, score_record, pdf_available)
    status_code = status_info.code
    status_css = status_info.css
    status_timestamp = status_info.timestamp

    locked_flag = locked or (score_record.locked_by_admin if score_record else False)

    if locked_flag:
        status_code = "locked"
        status_css = "warning"
        if score_record:
            status_timestamp = score_record.admin_updated_at or status_timestamp or score_record.updated_at
    elif score_record:
        if score_record.admin_override:
            status_code = "admin_override"
            status_css = "warning"
            status_timestamp = score_record.admin_updated_at or score_record.updated_at or status_timestamp
        elif score_record.admin_entered:
            status_code = "admin_entered"
            status_css = ""
            status_timestamp = score_record.admin_updated_at or score_record.updated_at or status_timestamp
        elif score_record.teacher_finalized:
            status_code = "finalized"
            status_css = "success"
            status_timestamp = score_record.teacher_finalized_at or status_timestamp or score_record.updated_at
        elif score_record.score is not None and status_code not in {"awaiting_finalization", "waiting_upload"}:
            status_code = "in_progress"

    resolved_label = PORTAL_STATUS_LABELS.get(status_code, status_info.label or "Not started")
    return SimpleNamespace(code=status_code, label=resolved_label, css=status_css, timestamp=status_timestamp)


def _teacher_portal_assignments(teacher: Teacher, stage: Stage) -> list[SimpleNamespace]:
    assignment_ids = _teacher_portal_assignment_ids(teacher, stage)
    if not assignment_ids:
        return []

    assignments = (
        EssayAssignment.query.options(
            joinedload(EssayAssignment.student),
            joinedload(EssayAssignment.batch),
            joinedload(EssayAssignment.group).joinedload(ReadingGroup.members).joinedload(ReadingGroupMember.teacher),
            joinedload(EssayAssignment.extra_readers),
            joinedload(EssayAssignment.scores),
        )
        .filter(EssayAssignment.id.in_(assignment_ids))
        .order_by(EssayAssignment.id.asc())
        .all()
    )

    global_stage_locked = _is_stage_locked(stage)

    entries: list[SimpleNamespace] = []
    for assignment in assignments:
        student = assignment.student
        if not student or student.is_absent:
            continue
        score_record = next(
            (score for score in assignment.scores if score.teacher_id == teacher.id and score.stage == stage),
            None,
        )
        pdf_path = _essay_pdf_path(student)
        pdf_available = pdf_path is not None
        if stage == Stage.STAGE_2 and not assignment.stage_two_candidate:
            continue
        assignment_locked = assignment.stage1_locked if stage == Stage.STAGE_1 else assignment.stage2_locked
        status_info = _resolve_portal_status(
            student,
            score_record,
            pdf_available,
            locked=(assignment_locked or global_stage_locked),
        )
        status = status_info.code
        essay_available = status not in {"awaiting_finalization", "waiting_upload"}
        resolved_label = status_info.label
        if assignment.group:
            group_label = assignment.group.name or str(assignment.group.id)
        else:
            group_label = "—"
        essay_id = student.id if student else None
        display_label = f"Essay {essay_id}" if essay_id is not None else f"Assignment {assignment.id}"
        entry = SimpleNamespace(
            assignment_id=assignment.id,
            stage=stage,
            essay_id=essay_id,
            display_label=display_label,
            group_label=group_label,
            stage_label=STAGE_LABELS[stage],
            essay_available=essay_available,
            score_record=score_record,
            status=status,
            status_label=resolved_label,
            status_css=status_info.css,
            status_timestamp=status_info.timestamp,
            updated_at=score_record.updated_at if score_record else None,
            finalized=bool(score_record.teacher_finalized) if score_record else False,
            download_url=url_for(
                "teacher_portal.download_assignment",
                assignment_id=assignment.id,
                stage=stage.value,
            )
            if essay_available
            else None,
        )
        entries.append(entry)

    entries.sort(key=lambda entry: (entry.display_label, entry.assignment_id))
    return entries


def _get_stage_one_assignment(student: Student) -> EssayAssignment | None:
    active_batch = _get_active_batch(Stage.STAGE_1)
    if not active_batch:
        return None
    return (
        EssayAssignment.query
        .filter_by(student_id=student.id, stage=Stage.STAGE_1, batch_id=active_batch.id)
        .order_by(EssayAssignment.id.desc())
        .first()
    )


def _stage_assessors(assignment: EssayAssignment | None, stage: Stage, include_group: bool = False) -> list[SimpleNamespace]:
    assessors: list[SimpleNamespace] = []
    if not assignment:
        return assessors

    seen: set[int] = set()
    if include_group and assignment.group:
        for member in assignment.group.members:
            teacher = member.teacher
            if not member.active or not teacher or teacher.is_absent:
                continue
            if teacher.id in seen:
                continue
            assessors.append(
                SimpleNamespace(teacher=teacher, teacher_id=teacher.id, source="Group", is_extra=False, extra_reader=None)
            )
            seen.add(teacher.id)

    for extra in assignment.extra_readers:
        if extra.stage != stage:
            continue
        teacher = extra.teacher
        if not teacher or teacher.is_absent or teacher.id in seen:
            continue
        assessors.append(
            SimpleNamespace(teacher=teacher, teacher_id=teacher.id, source="Extra", is_extra=True, extra_reader=extra)
        )
        seen.add(teacher.id)

    return assessors


def _compute_stage_one_status(assignment: EssayAssignment | None) -> SimpleNamespace:
    assessors = _stage_assessors(assignment, Stage.STAGE_1, include_group=True)
    expected = len(assessors)
    if not assignment:
        return SimpleNamespace(
            entered_scores=0,
            expected_scores=expected,
            average_score=None,
            score_range=None,
            recommendation="No published Stage 1 batch.",
            needs_extra=False,
            stage_two=False,
            completed=False,
        )

    scores = [
        score
        for score in assignment.scores
        if score.stage == Stage.STAGE_1 and score.score is not None
    ]
    entered = len(scores)
    average = sum(s.score for s in scores) / entered if entered else None
    score_range = None
    if len(scores) >= 2:
        values = [s.score for s in scores]
        score_range = max(values) - min(values)

    if expected == 0:
        recommendation = "No active readers assigned."
    elif entered < expected:
        missing = expected - entered
        recommendation = f"Awaiting {missing} reader score{'s' if missing != 1 else ''}."
    elif score_range is not None and score_range > 3:
        recommendation = "Score disparity >3: assign additional reader."
    elif average is not None and average >= 7:
        recommendation = "Qualifies for Stage 2."
    else:
        recommendation = "Average below 7: retain in Stage 1."

    return SimpleNamespace(
        entered_scores=entered,
        expected_scores=expected,
        average_score=average,
        score_range=score_range,
        recommendation=recommendation,
        needs_extra=assignment.needs_additional_reading,
        stage_two=assignment.stage_two_candidate,
        completed=expected > 0 and entered >= expected,
    )



def _compute_stage_two_status(assignment: EssayAssignment | None) -> SimpleNamespace:
    assessors = _stage_assessors(assignment, Stage.STAGE_2, include_group=False)
    expected = len(assessors)
    if not assignment:
        return SimpleNamespace(
            entered_scores=0,
            expected_scores=expected,
            average_score=None,
            score_range=None,
            completed=False,
        )

    scores = [
        score
        for score in assignment.scores
        if score.stage == Stage.STAGE_2 and score.score is not None
    ]
    entered = len(scores)
    average = sum(s.score for s in scores) / entered if entered else None
    score_range = None
    if len(scores) >= 2:
        values = [s.score for s in scores]
        score_range = max(values) - min(values)

    return SimpleNamespace(
        entered_scores=entered,
        expected_scores=expected,
        average_score=average,
        score_range=score_range,
        completed=expected > 0 and entered >= expected,
    )


def _compute_combined_status(assignment: EssayAssignment | None) -> SimpleNamespace:
    if not assignment:
        return SimpleNamespace(count=0, average=None, score_range=None)

    values = [score.score for score in assignment.scores if score.score is not None]
    if not values:
        return SimpleNamespace(count=0, average=None, score_range=None)

    average = sum(values) / len(values)
    score_range = max(values) - min(values) if len(values) >= 2 else None
    return SimpleNamespace(count=len(values), average=average, score_range=score_range)

def _apply_stage_one_rules(assignment: EssayAssignment) -> None:
    status = _compute_stage_one_status(assignment)
    if not status.completed:
        return
    if status.score_range is not None and status.score_range > 3:
        assignment.needs_additional_reading = True
        assignment.stage_two_candidate = False
    else:
        assignment.needs_additional_reading = False
        if status.average_score is not None and status.average_score >= 7:
            assignment.stage_two_candidate = True
        else:
            assignment.stage_two_candidate = False


def _ensure_student_credentials(student: Student) -> None:
    if not student.upload_username:
        student.upload_username = _generate_unique_username(student.first_name, student.last_name)
    if not student.upload_password_hash or not student.upload_token:
        raw_password = secrets.token_urlsafe(8)
        student.upload_password_hash = generate_password_hash(raw_password)
        student.upload_token = raw_password
        student.__dict__["_plain_upload_password"] = raw_password
    db.session.flush()


def _student_from_session() -> Student | None:
    student_id = session.get("student_upload_id")
    if not student_id:
        return None
    return db.session.get(Student, student_id)

def _current_admin() -> str | None:
    return session.get("admin_user")


def _parse_admin_users() -> dict[str, str]:
    raw = current_app.config.get("ADMIN_USERS", "")
    if isinstance(raw, dict):
        return {str(k): str(v) for k, v in raw.items()}
    if isinstance(raw, (list, tuple)):
        entries = [str(item) for item in raw]
    else:
        entries = [segment.strip() for segment in str(raw).split(",") if segment.strip()]
    credentials: dict[str, str] = {}
    for entry in entries:
        if ":" not in entry:
            continue
        username, password = entry.split(":", 1)
        credentials[username.strip()] = password.strip()
    return credentials


def _validate_admin_credentials(username: str, password: str) -> bool:
    credentials = _parse_admin_users()
    stored = credentials.get(username)
    if not stored:
        return False
    if stored.startswith("pbkdf2:") or stored.startswith("scrypt:"):
        return check_password_hash(stored, password)
    return secrets.compare_digest(stored, password)


def log_activity(
    action: str,
    description: str,
    *,
    actor: str | None = None,
    object_type: str | None = None,
    object_id: str | None = None,
    details: dict | None = None,
) -> None:
    actor_name = actor or _current_admin() or "system"
    entry = ActivityLog(
        actor=actor_name,
        action=action,
        description=description,
        object_type=object_type,
        object_id=str(object_id) if object_id is not None else None,
        details=details,
    )
    db.session.add(entry)


def _essay_pdf_path(student: Student) -> Path | None:
    if not student.uploaded_filename:
        return None
    path = _get_upload_folder() / student.uploaded_filename
    if path.exists():
        return path
    return None


def _create_teacher_title_page(teacher: Teacher, group: ReadingGroup, essay_ids: list[int]) -> PdfReader:
    buffer = BytesIO()
    width, height = A4
    c = canvas.Canvas(buffer, pagesize=A4)
    margin = 40

    c.setFont("Helvetica-Bold", 22)
    c.drawString(margin, height - margin - 10, "IPO Essay Packet")
    c.setFont("Helvetica", 14)
    c.drawString(margin, height - margin - 36, f"Group: {group.name or group.id}")

    group_label = getattr(group, "name", None) or getattr(group, "id", "—")
    info_rows = [
        ("Teacher ID", teacher.id),
        ("Name", f"{teacher.first_name} {teacher.last_name}"),
        ("Group", group_label),
    ]

    table_top = height - margin - 70
    row_height = 26
    col_widths = [150, width - 2 * margin - 150]
    c.setLineWidth(1)
    y = table_top
    for label, value in info_rows:
        c.rect(margin, y - row_height, col_widths[0], row_height)
        c.rect(margin + col_widths[0], y - row_height, col_widths[1], row_height)
        c.setFont("Helvetica-Bold", 12)
        c.drawString(margin + 6, y - row_height + 8, str(label))
        c.setFont("Helvetica", 12)
        c.drawString(margin + col_widths[0] + 6, y - row_height + 8, str(value))
        y -= row_height

    essay_table_top = y - 20
    header_height = 26
    essay_row_height = 24
    columns = [180, width - 2 * margin - 180]
    c.rect(margin, essay_table_top - header_height, columns[0], header_height)
    c.rect(margin + columns[0], essay_table_top - header_height, columns[1], header_height)
    c.setFont("Helvetica-Bold", 12)
    c.drawString(margin + 6, essay_table_top - header_height + 8, "Essay ID")
    c.drawString(margin + columns[0] + 6, essay_table_top - header_height + 8, "Score")

    y = essay_table_top - header_height
    c.setFont("Helvetica", 12)
    entries = essay_ids or ["—"]
    for essay_id in entries:
        c.rect(margin, y - essay_row_height, columns[0], essay_row_height)
        c.rect(margin + columns[0], y - essay_row_height, columns[1], essay_row_height)
        c.drawString(margin + 6, y - essay_row_height + 8, str(essay_id))
        y -= essay_row_height
        if y < margin + 40:
            break

    c.save()
    buffer.seek(0)
    return PdfReader(buffer)


def _add_blank_page(writer: PdfWriter, template_page=None) -> None:
    if template_page is not None:
        width = float(template_page.mediabox.right - template_page.mediabox.left)
        height = float(template_page.mediabox.top - template_page.mediabox.bottom)
    else:
        width, height = A4
    writer.add_blank_page(width=width, height=height)


def _packets_double_sided() -> bool:
    return _get_setting(SETTING_PACKET_PRINT_MODE, "single") == "double"


def _auto_email_enabled() -> bool:
    if not current_app.config.get("SENDGRID_API_KEY") or not current_app.config.get("SENDGRID_FROM_EMAIL"):
        return False
    flag = _get_setting(SETTING_EMAIL_AUTOMATION_ENABLED, "false") or "false"
    return flag.lower() == "true"


def _teacher_portal_enabled() -> bool:
    flag = _get_setting(SETTING_TEACHER_PORTAL_ENABLED, "false") or "false"
    return flag.lower() == "true"


def _get_email_subject(key: str) -> str:
    return _get_setting(key) or DEFAULT_EMAIL_SUBJECTS[key]


def _get_email_body(key: str) -> str:
    return _get_setting(key) or DEFAULT_EMAIL_BODIES[key]


def _send_email(to_email: str, subject: str, html_content: str) -> None:
    if not to_email:
        return
    api_key = current_app.config.get("SENDGRID_API_KEY")
    from_email = current_app.config.get("SENDGRID_FROM_EMAIL")
    if not api_key or not from_email:
        current_app.logger.debug("SendGrid not configured; skipping email to %s", to_email)
        return
    try:
        sg = SendGridAPIClient(api_key)
        message = Mail(from_email=from_email, to_emails=to_email, subject=subject, html_content=html_content)
        sg.send(message)
    except Exception as exc:
        current_app.logger.warning("SendGrid error sending to %s: %s", to_email, exc)


def _send_templated_email(to_email: str, subject_key: str, body_key: str, context: dict) -> None:
    if not _auto_email_enabled():
        return
    subject_template = _get_email_subject(subject_key)
    body_template = _get_email_body(body_key)
    subject = render_template_string(subject_template, **context)
    body = render_template_string(body_template, **context)
    _send_email(to_email, subject, body)


def _send_student_confirmation_email(student: Student) -> None:
    if not _auto_email_enabled() or not student.email:
        return
    context = {
        "first_name": student.first_name,
        "last_name": student.last_name,
        "email": student.email,
        "country": student.country,
        "school": student.school,
        "essay_language": student.essay_language,
        "keyboard_preference": student.keyboard_preference,
        "meal_preference": student.meal_preference,
        "special_needs": student.special_needs or "",
    }
    _send_templated_email(student.email, SETTING_EMAIL_STUDENT_SUBJECT, SETTING_EMAIL_STUDENT_BODY, context)


def _send_teacher_confirmation_email(teacher: Teacher) -> None:
    if not _auto_email_enabled() or not teacher.email:
        return
    context = {
        "first_name": teacher.first_name,
        "last_name": teacher.last_name,
        "email": teacher.email,
        "country": teacher.country,
        "school": teacher.school,
        "languages": teacher.languages,
        "meal_preference": teacher.meal_preference,
        "tshirt_size": teacher.tshirt_size,
        "special_needs": teacher.special_needs or "",
        "delegation_leader": teacher.delegation_leader,
        "prior_ipo_assessor": teacher.prior_ipo_assessor,
    }
    _send_templated_email(teacher.email, SETTING_EMAIL_TEACHER_SUBJECT, SETTING_EMAIL_TEACHER_BODY, context)


def _send_teacher_message_notifications(message: TeacherMessage) -> None:
    if not _auto_email_enabled():
        return
    recipients: list[Teacher] = []
    if message.deliver_to_all:
        recipients = (
            Teacher.query.filter(
                Teacher.email.isnot(None),
                Teacher.is_absent.is_(False),
            ).all()
        )
    elif message.teacher:
        recipients = [message.teacher]
    unique = {}
    for teacher in recipients:
        if not teacher or not teacher.email:
            continue
        if teacher.id in unique:
            continue
        unique[teacher.id] = teacher

    board_url = url_for("web.teacher_board", _external=True)
    for teacher in unique.values():
        context = {
            "teacher_first_name": teacher.first_name,
            "teacher_last_name": teacher.last_name,
            "teacher_email": teacher.email,
            "title": message.title,
            "body": message.body,
            "priority": message.priority.value,
            "board_url": board_url,
        }
        _send_templated_email(teacher.email, SETTING_EMAIL_MESSAGE_SUBJECT, SETTING_EMAIL_MESSAGE_BODY, context)


def _create_essay_overlay_page(page, group: ReadingGroup, assignment: EssayAssignment) -> PdfReader:
    buffer = BytesIO()
    width = float(page.mediabox.right - page.mediabox.left)
    height = float(page.mediabox.top - page.mediabox.bottom)
    c = canvas.Canvas(buffer, pagesize=(width, height))
    margin = 36
    table_height = 36
    table_width = width - 2 * margin
    top = height - margin

    c.setStrokeColor(colors.black)
    c.setLineWidth(1)
    c.setFont("Helvetica-Bold", 12)
    c.drawString(margin, top + 4, "IPO Essay")

    c.rect(margin, top - table_height, table_width, table_height)
    col_width = table_width / 3
    for i in range(1, 3):
        c.line(margin + col_width * i, top - table_height, margin + col_width * i, top)

    group_label = getattr(group, "name", None) or getattr(group, "id", "—")
    essay_id = assignment.student.id if assignment.student else "—"
    labels = [
        ("Group", group_label),
        ("Essay", essay_id),
        ("Score", "     /10"),
    ]

    for idx, (label, value) in enumerate(labels):
        x = margin + col_width * idx + 6
        c.setFont("Helvetica-Bold", 10)
        c.drawString(x, top - 14, str(label))
        c.setFont("Helvetica", 10)
        c.drawString(x, top - 28, str(value))

    c.save()
    buffer.seek(0)
    return PdfReader(buffer)


def _planner_teacher_choices(stage: Stage, language: str | None = None) -> list[tuple[int, str]]:
    teachers = (
        Teacher.query.filter_by(is_absent=False)
        .order_by(Teacher.last_name.asc(), Teacher.first_name.asc())
        .all()
    )
    choices: list[tuple[int, str]] = []
    for teacher in teachers:
        _ensure_language_entries(teacher)
        languages = {entry.language for entry in teacher.language_entries}
        if language and language not in languages:
            continue
        display_langs = ", ".join(sorted(languages)) if languages else teacher.languages
        label = f"{teacher.first_name} {teacher.last_name} · {teacher.country} ({display_langs})"
        choices.append((teacher.id, label))
    return choices


def _teacher_has_active_group(teacher_id: int, stage: Stage, exclude_group_id: int | None = None) -> bool:
    query = (
        ReadingGroupMember.query.join(ReadingGroup)
        .filter(
            ReadingGroupMember.teacher_id == teacher_id,
            ReadingGroup.stage == stage,
            ReadingGroupMember.active.is_(True),
        )
    )
    if exclude_group_id is not None:
        query = query.filter(ReadingGroupMember.group_id != exclude_group_id)
    return db.session.query(query.exists()).scalar()


def _load_batch_groups(batch: AssignmentBatch) -> list[ReadingGroup]:
    return (
        ReadingGroup.query.options(
            joinedload(ReadingGroup.members).joinedload(ReadingGroupMember.teacher),
            joinedload(ReadingGroup.assignments).joinedload(EssayAssignment.student),
        )
        .filter(ReadingGroup.batch_id == batch.id)
        .order_by(ReadingGroup.language.asc(), ReadingGroup.name.asc())
        .all()
    )


def _auto_generate_groups_for_batch(batch: AssignmentBatch) -> dict[str, int | dict[str, int]]:
    removed_groups = 0
    for group in list(batch.groups):
        if group.auto_generated:
            for assignment in list(group.assignments):
                if assignment.manual_override:
                    assignment.group_id = None
                else:
                    db.session.delete(assignment)
            db.session.delete(group)
            removed_groups += 1

    db.session.flush()

    manual_teacher_ids: set[int] = set()
    manual_teacher_counts: dict[str, int] = defaultdict(int)
    manual_group_counts: dict[str, int] = defaultdict(int)
    for group in batch.groups:
        if group.stage != batch.stage:
            continue
        if not group.auto_generated:
            manual_group_counts[group.language] += 1
        for member in group.members:
            if not member.teacher or member.teacher.is_absent:
                continue
            manual_teacher_ids.add(member.teacher_id)
            if not group.auto_generated and member.active:
                manual_teacher_counts[group.language] += 1

    student_counts: dict[str, int] = defaultdict(int)
    for language, in Student.query.filter_by(is_absent=False).with_entities(Student.essay_language):
        if language:
            student_counts[language] += 1

    teachers = (
        Teacher.query.filter_by(is_absent=False)
        .order_by(Teacher.last_name.asc(), Teacher.first_name.asc())
        .all()
    )

    teacher_lookup: dict[int, Teacher] = {}
    eligible_teachers: list[Teacher] = []
    teacher_languages_map: dict[int, set[str]] = {}
    language_capacity: dict[str, int] = defaultdict(int)

    for teacher in teachers:
        teacher_lookup[teacher.id] = teacher
        if teacher.id in manual_teacher_ids:
            continue
        _ensure_language_entries(teacher)
        if _teacher_has_active_group(teacher.id, batch.stage):
            continue
        languages_spoken = {entry.language for entry in teacher.language_entries if entry.language}
        if not languages_spoken:
            continue
        eligible_teachers.append(teacher)
        teacher_languages_map[teacher.id] = languages_spoken
        for language in languages_spoken:
            language_capacity[language] += 1

    total_eligible = len(eligible_teachers)
    full_groups = total_eligible // 4
    remainder = total_eligible % 4
    slots_to_assign = full_groups * 4

    summary: dict[str, int | dict[str, int]] = {"removed": removed_groups}

    if full_groups == 0:
        summary["created"] = {}
        summary["backups"] = total_eligible
        _recalculate_group_targets(batch, student_counts)
        return summary

    min_per_teacher_load = max(current_app.config.get("PLANNER_MIN_PER_TEACHER_LOAD", 3), 1)
    languages = set(student_counts.keys()) | set(language_capacity.keys())

    language_group_capacity: dict[str, int] = {language: language_capacity.get(language, 0) // 4 for language in languages}
    language_min_groups: dict[str, int] = {}
    shortfalls: dict[str, int] = {}
    total_min_groups = 0

    for language in languages:
        capacity_groups = language_group_capacity.get(language, 0)
        if capacity_groups == 0:
            language_min_groups[language] = 0
            if student_counts.get(language, 0) > 0:
                required_slots = max(4, math.ceil(student_counts[language] / min_per_teacher_load))
                manual_slots = manual_teacher_counts.get(language, 0)
                needed_slots = max(required_slots - manual_slots, 0)
                if needed_slots > 0:
                    shortfalls[language] = needed_slots
            continue

        required_slots = 0
        if student_counts.get(language, 0) > 0:
            required_slots = max(4, math.ceil(student_counts[language] / min_per_teacher_load))
        manual_slots = manual_teacher_counts.get(language, 0)
        needed_slots = max(required_slots - manual_slots, 0)
        required_groups = math.ceil(needed_slots / 4) if needed_slots else 0
        min_groups = min(required_groups, capacity_groups)
        language_min_groups[language] = min_groups
        total_min_groups += min_groups
        if required_groups > capacity_groups:
            shortfalls[language] = (required_groups - capacity_groups) * 4

    if total_min_groups > full_groups:
        summary["created"] = {}
        summary["backups"] = total_eligible
        if shortfalls:
            summary["shortfall"] = shortfalls
        summary["matching_failed"] = True
        _recalculate_group_targets(batch, student_counts)
        return summary

    language_group_plan: dict[str, int] = {language: language_min_groups.get(language, 0) for language in languages}
    assigned_groups = sum(language_group_plan.values())
    remaining_groups = full_groups - assigned_groups

    def _best_language_for_extra_group() -> str | None:
        best_language = None
        best_score = None
        for language in languages:
            capacity = language_group_capacity.get(language, 0)
            current = language_group_plan.get(language, 0)
            if current >= capacity:
                continue
            manual_slots = manual_teacher_counts.get(language, 0)
            assigned_slots = current * 4
            score = student_counts.get(language, 0) / max(1, manual_slots + assigned_slots)
            if best_language is None or score > best_score or (
                math.isclose(score, best_score or 0.0) and student_counts.get(language, 0) > student_counts.get(best_language, 0)
            ):
                best_language = language
                best_score = score
        return best_language

    while remaining_groups > 0:
        language = _best_language_for_extra_group()
        if language is None:
            break
        language_group_plan[language] = language_group_plan.get(language, 0) + 1
        remaining_groups -= 1

    if sum(language_group_plan.values()) < full_groups:
        summary["created"] = {}
        summary["backups"] = total_eligible
        if shortfalls:
            summary["shortfall"] = shortfalls
        summary["matching_failed"] = True
        _recalculate_group_targets(batch, student_counts)
        return summary

    def _group_plan_to_slots(plan: dict[str, int]) -> dict[str, int]:
        return {language: count * 4 for language, count in plan.items() if count > 0}

    language_slot_plan = _group_plan_to_slots(language_group_plan)
    planned_slot_total = sum(language_slot_plan.values())
    if planned_slot_total != slots_to_assign:
        summary["created"] = {}
        summary["backups"] = total_eligible
        if shortfalls:
            summary["shortfall"] = shortfalls
        summary["matching_failed"] = True
        _recalculate_group_targets(batch, student_counts)
        return summary

    def _match_teachers_to_slots(plan: dict[str, int]) -> tuple[dict[str, list[int]] | None, dict[str, int]]:
        slots: list[str] = []
        slot_language: dict[str, str] = {}
        for language, count in plan.items():
            for idx in range(count):
                slot_id = f"{language}#{idx}"
                slots.append(slot_id)
                slot_language[slot_id] = language

        adjacency: dict[int, list[str]] = {}
        for teacher in eligible_teachers:
            langs = teacher_languages_map.get(teacher.id, set())
            adjacency[teacher.id] = [slot for slot in slots if slot_language[slot] in langs]

        match_slot: dict[str, int] = {}
        match_teacher: dict[int, str] = {}

        teacher_order = sorted(
            eligible_teachers,
            key=lambda t: (len(adjacency.get(t.id, [])), t.id),
        )

        def dfs(teacher_id: int, seen: set[str]) -> bool:
            for slot in adjacency.get(teacher_id, []):
                if slot in seen:
                    continue
                seen.add(slot)
                if slot not in match_slot or dfs(match_slot[slot], seen):
                    match_slot[slot] = teacher_id
                    match_teacher[teacher_id] = slot
                    return True
            return False

        for teacher in teacher_order:
            dfs(teacher.id, set())

        if len(match_slot) < len(slots):
            return None, {}

        assignments: dict[str, list[int]] = defaultdict(list)
        for slot, teacher_id in match_slot.items():
            assignments[slot_language[slot]].append(teacher_id)
        return assignments, {language: plan.get(language, 0) for language in plan}

    assignments, _ = _match_teachers_to_slots(language_slot_plan)
    adjustment_attempts = 0
    while assignments is None and adjustment_attempts < len(language_group_plan) + 5:
        reducible = [
            language
            for language, group_count in language_group_plan.items()
            if group_count > language_min_groups.get(language, 0)
        ]
        if not reducible:
            break
        reducible.sort(
            key=lambda language: (
                -(language_group_plan.get(language, 0) - language_min_groups.get(language, 0)),
                student_counts.get(language, 0),
                language,
            )
        )
        language_to_reduce = reducible[0]
        language_group_plan[language_to_reduce] -= 1

        while sum(language_group_plan.values()) < full_groups:
            candidate = _best_language_for_extra_group()
            if candidate is None:
                break
            if language_group_plan.get(candidate, 0) >= language_group_capacity.get(candidate, 0):
                break
            language_group_plan[candidate] = language_group_plan.get(candidate, 0) + 1

        if sum(language_group_plan.values()) < full_groups:
            break

        language_slot_plan = _group_plan_to_slots(language_group_plan)
        assignments, _ = _match_teachers_to_slots(language_slot_plan)
        adjustment_attempts += 1

    if assignments is None:
        summary["created"] = {}
        summary["backups"] = total_eligible
        if shortfalls:
            summary["shortfall"] = shortfalls
        summary["matching_failed"] = True
        _recalculate_group_targets(batch, student_counts)
        return summary

    created_count: dict[str, int] = defaultdict(int)
    used_teacher_ids: set[int] = set()

    def _build_groups_for_language(language: str, teacher_ids: list[int]) -> list[list[Teacher]]:
        teachers_in_language = [teacher_lookup[tid] for tid in teacher_ids]
        teachers_in_language.sort(key=lambda t: (t.country, t.last_name, t.first_name, t.id))
        groups: list[list[Teacher]] = []
        pool = teachers_in_language
        while len(pool) >= 4:
            selected: list[Teacher] = []
            used_countries: set[str] = set()
            remainder_list: list[Teacher] = []
            for teacher in pool:
                if len(selected) == 4:
                    remainder_list.append(teacher)
                    continue
                if teacher.country not in used_countries:
                    selected.append(teacher)
                    used_countries.add(teacher.country)
                else:
                    remainder_list.append(teacher)
            if len(selected) < 4:
                needed = 4 - len(selected)
                selected.extend(remainder_list[:needed])
                remainder_list = remainder_list[needed:]
            groups.append(selected)
            pool = remainder_list
        return groups

    for language, teacher_ids in assignments.items():
        if not teacher_ids:
            continue
        language_groups = _build_groups_for_language(language, teacher_ids)
        for members in language_groups:
            group_name = f"{language} Group {created_count[language] + manual_group_counts.get(language, 0) + 1}"
            group = ReadingGroup(
                name=group_name,
                language=language,
                stage=batch.stage,
                target_essay_load=0,
                allow_same_country=False,
                auto_generated=True,
                status=batch.status,
                batch=batch,
            )
            db.session.add(group)
            db.session.flush()
            for idx, teacher in enumerate(members):
                role = GroupMemberRole.LEADER if idx == 0 else GroupMemberRole.READER
                member = ReadingGroupMember(
                    group_id=group.id,
                    teacher_id=teacher.id,
                    role=role,
                    active=True,
                )
                db.session.add(member)
                used_teacher_ids.add(teacher.id)
            created_count[language] += 1

    matched_teacher_ids = used_teacher_ids.copy()
    backup_teachers = [teacher for teacher in eligible_teachers if teacher.id not in matched_teacher_ids]

    if remainder == 0:
        backup_teachers = []

    if backup_teachers:
        target_groups = [
            group
            for group in batch.groups
            if group.stage == batch.stage and group.auto_generated and not db.inspect(group).deleted
        ]
        target_groups.sort(key=lambda g: (g.language, g.id))
        if target_groups:
            for idx, teacher in enumerate(backup_teachers):
                group = target_groups[idx % len(target_groups)]
                member = ReadingGroupMember(
                    group_id=group.id,
                    teacher_id=teacher.id,
                    role=GroupMemberRole.BACKUP,
                    active=False,
                )
                db.session.add(member)
                used_teacher_ids.add(teacher.id)

    summary_created = {language: count for language, count in created_count.items() if count}
    summary["created"] = summary_created
    summary["backups"] = len(backup_teachers)
    if shortfalls:
        summary["shortfall"] = shortfalls

    _recalculate_group_targets(batch, student_counts)
    return summary


def _recalculate_group_targets(batch: AssignmentBatch, student_counts: dict[str, int] | None = None) -> None:
    if student_counts is None:
        counts: dict[str, int] = defaultdict(int)
        for language, in Student.query.filter_by(is_absent=False).with_entities(Student.essay_language):
            if language:
                counts[language] += 1
        student_counts = counts

    min_per_teacher_load = max(current_app.config.get("PLANNER_MIN_PER_TEACHER_LOAD", 3), 1)

    groups_by_language: dict[str, list[ReadingGroup]] = defaultdict(list)
    for group in batch.groups:
        if group.stage != batch.stage:
            continue
        groups_by_language[group.language].append(group)

    for language, groups in groups_by_language.items():
        total_students = student_counts.get(language, 0)
        active_counts: dict[int, int] = {}
        total_active_teachers = 0

        for group in groups:
            active_members = [
                member
                for member in group.members
                if member.active and member.teacher and not member.teacher.is_absent
            ]
            active_count = len(active_members)
            if active_count == 0:
                group.target_essay_load = 0
                continue
            active_counts[group.id] = active_count
            total_active_teachers += active_count

        if total_active_teachers == 0:
            continue

        per_teacher_load = max(math.ceil(total_students / total_active_teachers), min_per_teacher_load)

        for group in groups:
            active_count = active_counts.get(group.id)
            if not active_count:
                continue
            group.target_essay_load = max(per_teacher_load * active_count, 1)


def _auto_assign_essays(batch: AssignmentBatch) -> tuple[int, list[Student]]:
    # remove existing non-manual assignments
    for assignment in list(batch.assignments):
        if assignment.manual_override:
            continue
        db.session.delete(assignment)
    db.session.flush()
    _recalculate_group_targets(batch)

    groups = [group for group in batch.groups if group.members]
    if not groups:
        return 0, []

    group_teacher_countries: dict[int, set[str]] = {}
    for group in groups:
        countries = {
            member.teacher.country
            for member in group.members
            if member.active and member.teacher and not member.teacher.is_absent
        }
        group_teacher_countries[group.id] = countries

    group_assignment_counts: dict[int, int] = defaultdict(int)
    for assignment in batch.assignments:
        if assignment.group_id:
            group_assignment_counts[assignment.group_id] += 1

    students = (
        Student.query.filter_by(is_absent=False)
        .order_by(Student.essay_language.asc(), Student.country.asc())
        .all()
    )
    skipped: list[Student] = []
    assigned = 0

    for student in students:
        manual_assignment = next(
            (a for a in batch.assignments if a.student_id == student.id and a.manual_override),
            None,
        )
        if manual_assignment:
            continue

        candidate_groups = []
        for group in groups:
            if group.language != student.essay_language:
                continue
            if group.locked:
                continue
            active_members = [
                member
                for member in group.members
                if member.active and member.teacher and not member.teacher.is_absent
            ]
            if len(active_members) < 4:
                continue
            current_load = group_assignment_counts.get(group.id, 0)
            if current_load >= group.target_essay_load:
                continue
            countries = group_teacher_countries.get(group.id, set())
            if not group.allow_same_country and student.country in countries:
                continue
            if _teacher_has_active_group_conflict(group, student.country):
                continue
            candidate_groups.append(group)

        if not candidate_groups:
            skipped.append(student)
            continue

        candidate_groups.sort(
            key=lambda grp: (
                group_assignment_counts.get(grp.id, 0),
                grp.target_essay_load,
                grp.id,
            )
        )
        chosen_group = candidate_groups[0]
        assignment = EssayAssignment(
            student_id=student.id,
            group_id=chosen_group.id,
            batch=batch,
            stage=batch.stage,
            manual_override=False,
            status=PlannerStatus.DRAFT,
        )
        db.session.add(assignment)
        group_assignment_counts[chosen_group.id] += 1
        assigned += 1

    return assigned, skipped


def _teacher_has_active_group_conflict(group: ReadingGroup, student_country: str) -> bool:
    if group.allow_same_country:
        return False
    for member in group.members:
        if not member.active or not member.teacher or member.teacher.is_absent:
            continue
        if member.teacher.country == student_country:
            return True
    return False


def _render_pdf(template_name: str, filename: str, **context):
    html = render_template(template_name, **context)
    pdf_bytes = HTML(string=html, base_url=request.url_root).write_pdf()
    response = make_response(pdf_bytes)
    response.headers["Content-Type"] = "application/pdf"
    response.headers["Content-Disposition"] = f"attachment; filename={filename}"
    return response


def _run_mysqldump(output_path: Path) -> bool:
    database_url = _get_database_url()
    if not database_url or "mysql" not in database_url:
        return False

    url = make_url(database_url)
    env = os.environ.copy()
    if url.password:
        env["MYSQL_PWD"] = url.password

    cmd = [
        "mysqldump",
        f"--host={url.host or 'localhost'}",
        f"--port={url.port or 3306}",
        f"--user={url.username or ''}",
        url.database or "",
    ]

    import subprocess

    with output_path.open("wb") as fh:
        subprocess.check_call(cmd, env=env, stdout=fh)
    return True


def _get_database_url() -> str | None:
    return current_app.config.get("DATABASE_URL") or current_app.config.get("SQLALCHEMY_DATABASE_URI")


def _export_database() -> tuple[Path, str] | None:
    backups_dir = Path(current_app.config.get("BACKUP_FOLDER", Path(current_app.instance_path) / "backups"))
    backups_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.utcnow().strftime("%Y%m%d-%H%M%S")
    filename = f"ipo-db-{timestamp}.sql"
    output_path = backups_dir / filename

    database_url = _get_database_url() or ""
    if database_url.startswith("sqlite"):
        db_path = database_url.replace("sqlite://", "")
        db_file = Path(db_path)
        if not db_file.exists():
            return None
        import shutil

        shutil.copyfile(db_file, output_path)
        return output_path, filename

    if "mysql" in database_url:
        if _run_mysqldump(output_path):
            return output_path, filename

    return None


def _zip_essays(only_finalized: bool = False) -> tuple[BytesIO, str] | None:
    base_folder = Path(_get_upload_folder())
    if not base_folder.exists():
        return None

    timestamp = datetime.utcnow().strftime("%Y%m%d-%H%M%S")
    zip_buffer = BytesIO()
    import zipfile
    import csv as csv_module

    students_query = Student.query
    if only_finalized:
        students_query = students_query.filter(Student.essay_finalized.is_(True))
    students = students_query.order_by(Student.id.asc()).all()

    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        manifest_rows = []
        for student in students:
            pdf_path = _essay_pdf_path(student)
            if not pdf_path or not pdf_path.exists():
                continue
            safe_name = f"{student.id}-{student.last_name}_{student.first_name}.pdf"
            manifest_rows.append(
                {
                    "student_id": student.id,
                    "first_name": student.first_name,
                    "last_name": student.last_name,
                    "country": student.country,
                    "uploaded_at": student.uploaded_at.isoformat() if student.uploaded_at else "",
                    "finalized": "yes" if student.essay_finalized else "no",
                    "filename": Path(pdf_path).name,
                }
            )
            archive.write(pdf_path, f"essays/{safe_name}")

        manifest_bytes = io.StringIO()
        fieldnames = ["student_id", "first_name", "last_name", "country", "uploaded_at", "finalized", "filename"]
        writer = csv_module.DictWriter(manifest_bytes, fieldnames=fieldnames)
        writer.writeheader()
        for row in manifest_rows:
            writer.writerow(row)
        archive.writestr("manifest.csv", manifest_bytes.getvalue())

    zip_buffer.seek(0)
    filename = f"ipo-essays-{timestamp}.zip"
    return zip_buffer, filename


def _build_teacher_schedules(groups: list[ReadingGroup]) -> list[dict]:
    schedule_map: dict[int, dict] = {}
    for group in groups:
        assignments = sorted(
            group.assignments,
            key=lambda assignment: (
                assignment.student.essay_language if assignment.student else "",
                assignment.student.country if assignment.student else "",
            ),
        )
        for member in group.members:
            if not member.active or not member.teacher:
                continue
            teacher = member.teacher
            entry = schedule_map.setdefault(
                teacher.id,
                {
                    "teacher": teacher,
                    "group": group,
                    "role": member.role,
                    "assignments": [],
                },
            )
            entry["assignments"] = assignments
            entry["role"] = member.role

    schedules = list(schedule_map.values())
    schedules.sort(key=lambda item: (item["teacher"].last_name, item["teacher"].first_name))
    return schedules


@web_bp.route("/")
def index():
    return render_template("index.html")


@web_bp.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    if _current_admin():
        return redirect(request.args.get("next") or url_for("web.admin_dashboard"))

    form = AdminLoginForm()
    next_url = request.args.get("next") or request.form.get("next")
    credentials = _parse_admin_users()
    if not credentials:
        flash("No admin accounts configured. Please set ADMIN_USERS.", "error")

    if form.validate_on_submit() and credentials:
        username = form.username.data.strip()
        if _validate_admin_credentials(username, form.password.data):
            session["admin_user"] = username
            session.permanent = True
            log_activity("admin_login", f"{username} signed in", actor=username)
            db.session.commit()
            flash("Signed in successfully.", "success")
            return redirect(next_url or url_for("web.admin_dashboard"))
        else:
            log_activity("admin_login_failed", f"Failed login attempt for {username}", actor=username)
            db.session.commit()
            flash("Invalid credentials.", "error")

    return render_template("admin/login.html", form=form, next_url=next_url)


@web_bp.route("/admin/logout")
def admin_logout():
    username = _current_admin()
    if username:
        log_activity("admin_logout", f"{username} signed out", actor=username)
        db.session.commit()
    session.pop("admin_user", None)
    flash("Signed out.", "success")
    return redirect(url_for("web.admin_login"))


@web_bp.route("/participant/login", methods=["GET", "POST"])
def student_login():
    form = StudentLoginForm()
    if form.validate_on_submit():
        username = form.username.data.strip()
        student = Student.query.filter_by(upload_username=username, is_absent=False).first()
        if not student or not student.upload_password_hash:
            flash("Invalid credentials.", "error")
        elif not check_password_hash(student.upload_password_hash, form.password.data.strip()):
            flash("Invalid credentials.", "error")
            log_activity(
                "student_upload_login_failed",
                f"Failed login for {username}",
                details={"username": username},
            )
            db.session.commit()
        else:
            session["student_upload_id"] = student.id
            log_activity(
                "student_upload_login",
                f"Student {student.first_name} {student.last_name} signed in",
                object_type="student",
                object_id=student.id,
                details={"username": student.upload_username},
            )
            db.session.commit()
            return redirect(url_for("web.student_upload"))
    return render_template("student/login.html", form=form)


@web_bp.route("/participant/logout")
def student_logout():
    student = _student_from_session()
    if student:
        log_activity(
            "student_upload_logout",
            f"Student {student.first_name} {student.last_name} signed out",
            object_type="student",
            object_id=student.id,
        )
        db.session.commit()
    session.pop("student_upload_id", None)
    flash("Signed out.", "success")
    return redirect(url_for("web.student_login"))


@web_bp.route("/participant/upload", methods=["GET", "POST"])
def student_upload():
    student = _student_from_session()
    if not student or student.is_absent:
        flash("Please log in before uploading your essay.", "error")
        return redirect(url_for("web.student_login"))
    form = StudentUploadForm()
    action = request.form.get("action", "upload").strip()

    if request.method == "POST" and action == "finalize":
        if student.essay_finalized:
            flash("Your essay is already marked as finished.", "info")
        elif not student.uploaded_filename:
            flash("Upload your essay before marking it as finished.", "error")
        else:
            student.essay_finalized = True
            student.essay_finalized_at = datetime.utcnow()
            db.session.flush()
            log_activity(
                "student_essay_finalized",
                f"Student {student.first_name} {student.last_name} finalized essay",
                object_type="student",
                object_id=student.id,
                details={"filename": student.uploaded_filename},
            )
            db.session.commit()
            flash("Your essay has been marked as finished. Further uploads are disabled.", "success")
        return redirect(url_for("web.student_upload"))

    if student.essay_finalized:
        return render_template("student/upload.html", form=form, student=student)

    if form.validate_on_submit():
        file = form.essay.data
        if not file:
            flash("No file provided.", "error")
            return redirect(url_for("web.student_upload"))
        filename = secure_filename(file.filename or "")
        if not filename.lower().endswith(".pdf"):
            flash("Only PDF files are allowed.", "error")
            return redirect(url_for("web.student_upload"))
        file.seek(0, 2)
        size = file.tell()
        file.seek(0)
        if size > MAX_UPLOAD_SIZE:
            flash("File too large (max 10 MB).", "error")
            return redirect(url_for("web.student_upload"))
        upload_folder = _get_upload_folder()
        timestamp = datetime.utcnow().strftime("%Y%m%d%H%M%S")
        stored_name = f"student-{student.id}-{timestamp}.pdf"
        file_path = upload_folder / stored_name
        file.save(file_path)
        if student.uploaded_filename:
            old_path = upload_folder / student.uploaded_filename
            if old_path.exists():
                old_path.unlink()
        student.uploaded_filename = stored_name
        student.uploaded_at = datetime.utcnow()
        student.essay_finalized = False
        student.essay_finalized_at = None
        log_activity(
            "student_essay_uploaded",
            f"Student {student.first_name} {student.last_name} uploaded essay",
            object_type="student",
            object_id=student.id,
            details={"filename": stored_name},
        )
        db.session.commit()
        flash("Essay uploaded successfully.", "success")
        return redirect(url_for("web.student_upload"))
    return render_template("student/upload.html", form=form, student=student)


@web_bp.route("/participant/upload/preview")
def student_upload_preview():
    student = _student_from_session()
    if not student or student.is_absent or not student.uploaded_filename:
        abort(404)
    pdf_path = _essay_pdf_path(student)
    if not pdf_path or not pdf_path.exists():
        abort(404)
    response = send_file(str(pdf_path), mimetype="application/pdf")
    response.headers["Cache-Control"] = "no-store"
    return response


@web_bp.route("/register/student", methods=["GET", "POST"])
def register_student():
    form = StudentRegistrationForm()
    if not form.is_submitted():
        form.submit.label.text = "Submit registration"
        form.is_absent.data = False
    if form.validate_on_submit():
        student = Student(
            first_name=form.first_name.data.strip(),
            last_name=form.last_name.data.strip(),
            email=form.email.data.lower().strip(),
            country=form.country.data.strip(),
            school=form.school.data.strip(),
            gender=form.gender.data,
            date_of_birth=form.date_of_birth.data,
            essay_language=form.essay_language.data,
            keyboard_preference=form.keyboard_preference.data,
            meal_preference=form.meal_preference.data,
            special_needs=(form.special_needs.data.strip() or None)
            if form.special_needs.data
            else None,
            is_absent=bool(form.is_absent.data),
        )
        _ensure_student_credentials(student)
        db.session.add(student)
        try:
            db.session.flush()
            log_activity(
    "student_registered",
    f"Student {student.first_name} {student.last_name} registered",
    object_type="student",
    object_id=student.id,
    details={
        "email": student.email,
        "country": student.country,
        "language": student.essay_language,
        "upload_username": student.upload_username,
    },
)
            db.session.commit()
            _send_student_confirmation_email(student)
            flash("Student registered successfully.", "success")
            return redirect(url_for("web.register_student"))
        except IntegrityError:
            db.session.rollback()
            flash("This email address is already registered.", "error")

    return render_template("register_student.html", form=form, show_absence_toggle=False)


@web_bp.route("/register/teacher", methods=["GET", "POST"])
def register_teacher():
    form = TeacherRegistrationForm()
    if not form.is_submitted() and not form.languages.data:
        form.languages.data = ["English"]
    form.submit.label.text = "Submit registration"
    if not form.is_submitted():
        form.is_absent.data = False
    if form.validate_on_submit():
        teacher = Teacher(
            first_name=form.first_name.data.strip(),
            last_name=form.last_name.data.strip(),
            email=form.email.data.lower().strip(),
            country=form.country.data.strip(),
            school=form.school.data.strip(),
            gender=form.gender.data,
            languages=", ".join(form.languages.data),
            meal_preference=form.meal_preference.data,
            tshirt_size=form.tshirt_size.data,
            special_needs=(form.special_needs.data.strip() or None)
            if form.special_needs.data
            else None,
            delegation_leader=bool(form.delegation_leader.data),
            language_entries=[TeacherLanguage(language=lang) for lang in form.languages.data],
            is_absent=bool(form.is_absent.data),
        )
        db.session.add(teacher)
        _ensure_teacher_portal_credentials(teacher)
        try:
            db.session.flush()
            log_activity(
                "teacher_registered",
                f"Teacher {teacher.first_name} {teacher.last_name} registered",
                object_type="teacher",
                object_id=teacher.id,
                details={
                    "email": teacher.email,
                    "country": teacher.country,
                    "languages": form.languages.data,
                    "portal_username": teacher.portal_username,
                },
            )
            db.session.commit()
            _send_teacher_confirmation_email(teacher)
            flash("Teacher registered successfully.", "success")
            return redirect(url_for("web.register_teacher"))
        except IntegrityError:
            db.session.rollback()
            flash("This email address is already registered.", "error")

    return render_template("register_teacher.html", form=form, show_absence_toggle=False)


@web_bp.route("/admin")
def admin_dashboard():
    filters = {
        "essay_language": request.args.get("essay_language") or None,
        "alert_level": request.args.get("alert_level") or None,
    }

    metrics, alerts, tables, deadlines = _collect_dashboard_data(filters)
    language_options = [choice[0] for choice in LANGUAGE_CHOICES]
    alert_options = [
        {"value": "", "label": "All"},
        {"value": "warning", "label": "Warnings"},
        {"value": "info", "label": "Info"},
    ]
    stage1_locked = _is_stage_locked(Stage.STAGE_1)
    stage2_locked = _is_stage_locked(Stage.STAGE_2)

    return render_template(
        "admin/dashboard.html",
        metrics=metrics,
        alerts=alerts,
        tables=tables,
        deadlines=deadlines,
        filters=filters,
        language_options=language_options,
        alert_options=alert_options,
        stage_lock_state={
            "stage_1": stage1_locked,
            "stage_2": stage2_locked,
        },
        Stage=Stage,
        last_refreshed=datetime.utcnow(),
        **_quick_message_context(),
    )


@web_bp.route("/admin/grading/lock", methods=["POST"])
def admin_toggle_grading_lock():
    if not _current_admin():
        abort(403)

    stage_value = request.form.get("stage")
    target_state = request.form.get("state")

    try:
        stage = Stage(stage_value)
    except (ValueError, TypeError):
        abort(400)

    if target_state not in {"lock", "unlock"}:
        abort(400)

    desired_lock = target_state == "lock"
    _set_stage_lock(stage, desired_lock)

    log_activity(
        "grading_stage_lock",
        f"Grading lock for {stage.value} set to {desired_lock}",
        object_type="grading",
        details={
            "stage": stage.value,
            "locked": desired_lock,
            "actor": _current_admin(),
        },
    )

    db.session.commit()

    stage_label = STAGE_LABELS.get(stage, stage.value.title())
    flash(f"{stage_label} grading {'locked' if desired_lock else 'unlocked'}.", "success")

    redirect_target = request.form.get("redirect") or request.referrer or url_for("web.admin_dashboard")
    return redirect(redirect_target)





def _collect_dashboard_data(filters: dict | None = None):
    filters = filters or {}
    essay_language_filter = filters.get("essay_language") or None
    alert_level_filter = filters.get("alert_level") or None

    now = datetime.utcnow()

    # Student metrics
    total_students = Student.query.count()
    uploads_complete = Student.query.filter(Student.uploaded_filename.isnot(None)).count()
    uploads_pending = Student.query.filter(
        Student.uploaded_filename.is_(None),
        Student.is_absent.is_(False),
    ).count()
    absent_students = Student.query.filter_by(is_absent=True).count()
    students_without_uploads = (
        Student.query.filter(
            Student.uploaded_filename.is_(None),
            Student.is_absent.is_(False),
        )
        .order_by(Student.created_at.asc())
        .all()
    )

    # Teacher metrics and language map
    teachers = Teacher.query.order_by(Teacher.last_name.asc(), Teacher.first_name.asc()).all()
    teacher_languages: dict[int, set[str]] = {}
    teacher_load: dict[int, dict] = {}
    active_teachers = 0
    absent_teachers = 0
    for teacher in teachers:
        _ensure_language_entries(teacher)
        languages = {entry.language for entry in teacher.language_entries if entry.language}
        teacher_languages[teacher.id] = languages
        teacher_load[teacher.id] = {
            "teacher": teacher,
            "assigned": 0,
            "completed": 0,
            "pending": 0,
            "is_absent": teacher.is_absent,
        }
        if teacher.is_absent:
            absent_teachers += 1
        else:
            active_teachers += 1

    # Group staffing metrics
    groups = (
        ReadingGroup.query.options(
            joinedload(ReadingGroup.members).joinedload(ReadingGroupMember.teacher)
        ).all()
    )
    understaffed_groups = []
    active_teacher_ids = set()
    for group in groups:
        active_members = [
            member
            for member in group.members
            if member.active and member.teacher and not member.teacher.is_absent
        ]
        for member in active_members:
            active_teacher_ids.add(member.teacher_id)
        if len(active_members) < 4:
            understaffed_groups.append(
                {
                    "group": group,
                    "active_count": len(active_members),
                    "language": group.language,
                }
            )

    # Stage metrics
    stage1_assignments = (
        EssayAssignment.query.options(
            joinedload(EssayAssignment.scores),
            joinedload(EssayAssignment.student),
            joinedload(EssayAssignment.group)
            .joinedload(ReadingGroup.members)
            .joinedload(ReadingGroupMember.teacher),
        )
        .filter(EssayAssignment.stage == Stage.STAGE_1)
        .all()
    )

    stage1_total = len(stage1_assignments)
    stage1_completed = 0
    stage1_pending_count = 0
    stage1_expected_scores = 0
    stage1_entered_scores = 0
    tie_break_needed = 0
    stage1_pending_list = []

    stage2_candidates = []
    stage2_completed = 0
    stage2_pending_count = 0
    stage2_expected_scores = 0
    stage2_entered_scores = 0
    stage2_pending_list = []
    stage3_recommended = 0

    for assignment in stage1_assignments:
        status = _compute_stage_one_status(assignment)
        expected = status.expected_scores or 0
        entered = status.entered_scores or 0
        stage1_expected_scores += expected
        stage1_entered_scores += entered
        if status.completed:
            stage1_completed += 1
        else:
            stage1_pending_count += 1
            stage1_pending_list.append(
                {
                    "assignment": assignment,
                    "student": assignment.student,
                    "missing": max(expected - entered, 0),
                }
            )
        if status.needs_extra or assignment.needs_additional_reading:
            tie_break_needed += 1

        stage1_scores_map = {
            score.teacher_id: score
            for score in assignment.scores
            if score.stage == Stage.STAGE_1 and score.score is not None
        }
        for assessor in _stage_assessors(assignment, Stage.STAGE_1, include_group=True):
            teacher = assessor.teacher
            info = teacher_load.get(teacher.id)
            if not info:
                continue
            info["assigned"] += 1
            if stage1_scores_map.get(teacher.id):
                info["completed"] += 1

        if assignment.stage_two_candidate:
            stage2_candidates.append(assignment)
            stage2_status = _compute_stage_two_status(assignment)
            expected2 = stage2_status.expected_scores or 0
            entered2 = stage2_status.entered_scores or 0
            stage2_expected_scores += expected2
            stage2_entered_scores += entered2
            if expected2 > 0 and entered2 >= expected2:
                stage2_completed += 1
            else:
                stage2_pending_count += 1
                stage2_pending_list.append(
                    {
                        "assignment": assignment,
                        "student": assignment.student,
                        "missing": max(expected2 - entered2, 0),
                    }
                )
        if assignment.stage_three_recommended:
            stage3_recommended += 1

    for info in teacher_load.values():
        info["pending"] = max(info["assigned"] - info["completed"], 0)

    teacher_workload = [
        info
        for info in teacher_load.values()
        if info["assigned"] > 0 and not info["is_absent"]
    ]
    teacher_workload.sort(key=lambda entry: (entry["pending"], entry["assigned"]), reverse=True)
    teacher_workload = teacher_workload[:8]

    teacher_pending_count = sum(1 for info in teacher_load.values() if info["pending"] > 0 and not info["is_absent"])

    stage1_completion_rate = (stage1_completed / stage1_total * 100) if stage1_total else 100
    stage1_score_rate = (stage1_entered_scores / stage1_expected_scores * 100) if stage1_expected_scores else 100
    stage2_completion_rate = (stage2_completed / len(stage2_candidates) * 100) if stage2_candidates else 100
    stage2_score_rate = (stage2_entered_scores / stage2_expected_scores * 100) if stage2_expected_scores else 100

    metrics = {
        "students": {
            "total": total_students,
            "uploads_pending": uploads_pending,
            "uploads_complete": uploads_complete,
            "absent": absent_students,
        },
        "teachers": {
            "active": active_teachers,
            "absent": absent_teachers,
            "pending_scores": teacher_pending_count,
        },
        "groups": {
            "total": len(groups),
            "understaffed": len(understaffed_groups),
        },
        "stage": {
            "stage1": {
                "total": stage1_total,
                "completed": stage1_completed,
                "pending": stage1_pending_count,
                "expected_scores": stage1_expected_scores,
                "entered_scores": stage1_entered_scores,
                "tie_break": tie_break_needed,
                "completion_rate": stage1_completion_rate,
                "score_rate": stage1_score_rate,
            },
            "stage2": {
                "candidates": len(stage2_candidates),
                "completed": stage2_completed,
                "pending": stage2_pending_count,
                "expected_scores": stage2_expected_scores,
                "entered_scores": stage2_entered_scores,
                "completion_rate": stage2_completion_rate,
                "score_rate": stage2_score_rate,
            },
            "stage3": {
                "recommended": stage3_recommended,
            },
        },
    }

    alerts = []
    if uploads_pending:
        alerts.append(
            {
                "message": f"{uploads_pending} students have not uploaded their essays.",
                "level": "warning",
                "link": url_for("web.admin_students"),
            }
        )
    if len(understaffed_groups):
        alerts.append(
            {
                "message": f"{len(understaffed_groups)} reading group(s) have fewer than four active teachers.",
                "level": "warning",
                "link": url_for("web.admin_planner"),
            }
        )
    if stage1_pending_count:
        alerts.append(
            {
                "message": f"{stage1_pending_count} Stage 1 essay(s) still need scores.",
                "level": "warning",
                "link": url_for("web.admin_uploads"),
            }
        )
    if stage2_pending_count:
        alerts.append(
            {
                "message": f"{stage2_pending_count} Stage 2 essay(s) awaiting assessment.",
                "level": "info",
                "link": url_for("web.admin_stage2_overview"),
            }
        )
    if teacher_pending_count:
        alerts.append(
            {
                "message": f"{teacher_pending_count} teacher(s) still need to submit scores.",
                "level": "info",
                "link": url_for("web.admin_teachers"),
            }
        )

    if essay_language_filter:
        students_filtered = [
            student
            for student in students_without_uploads
            if student.essay_language == essay_language_filter
        ]
        stage1_filtered = [
            item
            for item in stage1_pending_list
            if item["student"] and item["student"].essay_language == essay_language_filter
        ]
    else:
        students_filtered = students_without_uploads
        stage1_filtered = stage1_pending_list

    if alert_level_filter:
        alerts_filtered = [alert for alert in alerts if alert["level"] == alert_level_filter]
    else:
        alerts_filtered = alerts

    tables = {
        "teacher_workload": teacher_workload,
        "students_without_uploads": students_filtered[:10],
        "stage1_pending": stage1_filtered[:8],
    }

    alerts = alerts_filtered

    deadlines = _collect_dashboard_deadlines(now)

    return metrics, alerts, tables, deadlines


def _get_setting(key: str, default: str | None = None) -> str | None:
    setting = AppSetting.query.filter_by(key=key).first()
    if setting and setting.value is not None:
        return setting.value
    return default


def _set_setting(key: str, value: str | None) -> None:
    setting = AppSetting.query.filter_by(key=key).first()
    if setting:
        setting.value = value
    else:
        setting = AppSetting(key=key, value=value)
        db.session.add(setting)


def _parse_bool(raw: str | None) -> bool:
    if raw is None:
        return False
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _stage_lock_key(stage: Stage) -> str:
    return SETTING_STAGE1_LOCK if stage == Stage.STAGE_1 else SETTING_STAGE2_LOCK


def _is_stage_locked(stage: Stage) -> bool:
    return _parse_bool(_get_setting(_stage_lock_key(stage), "false"))


def _set_stage_lock(stage: Stage, locked: bool) -> None:
    _set_setting(_stage_lock_key(stage), "true" if locked else "false")


def _collect_dashboard_deadlines(now: datetime) -> list[dict]:
    config = current_app.config
    deadlines: list[dict] = []

    upload_raw = _get_setting(SETTING_UPLOAD_DEADLINE, config.get("DASHBOARD_UPLOAD_DEADLINE"))
    stage2_raw = _get_setting(SETTING_STAGE2_DEADLINE, config.get("DASHBOARD_STAGE2_DEADLINE"))

    upload_deadline = _parse_deadline(upload_raw)
    stage2_deadline = _parse_deadline(stage2_raw)

    for label, deadline in (("Essay upload deadline", upload_deadline), ("Stage 2 deadline", stage2_deadline)):
        if deadline is None:
            deadlines.append({
                "label": label,
                "value": None,
                "display": "Not configured",
                "status": "info",
                "time_remaining": None,
            })
        else:
            delta = deadline - now
            deadlines.append({
                "label": label,
                "value": deadline,
                "display": deadline.strftime("%Y-%m-%d %H:%M UTC"),
                "status": "warning" if delta.total_seconds() < 0 else "info",
                "time_remaining": _humanize_timedelta(delta),
            })

    stage1_sla = _get_setting(SETTING_STAGE1_SLA, str(config.get("DASHBOARD_STAGE1_SCORE_SLA_HOURS", 24)))
    stage2_sla = _get_setting(SETTING_STAGE2_SLA, str(config.get("DASHBOARD_STAGE2_SCORE_SLA_HOURS", 24)))

    deadlines.append({
        "label": "Stage 1 score SLA",
        "value": None,
        "display": f"{stage1_sla} hours",
        "status": "info",
        "time_remaining": None,
    })
    deadlines.append({
        "label": "Stage 2 score SLA",
        "value": None,
        "display": f"{stage2_sla} hours",
        "status": "info",
        "time_remaining": None,
    })

    return deadlines


def _parse_deadline(raw: str | None) -> datetime | None:
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw)
    except ValueError:
        return None


def _humanize_timedelta(delta: timedelta) -> str:
    seconds = int(delta.total_seconds())
    prefix = 'Due in ' if seconds >= 0 else 'Overdue by '
    seconds = abs(seconds)
    days, remainder = divmod(seconds, 86400)
    hours, remainder = divmod(remainder, 3600)
    minutes, _ = divmod(remainder, 60)
    parts = []
    if days:
        parts.append(f"{days}d")
    if hours:
        parts.append(f"{hours}h")
    if minutes and not days:
        parts.append(f"{minutes}m")
    if not parts:
        parts.append('moments')
    return prefix + ' '.join(parts)


@web_bp.route("/admin/settings", methods=["GET", "POST"])
def admin_settings():
    form = DashboardSettingsForm()
    config = current_app.config

    if form.validate_on_submit():
        upload_value = form.upload_deadline.data.strftime("%Y-%m-%dT%H:%M") if form.upload_deadline.data else None
        stage2_value = form.stage2_deadline.data.strftime("%Y-%m-%dT%H:%M") if form.stage2_deadline.data else None
        stage1_sla_value = str(form.stage1_sla.data) if form.stage1_sla.data else None
        stage2_sla_value = str(form.stage2_sla.data) if form.stage2_sla.data else None

        _set_setting(SETTING_UPLOAD_DEADLINE, upload_value)
        _set_setting(SETTING_STAGE2_DEADLINE, stage2_value)
        _set_setting(SETTING_STAGE1_SLA, stage1_sla_value)
        _set_setting(SETTING_STAGE2_SLA, stage2_sla_value)
        _set_setting(SETTING_PACKET_PRINT_MODE, form.packet_print_mode.data)
        _set_setting(SETTING_TEACHER_PORTAL_ENABLED, "true" if form.teacher_portal_enabled.data else "false")
        _set_setting(SETTING_EMAIL_AUTOMATION_ENABLED, "true" if form.email_auto_enabled.data else "false")
        _set_setting(SETTING_EMAIL_STUDENT_SUBJECT, form.email_student_subject.data.strip() or None)
        _set_setting(SETTING_EMAIL_STUDENT_BODY, form.email_student_body.data.strip() or None)
        _set_setting(SETTING_EMAIL_TEACHER_SUBJECT, form.email_teacher_subject.data.strip() or None)
        _set_setting(SETTING_EMAIL_TEACHER_BODY, form.email_teacher_body.data.strip() or None)
        _set_setting(SETTING_EMAIL_MESSAGE_SUBJECT, form.email_message_subject.data.strip() or None)
        _set_setting(SETTING_EMAIL_MESSAGE_BODY, form.email_message_body.data.strip() or None)
        db.session.commit()
        flash("Dashboard settings updated.", "success")
        return redirect(url_for("web.admin_settings"))

    else:
        upload_raw = _get_setting(SETTING_UPLOAD_DEADLINE, config.get("DASHBOARD_UPLOAD_DEADLINE"))
        stage2_raw = _get_setting(SETTING_STAGE2_DEADLINE, config.get("DASHBOARD_STAGE2_DEADLINE"))
        stage1_sla_raw = _get_setting(SETTING_STAGE1_SLA, str(config.get("DASHBOARD_STAGE1_SCORE_SLA_HOURS", 24)))
        stage2_sla_raw = _get_setting(SETTING_STAGE2_SLA, str(config.get("DASHBOARD_STAGE2_SCORE_SLA_HOURS", 24)))

        if upload_raw:
            dt = _parse_deadline(upload_raw)
            if dt:
                form.upload_deadline.data = dt
        if stage2_raw:
            dt = _parse_deadline(stage2_raw)
            if dt:
                form.stage2_deadline.data = dt
        if stage1_sla_raw:
            try:
                form.stage1_sla.data = int(float(stage1_sla_raw))
            except ValueError:
                form.stage1_sla.data = None
        if stage2_sla_raw:
            try:
                form.stage2_sla.data = int(float(stage2_sla_raw))
            except ValueError:
                form.stage2_sla.data = None

        packet_mode = _get_setting(SETTING_PACKET_PRINT_MODE, "single")
        if packet_mode in {"single", "double"}:
            form.packet_print_mode.data = packet_mode
        else:
            form.packet_print_mode.data = "single"

        teacher_portal_flag = (_get_setting(SETTING_TEACHER_PORTAL_ENABLED, "false") or "false").lower() == "true"
        form.teacher_portal_enabled.data = teacher_portal_flag
        email_enabled_flag = (_get_setting(SETTING_EMAIL_AUTOMATION_ENABLED, "false") or "false").lower() == "true"
        form.email_auto_enabled.data = email_enabled_flag
        form.email_student_subject.data = _get_setting(SETTING_EMAIL_STUDENT_SUBJECT) or DEFAULT_EMAIL_SUBJECTS[SETTING_EMAIL_STUDENT_SUBJECT]
        form.email_student_body.data = _get_setting(SETTING_EMAIL_STUDENT_BODY) or DEFAULT_EMAIL_BODIES[SETTING_EMAIL_STUDENT_BODY]
        form.email_teacher_subject.data = _get_setting(SETTING_EMAIL_TEACHER_SUBJECT) or DEFAULT_EMAIL_SUBJECTS[SETTING_EMAIL_TEACHER_SUBJECT]
        form.email_teacher_body.data = _get_setting(SETTING_EMAIL_TEACHER_BODY) or DEFAULT_EMAIL_BODIES[SETTING_EMAIL_TEACHER_BODY]
        form.email_message_subject.data = _get_setting(SETTING_EMAIL_MESSAGE_SUBJECT) or DEFAULT_EMAIL_SUBJECTS[SETTING_EMAIL_MESSAGE_SUBJECT]
        form.email_message_body.data = _get_setting(SETTING_EMAIL_MESSAGE_BODY) or DEFAULT_EMAIL_BODIES[SETTING_EMAIL_MESSAGE_BODY]

    return render_template("admin/settings.html", form=form, config=config)


@web_bp.route("/admin/exports")
def admin_exports():
    if not _current_admin():
        abort(403)

    database_url = _get_database_url() or ""
    database_available = database_url.startswith("sqlite") or "mysql" in database_url
    return render_template(
        "admin/exports.html",
        database_available=database_available,
        teacher_portal_enabled=_teacher_portal_enabled(),
    )


@web_bp.route("/admin/exports/database", methods=["POST"])
def admin_export_database():
    if not _current_admin():
        abort(403)
    result = _export_database()
    if not result:
        flash("Database export is not available for the current configuration.", "error")
        return redirect(url_for("web.admin_exports"))
    path, filename = result
    log_activity("database_exported", f"Database export {filename} generated", object_type="backup", object_id=filename)
    return send_file(path, as_attachment=True, download_name=filename, mimetype="application/sql")


@web_bp.route("/admin/exports/essays", methods=["POST"])
def admin_export_essays():
    if not _current_admin():
        abort(403)
    only_finalized = request.form.get("finalized_only") == "1"
    result = _zip_essays(only_finalized=only_finalized)
    if not result:
        flash("No essays available to export.", "warning")
        return redirect(url_for("web.admin_exports"))
    zip_buffer, filename = result
    log_activity(
        "essays_exported",
        f"Essay archive {filename} generated",
        object_type="essay_export",
        details={"finalized_only": only_finalized},
    )
    return send_file(zip_buffer, as_attachment=True, download_name=filename, mimetype="application/zip")


@web_bp.route("/admin/help")
def admin_help():
    if not _current_admin():
        abort(403)
    return render_template("admin/help.html")


@web_bp.route("/admin/messages/quick", methods=["POST"])
def admin_message_quick():
    if not _current_admin():
        abort(403)

    form = QuickTeacherMessageForm()
    if form.validate_on_submit():
        try:
            teacher_id = int(form.teacher_id.data)
        except (TypeError, ValueError):
            flash("Invalid teacher selected.", "error")
            return redirect(request.referrer or url_for("web.admin_messages"))

        teacher = db.session.get(Teacher, teacher_id)
        if not teacher:
            flash("Teacher could not be found.", "error")
            return redirect(request.referrer or url_for("web.admin_messages"))

        try:
            priority = TeacherMessagePriority(form.priority.data)
        except ValueError:
            flash("Unknown priority selected.", "error")
            return redirect(request.referrer or url_for("web.admin_messages"))

        message = TeacherMessage(
            title=form.title.data.strip(),
            body=form.body.data.strip(),
            priority=priority,
            status=TeacherMessageStatus.ACTIVE,
            deliver_to_all=False,
            teacher_id=teacher.id,
            category=form.category.data.strip() or None,
            creator_id=_current_admin(),
        )
        db.session.add(message)
        db.session.flush()
        log_activity(
            "teacher_message_created",
            f"Message '{message.title}' created via quick compose",
            object_type="teacher_message",
            object_id=message.id,
            details={
                "priority": message.priority.value,
                "teacher_id": teacher.id,
                "deliver_to_all": False,
                "origin": request.referrer or request.path,
            },
        )
        db.session.commit()
        _send_teacher_message_notifications(message)
        flash(f"Message sent to {teacher.first_name} {teacher.last_name}.", "success")
    else:
        for field_errors in form.errors.values():
            for error in field_errors:
                flash(error, "error")

    return redirect(request.referrer or url_for("web.admin_messages"))


@web_bp.route("/admin/messages", methods=["GET", "POST"])
def admin_messages():
    if not _current_admin():
        abort(403)

    form = TeacherMessageForm()
    _prepare_message_form(form)

    templates = TeacherMessageTemplate.query.order_by(TeacherMessageTemplate.name.asc()).all()
    selected_template_id = request.args.get("template", type=int)
    selected_template = None
    if request.method == "GET" and selected_template_id:
        selected_template = next((tpl for tpl in templates if tpl.id == selected_template_id), None)
        if selected_template:
            form.title.data = selected_template.title
            form.body.data = selected_template.body
            form.category.data = selected_template.category or ""

    if form.validate_on_submit():
        deliver_to_all = form.teacher_id.data == 0
        teacher_id = None if deliver_to_all else form.teacher_id.data

        message = TeacherMessage(
            title=form.title.data.strip(),
            body=form.body.data.strip(),
            priority=TeacherMessagePriority(form.priority.data),
            status=TeacherMessageStatus.ACTIVE,
            deliver_to_all=deliver_to_all,
            teacher_id=teacher_id,
            category=(form.category.data.strip() or None),
            creator_id=_current_admin(),
        )
        db.session.add(message)
        db.session.flush()
        log_activity(
            "teacher_message_created",
            f"Message '{message.title}' created",
            object_type="teacher_message",
            object_id=message.id,
            details={
                "priority": message.priority.value,
                "teacher_id": teacher_id,
                "deliver_to_all": deliver_to_all,
                "origin": request.referrer or request.path,
            },
        )
        db.session.commit()
        _send_teacher_message_notifications(message)
        flash("Message posted.", "success")
        return redirect(url_for("web.admin_messages"))

    messages = (
        TeacherMessage.query.order_by(TeacherMessage.created_at.desc())
        .all()
    )

    return render_template(
        "admin/messages.html",
        form=form,
        templates=templates,
        selected_template_id=selected_template.id if selected_template else None,
        messages=messages,
        priorities=list(TeacherMessagePriority),
        statuses=list(TeacherMessageStatus),
        TeacherMessageStatus=TeacherMessageStatus,
    )


@web_bp.route("/admin/message-templates")
def admin_message_templates():
    if not _current_admin():
        abort(403)

    templates = (
        TeacherMessageTemplate.query.order_by(TeacherMessageTemplate.name.asc()).all()
    )
    return render_template(
        "admin/message_templates.html",
        templates=templates,
    )


@web_bp.route("/admin/message-templates/new", methods=["GET", "POST"])
def admin_message_template_new():
    if not _current_admin():
        abort(403)

    form = TeacherMessageTemplateForm()
    if form.validate_on_submit():
        template = TeacherMessageTemplate(
            name=form.name.data.strip(),
            title=form.title.data.strip(),
            body=form.body.data.strip(),
            category=form.category.data.strip() or None,
        )
        db.session.add(template)
        try:
            db.session.flush()
        except IntegrityError:
            db.session.rollback()
            form.name.errors.append("A template with this name already exists.")
        else:
            log_activity(
                "teacher_message_template_created",
                f"Template '{template.name}' created",
                object_type="teacher_message_template",
                object_id=template.id,
            )
            db.session.commit()
            flash("Template created.", "success")
            return redirect(url_for("web.admin_message_templates"))
    return render_template(
        "admin/message_template_form.html",
        form=form,
        template=None,
    )


@web_bp.route("/admin/message-templates/<int:template_id>/edit", methods=["GET", "POST"])
def admin_message_template_edit(template_id: int):
    if not _current_admin():
        abort(403)

    template = db.session.get(TeacherMessageTemplate, template_id)
    if not template:
        abort(404)

    form = TeacherMessageTemplateForm(obj=template)

    if form.validate_on_submit():
        template.name = form.name.data.strip()
        template.title = form.title.data.strip()
        template.body = form.body.data.strip()
        template.category = form.category.data.strip() or None
        try:
            db.session.flush()
        except IntegrityError:
            db.session.rollback()
            form.name.errors.append("A template with this name already exists.")
        else:
            log_activity(
                "teacher_message_template_updated",
                f"Template '{template.name}' updated",
                object_type="teacher_message_template",
                object_id=template.id,
            )
            db.session.commit()
            flash("Template updated.", "success")
            return redirect(url_for("web.admin_message_templates"))

    return render_template(
        "admin/message_template_form.html",
        form=form,
        template=template,
    )


@web_bp.route("/admin/message-templates/<int:template_id>/delete", methods=["POST"])
def admin_message_template_delete(template_id: int):
    if not _current_admin():
        abort(403)

    template = db.session.get(TeacherMessageTemplate, template_id)
    if not template:
        abort(404)

    db.session.delete(template)
    log_activity(
        "teacher_message_template_deleted",
        f"Template '{template.name}' deleted",
        object_type="teacher_message_template",
        object_id=template.id,
    )
    db.session.commit()
    flash("Template deleted.", "success")
    return redirect(url_for("web.admin_message_templates"))


@web_bp.route("/admin/messages/<int:message_id>/edit", methods=["GET", "POST"])
def admin_message_edit(message_id: int):
    if not _current_admin():
        abort(403)

    message = db.session.get(TeacherMessage, message_id)
    if not message:
        abort(404)

    form = TeacherMessageForm(obj=message)
    _prepare_message_form(form, message.teacher_id or 0)
    form.priority.data = message.priority.value

    if form.validate_on_submit():
        deliver_to_all = form.teacher_id.data == 0
        teacher_id = None if deliver_to_all else form.teacher_id.data

        message.title = form.title.data.strip()
        message.body = form.body.data.strip()
        message.priority = TeacherMessagePriority(form.priority.data)
        message.deliver_to_all = deliver_to_all
        message.teacher_id = teacher_id
        message.category = form.category.data.strip() or None
        message.updater_id = _current_admin()
        db.session.flush()
        log_activity(
            "teacher_message_updated",
            f"Message '{message.title}' updated",
            object_type="teacher_message",
            object_id=message.id,
            details={
                "teacher_id": teacher_id,
                "deliver_to_all": deliver_to_all,
            },
        )
        db.session.commit()
        flash("Message updated.", "success")
        return redirect(url_for("web.admin_messages"))

    return render_template(
        "admin/messages_edit.html",
        form=form,
        message=message,
    )


@web_bp.route("/admin/messages/<int:message_id>/archive", methods=["POST"])
def admin_message_archive(message_id: int):
    if not _current_admin():
        abort(403)
    message = db.session.get(TeacherMessage, message_id)
    if not message:
        abort(404)
    message.status = TeacherMessageStatus.ARCHIVED
    message.updater_id = _current_admin()
    db.session.flush()
    log_activity(
        "teacher_message_archived",
        f"Message '{message.title}' archived",
        object_type="teacher_message",
        object_id=message.id,
        details={"status": message.status.value},
    )
    db.session.commit()
    flash("Message archived.", "success")
    return redirect(url_for("web.admin_messages"))


@web_bp.route("/admin/messages/<int:message_id>/restore", methods=["POST"])
def admin_message_restore(message_id: int):
    if not _current_admin():
        abort(403)
    message = db.session.get(TeacherMessage, message_id)
    if not message:
        abort(404)
    message.status = TeacherMessageStatus.ACTIVE
    message.updater_id = _current_admin()
    db.session.flush()
    log_activity(
        "teacher_message_restored",
        f"Message '{message.title}' restored",
        object_type="teacher_message",
        object_id=message.id,
        details={"status": message.status.value},
    )
    db.session.commit()
    flash("Message restored.", "success")
    return redirect(url_for("web.admin_messages"))


@web_bp.route("/admin/messages/<int:message_id>/delete", methods=["POST"])
def admin_message_delete(message_id: int):
    if not _current_admin():
        abort(403)
    message = db.session.get(TeacherMessage, message_id)
    if not message:
        abort(404)
    db.session.delete(message)
    db.session.flush()
    log_activity(
        "teacher_message_deleted",
        f"Message '{message.title}' deleted",
        object_type="teacher_message",
        object_id=message.id,
    )
    db.session.commit()
    flash("Message deleted.", "success")
    return redirect(url_for("web.admin_messages"))


@web_bp.route("/admin/logs")
def admin_logs():
    if not _current_admin():
        abort(403)

    raw_filters = _log_filters_from_request()
    filters = raw_filters.copy()
    filters["page"] = max(filters["page"], 1)
    query = _filtered_activity_logs(filters).order_by(ActivityLog.created_at.desc())
    pagination = query.paginate(page=filters["page"], per_page=LOG_PAGE_SIZE, error_out=False)

    actions = [row[0] for row in db.session.query(ActivityLog.action).distinct().order_by(ActivityLog.action.asc())]
    object_types = [row[0] for row in db.session.query(ActivityLog.object_type).filter(ActivityLog.object_type.isnot(None)).distinct().order_by(ActivityLog.object_type.asc())]

    filters_display = raw_filters.copy()
    filters_display["start"] = filters["start"].isoformat(timespec="seconds") if filters.get("start") else ""
    filters_display["end"] = filters["end"].isoformat(timespec="seconds") if filters.get("end") else ""

    query_args = request.args.to_dict()
    base_args = {key: value for key, value in query_args.items() if key != "page"}
    prev_url = url_for("web.admin_logs", **base_args, page=pagination.prev_num) if pagination.has_prev else None
    next_url = url_for("web.admin_logs", **base_args, page=pagination.next_num) if pagination.has_next else None
    export_url = url_for("web.admin_logs_export", **query_args)

    return render_template(
        "admin/logs.html",
        logs=pagination.items,
        pagination=pagination,
        filters=filters_display,
        actions=actions,
        object_types=object_types,
        prev_url=prev_url,
        next_url=next_url,
        export_url=export_url,
    )


@web_bp.route("/admin/logs/export")
def admin_logs_export():
    if not _current_admin():
        abort(403)

    filters = _log_filters_from_request()
    query = _filtered_activity_logs(filters).order_by(ActivityLog.created_at.desc())
    limit = current_app.config.get("LOG_EXPORT_LIMIT", 5000)
    logs = query.limit(limit).all()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["timestamp", "actor", "action", "object_type", "object_id", "description", "details"])
    for entry in logs:
        writer.writerow([
            entry.created_at.isoformat(timespec="seconds") if entry.created_at else "",
            entry.actor,
            entry.action,
            entry.object_type or "",
            entry.object_id or "",
            entry.description or "",
            json.dumps(entry.details, ensure_ascii=False, indent=2) if entry.details else "",
        ])

    response = make_response(output.getvalue())
    response.headers["Content-Type"] = "text/csv; charset=utf-8"
    response.headers["Content-Disposition"] = "attachment; filename=activity-logs.csv"
    return response


@web_bp.route("/board/login", methods=["GET", "POST"])
def teacher_board_login():
    if _current_admin():
        return redirect(url_for("web.teacher_board"))

    portal_teacher = _teacher_portal_from_session()
    if _teacher_portal_enabled() and portal_teacher:
        return redirect(url_for("web.teacher_board"))

    form = TeacherBoardLoginForm()
    password_config = current_app.config.get("TEACHER_BOARD_PASSWORD")

    if password_config is None:
        flash("Teacher board password has not been configured.", "error")

    if form.validate_on_submit():
        supplied = form.password.data.strip()
        expected = password_config or ""
        if expected and not secrets.compare_digest(supplied, expected):
            flash("Invalid password.", "error")
            log_activity(
                "teacher_board_login_failed",
                "Teacher board login failed",
                actor="teacher_board",
                details={"remote_addr": request.remote_addr},
            )
            db.session.commit()
        else:
            session["teacher_board"] = True
            flash("Access granted.", "success")
            log_activity(
                "teacher_board_login",
                "Teacher board access granted",
                actor="teacher_board",
                details={"remote_addr": request.remote_addr},
            )
            db.session.commit()
            return redirect(url_for("web.teacher_board"))

    return render_template("teacher_board/login.html", form=form)


@web_bp.route("/board/logout")
def teacher_board_logout():
    session.pop("teacher_board", None)
    flash("Logged out of teacher board.", "success")
    log_activity(
        "teacher_board_logout",
        "Teacher board session ended",
        actor=_current_admin() or "teacher_board",
        details={"remote_addr": request.remote_addr},
    )
    db.session.commit()
    return redirect(url_for("web.teacher_board_login"))


@web_bp.route("/board")
def teacher_board():
    is_admin = bool(_current_admin())
    portal_teacher = _teacher_portal_from_session()
    if not is_admin and not _teacher_board_authorized():
        return redirect(url_for("web.teacher_board_login"))

    priority_param = request.args.get("priority") or ""
    teacher_param = request.args.get("teacher_id", type=int)
    category_param = request.args.get("category") or ""
    search_param = request.args.get("q") or ""

    query = TeacherMessage.query.filter(TeacherMessage.status == TeacherMessageStatus.ACTIVE)

    if portal_teacher and not is_admin:
        query = query.filter(
            or_(
                TeacherMessage.deliver_to_all.is_(True),
                TeacherMessage.teacher_id == portal_teacher.id,
            )
        )
        teacher_param = portal_teacher.id

    if priority_param:
        try:
            query = query.filter(TeacherMessage.priority == TeacherMessagePriority(priority_param))
        except ValueError:
            flash("Unknown priority selected.", "error")

    if teacher_param:
        if teacher_param == 0:
            pass
        else:
            query = query.filter(TeacherMessage.teacher_id == teacher_param)

    if category_param:
        query = query.filter(TeacherMessage.category.ilike(f"%{category_param}%"))

    if search_param:
        query = query.filter(
            or_(
                TeacherMessage.title.ilike(f"%{search_param}%"),
                TeacherMessage.body.ilike(f"%{search_param}%"),
            )
        )

    messages = query.order_by(TeacherMessage.created_at.desc()).all()
    if portal_teacher and not is_admin:
        teachers = [portal_teacher]
    else:
        teachers = Teacher.query.order_by(Teacher.last_name.asc(), Teacher.first_name.asc()).all()

    return render_template(
        "teacher_board/index.html",
        messages=messages,
        teachers=teachers,
        priorities=list(TeacherMessagePriority),
        filters={
            "priority": priority_param,
            "teacher_id": teacher_param or 0,
            "category": category_param,
            "q": search_param,
        },
        is_admin=is_admin,
        portal_teacher=portal_teacher,
    )


@teacher_portal_bp.before_request
def _teacher_portal_guard():
    if _teacher_portal_enabled():
        return None
    flash("Teacher portal is currently disabled. Please contact the organizing team for assistance.", "error")
    return redirect(url_for("web.teacher_board_login"))


@teacher_portal_bp.route("/login", methods=["GET", "POST"])
def login():
    if _teacher_portal_from_session():
        return redirect(url_for("teacher_portal.dashboard"))

    form = TeacherPortalLoginForm()
    next_candidate = request.args.get("next")

    if form.validate_on_submit():
        username = form.username.data.strip()
        password = form.password.data.strip()
        teacher = (
            Teacher.query.filter(
                Teacher.portal_username == username,
                Teacher.is_absent.is_(False),
            )
            .first()
        )
        if not teacher or not teacher.portal_password_hash:
            flash("Invalid credentials.", "error")
            log_activity(
                "teacher_portal_login_failed",
                f"Teacher portal login failed for {username}",
                actor="teacher_portal",
                details={"username": username, "remote_addr": request.remote_addr},
            )
            db.session.commit()
        elif not check_password_hash(teacher.portal_password_hash, password):
            flash("Invalid credentials.", "error")
            log_activity(
                "teacher_portal_login_failed",
                f"Teacher portal login failed for {username}",
                actor="teacher_portal",
                details={"username": username, "remote_addr": request.remote_addr},
            )
            db.session.commit()
        else:
            session["teacher_portal_id"] = teacher.id
            session["teacher_board"] = True
            teacher.portal_last_login = datetime.utcnow()
            log_activity(
                "teacher_portal_login",
                f"Teacher {teacher.first_name} {teacher.last_name} signed in",
                actor=teacher.portal_username or teacher.email,
                object_type="teacher",
                object_id=teacher.id,
            )
            db.session.commit()
            target = _portal_next_url(request.form.get("next") or next_candidate)
            return redirect(target or url_for("teacher_portal.dashboard"))

    return render_template(
        "teacher_portal/login.html",
        form=form,
        next_value=_portal_next_url(next_candidate),
    )


@teacher_portal_bp.route("/logout")
def logout():
    teacher = _teacher_portal_from_session()
    if teacher:
        log_activity(
            "teacher_portal_logout",
            f"Teacher {teacher.first_name} {teacher.last_name} signed out",
            actor=teacher.portal_username or teacher.email,
            object_type="teacher",
            object_id=teacher.id,
        )
        db.session.commit()
    session.pop("teacher_portal_id", None)
    session.pop("teacher_board", None)
    flash("Signed out of teacher portal.", "success")
    return redirect(url_for("teacher_portal.login"))


@teacher_portal_bp.route("/")
def dashboard():
    teacher = _teacher_portal_from_session()
    if not teacher:
        flash("Please sign in to continue.", "error")
        return redirect(url_for("teacher_portal.login", next=request.full_path))

    stage1_entries = _teacher_portal_assignments(teacher, Stage.STAGE_1)
    stage2_entries = _teacher_portal_assignments(teacher, Stage.STAGE_2)

    def _summary(entries: list[SimpleNamespace]) -> SimpleNamespace:
        total = len(entries)
        finalized = sum(1 for entry in entries if entry.status == "finalized")
        in_progress = sum(1 for entry in entries if entry.status == "in_progress")
        awaiting_finalization = sum(1 for entry in entries if entry.status == "awaiting_finalization")
        waiting_upload = sum(1 for entry in entries if entry.status == "waiting_upload")
        pending = sum(1 for entry in entries if entry.status == "pending")
        return SimpleNamespace(
            total=total,
            finalized=finalized,
            awaiting_finalization=awaiting_finalization,
            waiting_upload=waiting_upload,
            in_progress=in_progress,
            pending=pending,
        )

    stage1_summary = _summary(stage1_entries)
    stage2_summary = _summary(stage2_entries)

    messages = (
        TeacherMessage.query.filter(TeacherMessage.status == TeacherMessageStatus.ACTIVE)
        .filter(
            or_(
                TeacherMessage.deliver_to_all.is_(True),
                TeacherMessage.teacher_id == teacher.id,
            )
        )
        .order_by(
            TeacherMessage.priority.desc(),
            TeacherMessage.created_at.desc(),
        )
        .limit(10)
        .all()
    )

    return render_template(
        "teacher_portal/dashboard.html",
        teacher=teacher,
        stage1_entries=stage1_entries,
        stage2_entries=stage2_entries,
        stage1_summary=stage1_summary,
        stage2_summary=stage2_summary,
        messages=messages,
        stage_labels=STAGE_LABELS,
    )


@teacher_portal_bp.route("/assignments/<int:assignment_id>/<stage>", methods=["GET", "POST"])
def assignment_detail(assignment_id: int, stage: str):
    teacher = _teacher_portal_from_session()
    if not teacher:
        flash("Please sign in to continue.", "error")
        return redirect(url_for("teacher_portal.login", next=request.full_path))

    try:
        stage_enum = Stage(stage)
    except ValueError:
        abort(404)

    assignment = (
        EssayAssignment.query.options(
            joinedload(EssayAssignment.student),
            joinedload(EssayAssignment.batch),
            joinedload(EssayAssignment.group).joinedload(ReadingGroup.members).joinedload(ReadingGroupMember.teacher),
            joinedload(EssayAssignment.extra_readers).joinedload(EssayAssignmentExtraReader.teacher),
            joinedload(EssayAssignment.scores),
        )
        .filter_by(id=assignment_id)
        .first_or_404()
    )

    if assignment.batch and assignment.batch.status != PlannerStatus.PUBLISHED:
        abort(404)

    student = assignment.student
    if not student or student.is_absent:
        abort(404)

    if stage_enum == Stage.STAGE_2 and not assignment.stage_two_candidate:
        abort(404)

    assessors = _stage_assessors(assignment, stage_enum, include_group=stage_enum == Stage.STAGE_1)
    if not any(entry.teacher_id == teacher.id for entry in assessors):
        abort(403)

    score_record = next(
        (score for score in assignment.scores if score.teacher_id == teacher.id and score.stage == stage_enum),
        None,
    )

    essay_path = _essay_pdf_path(student)
    pdf_available = essay_path is not None
    stage_global_lock = _is_stage_locked(stage_enum)
    assignment_lock = assignment.stage1_locked if stage_enum == Stage.STAGE_1 else assignment.stage2_locked
    score_lock = bool(score_record.locked_by_admin) if score_record else False
    combined_lock = stage_global_lock or assignment_lock or score_lock
    status_info = _resolve_portal_status(student, score_record, pdf_available, locked=combined_lock)
    essay_available = status_info.code not in {"awaiting_finalization", "waiting_upload"}
    can_edit = essay_available and not combined_lock and (not score_record or not score_record.teacher_finalized)
    download_url = (
        url_for("teacher_portal.download_assignment", assignment_id=assignment.id, stage=stage_enum.value)
        if essay_available
        else None
    )
    group_label = assignment.group.name or str(assignment.group.id) if assignment.group else "—"
    essay_id = student.id
    display_label = f"Essay {essay_id}" if essay_id is not None else f"Assignment {assignment.id}"

    form = TeacherScoreForm()
    if request.method == "GET":
        if score_record and score_record.score is not None:
            form.score.data = score_record.score
        if score_record and score_record.comments:
            form.comments.data = score_record.comments

    if form.validate_on_submit():
        if not can_edit:
            if status_info.code == "awaiting_finalization":
                flash("This essay is waiting for the student to finalize their upload before grading can begin.", "warning")
            elif status_info.code == "waiting_upload":
                flash("The essay file is not yet available for grading.", "warning")
            else:
                flash("Scores for this essay have been finalized. Contact the admin team for changes.", "info")
            return redirect(url_for("teacher_portal.assignment_detail", assignment_id=assignment.id, stage=stage_enum.value))

        finalize_requested = bool(form.finalize.data)
        numeric_score = form.score.data
        if finalize_requested and numeric_score is None:
            form.score.errors.append("Score is required to finalize.")
            finalize_requested = False

        if numeric_score is not None and (numeric_score < 0 or numeric_score > 10):
            form.score.errors.append("Score must be between 0 and 10.")

            if form.errors:
                return render_template(
                    "teacher_portal/assignment_detail.html",
                    form=form,
                    stage=stage_enum,
                    stage_label=STAGE_LABELS[stage_enum],
                    score_record=score_record,
                    essay_available=essay_available,
                    can_edit=can_edit,
                    download_url=download_url,
                    group_label=group_label,
                    display_label=display_label,
                    status_info=status_info,
                    student_finalized=student.essay_finalized,
                    pdf_available=pdf_available,
                    grading_locked=combined_lock,
                    assignment_locked=assignment_lock,
                    global_lock=stage_global_lock,
                    score_lock=score_lock,
                )

        if score_record is None:
            score_record = EssayScore(
                student_id=student.id,
                teacher_id=teacher.id,
                assignment_id=assignment.id,
                stage=stage_enum,
            )
            db.session.add(score_record)

        score_record.score = float(numeric_score) if numeric_score is not None else None
        score_record.comments = (form.comments.data or "").strip() or None
        score_record.submitted_at = datetime.utcnow()
        score_record.admin_entered = False
        score_record.admin_override = False
        score_record.admin_updated_at = None

        if finalize_requested:
            score_record.teacher_finalized = True
            score_record.teacher_finalized_at = datetime.utcnow()
            flash("Score finalized. Thank you!", "success")
            log_activity(
                "teacher_portal_score_finalized",
                f"{teacher.first_name} {teacher.last_name} finalized {stage_enum.value} score",
                actor=teacher.portal_username or teacher.email,
                object_type="essay_assignment",
                object_id=assignment.id,
                details={
                    "stage": stage_enum.value,
                    "student_id": student.id,
                    "score": score_record.score,
                },
            )
        else:
            score_record.teacher_finalized = False
            score_record.teacher_finalized_at = None
            flash("Draft saved.", "success")
            log_activity(
                "teacher_portal_score_saved",
                f"{teacher.first_name} {teacher.last_name} saved {stage_enum.value} score draft",
                actor=teacher.portal_username or teacher.email,
                object_type="essay_assignment",
                object_id=assignment.id,
                details={
                    "stage": stage_enum.value,
                    "student_id": student.id,
                    "score": score_record.score,
                },
            )

        db.session.commit()
        return redirect(url_for("teacher_portal.assignment_detail", assignment_id=assignment.id, stage=stage_enum.value))

    return render_template(
        "teacher_portal/assignment_detail.html",
        form=form,
        stage=stage_enum,
        stage_label=STAGE_LABELS[stage_enum],
        score_record=score_record,
        essay_available=essay_available,
        can_edit=can_edit,
        download_url=download_url,
        group_label=group_label,
        display_label=display_label,
        status_info=status_info,
        student_finalized=student.essay_finalized,
        pdf_available=pdf_available,
        grading_locked=combined_lock,
        assignment_locked=assignment_lock,
        global_lock=stage_global_lock,
        score_lock=score_lock,
    )


@teacher_portal_bp.route("/assignments/<int:assignment_id>/<stage>/download")
def download_assignment(assignment_id: int, stage: str):
    teacher = _teacher_portal_from_session()
    if not teacher:
        flash("Please sign in to continue.", "error")
        return redirect(url_for("teacher_portal.login", next=request.full_path))

    try:
        stage_enum = Stage(stage)
    except ValueError:
        abort(404)

    assignment = (
        EssayAssignment.query.options(
            joinedload(EssayAssignment.student),
            joinedload(EssayAssignment.batch),
            joinedload(EssayAssignment.group).joinedload(ReadingGroup.members),
            joinedload(EssayAssignment.extra_readers),
        )
        .filter_by(id=assignment_id)
        .first_or_404()
    )

    if assignment.batch and assignment.batch.status != PlannerStatus.PUBLISHED:
        abort(404)
    student = assignment.student
    if not student or student.is_absent:
        abort(404)
    if stage_enum == Stage.STAGE_2 and not assignment.stage_two_candidate:
        abort(404)

    assessors = _stage_assessors(assignment, stage_enum, include_group=stage_enum == Stage.STAGE_1)
    if not any(entry.teacher_id == teacher.id for entry in assessors):
        abort(403)

    if not student.essay_finalized:
        flash("This essay is awaiting student finalization and cannot be downloaded yet.", "error")
        return redirect(url_for("teacher_portal.assignment_detail", assignment_id=assignment.id, stage=stage_enum.value))

    pdf_path = _essay_pdf_path(student)
    if not pdf_path:
        flash("Essay file is not yet available.", "error")
        return redirect(url_for("teacher_portal.assignment_detail", assignment_id=assignment.id, stage=stage_enum.value))

    log_activity(
        "teacher_portal_download_essay",
        f"{teacher.first_name} {teacher.last_name} downloaded essay",
        actor=teacher.portal_username or teacher.email,
        object_type="essay_assignment",
        object_id=assignment.id,
        details={"stage": stage_enum.value, "student_id": student.id},
    )
    db.session.commit()

    filename = secure_filename(f"essay-{student.id}-{stage_enum.value}.pdf")
    return send_file(
        pdf_path,
        as_attachment=True,
        download_name=filename,
        mimetype="application/pdf",
    )


@web_bp.route("/admin/students")
def admin_students():
    students = Student.query.order_by(Student.created_at.desc()).all()
    return render_template("admin/students.html", students=students)


@web_bp.route("/admin/teachers")
def admin_teachers():
    teachers = Teacher.query.order_by(Teacher.created_at.desc()).all()
    return render_template(
        "admin/teachers.html",
        teachers=teachers,
        **_quick_message_context(),
    )


@web_bp.route("/admin/students/<int:student_id>/edit", methods=["GET", "POST"])
def edit_student(student_id: int):
    student = db.session.get(Student, student_id)
    if not student:
        abort(404)

    form = StudentRegistrationForm(obj=student)
    form.submit.label.text = "Save changes"

    if form.validate_on_submit():
        student.first_name = form.first_name.data.strip()
        student.last_name = form.last_name.data.strip()
        student.email = form.email.data.lower().strip()
        student.country = form.country.data.strip()
        student.school = form.school.data.strip()
        student.gender = form.gender.data
        student.date_of_birth = form.date_of_birth.data
        student.essay_language = form.essay_language.data
        student.keyboard_preference = form.keyboard_preference.data
        student.meal_preference = form.meal_preference.data
        student.special_needs = (form.special_needs.data.strip() or None) if form.special_needs.data else None
        student.is_absent = bool(form.is_absent.data)
        if not student.upload_username or not student.upload_password_hash:
            _ensure_student_credentials(student)

        try:
            db.session.flush()
            log_activity(
        "student_updated",
        f"Student {student.first_name} {student.last_name} updated",
        object_type="student",
        object_id=student.id,
        details={
            "email": student.email,
            "country": student.country,
            "language": student.essay_language,
            "upload_username": student.upload_username,
        },
    )
            db.session.commit()
            flash("Student details updated successfully.", "success")
            return redirect(url_for("web.admin_students"))
        except IntegrityError:
            db.session.rollback()
            flash("This email address is already registered with another student.", "error")

    return render_template(
        "register_student.html",
        form=form,
        form_title="Edit student",
        show_absence_toggle=True,
    )


@web_bp.route("/admin/teachers/<int:teacher_id>/edit", methods=["GET", "POST"])
def edit_teacher(teacher_id: int):
    teacher = db.session.get(Teacher, teacher_id)
    if not teacher:
        abort(404)

    form = TeacherRegistrationForm(obj=teacher)
    if not form.is_submitted():
        languages = [lang.strip() for lang in teacher.languages.split(",")] if teacher.languages else ["English"]
        form.languages.data = [lang for lang in languages if lang]
    form.submit.label.text = "Save changes"

    if form.validate_on_submit():
        teacher.first_name = form.first_name.data.strip()
        teacher.last_name = form.last_name.data.strip()
        teacher.email = form.email.data.lower().strip()
        teacher.country = form.country.data.strip()
        teacher.school = form.school.data.strip()
        teacher.gender = form.gender.data
        teacher.languages = ", ".join(form.languages.data)

        current_languages = {entry.language for entry in teacher.language_entries}
        desired_languages = set(form.languages.data)

        for entry in list(teacher.language_entries):
            if entry.language not in desired_languages:
                teacher.language_entries.remove(entry)
                db.session.delete(entry)

        for lang in desired_languages - current_languages:
            teacher.language_entries.append(TeacherLanguage(language=lang))
        teacher.meal_preference = form.meal_preference.data
        teacher.tshirt_size = form.tshirt_size.data
        teacher.special_needs = (form.special_needs.data.strip() or None) if form.special_needs.data else None
        teacher.delegation_leader = bool(form.delegation_leader.data)
        teacher.is_absent = bool(form.is_absent.data)

        try:
            db.session.flush()
            log_activity(
                "teacher_updated",
                f"Teacher {teacher.first_name} {teacher.last_name} updated",
                object_type="teacher",
                object_id=teacher.id,
                details={
                    "email": teacher.email,
                    "country": teacher.country,
                    "languages": form.languages.data,
                },
            )
            db.session.commit()
            flash("Teacher details updated successfully.", "success")
            return redirect(url_for("web.admin_teachers"))
        except IntegrityError:
            db.session.rollback()
            flash("This email address is already registered with another teacher.", "error")

    return render_template(
        "register_teacher.html",
        form=form,
        form_title="Edit teacher",
        show_absence_toggle=True,
    )


@web_bp.route("/admin/uploads")
def admin_uploads():
    active_batch = _get_active_batch(Stage.STAGE_1)
    if not active_batch:
        flash("No Stage 1 batch is published; draft assignments are ignored.", "warning")
    students = (
        Student.query.filter_by(is_absent=False)
        .order_by(Student.last_name.asc(), Student.first_name.asc())
        .all()
    )
    status_map = {}
    for student in students:
        assignment = _get_stage_one_assignment(student)
        status_map[student.id] = _compute_stage_one_status(assignment)
    return render_template("admin/uploads.html", students=students, status_map=status_map, active_batch=active_batch)


@web_bp.route("/admin/uploads/<int:student_id>/download")
def admin_download_essay(student_id: int):
    student = db.session.get(Student, student_id)
    if not student or not student.uploaded_filename:
        abort(404)
    upload_folder = _get_upload_folder()
    file_path = upload_folder / student.uploaded_filename
    if not file_path.exists():
        abort(404)
    return send_from_directory(upload_folder, student.uploaded_filename, as_attachment=True)


@web_bp.route("/admin/students/cards.pdf")
def admin_student_cards_pdf():
    active_batch = _get_active_batch(Stage.STAGE_1)
    if not active_batch:
        flash("Publish a Stage 1 batch before generating cards.", "error")
        return redirect(url_for("web.admin_planner"))
    students = (
        Student.query.filter_by(is_absent=False)
        .order_by(Student.country.asc(), Student.last_name.asc())
        .all()
    )
    html = render_template(
        "admin/pdf/student_cards.html",
        students=students,
        current_year=datetime.utcnow().year,
        upload_url=url_for("web.student_login", _external=True),
        event_theme="Essay Competition",
    )
    pdf_bytes = HTML(string=html, base_url=request.url_root).write_pdf()
    response = make_response(pdf_bytes)
    response.headers["Content-Type"] = "application/pdf"
    response.headers["Content-Disposition"] = "attachment; filename=participant-cards.pdf"
    return response


@web_bp.route("/admin/teachers/cards.pdf")
def admin_teacher_cards_pdf():
    if not _current_admin():
        abort(403)
    if not _teacher_portal_enabled():
        flash("Enable teacher portal in Settings before generating teacher cards.", "error")
        return redirect(url_for("web.admin_settings"))

    teachers = (
        Teacher.query.filter_by(is_absent=False)
        .order_by(Teacher.country.asc(), Teacher.last_name.asc())
        .all()
    )
    card_entries: list[dict] = []
    for teacher in teachers:
        username, plain_password = _ensure_teacher_portal_credentials(teacher, reset_password=True)
        if plain_password is None:
            # Ensure a password is available for the card by forcing a reset
            username, plain_password = _ensure_teacher_portal_credentials(teacher, reset_password=True)
        card_entries.append({
            "teacher": teacher,
            "username": username,
            "password": plain_password,
        })

    db.session.commit()

    html = render_template(
        "admin/pdf/teacher_cards.html",
        teachers=card_entries,
        login_url=url_for("teacher_portal.login", _external=True),
        board_url=url_for("web.teacher_board", _external=True),
        current_year=datetime.utcnow().year,
    )
    pdf_bytes = HTML(string=html, base_url=request.url_root).write_pdf()
    response = make_response(pdf_bytes)
    response.headers["Content-Type"] = "application/pdf"
    response.headers["Content-Disposition"] = "attachment; filename=teacher-portal-cards.pdf"
    log_activity(
        "teacher_portal_cards_generated",
        "Teacher portal cards generated",
        object_type="teacher_portal",
    )
    return response


@web_bp.route("/admin/uploads/<int:student_id>/scores", methods=["GET", "POST"])
def admin_score_student(student_id: int):
    student = db.session.get(Student, student_id)
    if not student or student.is_absent:
        abort(404)

    assignment = _get_stage_one_assignment(student)
    if not assignment:
        flash("No published Stage 1 assignment found for this student.", "error")
        return redirect(url_for("web.admin_uploads"))

    assessors = _stage_assessors(assignment, Stage.STAGE_1, include_group=True)
    scores_map = {
        score.teacher_id: score
        for score in assignment.scores
        if score.stage == Stage.STAGE_1
    }

    pdf_available = _essay_pdf_path(student) is not None
    stage1_global_lock = _is_stage_locked(Stage.STAGE_1)
    assignment_stage1_locked = assignment.stage1_locked or stage1_global_lock

    reader_entries = []
    for assessor in assessors:
        teacher = assessor.teacher
        score_record = scores_map.get(teacher.id)
        status_info = _resolve_portal_status(student, score_record, pdf_available, locked=assignment_stage1_locked)
        reader_entries.append(
            SimpleNamespace(
                teacher=teacher,
                teacher_id=teacher.id,
                source=assessor.source,
                is_extra=assessor.is_extra,
                score=score_record.score if score_record else None,
                updated_at=score_record.updated_at if score_record else None,
                finalized=score_record.teacher_finalized if score_record else False,
                finalized_at=score_record.teacher_finalized_at if score_record else None,
                submitted_at=score_record.submitted_at if score_record else None,
                portal_status_code=status_info.code,
                portal_status_label=status_info.label,
                portal_status_css=status_info.css,
                portal_status_timestamp=status_info.timestamp,
            )
        )

    assigned_teacher_ids = {entry.teacher_id for entry in reader_entries}
    stage2_teacher_ids = {assessor.teacher.id for assessor in _stage_assessors(assignment, Stage.STAGE_2, include_group=False)}
    exclude_ids = assigned_teacher_ids.union(stage2_teacher_ids)
    available_query = Teacher.query.filter_by(is_absent=False)
    if exclude_ids:
        available_query = available_query.filter(~Teacher.id.in_(exclude_ids))
    available_teachers = [
        teacher
        for teacher in available_query.order_by(Teacher.last_name.asc(), Teacher.first_name.asc()).all()
        if _teacher_can_grade(student, teacher, student.essay_language)
    ]

    remove_id = request.form.get("remove_reader")
    unlock_id = request.form.get("unlock_reader")
    action = request.form.get("action")

    if request.method == "POST" and action == "toggle_stage1_lock":
        assignment.stage1_locked = not assignment.stage1_locked
        now = datetime.utcnow()
        for score in assignment.scores:
            if score.stage != Stage.STAGE_1:
                continue
            score.locked_by_admin = assignment.stage1_locked
            if assignment.stage1_locked:
                score.admin_updated_at = now
        log_activity(
            "stage1_grading_lock",
            f"Stage 1 grading lock set to {assignment.stage1_locked} for student {student.id}",
            object_type="student",
            object_id=student.id,
            details={"locked": assignment.stage1_locked},
        )
        db.session.commit()
        flash(
            "Stage 1 grading locked." if assignment.stage1_locked else "Stage 1 grading unlocked.",
            "success",
        )
        return redirect(url_for("web.admin_score_student", student_id=student.id))

    if request.method == "POST" and unlock_id:
        try:
            teacher_id = int(unlock_id)
        except ValueError:
            flash("Invalid teacher selection.", "error")
            return redirect(url_for("web.admin_score_student", student_id=student.id))
        score_record = scores_map.get(teacher_id)
        if not score_record or not score_record.teacher_finalized:
            flash("Score is not finalized for this teacher.", "warning")
            return redirect(url_for("web.admin_score_student", student_id=student.id))
        score_record.teacher_finalized = False
        score_record.teacher_finalized_at = None
        score_record.admin_updated_at = datetime.utcnow()
        log_activity(
            "stage1_score_unlocked",
            f"Unlocked Stage 1 score for teacher {teacher_id} on student {student.id}",
            object_type="student",
            object_id=student.id,
            details={"teacher_id": teacher_id},
        )
        db.session.commit()
        flash("Teacher score unlocked for editing.", "success")
        return redirect(url_for("web.admin_score_student", student_id=student.id))

    if request.method == "POST" and remove_id:
        try:
            teacher_id = int(remove_id)
        except ValueError:
            flash("Invalid teacher selection.", "error")
            return redirect(url_for("web.admin_score_student", student_id=student.id))
        extra = EssayAssignmentExtraReader.query.filter_by(assignment_id=assignment.id, teacher_id=teacher_id, stage=Stage.STAGE_1).first()
        if not extra:
            flash("Extra reader not found for this essay.", "error")
            return redirect(url_for("web.admin_score_student", student_id=student.id))
        score_record = scores_map.get(teacher_id)
        if score_record and score_record.stage == Stage.STAGE_1:
            db.session.delete(score_record)
            scores_map.pop(teacher_id, None)
        db.session.delete(extra)
        log_activity(
            "stage1_extra_reader_removed",
            f"Removed extra reader {teacher_id} for student {student.id}",
            object_type="student",
            object_id=student.id,
            details={"teacher_id": teacher_id},
        )
        db.session.commit()
        flash("Extra reader removed.", "success")
        return redirect(url_for("web.admin_score_student", student_id=student.id))

    if request.method == "POST" and action == "add_reader":
        teacher_id = request.form.get("teacher_id")
        if not teacher_id:
            flash("Select a teacher to add.", "error")
            return redirect(url_for("web.admin_score_student", student_id=student.id))
        try:
            teacher_id_int = int(teacher_id)
        except ValueError:
            flash("Invalid teacher selection.", "error")
            return redirect(url_for("web.admin_score_student", student_id=student.id))
        teacher = db.session.get(Teacher, teacher_id_int)
        if not teacher or teacher.is_absent:
            flash("Teacher not available.", "error")
            return redirect(url_for("web.admin_score_student", student_id=student.id))
        if teacher_id_int in assigned_teacher_ids:
            flash("Teacher already assigned.", "warning")
            return redirect(url_for("web.admin_score_student", student_id=student.id))
        if not _teacher_can_grade(student, teacher, student.essay_language):
            flash("Teacher is not eligible to grade this essay.", "error")
            return redirect(url_for("web.admin_score_student", student_id=student.id))
        db.session.add(EssayAssignmentExtraReader(assignment_id=assignment.id, teacher_id=teacher_id_int, stage=Stage.STAGE_1))
        log_activity(
            "stage1_extra_reader_added",
            f"Added extra reader {teacher_id_int} for student {student.id}",
            object_type="student",
            object_id=student.id,
            details={"teacher_id": teacher_id_int},
        )
        db.session.commit()
        flash("Additional reader assigned.", "success")
        return redirect(url_for("web.admin_score_student", student_id=student.id))

    if request.method == "POST" and action == "update_scores":
        updates = {}
        now = datetime.utcnow()
        for entry in reader_entries:
            field_name = f"score_{entry.teacher_id}"
            value = request.form.get(field_name, "").strip()
            if not value:
                continue
            try:
                numeric = float(value)
            except ValueError:
                flash(f"Invalid score for {entry.teacher.first_name} {entry.teacher.last_name}.", "error")
                return redirect(url_for("web.admin_score_student", student_id=student.id))
            if numeric < 0 or numeric > 10:
                flash("Scores must be between 0 and 10.", "error")
                return redirect(url_for("web.admin_score_student", student_id=student.id))
            score_record = scores_map.get(entry.teacher_id)
            if not score_record:
                score_record = EssayScore(
                    student_id=student.id,
                    teacher_id=entry.teacher_id,
                    assignment_id=assignment.id,
                    stage=Stage.STAGE_1,
                )
                db.session.add(score_record)
                scores_map[entry.teacher_id] = score_record
            prev_admin_entered = score_record.admin_entered if score_record else False
            prev_admin_override = score_record.admin_override if score_record else False
            had_teacher_input = bool(score_record.submitted_at) or bool(score_record.teacher_finalized)
            existing_score = score_record.score if score_record and score_record.score is not None else None

            if existing_score is not None and math.isclose(existing_score, numeric, abs_tol=1e-9):
                continue

            score_record.score = numeric
            score_record.admin_updated_at = now
            if had_teacher_input and not prev_admin_override and not prev_admin_entered:
                score_record.admin_override = True
                score_record.admin_entered = False
            elif prev_admin_override:
                score_record.admin_override = True
                score_record.admin_entered = False
            else:
                score_record.admin_entered = True
                score_record.admin_override = False

            score_record.teacher_finalized = False
            score_record.teacher_finalized_at = None
            updates[entry.teacher_id] = numeric
        if not updates:
            flash("No score changes detected.", "info")
            return redirect(url_for("web.admin_score_student", student_id=student.id))

        _apply_stage_one_rules(assignment)
        log_activity(
            "stage1_scores_updated",
            f"Stage 1 scores updated for student {student.id}",
            object_type="student",
            object_id=student.id,
            details={"updates": updates},
        )
        db.session.commit()
        flash("Scores saved.", "success")
        return redirect(url_for("web.admin_score_student", student_id=student.id))

    if request.method == "POST" and action == "mark_stage2":
        assignment.stage_two_candidate = not assignment.stage_two_candidate
        if assignment.stage_two_candidate:
            assignment.needs_additional_reading = False
        log_activity(
            "stage1_mark_stage2",
            f"Stage 2 flag set to {assignment.stage_two_candidate} for student {student.id}",
            object_type="student",
            object_id=student.id,
        )
        db.session.commit()
        return redirect(url_for("web.admin_score_student", student_id=student.id))

    if request.method == "POST" and action == "mark_extra":
        assignment.needs_additional_reading = not assignment.needs_additional_reading
        if assignment.needs_additional_reading:
            assignment.stage_two_candidate = False
        log_activity(
            "stage1_mark_extra",
            f"Extra reading flag set to {assignment.needs_additional_reading} for student {student.id}",
            object_type="student",
            object_id=student.id,
        )
        db.session.commit()
        return redirect(url_for("web.admin_score_student", student_id=student.id))

    status = _compute_stage_one_status(assignment)
    reader_entries = []
    for assessor in _stage_assessors(assignment, Stage.STAGE_1, include_group=True):
        teacher = assessor.teacher
        score_record = scores_map.get(teacher.id)
        status_info = _resolve_portal_status(student, score_record, pdf_available, locked=assignment_stage1_locked)
        reader_entries.append(
            SimpleNamespace(
                teacher=teacher,
                teacher_id=teacher.id,
                source=assessor.source,
                is_extra=assessor.is_extra,
                score=score_record.score if score_record else None,
                updated_at=score_record.updated_at if score_record else None,
                finalized=score_record.teacher_finalized if score_record else False,
                finalized_at=score_record.teacher_finalized_at if score_record else None,
                submitted_at=score_record.submitted_at if score_record else None,
                portal_status_code=status_info.code,
                portal_status_label=status_info.label,
                portal_status_css=status_info.css,
                portal_status_timestamp=status_info.timestamp,
            )
        )

    return render_template(
        "admin/scoring.html",
        student=student,
        assignment=assignment,
        reader_entries=reader_entries,
        status=status,
        available_teachers=available_teachers,
        stage1_global_lock=stage1_global_lock,
        **_quick_message_context(),
    )


@web_bp.route("/admin/planner", methods=["GET", "POST"])
def admin_planner():
    form = AssignmentBatchForm()
    form.stage.data = Stage.STAGE_1.value

    if form.validate_on_submit():
        batch = AssignmentBatch(
            name=form.name.data.strip(),
            stage=Stage(form.stage.data),
            status=PlannerStatus.DRAFT,
            notes=form.notes.data.strip() if form.notes.data else None,
        )
        db.session.add(batch)
        db.session.flush()
        log_activity(
            "batch_created",
            f"Created assignment batch {batch.name}",
            object_type="assignment_batch",
            object_id=batch.id,
            details={"stage": batch.stage.value},
        )
        db.session.commit()
        flash("Assignment batch created.", "success")
        return redirect(url_for("web.admin_planner_batch", batch_id=batch.id))

    batches = AssignmentBatch.query.order_by(AssignmentBatch.created_at.desc()).all()
    active_batch = _get_active_batch(Stage.STAGE_1)
    return render_template(
        "admin/planner/overview.html",
        form=form,
        batches=batches,
        active_batch=active_batch,
        PlannerStatus=PlannerStatus,
    )


@web_bp.route("/admin/planner/batches/<int:batch_id>")
def admin_planner_batch(batch_id: int):
    batch = db.session.get(AssignmentBatch, batch_id)
    if not batch:
        abort(404)

    group_form = ReadingGroupForm()
    if not group_form.target_essay_load.data:
        group_form.target_essay_load.data = 5
    group_form.language.data = group_form.language.data or "English"
    group_form.auto_generated.data = True

    member_form = ReadingGroupMemberForm()
    member_form.teacher_id.choices = _planner_teacher_choices(batch.stage)
    member_form.role.choices = [(role.value, role.name.title()) for role in GroupMemberRole]

    groups = _load_batch_groups(batch)
    assigned_student_ids = {assignment.student_id for group in groups for assignment in group.assignments}
    students_by_language: dict[str, list[Student]] = defaultdict(list)
    for student in Student.query.order_by(Student.essay_language.asc(), Student.country.asc(), Student.last_name.asc()).all():
        if student.id in assigned_student_ids:
            continue
        students_by_language[student.essay_language].append(student)

    eligible_students_map: dict[int, list[Student]] = {}
    for group in groups:
        active_countries = {
            member.teacher.country
            for member in group.members
            if member.active and member.teacher
        }
        candidates = [
            student
            for student in students_by_language.get(group.language, [])
            if group.allow_same_country or student.country not in active_countries
        ]
        eligible_students_map[group.id] = candidates[:100]

    teachers = (
        Teacher.query.filter_by(is_absent=False)
        .order_by(Teacher.last_name.asc(), Teacher.first_name.asc())
        .all()
    )
    teacher_languages_map: dict[int, set[str]] = {}
    for teacher in teachers:
        _ensure_language_entries(teacher)
        teacher_languages_map[teacher.id] = {
            entry.language for entry in teacher.language_entries if entry.language
        }

    active_teacher_ids = {
        member.teacher_id
        for group in groups
        for member in group.members
        if member.active and member.teacher
    }
    available_teachers_map: dict[int, list[Teacher]] = {}
    group_status_map: dict[int, dict[str, int | bool]] = {}

    for group in groups:
        group_teacher_ids = {member.teacher_id for member in group.members if member.teacher}
        active_count = sum(
            1
            for member in group.members
            if member.active and member.teacher and not member.teacher.is_absent
        )
        needs_teachers = active_count < 4
        group_status_map[group.id] = {
            "active_count": active_count,
            "needs_teachers": needs_teachers,
            "missing": max(0, 4 - active_count),
        }

        available_teachers: list[Teacher] = []
        for teacher in teachers:
            if teacher.id in group_teacher_ids:
                continue
            if teacher.id in active_teacher_ids:
                continue
            languages_spoken = teacher_languages_map.get(teacher.id, set())
            if group.language not in languages_spoken:
                continue
            available_teachers.append(teacher)
        available_teachers_map[group.id] = available_teachers

    return render_template(
        "admin/planner/batch_detail.html",
        batch=batch,
        groups=groups,
        group_form=group_form,
        member_form=member_form,
        eligible_students_map=eligible_students_map,
        available_teachers_map=available_teachers_map,
        group_status_map=group_status_map,
        PlannerStatus=PlannerStatus,
        **_quick_message_context(),
    )


@web_bp.route("/admin/planner/batches/<int:batch_id>/groups", methods=["POST"])
def admin_planner_add_group(batch_id: int):
    batch = db.session.get(AssignmentBatch, batch_id)
    if not batch:
        abort(404)

    form = ReadingGroupForm()
    if form.validate_on_submit():
        target = form.target_essay_load.data or 5
        group = ReadingGroup(
            name=form.name.data.strip(),
            language=form.language.data,
            stage=batch.stage,
            target_essay_load=target,
            allow_same_country=bool(form.allow_same_country.data),
            auto_generated=bool(form.auto_generated.data),
            status=batch.status,
            batch=batch,
        )
        db.session.add(group)
        db.session.flush()
        log_activity(
            "group_created",
            f"Group {group.name} created for {group.language}",
            object_type="reading_group",
            object_id=group.id,
            details={"batch_id": batch.id, "language": group.language},
        )
        db.session.commit()
        flash("Reading group created.", "success")
    else:
        for errors in form.errors.values():
            for error in errors:
                flash(error, "error")

    return redirect(url_for("web.admin_planner_batch", batch_id=batch.id))


@web_bp.route("/admin/planner/batches/<int:batch_id>/groups/<int:group_id>/toggle-lock", methods=["POST"])
def admin_planner_toggle_lock(batch_id: int, group_id: int):
    batch = db.session.get(AssignmentBatch, batch_id)
    if not batch:
        abort(404)
    group = ReadingGroup.query.filter_by(id=group_id, batch_id=batch.id).first_or_404()
    group.locked = not group.locked
    log_activity(
        "group_lock_toggled",
        f"Group {group.name} lock set to {group.locked}",
        object_type="reading_group",
        object_id=group.id,
        details={"locked": group.locked},
    )
    db.session.commit()
    flash("Group lock status updated.", "success")
    return redirect(url_for("web.admin_planner_batch", batch_id=batch.id))


@web_bp.route("/admin/planner/batches/<int:batch_id>/groups/<int:group_id>/delete", methods=["POST"])
def admin_planner_delete_group(batch_id: int, group_id: int):
    batch = db.session.get(AssignmentBatch, batch_id)
    if not batch:
        abort(404)
    group = ReadingGroup.query.filter_by(id=group_id, batch_id=batch.id).first_or_404()
    if group.assignments:
        flash("Group cannot be deleted while assignments exist.", "error")
    else:
        group_name = group.name
        db.session.delete(group)
        log_activity(
            "group_deleted",
            f"Group {group_name} deleted",
            object_type="reading_group",
            object_id=group_id,
        )
        db.session.commit()
        flash("Reading group deleted.", "success")
    return redirect(url_for("web.admin_planner_batch", batch_id=batch.id))


@web_bp.route("/admin/planner/batches/<int:batch_id>/members", methods=["POST"])
def admin_planner_add_member(batch_id: int):
    batch = db.session.get(AssignmentBatch, batch_id)
    if not batch:
        abort(404)

    form = ReadingGroupMemberForm()
    form.teacher_id.choices = _planner_teacher_choices(batch.stage)
    form.role.choices = [(role.value, role.name.title()) for role in GroupMemberRole]
    group_id_value = request.form.get("group_id")
    if not group_id_value:
        flash("Group selection is required.", "error")
        return redirect(url_for("web.admin_planner_batch", batch_id=batch.id))

    group = ReadingGroup.query.filter_by(id=int(group_id_value), batch_id=batch.id).first()
    if not group:
        flash("Invalid group selection.", "error")
        return redirect(url_for("web.admin_planner_batch", batch_id=batch.id))

    if form.validate_on_submit():
        teacher_id = form.teacher_id.data
        if _teacher_has_active_group(teacher_id, batch.stage, exclude_group_id=group.id):
            flash("Teacher already assigned to an active group for this stage.", "error")
        else:
            already_member = any(member.teacher_id == teacher_id for member in group.members)
            if already_member:
                flash("Teacher is already part of this group.", "error")
            else:
                member = ReadingGroupMember(
                    group=group,
                    teacher_id=teacher_id,
                    role=GroupMemberRole(form.role.data),
                    active=bool(form.active.data),
                )
                db.session.add(member)
                db.session.flush()
                log_activity(
                    "group_member_added",
                    f"Teacher {member.teacher_id} added to group {group.name}",
                    object_type="reading_group",
                    object_id=group.id,
                    details={
                        "teacher_id": member.teacher_id,
                        "role": member.role.value,
                        "active": member.active,
                    },
                )
                db.session.commit()
                flash("Group member added.", "success")
    else:
        for errors in form.errors.values():
            for error in errors:
                flash(error, "error")

    return redirect(url_for("web.admin_planner_batch", batch_id=batch.id))


@web_bp.route("/admin/planner/batches/<int:batch_id>/members/<int:member_id>/remove", methods=["POST"])
def admin_planner_remove_member(batch_id: int, member_id: int):
    batch = db.session.get(AssignmentBatch, batch_id)
    if not batch:
        abort(404)
    member = (
        ReadingGroupMember.query.join(ReadingGroup)
        .filter(ReadingGroupMember.id == member_id, ReadingGroup.batch_id == batch.id)
        .first_or_404()
    )
    group_name = member.group.name if member.group else str(batch.id)
    teacher_id = member.teacher_id
    db.session.delete(member)
    log_activity(
        "group_member_removed",
        f"Teacher {teacher_id} removed from group {group_name}",
        object_type="reading_group",
        object_id=member.group_id,
        details={"teacher_id": teacher_id},
    )
    db.session.commit()
    flash("Group member removed.", "success")
    return redirect(url_for("web.admin_planner_batch", batch_id=batch.id))


@web_bp.route("/admin/planner/batches/<int:batch_id>/groups/<int:group_id>/assign", methods=["POST"])
def admin_planner_assign_manual(batch_id: int, group_id: int):
    batch = db.session.get(AssignmentBatch, batch_id)
    if not batch:
        abort(404)
    group = ReadingGroup.query.filter_by(id=group_id, batch_id=batch.id).first_or_404()
    if group.locked:
        flash("Group is locked.", "error")
        return redirect(url_for("web.admin_planner_batch", batch_id=batch.id))

    student_id_value = request.form.get("student_id")
    if not student_id_value:
        flash("Student selection is required.", "error")
        return redirect(url_for("web.admin_planner_batch", batch_id=batch.id))

    student = db.session.get(Student, int(student_id_value))
    if not student:
        flash("Selected student does not exist.", "error")
        return redirect(url_for("web.admin_planner_batch", batch_id=batch.id))

    existing_assignment = EssayAssignment.query.filter_by(batch_id=batch.id, student_id=student.id).first()
    if existing_assignment:
        flash("Student already assigned in this batch.", "error")
        return redirect(url_for("web.admin_planner_batch", batch_id=batch.id))

    if student.essay_language != group.language:
        flash("Student language does not match the group language.", "error")
        return redirect(url_for("web.admin_planner_batch", batch_id=batch.id))

    active_countries = {
        member.teacher.country
        for member in group.members
        if member.active and member.teacher and not member.teacher.is_absent
    }
    if not group.allow_same_country and student.country in active_countries:
        flash("Group cannot read students from the same country.", "error")
        return redirect(url_for("web.admin_planner_batch", batch_id=batch.id))

    assignment = EssayAssignment(
        student_id=student.id,
        group_id=group.id,
        batch=batch,
        stage=batch.stage,
        manual_override=True,
        status=PlannerStatus.DRAFT,
    )
    db.session.add(assignment)
    db.session.flush()
    log_activity(
        "assignment_added",
        f"Student {student.first_name} {student.last_name} assigned to {group.name}",
        object_type="essay_assignment",
        object_id=assignment.id,
        details={
            "student_id": student.id,
            "group_id": group.id,
            "batch_id": batch.id,
        },
    )
    db.session.commit()
    flash("Essay assigned to group.", "success")
    return redirect(url_for("web.admin_planner_batch", batch_id=batch.id))


@web_bp.route("/admin/planner/batches/<int:batch_id>/assignments/<int:assignment_id>/remove", methods=["POST"])
def admin_planner_remove_assignment(batch_id: int, assignment_id: int):
    batch = db.session.get(AssignmentBatch, batch_id)
    if not batch:
        abort(404)

    assignment = EssayAssignment.query.filter_by(id=assignment_id, batch_id=batch.id).first_or_404()
    if batch.status == PlannerStatus.PUBLISHED:
        flash("Cannot modify assignments on a published batch.", "error")
        return redirect(url_for("web.admin_planner_batch", batch_id=batch.id))

    db.session.delete(assignment)
    log_activity(
        "assignment_removed",
        f"Assignment {assignment_id} removed from batch {batch.name}",
        object_type="essay_assignment",
        object_id=assignment_id,
        details={"batch_id": batch.id, "group_id": assignment.group_id, "student_id": assignment.student_id},
    )
    db.session.commit()
    flash("Assignment removed.", "success")
    return redirect(url_for("web.admin_planner_batch", batch_id=batch.id))


@web_bp.route("/admin/planner/batches/<int:batch_id>/auto-generate", methods=["POST"])
def admin_planner_auto_generate(batch_id: int):
    batch = db.session.get(AssignmentBatch, batch_id)
    if not batch:
        abort(404)
    summary = _auto_generate_groups_for_batch(batch)
    if "created" in summary:
        created_total = sum(summary["created"].values())
    else:
        created_total = sum(
            count
            for key, count in summary.items()
            if key not in {"removed", "backups", "shortfall", "matching_failed"} and isinstance(count, int)
        )
    log_activity(
        "groups_auto_generated",
        f"Auto-generated groups for batch {batch.name}",
        object_type="assignment_batch",
        object_id=batch.id,
        details=summary,
    )
    db.session.commit()
    removed_count = summary.get("removed", 0)
    backups_count = summary.get("backups", 0)
    message = f"Generated {created_total} groups (removed {removed_count} auto-generated groups)."
    if backups_count:
        message += f" {backups_count} teacher(s) assigned as backups."
    if summary.get("matching_failed"):
        flash("Unable to auto-generate groups for all teachers. Please adjust teacher availability or language coverage.", "error")
    else:
        flash(message, "success")
        if summary.get("shortfall"):
            shortfall_items = ", ".join(f"{language}: {value}" for language, value in summary["shortfall"].items())
            flash(f"Not enough teachers in: {shortfall_items}. Some language coverage targets were reduced.", "warning")
    return redirect(url_for("web.admin_planner_batch", batch_id=batch.id))


@web_bp.route("/admin/planner/batches/<int:batch_id>/auto-assign", methods=["POST"])
def admin_planner_auto_assign(batch_id: int):
    batch = db.session.get(AssignmentBatch, batch_id)
    if not batch:
        abort(404)
    assigned, skipped = _auto_assign_essays(batch)
    metadata = {"assigned": assigned, "skipped": [student.id for student in skipped]}
    log_activity(
        "essays_auto_assigned",
        f"Auto-assigned essays for batch {batch.name}",
        object_type="assignment_batch",
        object_id=batch.id,
        details=metadata,
    )
    db.session.commit()
    if skipped:
        flash(
            f"Assigned {assigned} essays. {len(skipped)} essays need manual attention (no eligible group).",
            "error",
        )
    else:
        flash(f"Assigned {assigned} essays to reading groups.", "success")
    return redirect(url_for("web.admin_planner_batch", batch_id=batch.id))


@web_bp.route("/admin/planner/batches/<int:batch_id>/unpublish", methods=["POST"])
def admin_planner_unpublish(batch_id: int):
    batch = db.session.get(AssignmentBatch, batch_id)
    if not batch:
        abort(404)
    if batch.status != PlannerStatus.PUBLISHED:
        flash("Batch is not published.", "warning")
        return redirect(url_for("web.admin_planner_batch", batch_id=batch.id))

    batch.status = PlannerStatus.DRAFT
    batch.published_at = None

    for group in batch.groups:
        group.status = PlannerStatus.DRAFT
    for assignment in batch.assignments:
        assignment.status = PlannerStatus.DRAFT

    log_activity(
        "batch_unpublished",
        f"Unpublished batch {batch.name}",
        object_type="assignment_batch",
        object_id=batch.id,
        details={"stage": batch.stage.value},
    )
    db.session.commit()
    flash("Batch returned to draft state.", "success")
    return redirect(url_for("web.admin_planner_batch", batch_id=batch.id))


@web_bp.route("/admin/planner/batches/<int:batch_id>/publish", methods=["POST"])
def admin_planner_publish(batch_id: int):
    batch = db.session.get(AssignmentBatch, batch_id)
    if not batch:
        abort(404)

    unresolved_groups = [group for group in batch.groups if len(group.members) < 4]
    if unresolved_groups:
        flash("All groups must have at least four members before publishing.", "error")
        return redirect(url_for("web.admin_planner_batch", batch_id=batch.id))

    now = datetime.utcnow()
    batch.status = PlannerStatus.PUBLISHED
    batch.published_at = now

    other_batches = (
        AssignmentBatch.query.filter(
            AssignmentBatch.id != batch.id,
            AssignmentBatch.stage == batch.stage,
            AssignmentBatch.status == PlannerStatus.PUBLISHED,
        )
        .all()
    )
    for other in other_batches:
        other.status = PlannerStatus.DRAFT
        other.published_at = None

    for group in batch.groups:
        group.status = PlannerStatus.PUBLISHED
    for assignment in batch.assignments:
        assignment.status = PlannerStatus.PUBLISHED

    log_activity(
        "batch_published",
        f"Published assignment batch {batch.name}",
        object_type="assignment_batch",
        object_id=batch.id,
        details={
            "groups": len(batch.groups),
            "assignments": len(batch.assignments),
            "stage": batch.stage.value,
        },
    )
    db.session.commit()
    flash("Assignment batch published.", "success")
    return redirect(url_for("web.admin_planner_batch", batch_id=batch.id))


@web_bp.route("/admin/planner/batches/<int:batch_id>/delete", methods=["POST"])
def admin_planner_delete_batch(batch_id: int):
    batch = db.session.get(AssignmentBatch, batch_id)
    if not batch:
        abort(404)
    if batch.status == PlannerStatus.PUBLISHED:
        flash("Cannot delete a published batch. Unpublish another batch first.", "error")
        return redirect(url_for("web.admin_planner"))
    name = batch.name
    stage = batch.stage.value
    log_activity(
        "batch_deleted",
        f"Deleted batch {name}",
        object_type="assignment_batch",
        object_id=batch_id,
        details={"stage": stage},
    )
    db.session.delete(batch)
    db.session.commit()
    flash("Batch deleted.", "success")
    return redirect(url_for("web.admin_planner"))


@web_bp.route("/admin/planner/batches/<int:batch_id>/export/groups.pdf")
def admin_planner_export_groups_pdf(batch_id: int):
    batch = db.session.get(AssignmentBatch, batch_id)
    if not batch:
        abort(404)
    groups = _load_batch_groups(batch)
    slug = batch.name.lower().replace(" ", "-")
    filename = f"{slug}-groups.pdf"
    return _render_pdf("admin/planner/pdf/group_packet.html", filename, batch=batch, groups=groups)


@web_bp.route("/admin/planner/batches/<int:batch_id>/export/teachers.pdf")
def admin_planner_export_teachers_pdf(batch_id: int):
    batch = db.session.get(AssignmentBatch, batch_id)
    if not batch:
        abort(404)
    groups = _load_batch_groups(batch)
    schedules = _build_teacher_schedules(groups)
    slug = batch.name.lower().replace(" ", "-")
    filename = f"{slug}-teachers.pdf"
    return _render_pdf(
        "admin/planner/pdf/teacher_packet.html",
        filename,
        batch=batch,
        schedules=schedules,
    )


@web_bp.route("/admin/planner/groups/<int:group_id>/reader-packet.pdf")
def admin_group_reader_packet(group_id: int):
    group = (
        ReadingGroup.query.options(
            joinedload(ReadingGroup.members).joinedload(ReadingGroupMember.teacher),
            joinedload(ReadingGroup.assignments).joinedload(EssayAssignment.student),
        )
        .filter_by(id=group_id)
        .first()
    )
    if not group:
        abort(404)

    active_batch = _get_active_batch(group.stage)
    if not active_batch or group.batch_id != active_batch.id:
        flash("This group is not part of the active batch.", "error")
        return redirect(url_for("web.admin_planner_batch", batch_id=group.batch_id))

    assignments = [assignment for assignment in group.assignments if assignment.stage == Stage.STAGE_1]
    if not assignments:
        flash("No Stage 1 assignments found for this group.", "error")
        return redirect(url_for("web.admin_planner_batch", batch_id=group.batch_id))

    writer = PdfWriter()
    double_sided = _packets_double_sided()
    missing_files: list[int] = []

    for member in group.members:
        teacher = member.teacher
        if not member.active or not teacher or teacher.is_absent:
            continue

        essays = []
        for assignment in assignments:
            student = assignment.student
            if not student:
                continue
            pdf_path = _essay_pdf_path(student)
            if not pdf_path:
                missing_files.append(student.id)
                continue
            essays.append((assignment, student, pdf_path))

        title_reader = _create_teacher_title_page(teacher, group, [student.id for _, student, _ in essays])
        writer.add_page(title_reader.pages[0])

        if double_sided and essays:
            _add_blank_page(writer, title_reader.pages[0])

        for assignment, student, pdf_path in essays:
            try:
                reader = PdfReader(str(pdf_path))
            except Exception:
                missing_files.append(student.id)
                continue
            overlay_reader = _create_essay_overlay_page(reader.pages[0], group, assignment)
            first_page = reader.pages[0]
            first_page.merge_page(overlay_reader.pages[0])
            writer.add_page(first_page)
            for page in reader.pages[1:]:
                writer.add_page(page)

            if double_sided and len(reader.pages) % 2 != 0:
                _add_blank_page(writer, reader.pages[0])

    if not writer.pages:
        flash("No essays with uploads available for this group.", "error")
        return redirect(url_for("web.admin_planner_batch", batch_id=group.batch_id))

    output = BytesIO()
    writer.write(output)
    output.seek(0)

    if missing_files:
        flash(
            "Some essays are missing uploads: " + ", ".join(str(sid) for sid in sorted(set(missing_files))),
            "warning",
        )

    filename = f"group-{group.id}-reader-packet.pdf"
    return send_file(output, mimetype="application/pdf", as_attachment=True, download_name=filename)




@web_bp.route('/admin/stage2/<int:assignment_id>/packet.pdf')
def admin_stage2_packet(assignment_id: int):
    assignment = (
        EssayAssignment.query.options(
            joinedload(EssayAssignment.student),
            joinedload(EssayAssignment.extra_readers).joinedload(EssayAssignmentExtraReader.teacher),
        )
        .filter_by(id=assignment_id)
        .first()
    )
    if not assignment or not assignment.student:
        abort(404)

    if not assignment.stage_two_candidate:
        flash('Essay is not marked for Stage 2.', 'error')
        return redirect(url_for('web.admin_stage2_overview'))

    group = assignment.group or SimpleNamespace(name='Stage 1 group', id='—')
    assessors = _stage_assessors(assignment, Stage.STAGE_2, include_group=False)
    if not assessors:
        flash('No Stage 2 readers assigned.', 'warning')
        return redirect(url_for('web.admin_stage2_score_student', student_id=assignment.student_id))

    pdf_path = _essay_pdf_path(assignment.student)
    if not pdf_path:
        flash('Essay file missing.', 'error')
        return redirect(url_for('web.admin_stage2_score_student', student_id=assignment.student_id))

    writer = PdfWriter()
    double_sided = _packets_double_sided()

    for assessor in assessors:
        teacher = assessor.teacher
        title_reader = _create_teacher_title_page(teacher, assignment.group, [assignment.student.id] if assignment.student else [])
        writer.add_page(title_reader.pages[0])
        if double_sided:
            _add_blank_page(writer, title_reader.pages[0])

        reader = PdfReader(str(pdf_path))
        overlay_reader = _create_essay_overlay_page(reader.pages[0], assignment.group, assignment)
        first_page = reader.pages[0]
        first_page.merge_page(overlay_reader.pages[0])
        writer.add_page(first_page)
        for page in reader.pages[1:]:
            writer.add_page(page)

        if double_sided and len(reader.pages) % 2 != 0:
            _add_blank_page(writer, reader.pages[0])

    output = BytesIO()
    writer.write(output)
    output.seek(0)
    filename = f'stage2-packet-assignment-{assignment.id}.pdf'
    return send_file(output, mimetype='application/pdf', as_attachment=True, download_name=filename)
@web_bp.route("/admin/uploads/<int:assignment_id>/extra-reader-packet.pdf")
def admin_extra_reader_packet(assignment_id: int):
    assignment = (
        EssayAssignment.query.options(
            joinedload(EssayAssignment.group).joinedload(ReadingGroup.members).joinedload(ReadingGroupMember.teacher),
            joinedload(EssayAssignment.student),
            joinedload(EssayAssignment.extra_readers).joinedload(EssayAssignmentExtraReader.teacher),
        )
        .filter_by(id=assignment_id)
        .first()
    )
    if not assignment or not assignment.student:
        abort(404)

    group = assignment.group
    if not group:
        flash("Assignment is not linked to a group.", "error")
        return redirect(url_for("web.admin_uploads"))

    assessors = [entry for entry in _stage_assessors(assignment, Stage.STAGE_1) if entry.is_extra]
    if not assessors:
        flash("No extra readers assigned to this essay.", "warning")
        return redirect(url_for("web.admin_score_student", student_id=assignment.student_id))

    student = assignment.student
    pdf_path = _essay_pdf_path(student)
    if not pdf_path:
        flash("The student's essay has not been uploaded.", "error")
        return redirect(url_for("web.admin_score_student", student_id=assignment.student_id))

    try:
        essay_reader = PdfReader(str(pdf_path))
    except Exception:
        flash("Unable to open essay PDF.", "error")
        return redirect(url_for("web.admin_score_student", student_id=assignment.student_id))

    writer = PdfWriter()
    double_sided = _packets_double_sided()

    for assessor in assessors:
        teacher = assessor.teacher
        title_reader = _create_teacher_title_page(teacher, group, [student.id])
        writer.add_page(title_reader.pages[0])
        if double_sided:
            _add_blank_page(writer, title_reader.pages[0])

        essay_reader = PdfReader(str(pdf_path))
        overlay_reader = _create_essay_overlay_page(essay_reader.pages[0], group, assignment)
        first_page = essay_reader.pages[0]
        first_page.merge_page(overlay_reader.pages[0])
        writer.add_page(first_page)
        for page in essay_reader.pages[1:]:
            writer.add_page(page)

        if double_sided and len(essay_reader.pages) % 2 != 0:
            _add_blank_page(writer, essay_reader.pages[0])

    output = BytesIO()
    writer.write(output)
    output.seek(0)
    filename = f"extra-reader-assignment-{assignment.id}.pdf"
    return send_file(output, mimetype="application/pdf", as_attachment=True, download_name=filename)


@web_bp.route('/admin/stage2')
def admin_stage2_overview():
    active_batch = _get_active_batch(Stage.STAGE_1)
    if not active_batch:
        flash('Publish a Stage 1 batch before proceeding to Stage 2.', 'error')
        return redirect(url_for('web.admin_planner'))

    assignments = (
        EssayAssignment.query.options(joinedload(EssayAssignment.student))
        .filter(
            EssayAssignment.stage == Stage.STAGE_1,
            EssayAssignment.stage_two_candidate.is_(True),
            EssayAssignment.batch_id == active_batch.id,
        )
        .all()
    )
    candidates = [a for a in assignments if a.student and not a.student.is_absent]

    return render_template(
        'admin/stage2/overview.html',
        assignments=candidates,
        status_map={a.student_id: _compute_stage_one_status(a) for a in candidates},
    )


@web_bp.route('/admin/stage2/<int:student_id>', methods=['GET', 'POST'])
def admin_stage2_score_student(student_id: int):
    student = db.session.get(Student, student_id)
    if not student or student.is_absent:
        abort(404)

    assignment = _get_stage_one_assignment(student)
    if not assignment or not assignment.stage_two_candidate:
        flash('Student is not marked for Stage 2.', 'error')
        return redirect(url_for('web.admin_stage2_overview'))

    stage1_assessors = _stage_assessors(assignment, Stage.STAGE_1, include_group=True)
    stage1_scores_map = {
        score.teacher_id: score
        for score in assignment.scores
        if score.stage == Stage.STAGE_1
    }
    stage1_status = _compute_stage_one_status(assignment)
    stage2_assessors = _stage_assessors(assignment, Stage.STAGE_2, include_group=False)
    stage2_scores_map = {
        score.teacher_id: score
        for score in assignment.scores
        if score.stage == Stage.STAGE_2
    }

    pdf_available = _essay_pdf_path(student) is not None
    stage1_global_lock = _is_stage_locked(Stage.STAGE_1)
    stage2_global_lock = _is_stage_locked(Stage.STAGE_2)
    assignment_stage1_locked = assignment.stage1_locked or stage1_global_lock
    assignment_stage2_locked = assignment.stage2_locked or stage2_global_lock

    stage1_entries = []
    for assessor in stage1_assessors:
        teacher = assessor.teacher
        score_record = stage1_scores_map.get(teacher.id)
        status_info = _resolve_portal_status(student, score_record, pdf_available, locked=assignment_stage1_locked)
        stage1_entries.append(
            SimpleNamespace(
                teacher=teacher,
                teacher_id=teacher.id,
                source=assessor.source,
                is_extra=assessor.is_extra,
                score=score_record.score if score_record else None,
                updated_at=score_record.updated_at if score_record else None,
                submitted_at=score_record.submitted_at if score_record else None,
                finalized=score_record.teacher_finalized if score_record else False,
                finalized_at=score_record.teacher_finalized_at if score_record else None,
                portal_status_code=status_info.code,
                portal_status_label=status_info.label,
                portal_status_css=status_info.css,
                portal_status_timestamp=status_info.timestamp,
            )
        )

    entries = []
    for assessor in stage2_assessors:
        teacher = assessor.teacher
        score_record = stage2_scores_map.get(teacher.id)
        status_info = _resolve_portal_status(student, score_record, pdf_available, locked=assignment_stage2_locked)
        entries.append(
            SimpleNamespace(
                teacher=teacher,
                teacher_id=teacher.id,
                source=assessor.source,
                is_extra=True,
                score=score_record.score if score_record else None,
                updated_at=score_record.updated_at if score_record else None,
                finalized=score_record.teacher_finalized if score_record else False,
                finalized_at=score_record.teacher_finalized_at if score_record else None,
                portal_status_code=status_info.code,
                portal_status_label=status_info.label,
                portal_status_css=status_info.css,
                portal_status_timestamp=status_info.timestamp,
            )
        )

    assigned_teacher_ids = {entry.teacher_id for entry in entries}
    stage1_teacher_ids = {entry.teacher_id for entry in stage1_entries}
    available_query = Teacher.query.filter_by(is_absent=False)
    if assigned_teacher_ids or stage1_teacher_ids:
        available_query = available_query.filter(~Teacher.id.in_(assigned_teacher_ids.union(stage1_teacher_ids)))
    available_teachers = [
        teacher
        for teacher in available_query.order_by(Teacher.last_name.asc(), Teacher.first_name.asc()).all()
        if _teacher_can_grade(student, teacher, student.essay_language)
    ]

    teacher_stats: dict[int, SimpleNamespace] = {}
    suggested_teachers: list[Teacher] = []
    if available_teachers:
        load_assignments = (
            EssayAssignment.query.options(
                joinedload(EssayAssignment.scores),
                joinedload(EssayAssignment.extra_readers).joinedload(EssayAssignmentExtraReader.teacher),
                joinedload(EssayAssignment.group).joinedload(ReadingGroup.members).joinedload(ReadingGroupMember.teacher),
            )
            .filter(
                EssayAssignment.stage == Stage.STAGE_1,
                EssayAssignment.batch_id == assignment.batch_id,
            )
            .all()
        )
        load_snapshot = _teacher_load_snapshot(load_assignments)
        for teacher in available_teachers:
            entry = load_snapshot.get(teacher.id, _empty_load_entry())
            stage1_pending = max(entry.stage1_expected - entry.stage1_completed, 0)
            stage2_pending = max(entry.stage2_assigned - entry.stage2_completed, 0)
            teacher_stats[teacher.id] = SimpleNamespace(
                stage1_expected=entry.stage1_expected,
                stage1_completed=entry.stage1_completed,
                stage1_pending=stage1_pending,
                stage2_assigned=entry.stage2_assigned,
                stage2_completed=entry.stage2_completed,
                stage2_pending=stage2_pending,
                last_stage2_activity=entry.last_stage2_activity,
            )

        if teacher_stats:
            def _suggestion_key(t: Teacher):
                stats_entry = teacher_stats[t.id]
                last_activity = stats_entry.last_stage2_activity or datetime.min
                return (
                    1 if stats_entry.stage1_pending > 0 else 0,
                    stats_entry.stage1_pending,
                    stats_entry.stage2_pending,
                    stats_entry.stage2_assigned,
                    last_activity,
                    t.last_name,
                    t.first_name,
                )

            suggested_teachers = sorted(available_teachers, key=_suggestion_key)[:5]

    action = request.form.get('action')
    remove_id = request.form.get('remove_reader')
    unlock_id = request.form.get('unlock_reader')

    if request.method == 'POST' and action == 'toggle_stage2_lock':
        assignment.stage2_locked = not assignment.stage2_locked
        now = datetime.utcnow()
        for score in assignment.scores:
            if score.stage != Stage.STAGE_2:
                continue
            score.locked_by_admin = assignment.stage2_locked
            if assignment.stage2_locked:
                score.admin_updated_at = now
        log_activity(
            'stage2_grading_lock',
            f'Stage 2 grading lock set to {assignment.stage2_locked} for student {student.id}',
            object_type='student',
            object_id=student.id,
            details={'locked': assignment.stage2_locked},
        )
        db.session.commit()
        flash('Stage 2 grading locked.' if assignment.stage2_locked else 'Stage 2 grading unlocked.', 'success')
        return redirect(url_for('web.admin_stage2_score_student', student_id=student.id))

    if request.method == 'POST' and unlock_id:
        try:
            teacher_id = int(unlock_id)
        except ValueError:
            flash('Invalid teacher selection.', 'error')
            return redirect(url_for('web.admin_stage2_score_student', student_id=student.id))
        score_record = stage2_scores_map.get(teacher_id)
        if not score_record or not score_record.teacher_finalized:
            flash('Score is not finalized for this teacher.', 'warning')
            return redirect(url_for('web.admin_stage2_score_student', student_id=student.id))
        score_record.teacher_finalized = False
        score_record.teacher_finalized_at = None
        score_record.admin_updated_at = datetime.utcnow()
        log_activity(
            'stage2_score_unlocked',
            f'Unlocked Stage 2 score for teacher {teacher_id} on student {student.id}',
            object_type='student',
            object_id=student.id,
            details={'teacher_id': teacher_id},
        )
        db.session.commit()
        flash('Teacher score unlocked for editing.', 'success')
        return redirect(url_for('web.admin_stage2_score_student', student_id=student.id))

    if request.method == 'POST' and remove_id:
        try:
            teacher_id = int(remove_id)
        except ValueError:
            flash('Invalid teacher selection.', 'error')
            return redirect(url_for('web.admin_stage2_score_student', student_id=student.id))
        extra = EssayAssignmentExtraReader.query.filter_by(assignment_id=assignment.id, teacher_id=teacher_id, stage=Stage.STAGE_2).first()
        if not extra:
            flash('Extra reader not found for this essay.', 'error')
            return redirect(url_for('web.admin_stage2_score_student', student_id=student.id))
        score_record = stage2_scores_map.get(teacher_id)
        if score_record and score_record.stage == Stage.STAGE_2:
            db.session.delete(score_record)
            stage2_scores_map.pop(teacher_id, None)
        db.session.delete(extra)
        log_activity(
            'stage2_extra_reader_removed',
            f'Stage 2 reader removed: {teacher_id}',
            object_type='student',
            object_id=student.id,
            details={'teacher_id': teacher_id},
        )
        db.session.commit()
        flash('Stage 2 reader removed.', 'success')
        return redirect(url_for('web.admin_stage2_score_student', student_id=student.id))

    if request.method == 'POST' and action == 'add_reader':
        teacher_id = request.form.get('teacher_id')
        if not teacher_id:
            flash('Select a teacher to add.', 'error')
            return redirect(url_for('web.admin_stage2_score_student', student_id=student.id))
        try:
            teacher_id_int = int(teacher_id)
        except ValueError:
            flash('Invalid teacher selection.', 'error')
            return redirect(url_for('web.admin_stage2_score_student', student_id=student.id))
        if teacher_id_int in assigned_teacher_ids or teacher_id_int in stage1_teacher_ids:
            flash('Teacher already assigned to this essay.', 'warning')
            return redirect(url_for('web.admin_stage2_score_student', student_id=student.id))
        teacher = db.session.get(Teacher, teacher_id_int)
        if not teacher or teacher.is_absent:
            flash('Teacher not available.', 'error')
            return redirect(url_for('web.admin_stage2_score_student', student_id=student.id))
        if not _teacher_can_grade(student, teacher, student.essay_language):
            flash('Teacher is not eligible to grade this essay.', 'error')
            return redirect(url_for('web.admin_stage2_score_student', student_id=student.id))
        db.session.add(
            EssayAssignmentExtraReader(
                assignment_id=assignment.id,
                teacher_id=teacher_id_int,
                stage=Stage.STAGE_2,
            )
        )
        log_activity(
            'stage2_extra_reader_added',
            f'Added Stage 2 reader {teacher_id_int} for student {student.id}',
            object_type='student',
            object_id=student.id,
            details={'teacher_id': teacher_id_int},
        )
        db.session.commit()
        flash('Stage 2 reader assigned.', 'success')
        return redirect(url_for('web.admin_stage2_score_student', student_id=student.id))

    if request.method == 'POST' and action == 'update_scores':
        updates = {}
        now = datetime.utcnow()
        for entry in entries:
            field_name = f'score_{entry.teacher_id}'
            value = request.form.get(field_name, '').strip()
            if not value:
                continue
            try:
                numeric = float(value)
            except ValueError:
                flash(f"Invalid score for {entry.teacher.first_name} {entry.teacher.last_name}.", 'error')
                return redirect(url_for('web.admin_stage2_score_student', student_id=student.id))
            if numeric < 0 or numeric > 10:
                flash('Scores must be between 0 and 10.', 'error')
                return redirect(url_for('web.admin_stage2_score_student', student_id=student.id))
            score_record = stage2_scores_map.get(entry.teacher_id)
            if not score_record:
                score_record = EssayScore(
                    student_id=student.id,
                    teacher_id=entry.teacher_id,
                    assignment_id=assignment.id,
                    stage=Stage.STAGE_2,
                )
                db.session.add(score_record)
                stage2_scores_map[entry.teacher_id] = score_record
            prev_admin_entered = score_record.admin_entered if score_record else False
            prev_admin_override = score_record.admin_override if score_record else False
            had_teacher_input = bool(score_record.submitted_at) or bool(score_record.teacher_finalized)
            existing_score = score_record.score if score_record and score_record.score is not None else None

            if existing_score is not None and math.isclose(existing_score, numeric, abs_tol=1e-9):
                continue

            score_record.score = numeric
            score_record.admin_updated_at = now
            if had_teacher_input and not prev_admin_override and not prev_admin_entered:
                score_record.admin_override = True
                score_record.admin_entered = False
            elif prev_admin_override:
                score_record.admin_override = True
                score_record.admin_entered = False
            else:
                score_record.admin_entered = True
                score_record.admin_override = False

            score_record.teacher_finalized = False
            score_record.teacher_finalized_at = None
            updates[entry.teacher_id] = numeric
        if not updates:
            flash('No score changes detected.', 'info')
            return redirect(url_for('web.admin_stage2_score_student', student_id=student.id))

        log_activity(
            'stage2_scores_updated',
            f'Stage 2 scores updated for student {student.id}',
            object_type='student',
            object_id=student.id,
            details={'updates': updates},
        )
        db.session.commit()
        flash('Stage 2 scores saved.', 'success')
        return redirect(url_for('web.admin_stage2_score_student', student_id=student.id))

    if request.method == 'POST' and action == 'mark_stage3':
        assignment.stage_three_recommended = not assignment.stage_three_recommended
        log_activity(
            'stage2_mark_stage3',
            f'Stage 3 recommendation set to {assignment.stage_three_recommended} for student {student.id}',
            object_type='student',
            object_id=student.id,
        )
        db.session.commit()
        return redirect(url_for('web.admin_stage2_score_student', student_id=student.id))

    stage2_status = _compute_stage_two_status(assignment)
    combined_status = _compute_combined_status(assignment)
    entries = []
    for assessor in _stage_assessors(assignment, Stage.STAGE_2, include_group=False):
        teacher = assessor.teacher
        score_record = stage2_scores_map.get(teacher.id)
        status_info = _resolve_portal_status(student, score_record, pdf_available, locked=assignment_stage2_locked)
        entries.append(
            SimpleNamespace(
                teacher=teacher,
                teacher_id=teacher.id,
                source=assessor.source,
                is_extra=True,
                score=score_record.score if score_record else None,
                updated_at=score_record.updated_at if score_record else None,
                finalized=score_record.teacher_finalized if score_record else False,
                finalized_at=score_record.teacher_finalized_at if score_record else None,
                submitted_at=score_record.submitted_at if score_record else None,
                portal_status_code=status_info.code,
                portal_status_label=status_info.label,
                portal_status_css=status_info.css,
                portal_status_timestamp=status_info.timestamp,
            )
        )

    return render_template(
        'admin/stage2/scoring.html',
        student=student,
        assignment=assignment,
        stage1_status=stage1_status,
        stage1_entries=stage1_entries,
        stage2_status=stage2_status,
        combined_status=combined_status,
        entries=entries,
        available_teachers=available_teachers,
        teacher_stats=teacher_stats,
        suggested_teachers=suggested_teachers,
        stage1_global_lock=stage1_global_lock,
        stage2_global_lock=stage2_global_lock,
        **_quick_message_context(),
    )

@web_bp.route("/admin/students/export")
def export_students():
    students = Student.query.order_by(Student.id.asc()).all()
    workbook = _students_workbook(students)
    return send_file(
        workbook,
        as_attachment=True,
        download_name="ipo-students.xlsx",
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


@web_bp.route("/admin/teachers/export")
def export_teachers():
    teachers = Teacher.query.order_by(Teacher.id.asc()).all()
    workbook = _teachers_workbook(teachers)
    return send_file(
        workbook,
        as_attachment=True,
        download_name="ipo-teachers.xlsx",
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


def _students_workbook(students: list[Student]) -> io.BytesIO:
    wb = Workbook()
    ws = wb.active
    ws.title = "Students"
    ws.append(
        [
            "ID",
            "Country",
            "First name",
            "Last name",
            "Email",
            "School",
            "Gender",
            "Date of birth",
            "Essay language",
            "Keyboard preference",
            "Meal preference",
            "Special needs",
            "Created at",
            "Updated at",
        ]
    )

    for student in students:
        ws.append(
            [
                student.id,
                student.country,
                student.first_name,
                student.last_name,
                student.email,
                student.school,
                student.gender,
                student.date_of_birth.isoformat() if student.date_of_birth else "",
                student.essay_language,
                student.keyboard_preference,
                student.meal_preference,
                student.special_needs or "",
                student.created_at.strftime("%Y-%m-%d %H:%M") if student.created_at else "",
                student.updated_at.strftime("%Y-%m-%d %H:%M") if student.updated_at else "",
            ]
        )

    ws.freeze_panes = "A2"
    ws.auto_filter.ref = ws.dimensions

    stream = io.BytesIO()
    wb.save(stream)
    stream.seek(0)
    return stream


def _teachers_workbook(teachers: list[Teacher]) -> io.BytesIO:
    wb = Workbook()
    ws = wb.active
    ws.title = "Teachers"
    ws.append(
        [
            "ID",
            "Country",
            "First name",
            "Last name",
            "Email",
            "School",
            "Gender",
            "Languages",
            "Meal preference",
            "T-shirt size",
            "Delegation leader",
            "Special needs",
            "Created at",
            "Updated at",
        ]
    )

    for teacher in teachers:
        ws.append(
            [
                teacher.id,
                teacher.country,
                teacher.first_name,
                teacher.last_name,
                teacher.email,
                teacher.school,
                teacher.gender,
                teacher.languages,
                teacher.meal_preference,
                teacher.tshirt_size,
                "Yes" if teacher.delegation_leader else "No",
                teacher.special_needs or "",
                teacher.created_at.strftime("%Y-%m-%d %H:%M") if teacher.created_at else "",
                teacher.updated_at.strftime("%Y-%m-%d %H:%M") if teacher.updated_at else "",
            ]
        )

    ws.freeze_panes = "A2"
    ws.auto_filter.ref = ws.dimensions

    stream = io.BytesIO()
    wb.save(stream)
    stream.seek(0)
    return stream
