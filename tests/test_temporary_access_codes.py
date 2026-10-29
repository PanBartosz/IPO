from __future__ import annotations

from datetime import date, datetime
from io import BytesIO
from importlib import import_module

from pypdf import PdfReader
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations
from flask import make_response
from werkzeug.security import check_password_hash, generate_password_hash

import ipo_app.views as views
from ipo_app.extensions import db
from ipo_app.models import ActivityLog, AppSetting, AssignmentBatch, PlannerStatus, Stage, Student, Teacher


def _set_setting(key: str, value: str) -> None:
    existing = AppSetting.query.filter_by(key=key).first()
    if existing:
        existing.value = value
    else:
        db.session.add(AppSetting(key=key, value=value))
    db.session.commit()


def _login_admin(client) -> None:
    with client.session_transaction() as session:
        session["admin_user"] = "admin"


def _student(**overrides) -> Student:
    data = {
        "country": "Testland",
        "first_name": "Student",
        "last_name": "Access",
        "email": "student.access@example.test",
        "school": "Test School",
        "date_of_birth": date(2000, 1, 1),
        "essay_language": "English",
        "keyboard_preference": "QWERTY",
        "meal_preference": "No preference",
        "upload_username": "student-access",
        "upload_password_hash": generate_password_hash("student-pass"),
        "upload_token": "legacy-student-password-copy",
        "temporary_access_code": "student-code",
    }
    data.update(overrides)
    return Student(**data)


def _teacher(**overrides) -> Teacher:
    data = {
        "country": "Testland",
        "first_name": "Teacher",
        "last_name": "Access",
        "email": "teacher.access@example.test",
        "school": "Test School",
        "languages": "English",
        "meal_preference": "No preference",
        "tshirt_size": "M",
        "portal_username": "teacher-access",
        "portal_password_hash": generate_password_hash("teacher-pass"),
        "portal_token": "teacher-portal-token",
        "temporary_access_code": "teacher-code",
    }
    data.update(overrides)
    return Teacher(**data)


def _csrf(client, csrf_token) -> str:
    return csrf_token(client.get("/admin/settings"))


def test_student_regular_password_remains_valid_and_temporary_code_is_opt_in(client, csrf_token):
    with client.application.app_context():
        db.session.add(_student())
        db.session.commit()

    login_page = client.get("/participant/login")
    token = csrf_token(login_page)
    response = client.post(
        "/participant/login",
        data={
            "csrf_token": token,
            "username": "student-access",
            "password": "student-pass",
            "submit": "Sign in",
        },
        follow_redirects=False,
    )
    assert response.status_code == 302

    with client.session_transaction() as session:
        session.clear()

    login_page = client.get("/participant/login")
    token = csrf_token(login_page)
    response = client.post(
        "/participant/login",
        data={
            "csrf_token": token,
            "username": "student-access",
            "password": "student-code",
            "submit": "Sign in",
        },
        follow_redirects=False,
    )
    assert response.status_code == 200
    with client.session_transaction() as session:
        assert "student_upload_id" not in session

    with client.application.app_context():
        _set_setting(views.SETTING_STUDENT_TEMPORARY_ACCESS_LOGIN_ENABLED, "true")

    login_page = client.get("/participant/login")
    token = csrf_token(login_page)
    response = client.post(
        "/participant/login",
        data={
            "csrf_token": token,
            "username": "student-access",
            "password": "student-code",
            "submit": "Sign in",
        },
        follow_redirects=False,
    )
    assert response.status_code == 302

    with client.application.app_context():
        student = Student.query.filter_by(upload_username="student-access").one()
        assert check_password_hash(student.upload_password_hash, "student-pass")
        log = ActivityLog.query.filter_by(action="student_upload_login").order_by(ActivityLog.id.desc()).first()
        assert log is not None
        assert log.details["auth_method"] == "temporary_access_code"


def test_teacher_regular_password_remains_valid_and_temporary_code_is_opt_in(client, csrf_token):
    with client.application.app_context():
        _set_setting(views.SETTING_TEACHER_PORTAL_ENABLED, "true")
        db.session.add(_teacher())
        db.session.commit()

    login_page = client.get("/teacher/login")
    token = csrf_token(login_page)
    response = client.post(
        "/teacher/login",
        data={
            "csrf_token": token,
            "username": "teacher-access",
            "password": "teacher-pass",
            "submit": "Sign in",
        },
        follow_redirects=False,
    )
    assert response.status_code == 302

    with client.session_transaction() as session:
        session.clear()

    login_page = client.get("/teacher/login")
    token = csrf_token(login_page)
    response = client.post(
        "/teacher/login",
        data={
            "csrf_token": token,
            "username": "teacher-access",
            "password": "teacher-code",
            "submit": "Sign in",
        },
        follow_redirects=False,
    )
    assert response.status_code == 200
    with client.session_transaction() as session:
        assert "teacher_portal_id" not in session

    with client.application.app_context():
        _set_setting(views.SETTING_TEACHER_TEMPORARY_ACCESS_LOGIN_ENABLED, "true")

    login_page = client.get("/teacher/login")
    token = csrf_token(login_page)
    response = client.post(
        "/teacher/login",
        data={
            "csrf_token": token,
            "username": "teacher-access",
            "password": "teacher-code",
            "submit": "Sign in",
        },
        follow_redirects=False,
    )
    assert response.status_code == 302

    with client.application.app_context():
        teacher = Teacher.query.filter_by(portal_username="teacher-access").one()
        assert check_password_hash(teacher.portal_password_hash, "teacher-pass")
        log = ActivityLog.query.filter_by(action="teacher_portal_login").order_by(ActivityLog.id.desc()).first()
        assert log is not None
        assert log.details["auth_method"] == "temporary_access_code"


def test_card_generation_does_not_change_password_hashes_or_tokens(client, csrf_token, monkeypatch):
    _login_admin(client)

    captured: dict[str, object] = {}

    def fake_render_pdf(template_name: str, filename: str, **context):
        captured[template_name] = context
        response = make_response(b"%PDF-1.4\n")
        response.headers["Content-Type"] = "application/pdf"
        return response

    monkeypatch.setattr(views, "_render_pdf", fake_render_pdf)

    with client.application.app_context():
        _set_setting(views.SETTING_TEACHER_PORTAL_ENABLED, "true")
        _set_setting(views.SETTING_LOGIN_EMAIL_ENABLED, "true")
        _set_setting(views.SETTING_LOGIN_FOLDED_ALIAS_ENABLED, "true")
        student = _student(upload_username="żółć1")
        teacher = _teacher(portal_username="łukasz1")
        batch = AssignmentBatch(
            stage=Stage.STAGE_1,
            status=PlannerStatus.PUBLISHED,
            name="Published Stage 1",
            published_at=datetime.utcnow(),
        )
        db.session.add_all([student, teacher, batch])
        db.session.commit()
        student_id = student.id
        teacher_id = teacher.id

    assert client.get("/admin/students/cards.pdf").status_code == 200
    assert client.get("/admin/teachers/cards.pdf").status_code == 200

    with client.application.app_context():
        student = db.session.get(Student, student_id)
        teacher = db.session.get(Teacher, teacher_id)
        assert student is not None
        assert teacher is not None
        assert check_password_hash(student.upload_password_hash, "student-pass")
        assert student.upload_token == "legacy-student-password-copy"
        assert student.temporary_access_code == "student-code"
        assert check_password_hash(teacher.portal_password_hash, "teacher-pass")
        assert teacher.portal_token == "teacher-portal-token"
        assert teacher.temporary_access_code == "teacher-code"

    student_context = captured["admin/pdf/student_cards.html"]
    teacher_context = captured["admin/pdf/teacher_cards.html"]
    student_entry = student_context["students"][0]
    teacher_entry = teacher_context["teachers"][0]
    assert student_entry["temporary_access_code"] == "student-code"
    assert teacher_entry["temporary_access_code"] == "teacher-code"
    student_login_options = {option["label"]: option["value"] for option in student_entry["login_options"]}
    teacher_login_options = {option["label"]: option["value"] for option in teacher_entry["login_options"]}
    assert student_login_options == {
        "Username": "żółć1",
        "ASCII username": "zolc1",
        "Email": "student.access@example.test",
    }
    assert teacher_login_options == {
        "Username": "łukasz1",
        "ASCII username": "lukasz1",
        "Email": "teacher.access@example.test",
    }


def test_card_pdfs_render_unicode_names_with_embedded_font(client):
    _login_admin(client)

    with client.application.app_context():
        _set_setting(views.SETTING_TEACHER_PORTAL_ENABLED, "true")
        student = _student(
            first_name="Zoë",
            last_name="Działoszyńska-Γεωργίου",
            country="Česko",
            upload_username="student-unicode",
            email="student.unicode@example.test",
        )
        teacher = _teacher(
            first_name="Bartosz",
            last_name="Działoszyński-Иванов",
            country="Polska",
            portal_username="teacher-unicode",
            email="teacher.unicode@example.test",
        )
        batch = AssignmentBatch(
            stage=Stage.STAGE_1,
            status=PlannerStatus.PUBLISHED,
            name="Published Stage 1",
            published_at=datetime.utcnow(),
        )
        db.session.add_all([student, teacher, batch])
        db.session.commit()

    student_response = client.get("/admin/students/cards.pdf")
    teacher_response = client.get("/admin/teachers/cards.pdf")

    assert student_response.status_code == 200
    assert teacher_response.status_code == 200
    student_text = " ".join(
        (page.extract_text() or "")
        for page in PdfReader(BytesIO(student_response.data)).pages
    )
    teacher_text = " ".join(
        (page.extract_text() or "")
        for page in PdfReader(BytesIO(teacher_response.data)).pages
    )
    assert "Zoë Działoszyńska-" in student_text
    assert "Γεωργίου" in student_text
    assert "Česko" in student_text
    assert "Bartosz Działoszyński-" in teacher_text
    assert "Иванов" in teacher_text
    assert "Polska" in teacher_text


def test_compact_access_table_pdfs_render_card_credentials(client):
    _login_admin(client)

    with client.application.app_context():
        _set_setting(views.SETTING_TEACHER_PORTAL_ENABLED, "true")
        _set_setting(views.SETTING_LOGIN_EMAIL_ENABLED, "true")
        _set_setting(views.SETTING_LOGIN_FOLDED_ALIAS_ENABLED, "true")
        db.session.add(
            _student(
                first_name="Zoë",
                last_name="Działoszyńska",
                country="Česko",
                upload_username="żółć1",
                email="student.table@example.test",
                temporary_access_code="student-table-code",
            )
        )
        db.session.add(
            _teacher(
                first_name="Łukasz",
                last_name="Kowalski",
                country="Polska",
                portal_username="łukasz1",
                email="teacher.table@example.test",
                temporary_access_code="teacher-table-code",
            )
        )
        db.session.commit()

    exports_html = client.get("/admin/exports").get_data(as_text=True)
    students_html = client.get("/admin/students").get_data(as_text=True)
    teachers_html = client.get("/admin/teachers").get_data(as_text=True)
    assert "/admin/students/access-table.pdf" in exports_html
    assert "/admin/teachers/access-table.pdf" in exports_html
    assert "/admin/students/access-table.pdf" in students_html
    assert "/admin/teachers/access-table.pdf" in teachers_html

    student_response = client.get("/admin/students/access-table.pdf")
    teacher_response = client.get("/admin/teachers/access-table.pdf")
    assert student_response.status_code == 200
    assert teacher_response.status_code == 200
    assert "application/pdf" in student_response.headers.get("Content-Type", "")
    assert "application/pdf" in teacher_response.headers.get("Content-Type", "")

    student_text = " ".join(
        (page.extract_text() or "")
        for page in PdfReader(BytesIO(student_response.data)).pages
    )
    teacher_text = " ".join(
        (page.extract_text() or "")
        for page in PdfReader(BytesIO(teacher_response.data)).pages
    )
    assert "Zoë Działoszyńska" in student_text
    assert "Česko" in student_text
    assert "żółć1" in student_text
    assert "zolc1" in student_text
    assert "student.table@example.test" in student_text
    assert "student-table-code" in student_text
    assert "Łukasz Kowalski" in teacher_text
    assert "Polska" in teacher_text
    assert "łukasz1" in teacher_text
    assert "lukasz1" in teacher_text
    assert "teacher.table@example.test" in teacher_text
    assert "teacher-table-code" in teacher_text


def test_rotating_temporary_codes_preserves_password_hashes_and_regular_tokens(client, csrf_token, monkeypatch):
    _login_admin(client)
    generated_codes = iter(["new-student-code", "new-teacher-code"])
    monkeypatch.setattr(views.secrets, "token_urlsafe", lambda _size: next(generated_codes))
    with client.application.app_context():
        student = _student()
        teacher = _teacher()
        db.session.add_all([student, teacher])
        db.session.commit()
        student_id = student.id
        teacher_id = teacher.id

    token = _csrf(client, csrf_token)
    response = client.post(
        "/admin/settings/temporary-access-codes",
        data={
            "csrf_token": token,
            "action": "rotate",
            "audience": "students",
            "confirm_rotation": "yes",
        },
        follow_redirects=False,
    )
    assert response.status_code == 302

    token = _csrf(client, csrf_token)
    response = client.post(
        "/admin/settings/temporary-access-codes",
        data={
            "csrf_token": token,
            "action": "rotate",
            "audience": "teachers",
            "confirm_rotation": "yes",
        },
        follow_redirects=False,
    )
    assert response.status_code == 302

    with client.application.app_context():
        student = db.session.get(Student, student_id)
        teacher = db.session.get(Teacher, teacher_id)
        assert student is not None
        assert teacher is not None
        assert student.temporary_access_code != "student-code"
        assert teacher.temporary_access_code != "teacher-code"
        assert check_password_hash(student.upload_password_hash, "student-pass")
        assert student.upload_token == "legacy-student-password-copy"
        assert check_password_hash(teacher.portal_password_hash, "teacher-pass")
        assert teacher.portal_token == "teacher-portal-token"


def test_temporary_access_code_migration_preserves_existing_password_columns(tmp_path, monkeypatch):
    migration = import_module("migrations.versions.a2b4c6d8e0f1_add_temporary_access_codes")
    generated_codes = iter(["migration-student-1", "migration-student-2", "migration-teacher-1", "migration-teacher-2"])
    monkeypatch.setattr(migration.secrets, "token_urlsafe", lambda _size: next(generated_codes))
    engine = sa.create_engine(f"sqlite:///{tmp_path / 'migration.db'}")
    metadata = sa.MetaData()
    students = sa.Table(
        "students",
        metadata,
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("upload_password_hash", sa.String(255)),
        sa.Column("upload_token", sa.String(64)),
    )
    teachers = sa.Table(
        "teachers",
        metadata,
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("portal_password_hash", sa.String(255)),
        sa.Column("portal_token", sa.String(64)),
    )
    with engine.begin() as connection:
        metadata.create_all(connection)
        connection.execute(
            students.insert(),
            [
                {"id": 1, "upload_password_hash": "student-hash-1", "upload_token": "student-password-1"},
                {"id": 2, "upload_password_hash": "student-hash-2", "upload_token": "student-password-2"},
            ],
        )
        connection.execute(
            teachers.insert(),
            [
                {"id": 1, "portal_password_hash": "teacher-hash-1", "portal_token": "teacher-token-1"},
                {"id": 2, "portal_password_hash": "teacher-hash-2", "portal_token": "teacher-token-2"},
            ],
        )

    with engine.begin() as connection:
        context = MigrationContext.configure(connection)
        monkeypatch.setattr(migration, "op", Operations(context))
        migration.upgrade()

        student_rows = connection.execute(
            sa.text("SELECT id, upload_password_hash, upload_token, temporary_access_code FROM students ORDER BY id")
        ).mappings().all()
        teacher_rows = connection.execute(
            sa.text("SELECT id, portal_password_hash, portal_token, temporary_access_code FROM teachers ORDER BY id")
        ).mappings().all()

    assert [row["upload_password_hash"] for row in student_rows] == ["student-hash-1", "student-hash-2"]
    assert [row["upload_token"] for row in student_rows] == ["student-password-1", "student-password-2"]
    assert [row["portal_password_hash"] for row in teacher_rows] == ["teacher-hash-1", "teacher-hash-2"]
    assert [row["portal_token"] for row in teacher_rows] == ["teacher-token-1", "teacher-token-2"]

    student_codes = {row["temporary_access_code"] for row in student_rows}
    teacher_codes = {row["temporary_access_code"] for row in teacher_rows}
    assert len(student_codes) == 2
    assert len(teacher_codes) == 2
    assert None not in student_codes
    assert None not in teacher_codes
    assert student_codes.isdisjoint({"student-password-1", "student-password-2"})
