#!/usr/bin/env python

"""Create a repeatable assessor-webinar demo state.

This script is intentionally additive to the application codebase: it uses the
existing app factory, models, seed helpers, and planner helpers, but does not
change core application behavior.
"""

from __future__ import annotations

import argparse
import csv
import random
import secrets
import sys
import warnings
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

warnings.filterwarnings(
    "ignore",
    category=DeprecationWarning,
    message=r"datetime\.datetime\.utcnow\(\) is deprecated.*",
)

CURRENT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = CURRENT_DIR.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from werkzeug.security import generate_password_hash  # noqa: E402

from ipo_app import create_app  # noqa: E402
from ipo_app.extensions import db  # noqa: E402
from ipo_app.models import (  # noqa: E402
    AssignmentBatch,
    EssayAssignment,
    EssayAssignmentExtraReader,
    EssayScore,
    GroupMemberRole,
    PlannerStatus,
    ReadingGroup,
    ReadingGroupMember,
    Stage,
    Student,
    Survey,
    SurveyAssignment,
    SurveyAssignmentStatus,
    SurveyAudience,
    SurveyQuestion,
    SurveyQuestionType,
    SurveyStatus,
    Teacher,
    TeacherLanguage,
    TeacherMessage,
    TeacherMessagePriority,
    TeacherMessageStatus,
)
from ipo_app.views import (  # noqa: E402
    SETTING_EMAIL_AUTOMATION_ENABLED,
    SETTING_ESSAY_WORD_LIMIT,
    SETTING_ESSAY_WORD_LIMIT_MODE,
    SETTING_EVENT_END_OVERRIDE,
    SETTING_LOGIN_EMAIL_ENABLED,
    SETTING_LOGIN_FOLDED_ALIAS_ENABLED,
    SETTING_PACKET_PRINT_MODE,
    SETTING_REGISTRATION_INVITE_ONLY,
    SETTING_STAGE1_LOCK,
    SETTING_STAGE2_LOCK,
    SETTING_TEACHER_PORTAL_ENABLED,
    SETTING_UPLOAD_LOCK,
    SETTING_UPLOAD_MODULE_ENABLED,
    _auto_assign_essays,
    _auto_generate_groups_for_batch,
    _set_setting,
)
from scripts import seed_mock_data  # noqa: E402
from scripts.purge_participant_data import (  # noqa: E402
    ACTIVITY_LOG_PURGE,
    BASE_PURGE_PLAN,
    _collect_counts,
    _collect_upload_filenames,
    _delete_upload_files,
    _print_counts,
    _print_preserved_counts,
    _purge_targets,
    _upload_folder,
)
from scripts.seed_mock_essays import build_placeholder_writer  # noqa: E402
from scripts.utils import seed_helpers as helpers  # noqa: E402


DEFAULT_DEMO_USERNAME = "demo-assessor"
DEFAULT_DEMO_PASSWORD = "assess-demo-2026"
DEFAULT_BATCH_NAME = "Assessor webinar demo batch"
DEMO_ACTOR = "webinar-bootstrap"


@dataclass
class TeacherPortalCredential:
    teacher: Teacher
    username: str
    password: str


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Prepare a complete assessor webinar demo state."
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Required when existing participant/demo records will be purged.",
    )
    parser.add_argument(
        "--purge-activity-logs",
        action="store_true",
        help="Also purge activity logs. By default logs are preserved.",
    )
    parser.add_argument(
        "--keep-upload-files",
        action="store_true",
        help="Do not delete referenced upload files during purge.",
    )
    parser.add_argument(
        "--students",
        type=int,
        default=90,
        help="Number of seeded students to create. Default: 90.",
    )
    parser.add_argument(
        "--demo-username",
        default=DEFAULT_DEMO_USERNAME,
        help=f"Teacher portal username for the demo assessor. Default: {DEFAULT_DEMO_USERNAME}.",
    )
    parser.add_argument(
        "--demo-password",
        default=DEFAULT_DEMO_PASSWORD,
        help=f"Teacher portal password for the demo assessor. Default: {DEFAULT_DEMO_PASSWORD}.",
    )
    parser.add_argument(
        "--attendee-teachers",
        type=int,
        default=0,
        help="Number of additional teacher portal accounts to generate for attendee hands-on testing. Default: 0.",
    )
    parser.add_argument(
        "--attendee-username-prefix",
        default="webinar-teacher",
        help="Username prefix for generated attendee teacher accounts. Default: webinar-teacher.",
    )
    parser.add_argument(
        "--attendee-password-prefix",
        default="webinar-pass",
        help="Password prefix for generated attendee teacher accounts. Default: webinar-pass.",
    )
    parser.add_argument(
        "--attendee-assignments-per-group",
        type=int,
        default=2,
        help="Manual Stage 1 assignments per attendee reading group. Default: 2.",
    )
    parser.add_argument(
        "--attendee-credentials-file",
        default=None,
        help="Optional CSV path for generated attendee teacher credentials.",
    )
    parser.add_argument(
        "--batch-name",
        default=DEFAULT_BATCH_NAME,
        help=f"Stage 1 batch name. Default: {DEFAULT_BATCH_NAME}.",
    )
    parser.add_argument(
        "--base-url",
        default="http://localhost:5000",
        help="Base URL printed in the final credential summary.",
    )
    parser.add_argument(
        "--random-seed",
        type=int,
        default=42,
        help="Random seed for repeatable data and scores. Default: 42.",
    )
    return parser.parse_args()


def _has_existing_demo_data(targets) -> bool:
    counts = _collect_counts(targets)
    return any(counts.values())


def purge_existing_data(app, *, purge_activity_logs: bool, delete_upload_files: bool) -> None:
    targets = BASE_PURGE_PLAN + ((ACTIVITY_LOG_PURGE,) if purge_activity_logs else ())
    upload_filenames = _collect_upload_filenames() if delete_upload_files else set()
    before = _collect_counts(targets)
    _print_counts("Targeted rows before webinar bootstrap purge:", targets, before)
    _print_preserved_counts()

    deleted = _purge_targets(targets)
    db.session.commit()
    _print_counts("Deleted rows:", targets, deleted)

    if delete_upload_files:
        base = _upload_folder(app)
        removed, missing, skipped_unsafe, errors = _delete_upload_files(base, upload_filenames)
        print("Upload file cleanup:")
        print(f"  - removed: {removed}")
        print(f"  - missing: {missing}")
        print(f"  - skipped_unsafe: {skipped_unsafe}")
        print(f"  - errors: {errors}")
        if errors:
            raise RuntimeError("Upload file cleanup reported errors.")


def _reset_seed_module_state() -> None:
    for name in (
        "_teacher_email_counts",
        "_student_email_counts",
        "_student_username_set",
        "_seed_teacher_credentials",
        "_seed_delegation_leader_credentials",
    ):
        value = getattr(seed_mock_data, name, None)
        if hasattr(value, "clear"):
            value.clear()


def seed_people(student_count: int, random_seed: int) -> None:
    _reset_seed_module_state()
    seed_mock_data.random.seed(random_seed)
    teachers = seed_mock_data.seed_teachers()
    students = seed_mock_data.seed_students(student_count)
    db.session.commit()
    seed_mock_data.ensure_message_templates()
    print(f"Seeded baseline data: {teachers} teachers, {students} students.")


def mark_seeded_people_demo_ready() -> None:
    now = datetime.utcnow()
    for teacher in Teacher.query.all():
        teacher.accepted_ethics = True
        teacher.accepted_ethics_at = teacher.accepted_ethics_at or now
        teacher.declared_assessor_competence = True
        teacher.declared_assessor_competence_at = teacher.declared_assessor_competence_at or now
        teacher.gdpr_acknowledged = True
        teacher.gdpr_acknowledged_at = teacher.gdpr_acknowledged_at or now
        teacher.photo_consent = True
        teacher.photo_consent_at = teacher.photo_consent_at or now

    for student in Student.query.all():
        student.accepted_ethics = True
        student.accepted_ethics_at = student.accepted_ethics_at or now
        student.gdpr_acknowledged = True
        student.gdpr_acknowledged_at = student.gdpr_acknowledged_at or now
        student.photo_consent = True
        student.photo_consent_at = student.photo_consent_at or now

    db.session.commit()


def create_demo_teacher(username: str, password: str) -> Teacher:
    now = datetime.utcnow()
    teacher = Teacher(
        country="Webinarland",
        first_name="Demo",
        last_name="Assessor",
        email="demo.assessor@ipo.test",
        school="IPO Webinar Demo School",
        sex_document="female",
        accommodation_room_sharing="any_sex",
        languages="English",
        prior_ipo_assessor=True,
        prior_ipo_assessor_level=3,
        meal_preference="No preference",
        special_needs=None,
        tshirt_size="M",
        delegation_leader=False,
        is_absent=False,
        accepted_ethics=True,
        accepted_ethics_at=now,
        declared_assessor_competence=True,
        declared_assessor_competence_at=now,
        gdpr_acknowledged=True,
        gdpr_acknowledged_at=now,
        photo_consent=True,
        photo_consent_at=now,
        portal_username=username,
        portal_password_hash=generate_password_hash(password),
        portal_token=f"demo-{secrets.token_hex(16)}",
    )
    teacher.language_entries = [TeacherLanguage(language="English")]
    db.session.add(teacher)
    db.session.flush()
    return teacher


def _attendee_username(prefix: str, index: int) -> str:
    return f"{prefix}-{index:03d}"


def _attendee_password(prefix: str, index: int) -> str:
    return f"{prefix}-{index:03d}"


def create_attendee_teachers(
    *,
    count: int,
    username_prefix: str,
    password_prefix: str,
) -> list[TeacherPortalCredential]:
    now = datetime.utcnow()
    credentials: list[TeacherPortalCredential] = []
    for index in range(1, count + 1):
        username = _attendee_username(username_prefix, index)
        password = _attendee_password(password_prefix, index)
        teacher = Teacher(
            country="Webinarland",
            first_name="Webinar",
            last_name=f"Teacher {index:03d}",
            email=f"webinar.teacher.{index:03d}@ipo.test",
            school="IPO Webinar Practice School",
            sex_document="female" if index % 2 else "male",
            accommodation_room_sharing="any_sex",
            languages="English",
            prior_ipo_assessor=True,
            prior_ipo_assessor_level=1,
            meal_preference="No preference",
            special_needs=None,
            tshirt_size="M",
            delegation_leader=False,
            is_absent=False,
            accepted_ethics=True,
            accepted_ethics_at=now,
            declared_assessor_competence=True,
            declared_assessor_competence_at=now,
            gdpr_acknowledged=True,
            gdpr_acknowledged_at=now,
            photo_consent=True,
            photo_consent_at=now,
            portal_username=username,
            portal_password_hash=generate_password_hash(password),
            portal_token=f"attendee-{secrets.token_hex(16)}",
        )
        teacher.language_entries = [TeacherLanguage(language="English")]
        db.session.add(teacher)
        credentials.append(TeacherPortalCredential(teacher=teacher, username=username, password=password))
    db.session.flush()
    return credentials


def _teacher_languages(teacher: Teacher) -> set[str]:
    languages = {entry.language for entry in teacher.language_entries if entry.language}
    if not languages and teacher.languages:
        languages = {item.strip() for item in teacher.languages.split(",") if item.strip()}
    return languages


def select_support_teachers(
    demo_teacher: Teacher,
    count: int = 3,
    *,
    exclude_teacher_ids: set[int] | None = None,
) -> list[Teacher]:
    excluded = set(exclude_teacher_ids or set())
    excluded.add(demo_teacher.id)
    candidates = [
        teacher
        for teacher in Teacher.query.order_by(Teacher.country.asc(), Teacher.last_name.asc()).all()
        if teacher.id not in excluded
        and not teacher.is_absent
        and teacher.declared_assessor_competence
        and "English" in _teacher_languages(teacher)
    ]
    selected: list[Teacher] = []
    seen_countries = {demo_teacher.country}
    for teacher in candidates:
        if teacher.country in seen_countries:
            continue
        selected.append(teacher)
        seen_countries.add(teacher.country)
        if len(selected) == count:
            return selected
    for teacher in candidates:
        if teacher in selected:
            continue
        selected.append(teacher)
        if len(selected) == count:
            return selected
    raise RuntimeError("Not enough English-speaking support teachers for the demo group.")


def _assigned_student_ids(batch: AssignmentBatch) -> set[int]:
    return {assignment.student_id for assignment in batch.assignments if assignment.student_id}


def _active_group_countries(group: ReadingGroup) -> set[str]:
    return {
        member.teacher.country
        for member in group.members
        if member.active and member.teacher and not member.teacher.is_absent
    }


def _assign_manual_english_students(
    *,
    batch: AssignmentBatch,
    group: ReadingGroup,
    count: int,
) -> list[EssayAssignment]:
    used_student_ids = _assigned_student_ids(batch)
    blocked_countries = _active_group_countries(group)
    candidates = (
        Student.query.filter_by(essay_language="English", is_absent=False)
        .order_by(Student.country.asc(), Student.last_name.asc(), Student.id.asc())
        .all()
    )
    assignments: list[EssayAssignment] = []
    for student in candidates:
        if student.id in used_student_ids:
            continue
        if not group.allow_same_country and student.country in blocked_countries:
            continue
        assignment = EssayAssignment(
            student_id=student.id,
            group=group,
            batch=batch,
            stage=Stage.STAGE_1,
            manual_override=True,
            status=PlannerStatus.DRAFT,
        )
        db.session.add(assignment)
        assignments.append(assignment)
        used_student_ids.add(student.id)
        if len(assignments) == count:
            break

    if len(assignments) < count:
        raise RuntimeError(
            f"Not enough English-language students for attendee group {group.name}. "
            "Reduce --attendee-teachers, reduce --attendee-assignments-per-group, or increase --students."
        )
    return assignments


def create_attendee_groups(
    *,
    batch: AssignmentBatch,
    demo_teacher: Teacher,
    attendee_credentials: list[TeacherPortalCredential],
    assignments_per_group: int,
) -> list[ReadingGroup]:
    if not attendee_credentials:
        return []

    used_teacher_ids = {
        member.teacher_id
        for group in batch.groups
        for member in group.members
        if member.teacher_id
    }
    attendee_groups: list[ReadingGroup] = []
    attendee_teachers = [credential.teacher for credential in attendee_credentials]

    for offset in range(0, len(attendee_teachers), 4):
        chunk = attendee_teachers[offset : offset + 4]
        missing = 4 - len(chunk)
        support_teachers: list[Teacher] = []
        if missing:
            support_teachers = select_support_teachers(
                demo_teacher,
                missing,
                exclude_teacher_ids=used_teacher_ids | {teacher.id for teacher in attendee_teachers},
            )
        members = [*chunk, *support_teachers]
        group = ReadingGroup(
            name=f"Webinar Attendee Group {len(attendee_groups) + 1}",
            stage=Stage.STAGE_1,
            language="English",
            target_essay_load=assignments_per_group,
            status=PlannerStatus.DRAFT,
            auto_generated=False,
            locked=True,
            allow_same_country=False,
            notes="Manual group for generated attendee practice accounts.",
            batch=batch,
        )
        db.session.add(group)
        db.session.flush()
        for index, teacher in enumerate(members):
            db.session.add(
                ReadingGroupMember(
                    group=group,
                    teacher=teacher,
                    role=GroupMemberRole.LEADER if index == 0 else GroupMemberRole.READER,
                    active=True,
                )
            )
            used_teacher_ids.add(teacher.id)
        db.session.flush()
        _assign_manual_english_students(
            batch=batch,
            group=group,
            count=assignments_per_group,
        )
        attendee_groups.append(group)
    db.session.flush()
    return attendee_groups


def create_batch_and_demo_group(
    *,
    batch_name: str,
    demo_teacher: Teacher,
    attendee_credentials: list[TeacherPortalCredential],
    attendee_assignments_per_group: int,
    demo_assignment_count: int = 6,
) -> tuple[AssignmentBatch, ReadingGroup, list[EssayAssignment], list[ReadingGroup], dict]:
    batch = AssignmentBatch(
        name=batch_name,
        stage=Stage.STAGE_1,
        status=PlannerStatus.DRAFT,
        created_by=DEMO_ACTOR,
        notes="Generated by scripts/bootstrap_assessor_webinar.py.",
    )
    db.session.add(batch)
    db.session.flush()

    support_teachers = select_support_teachers(demo_teacher, 3)
    demo_group = ReadingGroup(
        name="Webinar Demo Group",
        stage=Stage.STAGE_1,
        language="English",
        target_essay_load=demo_assignment_count,
        status=PlannerStatus.DRAFT,
        auto_generated=False,
        locked=False,
        allow_same_country=False,
        notes="Manual group used for assessor webinar demonstration.",
        batch=batch,
    )
    db.session.add(demo_group)
    db.session.flush()

    members = [demo_teacher, *support_teachers]
    for index, teacher in enumerate(members):
        db.session.add(
            ReadingGroupMember(
                group=demo_group,
                teacher=teacher,
                role=GroupMemberRole.LEADER if index == 0 else GroupMemberRole.READER,
                active=True,
            )
        )
    db.session.flush()

    blocked_countries = {teacher.country for teacher in members}
    demo_students = [
        student
        for student in Student.query.filter_by(essay_language="English", is_absent=False)
        .order_by(Student.country.asc(), Student.last_name.asc(), Student.id.asc())
        .all()
        if student.country not in blocked_countries
    ]
    if len(demo_students) < demo_assignment_count:
        demo_group.allow_same_country = True
        demo_students = (
            Student.query.filter_by(essay_language="English", is_absent=False)
            .order_by(Student.country.asc(), Student.last_name.asc(), Student.id.asc())
            .limit(demo_assignment_count)
            .all()
        )
    if len(demo_students) < demo_assignment_count:
        raise RuntimeError("Not enough English-language students for the demo assignments.")

    demo_assignments: list[EssayAssignment] = []
    for student in demo_students[:demo_assignment_count]:
        assignment = EssayAssignment(
            student_id=student.id,
            group=demo_group,
            batch=batch,
            stage=Stage.STAGE_1,
            manual_override=True,
            status=PlannerStatus.DRAFT,
        )
        db.session.add(assignment)
        demo_assignments.append(assignment)
    db.session.flush()

    attendee_groups = create_attendee_groups(
        batch=batch,
        demo_teacher=demo_teacher,
        attendee_credentials=attendee_credentials,
        assignments_per_group=attendee_assignments_per_group,
    )

    group_summary = _auto_generate_groups_for_batch(batch)
    if group_summary.get("matching_failed"):
        raise RuntimeError(f"Auto group generation failed: {group_summary}")
    assigned, skipped = _auto_assign_essays(batch)
    print(f"Planner auto setup: assigned {assigned} additional essays; skipped {len(skipped)}.")
    for group in attendee_groups:
        group.locked = False

    now = datetime.utcnow()
    batch.status = PlannerStatus.PUBLISHED
    batch.published_at = now
    for group in batch.groups:
        group.status = PlannerStatus.PUBLISHED
    for assignment in batch.assignments:
        assignment.status = PlannerStatus.PUBLISHED
    db.session.commit()
    return batch, demo_group, demo_assignments, attendee_groups, group_summary


def create_placeholder_essays() -> int:
    processed = 0
    now = datetime.utcnow()
    for student in Student.query.filter_by(is_absent=False).order_by(Student.id.asc()).all():
        writer = build_placeholder_writer(student)
        stored_path = helpers.write_pdf_to_student(student, writer, overwrite=True)
        if stored_path is None:
            continue
        student.essay_finalized = True
        student.essay_finalized_at = now
        processed += 1
    db.session.commit()
    return processed


def seed_stage1_scores(
    demo_teacher: Teacher,
    random_seed: int,
    *,
    excluded_teacher_ids: set[int] | None = None,
) -> None:
    rng = random.Random(random_seed)
    now = datetime.utcnow()
    excluded = set(excluded_teacher_ids or set())
    excluded.add(demo_teacher.id)
    score_options = helpers.ScoreOptions(min_score=4.5, max_score=9.5, step=0.1, finalize=False)
    score_options.validate()

    assignments = (
        EssayAssignment.query.filter_by(stage=Stage.STAGE_1)
        .order_by(EssayAssignment.student_id.asc())
        .all()
    )
    total_scores = 0
    for assignment in assignments:
        student = assignment.student
        if not student or student.is_absent:
            continue
        assessors = helpers.stage_assessors(assignment, Stage.STAGE_1, include_group=True)
        if not assessors:
            continue

        should_promote = rng.random() < 0.27
        force_high_spread = rng.random() < 0.12 and len(assessors) >= 2
        if force_high_spread:
            should_promote = False
        target_mean = rng.uniform(7.2, 8.2) if should_promote else rng.uniform(5.0, 6.3)
        target_std = 0.35 if should_promote else 0.6

        changed_records: list[EssayScore] = []
        for assessor in assessors:
            teacher = assessor.teacher
            if not teacher or teacher.id in excluded:
                continue
            record = helpers.ensure_score_record(
                assignment,
                student.id,
                teacher.id,
                Stage.STAGE_1,
            )
            raw_score = rng.normalvariate(target_mean, target_std)
            score_value = score_options.quantize(raw_score)
            helpers.update_score(record, score_value, options=score_options, now=now)
            changed_records.append(record)
            total_scores += 1

        if force_high_spread and len(changed_records) >= 2:
            low_value = score_options.quantize(max(score_options.min_score, target_mean - 1.8))
            high_value = score_options.quantize(min(score_options.max_score, low_value + 3.5))
            helpers.update_score(changed_records[0], low_value, options=score_options, now=now)
            helpers.update_score(changed_records[-1], high_value, options=score_options, now=now)

        if should_promote and changed_records:
            stage1_values = [
                score.score
                for score in assignment.scores
                if score.stage == Stage.STAGE_1 and score.score is not None
            ]
            if stage1_values:
                average = sum(stage1_values) / len(stage1_values)
                if average < 7.0:
                    boost = 7.2 - average
                    for record in changed_records:
                        boosted = score_options.quantize(min(score_options.max_score, record.score + boost))
                        helpers.update_score(record, boosted, options=score_options, now=now)

        helpers.apply_stage1_rules(assignment)

    db.session.commit()
    print(f"Seeded {total_scores} Stage 1 non-demo reader scores.")


def _delete_demo_score(assignment: EssayAssignment, teacher: Teacher, stage: Stage) -> None:
    EssayScore.query.filter_by(
        assignment_id=assignment.id,
        teacher_id=teacher.id,
        stage=stage,
    ).delete(synchronize_session=False)


def _set_demo_score(
    assignment: EssayAssignment,
    teacher: Teacher,
    stage: Stage,
    *,
    score: float,
    comments: str,
    finalized: bool,
) -> EssayScore:
    now = datetime.utcnow()
    record = helpers.ensure_score_record(assignment, assignment.student_id, teacher.id, stage)
    record.score = helpers.ScoreOptions(min_score=1, max_score=10).quantize(score)
    record.comments = comments
    record.submitted_at = now
    record.teacher_finalized = finalized
    record.teacher_finalized_at = now if finalized else None
    record.admin_entered = False
    record.admin_override = False
    record.admin_updated_at = None
    record.locked_by_admin = False
    return record


def shape_demo_teacher_assignments(demo_teacher: Teacher, demo_assignments: list[EssayAssignment]) -> None:
    if len(demo_assignments) < 5:
        raise RuntimeError("Expected at least five demo assignments.")

    ordered = sorted(demo_assignments, key=lambda assignment: assignment.id)
    pending, draft, finalized, locked, awaiting = ordered[:5]

    for assignment in ordered:
        _delete_demo_score(assignment, demo_teacher, Stage.STAGE_1)
        assignment.stage1_locked = False
        assignment.student.essay_finalized = True
        assignment.student.essay_finalized_at = assignment.student.essay_finalized_at or datetime.utcnow()

    _set_demo_score(
        draft,
        demo_teacher,
        Stage.STAGE_1,
        score=8.0,
        comments="Draft score prepared for the webinar.",
        finalized=False,
    )
    _set_demo_score(
        finalized,
        demo_teacher,
        Stage.STAGE_1,
        score=8.5,
        comments="Finalized demo score.",
        finalized=True,
    )
    locked.stage1_locked = True
    awaiting.student.essay_finalized = False
    awaiting.student.essay_finalized_at = None

    for assignment in ordered:
        helpers.apply_stage1_rules(assignment)

    db.session.commit()


def _add_extra_reader(assignment: EssayAssignment, teacher: Teacher, stage: Stage) -> None:
    exists = EssayAssignmentExtraReader.query.filter_by(
        assignment_id=assignment.id,
        teacher_id=teacher.id,
        stage=stage.value,
    ).first()
    if exists:
        return
    db.session.add(
        EssayAssignmentExtraReader(
            assignment=assignment,
            teacher=teacher,
            stage=stage.value,
        )
    )


def add_stage2_demo_assignments(demo_teacher: Teacher) -> int:
    candidates = (
        EssayAssignment.query.join(Student)
        .filter(
            EssayAssignment.stage == Stage.STAGE_1,
            EssayAssignment.stage_two_candidate.is_(True),
            Student.essay_language == "English",
            Student.is_absent.is_(False),
        )
        .order_by(EssayAssignment.id.asc())
        .limit(2)
        .all()
    )
    if len(candidates) < 2:
        fallback = (
            EssayAssignment.query.join(Student)
            .filter(
                EssayAssignment.stage == Stage.STAGE_1,
                Student.essay_language == "English",
                Student.is_absent.is_(False),
            )
            .order_by(EssayAssignment.id.asc())
            .limit(2)
            .all()
        )
        for assignment in fallback:
            assignment.stage_two_candidate = True
        candidates = fallback

    if not candidates:
        return 0

    support_teachers = select_support_teachers(demo_teacher, 3)
    for index, assignment in enumerate(candidates):
        assignment.stage_two_candidate = True
        _add_extra_reader(assignment, demo_teacher, Stage.STAGE_2)
        support = support_teachers[index % len(support_teachers)]
        _add_extra_reader(assignment, support, Stage.STAGE_2)
        support_record = helpers.ensure_score_record(
            assignment,
            assignment.student_id,
            support.id,
            Stage.STAGE_2,
        )
        helpers.update_score(
            support_record,
            8.0 + (index * 0.3),
            options=helpers.ScoreOptions(min_score=1, max_score=10, step=0.1, finalize=False),
            now=datetime.utcnow(),
        )
        if index == 1:
            _set_demo_score(
                assignment,
                demo_teacher,
                Stage.STAGE_2,
                score=8.5,
                comments="Stage 2 draft prepared for the webinar.",
                finalized=False,
            )
        else:
            _delete_demo_score(assignment, demo_teacher, Stage.STAGE_2)

    db.session.commit()
    return len(candidates)


def create_messages_and_survey(demo_teacher: Teacher) -> None:
    now = datetime.utcnow()
    db.session.add(
        TeacherMessage(
            title="Assessor briefing reminder",
            body=(
                "Please use the teacher portal to download assigned essays, save draft scores, "
                "and finalize only after checking the score carefully."
            ),
            priority=TeacherMessagePriority.HIGH,
            status=TeacherMessageStatus.ACTIVE,
            deliver_to_all=True,
            category="Briefing",
            creator_id=DEMO_ACTOR,
        )
    )
    db.session.add(
        TeacherMessage(
            title="Demo assessor private note",
            body="This targeted message is visible only to the demo assessor account.",
            priority=TeacherMessagePriority.NORMAL,
            status=TeacherMessageStatus.ACTIVE,
            deliver_to_all=False,
            teacher=demo_teacher,
            category="Support",
            creator_id=DEMO_ACTOR,
        )
    )

    survey = Survey(
        title="Assessor readiness check",
        description="Short demo survey used during the webinar.",
        status=SurveyStatus.PUBLISHED,
        audience=SurveyAudience.TEACHER,
        allow_edit=True,
        open_at=now - timedelta(minutes=5),
        close_at=now + timedelta(days=1),
        created_by=DEMO_ACTOR,
    )
    db.session.add(survey)
    db.session.flush()
    db.session.add_all(
        [
            SurveyQuestion(
                survey=survey,
                prompt="Are you able to access your assigned essays?",
                type=SurveyQuestionType.RADIO,
                required=True,
                options=["Yes", "No"],
                position=1,
            ),
            SurveyQuestion(
                survey=survey,
                prompt="Any issue the admin team should know before scoring opens?",
                type=SurveyQuestionType.LONG_TEXT,
                required=False,
                position=2,
            ),
        ]
    )
    db.session.add(
        SurveyAssignment(
            survey=survey,
            teacher=demo_teacher,
            status=SurveyAssignmentStatus.PENDING,
            delivery_token=secrets.token_urlsafe(16),
        )
    )
    db.session.commit()


def configure_demo_settings() -> None:
    values = {
        SETTING_TEACHER_PORTAL_ENABLED: "true",
        SETTING_UPLOAD_MODULE_ENABLED: "true",
        SETTING_UPLOAD_LOCK: "false",
        SETTING_STAGE1_LOCK: "false",
        SETTING_STAGE2_LOCK: "false",
        SETTING_REGISTRATION_INVITE_ONLY: "false",
        SETTING_EMAIL_AUTOMATION_ENABLED: "false",
        SETTING_LOGIN_EMAIL_ENABLED: "true",
        SETTING_LOGIN_FOLDED_ALIAS_ENABLED: "true",
        SETTING_PACKET_PRINT_MODE: "single",
        SETTING_ESSAY_WORD_LIMIT: "1500",
        SETTING_ESSAY_WORD_LIMIT_MODE: "soft",
        SETTING_EVENT_END_OVERRIDE: "auto",
    }
    for key, value in values.items():
        _set_setting(key, value)
    db.session.commit()


def _admin_user_summary(raw: str | dict | list | tuple | None) -> str:
    if isinstance(raw, dict):
        usernames = list(raw.keys())
    elif isinstance(raw, (list, tuple)):
        usernames = [str(item).split(":", 1)[0] for item in raw if ":" in str(item)]
    else:
        usernames = [segment.split(":", 1)[0].strip() for segment in str(raw or "").split(",") if ":" in segment]
    if not usernames:
        return "No ADMIN_USERS configured."
    return ", ".join(usernames)


def print_summary(
    *,
    app,
    args: argparse.Namespace,
    batch: AssignmentBatch,
    demo_group: ReadingGroup,
    demo_teacher: Teacher,
    demo_assignments: list[EssayAssignment],
    attendee_credentials: list[TeacherPortalCredential],
    attendee_groups: list[ReadingGroup],
    essays_processed: int,
    stage2_count: int,
) -> None:
    base_url = args.base_url.rstrip("/")
    teacher_board_password = app.config.get("TEACHER_BOARD_PASSWORD") or "<not configured>"
    print("")
    print("Assessor webinar demo state is ready.")
    print("")
    print("URLs")
    print(f"  App: {base_url}")
    print(f"  Admin: {base_url}/admin/login")
    print(f"  Teacher portal: {base_url}/teacher/login")
    print(f"  Teacher board: {base_url}/board/login")
    print("")
    print("Credentials")
    print(f"  Demo teacher: {args.demo_username} / {args.demo_password}")
    print(f"  Teacher board password: {teacher_board_password}")
    print(f"  Admin usernames from ADMIN_USERS: {_admin_user_summary(app.config.get('ADMIN_USERS'))}")
    print("  Admin password source: ADMIN_USERS environment variable.")
    if attendee_credentials:
        print("")
        print("Attendee teacher accounts")
        for credential in attendee_credentials:
            teacher_name = f"{credential.teacher.first_name} {credential.teacher.last_name}"
            print(f"  {teacher_name}: {credential.username} / {credential.password}")
        if args.attendee_credentials_file:
            print(f"  CSV: {args.attendee_credentials_file}")
    print("")
    print("Demo objects")
    print(f"  Batch: #{batch.id} {batch.name}")
    print(f"  Demo group: #{demo_group.id} {demo_group.name}")
    print(f"  Demo teacher: #{demo_teacher.id} {demo_teacher.first_name} {demo_teacher.last_name}")
    print(f"  Demo Stage 1 assignments: {len(demo_assignments)}")
    print(f"  Demo Stage 2 assignments: {stage2_count}")
    print(f"  Attendee practice accounts: {len(attendee_credentials)}")
    print(f"  Attendee practice groups: {len(attendee_groups)}")
    print(f"  Placeholder essays generated: {essays_processed}")
    print("")
    print("Suggested first teacher workflow")
    print("  1. Log in as the demo teacher.")
    print("  2. Open a Not started Stage 1 assignment, download the PDF, and save a draft score.")
    print("  3. Finalize that score and show that editing is disabled.")
    print("  4. Use the admin score page to unlock it, then show that the draft is editable again.")
    print("  5. Open the locked and awaiting-finalization assignments to explain blocked states.")
    if attendee_credentials:
        print("")
        print("Suggested hands-on account usage")
        print("  - Give attendee accounts to teachers who should try the portal during or after the webinar.")
        print("  - Keep the demo teacher account for the presenter so the staged examples stay predictable.")
        print("  - Attendee accounts start with unscored Stage 1 practice assignments.")


def write_attendee_credentials_file(
    *,
    attendee_credentials: list[TeacherPortalCredential],
    base_url: str,
    output_path: str,
) -> None:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    portal_url = f"{base_url.rstrip('/')}/teacher/login"
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["name", "username", "password", "teacher_portal_url"],
        )
        writer.writeheader()
        for credential in attendee_credentials:
            writer.writerow(
                {
                    "name": f"{credential.teacher.first_name} {credential.teacher.last_name}",
                    "username": credential.username,
                    "password": credential.password,
                    "teacher_portal_url": portal_url,
                }
            )


def validate_args(args: argparse.Namespace) -> bool:
    if args.students < 20:
        print("--students must be at least 20 for a useful planner demo.", file=sys.stderr)
        return False
    if args.attendee_teachers < 0:
        print("--attendee-teachers cannot be negative.", file=sys.stderr)
        return False
    if args.attendee_assignments_per_group < 1:
        print("--attendee-assignments-per-group must be at least 1.", file=sys.stderr)
        return False
    attendee_usernames = {
        _attendee_username(args.attendee_username_prefix, index)
        for index in range(1, args.attendee_teachers + 1)
    }
    if args.demo_username in attendee_usernames:
        print("--demo-username conflicts with a generated attendee username.", file=sys.stderr)
        return False
    return True


def main() -> int:
    args = parse_args()
    if not validate_args(args):
        return 2

    app = create_app()
    with app.app_context():
        targets = BASE_PURGE_PLAN + ((ACTIVITY_LOG_PURGE,) if args.purge_activity_logs else ())
        if _has_existing_demo_data(targets):
            if not args.yes:
                print("Existing participant/demo data detected.")
                print("Re-run with --yes to purge participant, planner, scoring, survey, invitation, and message data.")
                return 2
            purge_existing_data(
                app,
                purge_activity_logs=args.purge_activity_logs,
                delete_upload_files=not args.keep_upload_files,
            )

        seed_people(args.students, args.random_seed)
        mark_seeded_people_demo_ready()
        demo_teacher = create_demo_teacher(args.demo_username, args.demo_password)
        attendee_credentials = create_attendee_teachers(
            count=args.attendee_teachers,
            username_prefix=args.attendee_username_prefix,
            password_prefix=args.attendee_password_prefix,
        )
        configure_demo_settings()
        essays_processed = create_placeholder_essays()
        batch, demo_group, demo_assignments, attendee_groups, group_summary = create_batch_and_demo_group(
            batch_name=args.batch_name,
            demo_teacher=demo_teacher,
            attendee_credentials=attendee_credentials,
            attendee_assignments_per_group=args.attendee_assignments_per_group,
        )
        seed_stage1_scores(
            demo_teacher,
            args.random_seed,
            excluded_teacher_ids={credential.teacher.id for credential in attendee_credentials},
        )
        shape_demo_teacher_assignments(demo_teacher, demo_assignments)
        stage2_count = add_stage2_demo_assignments(demo_teacher)
        create_messages_and_survey(demo_teacher)
        if attendee_credentials and args.attendee_credentials_file:
            write_attendee_credentials_file(
                attendee_credentials=attendee_credentials,
                base_url=args.base_url,
                output_path=args.attendee_credentials_file,
            )

        print(f"Auto-generated group summary: {group_summary}")
        print_summary(
            app=app,
            args=args,
            batch=batch,
            demo_group=demo_group,
            demo_teacher=demo_teacher,
            demo_assignments=demo_assignments,
            attendee_credentials=attendee_credentials,
            attendee_groups=attendee_groups,
            essays_processed=essays_processed,
            stage2_count=stage2_count,
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
