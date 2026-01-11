from datetime import date

from ipo_app.extensions import db
from ipo_app.models import (
    AppSetting,
    DelegationInvite,
    DelegationInviteRole,
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


def test_student_invite_link_sets_opened_at_on_first_view(client):
    with client.application.app_context():
        _set_setting("registration_invite_only", "true")
        invite = DelegationInvite(
            token="student-opened-token",
            role=DelegationInviteRole.STUDENT,
            country="Testland",
            first_name="Invited",
            last_name="Student",
            email="invited.student@example.com",
        )
        db.session.add(invite)
        db.session.commit()
        invite_id = invite.id

    response = client.get("/register/student?invite=student-opened-token")
    assert response.status_code == 200

    with client.application.app_context():
        refreshed = db.session.get(DelegationInvite, invite_id)
        assert refreshed is not None
        assert refreshed.opened_at is not None
        assert refreshed.accepted_at is None


def test_student_registration_via_invite_marks_invite_accepted_and_prevents_reuse(client, csrf_token):
    with client.application.app_context():
        _set_setting("registration_invite_only", "true")
        invite = DelegationInvite(
            token="student-accept-token",
            role=DelegationInviteRole.STUDENT,
            country="Testland",
            first_name="Invited",
            last_name="Student",
            email="invited.accept@example.com",
        )
        db.session.add(invite)
        db.session.commit()
        invite_id = invite.id

    register_page = client.get("/register/student?invite=student-accept-token")
    token = csrf_token(register_page)

    response = client.post(
        "/register/student",
        data={
            "csrf_token": token,
            "invite": "student-accept-token",
            "first_name": "Invited",
            "last_name": "Student",
            "email": "invited.accept@example.com",
            "country": "Testland",
            "school": "Test School",
            "sex_document": "female",
            "accommodation_room_sharing": "same_sex",
            "date_of_birth": date(2000, 1, 1).isoformat(),
            "essay_language": "English",
            "keyboard_preference": "QWERTY",
            "meal_preference": "No preference",
            "gdpr_acknowledged": "y",
            "photo_consent": "yes",
            "accepted_ethics": "y",
            "submit": "Submit registration",
        },
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert response.headers["Location"] == "/"

    with client.application.app_context():
        refreshed = db.session.get(DelegationInvite, invite_id)
        assert refreshed is not None
        assert refreshed.accepted_at is not None
        assert refreshed.student_id is not None

        student = db.session.get(Student, refreshed.student_id)
        assert student is not None
        assert student.email == "invited.accept@example.com"
        assert student.country == "Testland"
        assert student.upload_username
        assert student.upload_password_hash

    reused = client.get("/register/student?invite=student-accept-token")
    assert reused.status_code == 200
    html = reused.get_data(as_text=True)
    assert "already been used" in html
    assert "<form" not in html


def test_teacher_delegation_leader_invite_registers_teacher_as_delegation_leader(client, csrf_token):
    with client.application.app_context():
        _set_setting("registration_invite_only", "true")
        invite = DelegationInvite(
            token="teacher-leader-token",
            role=DelegationInviteRole.TEACHER,
            delegation_leader=True,
            country="Testland",
            first_name="Invited",
            last_name="Leader",
            email="invited.leader@example.com",
        )
        db.session.add(invite)
        db.session.commit()
        invite_id = invite.id

    register_page = client.get("/register/teacher?invite=teacher-leader-token")
    token = csrf_token(register_page)

    response = client.post(
        "/register/teacher",
        data={
            "csrf_token": token,
            "invite": "teacher-leader-token",
            "first_name": "Invited",
            "last_name": "Leader",
            "email": "invited.leader@example.com",
            "country": "Testland",
            "school": "Test School",
            "sex_document": "male",
            "accommodation_room_sharing": "any_sex",
            "languages": ["English"],
            "meal_preference": "No preference",
            "tshirt_size": "M",
            "prior_ipo_assessor_level": "0",
            "gdpr_acknowledged": "y",
            "photo_consent": "yes",
            "declared_assessor_competence": "y",
            "accepted_ethics": "y",
            "submit": "Submit registration",
        },
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert response.headers["Location"] == "/"

    with client.application.app_context():
        refreshed = db.session.get(DelegationInvite, invite_id)
        assert refreshed is not None
        assert refreshed.accepted_at is not None
        assert refreshed.teacher_id is not None

        teacher = db.session.get(Teacher, refreshed.teacher_id)
        assert teacher is not None
        assert teacher.email == "invited.leader@example.com"
        assert teacher.country == "Testland"
        assert teacher.delegation_leader is True
        assert teacher.portal_username
        assert teacher.portal_password_hash

