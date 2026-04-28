from datetime import date, datetime
from pathlib import Path

from ipo_app.extensions import db
from ipo_app.models import (
    AssignmentBatch,
    EssayAssignment,
    EssayAssignmentExtraReader,
    EssayScore,
    GroupMemberRole,
    PlannerStatus,
    ReadingGroup,
    ReadingGroupMember,
    Stage,
    Student,
    Teacher,
    TeacherLanguage,
)


def _login_admin(client) -> None:
    with client.session_transaction() as session:
        session["admin_user"] = "admin"


def _create_teacher(label: str, *, country: str = "Teacherland") -> int:
    teacher = Teacher(
        country=country,
        first_name="Teacher",
        last_name=label,
        email=f"{label}@example.test",
        school="Test School",
        languages="English",
        meal_preference="No preference",
        tshirt_size="M",
        declared_assessor_competence=True,
    )
    teacher.language_entries.append(TeacherLanguage(language="English"))
    db.session.add(teacher)
    db.session.commit()
    return teacher.id


def _create_student(label: str, app) -> int:
    student = Student(
        country="Studentland",
        first_name="Student",
        last_name=label,
        email=f"{label}@example.test",
        school="Test School",
        date_of_birth=date(2000, 1, 1),
        essay_language="English",
        keyboard_preference="QWERTY",
        meal_preference="No preference",
        uploaded_filename=f"{label}.pdf",
        uploaded_at=datetime.utcnow(),
        essay_finalized=True,
        essay_finalized_at=datetime.utcnow(),
    )
    db.session.add(student)
    db.session.commit()

    upload_folder = Path(app.config["UPLOAD_FOLDER"])
    upload_folder.mkdir(parents=True, exist_ok=True)
    (upload_folder / student.uploaded_filename).write_bytes(b"%PDF-1.4\n% admin grading\n%%EOF\n")
    return student.id


def _create_stage1_assignment(
    *,
    student_id: int,
    reader_ids: list[int],
    stage_two_candidate: bool = False,
    batch_id: int | None = None,
) -> int:
    if batch_id is None:
        batch = AssignmentBatch(name=f"Batch {student_id}", stage=Stage.STAGE_1, status=PlannerStatus.PUBLISHED)
        db.session.add(batch)
        db.session.flush()
        batch_id = batch.id

    group = ReadingGroup(name=f"Group {student_id}", stage=Stage.STAGE_1, language="English", batch_id=batch_id)
    db.session.add(group)
    db.session.flush()

    for teacher_id in reader_ids:
        db.session.add(
            ReadingGroupMember(
                group_id=group.id,
                teacher_id=teacher_id,
                role=GroupMemberRole.READER,
                active=True,
            )
        )

    assignment = EssayAssignment(
        student_id=student_id,
        group_id=group.id,
        batch_id=batch_id,
        stage=Stage.STAGE_1,
        status=PlannerStatus.PUBLISHED,
        stage_two_candidate=stage_two_candidate,
    )
    db.session.add(assignment)
    db.session.commit()
    return assignment.id


def _add_score(*, assignment_id: int, student_id: int, teacher_id: int, stage: Stage, score: float) -> None:
    db.session.add(
        EssayScore(
            assignment_id=assignment_id,
            student_id=student_id,
            teacher_id=teacher_id,
            stage=stage,
            score=score,
            submitted_at=datetime.utcnow(),
        )
    )


def _add_stage1_extra_reader(*, assignment_id: int, teacher_id: int) -> None:
    db.session.add(
        EssayAssignmentExtraReader(
            assignment_id=assignment_id,
            teacher_id=teacher_id,
            stage=Stage.STAGE_1.value,
        )
    )


def test_admin_stage1_rejects_non_statutory_score(client, csrf_token):
    with client.application.app_context():
        teacher_id = _create_teacher("stage1-reader")
        student_id = _create_student("stage1-invalid-score", client.application)
        assignment_id = _create_stage1_assignment(student_id=student_id, reader_ids=[teacher_id])

    _login_admin(client)
    page = client.get(f"/admin/uploads/{student_id}/scores")
    token = csrf_token(page)

    response = client.post(
        f"/admin/uploads/{student_id}/scores",
        data={
            "csrf_token": token,
            "action": "update_scores",
            f"score_{teacher_id}": "7.76",
        },
        follow_redirects=False,
    )

    assert response.status_code == 302
    with client.application.app_context():
        assert (
            EssayScore.query
            .filter_by(assignment_id=assignment_id, teacher_id=teacher_id, stage=Stage.STAGE_1)
            .all()
            == []
        )


def test_admin_stage2_rejects_non_statutory_score(client, csrf_token):
    with client.application.app_context():
        stage1_reader_id = _create_teacher("stage2-stage1-reader")
        stage2_reader_id = _create_teacher("stage2-reader")
        student_id = _create_student("stage2-invalid-score", client.application)
        assignment_id = _create_stage1_assignment(
            student_id=student_id,
            reader_ids=[stage1_reader_id],
            stage_two_candidate=True,
        )
        db.session.add(
            EssayAssignmentExtraReader(
                assignment_id=assignment_id,
                teacher_id=stage2_reader_id,
                stage=Stage.STAGE_2.value,
            )
        )
        db.session.commit()

    _login_admin(client)
    page = client.get(f"/admin/stage2/{student_id}")
    token = csrf_token(page)

    response = client.post(
        f"/admin/stage2/{student_id}",
        data={
            "csrf_token": token,
            "action": "update_scores",
            f"score_{stage2_reader_id}": "7.76",
        },
        follow_redirects=False,
    )

    assert response.status_code == 302
    with client.application.app_context():
        assert (
            EssayScore.query
            .filter_by(assignment_id=assignment_id, teacher_id=stage2_reader_id, stage=Stage.STAGE_2)
            .all()
            == []
        )


def test_admin_stage1_jump_uses_public_essay_id_not_assignment_id(client):
    with client.application.app_context():
        _create_student("jump-dummy-a", client.application)
        _create_student("jump-dummy-b", client.application)
        teacher_id = _create_teacher("jump-stage1-reader")
        student_id = _create_student("jump-stage1-public-id", client.application)
        assignment_id = _create_stage1_assignment(student_id=student_id, reader_ids=[teacher_id])
        assert assignment_id != student_id

    _login_admin(client)

    response = client.get(
        f"/admin/essays/jump?stage=stage_1&essay_id={student_id}",
        follow_redirects=False,
    )
    assert response.status_code == 302
    assert response.headers["Location"] == f"/admin/uploads/{student_id}/scores"

    assignment_id_response = client.get(
        f"/admin/essays/jump?stage=stage_1&essay_id={assignment_id}",
        follow_redirects=False,
    )
    assert assignment_id_response.status_code == 302
    assert assignment_id_response.headers["Location"].endswith("/admin/uploads")


def test_admin_stage2_jump_opens_candidate_and_falls_back_to_stage1(client):
    with client.application.app_context():
        batch = AssignmentBatch(name="Jump Batch", stage=Stage.STAGE_1, status=PlannerStatus.PUBLISHED)
        db.session.add(batch)
        db.session.flush()

        candidate_reader_id = _create_teacher("jump-stage2-candidate-stage1")
        candidate_stage2_id = _create_teacher("jump-stage2-candidate-reader")
        candidate_student_id = _create_student("jump-stage2-candidate", client.application)
        candidate_assignment_id = _create_stage1_assignment(
            student_id=candidate_student_id,
            reader_ids=[candidate_reader_id],
            stage_two_candidate=True,
            batch_id=batch.id,
        )
        db.session.add(
            EssayAssignmentExtraReader(
                assignment_id=candidate_assignment_id,
                teacher_id=candidate_stage2_id,
                stage=Stage.STAGE_2.value,
            )
        )

        noncandidate_reader_id = _create_teacher("jump-stage2-noncandidate-reader")
        noncandidate_student_id = _create_student("jump-stage2-noncandidate", client.application)
        _create_stage1_assignment(
            student_id=noncandidate_student_id,
            reader_ids=[noncandidate_reader_id],
            batch_id=batch.id,
        )
        db.session.commit()

    _login_admin(client)

    candidate = client.get(
        f"/admin/essays/jump?stage=stage_2&essay_id={candidate_student_id}",
        follow_redirects=False,
    )
    assert candidate.status_code == 302
    assert candidate.headers["Location"] == f"/admin/stage2/{candidate_student_id}"

    noncandidate = client.get(
        f"/admin/essays/jump?stage=stage_2&essay_id={noncandidate_student_id}",
        follow_redirects=False,
    )
    assert noncandidate.status_code == 302
    assert noncandidate.headers["Location"] == f"/admin/uploads/{noncandidate_student_id}/scores"


def test_admin_stage_overviews_show_essay_id_jump_controls(client):
    with client.application.app_context():
        teacher_id = _create_teacher("overview-jump-reader")
        student_id = _create_student("overview-jump-student", client.application)
        _create_stage1_assignment(student_id=student_id, reader_ids=[teacher_id], stage_two_candidate=True)

    _login_admin(client)

    stage1 = client.get("/admin/uploads")
    assert stage1.status_code == 200
    stage1_html = stage1.get_data(as_text=True)
    assert "Essay ID" in stage1_html
    assert 'name="essay_id"' in stage1_html
    assert 'value="stage_1"' in stage1_html

    stage2 = client.get("/admin/stage2")
    assert stage2.status_code == 200
    stage2_html = stage2.get_data(as_text=True)
    assert "Essay ID" in stage2_html
    assert 'name="essay_id"' in stage2_html
    assert 'value="stage_2"' in stage2_html


def test_dashboard_surfaces_additional_assessor_queue(client):
    with client.application.app_context():
        batch = AssignmentBatch(name="Extra Reader Batch", stage=Stage.STAGE_1, status=PlannerStatus.PUBLISHED)
        db.session.add(batch)
        db.session.flush()

        base_a = _create_teacher("extra-base-a")
        base_b = _create_teacher("extra-base-b")
        extra_a = _create_teacher("extra-assigned-a")
        extra_b = _create_teacher("extra-assigned-b")
        extra_c = _create_teacher("extra-resolved")

        needs_assignment_student = _create_student("extra-needs-assignment", client.application)
        needs_assignment_id = _create_stage1_assignment(
            student_id=needs_assignment_student,
            reader_ids=[base_a, base_b],
            batch_id=batch.id,
        )
        _add_score(assignment_id=needs_assignment_id, student_id=needs_assignment_student, teacher_id=base_a, stage=Stage.STAGE_1, score=5)
        _add_score(assignment_id=needs_assignment_id, student_id=needs_assignment_student, teacher_id=base_b, stage=Stage.STAGE_1, score=9)
        db.session.get(EssayAssignment, needs_assignment_id).needs_additional_reading = True

        awaiting_student = _create_student("extra-awaiting-score", client.application)
        awaiting_id = _create_stage1_assignment(
            student_id=awaiting_student,
            reader_ids=[base_a, base_b],
            batch_id=batch.id,
        )
        _add_score(assignment_id=awaiting_id, student_id=awaiting_student, teacher_id=base_a, stage=Stage.STAGE_1, score=5)
        _add_score(assignment_id=awaiting_id, student_id=awaiting_student, teacher_id=base_b, stage=Stage.STAGE_1, score=9)
        _add_stage1_extra_reader(assignment_id=awaiting_id, teacher_id=extra_a)
        db.session.get(EssayAssignment, awaiting_id).needs_additional_reading = True

        review_student = _create_student("extra-review-spread", client.application)
        review_id = _create_stage1_assignment(
            student_id=review_student,
            reader_ids=[base_a, base_b],
            batch_id=batch.id,
        )
        _add_score(assignment_id=review_id, student_id=review_student, teacher_id=base_a, stage=Stage.STAGE_1, score=5)
        _add_score(assignment_id=review_id, student_id=review_student, teacher_id=base_b, stage=Stage.STAGE_1, score=9)
        _add_stage1_extra_reader(assignment_id=review_id, teacher_id=extra_b)
        _add_score(assignment_id=review_id, student_id=review_student, teacher_id=extra_b, stage=Stage.STAGE_1, score=9)
        db.session.get(EssayAssignment, review_id).needs_additional_reading = True

        resolved_student = _create_student("extra-resolved-student", client.application)
        resolved_id = _create_stage1_assignment(
            student_id=resolved_student,
            reader_ids=[base_a, base_b],
            batch_id=batch.id,
        )
        _add_score(assignment_id=resolved_id, student_id=resolved_student, teacher_id=base_a, stage=Stage.STAGE_1, score=7)
        _add_score(assignment_id=resolved_id, student_id=resolved_student, teacher_id=base_b, stage=Stage.STAGE_1, score=8)
        _add_stage1_extra_reader(assignment_id=resolved_id, teacher_id=extra_c)
        _add_score(assignment_id=resolved_id, student_id=resolved_student, teacher_id=extra_c, stage=Stage.STAGE_1, score=7.5)
        db.session.commit()

    _login_admin(client)
    response = client.get("/admin")
    assert response.status_code == 200
    html = response.get_data(as_text=True)

    assert "Additional Assessors" in html
    assert "3" in html
    assert "1 need assignment" in html
    assert "1 awaiting extra score" in html
    assert "1 need spread review" in html
    assert "1 resolved after extra reading" in html
    assert "Needs extra reader assignment" in html
    assert "Extra reader assigned; awaiting score" in html
    assert "Extra score entered; review spread" in html
    assert "/admin/uploads?status=needs_extra" in html


def test_stage1_extra_reader_filters_limit_overview_rows(client):
    with client.application.app_context():
        batch = AssignmentBatch(name="Extra Reader Filter Batch", stage=Stage.STAGE_1, status=PlannerStatus.PUBLISHED)
        db.session.add(batch)
        db.session.flush()

        base_a = _create_teacher("filter-base-a")
        base_b = _create_teacher("filter-base-b")
        extra_reader = _create_teacher("filter-extra-reader")

        needs_assignment_student = _create_student("filter-needs-assignment", client.application)
        needs_assignment_id = _create_stage1_assignment(
            student_id=needs_assignment_student,
            reader_ids=[base_a, base_b],
            batch_id=batch.id,
        )
        _add_score(assignment_id=needs_assignment_id, student_id=needs_assignment_student, teacher_id=base_a, stage=Stage.STAGE_1, score=5)
        _add_score(assignment_id=needs_assignment_id, student_id=needs_assignment_student, teacher_id=base_b, stage=Stage.STAGE_1, score=9)
        db.session.get(EssayAssignment, needs_assignment_id).needs_additional_reading = True

        awaiting_student = _create_student("filter-awaiting-score", client.application)
        awaiting_id = _create_stage1_assignment(
            student_id=awaiting_student,
            reader_ids=[base_a, base_b],
            batch_id=batch.id,
        )
        _add_score(assignment_id=awaiting_id, student_id=awaiting_student, teacher_id=base_a, stage=Stage.STAGE_1, score=5)
        _add_score(assignment_id=awaiting_id, student_id=awaiting_student, teacher_id=base_b, stage=Stage.STAGE_1, score=9)
        _add_stage1_extra_reader(assignment_id=awaiting_id, teacher_id=extra_reader)
        db.session.get(EssayAssignment, awaiting_id).needs_additional_reading = True
        db.session.commit()

    _login_admin(client)
    response = client.get("/admin/uploads?status=extra_needs_assignment")
    assert response.status_code == 200
    html = response.get_data(as_text=True)

    assert "filter-needs-assignment" in html
    assert "Needs extra reader assignment" in html
    assert "filter-awaiting-score" not in html
    assert "Extra reader assigned; awaiting score" not in html
