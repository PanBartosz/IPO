from ipo_app.extensions import db
from datetime import date

import ipo_app.views as views
from ipo_app.models import (
    ActivityLog,
    AssignmentBatch,
    PlannerStatus,
    ReadingGroup,
    Stage,
    Student,
    Teacher,
    TeacherLanguage,
)


def _create_teacher(*, first_name: str, last_name: str, email: str, assessor: bool) -> int:
    teacher = Teacher(
        country="Testland",
        first_name=first_name,
        last_name=last_name,
        email=email,
        school="Test School",
        languages="English",
        meal_preference="No preference",
        tshirt_size="M",
        declared_assessor_competence=assessor,
    )
    teacher.language_entries.append(TeacherLanguage(language="English"))
    db.session.add(teacher)
    db.session.commit()
    return teacher.id


def test_admin_planner_create_batch_creates_row_and_log(client, csrf_token):
    with client.session_transaction() as session:
        session["admin_user"] = "admin"

    token = csrf_token(client.get("/admin/planner"))
    response = client.post(
        "/admin/planner",
        data={
            "csrf_token": token,
            "name": "Batch 1",
            "stage": Stage.STAGE_1.value,
            "notes": "",
            "submit": "Create batch",
        },
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert response.headers["Location"].startswith("/admin/planner/batches/")

    with client.application.app_context():
        batch = AssignmentBatch.query.filter_by(name="Batch 1").first()
        assert batch is not None
        assert batch.stage == Stage.STAGE_1
        assert batch.status == PlannerStatus.DRAFT

        log = ActivityLog.query.filter_by(
            action="batch_created",
            object_type="assignment_batch",
            object_id=str(batch.id),
        ).first()
        assert log is not None


def test_admin_planner_add_group_creates_row_and_log(client, csrf_token):
    with client.application.app_context():
        batch = AssignmentBatch(name="Batch 1", stage=Stage.STAGE_1, status=PlannerStatus.DRAFT)
        db.session.add(batch)
        db.session.commit()
        batch_id = batch.id

    with client.session_transaction() as session:
        session["admin_user"] = "admin"

    token = csrf_token(client.get(f"/admin/planner/batches/{batch_id}"))
    response = client.post(
        f"/admin/planner/batches/{batch_id}/groups",
        data={
            "csrf_token": token,
            "name": "Group 1",
            "language": "English",
            "target_essay_load": "4",
            "allow_same_country": "y",
            "auto_generated": "y",
            "submit": "Save group",
        },
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert response.headers["Location"] == f"/admin/planner/batches/{batch_id}"

    with client.application.app_context():
        group = ReadingGroup.query.filter_by(batch_id=batch_id, name="Group 1").first()
        assert group is not None
        assert group.language == "English"
        assert group.target_essay_load == 4
        assert group.allow_same_country is True
        assert group.auto_generated is True
        assert group.stage == Stage.STAGE_1

        log = ActivityLog.query.filter_by(
            action="group_created",
            object_type="reading_group",
            object_id=str(group.id),
        ).first()
        assert log is not None


def test_planner_teacher_choices_and_batch_view_exclude_non_assessors(client):
    with client.application.app_context():
        _create_teacher(
            first_name="Eligible",
            last_name="Assessor",
            email="eligible.assessor@example.com",
            assessor=True,
        )
        _create_teacher(
            first_name="Hidden",
            last_name="NonAssessor",
            email="hidden.nonassessor@example.com",
            assessor=False,
        )
        batch = AssignmentBatch(name="Eligibility Batch", stage=Stage.STAGE_1, status=PlannerStatus.DRAFT)
        db.session.add(batch)
        db.session.flush()
        db.session.add(
            ReadingGroup(
                name="Eligibility Group",
                language="English",
                target_essay_load=4,
                stage=Stage.STAGE_1,
                batch_id=batch.id,
            )
        )
        db.session.commit()
        batch_id = batch.id

        choices = views._planner_teacher_choices(Stage.STAGE_1)
        labels = [label for _teacher_id, label in choices]
        assert any("Eligible Assessor" in label for label in labels)
        assert not any("Hidden NonAssessor" in label for label in labels)

    with client.session_transaction() as session:
        session["admin_user"] = "admin"

    response = client.get(f"/admin/planner/batches/{batch_id}")
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "Eligible Assessor" in html
    assert "Hidden NonAssessor" not in html


def test_teacher_can_grade_rejects_non_assessor_even_with_language_and_country_match_rules(client):
    with client.application.app_context():
        student = Student(
            country="Country A",
            first_name="Student",
            last_name="One",
            email="student.one@example.com",
            school="Test School",
            date_of_birth=date(2000, 1, 1),
            essay_language="English",
            keyboard_preference="QWERTY",
            meal_preference="No preference",
        )
        teacher = Teacher(
            country="Country B",
            first_name="Teacher",
            last_name="One",
            email="teacher.one@example.com",
            school="Test School",
            languages="English",
            meal_preference="No preference",
            tshirt_size="M",
            declared_assessor_competence=False,
        )
        teacher.language_entries.append(TeacherLanguage(language="English"))
        db.session.add_all([student, teacher])
        db.session.commit()

        assert views._teacher_can_grade(student, teacher, "English") is False

        teacher.declared_assessor_competence = True
        db.session.commit()
        assert views._teacher_can_grade(student, teacher, "English") is True
