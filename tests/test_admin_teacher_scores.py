from datetime import date, datetime

import pytest

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


def _create_teacher(label: str, *, country: str = "Teacherland") -> Teacher:
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
    db.session.flush()
    return teacher


def _create_student(label: str, *, country: str = "Studentland") -> Student:
    student = Student(
        country=country,
        first_name="Student",
        last_name=label,
        email=f"{label}@example.test",
        school="Test School",
        date_of_birth=date(2000, 1, 1),
        essay_language="English",
        keyboard_preference="QWERTY",
        meal_preference="No preference",
        uploaded_at=datetime.utcnow(),
        essay_finalized=True,
        essay_finalized_at=datetime.utcnow(),
    )
    db.session.add(student)
    db.session.flush()
    return student


def _create_batch() -> AssignmentBatch:
    batch = AssignmentBatch(name="Teacher Scores Batch", stage=Stage.STAGE_1, status=PlannerStatus.PUBLISHED)
    db.session.add(batch)
    db.session.flush()
    return batch


def _create_group(batch: AssignmentBatch, label: str = "Group") -> ReadingGroup:
    group = ReadingGroup(
        name=label,
        stage=Stage.STAGE_1,
        language="English",
        status=PlannerStatus.PUBLISHED,
        batch_id=batch.id,
    )
    db.session.add(group)
    db.session.flush()
    return group


def _add_reader(group: ReadingGroup, teacher: Teacher) -> None:
    db.session.add(
        ReadingGroupMember(
            group_id=group.id,
            teacher_id=teacher.id,
            role=GroupMemberRole.READER,
            active=True,
        )
    )


def _create_assignment(
    *,
    batch: AssignmentBatch,
    group: ReadingGroup,
    student: Student,
    stage_two_candidate: bool = False,
) -> EssayAssignment:
    assignment = EssayAssignment(
        student_id=student.id,
        group_id=group.id,
        batch_id=batch.id,
        stage=Stage.STAGE_1,
        status=PlannerStatus.PUBLISHED,
        stage_two_candidate=stage_two_candidate,
    )
    db.session.add(assignment)
    db.session.flush()
    return assignment


def _add_score(
    *,
    assignment: EssayAssignment,
    student: Student,
    teacher: Teacher,
    stage: Stage,
    score: float,
    finalized: bool = False,
) -> EssayScore:
    score_record = EssayScore(
        assignment_id=assignment.id,
        student_id=student.id,
        teacher_id=teacher.id,
        stage=stage,
        score=score,
        submitted_at=datetime.utcnow(),
        teacher_finalized=finalized,
        teacher_finalized_at=datetime.utcnow() if finalized else None,
    )
    db.session.add(score_record)
    db.session.flush()
    return score_record


def test_teacher_actions_include_scores_link(client):
    with client.application.app_context():
        teacher = _create_teacher("scores-action")
        db.session.commit()
        teacher_id = teacher.id

    _login_admin(client)
    response = client.get("/admin/teachers")

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert f"/admin/teachers/{teacher_id}/scores" in html
    assert "Scores" in html


def test_teacher_scores_page_lists_stage1_and_stage2_assignments(client):
    with client.application.app_context():
        batch = _create_batch()
        target = _create_teacher("listed-target")
        other = _create_teacher("listed-other")
        group = _create_group(batch, "Listed Group")
        _add_reader(group, target)
        _add_reader(group, other)

        stage1_student = _create_student("listed-stage1")
        stage1_assignment = _create_assignment(batch=batch, group=group, student=stage1_student)

        extra_group = _create_group(batch, "Extra Group")
        _add_reader(extra_group, other)
        extra_student = _create_student("listed-extra")
        extra_assignment = _create_assignment(batch=batch, group=extra_group, student=extra_student)
        db.session.add(
            EssayAssignmentExtraReader(
                assignment_id=extra_assignment.id,
                teacher_id=target.id,
                stage=Stage.STAGE_1.value,
            )
        )

        stage2_student = _create_student("listed-stage2")
        stage2_assignment = _create_assignment(
            batch=batch,
            group=group,
            student=stage2_student,
            stage_two_candidate=True,
        )
        db.session.add(
            EssayAssignmentExtraReader(
                assignment_id=stage2_assignment.id,
                teacher_id=target.id,
                stage=Stage.STAGE_2.value,
            )
        )

        unassigned_group = _create_group(batch, "Unassigned Group")
        _add_reader(unassigned_group, other)
        unassigned_student = _create_student("listed-unassigned")
        _create_assignment(batch=batch, group=unassigned_group, student=unassigned_student)
        db.session.commit()
        teacher_id = target.id
        expected_ids = {stage1_student.id, extra_student.id, stage2_student.id}
        unexpected_id = unassigned_student.id
        stage1_assignment_id = stage1_assignment.id

    _login_admin(client)
    response = client.get(f"/admin/teachers/{teacher_id}/scores")

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    for essay_id in expected_ids:
        assert f"<td>{essay_id}</td>" in html
    assert f"<td>{unexpected_id}</td>" not in html
    assert "Listed Group" in html
    assert "Extra reader" in html
    assert "Stage 2 reader" in html
    assert f'name="score_{stage1_assignment_id}"' in html


def test_teacher_scores_stage1_save_creates_admin_score_and_recomputes_rules(client, csrf_token):
    with client.application.app_context():
        batch = _create_batch()
        target = _create_teacher("stage1-save-target")
        other_readers = [_create_teacher(f"stage1-save-other-{index}") for index in range(3)]
        group = _create_group(batch, "Stage 1 Save Group")
        _add_reader(group, target)
        for reader in other_readers:
            _add_reader(group, reader)

        student = _create_student("stage1-save")
        assignment = _create_assignment(batch=batch, group=group, student=student)
        for reader in other_readers:
            _add_score(assignment=assignment, student=student, teacher=reader, stage=Stage.STAGE_1, score=7)
        db.session.commit()
        teacher_id = target.id
        assignment_id = assignment.id
        student_id = student.id

    _login_admin(client)
    page = client.get(f"/admin/teachers/{teacher_id}/scores")
    token = csrf_token(page)
    response = client.post(
        f"/admin/teachers/{teacher_id}/scores",
        data={
            "csrf_token": token,
            "action": "update_scores",
            "stage": Stage.STAGE_1.value,
            f"score_{assignment_id}": "8",
        },
        follow_redirects=False,
    )

    assert response.status_code == 302
    with client.application.app_context():
        score = EssayScore.query.filter_by(
            assignment_id=assignment_id,
            teacher_id=teacher_id,
            stage=Stage.STAGE_1,
        ).first()
        assignment = db.session.get(EssayAssignment, assignment_id)
        assert score is not None
        assert score.score == pytest.approx(8)
        assert score.admin_entered is True
        assert score.admin_override is False
        assert score.teacher_finalized is False
        assert assignment.stage_two_candidate is True
        assert assignment.student_id == student_id


def test_teacher_scores_rejects_invalid_score_without_partial_save(client, csrf_token):
    with client.application.app_context():
        batch = _create_batch()
        teacher = _create_teacher("invalid-target")
        group = _create_group(batch, "Invalid Group")
        _add_reader(group, teacher)
        student_a = _create_student("invalid-a")
        student_b = _create_student("invalid-b")
        assignment_a = _create_assignment(batch=batch, group=group, student=student_a)
        assignment_b = _create_assignment(batch=batch, group=group, student=student_b)
        db.session.commit()
        teacher_id = teacher.id
        assignment_a_id = assignment_a.id
        assignment_b_id = assignment_b.id

    _login_admin(client)
    page = client.get(f"/admin/teachers/{teacher_id}/scores")
    token = csrf_token(page)
    response = client.post(
        f"/admin/teachers/{teacher_id}/scores",
        data={
            "csrf_token": token,
            "action": "update_scores",
            "stage": Stage.STAGE_1.value,
            f"score_{assignment_a_id}": "8",
            f"score_{assignment_b_id}": "7.76",
        },
        follow_redirects=False,
    )

    assert response.status_code == 302
    with client.application.app_context():
        assert EssayScore.query.filter_by(assignment_id=assignment_a_id, teacher_id=teacher_id).first() is None
        assert EssayScore.query.filter_by(assignment_id=assignment_b_id, teacher_id=teacher_id).first() is None


def test_teacher_scores_update_finalized_score_marks_admin_override_and_reopens(client, csrf_token):
    with client.application.app_context():
        batch = _create_batch()
        teacher = _create_teacher("override-target")
        group = _create_group(batch, "Override Group")
        _add_reader(group, teacher)
        student = _create_student("override-student")
        assignment = _create_assignment(batch=batch, group=group, student=student)
        _add_score(
            assignment=assignment,
            student=student,
            teacher=teacher,
            stage=Stage.STAGE_1,
            score=6,
            finalized=True,
        )
        db.session.commit()
        teacher_id = teacher.id
        assignment_id = assignment.id

    _login_admin(client)
    page = client.get(f"/admin/teachers/{teacher_id}/scores")
    token = csrf_token(page)
    response = client.post(
        f"/admin/teachers/{teacher_id}/scores",
        data={
            "csrf_token": token,
            "action": "update_scores",
            "stage": Stage.STAGE_1.value,
            f"score_{assignment_id}": "8.5",
        },
        follow_redirects=False,
    )

    assert response.status_code == 302
    with client.application.app_context():
        score = EssayScore.query.filter_by(
            assignment_id=assignment_id,
            teacher_id=teacher_id,
            stage=Stage.STAGE_1,
        ).first()
        assert score.score == pytest.approx(8.5)
        assert score.admin_override is True
        assert score.admin_entered is False
        assert score.teacher_finalized is False
        assert score.teacher_finalized_at is None


def test_teacher_scores_stage2_save_creates_admin_score(client, csrf_token):
    with client.application.app_context():
        batch = _create_batch()
        teacher = _create_teacher("stage2-target")
        group = _create_group(batch, "Stage 2 Group")
        student = _create_student("stage2-student")
        assignment = _create_assignment(batch=batch, group=group, student=student, stage_two_candidate=True)
        db.session.add(
            EssayAssignmentExtraReader(
                assignment_id=assignment.id,
                teacher_id=teacher.id,
                stage=Stage.STAGE_2.value,
            )
        )
        db.session.commit()
        teacher_id = teacher.id
        assignment_id = assignment.id

    _login_admin(client)
    page = client.get(f"/admin/teachers/{teacher_id}/scores")
    token = csrf_token(page)
    response = client.post(
        f"/admin/teachers/{teacher_id}/scores",
        data={
            "csrf_token": token,
            "action": "update_scores",
            "stage": Stage.STAGE_2.value,
            f"score_{assignment_id}": "9",
        },
        follow_redirects=False,
    )

    assert response.status_code == 302
    with client.application.app_context():
        score = EssayScore.query.filter_by(
            assignment_id=assignment_id,
            teacher_id=teacher_id,
            stage=Stage.STAGE_2,
        ).first()
        assert score is not None
        assert score.score == pytest.approx(9)
        assert score.admin_entered is True
        assert score.admin_override is False
