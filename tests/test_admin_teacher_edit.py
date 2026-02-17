from werkzeug.security import generate_password_hash

from ipo_app.extensions import db
from ipo_app.models import Teacher, TeacherLanguage


def _create_teacher(*, email: str) -> int:
    teacher = Teacher(
        country="Testland",
        first_name="Editable",
        last_name="Teacher",
        email=email,
        school="Original School",
        sex_document="female",
        accommodation_room_sharing="same_sex",
        languages="English",
        meal_preference="No preference",
        tshirt_size="M",
        delegation_leader=False,
        prior_ipo_assessor=False,
        prior_ipo_assessor_level=0,
        portal_username=f"teacher-{email.split('@')[0]}",
        portal_password_hash=generate_password_hash("teacher-pass"),
    )
    teacher.language_entries.append(TeacherLanguage(language="English"))
    db.session.add(teacher)
    db.session.commit()
    return teacher.id


def test_admin_teacher_edit_updates_without_server_error_and_toggles_delegation_leader(client, csrf_token):
    with client.application.app_context():
        teacher_id = _create_teacher(email="editable.teacher@example.com")

    with client.session_transaction() as session:
        session["admin_user"] = "admin"

    edit_page = client.get(f"/admin/teachers/{teacher_id}/edit")
    assert edit_page.status_code == 200
    token = csrf_token(edit_page)

    response = client.post(
        f"/admin/teachers/{teacher_id}/edit",
        data={
            "csrf_token": token,
            "first_name": "Updated",
            "last_name": "Teacher",
            "email": "editable.teacher@example.com",
            "country": "Testland",
            "school": "Updated School",
            "sex_document": "female",
            "accommodation_room_sharing": "same_sex",
            "languages": ["English", "French"],
            "meal_preference": "Vegetarian",
            "tshirt_size": "L",
            "prior_ipo_assessor_level": "1",
            "photo_consent": "yes",
            "delegation_leader": "y",
            "is_absent": "y",
            "submit": "Save changes",
        },
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert response.headers["Location"] == "/admin/teachers"

    with client.application.app_context():
        teacher = db.session.get(Teacher, teacher_id)
        assert teacher is not None
        assert teacher.first_name == "Updated"
        assert teacher.school == "Updated School"
        assert teacher.delegation_leader is True
        assert teacher.is_absent is True
        assert set((teacher.languages or "").split(", ")) == {"English", "French"}
