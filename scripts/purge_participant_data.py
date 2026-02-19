#!/usr/bin/env python

"""Purge participant-related records while keeping app settings and core config."""

from __future__ import annotations

import argparse
import os
import sys
from dataclasses import dataclass
from pathlib import Path

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(CURRENT_DIR, ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from ipo_app import create_app  # noqa: E402
from ipo_app.extensions import db  # noqa: E402
from ipo_app.models import (  # noqa: E402
    ActivityLog,
    AppSetting,
    AssignmentBatch,
    CommunicationCampaign,
    CommunicationRecipient,
    DelegationInvite,
    EssayAssignment,
    EssayAssignmentExtraReader,
    EssayScore,
    EssayUpload,
    PasswordResetToken,
    ReadingGroup,
    ReadingGroupMember,
    Student,
    Survey,
    SurveyAssignment,
    SurveyQuestion,
    SurveyResponse,
    Teacher,
    TeacherLanguage,
    TeacherMessage,
    TeacherMessageTemplate,
)


@dataclass(frozen=True)
class PurgeTarget:
    label: str
    model: type[db.Model]


BASE_PURGE_PLAN: tuple[PurgeTarget, ...] = (
    PurgeTarget("survey_responses", SurveyResponse),
    PurgeTarget("survey_assignments", SurveyAssignment),
    PurgeTarget("survey_questions", SurveyQuestion),
    PurgeTarget("surveys", Survey),
    PurgeTarget("essay_assignment_extra_readers", EssayAssignmentExtraReader),
    PurgeTarget("essay_scores", EssayScore),
    PurgeTarget("essay_assignments", EssayAssignment),
    PurgeTarget("reading_group_members", ReadingGroupMember),
    PurgeTarget("reading_groups", ReadingGroup),
    PurgeTarget("assignment_batches", AssignmentBatch),
    PurgeTarget("essay_uploads", EssayUpload),
    PurgeTarget("password_reset_tokens", PasswordResetToken),
    PurgeTarget("teacher_messages", TeacherMessage),
    PurgeTarget("teacher_languages", TeacherLanguage),
    PurgeTarget("communication_recipients", CommunicationRecipient),
    PurgeTarget("communication_campaigns", CommunicationCampaign),
    PurgeTarget("delegation_invites", DelegationInvite),
    PurgeTarget("students", Student),
    PurgeTarget("teachers", Teacher),
)

ACTIVITY_LOG_PURGE = PurgeTarget("activity_logs", ActivityLog)


def _count_rows(model: type[db.Model]) -> int:
    return db.session.query(model).count()


def _collect_counts(targets: tuple[PurgeTarget, ...]) -> dict[str, int]:
    return {target.label: _count_rows(target.model) for target in targets}


def _print_counts(title: str, targets: tuple[PurgeTarget, ...], counts: dict[str, int]) -> None:
    print(title)
    for target in targets:
        print(f"  - {target.label}: {counts[target.label]}")
    print(f"  Total targeted rows: {sum(counts.values())}")


def _purge_targets(targets: tuple[PurgeTarget, ...]) -> dict[str, int]:
    deleted: dict[str, int] = {}
    for target in targets:
        removed = db.session.query(target.model).delete(synchronize_session=False)
        deleted[target.label] = int(removed or 0)
    return deleted


def _upload_folder(app) -> Path:
    folder = Path(app.config.get("UPLOAD_FOLDER", Path(app.instance_path) / "uploads"))
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def _collect_upload_filenames() -> set[str]:
    names: set[str] = set()
    for (value,) in db.session.query(Student.uploaded_filename).filter(Student.uploaded_filename.isnot(None)).all():
        if value:
            names.add(value)
    for (value,) in db.session.query(EssayUpload.filename).all():
        if value:
            names.add(value)
    return names


def _safe_upload_path(base: Path, raw_name: str) -> Path | None:
    candidate = Path(raw_name)
    if candidate.is_absolute() or ".." in candidate.parts:
        return None
    base_resolved = base.resolve()
    path_resolved = (base / candidate).resolve()
    try:
        path_resolved.relative_to(base_resolved)
    except ValueError:
        return None
    return path_resolved


def _delete_upload_files(base: Path, filenames: set[str]) -> tuple[int, int, int, int]:
    removed = 0
    missing = 0
    skipped_unsafe = 0
    errors = 0

    for name in sorted(filenames):
        safe_path = _safe_upload_path(base, name)
        if safe_path is None:
            skipped_unsafe += 1
            continue
        if not safe_path.exists():
            missing += 1
            continue
        try:
            safe_path.unlink()
            removed += 1
        except OSError as exc:
            errors += 1
            print(f"  ! Could not remove {safe_path}: {exc}")

    return removed, missing, skipped_unsafe, errors


def _print_preserved_counts() -> None:
    print("Preserved tables (for confidence check):")
    print(f"  - app_settings: {_count_rows(AppSetting)}")
    print(f"  - teacher_message_templates: {_count_rows(TeacherMessageTemplate)}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Purge participant-related data (students, teachers, invitations and dependent records) "
            "while keeping settings and static templates."
        )
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview counts only. No data will be modified.",
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Required to execute destructive purge.",
    )
    parser.add_argument(
        "--purge-activity-logs",
        action="store_true",
        help="Also delete all activity logs (default keeps them).",
    )
    parser.add_argument(
        "--delete-upload-files",
        action="store_true",
        help="Also delete uploaded files referenced by participant records from UPLOAD_FOLDER.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    app = create_app()

    with app.app_context():
        targets: tuple[PurgeTarget, ...] = BASE_PURGE_PLAN + ((ACTIVITY_LOG_PURGE,) if args.purge_activity_logs else ())
        upload_filenames = _collect_upload_filenames() if args.delete_upload_files else set()

        before = _collect_counts(targets)
        _print_counts("Targeted rows before purge:", targets, before)
        if args.delete_upload_files:
            print(f"Referenced upload files queued for deletion: {len(upload_filenames)}")
        _print_preserved_counts()

        if args.dry_run:
            print("Dry run complete. No rows were deleted.")
            return 0

        if not args.yes:
            print("Refusing to purge without --yes. Re-run with --dry-run to preview impact.")
            return 2

        try:
            deleted = _purge_targets(targets)
            db.session.commit()
        except Exception:
            db.session.rollback()
            raise

        _print_counts("Deleted rows:", targets, deleted)
        after = _collect_counts(targets)
        _print_counts("Targeted rows after purge:", targets, after)
        _print_preserved_counts()

        if args.delete_upload_files:
            base = _upload_folder(app)
            removed, missing, skipped_unsafe, errors = _delete_upload_files(base, upload_filenames)
            print("Upload file cleanup:")
            print(f"  - removed: {removed}")
            print(f"  - missing: {missing}")
            print(f"  - skipped_unsafe: {skipped_unsafe}")
            print(f"  - errors: {errors}")
            if errors:
                return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
