# International Philosophy Olympiad Admin Portal (working document)

## Purpose
The IPO Admin Portal streamlines logistics for the International Philosophy Olympiad. It centralizes student and teacher registrations, essay workflow management, stage planning, message broadcasting, and PDF packet generation, keeping the competition compliant with IPO statutes.

## Features
- **Registrations**: Collect student and teacher data, log activity, and email confirmations (SendGrid optional).
- **Admin dashboard**: Metrics, alerts, and quick access to key modules.
- **Stage 1 planner**: Build reading groups, manage assignments, auto-generate/assign essays with duplex-aware packet exports.
-   *Duplex-aware* means the generated PDFs insert blank spacer pages so each teacher title page prints on its own sheet and every essay starts on a fresh front page — preventing backsides from leaking into the next packet.
- **Stage 2 scoring**: Monitor candidate essays, assign readers, produce stage-specific packets.
- **Stage 3 packets**: Assemble ad-hoc steering committee packets for recommended essays with comment-ready overlays.
- **Grades export**: Produce anonymised Excel/PDF reports with per-stage scores, averages, and spreads; filter by country, stage, and recommendation status.
- **Scoring controls**: Track teacher draft/final states, flag admin-entered overrides, unlock finalized scores, and toggle per-stage or per-student grading locks.
- **Student uploads**: Secure login, PDF upload with server-backed preview, finalize submissions.
- **Teacher messaging**: Post announcements, email notifications, archive/restore with audit trails.
- **Communication campaigns**: Compose rich-text emails, filter by role/country, preview SendGrid delivery counts, and log every send for auditing.
- **Surveys**: Build questionnaires with multiple question types, publish to selected audiences, send notifications/reminders, and monitor completion.
- **Password resets**: Link-based self-service resets for students and teachers, plus admin-triggered resets with full audit logging.
- **Teacher portal**: Optional per-teacher login to download assigned essays, record scores, and finalize results with audit logging.
- **Settings**: Configure deadlines, SLA, duplex mode, survey/password email templates, and automation.
- **Audit logs**: Filtered activity trail with CSV export.
- **Seed tools**: Mock data seeding and PDF downloads for quick demos.
- **Exports**: Admin tools to download SQL dumps and essay ZIP archives for safe keeping.

## Configuration
### Environment variables
Set these in `.env`, Docker env, or your host:

| Variable | Description | Default |
| --- | --- | --- |
| `FLASK_APP` | Entry module | `ipo_app:create_app` |
| `FLASK_ENV`, `FLASK_DEBUG` | Flask mode | development/1 |
| `SECRET_KEY` | Session secret | `change-me` |
| `DATABASE_URL` | SQLAlchemy URI | sqlite file |
| `ADMIN_USERS` | `username:password` pairs | empty |
| `UPLOAD_FOLDER` | PDF storage path | `instance/uploads` |
| `MAX_UPLOAD_SIZE` | Upload limit in bytes | 10 MB |
| `TEACHER_BOARD_PASSWORD` | Teacher board login | empty |
| `DASHBOARD_*` | Optional default deadlines/SLA | n/a |
| `SENDGRID_API_KEY` | SendGrid token (optional) | empty |
| `SENDGRID_FROM_EMAIL` | Verified sender (optional) | empty |

### App settings (runtime)
Under **Admin → Settings**, admins can toggle the teacher portal, switch duplex printing, enable automatic emails, and edit the registration/message/survey/password email templates. Values are persisted in `app_settings` (Text columns).
The new **Admin → Communication** module reuses the same SendGrid credentials to deliver targeted broadcasts; drafts and previews are available even when SendGrid is not configured. The built-in rich text editor is the TinyMCE community build served locally from `static/vendor/tinymce`, so no API key is required.
Data exports (SQL + essay ZIP) are under **Admin → Exports** and require admin authentication. Database dumps currently support MariaDB/MySQL (via `mysqldump` installed in the Docker image) or SQLite (file copy).

## Teacher portal workflow
1. Enable **“Enable teacher portal (individual login & online grading)”** under **Admin → Settings** when you are ready to open the scoring portal.
2. Visit **Admin → Exports → Teacher portal cards** to generate PDF cards. Each export resets every teacher’s temporary password and lists the portal and board URLs.
3. Teachers sign in at `/teacher/login` with their unique username/password. Successful portal logins automatically unlock the personalized teacher board view.
4. From the portal dashboard, teachers can download assigned essays, respond to surveys, save draft scores, and finalize submissions. Finalized scores lock editing for the teacher, but admins can reopen a score at any time via the **Unlock** action on the Stage 1/Stage 2 scoring pages.
6. Stage lock toggles freeze both grading and essay downloads for the affected stage; unlock when jurors need access again.
5. Toggle the setting back off to close the portal—teachers will be redirected with a notice that the portal is offline. Lock settings you changed while the portal was disabled are still honored once it is re-enabled.

## Stage 3 steering committee workflow
1. Flag Stage 2 essays for Stage 3 consideration from the Stage 2 scoring screen.
2. Navigate to **Admin → Stage 2 → Stage 3 packets**.
3. Enter the steering committee member names (one per line), adjust the committee label if needed, and select the essays to include (all recommended essays are preselected).
4. Generate the PDF—each member receives a title sheet and full essay set with a “Comments” column instead of scores.
5. Re-run the generator any time the committee roster or essay list changes; the packets pull the latest essay uploads.

## Grades export
1. Open **Admin → Grades export** to configure filters for the grade report.
2. Choose the countries (or leave empty for all), select which stages to include, and optionally limit to Stage 3 recommendations.
3. Toggle anonymisation for students and teachers independently, decide whether to include timestamps, and choose between a detailed or compact layout. You can also split the Excel workbook into one worksheet per country.
4. Pick the output format (Excel or PDF) and download the generated report for delegates, steering committee members, or internal analysis.

## Password reset workflow
- Students and teachers can click **“Forgot password?”** on their respective login screens to request an expiring reset link (valid for 24 hours). Passwords are rotated only after the recipient opens the link and confirms the reset.
- Admins can trigger a reset directly from the **Students** or **Teachers** list/action menus. Each reset sends the same confirmation email (if automation is enabled) and records an activity log entry.
- Email templates for both the reset link and the final credentials delivery are configurable under **Admin → Settings**; customize them before enabling automation in production.
- If SendGrid is disabled, the app still generates new credentials—share the link/password manually using the success flash message shown to admins.

## Deployment
### Docker Compose (development)
Admin and MariaDB containers are defined in `docker-compose.yml`. Quick start:
```bash
docker compose up --build
# web: http://localhost:5000, db: localhost:3306, phpMyAdmin: http://localhost:8081
```
`entrypoint.sh` runs `flask db upgrade` automatically. Bind mounts enable live code edits.

### Manual (venv)
```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
export FLASK_APP=ipo_app:create_app
flask db upgrade
flask run
```
Provide a MySQL/MariaDB `DATABASE_URL` or keep the SQLite default.

### Production considerations
- Set strong `SECRET_KEY` and disable `FLASK_DEBUG`.
- Use Gunicorn/uwsgi with reverse proxy; enable TLS.
- Pin a managed MySQL/MariaDB instance; run `flask db upgrade` on deploys.
- Configure SendGrid credentials if you need automated emails; otherwise leave disabled.
- Mount persistent storage at `UPLOAD_FOLDER` for essay PDFs.
- Regularly export `app_settings` and database backups; they contain runtime configuration and audit logs.

## Project structure
```
ipo_app/
 ├── __init__.py        # Flask app factory
 ├── config.py          # Base config + env lookups
 ├── models.py          # SQLAlchemy models (students, teachers, messages, settings, logs…)
 ├── views.py           # Blueprints, routes, PDF generation, email helpers
 ├── forms.py           # WTForms definitions
 ├── templates/         # Jinja2 templates (admin, student, teacher, PDF)
 ├── static/            # CSS/JS assets
 └── extensions.py      # SQLAlchemy / Migrate bindings
migrations/             # Alembic migration history
scripts/seed_mock_data.py
scripts/seed_mock_essays.py
scripts/seed_stage1_scores.py
scripts/seed_stage2_scores.py
Dockerfile, docker-compose.yml, requirements.txt
share/                  # Reference IPO documents
```

## Running seed data
With Flask context configured:
```bash
python scripts/seed_mock_data.py --reset
```
Seeds realistic students/teachers; respect the default admin login (`admin:dev-password`) in compose.

Additional helpers speed up end-to-end grading tests:
- `python scripts/seed_mock_essays.py` uploads placeholder PDFs (or copies a provided template) for selected students, with options to finalize or overwrite existing files.
- `python scripts/seed_stage1_scores.py` generates Stage 1 scores for all assigned readers, with tunable Stage 2 promotion/extra-reader rates and optional rule checks that toggle Stage 2 flags.
- `python scripts/seed_stage2_scores.py` fills in Stage 2 reader scores for Stage 2 candidates (or any assignment with Stage 2 readers) using configurable score ranges.

## Testing
Current repo has no automated tests; `pytest` runs but collects none. Add tests under `tests/` and target `pytest` in CI.

## Contributing
1. Fork + clone
2. Create feature branch
3. Add/adjust migrations as needed (`flask db migrate`)
4. Update `requirements.txt` if dependencies change
5. Document new settings or env vars in this README
6. Submit PR with manual test notes

---
Questions or issues? Check the IPO statutes (`share/International Philosophy Olympiad Statute.html`) for competition rules or open an issue in your project tracker.
