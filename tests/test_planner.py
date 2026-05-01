from ipo_app.extensions import db
from datetime import date, datetime
from io import BytesIO
from pathlib import Path

import ipo_app.views as views
from ipo_app.models import (
    ActivityLog,
    AssignmentBatch,
    EssayAssignment,
    EssayAssignmentExtraReader,
    EssayScore,
    GroupMemberRole,
    PlannerAlgorithm,
    PlannerStatus,
    ReadingGroup,
    ReadingGroupMember,
    Stage,
    Student,
    Teacher,
    TeacherLanguage,
)
from PyPDF2 import PdfReader
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas


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


def _create_assessor(
    index: int,
    *,
    country: str | None = None,
    languages: tuple[str, ...] = ("English",),
) -> Teacher:
    teacher = Teacher(
        country=country or f"Teacherland {index}",
        first_name=f"Teacher{index}",
        last_name=f"Assessor{index}",
        email=f"teacher{index}@example.com",
        school="Test School",
        languages=", ".join(languages),
        meal_preference="No preference",
        tshirt_size="M",
        declared_assessor_competence=True,
    )
    teacher.language_entries = [TeacherLanguage(language=language) for language in languages]
    return teacher


def _create_student(index: int, *, country: str | None = None, language: str = "English") -> Student:
    return Student(
        country=country or f"Studentland {index}",
        first_name=f"Student{index}",
        last_name=f"Writer{index}",
        email=f"student{index}@example.com",
        school="Test School",
        date_of_birth=date(2000, 1, 1),
        essay_language=language,
        keyboard_preference="QWERTY",
        meal_preference="No preference",
    )


def _add_reader(group: ReadingGroup, teacher: Teacher, *, role: GroupMemberRole = GroupMemberRole.READER) -> None:
    db.session.add(
        ReadingGroupMember(
            group_id=group.id,
            teacher_id=teacher.id,
            role=role,
            active=True,
        )
    )


def _add_stage1_score(assignment: EssayAssignment, teacher: Teacher, score: float, *, finalized: bool = True) -> None:
    db.session.add(
        EssayScore(
            assignment_id=assignment.id,
            student_id=assignment.student_id,
            teacher_id=teacher.id,
            stage=Stage.STAGE_1,
            score=score,
            submitted_at=datetime.utcnow(),
            teacher_finalized=finalized,
            teacher_finalized_at=datetime.utcnow() if finalized else None,
        )
    )


def _write_valid_pdf(path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    buffer = BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=A4)
    pdf.drawString(72, 760, "Essay packet test")
    pdf.showPage()
    pdf.save()
    path.write_bytes(buffer.getvalue())


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


def test_strict_auto_generate_keeps_backup_teachers(client):
    with client.application.app_context():
        batch = AssignmentBatch(
            name="Strict Batch",
            stage=Stage.STAGE_1,
            status=PlannerStatus.DRAFT,
            planner_algorithm=PlannerAlgorithm.STRICT_FOUR_WITH_BACKUPS,
        )
        db.session.add(batch)
        db.session.add_all(_create_assessor(index) for index in range(5))
        db.session.add_all(_create_student(index) for index in range(5))
        db.session.commit()

        summary = views._auto_generate_groups_for_batch(batch)
        db.session.commit()

        assert summary["created"] == {"English": 1}
        assert summary["backups"] == 1

        groups = ReadingGroup.query.filter_by(batch_id=batch.id).all()
        assert len(groups) == 1
        members = groups[0].members
        active_members = [member for member in members if member.active]
        backup_members = [member for member in members if member.role == GroupMemberRole.BACKUP]
        assert len(active_members) == 4
        assert len(backup_members) == 1
        assert backup_members[0].active is False


def test_all_assessors_auto_generate_uses_every_teacher_without_backups_and_assigns_underfilled_groups(client):
    with client.application.app_context():
        batch = AssignmentBatch(
            name="All Assessors Batch",
            stage=Stage.STAGE_1,
            status=PlannerStatus.DRAFT,
            planner_algorithm=PlannerAlgorithm.ALL_ASSESSORS_NO_BACKUPS,
        )
        db.session.add(batch)
        db.session.add_all(_create_assessor(index) for index in range(6))
        db.session.add_all(_create_student(index) for index in range(8))
        db.session.commit()

        summary = views._auto_generate_groups_for_batch(batch)
        db.session.commit()

        assert summary["created"] == {"English": 2}
        assert summary["backups"] == 0
        assert summary["teachers_assigned"] == 6
        assert summary["underfilled"] == 1

        groups = ReadingGroup.query.filter_by(batch_id=batch.id).order_by(ReadingGroup.id.asc()).all()
        active_counts = sorted(
            sum(1 for member in group.members if member.active and member.role != GroupMemberRole.BACKUP)
            for group in groups
        )
        assert active_counts == [2, 4]
        assert not any(member.role == GroupMemberRole.BACKUP for group in groups for member in group.members)

        assigned, skipped = views._auto_assign_essays(batch)
        db.session.commit()

        assert assigned == 8
        assert skipped == []
        underfilled_group = next(group for group in groups if len([member for member in group.members if member.active]) == 2)
        assert EssayAssignment.query.filter_by(batch_id=batch.id, group_id=underfilled_group.id).count() > 0


def test_auto_generate_removes_manual_assignments_from_replaced_generated_groups(client):
    with client.application.app_context():
        batch = AssignmentBatch(
            name="Replace Generated Batch",
            stage=Stage.STAGE_1,
            status=PlannerStatus.DRAFT,
            planner_algorithm=PlannerAlgorithm.ALL_ASSESSORS_NO_BACKUPS,
        )
        db.session.add(batch)
        db.session.flush()
        generated_group = ReadingGroup(
            name="Generated Old",
            language="English",
            target_essay_load=4,
            stage=Stage.STAGE_1,
            auto_generated=True,
            batch_id=batch.id,
        )
        student = _create_student(99)
        db.session.add_all([generated_group, student])
        db.session.flush()
        db.session.add(
            EssayAssignment(
                student_id=student.id,
                group_id=generated_group.id,
                batch_id=batch.id,
                stage=Stage.STAGE_1,
                manual_override=True,
                status=PlannerStatus.DRAFT,
            )
        )
        db.session.add_all(_create_assessor(index) for index in range(2))
        db.session.commit()

        summary = views._auto_generate_groups_for_batch(batch)
        db.session.commit()

        assert summary["removed"] == 1
        assert summary["removed_assignments"] == 1
        assert EssayAssignment.query.filter_by(batch_id=batch.id, student_id=student.id).count() == 0


def test_published_batch_blocks_auto_generate_route(client, csrf_token):
    with client.application.app_context():
        batch = AssignmentBatch(
            name="Published Batch",
            stage=Stage.STAGE_1,
            status=PlannerStatus.PUBLISHED,
            planner_algorithm=PlannerAlgorithm.ALL_ASSESSORS_NO_BACKUPS,
        )
        db.session.add(batch)
        db.session.add_all(_create_assessor(index) for index in range(4))
        db.session.commit()
        batch_id = batch.id

    with client.session_transaction() as session:
        session["admin_user"] = "admin"

    token = csrf_token(client.get(f"/admin/planner/batches/{batch_id}"))
    response = client.post(
        f"/admin/planner/batches/{batch_id}/auto-generate",
        data={"csrf_token": token},
        follow_redirects=False,
    )

    assert response.status_code == 302
    with client.application.app_context():
        assert ReadingGroup.query.filter_by(batch_id=batch_id).count() == 0


def test_publish_all_assessors_batch_allows_underfilled_groups(client, csrf_token):
    with client.application.app_context():
        batch = AssignmentBatch(
            name="Publish Underfilled Batch",
            stage=Stage.STAGE_1,
            status=PlannerStatus.DRAFT,
            planner_algorithm=PlannerAlgorithm.ALL_ASSESSORS_NO_BACKUPS,
        )
        db.session.add(batch)
        db.session.add_all(_create_assessor(index) for index in range(2))
        db.session.commit()
        views._auto_generate_groups_for_batch(batch)
        db.session.commit()
        batch_id = batch.id

    with client.session_transaction() as session:
        session["admin_user"] = "admin"

    token = csrf_token(client.get(f"/admin/planner/batches/{batch_id}"))
    response = client.post(
        f"/admin/planner/batches/{batch_id}/publish",
        data={"csrf_token": token},
        follow_redirects=False,
    )

    assert response.status_code == 302
    with client.application.app_context():
        batch = db.session.get(AssignmentBatch, batch_id)
        assert batch.status == PlannerStatus.PUBLISHED


def test_stage1_status_requires_four_readings_for_underfilled_assignment(client):
    with client.application.app_context():
        batch = AssignmentBatch(
            name="Four Reading Batch",
            stage=Stage.STAGE_1,
            status=PlannerStatus.PUBLISHED,
            planner_algorithm=PlannerAlgorithm.ALL_ASSESSORS_NO_BACKUPS,
        )
        group = ReadingGroup(
            name="Underfilled",
            language="English",
            target_essay_load=2,
            stage=Stage.STAGE_1,
            status=PlannerStatus.PUBLISHED,
            batch=batch,
        )
        reader_a = _create_assessor(101, country="Readerland A")
        reader_b = _create_assessor(102, country="Readerland B")
        student = _create_student(101, country="Studentland")
        db.session.add_all([batch, group, reader_a, reader_b, student])
        db.session.flush()
        _add_reader(group, reader_a, role=GroupMemberRole.LEADER)
        _add_reader(group, reader_b)
        assignment = EssayAssignment(
            student_id=student.id,
            group_id=group.id,
            batch_id=batch.id,
            stage=Stage.STAGE_1,
            status=PlannerStatus.PUBLISHED,
        )
        db.session.add(assignment)
        db.session.flush()
        _add_stage1_score(assignment, reader_a, 7)
        _add_stage1_score(assignment, reader_b, 8)
        db.session.commit()

        status = views._compute_stage_one_status(assignment)

        assert status.assigned_readers == 2
        assert status.required_readers == 4
        assert status.expected_scores == 4
        assert status.entered_scores == 2
        assert status.missing_reader_assignments == 2
        assert status.completed is False
        assert "additional reader assignment" in status.recommendation


def test_planner_batch_diagnostics_summarize_assignment_risks(client):
    with client.application.app_context():
        batch = AssignmentBatch(
            name="Diagnostics Batch",
            stage=Stage.STAGE_1,
            status=PlannerStatus.DRAFT,
            planner_algorithm=PlannerAlgorithm.ALL_ASSESSORS_NO_BACKUPS,
        )
        group = ReadingGroup(
            name="Diagnostics Group",
            language="English",
            target_essay_load=1,
            stage=Stage.STAGE_1,
            status=PlannerStatus.DRAFT,
            allow_same_country=False,
            batch=batch,
        )
        reader_a = _create_assessor(301, country="Sharedland")
        reader_b = _create_assessor(302, country="Readerland")
        free_assessor = _create_assessor(303, country="Freeland")
        absent_assessor = _create_assessor(304, country="Absentland")
        absent_assessor.is_absent = True
        non_assessor = Teacher(
            country="Organizers",
            first_name="Teacher305",
            last_name="NonAssessor305",
            email="teacher305@example.com",
            school="Test School",
            languages="English",
            meal_preference="No preference",
            tshirt_size="M",
            declared_assessor_competence=False,
        )
        assigned_student = _create_student(301, country="Sharedland")
        unassigned_student = _create_student(302, country="Studentland")
        absent_student = _create_student(303, country="Absent Studentland")
        absent_student.is_absent = True
        db.session.add_all([
            batch,
            group,
            reader_a,
            reader_b,
            free_assessor,
            absent_assessor,
            non_assessor,
            assigned_student,
            unassigned_student,
            absent_student,
        ])
        db.session.flush()
        _add_reader(group, reader_a, role=GroupMemberRole.LEADER)
        _add_reader(group, reader_b)
        _add_reader(group, absent_assessor)
        db.session.add_all([
            EssayAssignment(
                student_id=assigned_student.id,
                group_id=group.id,
                batch_id=batch.id,
                stage=Stage.STAGE_1,
                status=PlannerStatus.DRAFT,
            ),
            EssayAssignment(
                student_id=absent_student.id,
                group_id=group.id,
                batch_id=batch.id,
                stage=Stage.STAGE_1,
                status=PlannerStatus.DRAFT,
            ),
        ])
        db.session.commit()

        groups = views._load_batch_groups(batch)
        diagnostics = views._planner_batch_diagnostics(batch, groups)

        assert diagnostics.total_teachers == 5
        assert diagnostics.non_absent_teachers == 4
        assert diagnostics.eligible_assessors == 3
        assert diagnostics.total_students == 3
        assert diagnostics.non_absent_students == 2
        assert diagnostics.group_count == 1
        assert diagnostics.assignment_count == 2
        assert diagnostics.assigned_present_students == 1
        assert diagnostics.unassigned_students == 1
        assert diagnostics.groups_below_three == 1
        assert diagnostics.groups_below_four == 1
        assert diagnostics.groups_with_absent_teachers == 1
        assert diagnostics.absent_group_members == 1
        assert diagnostics.eligible_assessors_without_group == 1
        assert diagnostics.missing_reader_slots == 4
        assert diagnostics.under_read_assignments == 2
        assert diagnostics.country_conflicts == 1
        assert diagnostics.assigned_absent_students == 1
        assert diagnostics.groups_over_target == 1
        assert diagnostics.teacher_assignment_label == "Eligible assessors without group"
        assert diagnostics.readiness_label == "Review needed"
        assert {issue.title for issue in diagnostics.issues} >= {
            "Students not assigned",
            "Groups below 3 assessors",
            "Groups with absent teachers",
            "Eligible assessors without group",
            "Country conflicts",
            "Assigned absent students",
        }


def test_planner_batch_view_renders_diagnostics_dashboard(client):
    with client.application.app_context():
        batch = AssignmentBatch(
            name="Diagnostics View Batch",
            stage=Stage.STAGE_1,
            status=PlannerStatus.DRAFT,
            planner_algorithm=PlannerAlgorithm.ALL_ASSESSORS_NO_BACKUPS,
        )
        group = ReadingGroup(
            name="Diagnostics View Group",
            language="English",
            target_essay_load=2,
            stage=Stage.STAGE_1,
            status=PlannerStatus.DRAFT,
            batch=batch,
        )
        reader = _create_assessor(306)
        absent_reader = _create_assessor(307)
        absent_reader.is_absent = True
        student = _create_student(306)
        db.session.add_all([batch, group, reader, absent_reader, student])
        db.session.flush()
        _add_reader(group, reader, role=GroupMemberRole.LEADER)
        _add_reader(group, absent_reader)
        db.session.add(
            EssayAssignment(
                student_id=student.id,
                group_id=group.id,
                batch_id=batch.id,
                stage=Stage.STAGE_1,
                status=PlannerStatus.DRAFT,
            )
        )
        db.session.commit()
        batch_id = batch.id

    with client.session_transaction() as session:
        session["admin_user"] = "admin"

    response = client.get(f"/admin/planner/batches/{batch_id}")

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "Check groups and assignments" in html
    assert "Readiness checks" in html
    assert "Teachers" in html
    assert "Students" in html
    assert "Eligible assessors without group" in html
    assert "Groups with absent teachers" in html
    assert "Missing Stage 1 reader slots" in html
    assert "Repair for absences" in html


def test_planner_absence_repair_removes_absences_and_adds_free_teacher(client, csrf_token):
    with client.application.app_context():
        batch = AssignmentBatch(
            name="Absence Repair Batch",
            stage=Stage.STAGE_1,
            status=PlannerStatus.PUBLISHED,
            planner_algorithm=PlannerAlgorithm.ALL_ASSESSORS_NO_BACKUPS,
        )
        group = ReadingGroup(
            name="Repair Group",
            language="English",
            target_essay_load=2,
            stage=Stage.STAGE_1,
            status=PlannerStatus.PUBLISHED,
            batch=batch,
        )
        readers = [_create_assessor(801 + offset, country=f"Readerland {offset}") for offset in range(3)]
        absent_reader = _create_assessor(805, country="Absentland")
        absent_reader.is_absent = True
        free_reader = _create_assessor(806, country="Freeland")
        present_student = _create_student(801, country="Studentland")
        absent_student = _create_student(802, country="Absent Studentland")
        absent_student.is_absent = True
        db.session.add_all([batch, group, *readers, absent_reader, free_reader, present_student, absent_student])
        db.session.flush()
        _add_reader(group, readers[0], role=GroupMemberRole.LEADER)
        _add_reader(group, readers[1])
        _add_reader(group, readers[2])
        _add_reader(group, absent_reader)
        present_assignment = EssayAssignment(
            student_id=present_student.id,
            group_id=group.id,
            batch_id=batch.id,
            stage=Stage.STAGE_1,
            status=PlannerStatus.PUBLISHED,
        )
        absent_assignment = EssayAssignment(
            student_id=absent_student.id,
            group_id=group.id,
            batch_id=batch.id,
            stage=Stage.STAGE_1,
            status=PlannerStatus.PUBLISHED,
        )
        db.session.add_all([present_assignment, absent_assignment])
        db.session.commit()
        batch_id = batch.id
        group_id = group.id
        absent_reader_id = absent_reader.id
        free_reader_id = free_reader.id
        present_assignment_id = present_assignment.id
        absent_assignment_id = absent_assignment.id

    with client.session_transaction() as session:
        session["admin_user"] = "admin"

    page = client.get(f"/admin/planner/batches/{batch_id}")
    token = csrf_token(page)
    html = page.get_data(as_text=True)
    assert "Remove absent teacher" in html
    assert "Remove absent student" in html
    assert "Add available teacher" in html

    response = client.post(
        f"/admin/planner/batches/{batch_id}/absence-repair",
        data={"csrf_token": token},
        follow_redirects=True,
    )

    assert response.status_code == 200
    with client.application.app_context():
        assert db.session.get(EssayAssignment, present_assignment_id) is not None
        assert db.session.get(EssayAssignment, absent_assignment_id) is None
        assert ReadingGroupMember.query.filter_by(group_id=group_id, teacher_id=absent_reader_id).first() is None
        free_member = ReadingGroupMember.query.filter_by(group_id=group_id, teacher_id=free_reader_id).first()
        assert free_member is not None
        assert free_member.active is True
        assert ActivityLog.query.filter_by(action="planner_absence_repair_applied").first() is not None


def test_planner_absence_repair_is_noop_when_batch_has_no_absences(client, csrf_token):
    with client.application.app_context():
        batch = AssignmentBatch(
            name="No Absence Repair Batch",
            stage=Stage.STAGE_1,
            status=PlannerStatus.PUBLISHED,
            planner_algorithm=PlannerAlgorithm.ALL_ASSESSORS_NO_BACKUPS,
        )
        group = ReadingGroup(
            name="Stable Group",
            language="English",
            target_essay_load=1,
            stage=Stage.STAGE_1,
            status=PlannerStatus.PUBLISHED,
            batch=batch,
        )
        readers = [_create_assessor(901 + offset, country=f"Stableland {offset}") for offset in range(4)]
        student = _create_student(901, country="Studentland")
        db.session.add_all([batch, group, *readers, student])
        db.session.flush()
        for index, reader in enumerate(readers):
            _add_reader(group, reader, role=GroupMemberRole.LEADER if index == 0 else GroupMemberRole.READER)
        db.session.add(
            EssayAssignment(
                student_id=student.id,
                group_id=group.id,
                batch_id=batch.id,
                stage=Stage.STAGE_1,
                status=PlannerStatus.PUBLISHED,
            )
        )
        db.session.commit()
        batch_id = batch.id

    with client.session_transaction() as session:
        session["admin_user"] = "admin"

    page = client.get(f"/admin/planner/batches/{batch_id}")
    token = csrf_token(page)
    assert "Repair for absences" not in page.get_data(as_text=True)

    response = client.post(
        f"/admin/planner/batches/{batch_id}/absence-repair",
        data={"csrf_token": token},
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert "No absence repair changes are currently needed." in response.get_data(as_text=True)
    with client.application.app_context():
        assert ActivityLog.query.filter_by(action="planner_absence_repair_applied").first() is None


def test_planner_absence_repair_promotes_reader_when_absent_teacher_was_leader(client, csrf_token):
    with client.application.app_context():
        batch = AssignmentBatch(
            name="Absent Leader Repair Batch",
            stage=Stage.STAGE_1,
            status=PlannerStatus.PUBLISHED,
            planner_algorithm=PlannerAlgorithm.ALL_ASSESSORS_NO_BACKUPS,
        )
        group = ReadingGroup(
            name="Leader Repair Group",
            language="English",
            target_essay_load=1,
            stage=Stage.STAGE_1,
            status=PlannerStatus.PUBLISHED,
            batch=batch,
        )
        absent_leader = _create_assessor(921, country="Absentland")
        absent_leader.is_absent = True
        readers = [_create_assessor(922 + offset, country=f"Readerland {offset}") for offset in range(3)]
        student = _create_student(921, country="Studentland")
        db.session.add_all([batch, group, absent_leader, *readers, student])
        db.session.flush()
        _add_reader(group, absent_leader, role=GroupMemberRole.LEADER)
        for reader in readers:
            _add_reader(group, reader)
        db.session.add(
            EssayAssignment(
                student_id=student.id,
                group_id=group.id,
                batch_id=batch.id,
                stage=Stage.STAGE_1,
                status=PlannerStatus.PUBLISHED,
            )
        )
        db.session.commit()
        batch_id = batch.id
        group_id = group.id
        absent_leader_id = absent_leader.id
        promoted_reader_id = readers[0].id

    with client.session_transaction() as session:
        session["admin_user"] = "admin"

    page = client.get(f"/admin/planner/batches/{batch_id}")
    html = page.get_data(as_text=True)
    assert "Remove absent teacher" in html
    assert "Make Teacher922 Assessor922 leader" in html

    token = csrf_token(page)
    response = client.post(
        f"/admin/planner/batches/{batch_id}/absence-repair",
        data={"csrf_token": token},
        follow_redirects=True,
    )

    assert response.status_code == 200
    with client.application.app_context():
        assert ReadingGroupMember.query.filter_by(group_id=group_id, teacher_id=absent_leader_id).first() is None
        active_members = ReadingGroupMember.query.filter_by(group_id=group_id, active=True).all()
        assert len(active_members) == 3
        leaders = [member for member in active_members if member.role == GroupMemberRole.LEADER]
        assert len(leaders) == 1
        assert leaders[0].teacher_id == promoted_reader_id


def test_planner_absence_repair_filters_free_teachers_by_language_and_country(client, csrf_token):
    with client.application.app_context():
        batch = AssignmentBatch(
            name="Eligibility Repair Batch",
            stage=Stage.STAGE_1,
            status=PlannerStatus.PUBLISHED,
            planner_algorithm=PlannerAlgorithm.ALL_ASSESSORS_NO_BACKUPS,
        )
        group = ReadingGroup(
            name="Eligibility Repair Group",
            language="English",
            target_essay_load=1,
            stage=Stage.STAGE_1,
            status=PlannerStatus.PUBLISHED,
            batch=batch,
        )
        readers = [_create_assessor(941 + offset, country=f"Readerland {offset}") for offset in range(3)]
        absent_reader = _create_assessor(945, country="Absentland")
        absent_reader.is_absent = True
        wrong_language = _create_assessor(946, country="Freeland", languages=("Spanish",))
        country_conflict = _create_assessor(947, country="Studentland")
        eligible = _create_assessor(948, country="Otherland")
        student = _create_student(941, country="Studentland")
        db.session.add_all(
            [batch, group, *readers, absent_reader, wrong_language, country_conflict, eligible, student]
        )
        db.session.flush()
        for index, reader in enumerate(readers):
            _add_reader(group, reader, role=GroupMemberRole.LEADER if index == 0 else GroupMemberRole.READER)
        _add_reader(group, absent_reader)
        db.session.add(
            EssayAssignment(
                student_id=student.id,
                group_id=group.id,
                batch_id=batch.id,
                stage=Stage.STAGE_1,
                status=PlannerStatus.PUBLISHED,
            )
        )
        db.session.commit()
        batch_id = batch.id
        group_id = group.id
        wrong_language_id = wrong_language.id
        country_conflict_id = country_conflict.id
        eligible_id = eligible.id

    with client.session_transaction() as session:
        session["admin_user"] = "admin"

    page = client.get(f"/admin/planner/batches/{batch_id}")
    html = page.get_data(as_text=True)
    assert "Add available teacher Teacher948 Assessor948" in html
    assert "Add available teacher Teacher946 Assessor946" not in html
    assert "Add available teacher Teacher947 Assessor947" not in html

    token = csrf_token(page)
    response = client.post(
        f"/admin/planner/batches/{batch_id}/absence-repair",
        data={"csrf_token": token},
        follow_redirects=True,
    )

    assert response.status_code == 200
    with client.application.app_context():
        assert ReadingGroupMember.query.filter_by(group_id=group_id, teacher_id=eligible_id).first() is not None
        assert ReadingGroupMember.query.filter_by(group_id=group_id, teacher_id=wrong_language_id).first() is None
        assert ReadingGroupMember.query.filter_by(group_id=group_id, teacher_id=country_conflict_id).first() is None


def test_planner_absence_repair_moves_reader_only_when_group_falls_below_three(client, csrf_token):
    with client.application.app_context():
        batch = AssignmentBatch(
            name="Absence Move Batch",
            stage=Stage.STAGE_1,
            status=PlannerStatus.PUBLISHED,
            planner_algorithm=PlannerAlgorithm.ALL_ASSESSORS_NO_BACKUPS,
        )
        target = ReadingGroup(
            name="Target Repair",
            language="English",
            target_essay_load=1,
            stage=Stage.STAGE_1,
            status=PlannerStatus.PUBLISHED,
            batch=batch,
        )
        donor = ReadingGroup(
            name="Donor Repair",
            language="English",
            target_essay_load=1,
            stage=Stage.STAGE_1,
            status=PlannerStatus.PUBLISHED,
            batch=batch,
        )
        target_active = [_create_assessor(821 + offset, country=f"Targetland {offset}") for offset in range(2)]
        target_absent = [_create_assessor(831 + offset, country=f"Absentland {offset}") for offset in range(2)]
        for teacher in target_absent:
            teacher.is_absent = True
        donor_readers = [_create_assessor(841 + offset, country=f"Donorland {offset}") for offset in range(4)]
        target_student = _create_student(821, country="Target Studentland")
        donor_student = _create_student(822, country="Donor Studentland")
        db.session.add_all([batch, target, donor, *target_active, *target_absent, *donor_readers, target_student, donor_student])
        db.session.flush()
        _add_reader(target, target_active[0], role=GroupMemberRole.LEADER)
        _add_reader(target, target_active[1])
        for teacher in target_absent:
            _add_reader(target, teacher)
        for index, teacher in enumerate(donor_readers):
            _add_reader(donor, teacher, role=GroupMemberRole.LEADER if index == 0 else GroupMemberRole.READER)
        db.session.add_all([
            EssayAssignment(
                student_id=target_student.id,
                group_id=target.id,
                batch_id=batch.id,
                stage=Stage.STAGE_1,
                status=PlannerStatus.PUBLISHED,
            ),
            EssayAssignment(
                student_id=donor_student.id,
                group_id=donor.id,
                batch_id=batch.id,
                stage=Stage.STAGE_1,
                status=PlannerStatus.PUBLISHED,
            ),
        ])
        db.session.commit()
        batch_id = batch.id
        target_id = target.id
        donor_id = donor.id
        donor_reader_ids = {teacher.id for teacher in donor_readers}

    with client.session_transaction() as session:
        session["admin_user"] = "admin"

    token = csrf_token(client.get(f"/admin/planner/batches/{batch_id}"))
    response = client.post(
        f"/admin/planner/batches/{batch_id}/absence-repair",
        data={"csrf_token": token},
        follow_redirects=True,
    )

    assert response.status_code == 200
    with client.application.app_context():
        target_members = (
            ReadingGroupMember.query.join(Teacher)
            .filter(
                ReadingGroupMember.group_id == target_id,
                ReadingGroupMember.active.is_(True),
                Teacher.is_absent.is_(False),
            )
            .all()
        )
        donor_members = (
            ReadingGroupMember.query.join(Teacher)
            .filter(
                ReadingGroupMember.group_id == donor_id,
                ReadingGroupMember.active.is_(True),
                Teacher.is_absent.is_(False),
            )
            .all()
        )
        assert len(target_members) == 3
        assert len(donor_members) == 3
        moved_ids = {member.teacher_id for member in target_members}.intersection(donor_reader_ids)
        assert len(moved_ids) == 1


def test_planner_absence_repair_does_not_move_from_three_reader_donor(client, csrf_token):
    with client.application.app_context():
        batch = AssignmentBatch(
            name="Donor Floor Repair Batch",
            stage=Stage.STAGE_1,
            status=PlannerStatus.PUBLISHED,
            planner_algorithm=PlannerAlgorithm.ALL_ASSESSORS_NO_BACKUPS,
        )
        target = ReadingGroup(
            name="Target Below Three",
            language="English",
            target_essay_load=1,
            stage=Stage.STAGE_1,
            status=PlannerStatus.PUBLISHED,
            batch=batch,
        )
        donor = ReadingGroup(
            name="Donor At Floor",
            language="English",
            target_essay_load=1,
            stage=Stage.STAGE_1,
            status=PlannerStatus.PUBLISHED,
            batch=batch,
        )
        target_active = [_create_assessor(961 + offset, country=f"Targetland {offset}") for offset in range(2)]
        target_absent = [_create_assessor(971 + offset, country=f"Absentland {offset}") for offset in range(2)]
        for teacher in target_absent:
            teacher.is_absent = True
        donor_readers = [_create_assessor(981 + offset, country=f"Donorland {offset}") for offset in range(3)]
        target_student = _create_student(961, country="Target Studentland")
        donor_student = _create_student(962, country="Donor Studentland")
        db.session.add_all(
            [batch, target, donor, *target_active, *target_absent, *donor_readers, target_student, donor_student]
        )
        db.session.flush()
        _add_reader(target, target_active[0], role=GroupMemberRole.LEADER)
        _add_reader(target, target_active[1])
        for teacher in target_absent:
            _add_reader(target, teacher)
        for index, teacher in enumerate(donor_readers):
            _add_reader(donor, teacher, role=GroupMemberRole.LEADER if index == 0 else GroupMemberRole.READER)
        db.session.add_all([
            EssayAssignment(
                student_id=target_student.id,
                group_id=target.id,
                batch_id=batch.id,
                stage=Stage.STAGE_1,
                status=PlannerStatus.PUBLISHED,
            ),
            EssayAssignment(
                student_id=donor_student.id,
                group_id=donor.id,
                batch_id=batch.id,
                stage=Stage.STAGE_1,
                status=PlannerStatus.PUBLISHED,
            ),
        ])
        db.session.commit()
        batch_id = batch.id
        target_id = target.id
        donor_id = donor.id
        donor_reader_ids = {teacher.id for teacher in donor_readers}

    with client.session_transaction() as session:
        session["admin_user"] = "admin"

    token = csrf_token(client.get(f"/admin/planner/batches/{batch_id}"))
    response = client.post(
        f"/admin/planner/batches/{batch_id}/absence-repair",
        data={"csrf_token": token},
        follow_redirects=True,
    )

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "would still have only 2 active teachers after repair" in html
    with client.application.app_context():
        target_members = (
            ReadingGroupMember.query.join(Teacher)
            .filter(
                ReadingGroupMember.group_id == target_id,
                ReadingGroupMember.active.is_(True),
                Teacher.is_absent.is_(False),
            )
            .all()
        )
        donor_members = (
            ReadingGroupMember.query.join(Teacher)
            .filter(
                ReadingGroupMember.group_id == donor_id,
                ReadingGroupMember.active.is_(True),
                Teacher.is_absent.is_(False),
            )
            .all()
        )
        assert len(target_members) == 2
        assert len(donor_members) == 3
        assert {member.teacher_id for member in target_members}.isdisjoint(donor_reader_ids)


def test_planner_absence_repair_refuses_when_scores_exist(client, csrf_token):
    with client.application.app_context():
        batch = AssignmentBatch(
            name="Scored Absence Repair Batch",
            stage=Stage.STAGE_1,
            status=PlannerStatus.PUBLISHED,
            planner_algorithm=PlannerAlgorithm.ALL_ASSESSORS_NO_BACKUPS,
        )
        group = ReadingGroup(
            name="Scored Repair Group",
            language="English",
            target_essay_load=1,
            stage=Stage.STAGE_1,
            status=PlannerStatus.PUBLISHED,
            batch=batch,
        )
        reader = _create_assessor(861, country="Readerland")
        absent_reader = _create_assessor(862, country="Absentland")
        absent_reader.is_absent = True
        free_reader = _create_assessor(863, country="Freeland")
        student = _create_student(861, country="Studentland")
        db.session.add_all([batch, group, reader, absent_reader, free_reader, student])
        db.session.flush()
        _add_reader(group, reader, role=GroupMemberRole.LEADER)
        _add_reader(group, absent_reader)
        assignment = EssayAssignment(
            student_id=student.id,
            group_id=group.id,
            batch_id=batch.id,
            stage=Stage.STAGE_1,
            status=PlannerStatus.PUBLISHED,
        )
        db.session.add(assignment)
        db.session.flush()
        _add_stage1_score(assignment, reader, 6.0)
        db.session.commit()
        batch_id = batch.id
        group_id = group.id
        absent_reader_id = absent_reader.id
        free_reader_id = free_reader.id

    with client.session_transaction() as session:
        session["admin_user"] = "admin"

    token = csrf_token(client.get(f"/admin/planner/batches/{batch_id}"))
    response = client.post(
        f"/admin/planner/batches/{batch_id}/absence-repair",
        data={"csrf_token": token},
        follow_redirects=True,
    )

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "repair must be handled manually" in html
    with client.application.app_context():
        assert ReadingGroupMember.query.filter_by(group_id=group_id, teacher_id=absent_reader_id).first() is not None
        assert ReadingGroupMember.query.filter_by(group_id=group_id, teacher_id=free_reader_id).first() is None


def test_planner_absence_repair_refuses_for_stage_two_batches(client, csrf_token):
    with client.application.app_context():
        batch = AssignmentBatch(
            name="Stage Two Absence Repair Batch",
            stage=Stage.STAGE_2,
            status=PlannerStatus.PUBLISHED,
            planner_algorithm=PlannerAlgorithm.ALL_ASSESSORS_NO_BACKUPS,
        )
        group = ReadingGroup(
            name="Stage Two Repair Group",
            language="English",
            target_essay_load=1,
            stage=Stage.STAGE_2,
            status=PlannerStatus.PUBLISHED,
            batch=batch,
        )
        reader = _create_assessor(1001, country="Readerland")
        absent_reader = _create_assessor(1002, country="Absentland")
        absent_reader.is_absent = True
        student = _create_student(1001, country="Studentland")
        db.session.add_all([batch, group, reader, absent_reader, student])
        db.session.flush()
        _add_reader(group, reader, role=GroupMemberRole.LEADER)
        _add_reader(group, absent_reader)
        db.session.add(
            EssayAssignment(
                student_id=student.id,
                group_id=group.id,
                batch_id=batch.id,
                stage=Stage.STAGE_2,
                status=PlannerStatus.PUBLISHED,
            )
        )
        db.session.commit()
        batch_id = batch.id
        group_id = group.id
        absent_reader_id = absent_reader.id

    with client.session_transaction() as session:
        session["admin_user"] = "admin"

    token = csrf_token(client.get(f"/admin/planner/batches/{batch_id}"))
    response = client.post(
        f"/admin/planner/batches/{batch_id}/absence-repair",
        data={"csrf_token": token},
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert "supported for Stage 1 batches only" in response.get_data(as_text=True)
    with client.application.app_context():
        assert ReadingGroupMember.query.filter_by(group_id=group_id, teacher_id=absent_reader_id).first() is not None


def _create_six_score_stage1_assignment(index: int) -> tuple[EssayAssignment, list[Teacher]]:
    batch = AssignmentBatch(
        name=f"Trimmed Average Batch {index}",
        stage=Stage.STAGE_1,
        status=PlannerStatus.PUBLISHED,
        planner_algorithm=PlannerAlgorithm.STRICT_FOUR_WITH_BACKUPS,
    )
    group = ReadingGroup(
        name=f"Trimmed Average Group {index}",
        language="English",
        stage=Stage.STAGE_1,
        status=PlannerStatus.PUBLISHED,
        batch=batch,
    )
    teachers = [_create_assessor(index * 10 + offset) for offset in range(1, 7)]
    student = _create_student(index, country=f"Trim Student {index}")
    db.session.add_all([batch, group, student, *teachers])
    db.session.flush()
    for offset, teacher in enumerate(teachers[:4]):
        _add_reader(group, teacher, role=GroupMemberRole.LEADER if offset == 0 else GroupMemberRole.READER)
    assignment = EssayAssignment(
        student_id=student.id,
        group_id=group.id,
        batch_id=batch.id,
        stage=Stage.STAGE_1,
        status=PlannerStatus.PUBLISHED,
    )
    db.session.add(assignment)
    db.session.flush()
    for teacher in teachers[4:]:
        db.session.add(
            EssayAssignmentExtraReader(
                assignment_id=assignment.id,
                teacher_id=teacher.id,
                stage=Stage.STAGE_1.value,
            )
        )
    for teacher, score in zip(teachers, [1, 7, 7, 7, 8, 10], strict=True):
        _add_stage1_score(assignment, teacher, score)
    db.session.commit()
    return assignment, teachers


def test_stage1_trimmed_average_setting_controls_stage2_decision(client):
    with client.application.app_context():
        views._set_setting(views.SETTING_STAGE1_TRIM_EXTREME_SCORES, "true")
        assignment, _teachers = _create_six_score_stage1_assignment(41)

        status = views._compute_stage_one_status(assignment)
        views._apply_stage_one_rules(assignment)

        assert status.entered_scores == 6
        assert status.expected_scores == 6
        assert status.average_is_trimmed is True
        assert status.average_score_count == 4
        assert status.raw_score_count == 6
        assert abs(status.raw_average_score - (40 / 6)) < 0.0001
        assert abs(status.average_score - 7.25) < 0.0001
        assert status.score_range == 9
        assert status.recommendation == "Qualifies for Stage 2."
        assert assignment.needs_additional_reading is False
        assert assignment.stage_two_candidate is True


def test_stage1_default_average_still_requires_extra_reader_on_large_spread(client):
    with client.application.app_context():
        assignment, _teachers = _create_six_score_stage1_assignment(42)

        status = views._compute_stage_one_status(assignment)
        views._apply_stage_one_rules(assignment)

        assert status.average_is_trimmed is False
        assert abs(status.average_score - (40 / 6)) < 0.0001
        assert status.recommendation == "Score disparity >3: assign additional reader."
        assert assignment.needs_additional_reading is True
        assert assignment.stage_two_candidate is False


def test_supplemental_reader_route_assigns_free_teacher_to_eligible_underfilled_essays(client, csrf_token):
    with client.application.app_context():
        batch = AssignmentBatch(
            name="Supplemental Batch",
            stage=Stage.STAGE_1,
            status=PlannerStatus.PUBLISHED,
            planner_algorithm=PlannerAlgorithm.ALL_ASSESSORS_NO_BACKUPS,
        )
        target_group = ReadingGroup(
            name="Target",
            language="English",
            target_essay_load=2,
            stage=Stage.STAGE_1,
            status=PlannerStatus.PUBLISHED,
            batch=batch,
        )
        source_group = ReadingGroup(
            name="Source",
            language="English",
            target_essay_load=1,
            stage=Stage.STAGE_1,
            status=PlannerStatus.PUBLISHED,
            batch=batch,
        )
        base_a = _create_assessor(201, country="Base A")
        base_b = _create_assessor(202, country="Base B")
        free_teacher = _create_assessor(203, country="Free Country")
        eligible_student = _create_student(201, country="Eligible Country")
        conflict_student = _create_student(202, country="Free Country")
        source_student = _create_student(203, country="Source Country")
        db.session.add_all(
            [
                batch,
                target_group,
                source_group,
                base_a,
                base_b,
                free_teacher,
                eligible_student,
                conflict_student,
                source_student,
            ]
        )
        db.session.flush()
        _add_reader(target_group, base_a, role=GroupMemberRole.LEADER)
        _add_reader(target_group, base_b)
        _add_reader(source_group, free_teacher, role=GroupMemberRole.LEADER)
        eligible_assignment = EssayAssignment(
            student_id=eligible_student.id,
            group_id=target_group.id,
            batch_id=batch.id,
            stage=Stage.STAGE_1,
            status=PlannerStatus.PUBLISHED,
        )
        conflict_assignment = EssayAssignment(
            student_id=conflict_student.id,
            group_id=target_group.id,
            batch_id=batch.id,
            stage=Stage.STAGE_1,
            status=PlannerStatus.PUBLISHED,
        )
        source_assignment = EssayAssignment(
            student_id=source_student.id,
            group_id=source_group.id,
            batch_id=batch.id,
            stage=Stage.STAGE_1,
            status=PlannerStatus.PUBLISHED,
        )
        db.session.add_all([eligible_assignment, conflict_assignment, source_assignment])
        db.session.flush()
        _add_stage1_score(source_assignment, free_teacher, 8)
        db.session.commit()
        batch_id = batch.id
        target_group_id = target_group.id
        free_teacher_id = free_teacher.id
        eligible_assignment_id = eligible_assignment.id
        conflict_assignment_id = conflict_assignment.id

    with client.session_transaction() as session:
        session["admin_user"] = "admin"

    token = csrf_token(client.get(f"/admin/planner/batches/{batch_id}"))
    response = client.post(
        f"/admin/planner/batches/{batch_id}/groups/{target_group_id}/supplemental-readers",
        data={"csrf_token": token, "teacher_id": str(free_teacher_id)},
        follow_redirects=False,
    )

    assert response.status_code == 302
    with client.application.app_context():
        extra_rows = EssayAssignmentExtraReader.query.filter_by(
            teacher_id=free_teacher_id,
            stage=Stage.STAGE_1.value,
        ).all()
        assert [row.assignment_id for row in extra_rows] == [eligible_assignment_id]
        assert not EssayAssignmentExtraReader.query.filter_by(
            assignment_id=conflict_assignment_id,
            teacher_id=free_teacher_id,
            stage=Stage.STAGE_1.value,
        ).first()


def test_supplemental_reader_route_blocks_teacher_with_pending_stage1_work(client, csrf_token):
    with client.application.app_context():
        batch = AssignmentBatch(
            name="Busy Supplemental Batch",
            stage=Stage.STAGE_1,
            status=PlannerStatus.PUBLISHED,
            planner_algorithm=PlannerAlgorithm.ALL_ASSESSORS_NO_BACKUPS,
        )
        target_group = ReadingGroup(
            name="Target Busy",
            language="English",
            stage=Stage.STAGE_1,
            status=PlannerStatus.PUBLISHED,
            batch=batch,
        )
        source_group = ReadingGroup(
            name="Busy Source",
            language="English",
            stage=Stage.STAGE_1,
            status=PlannerStatus.PUBLISHED,
            batch=batch,
        )
        base_reader = _create_assessor(301, country="Base Country")
        busy_teacher = _create_assessor(302, country="Busy Country")
        target_student = _create_student(301, country="Target Country")
        source_student = _create_student(302, country="Source Country")
        db.session.add_all([batch, target_group, source_group, base_reader, busy_teacher, target_student, source_student])
        db.session.flush()
        _add_reader(target_group, base_reader, role=GroupMemberRole.LEADER)
        _add_reader(source_group, busy_teacher, role=GroupMemberRole.LEADER)
        target_assignment = EssayAssignment(
            student_id=target_student.id,
            group_id=target_group.id,
            batch_id=batch.id,
            stage=Stage.STAGE_1,
            status=PlannerStatus.PUBLISHED,
        )
        source_assignment = EssayAssignment(
            student_id=source_student.id,
            group_id=source_group.id,
            batch_id=batch.id,
            stage=Stage.STAGE_1,
            status=PlannerStatus.PUBLISHED,
        )
        db.session.add_all([target_assignment, source_assignment])
        db.session.commit()
        batch_id = batch.id
        target_group_id = target_group.id
        busy_teacher_id = busy_teacher.id

    with client.session_transaction() as session:
        session["admin_user"] = "admin"

    token = csrf_token(client.get(f"/admin/planner/batches/{batch_id}"))
    response = client.post(
        f"/admin/planner/batches/{batch_id}/groups/{target_group_id}/supplemental-readers",
        data={"csrf_token": token, "teacher_id": str(busy_teacher_id)},
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert "still has 1 pending Stage 1 assignment" in response.get_data(as_text=True)
    with client.application.app_context():
        assert EssayAssignmentExtraReader.query.filter_by(teacher_id=busy_teacher_id).count() == 0


def test_planner_can_remove_supplemental_reader_from_published_group(client, csrf_token):
    with client.application.app_context():
        batch = AssignmentBatch(
            name="Remove Supplemental Batch",
            stage=Stage.STAGE_1,
            status=PlannerStatus.PUBLISHED,
            planner_algorithm=PlannerAlgorithm.ALL_ASSESSORS_NO_BACKUPS,
        )
        target_group = ReadingGroup(
            name="Target Remove",
            language="English",
            stage=Stage.STAGE_1,
            status=PlannerStatus.PUBLISHED,
            batch=batch,
        )
        other_group = ReadingGroup(
            name="Other Remove",
            language="English",
            stage=Stage.STAGE_1,
            status=PlannerStatus.PUBLISHED,
            batch=batch,
        )
        core_reader = _create_assessor(351, country="Core Country")
        supplemental_teacher = _create_assessor(352, country="Supplemental Country")
        target_student_a = _create_student(351, country="Target A")
        target_student_b = _create_student(352, country="Target B")
        other_student = _create_student(353, country="Other Target")
        db.session.add_all(
            [
                batch,
                target_group,
                other_group,
                core_reader,
                supplemental_teacher,
                target_student_a,
                target_student_b,
                other_student,
            ]
        )
        db.session.flush()
        _add_reader(target_group, core_reader, role=GroupMemberRole.LEADER)
        target_assignment_a = EssayAssignment(
            student_id=target_student_a.id,
            group_id=target_group.id,
            batch_id=batch.id,
            stage=Stage.STAGE_1,
            status=PlannerStatus.PUBLISHED,
        )
        target_assignment_b = EssayAssignment(
            student_id=target_student_b.id,
            group_id=target_group.id,
            batch_id=batch.id,
            stage=Stage.STAGE_1,
            status=PlannerStatus.PUBLISHED,
        )
        other_assignment = EssayAssignment(
            student_id=other_student.id,
            group_id=other_group.id,
            batch_id=batch.id,
            stage=Stage.STAGE_1,
            status=PlannerStatus.PUBLISHED,
        )
        db.session.add_all([target_assignment_a, target_assignment_b, other_assignment])
        db.session.flush()
        db.session.add_all(
            [
                EssayAssignmentExtraReader(
                    assignment_id=target_assignment_a.id,
                    teacher_id=supplemental_teacher.id,
                    stage=Stage.STAGE_1.value,
                ),
                EssayAssignmentExtraReader(
                    assignment_id=target_assignment_b.id,
                    teacher_id=supplemental_teacher.id,
                    stage=Stage.STAGE_1.value,
                ),
                EssayAssignmentExtraReader(
                    assignment_id=other_assignment.id,
                    teacher_id=supplemental_teacher.id,
                    stage=Stage.STAGE_1.value,
                ),
            ]
        )
        _add_stage1_score(target_assignment_a, supplemental_teacher, 8)
        _add_stage1_score(other_assignment, supplemental_teacher, 9)
        db.session.commit()
        batch_id = batch.id
        target_group_id = target_group.id
        supplemental_teacher_id = supplemental_teacher.id
        target_assignment_ids = {target_assignment_a.id, target_assignment_b.id}
        other_assignment_id = other_assignment.id

    with client.session_transaction() as session:
        session["admin_user"] = "admin"

    token = csrf_token(client.get(f"/admin/planner/batches/{batch_id}"))
    response = client.post(
        (
            f"/admin/planner/batches/{batch_id}/groups/{target_group_id}"
            f"/supplemental-readers/{supplemental_teacher_id}/remove"
        ),
        data={"csrf_token": token},
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert "Removed Teacher352 Assessor352 from 2 supplemental Stage 1 readings." in response.get_data(as_text=True)
    with client.application.app_context():
        removed_extra_rows = (
            EssayAssignmentExtraReader.query
            .filter(
                EssayAssignmentExtraReader.assignment_id.in_(target_assignment_ids),
                EssayAssignmentExtraReader.teacher_id == supplemental_teacher_id,
                EssayAssignmentExtraReader.stage == Stage.STAGE_1.value,
            )
            .count()
        )
        assert removed_extra_rows == 0
        assert not EssayScore.query.filter(
            EssayScore.assignment_id.in_(target_assignment_ids),
            EssayScore.teacher_id == supplemental_teacher_id,
            EssayScore.stage == Stage.STAGE_1,
        ).first()
        assert EssayAssignmentExtraReader.query.filter_by(
            assignment_id=other_assignment_id,
            teacher_id=supplemental_teacher_id,
            stage=Stage.STAGE_1.value,
        ).first()
        assert EssayScore.query.filter_by(
            assignment_id=other_assignment_id,
            teacher_id=supplemental_teacher_id,
            stage=Stage.STAGE_1,
        ).first()


def test_individual_teacher_packet_includes_group_and_supplemental_assignments(client):
    with client.application.app_context():
        batch = AssignmentBatch(
            name="Packet Batch",
            stage=Stage.STAGE_1,
            status=PlannerStatus.PUBLISHED,
            planner_algorithm=PlannerAlgorithm.ALL_ASSESSORS_NO_BACKUPS,
        )
        group_a = ReadingGroup(
            name="Packet Group A",
            language="English",
            stage=Stage.STAGE_1,
            status=PlannerStatus.PUBLISHED,
            batch=batch,
        )
        group_b = ReadingGroup(
            name="Packet Group B",
            language="English",
            stage=Stage.STAGE_1,
            status=PlannerStatus.PUBLISHED,
            batch=batch,
        )
        packet_teacher = _create_assessor(401, country="Packet Country")
        other_teacher = _create_assessor(402, country="Other Country")
        other_teacher_2 = _create_assessor(403, country="Other Country 2")
        other_teacher_3 = _create_assessor(404, country="Other Country 3")
        primary_student = _create_student(401, country="Primary Country")
        supplemental_student = _create_student(402, country="Supplemental Country")
        db.session.add_all(
            [
                batch,
                group_a,
                group_b,
                packet_teacher,
                other_teacher,
                other_teacher_2,
                other_teacher_3,
                primary_student,
                supplemental_student,
            ]
        )
        db.session.flush()
        _add_reader(group_a, packet_teacher, role=GroupMemberRole.LEADER)
        _add_reader(group_b, other_teacher, role=GroupMemberRole.LEADER)
        _add_reader(group_b, other_teacher_2)
        _add_reader(group_b, other_teacher_3)
        primary_assignment = EssayAssignment(
            student_id=primary_student.id,
            group_id=group_a.id,
            batch_id=batch.id,
            stage=Stage.STAGE_1,
            status=PlannerStatus.PUBLISHED,
        )
        supplemental_assignment = EssayAssignment(
            student_id=supplemental_student.id,
            group_id=group_b.id,
            batch_id=batch.id,
            stage=Stage.STAGE_1,
            status=PlannerStatus.PUBLISHED,
        )
        db.session.add_all([primary_assignment, supplemental_assignment])
        db.session.flush()
        db.session.add(
            EssayAssignmentExtraReader(
                assignment_id=supplemental_assignment.id,
                teacher_id=packet_teacher.id,
                stage=Stage.STAGE_1.value,
            )
        )

        upload_folder = client.application.config["UPLOAD_FOLDER"]
        primary_student.uploaded_filename = f"primary-{primary_student.id}.pdf"
        supplemental_student.uploaded_filename = f"supplemental-{supplemental_student.id}.pdf"
        _write_valid_pdf(Path(upload_folder) / primary_student.uploaded_filename)
        _write_valid_pdf(Path(upload_folder) / supplemental_student.uploaded_filename)
        db.session.commit()
        batch_id = batch.id
        packet_teacher_id = packet_teacher.id
        group_b_id = group_b.id

    with client.session_transaction() as session:
        session["admin_user"] = "admin"

    planner_page = client.get(f"/admin/planner/batches/{batch_id}")
    assert planner_page.status_code == 200
    planner_html = planner_page.get_data(as_text=True)
    packet_url = f"/admin/planner/batches/{batch_id}/teachers/{packet_teacher_id}/reader-packet.pdf"
    remove_url = (
        f"/admin/planner/batches/{batch_id}/groups/{group_b_id}"
        f"/supplemental-readers/{packet_teacher_id}/remove"
    )
    assert 'class="pdf-icon-link"' in planner_html
    assert packet_url in planner_html
    assert remove_url in planner_html
    assert "Download PDF packet for Teacher401 Assessor401" in planner_html
    assert "Individual packets:" not in planner_html
    assert "supplemental-reader-list" in planner_html
    assert "Supplemental &middot; 1 essay" in planner_html
    assert planner_html.index("Teacher402 Assessor402") < planner_html.index("supplemental-reader-list")

    response = client.get(
        packet_url,
        follow_redirects=False,
    )

    assert response.status_code == 200
    assert "application/pdf" in response.headers.get("Content-Type", "")
    reader = PdfReader(BytesIO(response.data))
    assert len(reader.pages) >= 3
