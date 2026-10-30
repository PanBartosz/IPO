# IPO App – Architecture (baseline)

This document describes the *current* technical architecture of the IPO application as it exists in this repository. It is intended as a stable reference for future agentic work and should be kept up to date as the code changes.

## 1) System overview

**Purpose**
- Support International Philosophy Olympiad logistics end-to-end: registrations, essay uploads/finalization, multi-stage assignment and scoring, communications, surveys, exports and auditing.

**Primary interfaces**
- **Admin panel**: operational control, planning, exports, communications, settings, audit.
- **Student portal**: login, PDF upload, finalization, (optionally) surveys/password reset.
- **Teacher portal**: login, download assignments, score/finalize, surveys, password reset.

**Tech stack**
- **Backend**: Flask (app factory), Jinja templates, WTForms.
- **Persistence**: SQLAlchemy ORM, Alembic migrations (`migrations/`).
- **Database**: MariaDB/MySQL (compose default) or SQLite (fallback).
- **Email**: optional SendGrid integration (when configured).
- **PDF generation**: server-side generation (Cairo/Pango dependencies in `Dockerfile`).
- **Rich text editor**: TinyMCE community build vendored in `ipo_app/static/vendor/tinymce`.

## 2) Runtime topology

**Development (docker-compose)**
- `web`: Flask app container, runs `flask db upgrade` on startup (via `entrypoint.sh`).
- `db`: MariaDB container with persistent volume `db_data`.
- `phpmyadmin`: optional database UI.

**Key configuration**
- Environment variables described in `README.md` (notably `DATABASE_URL`, `SECRET_KEY`, `ADMIN_USERS`, `UPLOAD_FOLDER`, `SENDGRID_*`, `TEACHER_BOARD_PASSWORD`).
- Runtime settings stored in DB table `app_settings` (model `AppSetting`) and editable in Admin UI.

## 3) Code organization

Repository (core):
- `ipo_app/__init__.py`: Flask app factory (`create_app`), blueprint registration, extensions init.
- `ipo_app/config.py`: config defaults + env lookups.
- `ipo_app/extensions.py`: SQLAlchemy and migrations wiring.
- `ipo_app/models.py`: SQLAlchemy models + enums (registrations, assignments, scoring, settings, comms, audit, surveys).
- `ipo_app/forms.py`: WTForms definitions (registrations, admin workflows, portal actions).
- `ipo_app/views.py`: main routes/blueprints, access control, workflow logic, exports, PDF/email helpers.
- `ipo_app/appearance.py`: edition identity and palette defaults, appearance forms, admin branding routes, image validation and public brand asset delivery. Configuration is stored as versioned JSON in `AppSetting`; absent settings reproduce the original Warsaw 2026 identity. Uploaded branding assets live in `UPLOAD_FOLDER/branding/`.
- `ipo_app/templates/`: Jinja templates (admin, student, teacher_portal, PDFs).
- `ipo_app/static/`: CSS/JS assets, vendored TinyMCE.
- `migrations/`: Alembic migrations.
- `scripts/`: seed/mock utilities (data, essays, stage scoring).

## 4) AuthN/AuthZ model

**Admin authentication**
- Admin users are configured via `ADMIN_USERS` env var as `username:password` pairs.
- Admin endpoints rely on an “admin session” (Flask session cookie).

**Student authentication**
- Students have portal credentials stored on the `Student` model:
  - `upload_username`, `upload_password_hash`, `upload_token`
- Student login is typically username+password; password reset flow uses time-limited tokens (`PasswordResetToken`).

**Teacher authentication**
- Teachers have portal credentials stored on the `Teacher` model:
  - `portal_username`, `portal_password_hash`, `portal_token`
- Teacher login records `portal_last_login`; password reset uses `PasswordResetToken`.

**Role boundaries**
- “Roles” are mostly implicit by which portal/blueprint is used (admin vs student vs teacher).
- Additional attributes drive behavior:
  - `Teacher.delegation_leader` (boolean)
  - `Student.is_absent` / `Teacher.is_absent` (exclude from operations unless explicitly included)
- Delegation leaders have access to a teacher-portal invite screen to manage delegation registrations and can download delegation essays after the event end time.
- Admins can manage and bootstrap invites (including delegation leaders) via **Admin → Invitation**.

## 5) Core domain model (high level)

**Registrations**
- `Student`: personal data, operational preferences (language, keyboard, meal, special needs), essay upload state.
- `Teacher`: personal data, languages, “delegation leader” flag, portal access.
- `DelegationInvite`: invitation tokens for student/teacher registrations (and delegation leader bootstrap) tied to a country, optional inviter (`invited_by_id`), `delegation_leader` flag, and invite lifecycle (opened/accepted/revoked).
- Registration records store GDPR notice acknowledgement and photo publication consent values with timestamps.

**Essay upload**
- Stored as filenames + timestamps in `Student`:
  - `uploaded_filename`, `uploaded_at`, `essay_finalized`, `essay_finalized_at`
- Storage location is configured via `UPLOAD_FOLDER` (defaults under `instance/`).
- Upload history is stored in `EssayUpload`, preserving past versions with word counts and (if applicable) finalization timestamps.

**Assignments & scoring**
- The scoring domain uses:
  - Stages (enum `Stage` in code; displayed as Stage 1/2/3 in admin UI)
  - Reading groups and membership (e.g. group member roles via `GroupMemberRole`)
  - Essay assignments and score records (e.g. `EssayScore` with `teacher_finalized`, `locked_by_admin`)
  - Candidate flags and locks (e.g. per-stage lock fields on assignments + global stage locks in settings)

**Communications**
- Teacher message board:
  - `TeacherMessage`, `TeacherMessageTemplate`
- Email campaigns:
  - `CommunicationCampaign` + recipient tracking models (status, failures, counts)

**Surveys**
- Survey authoring + publication + per-person assignments:
  - `Survey*` models and `SurveyAssignment` relations to student/teacher.

**Settings**
- `AppSetting` key/value store used for “feature flags” and operational toggles (deadlines, locks, email templates, etc.).
- Upload settings include a configurable essay word limit and mode (off/soft/hard); the system estimates word counts from uploaded PDFs.
- An event end timestamp controls student self-downloads, with an admin override to force student downloads open or closed.
- Delegation leader essay downloads use a separate manual setting and stay blocked until an administrator enables them.
- Registration settings include rich-text consent/statement content used on student/teacher registration forms.
- Registration access can be set to invite-only, with dedicated email templates for invitation links.
- GDPR notice and photo consent text blocks are editable in Admin Settings and shared across student/teacher registration.

**Audit**
- Activity/audit models exist for tracking operational actions (see `ipo_app/models.py` and admin screens in `ipo_app/views.py`).

## 6) Workflow state machines (conceptual)

### 6.1 Registration → credentials → portal access
1. User submits registration form (student or teacher).
2. Admin reviews/operates on lists; system can generate credentials/tokens.
3. User logs in and performs portal actions (upload, scoring, surveys).

### 6.2 Student essay upload lifecycle
- `not uploaded` → `uploaded` (PDF present) → `finalized` (locked for the student).
- Admin can globally lock uploads/finalization via settings, and can override/operate if needed.

### 6.3 Teacher scoring lifecycle (per assignment)
- `awaiting student finalization` → `available` → `draft score` → `teacher finalized`.
- A separate teacher assessment visibility setting can hide assigned essays, own grades, scoring pages, and essay downloads while keeping the broader teacher portal available.
- Admin can lock/unlock grading (global stage lock + per-assignment lock + per-score `locked_by_admin`).

### 6.4 Stage progression (admin-operated)
- Stage 1 planning/publishing produces assignments.
- Stage 1 scoring produces stats (average/spread) and flags (e.g. stage 2 candidate).
- Stage 2 assignments/scoring and further recommendation workflow support Stage 3 packet generation.

### 6.5 Invitations (delegation + normal)
- Delegation leaders issue student/teacher invites from the teacher portal; admins can create and manage invites across all countries via **Admin → Invitation**.
- Invite links route participants to registration forms with prefilled, locked delegation fields (email + country).
- Teacher invites can optionally be marked as “delegation leader” invites; accepting such an invite registers the teacher with `Teacher.delegation_leader = True`.
- Invites have a lifecycle: created → opened (link visited) → accepted (registration completed) or revoked.

## 7) Integration points and external dependencies

**Email**
- SendGrid optional; when disabled the app still generates credentials and relies on manual distribution.

**Database tools**
- Docker image includes `default-mysql-client` and supports DB dumps via `mysqldump` when running on MySQL/MariaDB.

**PDF generation**
- System packages installed in `Dockerfile` enable server-side rendering of PDFs (exports, packets, cards).

## 8) Known architecture constraints / risks

- The main route module (`ipo_app/views.py`) is large and concentrates multiple concerns (routing, business logic, PDF/email helpers). Refactors should preserve behavior and focus on low-risk extraction (helpers/services) over large rewrites.
- Automated tests exist under `tests/` (pytest). Changes to workflow logic should be validated by adding focused tests and/or performing targeted manual checks.
