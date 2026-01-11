import re
from datetime import date, datetime, timedelta

from werkzeug.security import check_password_hash, generate_password_hash

from ipo_app.extensions import db
from ipo_app.models import (
    AppSetting,
    PasswordResetAudience,
    PasswordResetToken,
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


def _create_student(*, email: str) -> int:
    student = Student(
        country="Testland",
        first_name="Student",
        last_name="Reset",
        email=email,
        school="Test School",
        date_of_birth=date(2000, 1, 1),
        essay_language="English",
        keyboard_preference="QWERTY",
        meal_preference="No preference",
        upload_username=f"user-{email.split('@')[0]}",
        upload_password_hash=generate_password_hash("old-password"),
        upload_token="old-token",
    )
    db.session.add(student)
    db.session.commit()
    return student.id


def _create_teacher(*, email: str) -> int:
    teacher = Teacher(
        country="Testland",
        first_name="Teacher",
        last_name="Reset",
        email=email,
        school="Test School",
        languages="English",
        meal_preference="No preference",
        tshirt_size="M",
        portal_username=f"teacher-{email.split('@')[0]}",
        portal_password_hash=generate_password_hash("old-password"),
    )
    db.session.add(teacher)
    db.session.commit()
    return teacher.id


def _extract_password_from_completed_reset(html: str) -> str:
    match = re.search(r"<li><strong>New password:</strong>\s*<code>([^<]+)</code>", html)
    assert match, "Expected new password in reset completion page"
    return match.group(1)


def test_student_reset_request_creates_token_and_invalidates_previous_tokens(client, csrf_token):
    with client.application.app_context():
        student_id = _create_student(email="student.reset@example.com")

    request_page = client.get("/participant/reset")
    token = csrf_token(request_page)

    response = client.post(
        "/participant/reset",
        data={
            "csrf_token": token,
            "email": "student.reset@example.com",
            "submit": "Send reset email",
        },
        follow_redirects=False,
    )
    assert response.status_code == 200

    with client.application.app_context():
        tokens = (
            PasswordResetToken.query
            .filter_by(audience=PasswordResetAudience.STUDENT, student_id=student_id)
            .order_by(PasswordResetToken.id.asc())
            .all()
        )
        assert len(tokens) == 1
        assert tokens[0].used_at is None

    request_page = client.get("/participant/reset")
    token = csrf_token(request_page)
    response = client.post(
        "/participant/reset",
        data={
            "csrf_token": token,
            "email": "student.reset@example.com",
            "submit": "Send reset email",
        },
        follow_redirects=False,
    )
    assert response.status_code == 200

    with client.application.app_context():
        tokens = (
            PasswordResetToken.query
            .filter_by(audience=PasswordResetAudience.STUDENT, student_id=student_id)
            .order_by(PasswordResetToken.id.asc())
            .all()
        )
        assert len(tokens) == 2
        assert tokens[0].used_at is not None
        assert tokens[1].used_at is None


def test_student_reset_token_sets_new_password_and_marks_token_used(client, csrf_token):
    with client.application.app_context():
        student_id = _create_student(email="student.reset.token@example.com")
        reset_token = PasswordResetToken(
            audience=PasswordResetAudience.STUDENT,
            student_id=student_id,
            token="student-reset-token",
            expires_at=datetime.utcnow() + timedelta(hours=1),
        )
        db.session.add(reset_token)
        db.session.commit()

    ready_page = client.get("/participant/reset/student-reset-token")
    assert ready_page.status_code == 200
    token = csrf_token(ready_page)

    response = client.post(
        "/participant/reset/student-reset-token",
        data={"csrf_token": token, "submit": "Generate new password"},
        follow_redirects=False,
    )
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "New password generated" in html

    new_password = _extract_password_from_completed_reset(html)

    with client.application.app_context():
        student = db.session.get(Student, student_id)
        assert student is not None
        assert check_password_hash(student.upload_password_hash, new_password)
        assert not check_password_hash(student.upload_password_hash, "old-password")

        token_row = PasswordResetToken.query.filter_by(token="student-reset-token").first()
        assert token_row is not None
        assert token_row.used_at is not None


def test_student_reset_token_rejects_expired_and_used_tokens(client):
    with client.application.app_context():
        student_id = _create_student(email="student.reset.invalid@example.com")

        expired = PasswordResetToken(
            audience=PasswordResetAudience.STUDENT,
            student_id=student_id,
            token="student-expired-token",
            expires_at=datetime.utcnow() - timedelta(hours=1),
        )
        used = PasswordResetToken(
            audience=PasswordResetAudience.STUDENT,
            student_id=student_id,
            token="student-used-token",
            expires_at=datetime.utcnow() + timedelta(hours=1),
            used_at=datetime.utcnow(),
        )
        db.session.add_all([expired, used])
        db.session.commit()

    expired_page = client.get("/participant/reset/student-expired-token")
    assert expired_page.status_code == 200
    assert "This reset link has expired." in expired_page.get_data(as_text=True)

    used_page = client.get("/participant/reset/student-used-token")
    assert used_page.status_code == 200
    assert "This reset link has already been used." in used_page.get_data(as_text=True)


def test_teacher_reset_token_sets_new_password_and_marks_token_used(client, csrf_token):
    with client.application.app_context():
        _set_setting("teacher_portal_enabled", "true")
        teacher_id = _create_teacher(email="teacher.reset@example.com")
        reset_token = PasswordResetToken(
            audience=PasswordResetAudience.TEACHER,
            teacher_id=teacher_id,
            token="teacher-reset-token",
            expires_at=datetime.utcnow() + timedelta(hours=1),
        )
        db.session.add(reset_token)
        db.session.commit()

    ready_page = client.get("/teacher/reset/teacher-reset-token")
    assert ready_page.status_code == 200
    token = csrf_token(ready_page)

    response = client.post(
        "/teacher/reset/teacher-reset-token",
        data={"csrf_token": token, "submit": "Generate new password"},
        follow_redirects=False,
    )
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "New password generated" in html

    new_password = _extract_password_from_completed_reset(html)

    with client.application.app_context():
        teacher = db.session.get(Teacher, teacher_id)
        assert teacher is not None
        assert check_password_hash(teacher.portal_password_hash, new_password)
        assert not check_password_hash(teacher.portal_password_hash, "old-password")

        token_row = PasswordResetToken.query.filter_by(token="teacher-reset-token").first()
        assert token_row is not None
        assert token_row.used_at is not None


def test_student_reset_request_unknown_email_does_not_generate_token(client, csrf_token):
    request_page = client.get("/participant/reset")
    token = csrf_token(request_page)

    response = client.post(
        "/participant/reset",
        data={
            "csrf_token": token,
            "email": "missing.student@example.com",
            "submit": "Send reset email",
        },
        follow_redirects=False,
    )

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "If an account exists for" in html

    with client.application.app_context():
        assert PasswordResetToken.query.count() == 0


def test_teacher_reset_request_unknown_email_does_not_generate_token(client, csrf_token):
    with client.application.app_context():
        _set_setting("teacher_portal_enabled", "true")

    request_page = client.get("/teacher/reset")
    token = csrf_token(request_page)

    response = client.post(
        "/teacher/reset",
        data={
            "csrf_token": token,
            "email": "missing.teacher@example.com",
            "submit": "Send reset email",
        },
        follow_redirects=False,
    )

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "If an account exists for" in html

    with client.application.app_context():
        assert PasswordResetToken.query.count() == 0
