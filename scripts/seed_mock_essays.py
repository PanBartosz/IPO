#!/usr/bin/env python

"""Generate or copy mock essay uploads for selected students."""

from __future__ import annotations

import argparse
import random
import textwrap
from datetime import datetime
from pathlib import Path

from scripts.utils import seed_helpers as helpers

from ipo_app.extensions import db  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create mock essay uploads for testing.")
    parser.add_argument("--student-id", dest="student_ids", action="append", type=int, help="Limit to specific student ID (repeatable).")
    parser.add_argument("--country", dest="countries", action="append", help="Limit to students from a given country (repeatable).")
    parser.add_argument("--include-absent", action="store_true", help="Include students marked as absent.")
    parser.add_argument("--source", type=Path, help="Path to a PDF template to copy for each student.")
    parser.add_argument("--finalize", action="store_true", help="Mark uploaded essays as finalized.")
    parser.add_argument("--overwrite", action="store_true", help="Replace existing uploads.")
    parser.add_argument("--limit", type=int, help="Randomly sample N students before processing.")
    parser.add_argument("--random-seed", type=int, help="Seed for random sampling.")
    parser.add_argument("--dry-run", action="store_true", help="Snapshot changes without committing them.")
    return parser.parse_args()


def build_placeholder_writer(student) -> callable:
    def _writer(destination: Path) -> None:
        from reportlab.lib.pagesizes import A4  # noqa: PLC0415
        from reportlab.pdfgen import canvas  # noqa: PLC0415

        c = canvas.Canvas(str(destination), pagesize=A4)
        width, height = A4
        margin = 72

        c.setFont("Helvetica-Bold", 20)
        c.drawString(margin, height - margin, f"Essay {student.id}")

        c.setFont("Helvetica", 12)
        lines = [
            f"Student: {student.first_name} {student.last_name}",
            f"Country: {student.country}",
            f"Language: {student.essay_language}",
            "",
            "This is a placeholder essay generated for testing workflows.",
            "Replace with real content when executing manual test scenarios.",
        ]

        y = height - margin - 40
        for line in lines:
            c.drawString(margin, y, line)
            y -= 18

        body = (
            "Philosophy invites us to question the assumptions that give shape to our shared reality. "
            "When graders review this document they can focus on interface flows instead of the prose."
        )
        wrapped = textwrap.wrap(body, width=90)
        text_obj = c.beginText(margin, y - 24)
        text_obj.setFont("Helvetica-Oblique", 11)
        for line in wrapped:
            text_obj.textLine(line)
        c.drawText(text_obj)
        c.showPage()
        c.save()

    return _writer


def main() -> None:
    args = parse_args()
    rng = random.Random(args.random_seed)

    with helpers.app_context():
        students = helpers.fetch_students(
            student_ids=args.student_ids,
            countries=args.countries,
            include_absent=args.include_absent,
        )

        if args.limit is not None and args.limit >= 0 and len(students) > args.limit:
            students = rng.sample(students, args.limit)

        if not students:
            print("No students matched the filter criteria.")
            return

        source_path = args.source.resolve() if args.source else None
        if source_path and not source_path.exists():
            raise FileNotFoundError(source_path)

        processed = 0
        skipped_existing = 0

        for student in students:
            if student.is_absent and not args.include_absent:
                continue

            if student.uploaded_filename and not args.overwrite:
                skipped_existing += 1
                continue

            if source_path:
                stored_path = helpers.copy_pdf_to_student(
                    student,
                    source_path,
                    overwrite=args.overwrite,
                )
            else:
                writer = build_placeholder_writer(student)
                stored_path = helpers.write_pdf_to_student(
                    student,
                    writer,
                    overwrite=args.overwrite,
                )

            if stored_path is None:
                continue

            if args.finalize:
                student.essay_finalized = True
                student.essay_finalized_at = datetime.utcnow()
            else:
                student.essay_finalized = False
                student.essay_finalized_at = None

            processed += 1

        if args.dry_run:
            db.session.rollback()
        else:
            db.session.commit()

        print(f"Processed {processed} students.")
        if skipped_existing:
            print(f"Skipped {skipped_existing} students with existing uploads (use --overwrite to replace).")


if __name__ == "__main__":
    main()
