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
        base_c = _create_teacher("extra-base-c")
        base_d = _create_teacher("extra-base-d")
        extra_a = _create_teacher("extra-assigned-a")
        extra_b = _create_teacher("extra-assigned-b")
        extra_d = _create_teacher("extra-assigned-d")
        extra_e = _create_teacher("extra-assigned-e")
        extra_c = _create_teacher("extra-resolved")

        needs_assignment_student = _create_student("extra-needs-assignment", client.application)
        needs_assignment_id = _create_stage1_assignment(
            student_id=needs_assignment_student,
            reader_ids=[base_a, base_b, base_c, base_d],
            batch_id=batch.id,
        )
        _add_score(assignment_id=needs_assignment_id, student_id=needs_assignment_student, teacher_id=base_a, stage=Stage.STAGE_1, score=5)
        _add_score(assignment_id=needs_assignment_id, student_id=needs_assignment_student, teacher_id=base_b, stage=Stage.STAGE_1, score=9)
        _add_score(assignment_id=needs_assignment_id, student_id=needs_assignment_student, teacher_id=base_c, stage=Stage.STAGE_1, score=5)
        _add_score(assignment_id=needs_assignment_id, student_id=needs_assignment_student, teacher_id=base_d, stage=Stage.STAGE_1, score=9)
        db.session.get(EssayAssignment, needs_assignment_id).needs_additional_reading = True

        awaiting_student = _create_student("extra-awaiting-score", client.application)
        awaiting_id = _create_stage1_assignment(
            student_id=awaiting_student,
            reader_ids=[base_a, base_b, base_c, base_d],
            batch_id=batch.id,
        )
        _add_score(assignment_id=awaiting_id, student_id=awaiting_student, teacher_id=base_a, stage=Stage.STAGE_1, score=5)
        _add_score(assignment_id=awaiting_id, student_id=awaiting_student, teacher_id=base_b, stage=Stage.STAGE_1, score=9)
        _add_score(assignment_id=awaiting_id, student_id=awaiting_student, teacher_id=base_c, stage=Stage.STAGE_1, score=5)
        _add_score(assignment_id=awaiting_id, student_id=awaiting_student, teacher_id=base_d, stage=Stage.STAGE_1, score=9)
        _add_stage1_extra_reader(assignment_id=awaiting_id, teacher_id=extra_a)
        _add_stage1_extra_reader(assignment_id=awaiting_id, teacher_id=extra_d)
        db.session.get(EssayAssignment, awaiting_id).needs_additional_reading = True

        review_student = _create_student("extra-review-spread", client.application)
        review_id = _create_stage1_assignment(
            student_id=review_student,
            reader_ids=[base_a, base_b, base_c, base_d],
            batch_id=batch.id,
        )
        _add_score(assignment_id=review_id, student_id=review_student, teacher_id=base_a, stage=Stage.STAGE_1, score=5)
        _add_score(assignment_id=review_id, student_id=review_student, teacher_id=base_b, stage=Stage.STAGE_1, score=9)
        _add_score(assignment_id=review_id, student_id=review_student, teacher_id=base_c, stage=Stage.STAGE_1, score=5)
        _add_score(assignment_id=review_id, student_id=review_student, teacher_id=base_d, stage=Stage.STAGE_1, score=9)
        _add_stage1_extra_reader(assignment_id=review_id, teacher_id=extra_b)
        _add_stage1_extra_reader(assignment_id=review_id, teacher_id=extra_e)
        _add_score(assignment_id=review_id, student_id=review_student, teacher_id=extra_b, stage=Stage.STAGE_1, score=9)
        _add_score(assignment_id=review_id, student_id=review_student, teacher_id=extra_e, stage=Stage.STAGE_1, score=8)
        db.session.get(EssayAssignment, review_id).needs_additional_reading = True

        resolved_student = _create_student("extra-resolved-student", client.application)
        resolved_id = _create_stage1_assignment(
            student_id=resolved_student,
            reader_ids=[base_a, base_b, base_c, base_d],
            batch_id=batch.id,
        )
        _add_score(assignment_id=resolved_id, student_id=resolved_student, teacher_id=base_a, stage=Stage.STAGE_1, score=7)
        _add_score(assignment_id=resolved_id, student_id=resolved_student, teacher_id=base_b, stage=Stage.STAGE_1, score=8)
        _add_score(assignment_id=resolved_id, student_id=resolved_student, teacher_id=base_c, stage=Stage.STAGE_1, score=7)
        _add_score(assignment_id=resolved_id, student_id=resolved_student, teacher_id=base_d, stage=Stage.STAGE_1, score=8)
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
    assert "1 awaiting extra scores" in html
    assert "1 need spread review" in html
    assert "1 resolved after extra reading" in html
    assert "Needs 2 additional reader assignments" in html
    assert "Additional reader assigned; awaiting score" in html
    assert "Additional scores entered; review spread" in html
    assert "/admin/uploads?status=needs_extra" in html


def test_dashboard_stage_metrics_are_scoped_to_active_published_batch(client):
    with client.application.app_context():
        active_batch = AssignmentBatch(name="Active Dashboard Batch", stage=Stage.STAGE_1, status=PlannerStatus.PUBLISHED)
        draft_batch = AssignmentBatch(name="Draft Dashboard Batch", stage=Stage.STAGE_1, status=PlannerStatus.DRAFT)
        db.session.add_all([active_batch, draft_batch])
        db.session.flush()

        active_reader = _create_teacher("dashboard-active-reader")
        draft_reader = _create_teacher("dashboard-draft-reader")
        active_student = _create_student("dashboard-active-student", client.application)
        draft_student = _create_student("dashboard-draft-student", client.application)
        _create_stage1_assignment(
            student_id=active_student,
            reader_ids=[active_reader],
            batch_id=active_batch.id,
        )
        _create_stage1_assignment(
            student_id=draft_student,
            reader_ids=[draft_reader],
            batch_id=draft_batch.id,
        )
        db.session.commit()

    _login_admin(client)
    response = client.get("/admin")
    assert response.status_code == 200
    html = response.get_data(as_text=True)

    assert "Active Dashboard Batch" in html
    assert "1 assigned essays" in html
    assert "dashboard-active-student" in html
    assert "dashboard-draft-student" not in html


def test_dashboard_action_queue_surfaces_group_coverage_and_can_assign_supplemental_reader(client, csrf_token):
    with client.application.app_context():
        batch = AssignmentBatch(name="Coverage Dashboard Batch", stage=Stage.STAGE_1, status=PlannerStatus.PUBLISHED)
        target_group = ReadingGroup(
            name="Coverage Target",
            stage=Stage.STAGE_1,
            language="English",
            status=PlannerStatus.PUBLISHED,
            batch=batch,
        )
        source_group = ReadingGroup(
            name="Coverage Source",
            stage=Stage.STAGE_1,
            language="English",
            status=PlannerStatus.PUBLISHED,
            batch=batch,
        )
        db.session.add_all([batch, target_group, source_group])
        db.session.flush()

        base_a = _create_teacher("coverage-base-a", country="Base A")
        base_b = _create_teacher("coverage-base-b", country="Base B")
        free_teacher = _create_teacher("coverage-free-reader", country="Free Country")
        target_student_a = _create_student("coverage-target-a", client.application)
        target_student_b = _create_student("coverage-target-b", client.application)
        source_student = _create_student("coverage-source", client.application)

        db.session.add_all(
            [
                ReadingGroupMember(group_id=target_group.id, teacher_id=base_a, role=GroupMemberRole.LEADER, active=True),
                ReadingGroupMember(group_id=target_group.id, teacher_id=base_b, role=GroupMemberRole.READER, active=True),
                ReadingGroupMember(group_id=source_group.id, teacher_id=free_teacher, role=GroupMemberRole.LEADER, active=True),
            ]
        )
        target_assignment_a = EssayAssignment(
            student_id=target_student_a,
            group_id=target_group.id,
            batch_id=batch.id,
            stage=Stage.STAGE_1,
            status=PlannerStatus.PUBLISHED,
        )
        target_assignment_b = EssayAssignment(
            student_id=target_student_b,
            group_id=target_group.id,
            batch_id=batch.id,
            stage=Stage.STAGE_1,
            status=PlannerStatus.PUBLISHED,
        )
        source_assignment = EssayAssignment(
            student_id=source_student,
            group_id=source_group.id,
            batch_id=batch.id,
            stage=Stage.STAGE_1,
            status=PlannerStatus.PUBLISHED,
        )
        db.session.add_all([target_assignment_a, target_assignment_b, source_assignment])
        db.session.flush()
        _add_score(
            assignment_id=source_assignment.id,
            student_id=source_student,
            teacher_id=free_teacher,
            stage=Stage.STAGE_1,
            score=8,
        )
        source_score = EssayScore.query.filter_by(
            assignment_id=source_assignment.id,
            teacher_id=free_teacher,
            stage=Stage.STAGE_1,
        ).first()
        source_score.teacher_finalized = True
        source_score.teacher_finalized_at = datetime.utcnow()
        db.session.commit()

        batch_id = batch.id
        target_group_id = target_group.id
        free_teacher_id = free_teacher
        target_assignment_ids = {target_assignment_a.id, target_assignment_b.id}

    _login_admin(client)
    page = client.get("/admin")
    assert page.status_code == 200
    html = page.get_data(as_text=True)

    assert "Action queue" in html
    assert "Coverage Target: reader coverage below four" in html
    assert "2 essays affected; 4 reader assignments missing." in html
    assert "coverage-free-reader" in html

    token = csrf_token(page)
    response = client.post(
        f"/admin/planner/batches/{batch_id}/groups/{target_group_id}/supplemental-readers",
        data={
            "csrf_token": token,
            "teacher_id": str(free_teacher_id),
            "redirect": "/admin",
        },
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/admin")
    with client.application.app_context():
        assigned = EssayAssignmentExtraReader.query.filter(
            EssayAssignmentExtraReader.assignment_id.in_(target_assignment_ids),
            EssayAssignmentExtraReader.teacher_id == free_teacher_id,
            EssayAssignmentExtraReader.stage == Stage.STAGE_1.value,
        ).count()
        assert assigned == 2


def test_dashboard_upload_rescue_includes_unfinalized_and_missing_files(client):
    with client.application.app_context():
        missing_upload = Student(
            country="Studentland",
            first_name="Upload",
            last_name="Missing",
            email="upload-missing@example.test",
            school="Test School",
            date_of_birth=date(2000, 1, 1),
            essay_language="English",
            keyboard_preference="QWERTY",
            meal_preference="No preference",
        )
        unfinalized = Student(
            country="Studentland",
            first_name="Upload",
            last_name="Unfinalized",
            email="upload-unfinalized@example.test",
            school="Test School",
            date_of_birth=date(2000, 1, 1),
            essay_language="English",
            keyboard_preference="QWERTY",
            meal_preference="No preference",
            uploaded_filename="upload-unfinalized.pdf",
            uploaded_at=datetime.utcnow(),
            essay_finalized=False,
        )
        missing_file = Student(
            country="Studentland",
            first_name="Upload",
            last_name="FileMissing",
            email="upload-file-missing@example.test",
            school="Test School",
            date_of_birth=date(2000, 1, 1),
            essay_language="English",
            keyboard_preference="QWERTY",
            meal_preference="No preference",
            uploaded_filename="upload-file-missing.pdf",
            uploaded_at=datetime.utcnow(),
            essay_finalized=True,
            essay_finalized_at=datetime.utcnow(),
        )
        db.session.add_all([missing_upload, unfinalized, missing_file])
        db.session.commit()

        upload_folder = Path(client.application.config["UPLOAD_FOLDER"])
        upload_folder.mkdir(parents=True, exist_ok=True)
        (upload_folder / "upload-unfinalized.pdf").write_bytes(b"%PDF-1.4\n% unfinalized\n%%EOF\n")

    _login_admin(client)
    response = client.get("/admin")
    assert response.status_code == 200
    html = response.get_data(as_text=True)

    assert "Upload rescue" in html
    assert "Missing upload" in html
    assert "Not finalized" in html
    assert "File missing" in html
    assert "Upload Unfinalized" in html


def test_stage1_extra_reader_filters_limit_overview_rows(client):
    with client.application.app_context():
        batch = AssignmentBatch(name="Extra Reader Filter Batch", stage=Stage.STAGE_1, status=PlannerStatus.PUBLISHED)
        db.session.add(batch)
        db.session.flush()

        base_a = _create_teacher("filter-base-a")
        base_b = _create_teacher("filter-base-b")
        base_c = _create_teacher("filter-base-c")
        base_d = _create_teacher("filter-base-d")
        extra_reader = _create_teacher("filter-extra-reader")
        second_extra_reader = _create_teacher("filter-second-extra-reader")

        needs_assignment_student = _create_student("filter-needs-assignment", client.application)
        needs_assignment_id = _create_stage1_assignment(
            student_id=needs_assignment_student,
            reader_ids=[base_a, base_b, base_c, base_d],
            batch_id=batch.id,
        )
        _add_score(assignment_id=needs_assignment_id, student_id=needs_assignment_student, teacher_id=base_a, stage=Stage.STAGE_1, score=5)
        _add_score(assignment_id=needs_assignment_id, student_id=needs_assignment_student, teacher_id=base_b, stage=Stage.STAGE_1, score=9)
        _add_score(assignment_id=needs_assignment_id, student_id=needs_assignment_student, teacher_id=base_c, stage=Stage.STAGE_1, score=5)
        _add_score(assignment_id=needs_assignment_id, student_id=needs_assignment_student, teacher_id=base_d, stage=Stage.STAGE_1, score=9)
        db.session.get(EssayAssignment, needs_assignment_id).needs_additional_reading = True

        awaiting_student = _create_student("filter-awaiting-score", client.application)
        awaiting_id = _create_stage1_assignment(
            student_id=awaiting_student,
            reader_ids=[base_a, base_b, base_c, base_d],
            batch_id=batch.id,
        )
        _add_score(assignment_id=awaiting_id, student_id=awaiting_student, teacher_id=base_a, stage=Stage.STAGE_1, score=5)
        _add_score(assignment_id=awaiting_id, student_id=awaiting_student, teacher_id=base_b, stage=Stage.STAGE_1, score=9)
        _add_score(assignment_id=awaiting_id, student_id=awaiting_student, teacher_id=base_c, stage=Stage.STAGE_1, score=5)
        _add_score(assignment_id=awaiting_id, student_id=awaiting_student, teacher_id=base_d, stage=Stage.STAGE_1, score=9)
        _add_stage1_extra_reader(assignment_id=awaiting_id, teacher_id=extra_reader)
        _add_stage1_extra_reader(assignment_id=awaiting_id, teacher_id=second_extra_reader)
        db.session.get(EssayAssignment, awaiting_id).needs_additional_reading = True
        db.session.commit()

    _login_admin(client)
    response = client.get("/admin/uploads?status=extra_needs_assignment")
    assert response.status_code == 200
    html = response.get_data(as_text=True)

    assert "filter-needs-assignment" in html
    assert "Needs reader" in html
    assert "filter-awaiting-score" not in html
    assert "Awaiting score" not in html
