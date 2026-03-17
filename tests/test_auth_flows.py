from datetime import date
from urllib.parse import parse_qs, urlparse

from werkzeug.security import generate_password_hash

import ipo_app.views as views
from ipo_app.extensions import db
from ipo_app.models import ActivityLog, AppSetting, Student, Teacher


def _set_setting(key: str, value: str) -> None:
    existing = AppSetting.query.filter_by(key=key).first()
    if existing:
        existing.value = value
    else:
        db.session.add(AppSetting(key=key, value=value))
    db.session.commit()


def test_admin_login_allows_access_to_admin_dashboard(client, csrf_token):
    login_page = client.get("/admin/login")
    token = csrf_token(login_page)

    response = client.post(
        "/admin/login",
        data={
            "csrf_token": token,
            "username": "admin",
            "password": "test-password",
            "submit": "Sign in",
        },
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert response.headers["Location"].startswith("/admin")

    dashboard = client.get("/admin")
    assert dashboard.status_code == 200


def test_admin_login_redirects_when_already_authenticated(client):
    with client.session_transaction() as session:
        session["admin_user"] = "admin"

    response = client.get("/admin/login", follow_redirects=False)

    assert response.status_code == 302
    assert response.headers["Location"].startswith("/admin")


def test_admin_logout_clears_session_and_redirects_to_login(client):
    with client.session_transaction() as session:
        session["admin_user"] = "admin"

    response = client.get("/admin/logout", follow_redirects=False)

    assert response.status_code == 302
    assert response.headers["Location"].startswith("/admin/login")

    with client.session_transaction() as session:
        assert "admin_user" not in session


def test_admin_login_invalid_credentials_do_not_create_session(client, csrf_token):
    login_page = client.get("/admin/login")
    token = csrf_token(login_page)

    response = client.post(
        "/admin/login",
        data={
            "csrf_token": token,
            "username": "admin",
            "password": "wrong-password",
            "submit": "Sign in",
        },
        follow_redirects=False,
    )

    assert response.status_code == 200
    with client.session_transaction() as session:
        assert "admin_user" not in session


def test_admin_login_rejects_open_redirect_next(client, csrf_token):
    login_page = client.get("/admin/login?next=https://evil.example")
    token = csrf_token(login_page)

    response = client.post(
        "/admin/login?next=https://evil.example",
        data={
            "csrf_token": token,
            "username": "admin",
            "password": "test-password",
            "submit": "Sign in",
        },
        follow_redirects=False,
    )

    assert response.status_code == 302
    location = response.headers["Location"]
    assert location.startswith("/admin")
    assert "evil.example" not in location


def test_admin_routes_require_authentication_redirects_to_login(client):
    response = client.get("/admin/settings", follow_redirects=False)
    assert response.status_code == 302
    assert "/admin/login" in response.headers["Location"]


def test_student_login_allows_access_to_portal(client, csrf_token):
    with client.application.app_context():
        student = Student(
            country="Testland",
            first_name="Student",
            last_name="One",
            email="student.one@example.test",
            school="Test School",
            date_of_birth=date(2000, 1, 1),
            essay_language="English",
            keyboard_preference="QWERTY",
            meal_preference="No preference",
            upload_username="student1",
            upload_password_hash=generate_password_hash("student-pass"),
        )
        db.session.add(student)
        db.session.commit()

    login_page = client.get("/participant/login")
    token = csrf_token(login_page)

    response = client.post(
        "/participant/login",
        data={
            "csrf_token": token,
            "username": "student1",
            "password": "student-pass",
            "submit": "Sign in",
        },
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert response.headers["Location"].startswith("/participant/portal")

    portal = client.get("/participant/portal")
    assert portal.status_code == 200


def test_student_login_invalid_credentials_do_not_create_session(client, csrf_token):
    with client.application.app_context():
        student = Student(
            country="Testland",
            first_name="Student",
            last_name="BadLogin",
            email="student.badlogin@example.test",
            school="Test School",
            date_of_birth=date(2000, 1, 1),
            essay_language="English",
            keyboard_preference="QWERTY",
            meal_preference="No preference",
            upload_username="student-bad",
            upload_password_hash=generate_password_hash("student-pass"),
        )
        db.session.add(student)
        db.session.commit()

    login_page = client.get("/participant/login")
    token = csrf_token(login_page)

    response = client.post(
        "/participant/login",
        data={
            "csrf_token": token,
            "username": "student-bad",
            "password": "wrong-password",
            "submit": "Sign in",
        },
        follow_redirects=False,
    )

    assert response.status_code == 200
    with client.session_transaction() as session:
        assert "student_upload_id" not in session


def test_student_login_rejects_open_redirect_next(client, csrf_token):
    with client.application.app_context():
        student = Student(
            country="Testland",
            first_name="Student",
            last_name="Redirect",
            email="student.redirect@example.test",
            school="Test School",
            date_of_birth=date(2000, 1, 1),
            essay_language="English",
            keyboard_preference="QWERTY",
            meal_preference="No preference",
            upload_username="student-redirect",
            upload_password_hash=generate_password_hash("student-pass"),
        )
        db.session.add(student)
        db.session.commit()

    login_page = client.get("/participant/login?next=https://evil.example")
    token = csrf_token(login_page)

    response = client.post(
        "/participant/login?next=https://evil.example",
        data={
            "csrf_token": token,
            "username": "student-redirect",
            "password": "student-pass",
            "submit": "Sign in",
        },
        follow_redirects=False,
    )

    assert response.status_code == 302
    location = response.headers["Location"]
    assert location.startswith("/participant/portal")
    assert "evil.example" not in location


def test_student_portal_requires_authentication(client):
    response = client.get("/participant/portal", follow_redirects=False)
    assert response.status_code == 302
    assert response.headers["Location"].startswith("/participant/login")


def test_student_portal_redirect_preserves_next_parameter(client):
    response = client.get("/participant/portal?foo=bar", follow_redirects=False)

    assert response.status_code == 302
    location = response.headers["Location"]
    parsed = urlparse(location)
    assert parsed.path == "/participant/login"
    query = parse_qs(parsed.query)
    assert query.get("next") == ["/participant/portal?foo=bar"]


def test_student_login_allows_folded_alias_when_enabled(client, csrf_token):
    with client.application.app_context():
        _set_setting(views.SETTING_LOGIN_FOLDED_ALIAS_ENABLED, "true")
        student = Student(
            country="Testland",
            first_name="Student",
            last_name="Alias",
            email="student.alias@example.test",
            school="Test School",
            date_of_birth=date(2000, 1, 1),
            essay_language="English",
            keyboard_preference="QWERTY",
            meal_preference="No preference",
            upload_username="żółć1",
            upload_password_hash=generate_password_hash("student-pass"),
        )
        db.session.add(student)
        db.session.commit()

    login_page = client.get("/participant/login")
    token = csrf_token(login_page)

    response = client.post(
        "/participant/login",
        data={
            "csrf_token": token,
            "username": "zolc1",
            "password": "student-pass",
            "submit": "Sign in",
        },
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert response.headers["Location"].startswith("/participant/portal")

    with client.application.app_context():
        log = ActivityLog.query.filter_by(action="student_upload_login").order_by(ActivityLog.id.desc()).first()
        assert log is not None
        assert log.details["username"] == "żółć1"
        assert log.details["submitted_username"] == "zolc1"
        assert log.details["login_match_type"] == "folded"


def test_student_login_rejects_folded_alias_when_disabled(client, csrf_token):
    with client.application.app_context():
        student = Student(
            country="Testland",
            first_name="Student",
            last_name="AliasDisabled",
            email="student.alias.disabled@example.test",
            school="Test School",
            date_of_birth=date(2000, 1, 1),
            essay_language="English",
            keyboard_preference="QWERTY",
            meal_preference="No preference",
            upload_username="żółć1",
            upload_password_hash=generate_password_hash("student-pass"),
        )
        db.session.add(student)
        db.session.commit()

    login_page = client.get("/participant/login")
    token = csrf_token(login_page)

    response = client.post(
        "/participant/login",
        data={
            "csrf_token": token,
            "username": "zolc1",
            "password": "student-pass",
            "submit": "Sign in",
        },
        follow_redirects=False,
    )

    assert response.status_code == 200
    with client.session_transaction() as session:
        assert "student_upload_id" not in session


def test_student_login_rejects_ambiguous_folded_alias(client, csrf_token):
    with client.application.app_context():
        _set_setting(views.SETTING_LOGIN_FOLDED_ALIAS_ENABLED, "true")
        db.session.add(
            Student(
                country="Testland",
                first_name="Student",
                last_name="AliasOne",
                email="student.alias.one@example.test",
                school="Test School",
                date_of_birth=date(2000, 1, 1),
                essay_language="English",
                keyboard_preference="QWERTY",
                meal_preference="No preference",
                upload_username="żuk1",
                upload_password_hash=generate_password_hash("student-pass"),
            )
        )
        db.session.add(
            Student(
                country="Testland",
                first_name="Student",
                last_name="AliasTwo",
                email="student.alias.two@example.test",
                school="Test School",
                date_of_birth=date(2000, 1, 2),
                essay_language="English",
                keyboard_preference="QWERTY",
                meal_preference="No preference",
                upload_username="źuk1",
                upload_password_hash=generate_password_hash("student-pass"),
            )
        )
        db.session.commit()

    login_page = client.get("/participant/login")
    token = csrf_token(login_page)

    response = client.post(
        "/participant/login",
        data={
            "csrf_token": token,
            "username": "zuk1",
            "password": "student-pass",
            "submit": "Sign in",
        },
        follow_redirects=False,
    )

    assert response.status_code == 200
    with client.session_transaction() as session:
        assert "student_upload_id" not in session

    with client.application.app_context():
        log = ActivityLog.query.filter_by(action="student_upload_login_ambiguous").order_by(ActivityLog.id.desc()).first()
        assert log is not None
        assert log.details["submitted_username"] == "zuk1"
        assert log.details["folded_username"] == "zuk1"
        assert log.details["match_count"] == 2


def test_teacher_portal_login_rejects_open_redirect_next(client, csrf_token):
    with client.application.app_context():
        _set_setting("teacher_portal_enabled", "true")
        teacher = Teacher(
            country="Testland",
            first_name="Teacher",
            last_name="One",
            email="teacher.one@example.test",
            school="Test School",
            languages="English",
            meal_preference="No preference",
            tshirt_size="M",
            portal_username="teacher1",
            portal_password_hash=generate_password_hash("teacher-pass"),
        )
        db.session.add(teacher)
        db.session.commit()

    login_page = client.get("/teacher/login?next=//evil.example")
    token = csrf_token(login_page)

    response = client.post(
        "/teacher/login?next=//evil.example",
        data={
            "csrf_token": token,
            "username": "teacher1",
            "password": "teacher-pass",
            "submit": "Sign in",
        },
        follow_redirects=False,
    )

    assert response.status_code == 302
    location = response.headers["Location"]
    assert location.startswith("/teacher")
    assert not location.startswith("//")
    assert "evil.example" not in location

    dashboard = client.get("/teacher/")
    assert dashboard.status_code == 200


def test_teacher_portal_login_rejects_crlf_next(client, csrf_token):
    with client.application.app_context():
        _set_setting("teacher_portal_enabled", "true")
        teacher = Teacher(
            country="Testland",
            first_name="Teacher",
            last_name="CRLF",
            email="teacher.crlf@example.test",
            school="Test School",
            languages="English",
            meal_preference="No preference",
            tshirt_size="M",
            portal_username="teacher-crlf",
            portal_password_hash=generate_password_hash("teacher-pass"),
        )
        db.session.add(teacher)
        db.session.commit()

    login_page = client.get("/teacher/login?next=%2Fteacher%2F%0D%0Aevil")
    token = csrf_token(login_page)

    response = client.post(
        "/teacher/login?next=%2Fteacher%2F%0D%0Aevil",
        data={
            "csrf_token": token,
            "username": "teacher-crlf",
            "password": "teacher-pass",
            "submit": "Sign in",
        },
        follow_redirects=False,
    )

    assert response.status_code == 302
    location = response.headers["Location"]
    assert location.startswith("/teacher")
    assert "evil" not in location


def test_teacher_portal_disabled_redirects_to_board_login(client):
    response = client.get("/teacher/login", follow_redirects=False)

    assert response.status_code == 302
    assert response.headers["Location"].startswith("/board/login")


def test_teacher_portal_login_accepts_safe_next(client, csrf_token):
    with client.application.app_context():
        _set_setting("teacher_portal_enabled", "true")
        teacher = Teacher(
            country="Testland",
            first_name="Teacher",
            last_name="Next",
            email="teacher.next@example.test",
            school="Test School",
            languages="English",
            meal_preference="No preference",
            tshirt_size="M",
            portal_username="teacher-next",
            portal_password_hash=generate_password_hash("teacher-pass"),
        )
        db.session.add(teacher)
        db.session.commit()

    login_page = client.get("/teacher/login?next=/teacher/surveys")
    token = csrf_token(login_page)

    response = client.post(
        "/teacher/login?next=/teacher/surveys",
        data={
            "csrf_token": token,
            "username": "teacher-next",
            "password": "teacher-pass",
            "submit": "Sign in",
            "next": "/teacher/surveys",
        },
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert response.headers["Location"] == "/teacher/surveys"

    surveys = client.get("/teacher/surveys")
    assert surveys.status_code == 200


def test_teacher_portal_login_invalid_credentials_do_not_create_session(client, csrf_token):
    with client.application.app_context():
        _set_setting("teacher_portal_enabled", "true")
        teacher = Teacher(
            country="Testland",
            first_name="Teacher",
            last_name="BadLogin",
            email="teacher.badlogin@example.test",
            school="Test School",
            languages="English",
            meal_preference="No preference",
            tshirt_size="M",
            portal_username="teacher-bad",
            portal_password_hash=generate_password_hash("teacher-pass"),
        )
        db.session.add(teacher)
        db.session.commit()

    login_page = client.get("/teacher/login")
    token = csrf_token(login_page)

    response = client.post(
        "/teacher/login",
        data={
            "csrf_token": token,
            "username": "teacher-bad",
            "password": "wrong-password",
            "submit": "Sign in",
        },
        follow_redirects=False,
    )

    assert response.status_code == 200
    with client.session_transaction() as session:
        assert "teacher_portal_id" not in session


def test_teacher_portal_login_allows_folded_alias_when_enabled(client, csrf_token):
    with client.application.app_context():
        _set_setting("teacher_portal_enabled", "true")
        _set_setting(views.SETTING_LOGIN_FOLDED_ALIAS_ENABLED, "true")
        teacher = Teacher(
            country="Testland",
            first_name="Teacher",
            last_name="Alias",
            email="teacher.alias@example.test",
            school="Test School",
            languages="English",
            meal_preference="No preference",
            tshirt_size="M",
            portal_username="łukasz1",
            portal_password_hash=generate_password_hash("teacher-pass"),
        )
        db.session.add(teacher)
        db.session.commit()

    login_page = client.get("/teacher/login")
    token = csrf_token(login_page)

    response = client.post(
        "/teacher/login",
        data={
            "csrf_token": token,
            "username": "lukasz1",
            "password": "teacher-pass",
            "submit": "Sign in",
        },
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert response.headers["Location"].startswith("/teacher")

    with client.application.app_context():
        log = ActivityLog.query.filter_by(action="teacher_portal_login").order_by(ActivityLog.id.desc()).first()
        assert log is not None
        assert log.details["username"] == "łukasz1"
        assert log.details["submitted_username"] == "lukasz1"
        assert log.details["login_match_type"] == "folded"


def test_teacher_portal_login_rejects_folded_alias_when_disabled(client, csrf_token):
    with client.application.app_context():
        _set_setting("teacher_portal_enabled", "true")
        teacher = Teacher(
            country="Testland",
            first_name="Teacher",
            last_name="AliasDisabled",
            email="teacher.alias.disabled@example.test",
            school="Test School",
            languages="English",
            meal_preference="No preference",
            tshirt_size="M",
            portal_username="łukasz1",
            portal_password_hash=generate_password_hash("teacher-pass"),
        )
        db.session.add(teacher)
        db.session.commit()

    login_page = client.get("/teacher/login")
    token = csrf_token(login_page)

    response = client.post(
        "/teacher/login",
        data={
            "csrf_token": token,
            "username": "lukasz1",
            "password": "teacher-pass",
            "submit": "Sign in",
        },
        follow_redirects=False,
    )

    assert response.status_code == 200
    with client.session_transaction() as session:
        assert "teacher_portal_id" not in session


def test_teacher_portal_login_rejects_ambiguous_folded_alias(client, csrf_token):
    with client.application.app_context():
        _set_setting("teacher_portal_enabled", "true")
        _set_setting(views.SETTING_LOGIN_FOLDED_ALIAS_ENABLED, "true")
        db.session.add(
            Teacher(
                country="Testland",
                first_name="Teacher",
                last_name="AliasOne",
                email="teacher.alias.one@example.test",
                school="Test School",
                languages="English",
                meal_preference="No preference",
                tshirt_size="M",
                portal_username="żuk1",
                portal_password_hash=generate_password_hash("teacher-pass"),
            )
        )
        db.session.add(
            Teacher(
                country="Testland",
                first_name="Teacher",
                last_name="AliasTwo",
                email="teacher.alias.two@example.test",
                school="Test School",
                languages="English",
                meal_preference="No preference",
                tshirt_size="M",
                portal_username="źuk1",
                portal_password_hash=generate_password_hash("teacher-pass"),
            )
        )
        db.session.commit()

    login_page = client.get("/teacher/login")
    token = csrf_token(login_page)

    response = client.post(
        "/teacher/login",
        data={
            "csrf_token": token,
            "username": "zuk1",
            "password": "teacher-pass",
            "submit": "Sign in",
        },
        follow_redirects=False,
    )

    assert response.status_code == 200
    with client.session_transaction() as session:
        assert "teacher_portal_id" not in session

    with client.application.app_context():
        log = ActivityLog.query.filter_by(action="teacher_portal_login_ambiguous").order_by(ActivityLog.id.desc()).first()
        assert log is not None
        assert log.details["submitted_username"] == "zuk1"
        assert log.details["folded_username"] == "zuk1"
        assert log.details["match_count"] == 2


def test_rate_limit_username_uses_folded_alias_when_enabled(client):
    with client.application.app_context():
        _set_setting(views.SETTING_LOGIN_FOLDED_ALIAS_ENABLED, "true")
        with client.application.test_request_context("/participant/login", method="POST", data={"username": "Żółć1"}):
            assert views._rate_limit_username() == "zolc1"

        _set_setting(views.SETTING_LOGIN_FOLDED_ALIAS_ENABLED, "false")
        with client.application.test_request_context("/participant/login", method="POST", data={"username": "Żółć1"}):
            assert views._rate_limit_username() == "żółć1"


def test_teacher_board_login_with_configured_password(client, csrf_token):
    login_page = client.get("/board/login")
    token = csrf_token(login_page)

    response = client.post(
        "/board/login",
        data={
            "csrf_token": token,
            "password": "board-password",
            "submit": "Enter message board",
        },
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert response.headers["Location"].startswith("/board")

    board = client.get("/board")
    assert board.status_code == 200
