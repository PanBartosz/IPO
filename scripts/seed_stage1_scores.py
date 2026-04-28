#!/usr/bin/env python

"""Populate Stage 1 scores for assigned readers."""

from __future__ import annotations

import argparse
import random
from datetime import datetime

from scripts.utils import seed_helpers as helpers

from ipo_app.extensions import db  # noqa: E402
from ipo_app.models import Stage  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Seed Stage 1 scores for mock testing.")
    parser.add_argument("--batch", type=int, help="Only process assignments from this batch ID.")
    parser.add_argument(
        "--student-id",
        dest="student_ids",
        action="append",
        type=int,
        help="Limit to specific student ID (repeatable).",
    )
    parser.add_argument("--min-score", type=float, default=4.5, help="Lower bound for generated scores.")
    parser.add_argument("--max-score", type=float, default=9.5, help="Upper bound for generated scores.")
    parser.add_argument("--step", type=float, default=0.1, help="Score increment when non-statutory scores are allowed.")
    parser.add_argument(
        "--allow-non-statutory-scores",
        action="store_true",
        help="Use the numeric step instead of the statutory IPO score grid.",
    )
    parser.add_argument("--finalize", action="store_true", help="Mark seeded scores as teacher-finalized.")
    parser.add_argument("--overwrite", action="store_true", help="Replace existing Stage 1 scores.")
    parser.add_argument(
        "--skip-rule-checks",
        action="store_true",
        help="Skip Stage 1 rule evaluation after seeding.",
    )
    parser.add_argument(
        "--stage2-target-rate",
        type=float,
        default=0.25,
        help="Approximate share of essays that should qualify for Stage 2 (0-1).",
    )
    parser.add_argument(
        "--high-spread-rate",
        type=float,
        default=0.10,
        help="Probability of forcing a wide spread (>3) to trigger additional readers (0-1).",
    )
    parser.add_argument(
        "--high-spread-gap",
        type=float,
        default=3.5,
        help="Target gap between lowest and highest score when forcing a wide spread.",
    )
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
        statutory_only=not args.allow_non_statutory_scores,
        finalize=args.finalize,
    )
    score_options.validate()

    stage2_target_rate = min(max(args.stage2_target_rate, 0.0), 1.0)
    high_spread_rate = min(max(args.high_spread_rate, 0.0), 1.0)
    high_spread_gap = max(3.1, args.high_spread_gap)

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

            assessors = helpers.stage_assessors(assignment, Stage.STAGE_1, include_group=True)
            if not assessors:
                continue

            existing_scores_present = any(
                score.stage == Stage.STAGE_1 and score.score is not None for score in assignment.scores
            )

            should_promote = rng.random() < stage2_target_rate
            force_high_spread = rng.random() < high_spread_rate and len(assessors) >= 2

            if existing_scores_present and not args.overwrite:
                should_promote = False
                force_high_spread = False
            if force_high_spread:
                should_promote = False

            if should_promote:
                target_mean = rng.uniform(7.2, 8.2)
                target_std = 0.35
            else:
                target_mean = rng.uniform(5.0, 6.3)
                target_std = 0.6

            changed = False
            updated_records: list = []

            for assessor in assessors:
                teacher = assessor.teacher
                if not teacher or teacher.is_absent:
                    continue

                record = helpers.ensure_score_record(
                    assignment,
                    student.id,
                    teacher.id,
                    Stage.STAGE_1,
                )

                if record.score is not None and not args.overwrite:
                    skipped += 1
                    continue

                raw_score = rng.normalvariate(target_mean, target_std)
                score_value = score_options.quantize(raw_score)
                helpers.update_score(record, score_value, options=score_options, now=now)
                updated_records.append(record)
                changed = True
                total_scores += 1

            if force_high_spread and len(updated_records) >= 2:
                low_idx = rng.randrange(len(updated_records))
                high_idx = low_idx
                while high_idx == low_idx:
                    high_idx = rng.randrange(len(updated_records))

                low_value = score_options.quantize(target_mean - high_spread_gap / 2)
                high_value = score_options.quantize(low_value + high_spread_gap)

                if high_value > score_options.max_score:
                    high_value = score_options.max_score
                    low_value = score_options.quantize(high_value - high_spread_gap)
                if low_value < score_options.min_score:
                    low_value = score_options.min_score
                    high_value = score_options.quantize(low_value + high_spread_gap)

                if high_value - low_value < 3.0:
                    high_value = score_options.quantize(low_value + 3.2)
                    if high_value > score_options.max_score:
                        high_value = score_options.max_score
                        low_value = score_options.quantize(high_value - 3.2)

                helpers.update_score(updated_records[low_idx], low_value, options=score_options, now=now)
                helpers.update_score(updated_records[high_idx], high_value, options=score_options, now=now)

            if should_promote and updated_records:
                stage1_values = [
                    score.score
                    for score in assignment.scores
                    if score.stage == Stage.STAGE_1 and score.score is not None
                ]
                if stage1_values:
                    average = sum(stage1_values) / len(stage1_values)
                    if average < 7.0:
                        boost = 7.0 - average + rng.uniform(0.2, 0.4)
                        for record in updated_records:
                            boosted = score_options.quantize(min(score_options.max_score, record.score + boost))
                            helpers.update_score(record, boosted, options=score_options, now=now)

            if changed:
                total_assignments += 1
                if not args.skip_rule_checks:
                    helpers.apply_stage1_rules(assignment)

        if args.dry_run:
            db.session.rollback()
        else:
            db.session.commit()

        print(f"Seeded {total_scores} Stage 1 scores across {total_assignments} assignments.")
        if skipped and not args.overwrite:
            print(f"Skipped {skipped} existing scores (use --overwrite to replace).")


if __name__ == "__main__":
    main()
