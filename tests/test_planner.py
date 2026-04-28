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

    with client.session_transaction() as session:
        session["admin_user"] = "admin"

    planner_page = client.get(f"/admin/planner/batches/{batch_id}")
    assert planner_page.status_code == 200
    planner_html = planner_page.get_data(as_text=True)
    packet_url = f"/admin/planner/batches/{batch_id}/teachers/{packet_teacher_id}/reader-packet.pdf"
    assert 'class="pdf-icon-link"' in planner_html
    assert packet_url in planner_html
    assert "Download PDF packet for Teacher401 Assessor401" in planner_html
    assert "Individual packets:" not in planner_html
    assert "supplemental-reader-list" in planner_html
    assert "Supplemental &middot; 1 essay" in planner_html

    response = client.get(
        packet_url,
        follow_redirects=False,
    )

    assert response.status_code == 200
    assert "application/pdf" in response.headers.get("Content-Type", "")
    reader = PdfReader(BytesIO(response.data))
    assert len(reader.pages) >= 3
