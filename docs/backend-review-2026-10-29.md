# Backend review — 2026-10-29

The review covered authentication and session handling, uploads and submission history, settings access, database and spreadsheet exports, dependency security, and repository publication. It used isolated test databases; it did not modify production records.

## Fixed findings

| Finding | Result |
| --- | --- |
| Student upload names had only second-level timestamps. Two replacements in one second overwrote the same file and made both history entries point to the latest bytes. | Upload names now include a random suffix. A regression test freezes the clock and checks both original files and the current upload pointer. |
| Teachers marked absent could retain an authenticated portal session and its message board access. | Session lookup checks the current teacher record and clears both permissions when the teacher is absent or deleted. Student session lookup also clears stale identities. |
| Redirect validation accepted backslashes and embedded control characters. The grading/upload lock routes also accepted external return URLs without validation. | Authentication and lock actions use the same local URL validator, rejecting browser-normalized external targets. |
| Participant names, schools, grades, and survey answers beginning with `=` became executable formulas in Excel exports. CSV exports also accepted formula prefixes. | Excel strings are written as literal text across all workbook exports. CSV fields with spreadsheet command prefixes are escaped. ZIP member names are sanitized. |
| SQLite backups copied only the database file, missing committed data still in the WAL journal and misresolving relative SQLite URLs. | Backups use SQLite's online backup API against the configured engine. Output connections are closed explicitly and backup names include a random suffix. |
| Successful database and essay exports added audit records without committing them. | Both export routes commit their audit entries. |
| Configuration classes read environment variables before the app loaded `.env`, so direct Gunicorn/app-factory startup could miss configuration. | `.env` is loaded before configuration classes are imported. A subprocess test checks startup with a separate environment file. |
| Repeated setting reads issued identical database queries throughout a request. | Settings are loaded once per request and transaction. Writes invalidate the snapshot; commit and rollback boundaries refresh it. No settings are shared across requests or workers. |
| Dependency auditing reported vulnerable Flask, Gunicorn, python-dotenv, WeasyPrint, PyPDF2, and pytest releases. | Updated affected packages and migrated PDF reading/writing to maintained `pypdf`. A fresh audit of the resolved requirements reports no known vulnerabilities. |

## Performance evidence

With the same isolated app, admin session, and `/admin/settings` request, SQLAlchemy query instrumentation counted **56 settings SELECTs before the change and 1 after**. The regression suite checks that the page continues to use one settings query, and that writes, rollbacks, empty values, and later requests return the correct values.

## Validation

- Baseline: 259 tests passed.
- Updated suite: 281 tests passed on Python 3.11 (Docker/CI runtime) and Python 3.14 (local runtime).
- A clean Python 3.11 environment was installed directly from `requirements.txt`, including freshly resolved transitive dependencies.
- PDF tests cover generated packets, Unicode credentials, overlays, and the two-page public assessor-group export after the PDF library upgrades.
- Gunicorn configuration validation, dependency consistency, Python compilation, and `git diff --check` passed.
- `pip-audit -r requirements.txt`: no known vulnerabilities found after the updates.

## Publication checks

- Gitleaks scanned reachable Git history with redacted output and reported no secrets.
- Reachable history was checked for tracked environment files, participant spreadsheets, database dumps, and credential files. The environment example and development Compose credentials are examples, not production credentials.
- Documentation screenshots were checked with OCR; the visible registration examples use synthetic `example.com` addresses.
- Local participant spreadsheets, diploma archives, uploads, databases, environment files, virtual environments, and applicable scratch files are excluded from Git or Docker build contexts. Existing local work was preserved and excluded from the publication commit.
- Added the complete, unmodified CC BY-NC-SA 4.0 legal text, README attribution and scope, package metadata, and third-party notices. Restored the upstream MIT notice for bundled TinyMCE 6.8.3; existing htmx and DejaVu notices are retained.

## Limits and operational follow-up

These checks do not establish that every application path is free of bugs. MariaDB/MySQL exports were reviewed but were not exercised against a live database. The dependency audit covers Python packages, not the host or container OS. Flask-Limiter still defaults to process-local memory; multiworker deployments need a supported shared storage backend when rate limits must apply across workers. The large `views.py` module remains in place; no broad structural refactor or database schema change was required for these fixes.
