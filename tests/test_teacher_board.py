from ipo_app.extensions import db
from ipo_app.models import ActivityLog, Teacher, TeacherMessage, TeacherMessagePriority, TeacherMessageStatus


def _create_teacher(*, email: str) -> int:
    teacher = Teacher(
        country="Testland",
        first_name="Teacher",
        last_name=email.split("@")[0],
        email=email,
        school="Test School",
        languages="English",
        meal_preference="No preference",
        tshirt_size="M",
    )
    db.session.add(teacher)
    db.session.commit()
    return teacher.id


def test_teacher_board_requires_auth_redirects_to_login(client):
    response = client.get("/board", follow_redirects=False)

    assert response.status_code == 302
    assert response.headers["Location"].startswith("/board/login")


def test_teacher_board_logout_clears_session_and_redirects_to_login(client):
    with client.session_transaction() as session:
        session["teacher_board"] = True

    response = client.get("/board/logout", follow_redirects=False)

    assert response.status_code == 302
    assert response.headers["Location"].startswith("/board/login")

    with client.session_transaction() as session:
        assert "teacher_board" not in session


def test_teacher_board_login_returns_503_when_password_not_configured(client, csrf_token):
    client.application.config["TEACHER_BOARD_PASSWORD"] = ""

    login_page = client.get("/board/login")
    token = csrf_token(login_page)

    response = client.post(
        "/board/login",
        data={
            "csrf_token": token,
            "password": "anything",
            "submit": "Enter message board",
        },
        follow_redirects=False,
    )

    assert response.status_code == 503
    with client.session_transaction() as session:
        assert "teacher_board" not in session


def test_teacher_board_login_rejects_invalid_password_and_logs(client, csrf_token):
    login_page = client.get("/board/login")
    token = csrf_token(login_page)

    response = client.post(
        "/board/login",
        data={
            "csrf_token": token,
            "password": "wrong-password",
            "submit": "Enter message board",
        },
        follow_redirects=False,
    )

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "Invalid password." in html

    with client.session_transaction() as session:
        assert "teacher_board" not in session

    with client.application.app_context():
        log = ActivityLog.query.filter_by(action="teacher_board_login_failed").first()
        assert log is not None


def test_teacher_board_for_portal_teacher_shows_broadcast_and_targeted_only(client):
    with client.application.app_context():
        teacher_a_id = _create_teacher(email="teacher.a@example.test")
        teacher_b_id = _create_teacher(email="teacher.b@example.test")

        db.session.add_all(
            [
                TeacherMessage(
                    title="Broadcast",
                    body="All teachers.",
                    priority=TeacherMessagePriority.NORMAL,
                    status=TeacherMessageStatus.ACTIVE,
                    deliver_to_all=True,
                    teacher_id=None,
                ),
                TeacherMessage(
                    title="To A",
                    body="Only A.",
                    priority=TeacherMessagePriority.NORMAL,
                    status=TeacherMessageStatus.ACTIVE,
                    deliver_to_all=False,
                    teacher_id=teacher_a_id,
                ),
                TeacherMessage(
                    title="To B",
                    body="Only B.",
                    priority=TeacherMessagePriority.NORMAL,
                    status=TeacherMessageStatus.ACTIVE,
                    deliver_to_all=False,
                    teacher_id=teacher_b_id,
                ),
                TeacherMessage(
                    title="Archived broadcast",
                    body="Should not appear.",
                    priority=TeacherMessagePriority.NORMAL,
                    status=TeacherMessageStatus.ARCHIVED,
                    deliver_to_all=True,
                    teacher_id=None,
                ),
            ]
        )
        db.session.commit()

    with client.session_transaction() as session:
        session["teacher_portal_id"] = teacher_a_id

    response = client.get("/board", follow_redirects=False)
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "Broadcast" in html
    assert "To A" in html
    assert "To B" not in html
    assert "Archived broadcast" not in html


def test_teacher_board_search_filters_title_and_body(client):
    with client.application.app_context():
        db.session.add_all(
            [
                TeacherMessage(
                    title="Needle in title",
                    body="Body one.",
                    priority=TeacherMessagePriority.NORMAL,
                    status=TeacherMessageStatus.ACTIVE,
                    deliver_to_all=True,
                    teacher_id=None,
                ),
                TeacherMessage(
                    title="Other title",
                    body="Needle in body.",
                    priority=TeacherMessagePriority.NORMAL,
                    status=TeacherMessageStatus.ACTIVE,
                    deliver_to_all=True,
                    teacher_id=None,
                ),
                TeacherMessage(
                    title="Unrelated",
                    body="No match.",
                    priority=TeacherMessagePriority.NORMAL,
                    status=TeacherMessageStatus.ACTIVE,
                    deliver_to_all=True,
                    teacher_id=None,
                ),
            ]
        )
        db.session.commit()

    with client.session_transaction() as session:
        session["teacher_board"] = True

    response = client.get("/board?q=needle", follow_redirects=False)
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "Needle in title" in html
    assert "Needle in body." in html
    assert "Unrelated" not in html
