from datetime import date

from ipo_app.models import Student, Teacher


def test_student_open_registration_creates_student_and_redirects(client, csrf_token):
    register_page = client.get("/register/student")
    token = csrf_token(register_page)

    response = client.post(
        "/register/student",
        data={
            "csrf_token": token,
            "first_name": "Open",
            "last_name": "Student",
            "email": "open.student@example.com",
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
    assert response.headers["Location"] == "/register/student"

    with client.application.app_context():
        student = Student.query.filter_by(email="open.student@example.com").first()
        assert student is not None
        assert student.upload_username
        assert student.upload_password_hash


def test_student_open_registration_rejects_duplicate_email(client, csrf_token):
    first_page = client.get("/register/student")
    first_token = csrf_token(first_page)

    response = client.post(
        "/register/student",
        data={
            "csrf_token": first_token,
            "first_name": "Duplicate",
            "last_name": "Student",
            "email": "duplicate.student@example.com",
            "country": "Testland",
            "school": "Test School",
            "sex_document": "female",
            "accommodation_room_sharing": "any_sex",
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

    second_page = client.get("/register/student")
    second_token = csrf_token(second_page)

    duplicate = client.post(
        "/register/student",
        data={
            "csrf_token": second_token,
            "first_name": "Duplicate2",
            "last_name": "Student",
            "email": "duplicate.student@example.com",
            "country": "Testland",
            "school": "Test School",
            "sex_document": "male",
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

    assert duplicate.status_code == 200
    html = duplicate.get_data(as_text=True)
    assert "already registered" in html.lower()

    with client.application.app_context():
        assert Student.query.filter_by(email="duplicate.student@example.com").count() == 1


def test_teacher_open_registration_creates_teacher_and_redirects(client, csrf_token):
    register_page = client.get("/register/teacher")
    token = csrf_token(register_page)

    response = client.post(
        "/register/teacher",
        data={
            "csrf_token": token,
            "first_name": "Open",
            "last_name": "Teacher",
            "email": "open.teacher@example.com",
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
    assert response.headers["Location"] == "/register/teacher"

    with client.application.app_context():
        teacher = Teacher.query.filter_by(email="open.teacher@example.com").first()
        assert teacher is not None
        assert teacher.portal_username
        assert teacher.portal_password_hash


def test_teacher_open_registration_rejects_duplicate_email(client, csrf_token):
    first_page = client.get("/register/teacher")
    first_token = csrf_token(first_page)

    response = client.post(
        "/register/teacher",
        data={
            "csrf_token": first_token,
            "first_name": "Duplicate",
            "last_name": "Teacher",
            "email": "duplicate.teacher@example.com",
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

    second_page = client.get("/register/teacher")
    second_token = csrf_token(second_page)

    duplicate = client.post(
        "/register/teacher",
        data={
            "csrf_token": second_token,
            "first_name": "Duplicate2",
            "last_name": "Teacher",
            "email": "duplicate.teacher@example.com",
            "country": "Testland",
            "school": "Test School",
            "sex_document": "female",
            "accommodation_room_sharing": "same_sex",
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

    assert duplicate.status_code == 200
    html = duplicate.get_data(as_text=True)
    assert "already registered" in html.lower()

    with client.application.app_context():
        assert Teacher.query.filter_by(email="duplicate.teacher@example.com").count() == 1


def test_teacher_open_registration_requires_english_language(client, csrf_token):
    register_page = client.get("/register/teacher")
    token = csrf_token(register_page)

    response = client.post(
        "/register/teacher",
        data={
            "csrf_token": token,
            "first_name": "No",
            "last_name": "English",
            "email": "no.english.teacher@example.com",
            "country": "Testland",
            "school": "Test School",
            "sex_document": "male",
            "accommodation_room_sharing": "any_sex",
            "languages": ["French"],
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

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "English must be selected" in html

    with client.application.app_context():
        assert Teacher.query.filter_by(email="no.english.teacher@example.com").count() == 0
