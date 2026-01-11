from datetime import date, datetime
from pathlib import Path

import pytest
from werkzeug.security import generate_password_hash

from ipo_app.extensions import db
from ipo_app.models import (
    AppSetting,
    AssignmentBatch,
    EssayAssignment,
    EssayScore,
    GroupMemberRole,
    PlannerStatus,
    ReadingGroup,
    ReadingGroupMember,
    Stage,
    Student,
    Teacher,
)


def _set_setting(key: str, value: str) -> None:
    existing = AppSetting.query.filter_by(key=key).first()
    if existing:
        existing.value = value
    else:
        db.session.add(AppSetting(key=key, value=value))
    db.session.commit()


def _create_teacher(*, username: str, password: str, country: str = "Testland") -> int:
    teacher = Teacher(
        country=country,
        first_name="Teacher",
        last_name=username,
        email=f"{username}@example.test",
        school="Test School",
        languages="English",
        meal_preference="No preference",
        tshirt_size="M",
        delegation_leader=False,
        portal_username=username,
        portal_password_hash=generate_password_hash(password),
    )
    db.session.add(teacher)
    db.session.commit()
    return teacher.id


def _create_student(*, label: str, country: str = "Testland") -> int:
    student = Student(
        country=country,
        first_name="Student",
        last_name=label,
        email=f"{label}@example.test",
        school="Test School",
        date_of_birth=date(2000, 1, 1),
        essay_language="English",
        keyboard_preference="QWERTY",
        meal_preference="No preference",
    )
    db.session.add(student)
    db.session.commit()
    return student.id


def _create_stage1_assignment(*, teacher_id: int, student_id: int) -> int:
    batch = AssignmentBatch(name="Batch 1", stage=Stage.STAGE_1, status=PlannerStatus.PUBLISHED)
    db.session.add(batch)
    db.session.flush()

    group = ReadingGroup(name="Group 1", stage=Stage.STAGE_1, language="English", batch_id=batch.id)
    db.session.add(group)
    db.session.flush()

    db.session.add(
        ReadingGroupMember(
            group_id=group.id,
            teacher_id=teacher_id,
            role=GroupMemberRole.READER,
            active=True,
        )
    )

    assignment = EssayAssignment(
        student_id=student_id,
        group_id=group.id,
        batch_id=batch.id,
        stage=Stage.STAGE_1,
    )
    db.session.add(assignment)
    db.session.commit()
    return assignment.id


def _login_teacher_portal(client, csrf_token, username: str, password: str) -> None:
    login_page = client.get("/teacher/login")
    token = csrf_token(login_page)
    response = client.post(
        "/teacher/login",
        data={
            "csrf_token": token,
            "username": username,
            "password": password,
            "submit": "Sign in",
        },
        follow_redirects=False,
    )
    assert response.status_code == 302


def test_teacher_sees_only_assigned_essays_on_dashboard(client, csrf_token):
    with client.application.app_context():
        _set_setting("teacher_portal_enabled", "true")
        teacher_a_id = _create_teacher(username="teacher-a", password="pass-a")
        teacher_b_id = _create_teacher(username="teacher-b", password="pass-b")

        student_a_id = _create_student(label="student-a")
        student_b_id = _create_student(label="student-b")

        _create_stage1_assignment(teacher_id=teacher_a_id, student_id=student_a_id)
        _create_stage1_assignment(teacher_id=teacher_b_id, student_id=student_b_id)

        expected_label = f"Essay {student_a_id}"
        unexpected_label = f"Essay {student_b_id}"

    _login_teacher_portal(client, csrf_token, "teacher-a", "pass-a")

    dashboard = client.get("/teacher/")
    assert dashboard.status_code == 200

    html = dashboard.get_data(as_text=True)
    assert expected_label in html
    assert unexpected_label not in html


def test_teacher_cannot_download_assignment_until_student_finalizes(client, csrf_token):
    with client.application.app_context():
        _set_setting("teacher_portal_enabled", "true")
        teacher_id = _create_teacher(username="teacher-download", password="teacher-pass")
        student_id = _create_student(label="student-download")
        student = db.session.get(Student, student_id)
        assert student is not None
        student.uploaded_filename = f"student-{student_id}-assignment.pdf"
        student.uploaded_at = datetime.utcnow()
        student.essay_finalized = False
        db.session.commit()

        upload_folder = Path(client.application.config["UPLOAD_FOLDER"])
        (upload_folder / student.uploaded_filename).write_bytes(b"%PDF-1.4\n% assignment\n%%EOF\n")

        assignment_id = _create_stage1_assignment(teacher_id=teacher_id, student_id=student_id)

    _login_teacher_portal(client, csrf_token, "teacher-download", "teacher-pass")

    response = client.get(f"/teacher/assignments/{assignment_id}/stage_1/download", follow_redirects=False)
    assert response.status_code == 302
    assert response.headers["Location"] == f"/teacher/assignments/{assignment_id}/stage_1"


def test_teacher_score_draft_save_persists_score_and_comments(client, csrf_token):
    with client.application.app_context():
        _set_setting("teacher_portal_enabled", "true")
        teacher_id = _create_teacher(username="teacher-draft", password="teacher-pass")
        student_id = _create_student(label="student-draft")
        student = db.session.get(Student, student_id)
        assert student is not None
        student.uploaded_filename = f"student-{student_id}-draft.pdf"
        student.uploaded_at = datetime.utcnow()
        student.essay_finalized = True
        student.essay_finalized_at = datetime.utcnow()
        db.session.commit()

        upload_folder = Path(client.application.config["UPLOAD_FOLDER"])
        (upload_folder / student.uploaded_filename).write_bytes(b"%PDF-1.4\n% draft\n%%EOF\n")

        assignment_id = _create_stage1_assignment(teacher_id=teacher_id, student_id=student_id)

    _login_teacher_portal(client, csrf_token, "teacher-draft", "teacher-pass")

    detail_page = client.get(f"/teacher/assignments/{assignment_id}/stage_1")
    token = csrf_token(detail_page)

    response = client.post(
        f"/teacher/assignments/{assignment_id}/stage_1",
        data={
            "csrf_token": token,
            "score": "7.50",
            "comments": "Solid essay.",
            "save": "Save draft",
        },
        follow_redirects=False,
    )
    assert response.status_code == 302
    assert response.headers["Location"] == f"/teacher/assignments/{assignment_id}/stage_1"

    with client.application.app_context():
        score = (
            EssayScore.query
            .filter_by(assignment_id=assignment_id, teacher_id=teacher_id, stage=Stage.STAGE_1)
            .first()
        )
        assert score is not None
        assert score.score == pytest.approx(7.5)
        assert score.comments == "Solid essay."
        assert score.teacher_finalized is False
        assert score.teacher_finalized_at is None
        assert score.submitted_at is not None


def test_teacher_score_finalization_sets_teacher_finalized_and_timestamp(client, csrf_token):
    with client.application.app_context():
        _set_setting("teacher_portal_enabled", "true")
        teacher_id = _create_teacher(username="teacher-finalize", password="teacher-pass")
        student_id = _create_student(label="student-finalize")
        student = db.session.get(Student, student_id)
        assert student is not None
        student.uploaded_filename = f"student-{student_id}-finalize.pdf"
        student.uploaded_at = datetime.utcnow()
        student.essay_finalized = True
        student.essay_finalized_at = datetime.utcnow()
        db.session.commit()

        upload_folder = Path(client.application.config["UPLOAD_FOLDER"])
        (upload_folder / student.uploaded_filename).write_bytes(b"%PDF-1.4\n% finalize\n%%EOF\n")

        assignment_id = _create_stage1_assignment(teacher_id=teacher_id, student_id=student_id)

    _login_teacher_portal(client, csrf_token, "teacher-finalize", "teacher-pass")

    detail_page = client.get(f"/teacher/assignments/{assignment_id}/stage_1")
    token = csrf_token(detail_page)

    response = client.post(
        f"/teacher/assignments/{assignment_id}/stage_1",
        data={
            "csrf_token": token,
            "score": "8.00",
            "comments": "Final score.",
            "finalize": "Finalize score",
        },
        follow_redirects=False,
    )
    assert response.status_code == 302
    assert response.headers["Location"] == f"/teacher/assignments/{assignment_id}/stage_1"

    with client.application.app_context():
        score = (
            EssayScore.query
            .filter_by(assignment_id=assignment_id, teacher_id=teacher_id, stage=Stage.STAGE_1)
            .first()
        )
        assert score is not None
        assert score.score == pytest.approx(8.0)
        assert score.comments == "Final score."
        assert score.teacher_finalized is True
        assert score.teacher_finalized_at is not None


def test_stage_lock_blocks_teacher_downloads_and_score_edits(client, csrf_token):
    with client.application.app_context():
        _set_setting("teacher_portal_enabled", "true")
        _set_setting("grading_stage1_locked", "true")
        teacher_id = _create_teacher(username="teacher-lock", password="teacher-pass")
        student_id = _create_student(label="student-lock")
        student = db.session.get(Student, student_id)
        assert student is not None
        student.uploaded_filename = f"student-{student_id}-lock.pdf"
        student.uploaded_at = datetime.utcnow()
        student.essay_finalized = True
        student.essay_finalized_at = datetime.utcnow()
        db.session.commit()

        upload_folder = Path(client.application.config["UPLOAD_FOLDER"])
        (upload_folder / student.uploaded_filename).write_bytes(b"%PDF-1.4\n% locked\n%%EOF\n")

        assignment_id = _create_stage1_assignment(teacher_id=teacher_id, student_id=student_id)

    _login_teacher_portal(client, csrf_token, "teacher-lock", "teacher-pass")

    download = client.get(f"/teacher/assignments/{assignment_id}/stage_1/download", follow_redirects=False)
    assert download.status_code == 302
    assert download.headers["Location"] == f"/teacher/assignments/{assignment_id}/stage_1"

    detail_page = client.get(f"/teacher/assignments/{assignment_id}/stage_1")
    token = csrf_token(detail_page)

    post = client.post(
        f"/teacher/assignments/{assignment_id}/stage_1",
        data={
            "csrf_token": token,
            "score": "6.00",
            "comments": "Should not save while locked.",
            "save": "Save draft",
        },
        follow_redirects=False,
    )
    assert post.status_code == 302
    assert post.headers["Location"] == f"/teacher/assignments/{assignment_id}/stage_1"

    with client.application.app_context():
        assert (
            EssayScore.query
            .filter_by(assignment_id=assignment_id, teacher_id=teacher_id, stage=Stage.STAGE_1)
            .all()
            == []
        )


def test_unassigned_teacher_cannot_access_assignment_detail_or_download(client, csrf_token):
    with client.application.app_context():
        _set_setting("teacher_portal_enabled", "true")
        teacher_assigned_id = _create_teacher(username="teacher-assigned", password="pass-a")
        teacher_other_id = _create_teacher(username="teacher-other", password="pass-b")
        student_id = _create_student(label="student-authz")
        assignment_id = _create_stage1_assignment(teacher_id=teacher_assigned_id, student_id=student_id)

    _login_teacher_portal(client, csrf_token, "teacher-other", "pass-b")

    response = client.get(f"/teacher/assignments/{assignment_id}/stage_1", follow_redirects=False)
    assert response.status_code == 403

    response = client.get(f"/teacher/assignments/{assignment_id}/stage_1/download", follow_redirects=False)
    assert response.status_code == 403
