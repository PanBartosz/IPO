from datetime import date

from ipo_app.extensions import db
from ipo_app.models import (
    AppSetting,
    Student,
    Survey,
    SurveyAssignment,
    SurveyAssignmentStatus,
    SurveyAudience,
    SurveyQuestion,
    SurveyQuestionType,
    SurveyResponse,
    SurveyStatus,
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
        last_name=email.split("@")[0],
        email=email,
        school="Test School",
        date_of_birth=date(2000, 1, 1),
        essay_language="English",
        keyboard_preference="QWERTY",
        meal_preference="No preference",
    )
    db.session.add(student)
    db.session.commit()
    return student.id


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


def _create_survey_with_question(*, audience: SurveyAudience, title: str) -> tuple[int, int]:
    survey = Survey(
        title=title,
        description=None,
        status=SurveyStatus.PUBLISHED,
        audience=audience,
        allow_edit=False,
        open_at=None,
        close_at=None,
        created_by="admin",
    )
    db.session.add(survey)
    db.session.flush()
    question = SurveyQuestion(
        survey_id=survey.id,
        prompt="Your answer",
        help_text=None,
        type=SurveyQuestionType.SHORT_TEXT,
        required=True,
        options=None,
        position=1,
    )
    db.session.add(question)
    db.session.commit()
    return survey.id, question.id


def test_student_can_submit_survey_response_and_assignment_completes(client, csrf_token):
    with client.application.app_context():
        student_id = _create_student(email="survey.student@example.com")
        survey_id, question_id = _create_survey_with_question(audience=SurveyAudience.STUDENT, title="Student survey")
        assignment = SurveyAssignment(
            survey_id=survey_id,
            student_id=student_id,
            status=SurveyAssignmentStatus.PENDING,
        )
        db.session.add(assignment)
        db.session.commit()
        assignment_id = assignment.id

    with client.session_transaction() as session:
        session["student_upload_id"] = student_id

    detail_page = client.get(f"/participant/surveys/{assignment_id}")
    token = csrf_token(detail_page)

    response = client.post(
        f"/participant/surveys/{assignment_id}",
        data={
            "csrf_token": token,
            f"question_{question_id}": "Student response text",
        },
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert response.headers["Location"] == f"/participant/surveys/{assignment_id}"

    with client.application.app_context():
        refreshed = db.session.get(SurveyAssignment, assignment_id)
        assert refreshed is not None
        assert refreshed.status == SurveyAssignmentStatus.COMPLETED
        assert refreshed.completed_at is not None
        assert refreshed.response is not None
        assert refreshed.response.response_data.get(str(question_id)) == "Student response text"

        stored = SurveyResponse.query.filter_by(assignment_id=assignment_id, survey_id=survey_id).first()
        assert stored is not None


def test_teacher_can_submit_survey_response_and_assignment_completes(client, csrf_token):
    with client.application.app_context():
        _set_setting("teacher_portal_enabled", "true")
        teacher_id = _create_teacher(email="survey.teacher@example.com")
        survey_id, question_id = _create_survey_with_question(audience=SurveyAudience.TEACHER, title="Teacher survey")
        assignment = SurveyAssignment(
            survey_id=survey_id,
            teacher_id=teacher_id,
            status=SurveyAssignmentStatus.PENDING,
        )
        db.session.add(assignment)
        db.session.commit()
        assignment_id = assignment.id

    with client.session_transaction() as session:
        session["teacher_portal_id"] = teacher_id

    detail_page = client.get(f"/teacher/surveys/{assignment_id}")
    token = csrf_token(detail_page)

    response = client.post(
        f"/teacher/surveys/{assignment_id}",
        data={
            "csrf_token": token,
            f"question_{question_id}": "Teacher response text",
        },
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert response.headers["Location"] == f"/teacher/surveys/{assignment_id}"

    with client.application.app_context():
        refreshed = db.session.get(SurveyAssignment, assignment_id)
        assert refreshed is not None
        assert refreshed.status == SurveyAssignmentStatus.COMPLETED
        assert refreshed.completed_at is not None
        assert refreshed.response is not None
        assert refreshed.response.response_data.get(str(question_id)) == "Teacher response text"
