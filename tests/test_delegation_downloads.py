from datetime import date, datetime
from pathlib import Path

from werkzeug.security import generate_password_hash

from ipo_app.extensions import db
from ipo_app.models import AppSetting, Student, Teacher


def _set_setting(key: str, value: str) -> None:
    existing = AppSetting.query.filter_by(key=key).first()
    if existing:
        existing.value = value
    else:
        db.session.add(AppSetting(key=key, value=value))
    db.session.commit()


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


def test_delegation_leader_download_blocked_before_event_end(client, csrf_token):
    with client.application.app_context():
        _set_setting("teacher_portal_enabled", "true")

        teacher = Teacher(
            country="Testland",
            first_name="Leader",
            last_name="One",
            email="leader.one@example.test",
            school="Test School",
            languages="English",
            meal_preference="No preference",
            tshirt_size="M",
            delegation_leader=True,
            portal_username="leader1",
            portal_password_hash=generate_password_hash("teacher-pass"),
        )
        db.session.add(teacher)

        student = Student(
            country="Testland",
            first_name="Student",
            last_name="Delegation",
            email="student.delegation@example.test",
            school="Test School",
            date_of_birth=date(2000, 1, 1),
            essay_language="English",
            keyboard_preference="QWERTY",
            meal_preference="No preference",
            uploaded_filename="student-delegation.pdf",
            uploaded_at=datetime.utcnow(),
            essay_finalized=True,
            essay_finalized_at=datetime.utcnow(),
        )
        db.session.add(student)
        db.session.commit()

        upload_folder = Path(client.application.config["UPLOAD_FOLDER"])
        (upload_folder / student.uploaded_filename).write_bytes(b"%PDF-1.4\n% delegation\n%%EOF\n")

    _login_teacher_portal(client, csrf_token, "leader1", "teacher-pass")

    response = client.get(f"/teacher/delegation/essays/{student.id}/download", follow_redirects=False)
    assert response.status_code == 302
    assert response.headers["Location"].startswith("/teacher/delegation/essays")


def test_delegation_leader_cannot_download_cross_country_essays(client, csrf_token):
    with client.application.app_context():
        _set_setting("teacher_portal_enabled", "true")
        _set_setting("event_end_override", "force_end")

        teacher = Teacher(
            country="Alpha",
            first_name="Leader",
            last_name="Cross",
            email="leader.cross@example.test",
            school="Test School",
            languages="English",
            meal_preference="No preference",
            tshirt_size="M",
            delegation_leader=True,
            portal_username="leader-cross",
            portal_password_hash=generate_password_hash("teacher-pass"),
        )
        db.session.add(teacher)

        student = Student(
            country="Beta",
            first_name="Student",
            last_name="Other",
            email="student.other@example.test",
            school="Test School",
            date_of_birth=date(2000, 1, 1),
            essay_language="English",
            keyboard_preference="QWERTY",
            meal_preference="No preference",
            uploaded_filename="student-other.pdf",
            uploaded_at=datetime.utcnow(),
            essay_finalized=True,
            essay_finalized_at=datetime.utcnow(),
        )
        db.session.add(student)
        db.session.commit()

        upload_folder = Path(client.application.config["UPLOAD_FOLDER"])
        (upload_folder / student.uploaded_filename).write_bytes(b"%PDF-1.4\n% delegation\n%%EOF\n")

    _login_teacher_portal(client, csrf_token, "leader-cross", "teacher-pass")

    response = client.get(f"/teacher/delegation/essays/{student.id}/download", follow_redirects=False)
    assert response.status_code == 404

