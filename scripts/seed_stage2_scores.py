#!/usr/bin/env python

"""Populate Stage 2 scores for assigned extra readers."""

from __future__ import annotations

import argparse
import random
from datetime import datetime

from scripts.utils import seed_helpers as helpers

from ipo_app.extensions import db  # noqa: E402
from ipo_app.models import Stage  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Seed Stage 2 scores for candidates.")
    parser.add_argument("--batch", type=int, help="Only process assignments from this batch ID.")
    parser.add_argument("--student-id", dest="student_ids", action="append", type=int, help="Limit to specific student ID (repeatable).")
    parser.add_argument("--min-score", type=float, default=6.5, help="Lower bound for generated scores.")
    parser.add_argument("--max-score", type=float, default=9.5, help="Upper bound for generated scores.")
    parser.add_argument("--step", type=float, default=0.1, help="Score increment (e.g. 0.1).")
    parser.add_argument("--finalize", action="store_true", help="Mark seeded scores as teacher-finalized.")
    parser.add_argument("--overwrite", action="store_true", help="Replace existing Stage 2 scores.")
    parser.add_argument("--include-non-candidates", action="store_true", help="Include students not flagged for Stage 2.")
    parser.add_argument("--random-seed", type=int, help="Random seed for reproducible scores.")
    parser.add_argument("--dry-run", action="store_true", help="Preview changes without committing.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    rng = random.Random(args.random_seed)

    score_options = helpers.ScoreOptions(
        min_score=args.min_score,
        max_score=args.max_score,
        step=args.step,
        finalize=args.finalize,
    )
    score_options.validate()

    with helpers.app_context():
        assignments = helpers.iter_assignments(
            stage=Stage.STAGE_1,
            batch_id=args.batch,
            student_ids=args.student_ids,
        )

        if not assignments:
            print("No assignments matched the filter criteria.")
            return

        total_scores = 0
        total_assignments = 0
        skipped = 0
        now = datetime.utcnow()

        for assignment in assignments:
            student = assignment.student
            if not student or student.is_absent:
                continue
            if not assignment.stage_two_candidate and not args.include_non_candidates:
                continue

            assessors = helpers.stage_assessors(assignment, Stage.STAGE_2, include_group=False)
            if not assessors:
                continue

            changed = False
            for assessor in assessors:
                teacher = assessor.teacher
                if not teacher or teacher.is_absent:
                    continue

                record = helpers.ensure_score_record(
                    assignment,
                    student.id,
                    teacher.id,
                    Stage.STAGE_2,
                )

                if record.score is not None and not args.overwrite:
                    skipped += 1
                    continue

                score_value = score_options.generate(rng)
                helpers.update_score(record, score_value, options=score_options, now=now)
                changed = True
                total_scores += 1

            if changed:
                total_assignments += 1

        if args.dry_run:
            db.session.rollback()
        else:
            db.session.commit()

        print(f"Seeded {total_scores} Stage 2 scores across {total_assignments} assignments.")
        if skipped and not args.overwrite:
            print(f"Skipped {skipped} existing scores (use --overwrite to replace).")


if __name__ == "__main__":
    main()
