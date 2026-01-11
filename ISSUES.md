# ISSUES.md — Audit Findings

## 1) Executive summary

This repository appears to be a Flask-based web application for running International Philosophy Olympiad logistics: student/teacher registration, essay uploads, multi-stage planning/scoring, teacher messaging, surveys, and admin exports (SQL dumps, essay ZIPs, PDF packets).

Top risks:
- Docker image builds can accidentally include local secrets and sensitive data because `Dockerfile` uses `COPY . .` and the repo has no `.dockerignore` (high likelihood, high blast radius).
- Multiple admin state-changing POST actions are missing CSRF protection, enabling cross-site request forgery against logged-in admins (locks, exports, etc.).
- Session/security configuration has dangerous defaults (`SECRET_KEY` fallback, missing explicit cookie hardening), increasing the chance of session compromise/misuse in misconfigured deployments.
- Student portal credentials are stored/distributed in ways that materially increase credential exposure risk (stored plaintext token field; passwords included in default email templates).
- Teacher board authentication fails open when `TEACHER_BOARD_PASSWORD` is unset, making the board effectively public in the default compose/dev configuration.

Top 10 fixes:
- Add `.dockerignore` (and tighten Docker build context) so `.env`/`instance/*` never ship in images.
- Enforce a non-default `SECRET_KEY` in non-dev and set secure session cookie flags and lifetimes.
- Add global CSRF protection (`CSRFProtect`) and ensure every POST form includes a CSRF token (including HTMX forms).
- Fix teacher board login to fail closed when `TEACHER_BOARD_PASSWORD` is missing/empty.
- Redesign student credential handling to avoid storing plaintext passwords/tokens and stop emailing passwords.
- Upgrade `PyMySQL` to `1.1.1` (CVE fix) and add dependency scanning to CI.
- Add brute-force protections (rate limiting/lockout) on all login endpoints.
- Validate/normalize `next` redirects consistently to prevent open redirects.
- Sanitize export artifacts (ZIP arcnames + CSV/XLSX cells) to prevent Zip Slip and formula injection.
- Add export limits/streaming to prevent memory/disk exhaustion (ZIP + DB dumps).

Quick wins:
- `.dockerignore` + stop copying non-runtime files into images.
- Fix teacher board password fail-open bug.
- Use `_portal_next_url()` for `student_login` and admin login `next`.
- Upgrade `PyMySQL` and rerun `pip-audit`.

Status update (2026-01-11):
- Fixed: ISSUE-001, ISSUE-002, ISSUE-003, ISSUE-004, ISSUE-006, ISSUE-008, ISSUE-014.

Review limits:
- No production environment/TLS/reverse-proxy configuration was available for verification.
- The UI was reviewed statically (template/CSS/JS inspection); runtime accessibility behavior wasn’t validated in a browser or with screen readers.
- Database contents and operational procedures (backup retention/encryption, access controls) were inferred from code and local `instance/` artifacts; verify in your deployment.

## 2) Findings overview (table)

| ID | Title | Category | Severity | Priority | Confidence | Component | OWASP/ASVS/CWE/WCAG mapping |
| --- | --- | --- | --- | --- | --- | --- | --- |
| ISSUE-001 | Missing `.dockerignore` + broad `COPY . .` can bake secrets/PII into Docker images | Security | Critical | P0 | High | Docker/Packaging | OWASP A05:2021; ASVS V14; CWE-200 |
| ISSUE-002 | Insecure/default `SECRET_KEY` and missing explicit session cookie hardening | Security | Critical | P0 | High | Auth/Session | OWASP A05:2021, A07:2021; ASVS V3; CWE-321 |
| ISSUE-003 | Admin POST actions lack CSRF protection (HTMX/forms) | Security | High | P0 | High | Admin UI | OWASP A01:2021; ASVS V4.2; CWE-352 |
| ISSUE-004 | Teacher board login fails open when `TEACHER_BOARD_PASSWORD` is unset | Security | High | P0 | High | Teacher board | OWASP A01:2021; ASVS V2.1; CWE-287 |
| ISSUE-005 | Student credentials handled insecurely (plaintext token field + default “email password” templates) | Security | High | P0 | High | Student portal | OWASP A02:2021, A07:2021; ASVS V2; CWE-256, CWE-522 |
| ISSUE-006 | Vulnerable dependency: `PyMySQL==1.1.0` (CVE-2024-36039) | Security | Medium | P1 | High | Dependencies | OWASP A06:2021; ASVS V1.5; CVE-2024-36039 |
| ISSUE-007 | Risky `render_template_string` for admin-editable email templates (SSTI) | Security | High | P1 | Medium | Email templating | OWASP A03:2021; ASVS V5.3; CWE-1336 |
| ISSUE-008 | No brute-force defenses on login endpoints (rate limiting/lockout) | Security | Medium | P1 | High | AuthN | OWASP A07:2021; ASVS V2.2; CWE-307 |
| ISSUE-009 | Open redirect via unvalidated `next` in student/admin login | Security | Medium | P2 | High | Auth flows | CWE-601 |
| ISSUE-010 | Export artifacts susceptible to CSV/XLSX formula injection | Security | Medium | P2 | Medium | Exports | CWE-1236 |
| ISSUE-011 | Essay ZIP export susceptible to Zip Slip via unsanitized arcnames | Security | Medium | P2 | Medium | Exports | CWE-22 |
| ISSUE-012 | Essay ZIP + DB dump exports risk memory/disk exhaustion (no limits/streaming/retention) | Performance | Medium | P2 | Medium | Exports | CWE-400 |
| ISSUE-013 | Essay upload filename can collide within the same second (history corruption) | Bug | Medium | P3 | High | Uploads | — |
| ISSUE-014 | Quick-message modal lacks complete focus management/ARIA state updates | Accessibility | Medium | P3 | Medium | Admin UI | WCAG 2.2: 2.1.1, 2.4.3, 4.1.2; Nielsen: consistency |
| ISSUE-015 | Add dependency/security scanning automation in CI (pip-audit, Dependabot/Renovate) | Process | Medium | P2 | High | CI/CD | OWASP A06:2021 |
| ISSUE-016 | Harden GitHub Actions workflow (pin actions, least-privilege permissions, token hygiene) | Process | Medium | P2 | Medium | CI/CD | OWASP A05:2021 |
| ISSUE-017 | Add `SECURITY.md` and a vulnerability reporting process | Process | Low | P3 | High | Repo hygiene | ASVS V1.1 |
| ISSUE-018 | Add minimal automated tests for critical flows (auth, uploads, exports) | Process | Medium | P2 | High | Test strategy | ASVS V1.1 |

## 3) Issues (sorted by Priority then Severity)

### ISSUE-001 — Missing `.dockerignore` + broad `COPY . .` can bake secrets/PII into Docker images

Category: Security
Severity: Critical
Priority: P0
Confidence: High
Component/Area: Docker/Packaging
Mappings: OWASP A05:2021 Security Misconfiguration; ASVS V14 (Configuration); CWE-200 (Exposure of Sensitive Information)
Status: Fixed (2026-01-11)

Implemented:
- Added `.dockerignore` to exclude `.env`, `instance/`, `.git/`, and common dev artifacts from the Docker build context.

Impact:

If a developer/operator builds the Docker image from a working tree containing `.env` and `instance/` data (uploads/backups), those files can be copied into the resulting image layer. This risks leaking secrets (session keys, DB credentials, SendGrid tokens) and PII (student essays, SQL dumps) via image registries, backups, or accidental sharing.

Evidence:

File(s): `Dockerfile:23-33`

Snippet:
```dockerfile
COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

COPY . .
```

File(s): `.gitignore:1-4`

Snippet:
```gitignore
.env
!.env.example
/instance/backups/
/instance/uploads/
```

Explanation: `.gitignore` does not affect Docker build context; without `.dockerignore`, `COPY . .` copies *everything* in the build context into the image.

Steps to reproduce (or reasoning path):

1. Ensure the working tree contains `.env` and/or `instance/uploads/*` and/or `instance/backups/*` (as in this workspace).
2. Build the image with `docker build .`.
3. Inspect the image filesystem (e.g., `docker run --rm <img> ls -la /app`) and observe sensitive files present.

Recommended fix (concrete):

1. Add a repo-root `.dockerignore` that excludes secrets, local instance data, and other non-runtime artifacts.
2. Consider tightening the Dockerfile to copy only the application code and required assets (and run as non-root; use a production WSGI server for production images).

Suggested patch/diff snippet:
```diff
*** Add File: .dockerignore
.env
.env.*
instance/
__pycache__/
*.pyc
*.pyo
*.log
.pytest_cache/
.vscode/
.idea/
```

Acceptance criteria:

- Building the Docker image from a typical dev working tree does not include `.env` or `instance/` contents.
- Image contents include only runtime-required files.

Test plan:

- Build: `docker build -t ipo:local .`
- Verify absence: `docker run --rm ipo:local sh -lc 'test ! -f /app/.env && test ! -d /app/instance/uploads && test ! -d /app/instance/backups'`
- Regression: confirm the container still starts and serves the app.

Fix effort: S
Dependencies/Notes:

- If you *need* runtime `instance/` directories, mount them as volumes in production rather than baking them into images.

### ISSUE-002 — Insecure/default `SECRET_KEY` and missing explicit session cookie hardening

Category: Security
Severity: Critical
Priority: P0
Confidence: High
Component/Area: Auth/Session
Mappings: OWASP A05:2021 Security Misconfiguration; OWASP A07:2021 Identification and Authentication Failures; ASVS V3 (Session Management); CWE-321 (Use of Hard-coded Cryptographic Key)
Status: Fixed (2026-01-11)

Implemented:
- Added fail-fast startup check for insecure `SECRET_KEY` outside development.
- Set explicit `SESSION_COOKIE_*` flags and `PERMANENT_SESSION_LIFETIME_HOURS` default (72h), with `SESSION_COOKIE_SECURE` defaulting to `True` outside development.

Impact:

If deployed with the default `SECRET_KEY` fallback, an attacker can forge/modify Flask session cookies, potentially impersonating users (admin/student/teacher) and performing sensitive actions (exports, downloads, settings changes). Missing explicit cookie security flags and session lifetimes increases the risk of session theft/replay and accidental long-lived admin sessions.

Evidence:

File(s): `ipo_app/config.py:5-18`

Snippet:
```python
class Config:
    SECRET_KEY = os.getenv("SECRET_KEY", "change-me")
    ...
    WTF_CSRF_ENABLED = True
```

Explanation: `SECRET_KEY` defaults to a known value if the environment variable is not set. Additionally, the repo does not explicitly configure `SESSION_COOKIE_SECURE`, `SESSION_COOKIE_SAMESITE`, or `PERMANENT_SESSION_LIFETIME` (defaults vary by framework/version and deployment).

Steps to reproduce (or reasoning path):

1. Deploy the app without setting `SECRET_KEY`.
2. Observe sessions are signed with a predictable key (`"change-me"`), enabling cookie forgery.

Recommended fix (concrete):

1. Fail fast when `SECRET_KEY` is unset/default in non-development environments.
2. Set explicit session cookie hardening in config (at minimum: `Secure`, `HttpOnly`, `SameSite`), and define a reasonable `PERMANENT_SESSION_LIFETIME` for admin sessions.
3. Document required production settings in `README.md` and `.env.example` (without real secrets).

Acceptance criteria:

- App refuses to start (or logs a fatal error) when `SECRET_KEY` is `"change-me"` outside development/test.
- Session cookies are issued with explicit security attributes appropriate for HTTPS deployments.
- Admin sessions expire as expected (documented and tested).

Test plan:

- Unit test: create app with `SECRET_KEY=change-me` and `FLASK_ENV=production` (or equivalent) and assert startup fails.
- Integration test: login as admin and inspect `Set-Cookie` attributes for session cookie.

Fix effort: M
Dependencies/Notes:

- Cookie `Secure` requires HTTPS at the edge; keep a dev override for local HTTP.

### ISSUE-003 — Admin POST actions lack CSRF protection (HTMX/forms)

Category: Security
Severity: High
Priority: P0
Confidence: High
Component/Area: Admin UI
Mappings: OWASP A01:2021 Broken Access Control; ASVS V4.2 (CSRF); CWE-352 (Cross-Site Request Forgery)
Status: Fixed (2026-01-11)

Implemented:
- Enabled global CSRF protection via `flask_wtf.CSRFProtect`.
- Added CSRF tokens to all POST forms, including HTMX-driven admin actions.

Impact:

A logged-in admin can be tricked into performing state-changing actions via a malicious site (e.g., locking uploads/grading, generating exports, triggering backups), potentially disrupting event operations and creating unwanted sensitive artifacts on disk.

Evidence:

File(s): `ipo_app/templates/admin/partials/dashboard_content.html:64-102`

Snippet:
```html
<form method="post" action="{{ url_for('web.admin_toggle_upload_lock') }}" hx-post="{{ url_for('web.admin_toggle_upload_lock') }}" hx-target="#dashboard-content">
  <input type="hidden" name="state" value="{{ 'unlock' if upload_state.locked else 'lock' }}">
  <button type="submit" class="button secondary">...</button>
</form>
```

File(s): `ipo_app/views.py:3949-4021`

Snippet:
```python
@web_bp.route("/admin/grading/lock", methods=["POST"])
def admin_toggle_grading_lock():
    if not _current_admin():
        abort(403)
    stage_value = request.form.get("stage")
    target_state = request.form.get("state")
    ...
```

File(s): `ipo_app/templates/admin/exports.html:16-43`

Snippet:
```html
<form method="post" action="{{ url_for('web.admin_export_database') }}">
  <button type="submit" class="button">Download database SQL</button>
</form>
```

Explanation: These POST forms do not include CSRF tokens (`{{ form.hidden_tag() }}` or `{{ csrf_token() }}`), and the handlers do not validate CSRF for non-`FlaskForm` endpoints. The app also does not currently initialize a global `CSRFProtect` middleware.

Steps to reproduce (or reasoning path):

1. Log in as an admin in one browser tab.
2. Visit an attacker-controlled page that auto-submits a cross-site POST to one of the admin endpoints.
3. Observe the server accepts the request and performs the action.

Recommended fix (concrete):

1. Add `flask_wtf.CSRFProtect` globally (app-level) so all non-GET requests are checked by default.
2. Ensure every POST form includes a CSRF token, including “simple” forms not backed by a `FlaskForm`:
   - Add `<input type="hidden" name="csrf_token" value="{{ csrf_token() }}">` for those.
3. For HTMX, either rely on hidden inputs (preferred) or set an `HX-Header` with the CSRF token and validate it server-side.

Acceptance criteria:

- Cross-site POSTs without a valid CSRF token are rejected (400/403).
- All admin POST forms include CSRF tokens.
- Legitimate same-site POSTs continue to work (including HTMX partial updates).

Test plan:

- Integration tests using Flask test client:
  - Authenticate as admin.
  - POST to each admin endpoint without CSRF token → expect rejection.
  - POST with CSRF token → expect success.
- Manual: verify admin dashboard lock toggles and exports still work in browser.

Fix effort: M
Dependencies/Notes:

- Inventory all `methods=["POST"]` routes in `ipo_app/views.py` and ensure each is either CSRF-protected or explicitly exempted with justification.

### ISSUE-004 — Teacher board login fails open when `TEACHER_BOARD_PASSWORD` is unset

Category: Security
Severity: High
Priority: P0
Confidence: High
Component/Area: Teacher board
Mappings: OWASP A01:2021 Broken Access Control; ASVS V2.1 (Authentication); CWE-287 (Improper Authentication)
Status: Fixed (2026-01-11)

Implemented:
- Teacher board login now fails closed when `TEACHER_BOARD_PASSWORD` is unset/empty (no session granted; returns 503 on submit).
- Added a dev `TEACHER_BOARD_PASSWORD` to `docker-compose.yml` and `.env.example` for local testing.

Impact:

If `TEACHER_BOARD_PASSWORD` is missing or empty (which is the current default in `Config`), any user can obtain a teacher-board session by submitting *any* password. This exposes internal messages and increases the likelihood of social engineering and information leakage.

Evidence:

File(s): `ipo_app/views.py:6552-6591`

Snippet:
```python
password_config = current_app.config.get("TEACHER_BOARD_PASSWORD")
...
supplied = form.password.data.strip()
expected = password_config or ""
if expected and not secrets.compare_digest(supplied, expected):
    flash("Invalid password.", "error")
    ...
else:
    session["teacher_board"] = True
    flash("Access granted.", "success")
    ...
```

Explanation: When `expected` is empty (`""`), the failure branch is skipped and access is granted.

Steps to reproduce (or reasoning path):

1. Run without `TEACHER_BOARD_PASSWORD` set.
2. Submit the teacher board login form with any password.
3. Observe “Access granted.” and an authorized session.

Recommended fix (concrete):

1. Fail closed when `TEACHER_BOARD_PASSWORD` is missing/empty: do not allow logins and present a clear “disabled/misconfigured” error.
2. Consider eliminating the shared password entirely when the teacher portal is enabled, and require per-teacher authentication for board access.

Suggested patch/diff snippet:
```diff
if not password_config:
    flash(\"Teacher board is disabled until TEACHER_BOARD_PASSWORD is configured.\", \"error\")
    return render_template(\"teacher_board/login.html\", form=form), 503
```

Acceptance criteria:

- If `TEACHER_BOARD_PASSWORD` is unset/empty, login attempts are rejected and no session flag is set.
- If set, only the correct password grants access.

Test plan:

- Unit test: `TEACHER_BOARD_PASSWORD=None` → POST login → expect 503/denied.
- Unit test: wrong password → denied; correct password → session contains `teacher_board`.

Fix effort: S
Dependencies/Notes:

- Also set `TEACHER_BOARD_PASSWORD` in `docker-compose.yml` (as a dev-only value) *only if* the teacher board is intended to be protected in dev.

### ISSUE-005 — Student credentials handled insecurely (plaintext token field + default “email password” templates)

Category: Security
Severity: High
Priority: P0
Confidence: High
Component/Area: Student portal
Mappings: OWASP A02:2021 Cryptographic Failures; OWASP A07:2021 Identification and Authentication Failures; ASVS V2 (Authentication); CWE-256 (Plaintext Storage of a Password); CWE-522 (Insufficiently Protected Credentials)

Impact:

Storing student portal passwords/tokens in plaintext increases blast radius if the database is leaked, backups are mishandled, or admin exports are compromised. Default email templates include passwords, which further increases credential exposure risk (mailbox compromise, forwarding, retention).

Evidence:

File(s): `ipo_app/models.py:12-45`

Snippet:
```python
class Student(db.Model, TimestampMixin):
    ...
    upload_username = db.Column(db.String(64), nullable=True, unique=True)
    upload_password_hash = db.Column(db.String(255), nullable=True)
    upload_token = db.Column(db.String(64), nullable=True, unique=True)
```

File(s): `ipo_app/views.py:1756-1767`

Snippet:
```python
plain_password = secrets.token_urlsafe(8)
student.upload_password_hash = generate_password_hash(plain_password)
student.upload_token = plain_password
```

File(s): `ipo_app/templates/admin/pdf/student_cards.html:72-75`

Snippet:
```html
<p><strong>Username:</strong> {{ student.upload_username }}</p>
<p><strong>Password:</strong> {{ student.upload_token }}</p>
```

File(s): `ipo_app/views.py:190-206`

Snippet:
```python
<li><strong>Username:</strong> {{ portal_username }}</li>
<li><strong>Password:</strong> {{ portal_password }}</li>
```

Explanation: The system keeps a retrievable plaintext credential (`upload_token`) and also encourages distribution via email templates.

Steps to reproduce (or reasoning path):

1. Create/register a student (or reset password).
2. Observe `Student.upload_token` is populated with the plaintext credential.
3. Generate student cards PDF or send the default registration email; the password is disclosed.

Recommended fix (concrete):

1. Replace `upload_token` plaintext storage with one of:
   - One-time login/reset links (token stored hashed in DB; exchange token for password set).
   - One-time printed codes generated at PDF-generation time and stored only hashed (reprint requires regeneration).
   - If “reprint must show the same password” is required, store an *encrypted* value (envelope encryption) and rotate the encryption key per event.
2. Update default email templates to send reset links rather than passwords.
3. Consider forcing a password change on first login (or using time-limited credentials for event day only).

Acceptance criteria:

- No plaintext student portal passwords are stored in the database.
- Emails and PDFs do not require persistent plaintext credentials; credentials are either one-time or encrypted-at-rest.
- Password reset flow remains usable and audited.

Test plan:

- Unit tests:
  - Credential generation stores only hashes (and optionally encrypted blobs), never plaintext.
  - Token exchange is single-use and time-limited.
- Integration tests:
  - Student can log in, upload, and reset password using the new flow.
  - Old credentials are invalidated after reset/exchange.

Fix effort: L
Dependencies/Notes:

- This change likely requires a DB migration (alter/remove `students.upload_token`) and updated operational runbooks for “printing cards.”

### ISSUE-006 — Vulnerable dependency: `PyMySQL==1.1.0` (CVE-2024-36039)

Category: Security
Severity: Medium
Priority: P1 (now)
Confidence: High
Component/Area: Dependencies
Mappings: OWASP A06:2021 Vulnerable and Outdated Components; ASVS V1.5; CVE-2024-36039
Status: Fixed (2026-01-11)

Implemented:
- Upgraded `PyMySQL` to `1.1.1`.

Impact:

Known vulnerabilities in database drivers can enable denial of service, information leaks, or other security impacts depending on usage patterns. This repo is pinned to a version flagged by `pip-audit`.

Evidence:

File(s): `requirements.txt:1-13`

Snippet:
```text
PyMySQL==1.1.0
```

Explanation: `pip-audit -r requirements.txt` reported `CVE-2024-36039` with fixed version `1.1.1`.

Steps to reproduce (or reasoning path):

1. Run `pip-audit -r requirements.txt`.
2. Observe the reported CVE for `pymysql 1.1.0`.

Recommended fix (concrete):

1. Bump `PyMySQL` to `1.1.1`.
2. Re-run `pip-audit` and a smoke test (at least app startup + DB connection).

Acceptance criteria:

- `requirements.txt` uses `PyMySQL==1.1.1` (or later non-vulnerable).
- `pip-audit` reports no known vulnerabilities for `pymysql`.

Test plan:

- `pip-audit -r requirements.txt`
- Start the app against MariaDB/MySQL and run a basic query/migration.

Fix effort: S
Dependencies/Notes:

- Consider adding a lockfile or hashes to reduce supply-chain risk.

### ISSUE-007 — Risky `render_template_string` for admin-editable email templates (SSTI)

Category: Security
Severity: High
Priority: P1 (now)
Confidence: Medium
Component/Area: Email templating
Mappings: OWASP A03:2021 Injection; ASVS V5.3 (Input Validation); CWE-1336 (Improper Neutralization of Special Elements in a Template Engine)

Impact:

Jinja templating is powerful enough to become code execution if an attacker can influence template strings. Because subjects/bodies are stored as editable settings, a compromised admin account (or any bug that enables settings tampering) can escalate to server-side template injection and potentially remote code execution or data exfiltration.

Evidence:

File(s): `ipo_app/views.py:2117-2124`

Snippet:
```python
subject_template = _get_email_subject(subject_key)
body_template = _get_email_body(body_key)
subject = render_template_string(subject_template, **context)
body = render_template_string(body_template, **context)
```

Explanation: `render_template_string` evaluates Jinja expressions and statements. Stored templates are not sandboxed or restricted to safe substitution.

Steps to reproduce (or reasoning path):

1. As an admin, set an email template value to a malicious Jinja payload (verification recommended in a non-production environment).
2. Trigger a send using that template.
3. Observe unexpected evaluation or errors indicating server-side execution.

Recommended fix (concrete):

1. Replace Jinja evaluation for user-editable templates with a safe, non-executable templating mechanism (e.g., `string.Template`, Mustache) that only substitutes whitelisted variables.
2. If Jinja must remain: use a sandboxed environment with strict undefined variables and block access to globals/filters; enforce a denylist for `{% %}` blocks and attribute traversal (still riskier than non-executable templating).
3. Add tests with known SSTI payloads to prevent regressions.

Acceptance criteria:

- Malicious Jinja payloads in stored templates do not execute and are rejected or rendered inert.
- Only documented variables can be substituted; unknown variables fail safely.

Test plan:

- Unit tests for template rendering:
  - benign template renders correctly
  - payloads like `{{ cycler.__init__.__globals__ }}` are rejected/return error without execution

Fix effort: M
Dependencies/Notes:

- This is tightly coupled with the CSRF and admin security posture: reduce the chance of settings tampering first (ISSUE-003).

### ISSUE-008 — No brute-force defenses on login endpoints (rate limiting/lockout)

Category: Security
Severity: Medium
Priority: P1 (now)
Confidence: High
Component/Area: AuthN
Mappings: OWASP A07:2021 Identification and Authentication Failures; ASVS V2.2; CWE-307 (Improper Restriction of Excessive Authentication Attempts)
Status: Fixed (2026-01-11)

Implemented:
- Added `Flask-Limiter` and rate limiting on login endpoints (10/min per username + 120/min per IP; teacher board login 10/min per IP).

Impact:

Public login endpoints (admin, student portal, teacher portal, teacher board) are susceptible to credential stuffing and brute force attempts. This increases the likelihood of account compromise (especially for shared-password endpoints like the teacher board).

Evidence:

File(s): `ipo_app/views.py:3056-3081`

Snippet:
```python
if form.validate_on_submit() and credentials:
    username = form.username.data.strip()
    if _validate_admin_credentials(username, form.password.data):
        session["admin_user"] = username
        ...
```

File(s): `ipo_app/views.py:6697-6738`

Snippet:
```python
if form.validate_on_submit():
    ...
    elif not check_password_hash(teacher.portal_password_hash, password):
        flash("Invalid credentials.", "error")
        ...
```

Explanation: There is logging of failed attempts, but no throttling, lockout, CAPTCHA, or per-IP rate limiting.

Steps to reproduce (or reasoning path):

1. Perform repeated POSTs to `/admin/login`, `/participant/login`, `/teacher/login`, or `/board/login`.
2. Observe there is no server-side rate limiting or increasing delay.

Recommended fix (concrete):

1. Add rate limiting (e.g., `flask-limiter`) per IP and per account identifier.
2. Add progressive delays and temporary lockouts after N failures.
3. Ensure logs/alerts are generated for suspicious patterns (burst failures, distributed attempts).

Acceptance criteria:

- Excessive failed logins are throttled (HTTP 429 or delayed responses).
- Lockouts are time-limited and auditable.
- Legitimate users can still log in reliably.

Test plan:

- Integration test: simulate N failed logins from the same IP and assert throttling triggers.
- Integration test: verify lockout resets after timeout.

Fix effort: M
Dependencies/Notes:

- Coordinate with operational requirements for event day (avoid blocking legitimate shared NAT users; consider per-account throttles).

### ISSUE-009 — Open redirect via unvalidated `next` in student/admin login

Category: Security
Severity: Medium
Priority: P2
Confidence: High
Component/Area: Auth flows
Mappings: CWE-601 (Open Redirect)

Impact:

Attackers can craft login links with a malicious `next` parameter so that, after successful login, users are redirected to an attacker-controlled site. This is commonly used for phishing and token/session confusion.

Evidence:

File(s): `ipo_app/views.py:3121-3123`

Snippet:
```python
next_param = request.args.get("next")
target = next_param if next_param else url_for("web.student_portal")
return redirect(target)
```

File(s): `ipo_app/views.py:3058-3060`

Snippet:
```python
if _current_admin():
    return redirect(request.args.get("next") or url_for("web.admin_dashboard"))
```

Explanation: `next` is not constrained to relative/internal paths for these flows. A safe helper (`_portal_next_url`) exists and is used for the teacher portal login, but not here.

Steps to reproduce (or reasoning path):

1. Visit `/participant/login?next=https://example.com` and log in successfully.
2. Observe redirection to the external URL.

Recommended fix (concrete):

1. Reuse `_portal_next_url()` (or a shared “safe redirect” helper) for student/admin flows.
2. Default to a fixed internal route if `next` is invalid.

Acceptance criteria:

- External `next` values are ignored and do not cause redirects off-site.
- Internal relative paths (e.g., `/participant/portal`) still work.

Test plan:

- Unit test: `next=https://evil.tld` → redirect goes to default internal page.
- Unit test: `next=/admin/uploads` → redirect stays internal.

Fix effort: S
Dependencies/Notes:

- Also validate any `redirect` parameters used in admin POST handlers (if kept) to prevent open redirects.

### ISSUE-010 — Export artifacts susceptible to CSV/XLSX formula injection

Category: Security
Severity: Medium
Priority: P2
Confidence: Medium
Component/Area: Exports
Mappings: CWE-1236 (Improper Neutralization of Formula Elements in a CSV File)

Impact:

If an attacker-controlled field (e.g., first/last name, school) begins with `=`, `+`, `-`, or `@`, exported CSV/XLSX files may be interpreted as formulas when opened in spreadsheet software. This can enable data exfiltration or code execution via spreadsheet features (depending on client configuration).

Evidence:

File(s): `ipo_app/views.py:6522-6549`

Snippet:
```python
writer.writerow(["timestamp", "actor", "action", "object_type", "object_id", "description", "details"])
for entry in logs:
    writer.writerow([entry.actor, entry.action, entry.description or "", ...])
```

File(s): `ipo_app/views.py:11087-11108`

Snippet:
```python
students = Student.query.order_by(Student.id.asc()).all()
workbook = _students_workbook(students)
return send_file(workbook, as_attachment=True, download_name="ipo-students.xlsx", ...)
```

Explanation: Values are written directly without neutralizing spreadsheet formula prefixes.

Steps to reproduce (or reasoning path):

1. Register a user with a field like `first_name="=HYPERLINK(\"https://evil\")"`.
2. Export students/teachers or logs.
3. Open the file in Excel/LibreOffice and observe formula evaluation (environment-dependent).

Recommended fix (concrete):

1. For CSV: prefix any cell starting with `[=+\\-@]` with a single quote `'` (or a tab) before writing.
2. For XLSX: write such values as explicit strings and/or prefix with `'` to prevent evaluation.
3. Add unit tests for the sanitizer.

Acceptance criteria:

- Exported CSV/XLSX files treat dangerous-leading characters as plain text.
- No existing exports break for normal values.

Test plan:

- Unit test: sanitize `=1+1` and ensure output begins with `'`.
- Manual: generate export and confirm Excel shows literal text.

Fix effort: M
Dependencies/Notes:

- Apply the same sanitization to `manifest.csv` inside the essay ZIP export.

### ISSUE-011 — Essay ZIP export susceptible to Zip Slip via unsanitized arcnames

Category: Security
Severity: Medium
Priority: P2
Confidence: Medium
Component/Area: Exports
Mappings: CWE-22 (Path Traversal)

Impact:

The generated essay ZIP may contain entries with `../` sequences if a student name includes path separators. When the ZIP is extracted, a vulnerable unzip tool may write outside the intended directory (impacting the operator’s machine or downstream systems that automatically extract archives).

Evidence:

File(s): `ipo_app/views.py:2993-3006`

Snippet:
```python
safe_name = f"{student.id}-{student.last_name}_{student.first_name}.pdf"
...
archive.write(pdf_path, f"essays/{safe_name}")
```

Explanation: `safe_name` is derived from user-controlled fields without sanitization and is used as a ZIP arcname.

Steps to reproduce (or reasoning path):

1. Create a student with `last_name="../evil"`.
2. Generate essay ZIP export.
3. Inspect ZIP entries; observe path traversal sequences.

Recommended fix (concrete):

1. Sanitize `safe_name` using `secure_filename` or a custom “zip-safe” sanitizer that removes separators and `..`.
2. Add unit tests that assert arcnames never contain `/`, `\\`, or `..` beyond the intended prefix.

Acceptance criteria:

- ZIP entry names are safe regardless of user-provided names.
- Extraction never writes outside `essays/` when using standard unzip tools.

Test plan:

- Unit test: create a fake student name with `../` and ensure archive path is normalized/safe.
- Manual: generate ZIP and inspect `zipinfo -1`.

Fix effort: S
Dependencies/Notes:

- This is primarily a “consumer-side” risk, but it’s still good hygiene for any exported archives.

### ISSUE-012 — Essay ZIP + DB dump exports risk memory/disk exhaustion (no limits/streaming/retention)

Category: Performance
Severity: Medium
Priority: P2
Confidence: Medium
Component/Area: Exports
Mappings: CWE-400 (Uncontrolled Resource Consumption)

Impact:

Export endpoints can generate large in-memory ZIPs and on-disk DB dumps. Without explicit limits and retention/cleanup, this can exhaust memory or disk, causing downtime during critical event operations.

Evidence:

File(s): `ipo_app/views.py:2947-2969`

Snippet:
```python
backups_dir = Path(... / "backups")
backups_dir.mkdir(parents=True, exist_ok=True)
...
if "mysql" in database_url:
    if _run_mysqldump(output_path):
        return output_path, filename
```

File(s): `ipo_app/views.py:2972-3017`

Snippet:
```python
zip_buffer = BytesIO()
...
with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as archive:
    ...
return zip_buffer, filename
```

Explanation: ZIP creation happens in memory (`BytesIO`). DB dumps are stored on disk under `instance/backups` with no retention policy.

Steps to reproduce (or reasoning path):

1. Accumulate many PDFs in the upload folder.
2. Trigger essay export; observe increased memory usage.
3. Trigger repeated DB exports; observe disk growth under backups.

Recommended fix (concrete):

1. Stream ZIP exports (or write to a temporary file) instead of building in memory.
2. Add explicit export limits (max essays, max total size) and warn admins when exceeded.
3. Implement backup retention (e.g., keep last N dumps or delete after download) and document secure storage expectations.

Acceptance criteria:

- Exports have predictable resource usage and do not OOM on larger datasets.
- Backups directory does not grow without bound; retention is enforced.

Test plan:

- Load test in staging with representative dataset sizes; measure memory/disk during exports.
- Regression: verify exported ZIP/SQL contents are complete for normal dataset sizes.

Fix effort: M
Dependencies/Notes:

- If you need “export must be instantaneous,” consider a background job queue and pre-generated artifacts.

### ISSUE-013 — Essay upload filename can collide within the same second (history corruption)

Category: Bug
Severity: Medium
Priority: P3
Confidence: High
Component/Area: Uploads
Mappings: —

Impact:

If a student uploads multiple times within the same second, the generated `stored_name` can collide and overwrite an existing PDF. This breaks upload history integrity (`EssayUpload`) and can lead to missing/incorrect files.

Evidence:

File(s): `ipo_app/views.py:3403-3407`

Snippet:
```python
timestamp = datetime.utcnow().strftime("%Y%m%d%H%M%S")
stored_name = f"student-{student.id}-{timestamp}.pdf"
file_path = upload_folder / stored_name
file.save(file_path)
```

Steps to reproduce (or reasoning path):

1. Upload two PDFs in quick succession (within one second).
2. Observe the second upload may overwrite the first.

Recommended fix (concrete):

1. Include higher-resolution time (microseconds) and/or a random suffix (e.g., `secrets.token_hex(4)` or UUID).
2. Optionally use an atomic “create new file” strategy and retry on collision.

Acceptance criteria:

- Two uploads within the same second always produce distinct filenames and preserve history.

Test plan:

- Unit test: generate multiple names in a tight loop and assert uniqueness.
- Integration test: simulate back-to-back uploads and ensure both files exist and are referenced correctly.

Fix effort: S
Dependencies/Notes:

- Keep filename format stable if external tooling depends on it; add suffix at the end to minimize disruption.

### ISSUE-014 — Quick-message modal lacks complete focus management/ARIA state updates

Category: Accessibility
Severity: Medium
Priority: P3
Confidence: Medium
Component/Area: Admin UI
Mappings: WCAG 2.2: 2.1.1 (Keyboard), 2.4.3 (Focus Order), 4.1.2 (Name, Role, Value); Nielsen: Consistency and standards
Status: Fixed (2026-01-11)

Implemented:
- Modal now toggles `aria-hidden`, traps focus while open, and restores focus to the triggering control on close.

Impact:

Keyboard-only and screen-reader users may have difficulty interacting with the modal: focus can move behind the dialog, `aria-hidden` does not reflect visibility, and focus is not restored to the triggering control on close. This risks non-compliance with WCAG 2.2 AA expectations for modal dialogs and increases admin workflow friction.

Evidence:

File(s): `ipo_app/templates/admin/partials/quick_message_modal.html:8-13`

Snippet:
```html
<div id="{{ modal_id }}" class="message-modal" aria-hidden="true">
  <div class="message-modal__dialog" role="dialog" aria-modal="true" aria-labelledby="{{ modal_id }}-title">
```

File(s): `ipo_app/templates/admin/partials/quick_message_modal.html:107-126`

Snippet:
```javascript
function openModal(teacherId, teacherName) {
  ...
  modal.classList.add("is-visible");
  document.body.classList.add("modal-open");
  if (titleInput) {
    titleInput.focus();
  }
}
function closeModal() {
  modal.classList.remove("is-visible");
  document.body.classList.remove("modal-open");
  resetForm();
}
```

Explanation: `aria-hidden` is not toggled, there is no focus trap, and the previously focused element isn’t restored.

Steps to reproduce (or reasoning path):

1. Open the modal using keyboard navigation.
2. Press `Tab` repeatedly.
3. Observe focus can move outside the dialog; closing does not return focus to the launch button.

Recommended fix (concrete):

1. Toggle `aria-hidden` to `false` when open and `true` when closed.
2. Implement a focus trap (cycle focus between first/last focusable elements in the dialog).
3. Store the opener element and restore focus on close.

Acceptance criteria:

- When the modal is open, focus stays within it and `aria-hidden` reflects visibility.
- Closing the modal restores focus to the triggering control.

Test plan:

- Manual keyboard test (Tab/Shift+Tab/Escape).
- Run an automated accessibility check (e.g., axe) on the admin dashboard page with modal open.

Fix effort: M
Dependencies/Notes:

- Consider using a small, well-tested dialog utility instead of bespoke focus-trap logic.

## 4) Hardening backlog (non-bug improvements)

### ISSUE-015 — Add dependency/security scanning automation in CI (pip-audit, Dependabot/Renovate)

Category: Process
Severity: Medium
Priority: P2
Confidence: High
Component/Area: CI/CD
Mappings: OWASP A06:2021 Vulnerable and Outdated Components

Impact:

Vulnerable dependencies (e.g., `PyMySQL`) can remain undetected until late. Automated scanning reduces mean time to remediation and prevents regressions.

Evidence:

File(s): `.github/workflows/docker-build-push.yml:15-25`

Snippet:
```yaml
- name: Install dependencies & run smoke tests
  run: |
    python -m pip install --upgrade pip
    pip install -r requirements.txt
    python -m compileall ipo_app scripts
```

Explanation: CI runs a syntax smoke check but does not run vulnerability scanning or dependency update tooling.

Steps to reproduce (or reasoning path):

1. Introduce a vulnerable pinned dependency.
2. Observe CI still passes without detection.

Recommended fix (concrete):

1. Add `pip-audit -r requirements.txt` to CI (or run it in a dedicated scheduled workflow).
2. Enable Dependabot (pip + GitHub Actions) or Renovate to propose updates.
3. Consider generating an SBOM (CycloneDX) and storing it as an artifact.

Acceptance criteria:

- CI fails on newly introduced known-vulnerable dependencies (configurable severity threshold).
- Dependency update PRs are generated automatically.

Test plan:

- Add a deliberate vulnerable version in a branch and ensure CI flags it.
- Verify Dependabot opens PRs for dependency updates.

Fix effort: S
Dependencies/Notes:

- Because this repo pins versions in `requirements.txt`, updates can be managed via bot PRs safely.

### ISSUE-016 — Harden GitHub Actions workflow (pin actions, least-privilege permissions, token hygiene)

Category: Process
Severity: Medium
Priority: P2
Confidence: Medium
Component/Area: CI/CD
Mappings: OWASP A05:2021 Security Misconfiguration

Impact:

Unpinned actions and broad default permissions increase supply-chain risk in CI. A compromised action tag or overprivileged token can lead to repository or package compromise.

Evidence:

File(s): `.github/workflows/docker-build-push.yml:8-40`

Snippet:
```yaml
uses: actions/checkout@v4
uses: actions/setup-python@v5
uses: docker/login-action@v3
uses: docker/build-push-action@v5
```

Explanation: Actions are pinned to tags rather than immutable commit SHAs; workflow permissions are not explicitly restricted; registry login uses a custom secret token.

Steps to reproduce (or reasoning path):

1. Review current workflow configuration; note absence of `permissions:` and SHA pinning.

Recommended fix (concrete):

1. Add `permissions:` with least privilege (e.g., `contents: read`, `packages: write` where needed).
2. Pin GitHub Actions to commit SHAs.
3. Prefer `GITHUB_TOKEN` (scoped via permissions) for GHCR where possible; avoid long-lived PATs.

Acceptance criteria:

- Workflow has explicit least-privilege permissions.
- All third-party actions are pinned by SHA.
- Package publishing works without a long-lived personal token (or token scope is minimized and rotated).

Test plan:

- Run workflow on a test branch and confirm image build/push still succeeds.

Fix effort: S
Dependencies/Notes:

- Keep an internal doc for token rotation if PATs remain necessary.

### ISSUE-017 — Add `SECURITY.md` and a vulnerability reporting process

Category: Process
Severity: Low
Priority: P3
Confidence: High
Component/Area: Repo hygiene
Mappings: ASVS V1.1 (Security Requirements)

Impact:

Without a clear disclosure path, security reports can be missed or mishandled, increasing time-to-fix and risk of public disclosure without mitigation.

Evidence:

File(s): `SECURITY.md` (missing in repo root)

Explanation: No security reporting guidance is present in the repository.

Steps to reproduce (or reasoning path):

1. Search for `SECURITY.md` in the repo; none found.

Recommended fix (concrete):

1. Add a `SECURITY.md` with:
   - supported versions (if any)
   - contact email(s)
   - expected response timelines
   - guidance on what information to include

Acceptance criteria:

- `SECURITY.md` exists and provides a clear contact process.

Test plan:

- N/A (documentation review).

Fix effort: S
Dependencies/Notes:

- If this is a private/internal project, still add internal reporting guidance.

### ISSUE-018 — Add minimal automated tests for critical flows (auth, uploads, exports)

Category: Process
Severity: Medium
Priority: P2
Confidence: High
Component/Area: Test strategy
Mappings: ASVS V1.1 (Security Requirements)

Impact:

Security-sensitive code paths (auth checks, locks, uploads, exports) can regress silently. Even a small test suite dramatically reduces the chance of shipping breakages during event-critical periods.

Evidence:

File(s): `README.md:157-159`

Snippet:
```text
## Testing
Current repo has no automated tests; `pytest` runs but collects none. Add tests under `tests/` and target `pytest` in CI.
```

Steps to reproduce (or reasoning path):

1. Run `pytest`.
2. Observe no tests are collected/executed.

Recommended fix (concrete):

1. Add a minimal `tests/` suite using Flask’s test client covering:
   - login flows (admin/student/teacher/board)
   - CSRF enforcement for admin POST actions
   - upload validation and download access control
   - export endpoints basic behavior (with size limits mocked)
2. Run these tests in CI and block merges on failures.

Acceptance criteria:

- CI runs tests and fails on regressions in critical flows.
- At least one test covers each P0 security control (CSRF, auth guards, safe redirects).

Test plan:

- Add `pytest` to dev dependencies (or CI-only installation) and run in GitHub Actions.
- Include regression tests for each fixed vulnerability.

Fix effort: L
Dependencies/Notes:

- Start with focused, deterministic tests; avoid end-to-end PDF rendering tests unless necessary (mock WeasyPrint/PyPDF2 where possible).

## 5) Appendix

Commands you ran (if any) + high-level results (no secrets)

- `git status -sb` (working tree has local modifications/untracked docs/templates; review focused on current workspace state).
- `pip-audit -r requirements.txt` (via a temporary venv) → 1 known vulnerability: `pymysql 1.1.0` → fixed in `1.1.1` (CVE-2024-36039).
- `bandit -r ipo_app scripts -q` (via a temporary venv) → 9 low-severity findings (mostly `subprocess` import/call and `random` usage in seed scripts).

Assumptions

- Admin access is controlled via `ADMIN_USERS` and the `protect_admin_routes` gate in `ipo_app/views.py`; deployment is expected to run behind HTTPS in production.
- `instance/` artifacts in this workspace may include sensitive data and are not intended to be committed; nonetheless they are part of the local build context unless `.dockerignore` is added.

Areas not reviewed (if any)

- Runtime infrastructure hardening (reverse proxy/TLS config, WAF, network policies) beyond what’s present in repo.
- The contents of binary documents under `docs/` and `share/` (reviewed only as supporting artifacts, not for security of their contents).
