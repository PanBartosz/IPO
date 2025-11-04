"""Shared helpers for seeding mock IPO grading data."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable, Iterable, Iterator, Sequence
import random
import shutil
import sys

CURRENT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = CURRENT_DIR.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from ipo_app import create_app  # noqa: E402
from ipo_app.extensions import db  # noqa: E402
from ipo_app.models import (  # noqa: E402
    EssayAssignment,
    EssayScore,
    Stage,
    Student,
    Teacher,
)
from ipo_app.views import _apply_stage_one_rules, _get_upload_folder, _stage_assessors  # noqa: E402


@contextmanager
def app_context() -> Iterator[None]:
    """Provide an application context for standalone scripts."""
    app = create_app()
    with app.app_context():
        yield


@dataclass
class ScoreOptions:
    """Configuration for generating mock scores."""

    min_score: float = 6.0
    max_score: float = 9.0
    step: float = 0.1
    finalize: bool = False
    admin_entered: bool = True
    admin_override: bool = False

    def validate(self) -> None:
        if self.min_score > self.max_score:
            raise ValueError("min_score cannot be greater than max_score")
        if self.step <= 0:
            raise ValueError("step must be positive")

    def generate(self, rng: random.Random) -> float:
        value = rng.uniform(self.min_score, self.max_score)
        return self.quantize(value)

    def quantize(self, value: float) -> float:
        self.validate()
        clamped = max(self.min_score, min(self.max_score, value))
        scaled = round(clamped / self.step)
        quantized = scaled * self.step
        return round(quantized, 2)


def fetch_students(
    *,
    student_ids: Sequence[int] | None = None,
    countries: Sequence[str] | None = None,
    include_absent: bool = False,
) -> list[Student]:
    query = Student.query
    if student_ids:
        query = query.filter(Student.id.in_(student_ids))
    if countries:
        query = query.filter(Student.country.in_(countries))
    if not include_absent:
        query = query.filter(Student.is_absent.is_(False))
    return query.order_by(Student.id.asc()).all()


def essay_upload_path() -> Path:
    """Resolve the upload directory."""
    return _get_upload_folder()


def prepare_student_upload(student: Student, *, filename: str | None = None, overwrite: bool = False) -> Path | None:
    """Reserve a filename for a student's essay upload."""
    if student.is_absent:
        return None
    upload_dir = essay_upload_path()
    upload_dir.mkdir(parents=True, exist_ok=True)

    if student.uploaded_filename and not overwrite:
        return upload_dir / student.uploaded_filename

    if filename is None:
        timestamp = datetime.utcnow().strftime("%Y%m%d%H%M%S")
        filename = f"student-{student.id}-{timestamp}.pdf"

    destination = upload_dir / filename

    if student.uploaded_filename and overwrite:
        old_path = upload_dir / student.uploaded_filename
        if old_path.exists() and old_path != destination:
            old_path.unlink()

    if destination.exists():
        destination.unlink()

    student.uploaded_filename = destination.name
    student.uploaded_at = datetime.utcnow()
    student.essay_finalized = False
    student.essay_finalized_at = None
    return destination


def copy_pdf_to_student(student: Student, source: Path, *, filename: str | None = None, overwrite: bool = False) -> Path | None:
    """Copy or replace a student's essay upload with a PDF."""
    if student.is_absent:
        return None
    if not source.exists():
        raise FileNotFoundError(source)
    destination = prepare_student_upload(student, filename=filename, overwrite=overwrite)
    if destination is None:
        return None
    shutil.copy2(source, destination)
    return destination


def write_pdf_to_student(
    student: Student,
    writer: Callable[[Path], None],
    *,
    filename: str | None = None,
    overwrite: bool = False,
) -> Path | None:
    """Generate a PDF via callback and store it for the student."""
    destination = prepare_student_upload(student, filename=filename, overwrite=overwrite)
    if destination is None:
        return None
    writer(destination)
    return destination


def iter_assignments(
    *,
    stage: Stage,
    batch_id: int | None = None,
    student_ids: Sequence[int] | None = None,
) -> Iterable[EssayAssignment]:
    query = (
        EssayAssignment.query.join(Student)
        .filter(
            EssayAssignment.stage == stage,
            Student.is_absent.is_(False),
        )
        .order_by(EssayAssignment.student_id.asc())
    )
    if batch_id is not None:
        query = query.filter(EssayAssignment.batch_id == batch_id)
    if student_ids:
        query = query.filter(EssayAssignment.student_id.in_(student_ids))
    return query.all()


def apply_stage1_rules(assignment: EssayAssignment) -> None:
    _apply_stage_one_rules(assignment)


def score_record_for(
    assignment: EssayAssignment,
    teacher_id: int,
    stage: Stage,
) -> EssayScore | None:
    return (
        EssayScore.query.filter_by(
            assignment_id=assignment.id,
            teacher_id=teacher_id,
            stage=stage,
        )
        .first()
    )


def ensure_score_record(
    assignment: EssayAssignment,
    student_id: int,
    teacher_id: int,
    stage: Stage,
) -> EssayScore:
    existing = score_record_for(assignment, teacher_id, stage)
    if existing:
        return existing
    record = EssayScore(
        student_id=student_id,
        teacher_id=teacher_id,
        assignment_id=assignment.id,
        stage=stage,
    )
    db.session.add(record)
    return record


def update_score(
    record: EssayScore,
    score: float,
    *,
    options: ScoreOptions,
    now: datetime,
) -> None:
    record.score = score
    record.submitted_at = now
    record.admin_entered = options.admin_entered
    record.admin_override = options.admin_override
    record.admin_updated_at = now
    record.teacher_finalized = options.finalize
    record.teacher_finalized_at = now if options.finalize else None
    record.locked_by_admin = False


def stage_assessors(assignment: EssayAssignment, stage: Stage, include_group: bool = False):
    return _stage_assessors(assignment, stage, include_group=include_group)


def ensure_teacher_can_grade(student: Student, teacher: Teacher) -> bool:
    return not teacher.is_absent and student.essay_language in (teacher.languages or "").split(",")
