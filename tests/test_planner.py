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
            "planner_group_soft_max": "6",
            "planner_allow_cross_language_assignments": "y",
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
        assert batch.planner_group_soft_max == 6
        assert batch.planner_allow_cross_language_assignments is True

        log = ActivityLog.query.filter_by(
            action="batch_created",
            object_type="assignment_batch",
            object_id=str(batch.id),
        ).first()
        assert log is not None
        assert log.details["planner_group_soft_max"] == 6
        assert log.details["planner_allow_cross_language_assignments"] is True


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


def test_admin_planner_updates_algorithm_and_group_soft_max(client, csrf_token):
    with client.application.app_context():
        batch = AssignmentBatch(
            name="Settings Batch",
            stage=Stage.STAGE_1,
            status=PlannerStatus.DRAFT,
            planner_algorithm=PlannerAlgorithm.STRICT_FOUR_WITH_BACKUPS,
            planner_group_soft_max=5,
        )
        group = ReadingGroup(
            name="Existing Group",
            language="English",
            target_essay_load=12,
            stage=Stage.STAGE_1,
            status=PlannerStatus.DRAFT,
            batch=batch,
        )
        readers = [_create_assessor(index) for index in range(10, 14)]
        student = _create_student(10)
        db.session.add_all([batch, group, student, *readers])
        db.session.flush()
        for reader in readers:
            _add_reader(group, reader)
        db.session.commit()
        batch_id = batch.id
        group_id = group.id

    with client.session_transaction() as session:
        session["admin_user"] = "admin"

    token = csrf_token(client.get(f"/admin/planner/batches/{batch_id}"))
    response = client.post(
        f"/admin/planner/batches/{batch_id}/algorithm",
        data={
            "csrf_token": token,
            "planner_algorithm": PlannerAlgorithm.ALL_ASSESSORS_NO_BACKUPS.value,
            "planner_group_soft_max": "6",
            "planner_allow_cross_language_assignments": "y",
        },
        follow_redirects=False,
    )

    assert response.status_code == 302

    with client.application.app_context():
        batch = db.session.get(AssignmentBatch, batch_id)
        assert batch.planner_algorithm == PlannerAlgorithm.ALL_ASSESSORS_NO_BACKUPS
        assert batch.planner_group_soft_max == 6
        assert batch.planner_allow_cross_language_assignments is True
        group = db.session.get(ReadingGroup, group_id)
        assert group.target_essay_load == 6

        log = ActivityLog.query.filter_by(
            action="planner_settings_updated",
            object_type="assignment_batch",
            object_id=str(batch.id),
        ).first()
        assert log is not None
        assert log.details["planner_group_soft_max"] == 6
        assert log.details["planner_allow_cross_language_assignments"] is True


def test_admin_planner_manual_assignment_allows_compatible_cross_language_group(client, csrf_token):
    with client.application.app_context():
        batch = AssignmentBatch(
            name="Manual Cross Language Batch",
            stage=Stage.STAGE_1,
            status=PlannerStatus.DRAFT,
            planner_allow_cross_language_assignments=True,
        )
        group = ReadingGroup(
            name="English Group",
            language="English",
            target_essay_load=5,
            stage=Stage.STAGE_1,
            status=PlannerStatus.DRAFT,
            batch=batch,
        )
        readers = [
            _create_assessor(index, languages=("English", "French"))
            for index in range(20, 24)
        ]
        student = _create_student(20, language="French")
        db.session.add_all([batch, group, student, *readers])
        db.session.flush()
        for reader in readers:
            _add_reader(group, reader)
        db.session.commit()
        batch_id = batch.id
        group_id = group.id
        student_id = student.id

    with client.session_transaction() as session:
        session["admin_user"] = "admin"

    token = csrf_token(client.get(f"/admin/planner/batches/{batch_id}"))
    response = client.post(
        f"/admin/planner/batches/{batch_id}/groups/{group_id}/assign",
        data={
            "csrf_token": token,
            "student_id": str(student_id),
        },
        follow_redirects=False,
    )

    assert response.status_code == 302
    with client.application.app_context():
        assignment = EssayAssignment.query.filter_by(batch_id=batch_id, student_id=student_id).first()
        assert assignment is not None
        assert assignment.group_id == group_id
        assert assignment.manual_override is True


def test_admin_planner_assignment_controls_exclude_absent_students(client, csrf_token):
    with client.application.app_context():
        batch = AssignmentBatch(
            name="Absent Student Assignment Batch",
            stage=Stage.STAGE_1,
            status=PlannerStatus.DRAFT,
        )
        group = ReadingGroup(
            name="English Group",
            language="English",
            target_essay_load=5,
            stage=Stage.STAGE_1,
            status=PlannerStatus.DRAFT,
            batch=batch,
        )
        readers = [_create_assessor(index) for index in range(30, 34)]
        present_student = _create_student(30)
        present_student.first_name = "PresentTarget"
        present_student.last_name = "Visible"
        absent_student = _create_student(31)
        absent_student.first_name = "AbsentTarget"
        absent_student.last_name = "Hidden"
        absent_student.is_absent = True
        db.session.add_all([batch, group, present_student, absent_student, *readers])
        db.session.flush()
        for reader in readers:
            _add_reader(group, reader)
        db.session.commit()
        batch_id = batch.id
        group_id = group.id
        absent_student_id = absent_student.id

    with client.session_transaction() as session:
        session["admin_user"] = "admin"

    response = client.get(f"/admin/planner/batches/{batch_id}")
    html = response.get_data(as_text=True)
    assert "PresentTarget Visible" in html
    assert "AbsentTarget Hidden" not in html

    token = csrf_token(response)
    post_response = client.post(
        f"/admin/planner/batches/{batch_id}/groups/{group_id}/assign",
        data={
            "csrf_token": token,
            "student_id": str(absent_student_id),
        },
        follow_redirects=False,
    )

    assert post_response.status_code == 302
    with client.application.app_context():
        assert EssayAssignment.query.filter_by(batch_id=batch_id, student_id=absent_student_id).first() is None


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


def test_planner_add_member_rejects_teacher_country_conflict(client, csrf_token):
    with client.application.app_context():
        batch = AssignmentBatch(
            name="Manual Conflict Batch",
            stage=Stage.STAGE_1,
            status=PlannerStatus.DRAFT,
            planner_algorithm=PlannerAlgorithm.ALL_ASSESSORS_NO_BACKUPS,
        )
        group = ReadingGroup(
            name="Manual Conflict Group",
            language="English",
            target_essay_load=1,
            stage=Stage.STAGE_1,
            status=PlannerStatus.DRAFT,
            batch=batch,
            allow_same_country=False,
        )
        base_reader = _create_assessor(51, country="Base Readerland")
        conflict_teacher = _create_assessor(52, country="Studentland")
        compatible_teacher = _create_assessor(53, country="Compatibleland")
        student = _create_student(51, country="Studentland")
        db.session.add_all([batch, group, base_reader, conflict_teacher, compatible_teacher, student])
        db.session.flush()
        _add_reader(group, base_reader, role=GroupMemberRole.LEADER)
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
        group_id = group.id
        conflict_teacher_id = conflict_teacher.id
        compatible_label = f"{compatible_teacher.first_name} {compatible_teacher.last_name}"
        conflict_label = f"{conflict_teacher.first_name} {conflict_teacher.last_name}"

    with client.session_transaction() as session:
        session["admin_user"] = "admin"

    page = client.get(f"/admin/planner/batches/{batch_id}")
    assert page.status_code == 200
    html = page.get_data(as_text=True)
    quick_add_start = html.index("<h4>Add teacher</h4>")
    quick_add_end = html.index("</form>", quick_add_start)
    quick_add_html = html[quick_add_start:quick_add_end]
    assert compatible_label in quick_add_html
    assert conflict_label not in quick_add_html

    token = csrf_token(page)
    response = client.post(
        f"/admin/planner/batches/{batch_id}/members",
        data={
            "csrf_token": token,
            "teacher_id": str(conflict_teacher_id),
            "group_id": str(group_id),
            "role": GroupMemberRole.READER.value,
            "active": "y",
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert "Teacher is not eligible for this group" in response.get_data(as_text=True)
    with client.application.app_context():
        assert (
            ReadingGroupMember.query.filter_by(group_id=group_id, teacher_id=conflict_teacher_id).first()
            is None
        )


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
        db.session.add_all(_create_assessor(index) for index in range(7))
        db.session.add_all(_create_student(index) for index in range(9))
        db.session.commit()

        summary = views._auto_generate_groups_for_batch(batch)
        db.session.commit()

        assert summary["created"] == {"English": 2}
        assert summary["backups"] == 0
        assert summary["teachers_assigned"] == 7
        assert summary["underfilled"] == 1

        groups = ReadingGroup.query.filter_by(batch_id=batch.id).order_by(ReadingGroup.id.asc()).all()
        active_counts = sorted(
            sum(1 for member in group.members if member.active and member.role != GroupMemberRole.BACKUP)
            for group in groups
        )
        assert active_counts == [3, 4]
        assert not any(member.role == GroupMemberRole.BACKUP for group in groups for member in group.members)

        assigned, skipped = views._auto_assign_essays(batch)
        db.session.commit()

        assert assigned == 9
        assert skipped == []
        underfilled_group = next(
            group for group in groups if len([member for member in group.members if member.active]) == 3
        )
        full_group = next(
            group for group in groups if len([member for member in group.members if member.active]) == 4
        )
        underfilled_count = EssayAssignment.query.filter_by(batch_id=batch.id, group_id=underfilled_group.id).count()
        full_count = EssayAssignment.query.filter_by(batch_id=batch.id, group_id=full_group.id).count()
        assert full_count > underfilled_count > 0


def test_all_assessors_auto_generate_uses_batch_soft_group_max_for_group_count(client):
    with client.application.app_context():
        batch_max_5 = AssignmentBatch(
            name="Soft Max 5 Batch",
            stage=Stage.STAGE_1,
            status=PlannerStatus.DRAFT,
            planner_algorithm=PlannerAlgorithm.ALL_ASSESSORS_NO_BACKUPS,
            planner_group_soft_max=5,
        )
        db.session.add(batch_max_5)
        db.session.add_all(_create_assessor(index) for index in range(50, 58))
        db.session.add_all(_create_student(index) for index in range(50, 62))
        db.session.commit()

        summary_max_5 = views._auto_generate_groups_for_batch(batch_max_5)
        db.session.commit()

        assert summary_max_5["created"] == {"English": 3}
        groups_max_5 = ReadingGroup.query.filter_by(batch_id=batch_max_5.id).all()
        assert sorted(
            sum(1 for member in group.members if member.active)
            for group in groups_max_5
        ) == [2, 3, 3]

        db.session.query(ReadingGroupMember).delete()
        db.session.query(ReadingGroup).delete()
        db.session.query(AssignmentBatch).delete()
        db.session.query(TeacherLanguage).delete()
        db.session.query(Teacher).delete()
        db.session.query(Student).delete()
        db.session.commit()

        batch_max_6 = AssignmentBatch(
            name="Soft Max 6 Batch",
            stage=Stage.STAGE_1,
            status=PlannerStatus.DRAFT,
            planner_algorithm=PlannerAlgorithm.ALL_ASSESSORS_NO_BACKUPS,
            planner_group_soft_max=6,
        )
        db.session.add(batch_max_6)
        db.session.add_all(_create_assessor(index) for index in range(60, 68))
        db.session.add_all(_create_student(index) for index in range(70, 82))
        db.session.commit()

        summary_max_6 = views._auto_generate_groups_for_batch(batch_max_6)
        db.session.commit()

        assert summary_max_6["created"] == {"English": 2}
        groups_max_6 = ReadingGroup.query.filter_by(batch_id=batch_max_6.id).all()
        assert sorted(
            sum(1 for member in group.members if member.active)
            for group in groups_max_6
        ) == [4, 4]


def test_auto_assign_soft_target_overflows_when_only_eligible_group_is_at_target(client):
    with client.application.app_context():
        batch = AssignmentBatch(
            name="Soft Target Overflow Batch",
            stage=Stage.STAGE_1,
            status=PlannerStatus.DRAFT,
            planner_algorithm=PlannerAlgorithm.ALL_ASSESSORS_NO_BACKUPS,
        )
        valid_group = ReadingGroup(
            name="Valid",
            language="English",
            target_essay_load=1,
            stage=Stage.STAGE_1,
            status=PlannerStatus.DRAFT,
            batch=batch,
        )
        conflict_group = ReadingGroup(
            name="Conflict",
            language="English",
            target_essay_load=1,
            stage=Stage.STAGE_1,
            status=PlannerStatus.DRAFT,
            batch=batch,
        )
        valid_reader = _create_assessor(31, country="Readerland")
        conflict_reader = _create_assessor(32, country="Conflictland")
        students = [_create_student(31 + offset, country="Conflictland") for offset in range(4)]
        db.session.add_all([batch, valid_group, conflict_group, valid_reader, conflict_reader, *students])
        db.session.flush()
        _add_reader(valid_group, valid_reader, role=GroupMemberRole.LEADER)
        _add_reader(conflict_group, conflict_reader, role=GroupMemberRole.LEADER)
        db.session.commit()

        assigned, skipped = views._auto_assign_essays(batch)
        db.session.commit()

        assert assigned == 4
        assert skipped == []
        assert valid_group.target_essay_load == 2
        assert conflict_group.target_essay_load == 2
        assert EssayAssignment.query.filter_by(batch_id=batch.id, group_id=valid_group.id).count() == 4
        assert EssayAssignment.query.filter_by(batch_id=batch.id, group_id=conflict_group.id).count() == 0


def test_auto_assign_repairs_generated_group_country_dead_end_before_assigning(client):
    with client.application.app_context():
        batch = AssignmentBatch(
            name="Country Coverage Repair Batch",
            stage=Stage.STAGE_1,
            status=PlannerStatus.DRAFT,
            planner_algorithm=PlannerAlgorithm.ALL_ASSESSORS_NO_BACKUPS,
        )
        french_group = ReadingGroup(
            name="French",
            language="French",
            target_essay_load=1,
            stage=Stage.STAGE_1,
            status=PlannerStatus.DRAFT,
            batch=batch,
            auto_generated=True,
        )
        english_group = ReadingGroup(
            name="English",
            language="English",
            target_essay_load=1,
            stage=Stage.STAGE_1,
            status=PlannerStatus.DRAFT,
            batch=batch,
            auto_generated=True,
        )
        uk_reader = _create_assessor(41, country="United Kingdom", languages=("English", "French"))
        bulgaria_reader = _create_assessor(42, country="Bulgaria", languages=("French",))
        montenegro_reader = _create_assessor(43, country="Montenegro", languages=("French",))
        romania_reader = _create_assessor(44, country="Romania", languages=("English", "French"))
        french_students = [
            _create_student(41, country="United Kingdom", language="French"),
            _create_student(42, country="United Kingdom", language="French"),
            _create_student(43, country="USA", language="French"),
        ]
        english_student = _create_student(44, country="USA", language="English")
        db.session.add_all(
            [
                batch,
                french_group,
                english_group,
                uk_reader,
                bulgaria_reader,
                montenegro_reader,
                romania_reader,
                *french_students,
                english_student,
            ]
        )
        db.session.flush()
        _add_reader(french_group, uk_reader, role=GroupMemberRole.LEADER)
        _add_reader(french_group, bulgaria_reader)
        _add_reader(french_group, montenegro_reader)
        _add_reader(english_group, romania_reader, role=GroupMemberRole.LEADER)
        db.session.commit()

        assigned, skipped = views._auto_assign_essays(batch)
        db.session.commit()

        assert assigned == 4
        assert skipped == []
        db.session.refresh(french_group)
        french_reader_countries = {
            member.teacher.country
            for member in french_group.members
            if member.active and member.teacher
        }
        assert "United Kingdom" not in french_reader_countries
        assert "Romania" in french_reader_countries
        assert EssayAssignment.query.filter_by(batch_id=batch.id, group_id=french_group.id).count() == 3
        assert ActivityLog.query.filter_by(action="planner_country_coverage_repaired").count() == 1


def test_auto_assign_keeps_languages_separate_without_cross_language_toggle(client):
    with client.application.app_context():
        batch = AssignmentBatch(
            name="Separate Language Batch",
            stage=Stage.STAGE_1,
            status=PlannerStatus.DRAFT,
            planner_algorithm=PlannerAlgorithm.ALL_ASSESSORS_NO_BACKUPS,
            planner_allow_cross_language_assignments=False,
        )
        english_group = ReadingGroup(
            name="English",
            language="English",
            target_essay_load=6,
            stage=Stage.STAGE_1,
            status=PlannerStatus.DRAFT,
            batch=batch,
        )
        french_group = ReadingGroup(
            name="French",
            language="French",
            target_essay_load=6,
            stage=Stage.STAGE_1,
            status=PlannerStatus.DRAFT,
            batch=batch,
        )
        english_readers = [
            _create_assessor(index, languages=("English", "French"))
            for index in range(90, 94)
        ]
        french_readers = [
            _create_assessor(index, languages=("French",))
            for index in range(94, 98)
        ]
        students = [_create_student(index, language="French") for index in range(90, 96)]
        db.session.add_all([batch, english_group, french_group, *english_readers, *french_readers, *students])
        db.session.flush()
        for reader in english_readers:
            _add_reader(english_group, reader)
        for reader in french_readers:
            _add_reader(french_group, reader)
        db.session.commit()

        assigned, skipped = views._auto_assign_essays(batch)
        db.session.commit()

        assert assigned == 6
        assert skipped == []
        assert EssayAssignment.query.filter_by(batch_id=batch.id, group_id=english_group.id).count() == 0
        assert EssayAssignment.query.filter_by(batch_id=batch.id, group_id=french_group.id).count() == 6


def test_auto_assign_uses_compatible_cross_language_groups_to_balance_load(client):
    with client.application.app_context():
        batch = AssignmentBatch(
            name="Cross Language Batch",
            stage=Stage.STAGE_1,
            status=PlannerStatus.DRAFT,
            planner_algorithm=PlannerAlgorithm.ALL_ASSESSORS_NO_BACKUPS,
            planner_allow_cross_language_assignments=True,
        )
        english_group = ReadingGroup(
            name="English",
            language="English",
            target_essay_load=6,
            stage=Stage.STAGE_1,
            status=PlannerStatus.DRAFT,
            batch=batch,
        )
        french_group = ReadingGroup(
            name="French",
            language="French",
            target_essay_load=6,
            stage=Stage.STAGE_1,
            status=PlannerStatus.DRAFT,
            batch=batch,
        )
        english_readers = [
            _create_assessor(index, languages=("English", "French"))
            for index in range(110, 114)
        ]
        french_readers = [
            _create_assessor(index, languages=("French",))
            for index in range(114, 118)
        ]
        students = [_create_student(index, language="French") for index in range(110, 116)]
        db.session.add_all([batch, english_group, french_group, *english_readers, *french_readers, *students])
        db.session.flush()
        for reader in english_readers:
            _add_reader(english_group, reader)
        for reader in french_readers:
            _add_reader(french_group, reader)
        db.session.commit()

        assigned, skipped = views._auto_assign_essays(batch)
        db.session.commit()

        assert assigned == 6
        assert skipped == []
        english_count = EssayAssignment.query.filter_by(batch_id=batch.id, group_id=english_group.id).count()
        french_count = EssayAssignment.query.filter_by(batch_id=batch.id, group_id=french_group.id).count()
        assert english_count > 0
        assert french_count > 0
        assert abs(english_count - french_count) <= 1

        diagnostics = views._planner_batch_diagnostics(batch, [english_group, french_group])
        assert diagnostics.cross_language_assignments == english_count
        assert diagnostics.language_conflicts == 0


def test_auto_assign_rejects_cross_language_group_when_any_active_reader_lacks_language(client):
    with client.application.app_context():
        batch = AssignmentBatch(
            name="Cross Language Incompatible Batch",
            stage=Stage.STAGE_1,
            status=PlannerStatus.DRAFT,
            planner_algorithm=PlannerAlgorithm.ALL_ASSESSORS_NO_BACKUPS,
            planner_allow_cross_language_assignments=True,
        )
        english_group = ReadingGroup(
            name="English",
            language="English",
            target_essay_load=6,
            stage=Stage.STAGE_1,
            status=PlannerStatus.DRAFT,
            batch=batch,
        )
        bilingual_reader = _create_assessor(130, languages=("English", "French"))
        english_only_reader = _create_assessor(131, languages=("English",))
        students = [_create_student(index, language="French") for index in range(130, 132)]
        db.session.add_all([batch, english_group, bilingual_reader, english_only_reader, *students])
        db.session.flush()
        _add_reader(english_group, bilingual_reader)
        _add_reader(english_group, english_only_reader)
        db.session.commit()

        assigned, skipped = views._auto_assign_essays(batch)
        db.session.commit()

        assert assigned == 0
        assert [student.id for student in skipped] == [student.id for student in students]


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


def test_stage1_status_requires_two_spread_readers_after_large_spread(client):
    with client.application.app_context():
        batch = AssignmentBatch(
            name="Spread Requirement Batch",
            stage=Stage.STAGE_1,
            status=PlannerStatus.PUBLISHED,
            planner_algorithm=PlannerAlgorithm.ALL_ASSESSORS_NO_BACKUPS,
        )
        group = ReadingGroup(
            name="Spread Requirement",
            language="English",
            target_essay_load=1,
            stage=Stage.STAGE_1,
            status=PlannerStatus.PUBLISHED,
            batch=batch,
        )
        readers = [_create_assessor(111 + offset, country=f"Readerland {offset}") for offset in range(4)]
        student = _create_student(111, country="Studentland")
        db.session.add_all([batch, group, *readers, student])
        db.session.flush()
        for offset, reader in enumerate(readers):
            _add_reader(group, reader, role=GroupMemberRole.LEADER if offset == 0 else GroupMemberRole.READER)
        assignment = EssayAssignment(
            student_id=student.id,
            group_id=group.id,
            batch_id=batch.id,
            stage=Stage.STAGE_1,
            status=PlannerStatus.PUBLISHED,
        )
        db.session.add(assignment)
        db.session.flush()
        for reader, score in zip(readers, [5, 9, 5, 9], strict=True):
            _add_stage1_score(assignment, reader, score)
        db.session.commit()

        status = views._compute_stage_one_status(assignment)
        views._apply_stage_one_rules(assignment)

        assert status.base_completed is True
        assert status.assigned_readers == 4
        assert status.required_readers == 6
        assert status.expected_scores == 6
        assert status.missing_reader_assignments == 2
        assert status.base_missing_reader_assignments == 0
        assert status.missing_spread_reader_assignments == 2
        assert status.needs_extra is True
        assert status.completed is False
        assert status.recommendation == "Score disparity >3: assign 2 additional readers."
        assert assignment.needs_additional_reading is True
        assert assignment.stage_two_candidate is False


def test_stage1_extra_reader_state_requires_second_spread_reader_before_awaiting_scores(client):
    with client.application.app_context():
        batch = AssignmentBatch(
            name="Second Spread Reader Batch",
            stage=Stage.STAGE_1,
            status=PlannerStatus.PUBLISHED,
            planner_algorithm=PlannerAlgorithm.ALL_ASSESSORS_NO_BACKUPS,
        )
        group = ReadingGroup(
            name="Second Spread Reader",
            language="English",
            target_essay_load=1,
            stage=Stage.STAGE_1,
            status=PlannerStatus.PUBLISHED,
            batch=batch,
        )
        readers = [_create_assessor(121 + offset, country=f"Readerland {offset}") for offset in range(4)]
        extra_a = _create_assessor(126, country="Extra A")
        extra_b = _create_assessor(127, country="Extra B")
        student = _create_student(121, country="Studentland")
        db.session.add_all([batch, group, *readers, extra_a, extra_b, student])
        db.session.flush()
        for offset, reader in enumerate(readers):
            _add_reader(group, reader, role=GroupMemberRole.LEADER if offset == 0 else GroupMemberRole.READER)
        assignment = EssayAssignment(
            student_id=student.id,
            group_id=group.id,
            batch_id=batch.id,
            stage=Stage.STAGE_1,
            status=PlannerStatus.PUBLISHED,
            needs_additional_reading=True,
        )
        db.session.add(assignment)
        db.session.flush()
        for reader, score in zip(readers, [5, 9, 5, 9], strict=True):
            _add_stage1_score(assignment, reader, score)
        db.session.add(
            EssayAssignmentExtraReader(
                assignment_id=assignment.id,
                teacher_id=extra_a.id,
                stage=Stage.STAGE_1.value,
            )
        )
        db.session.commit()

        status = views._compute_stage_one_status(assignment)
        extra_state = views._stage_one_extra_reader_state(assignment, status)

        assert status.assigned_readers == 5
        assert status.required_readers == 6
        assert status.missing_spread_reader_assignments == 1
        assert extra_state.bucket == "needs_assignment"
        assert extra_state.label == "Needs 1 additional reader assignment"

        db.session.add(
            EssayAssignmentExtraReader(
                assignment_id=assignment.id,
                teacher_id=extra_b.id,
                stage=Stage.STAGE_1.value,
            )
        )
        db.session.commit()

        status = views._compute_stage_one_status(assignment)
        extra_state = views._stage_one_extra_reader_state(assignment, status)

        assert status.assigned_readers == 6
        assert status.missing_spread_reader_assignments == 0
        assert status.missing_scores == 2
        assert extra_state.bucket == "awaiting_score"
        assert extra_state.missing_extra_scores == 2

        _add_stage1_score(assignment, extra_a, 7)
        _add_stage1_score(assignment, extra_b, 8)
        db.session.commit()

        status = views._compute_stage_one_status(assignment)
        extra_state = views._stage_one_extra_reader_state(assignment, status)

        assert status.entered_scores == 6
        assert status.expected_scores == 6
        assert status.recommendation == "Additional scores entered; review spread."
        assert extra_state.bucket == "review_spread"


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


def test_planner_absence_repair_does_not_add_only_country_conflicting_free_teacher(client, csrf_token):
    with client.application.app_context():
        batch = AssignmentBatch(
            name="Conflict Free Teacher Repair Batch",
            stage=Stage.STAGE_1,
            status=PlannerStatus.PUBLISHED,
            planner_algorithm=PlannerAlgorithm.ALL_ASSESSORS_NO_BACKUPS,
        )
        group = ReadingGroup(
            name="Conflict Free Teacher Repair",
            language="English",
            target_essay_load=1,
            stage=Stage.STAGE_1,
            status=PlannerStatus.PUBLISHED,
            batch=batch,
            allow_same_country=False,
        )
        readers = [_create_assessor(951 + offset, country=f"Readerland {offset}") for offset in range(3)]
        absent_reader = _create_assessor(955, country="Absentland")
        absent_reader.is_absent = True
        conflict_teacher = _create_assessor(956, country="Studentland")
        student = _create_student(951, country="Studentland")
        db.session.add_all([batch, group, *readers, absent_reader, conflict_teacher, student])
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
        absent_reader_id = absent_reader.id
        conflict_teacher_id = conflict_teacher.id

    with client.session_transaction() as session:
        session["admin_user"] = "admin"

    page = client.get(f"/admin/planner/batches/{batch_id}")
    html = page.get_data(as_text=True)
    assert "Remove absent teacher" in html
    assert "Add available teacher Teacher956 Assessor956" not in html

    token = csrf_token(page)
    response = client.post(
        f"/admin/planner/batches/{batch_id}/absence-repair",
        data={"csrf_token": token},
        follow_redirects=True,
    )

    assert response.status_code == 200
    with client.application.app_context():
        assert ReadingGroupMember.query.filter_by(group_id=group_id, teacher_id=absent_reader_id).first() is None
        assert ReadingGroupMember.query.filter_by(group_id=group_id, teacher_id=conflict_teacher_id).first() is None


def test_planner_absence_repair_flags_projected_country_conflict(client):
    with client.application.app_context():
        batch = AssignmentBatch(
            name="Projected Conflict Repair Batch",
            stage=Stage.STAGE_1,
            status=PlannerStatus.PUBLISHED,
            planner_algorithm=PlannerAlgorithm.ALL_ASSESSORS_NO_BACKUPS,
        )
        group = ReadingGroup(
            name="Projected Conflict Repair",
            language="English",
            target_essay_load=1,
            stage=Stage.STAGE_1,
            status=PlannerStatus.PUBLISHED,
            batch=batch,
            allow_same_country=False,
        )
        conflict_reader = _create_assessor(886, country="Studentland")
        absent_reader = _create_assessor(887, country="Absentland")
        absent_reader.is_absent = True
        student = _create_student(886, country="Studentland")
        db.session.add_all([batch, group, conflict_reader, absent_reader, student])
        db.session.flush()
        _add_reader(group, conflict_reader, role=GroupMemberRole.LEADER)
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

    with client.session_transaction() as session:
        session["admin_user"] = "admin"

    response = client.get(f"/admin/planner/batches/{batch_id}")

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "Projected Conflict Repair would still have country conflict after repair" in html
    assert "Teacher886 Assessor886 (Studentland)" in html


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


def test_planner_absence_repair_does_not_move_country_conflicting_reader(client, csrf_token):
    with client.application.app_context():
        batch = AssignmentBatch(
            name="Conflict Move Repair Batch",
            stage=Stage.STAGE_1,
            status=PlannerStatus.PUBLISHED,
            planner_algorithm=PlannerAlgorithm.ALL_ASSESSORS_NO_BACKUPS,
        )
        target = ReadingGroup(
            name="Conflict Move Target",
            language="English",
            target_essay_load=1,
            stage=Stage.STAGE_1,
            status=PlannerStatus.PUBLISHED,
            batch=batch,
            allow_same_country=False,
        )
        donor = ReadingGroup(
            name="Conflict Move Donor",
            language="English",
            target_essay_load=1,
            stage=Stage.STAGE_1,
            status=PlannerStatus.PUBLISHED,
            batch=batch,
            allow_same_country=False,
        )
        target_active = [_create_assessor(891 + offset, country=f"Targetland {offset}") for offset in range(2)]
        target_absent = [_create_assessor(895 + offset, country=f"Absentland {offset}") for offset in range(2)]
        for teacher in target_absent:
            teacher.is_absent = True
        donor_leader = _create_assessor(899, country="Leaderland")
        conflicting_donor_readers = [
            _create_assessor(900 + offset, country="Studentland") for offset in range(3)
        ]
        target_student = _create_student(891, country="Studentland")
        donor_student = _create_student(892, country="Donor Studentland")
        db.session.add_all(
            [
                batch,
                target,
                donor,
                *target_active,
                *target_absent,
                donor_leader,
                *conflicting_donor_readers,
                target_student,
                donor_student,
            ]
        )
        db.session.flush()
        _add_reader(target, target_active[0], role=GroupMemberRole.LEADER)
        _add_reader(target, target_active[1])
        for teacher in target_absent:
            _add_reader(target, teacher)
        _add_reader(donor, donor_leader, role=GroupMemberRole.LEADER)
        for teacher in conflicting_donor_readers:
            _add_reader(donor, teacher)
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
        conflicting_reader_ids = {teacher.id for teacher in conflicting_donor_readers}

    with client.session_transaction() as session:
        session["admin_user"] = "admin"

    page = client.get(f"/admin/planner/batches/{batch_id}")
    html = page.get_data(as_text=True)
    assert "Move Teacher900 Assessor900" not in html
    assert "Move Teacher901 Assessor901" not in html
    assert "Move Teacher902 Assessor902" not in html

    token = csrf_token(page)
    response = client.post(
        f"/admin/planner/batches/{batch_id}/absence-repair",
        data={"csrf_token": token},
        follow_redirects=True,
    )

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "would still have only 2 active teachers after repair" in html
    with client.application.app_context():
        target_teacher_ids = {
            member.teacher_id
            for member in ReadingGroupMember.query.filter_by(group_id=target_id, active=True).all()
            if not member.teacher.is_absent
        }
        donor_teacher_ids = {
            member.teacher_id
            for member in ReadingGroupMember.query.filter_by(group_id=donor_id, active=True).all()
            if not member.teacher.is_absent
        }
        assert target_teacher_ids.isdisjoint(conflicting_reader_ids)
        assert conflicting_reader_ids.issubset(donor_teacher_ids)


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
        assert status.required_readers == 6
        assert status.expected_scores == 6
        assert status.missing_spread_reader_assignments == 0
        assert status.recommendation == "Additional scores entered; review spread."
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
        primary_student.essay_word_count = 1420
        supplemental_student.essay_word_count = 1375
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
        primary_student_id = primary_student.id
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
    first_essay_text = reader.pages[1].extract_text() or ""
    normalized_first_essay_text = " ".join(first_essay_text.split())
    assert "IPO Essay" not in normalized_first_essay_text
    assert "Group:" in normalized_first_essay_text
    assert "Packet Group A" in normalized_first_essay_text
    assert "Essay:" in normalized_first_essay_text
    assert str(primary_student_id) in normalized_first_essay_text
    assert "Word count:" in normalized_first_essay_text
    assert "1420" in normalized_first_essay_text
    assert "Score:" in normalized_first_essay_text
    assert "/10" in normalized_first_essay_text


def test_public_assessor_groups_pdf_is_public_safe_and_compact(client):
    with client.application.app_context():
        batch = AssignmentBatch(
            name="Public Assessor Batch",
            stage=Stage.STAGE_1,
            status=PlannerStatus.PUBLISHED,
            planner_algorithm=PlannerAlgorithm.STRICT_FOUR_WITH_BACKUPS,
        )
        teachers = [_create_assessor(6000 + index) for index in range(100)]
        students = [
            _create_student(6000 + index, country=f"Hidden Country {index}")
            for index in range(25)
        ]
        db.session.add(batch)
        db.session.add_all(teachers + students)
        db.session.flush()

        for group_index in range(25):
            group = ReadingGroup(
                name=f"English Group {group_index + 1:02d}",
                language="English",
                stage=Stage.STAGE_1,
                status=PlannerStatus.PUBLISHED,
                batch=batch,
            )
            db.session.add(group)
            db.session.flush()
            for offset in range(4):
                role = GroupMemberRole.LEADER if offset == 0 else GroupMemberRole.READER
                _add_reader(group, teachers[group_index * 4 + offset], role=role)
            db.session.add(
                EssayAssignment(
                    student_id=students[group_index].id,
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

    planner_page = client.get(f"/admin/planner/batches/{batch_id}")
    assert planner_page.status_code == 200
    assert f"/admin/planner/batches/{batch_id}/export/assessor-groups.pdf" in planner_page.get_data(as_text=True)

    response = client.get(f"/admin/planner/batches/{batch_id}/export/assessor-groups.pdf")
    assert response.status_code == 200
    assert "application/pdf" in response.headers.get("Content-Type", "")

    reader = PdfReader(BytesIO(response.data))
    assert len(reader.pages) <= 10
    pdf_text = " ".join((page.extract_text() or "") for page in reader.pages)
    assert "Assessor Groups" in pdf_text
    assert "English Group 01" in pdf_text
    assert "Teacher6000 Assessor6000" in pdf_text
    assert "Student6000" not in pdf_text
    assert "Hidden Country" not in pdf_text


def test_individual_teacher_packet_embeds_unicode_teacher_name(client):
    with client.application.app_context():
        batch = AssignmentBatch(
            name="Unicode Packet Batch",
            stage=Stage.STAGE_1,
            status=PlannerStatus.PUBLISHED,
            planner_algorithm=PlannerAlgorithm.ALL_ASSESSORS_NO_BACKUPS,
        )
        group = ReadingGroup(
            name="Łódź Ελληνικά Кир",
            language="English",
            stage=Stage.STAGE_1,
            status=PlannerStatus.PUBLISHED,
            batch=batch,
        )
        packet_teacher = _create_assessor(405, country="Poland")
        packet_teacher.first_name = "Bartosz"
        packet_teacher.last_name = "Działoszyński"
        student = _create_student(405, country="Unicode Country")
        db.session.add_all([batch, group, packet_teacher, student])
        db.session.flush()
        _add_reader(group, packet_teacher, role=GroupMemberRole.LEADER)
        assignment = EssayAssignment(
            student_id=student.id,
            group_id=group.id,
            batch_id=batch.id,
            stage=Stage.STAGE_1,
            status=PlannerStatus.PUBLISHED,
        )
        db.session.add(assignment)
        db.session.flush()

        upload_folder = client.application.config["UPLOAD_FOLDER"]
        student.uploaded_filename = f"unicode-{student.id}.pdf"
        _write_valid_pdf(Path(upload_folder) / student.uploaded_filename)
        db.session.commit()
        batch_id = batch.id
        packet_teacher_id = packet_teacher.id

    with client.session_transaction() as session:
        session["admin_user"] = "admin"

    response = client.get(
        f"/admin/planner/batches/{batch_id}/teachers/{packet_teacher_id}/reader-packet.pdf",
        follow_redirects=False,
    )

    assert response.status_code == 200
    reader = PdfReader(BytesIO(response.data))
    title_page_text = " ".join((reader.pages[0].extract_text() or "").split())
    essay_page_text = " ".join((reader.pages[1].extract_text() or "").split())
    assert "Bartosz Działoszyński" in title_page_text
    assert "Łódź" in essay_page_text
    assert "Ελληνικά" in essay_page_text
    assert "Кир" in essay_page_text


def test_stage3_packet_uses_compact_essay_overlay(client, csrf_token):
    with client.application.app_context():
        batch = AssignmentBatch(
            name="Stage 3 Packet Batch",
            stage=Stage.STAGE_2,
            status=PlannerStatus.PUBLISHED,
        )
        group = ReadingGroup(
            name="Stage 3 Source Group",
            language="English",
            stage=Stage.STAGE_2,
            status=PlannerStatus.PUBLISHED,
            batch=batch,
        )
        student = _create_student(501, country="Stage 3 Country")
        student.essay_word_count = 1525
        db.session.add_all([batch, group, student])
        db.session.flush()
        assignment = EssayAssignment(
            student_id=student.id,
            group_id=group.id,
            batch_id=batch.id,
            stage=Stage.STAGE_2,
            status=PlannerStatus.PUBLISHED,
            stage_three_recommended=True,
        )
        db.session.add(assignment)
        db.session.flush()

        upload_folder = client.application.config["UPLOAD_FOLDER"]
        student.uploaded_filename = f"stage3-{student.id}.pdf"
        _write_valid_pdf(Path(upload_folder) / student.uploaded_filename)
        db.session.commit()
        assignment_id = assignment.id
        student_id = student.id

    with client.session_transaction() as session:
        session["admin_user"] = "admin"

    page = client.get("/admin/stage3/packets")
    token = csrf_token(page)
    response = client.post(
        "/admin/stage3/packets",
        data={
            "csrf_token": token,
            "committee_label": "Compact Committee",
            "member_names": "Committee Member",
            "essay_ids": [str(assignment_id)],
            "submit": "Generate packets",
        },
        follow_redirects=False,
    )

    assert response.status_code == 200
    assert "application/pdf" in response.headers.get("Content-Type", "")
    reader = PdfReader(BytesIO(response.data))
    assert len(reader.pages) >= 2
    essay_text = reader.pages[1].extract_text() or ""
    normalized_essay_text = " ".join(essay_text.split())
    assert "IPO Stage 3 Review" not in normalized_essay_text
    assert "Committee:" in normalized_essay_text
    assert "Compact Committee" in normalized_essay_text
    assert "Essay:" in normalized_essay_text
    assert str(student_id) in normalized_essay_text
    assert "Word count:" in normalized_essay_text
    assert "1525" in normalized_essay_text
    assert "Comments:" in normalized_essay_text
