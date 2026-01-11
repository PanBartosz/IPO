from ipo_app.extensions import db
from ipo_app.models import (
    ActivityLog,
    Teacher,
    TeacherMessage,
    TeacherMessagePriority,
    TeacherMessageStatus,
    TeacherMessageTemplate,
)
from werkzeug.security import generate_password_hash


def _create_teacher(*, email: str, portal_username: str | None = None) -> int:
    teacher = Teacher(
        country="Testland",
        first_name="Teacher",
        last_name=email.split("@")[0],
        email=email,
        school="Test School",
        languages="English",
        meal_preference="No preference",
        tshirt_size="M",
        portal_username=portal_username,
        portal_password_hash=generate_password_hash("teacher-pass") if portal_username else None,
    )
    db.session.add(teacher)
    db.session.commit()
    return teacher.id


def test_admin_messages_post_broadcast_creates_message_and_log(client, csrf_token):
    with client.session_transaction() as session:
        session["admin_user"] = "admin"

    token = csrf_token(client.get("/admin/messages"))
    response = client.post(
        "/admin/messages",
        data={
            "csrf_token": token,
            "title": "Broadcast announcement",
            "body": "Hello teachers.",
            "priority": "high",
            "teacher_id": "0",
            "category": "",
            "submit": "Post message",
        },
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert response.headers["Location"] == "/admin/messages"

    with client.application.app_context():
        message = TeacherMessage.query.filter_by(title="Broadcast announcement").first()
        assert message is not None
        assert message.deliver_to_all is True
        assert message.teacher_id is None
        assert message.status == TeacherMessageStatus.ACTIVE
        assert message.priority == TeacherMessagePriority.HIGH

        log = ActivityLog.query.filter_by(
            action="teacher_message_created",
            object_type="teacher_message",
            object_id=str(message.id),
        ).first()
        assert log is not None


def test_admin_messages_post_targeted_creates_message_and_log(client, csrf_token):
    with client.application.app_context():
        teacher_id = _create_teacher(email="targeted.teacher@example.com")

    with client.session_transaction() as session:
        session["admin_user"] = "admin"

    token = csrf_token(client.get("/admin/messages"))
    response = client.post(
        "/admin/messages",
        data={
            "csrf_token": token,
            "title": "Targeted announcement",
            "body": "Hello Teacher.",
            "priority": "normal",
            "teacher_id": str(teacher_id),
            "category": "Targeted",
            "submit": "Post message",
        },
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert response.headers["Location"] == "/admin/messages"

    with client.application.app_context():
        message = TeacherMessage.query.filter_by(title="Targeted announcement").first()
        assert message is not None
        assert message.deliver_to_all is False
        assert message.teacher_id == teacher_id
        assert message.status == TeacherMessageStatus.ACTIVE
        assert message.priority == TeacherMessagePriority.NORMAL

        log = ActivityLog.query.filter_by(
            action="teacher_message_created",
            object_type="teacher_message",
            object_id=str(message.id),
        ).first()
        assert log is not None


def test_admin_message_edit_updates_message_and_log(client, csrf_token):
    with client.application.app_context():
        teacher_id = _create_teacher(email="edit.teacher@example.com")
        message = TeacherMessage(
            title="Before edit",
            body="Old body",
            priority=TeacherMessagePriority.NORMAL,
            status=TeacherMessageStatus.ACTIVE,
            deliver_to_all=False,
            teacher_id=teacher_id,
            category=None,
            creator_id="admin",
        )
        db.session.add(message)
        db.session.commit()
        message_id = message.id

    with client.session_transaction() as session:
        session["admin_user"] = "admin"

    token = csrf_token(client.get(f"/admin/messages/{message_id}/edit"))
    response = client.post(
        f"/admin/messages/{message_id}/edit",
        data={
            "csrf_token": token,
            "title": "After edit",
            "body": "New body",
            "priority": "low",
            "teacher_id": "0",
            "category": "Edited",
            "submit": "Post message",
        },
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert response.headers["Location"] == "/admin/messages"

    with client.application.app_context():
        refreshed = db.session.get(TeacherMessage, message_id)
        assert refreshed is not None
        assert refreshed.title == "After edit"
        assert refreshed.body == "New body"
        assert refreshed.priority == TeacherMessagePriority.LOW
        assert refreshed.deliver_to_all is True
        assert refreshed.teacher_id is None
        assert refreshed.category == "Edited"

        log = ActivityLog.query.filter_by(
            action="teacher_message_updated",
            object_type="teacher_message",
            object_id=str(message_id),
        ).first()
        assert log is not None


def test_admin_message_archive_and_restore_toggle_status(client, csrf_token):
    with client.application.app_context():
        message = TeacherMessage(
            title="Archive me",
            body="Body",
            priority=TeacherMessagePriority.NORMAL,
            status=TeacherMessageStatus.ACTIVE,
            deliver_to_all=True,
            teacher_id=None,
            creator_id="admin",
        )
        db.session.add(message)
        db.session.commit()
        message_id = message.id

    with client.session_transaction() as session:
        session["admin_user"] = "admin"

    token = csrf_token(client.get("/admin/messages"))
    archived = client.post(
        f"/admin/messages/{message_id}/archive",
        data={"csrf_token": token},
        follow_redirects=False,
    )
    assert archived.status_code == 302
    assert archived.headers["Location"] == "/admin/messages"

    restored = client.post(
        f"/admin/messages/{message_id}/restore",
        data={"csrf_token": token},
        follow_redirects=False,
    )
    assert restored.status_code == 302
    assert restored.headers["Location"] == "/admin/messages"

    with client.application.app_context():
        refreshed = db.session.get(TeacherMessage, message_id)
        assert refreshed is not None
        assert refreshed.status == TeacherMessageStatus.ACTIVE

        archived_log = ActivityLog.query.filter_by(
            action="teacher_message_archived",
            object_type="teacher_message",
            object_id=str(message_id),
        ).first()
        assert archived_log is not None

        restored_log = ActivityLog.query.filter_by(
            action="teacher_message_restored",
            object_type="teacher_message",
            object_id=str(message_id),
        ).first()
        assert restored_log is not None


def test_admin_message_delete_removes_message_and_log(client, csrf_token):
    with client.application.app_context():
        message = TeacherMessage(
            title="Delete me",
            body="Body",
            priority=TeacherMessagePriority.NORMAL,
            status=TeacherMessageStatus.ACTIVE,
            deliver_to_all=True,
            teacher_id=None,
            creator_id="admin",
        )
        db.session.add(message)
        db.session.commit()
        message_id = message.id

    with client.session_transaction() as session:
        session["admin_user"] = "admin"

    token = csrf_token(client.get("/admin/messages"))
    response = client.post(
        f"/admin/messages/{message_id}/delete",
        data={"csrf_token": token},
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert response.headers["Location"] == "/admin/messages"

    with client.application.app_context():
        assert db.session.get(TeacherMessage, message_id) is None
        log = ActivityLog.query.filter_by(
            action="teacher_message_deleted",
            object_type="teacher_message",
            object_id=str(message_id),
        ).first()
        assert log is not None


def test_admin_quick_message_creates_targeted_message_and_log(client, csrf_token):
    with client.application.app_context():
        teacher_id = _create_teacher(email="quick.teacher@example.com")

    with client.session_transaction() as session:
        session["admin_user"] = "admin"

    token = csrf_token(client.get("/admin/messages"))
    response = client.post(
        "/admin/messages/quick",
        data={
            "csrf_token": token,
            "teacher_id": str(teacher_id),
            "title": "Quick note",
            "body": "Quick message body",
            "priority": "normal",
            "category": "Quick",
            "submit": "Send message",
        },
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert response.headers["Location"] == "/admin/messages"

    with client.application.app_context():
        message = TeacherMessage.query.filter_by(title="Quick note").first()
        assert message is not None
        assert message.deliver_to_all is False
        assert message.teacher_id == teacher_id

        log = ActivityLog.query.filter_by(
            action="teacher_message_created",
            object_type="teacher_message",
            object_id=str(message.id),
        ).first()
        assert log is not None
        assert "quick compose" in (log.description or "")


def test_admin_message_templates_can_prefill_message_form(client, csrf_token):
    with client.session_transaction() as session:
        session["admin_user"] = "admin"

    token = csrf_token(client.get("/admin/message-templates/new"))
    response = client.post(
        "/admin/message-templates/new",
        data={
            "csrf_token": token,
            "name": "urgent-template",
            "title": "Urgent template title",
            "body": "Urgent template body",
            "category": "Urgent",
            "submit": "Save template",
        },
        follow_redirects=False,
    )
    assert response.status_code == 302
    assert response.headers["Location"] == "/admin/message-templates"

    with client.application.app_context():
        template = TeacherMessageTemplate.query.filter_by(name="urgent-template").first()
        assert template is not None
        template_id = template.id

    page = client.get(f"/admin/messages?template={template_id}")
    assert page.status_code == 200
    html = page.get_data(as_text=True)
    assert 'value="Urgent template title"' in html
    assert "Urgent template body" in html
    assert 'value="Urgent"' in html


def test_admin_message_template_duplicate_name_is_rejected(client, csrf_token):
    with client.application.app_context():
        db.session.add(
            TeacherMessageTemplate(
                name="duplicate-template",
                title="First",
                body="Body",
                category=None,
            )
        )
        db.session.commit()

    with client.session_transaction() as session:
        session["admin_user"] = "admin"

    token = csrf_token(client.get("/admin/message-templates/new"))
    response = client.post(
        "/admin/message-templates/new",
        data={
            "csrf_token": token,
            "name": "duplicate-template",
            "title": "Second",
            "body": "Body 2",
            "category": "",
            "submit": "Save template",
        },
        follow_redirects=False,
    )

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "A template with this name already exists." in html

    with client.application.app_context():
        assert TeacherMessageTemplate.query.filter_by(name="duplicate-template").count() == 1

