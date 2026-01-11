import re

from werkzeug.security import generate_password_hash

from ipo_app.extensions import db
from ipo_app.models import AppSetting, DelegationInvite, DelegationInviteRole, Teacher


def _set_setting(key: str, value: str) -> None:
    existing = AppSetting.query.filter_by(key=key).first()
    if existing:
        existing.value = value
    else:
        db.session.add(AppSetting(key=key, value=value))
    db.session.commit()


def _extract_csrf(html: str, field_name: str) -> str:
    match = re.search(
        rf'name=[\"\\\']{re.escape(field_name)}[\"\\\'][^>]*value=[\"\\\']([^\"\\\']+)[\"\\\']',
        html,
    )
    assert match, f"CSRF field {field_name!r} not found"
    return match.group(1)


def _create_teacher(*, username: str, password: str, delegation_leader: bool) -> int:
    teacher = Teacher(
        country="Testland",
        first_name="Teacher",
        last_name=username,
        email=f"{username}@example.test",
        school="Test School",
        languages="English",
        meal_preference="No preference",
        tshirt_size="M",
        delegation_leader=delegation_leader,
        portal_username=username,
        portal_password_hash=generate_password_hash(password),
    )
    db.session.add(teacher)
    db.session.commit()
    return teacher.id


def test_registration_invite_only_blocks_student_registration_without_invite(client):
    with client.application.app_context():
        _set_setting("registration_invite_only", "true")

    response = client.get("/register/student")
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "Registration is available by invitation only" in html
    assert "<form" not in html


def test_registration_invite_only_blocks_teacher_registration_without_invite(client):
    with client.application.app_context():
        _set_setting("registration_invite_only", "true")

    response = client.get("/register/teacher")
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "Registration is available by invitation only" in html
    assert "<form" not in html


def test_delegation_invite_endpoints_reject_non_leader_teachers(client):
    with client.application.app_context():
        _set_setting("teacher_portal_enabled", "true")
        leader_id = _create_teacher(username="leader", password="pass", delegation_leader=True)
        non_leader_id = _create_teacher(username="member", password="pass", delegation_leader=False)

    with client.session_transaction() as session:
        session["teacher_portal_id"] = leader_id

    delegation_page = client.get("/teacher/delegation")
    assert delegation_page.status_code == 200
    html = delegation_page.get_data(as_text=True)
    student_token = _extract_csrf(html, "student-csrf_token")
    teacher_token = _extract_csrf(html, "teacher-csrf_token")

    with client.session_transaction() as session:
        session["teacher_portal_id"] = non_leader_id

    response = client.post(
        "/teacher/delegation/invite/student",
        data={
            "student-csrf_token": student_token,
            "student-first_name": "Student",
            "student-last_name": "Invite",
            "student-email": "student.invite@example.test",
            "student-submit": "Send student invite",
        },
        follow_redirects=False,
    )
    assert response.status_code == 403

    response = client.post(
        "/teacher/delegation/invite/teacher",
        data={
            "teacher-csrf_token": teacher_token,
            "teacher-first_name": "Teacher",
            "teacher-last_name": "Invite",
            "teacher-email": "teacher.invite@example.test",
            "teacher-submit": "Send teacher invite",
        },
        follow_redirects=False,
    )
    assert response.status_code == 403


def test_delegation_invite_prevents_duplicate_active_invites(client):
    with client.application.app_context():
        _set_setting("teacher_portal_enabled", "true")
        leader_id = _create_teacher(username="leader-dup", password="pass", delegation_leader=True)

    with client.session_transaction() as session:
        session["teacher_portal_id"] = leader_id

    delegation_page = client.get("/teacher/delegation")
    assert delegation_page.status_code == 200
    token = _extract_csrf(delegation_page.get_data(as_text=True), "student-csrf_token")

    email = "invitee@example.com"
    first_post = client.post(
        "/teacher/delegation/invite/student",
        data={
            "student-csrf_token": token,
            "student-first_name": "Invitee",
            "student-last_name": "One",
            "student-email": email,
            "student-submit": "Send student invite",
        },
        follow_redirects=False,
    )
    assert first_post.status_code == 302
    assert first_post.headers["Location"] == "/teacher/delegation"

    second_post = client.post(
        "/teacher/delegation/invite/student",
        data={
            "student-csrf_token": token,
            "student-first_name": "Invitee",
            "student-last_name": "One",
            "student-email": email,
            "student-submit": "Send student invite",
        },
        follow_redirects=False,
    )

    assert second_post.status_code == 200
    html = second_post.get_data(as_text=True)
    assert "An active student invite already exists for this email." in html

    with client.application.app_context():
        invites = DelegationInvite.query.filter_by(
            email=email,
            role=DelegationInviteRole.STUDENT,
            country="Testland",
        ).all()
        assert len(invites) == 1


def test_delegation_invite_prevents_duplicate_active_teacher_invites(client):
    with client.application.app_context():
        _set_setting("teacher_portal_enabled", "true")
        leader_id = _create_teacher(username="leader-dup-teacher", password="pass", delegation_leader=True)

    with client.session_transaction() as session:
        session["teacher_portal_id"] = leader_id

    delegation_page = client.get("/teacher/delegation")
    assert delegation_page.status_code == 200
    token = _extract_csrf(delegation_page.get_data(as_text=True), "teacher-csrf_token")

    email = "invitee.teacher@example.com"
    first_post = client.post(
        "/teacher/delegation/invite/teacher",
        data={
            "teacher-csrf_token": token,
            "teacher-first_name": "Invitee",
            "teacher-last_name": "Two",
            "teacher-email": email,
            "teacher-submit": "Send teacher invite",
        },
        follow_redirects=False,
    )
    assert first_post.status_code == 302
    assert first_post.headers["Location"] == "/teacher/delegation"

    second_post = client.post(
        "/teacher/delegation/invite/teacher",
        data={
            "teacher-csrf_token": token,
            "teacher-first_name": "Invitee",
            "teacher-last_name": "Two",
            "teacher-email": email,
            "teacher-submit": "Send teacher invite",
        },
        follow_redirects=False,
    )

    assert second_post.status_code == 200
    html = second_post.get_data(as_text=True)
    assert "An active teacher invite already exists for this email." in html

    with client.application.app_context():
        invites = DelegationInvite.query.filter_by(
            email=email,
            role=DelegationInviteRole.TEACHER,
            country="Testland",
        ).all()
        assert len(invites) == 1


def test_admin_invitation_revoke_prevents_reuse_of_invite_links(client, csrf_token):
    with client.application.app_context():
        _set_setting("registration_invite_only", "true")
        invite = DelegationInvite(
            token="revoked-invite-token",
            role=DelegationInviteRole.STUDENT,
            country="Testland",
            first_name="Revoked",
            last_name="Invite",
            email="revoked.invite@example.com",
        )
        db.session.add(invite)
        db.session.commit()
        invite_id = invite.id
        invite_token = invite.token

    with client.session_transaction() as session:
        session["admin_user"] = "admin"

    token = csrf_token(client.get("/admin/invitations"))
    response = client.post(
        f"/admin/invitations/invite/{invite_id}/revoke",
        data={"csrf_token": token},
        follow_redirects=False,
    )
    assert response.status_code == 302
    assert response.headers["Location"] == "/admin/invitations"

    with client.application.app_context():
        refreshed = db.session.get(DelegationInvite, invite_id)
        assert refreshed is not None
        assert refreshed.revoked_at is not None
        assert refreshed.accepted_at is None

    register_page = client.get(f"/register/student?invite={invite_token}")
    assert register_page.status_code == 200
    html = register_page.get_data(as_text=True)
    assert "This invite link has been revoked." in html
    assert "<form" not in html
