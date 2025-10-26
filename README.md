# International Philosophy Olympiad Admin Portal

## Purpose
The IPO Admin Portal streamlines logistics for the International Philosophy Olympiad. It centralizes student and teacher registrations, essay workflow management, stage planning, message broadcasting, and PDF packet generation, keeping the competition compliant with IPO statutes.

## Features
- **Registrations**: Collect student and teacher data, log activity, and email confirmations (SendGrid optional).
- **Admin dashboard**: Metrics, alerts, and quick access to key modules.
- **Stage 1 planner**: Build reading groups, manage assignments, auto-generate/assign essays with duplex-aware packet exports.
-   *Duplex-aware* means the generated PDFs insert blank spacer pages so each teacher title page prints on its own sheet and every essay starts on a fresh front page — preventing backsides from leaking into the next packet.
- **Stage 2 scoring**: Monitor candidate essays, assign readers, produce stage-specific packets.
- **Scoring controls**: Track teacher draft/final states, flag admin-entered overrides, unlock finalized scores, and toggle per-stage or per-student grading locks.
- **Student uploads**: Secure login, PDF upload with server-backed preview, finalize submissions.
- **Teacher messaging**: Post announcements, email notifications, archive/restore with audit trails.
- **Teacher portal**: Optional per-teacher login to download assigned essays, record scores, and finalize results with audit logging.
- **Settings**: Configure deadlines, SLA, duplex mode, email templates, and automation.
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
Under **Admin → Settings**, admins can toggle the teacher portal, switch duplex printing, enable automatic emails, and edit message templates. Values are persisted in `app_settings` (Text columns).
Data exports (SQL + essay ZIP) are under **Admin → Exports** and require admin authentication. Database dumps currently support MariaDB/MySQL (via `mysqldump` installed in the Docker image) or SQLite (file copy).

## Teacher portal workflow
1. Enable **“Enable teacher portal (individual login & online grading)”** under **Admin → Settings** when you are ready to open the scoring portal.
2. Visit **Admin → Exports → Teacher portal cards** to generate PDF cards. Each export resets every teacher’s temporary password and lists the portal and board URLs.
3. Teachers sign in at `/teacher/login` with their unique username/password. Successful portal logins automatically unlock the personalized teacher board view.
4. From the portal dashboard, teachers can download assigned essays, save draft scores, and finalize submissions. Finalized scores lock editing for the teacher, but admins can reopen a score at any time via the **Unlock** action on the Stage 1/Stage 2 scoring pages.
5. Toggle the setting back off to close the portal—teachers will be redirected with a notice that the portal is offline. Lock settings you changed while the portal was disabled are still honored once it is re-enabled.

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
Dockerfile, docker-compose.yml, requirements.txt
share/                  # Reference IPO documents
```

## Running seed data
With Flask context configured:
```bash
python scripts/seed_mock_data.py --reset
```
Seeds realistic students/teachers; respect the default admin login (`admin:dev-password`) in compose.

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
