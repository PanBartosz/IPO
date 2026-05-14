from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from uuid import uuid4

from ipo_app import create_app
from ipo_app.extensions import db
from ipo_app.models import (
    AssignmentBatch,
    EssayAssignment,
    EssayAssignmentExtraReader,
    GroupMemberRole,
    PlannerStatus,
    ReadingGroup,
    ReadingGroupMember,
    Stage,
    Student,
    Teacher,
    TeacherLanguage,
)


def _teacher(label: str, run_id: str, *, country: str = "Readerland") -> Teacher:
    teacher = Teacher(
        country=country,
        first_name="E2E",
        last_name=label,
        email=f"e2e-{run_id}-{label.lower()}@example.test",
        school="E2E School",
        languages="English",
        meal_preference="No preference",
        tshirt_size="M",
        declared_assessor_competence=True,
    )
    teacher.language_entries.append(TeacherLanguage(language="English"))
    db.session.add(teacher)
    db.session.flush()
    return teacher


def _student(label: str, run_id: str) -> Student:
    student = Student(
        country=f"Studentland {label}",
        first_name="E2E",
        last_name=label,
        email=f"e2e-{run_id}-{label.lower()}@example.test",
        school="E2E School",
        date_of_birth=datetime(2000, 1, 1).date(),
        essay_language="English",
        keyboard_preference="QWERTY",
        meal_preference="No preference",
        essay_finalized=True,
        essay_finalized_at=datetime.utcnow(),
    )
    db.session.add(student)
    db.session.flush()
    return student


def main() -> None:
    app = create_app()
    output_path = Path("output/e2e_teacher_scores.json")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    run_id = uuid4().hex[:10]

    with app.app_context():
        target = _teacher("TeacherScores", run_id)
        other_readers = [_teacher(f"Reader{index}", run_id, country=f"Readerland {index}") for index in range(1, 4)]

        batch = AssignmentBatch(
            name=f"E2E Teacher Scores {run_id}",
            stage=Stage.STAGE_1,
            status=PlannerStatus.PUBLISHED,
            published_at=datetime.utcnow(),
        )
        db.session.add(batch)
        db.session.flush()

        group = ReadingGroup(
            name=f"E2E Group {run_id}",
            stage=Stage.STAGE_1,
            language="English",
            status=PlannerStatus.PUBLISHED,
            batch_id=batch.id,
        )
        db.session.add(group)
        db.session.flush()

        for teacher in [target, *other_readers]:
            db.session.add(
                ReadingGroupMember(
                    group_id=group.id,
                    teacher_id=teacher.id,
                    role=GroupMemberRole.READER,
                    active=True,
                )
            )

        stage1_student = _student("Stage1", run_id)
        stage1_assignment = EssayAssignment(
            student_id=stage1_student.id,
            group_id=group.id,
            batch_id=batch.id,
            stage=Stage.STAGE_1,
            status=PlannerStatus.PUBLISHED,
        )
        db.session.add(stage1_assignment)

        stage2_student = _student("Stage2", run_id)
        stage2_assignment = EssayAssignment(
            student_id=stage2_student.id,
            group_id=group.id,
            batch_id=batch.id,
            stage=Stage.STAGE_1,
            status=PlannerStatus.PUBLISHED,
            stage_two_candidate=True,
        )
        db.session.add(stage2_assignment)
        db.session.flush()
        db.session.add(
            EssayAssignmentExtraReader(
                assignment_id=stage2_assignment.id,
                teacher_id=target.id,
                stage=Stage.STAGE_2.value,
            )
        )

        db.session.commit()

        payload = {
            "run_id": run_id,
            "teacher_id": target.id,
            "teacher_name": f"{target.first_name} {target.last_name}",
            "stage1_assignment_id": stage1_assignment.id,
            "stage1_student_id": stage1_student.id,
            "stage2_assignment_id": stage2_assignment.id,
            "stage2_student_id": stage2_student.id,
        }
        output_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
