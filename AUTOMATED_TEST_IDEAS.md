# Automated Test Ideas (Backlog)

This file tracks additional automated tests beyond the initial “top 10 ROI” suite and notes which ones are implemented under `tests/`.
They are grouped by area so it’s easy to expand coverage incrementally.

## Auth & Authorization
- [x] Admin logout clears session and redirects to `/admin/login`.
- [x] Direct GET `/admin/login` while already logged in redirects to `/admin`.
- [x] Invalid admin credentials do not create a session (and keep user on login page).
- [x] Invalid student credentials do not create a session (and show login page again).
- [x] Invalid teacher portal credentials do not create a session (and show login page again).
- [x] Teacher portal disabled → any `/teacher/*` route redirects to `/board/login` (guard behavior).
- [x] Teacher portal login accepts a safe `next=/teacher/...` and redirects there.
- [x] Student portal `next` parameter is preserved when redirecting from `/participant/portal` to login.
- [x] Teacher board requires authorization (redirects `/board` to `/board/login`).
- [x] Teacher board login fails closed when `TEACHER_BOARD_PASSWORD` is unset/empty (503 on submit).
- [x] Teacher board logout clears the session.

## CSRF & Security Controls
- [x] Admin POST with valid CSRF succeeds for `/admin/uploads/lock` and toggles `upload_locked`.
- [x] Admin POST with valid CSRF succeeds for `/admin/grading/lock` and toggles stage locks.
- [x] Admin POST with missing CSRF is rejected for representative endpoints across modules (planner, surveys, messages, invitations).
- [x] Safe redirect: `/admin/login?next=https://evil` does not redirect off-site after login.
- [x] Safe redirect: `/participant/login?next=https://evil` does not redirect off-site after login.
- [x] Teacher portal safe redirect: reject `next` containing CR/LF or whitespace variants.

## Uploads (Student)
- [x] Uploads disabled (`essay_upload_enabled=false`) blocks POST upload and finalize actions.
- [x] Upload lock (`upload_locked=true`) blocks POST upload and finalize actions.
- [x] Upload rejects non-`.pdf` filenames (e.g. `essay.txt`).
- [x] Upload history download (`/participant/upload/history/<id>/download`) returns 404 for wrong student.
- [x] Upload finalization requires an existing upload and sets `essay_finalized=True`.
- [x] “Hard” word-limit mode blocks finalization when `essay_word_count > essay_word_limit_words` (mock `_count_pdf_words`).

## Essay Access (Download/Preview Guards)
- [x] Student preview allowed after upload (`/participant/upload/preview` returns 200).
- [x] Student download blocked before event end (`/participant/upload/download` returns 403).
- [x] Student download allowed after event end (set `event_end` in the past or use `event_end_override=force_end` and assert 200).
- [x] Delegation leader essay download blocked before event end.
- [x] Delegation leader can only download essays from their country (404 cross-country).

## Exports
- [x] `/admin/exports` redirects to `/admin/login` for non-admin (global admin guard).
- [x] Essay archive export with `finalized_only=1` includes only finalized essays.
- [x] Essay archive export returns warning redirect when no essays exist.
- [x] Database export for SQLite returns an `.sql` file response and creates a backup artifact in `BACKUP_FOLDER`.
- [x] Log CSV export returns expected headers and respects `LOG_EXPORT_LIMIT`.
- [x] Student/teacher XLSX exports return XLSX content-type and include expected columns.

## Teacher Portal (Assignments & Scoring)
- [x] Teacher sees assigned essays only (setup minimal group/assignment rows).
- [x] Teacher cannot download assignment essay until student finalizes upload.
- [x] Teacher score draft save persists numeric score + comments.
- [x] Teacher score finalization sets `teacher_finalized=True` and timestamps.
- [x] Stage lock blocks teacher downloads and score edits.

## Invitations & Registration
- [x] Registration invite-only mode blocks open registration routes.
- [x] Delegation leader invite endpoints reject non-leader teachers (403).
- [x] Delegation invite prevents duplicate invites (same email/role/country) while active.
- [x] Admin invitation revoke prevents reuse of invite links.
- [x] Student open registration succeeds and creates portal credentials.
- [x] Student open registration rejects duplicate email addresses.
- [x] Teacher open registration succeeds and creates portal credentials.
- [x] Teacher open registration rejects duplicate email addresses.
- [x] Teacher registration validates that English is selected as a language.

## Surveys
- [x] Student surveys page requires authentication.
- [x] Teacher surveys page requires authentication and portal enabled.
- [x] Survey publish flow flips status and (when email automation enabled) queues recipients.
- [x] Survey responses XLSX export returns XLSX and includes expected columns.
- [x] Survey publish rejects draft surveys with no questions.
- [x] Student survey response submission saves data and completes assignment.
- [x] Teacher survey response submission saves data and completes assignment.

## Communication Campaigns
- [x] Creating a draft campaign validates required fields.
- [x] Preview endpoint renders without sending emails.
- [x] Send flow enqueues recipients and tracks success/failure states (with SendGrid mocked).
- [x] Resend-failed endpoint only retries failed recipients.
- [x] Send flow is blocked when SendGrid is not configured.
- [x] Resend-failed flow is blocked when SendGrid is not configured.

## Regression “Contracts” (Cheap, High Signal)
- [x] Admin pages render (smoke GET): `/admin`, `/admin/settings`, `/admin/exports`, `/admin/logs`.
- [x] Public pages render (smoke GET): `/`, `/participant/login`, `/board/login`.
- [x] Rate limits disabled in tests do not block repeated logins (sanity check).

## Password Resets
- [x] Student reset request creates a token and invalidates previous open tokens.
- [x] Student reset token sets a new password and marks the token used.
- [x] Student reset token rejects expired/used tokens.
- [x] Teacher reset token sets a new password and marks the token used (portal enabled).

## Invite Acceptance
- [x] Student invite link sets `opened_at` on first view.
- [x] Student registration via invite marks invite accepted and prevents reuse.
- [x] Teacher registration via delegation-leader invite sets `delegation_leader=True`.

## Teacher Portal Authorization (Extra)
- [x] Unassigned teacher cannot access assignment detail/download (403).

## Admin Messages (Teacher Board)
- [x] Admin can post a broadcast teacher-board message and it creates an activity log entry.
- [x] Admin can post a targeted teacher-board message and it creates an activity log entry.
- [x] Admin can edit an existing message and changes persist (with an activity log entry).
- [x] Admin archive/restore flow toggles message visibility status (with activity log entries).
- [x] Admin can delete a message (and logs the deletion).
- [x] Quick message endpoint creates a targeted message (and logs activity).
- [x] Message templates can be created and used to prefill the message compose form.
- [x] Message templates reject duplicate template names with a form error.

## Teacher Board (Filters & Visibility)
- [x] Teacher board login rejects invalid password and logs the failed attempt.
- [x] Portal-authenticated teachers see only broadcast messages and messages targeted to them (excluding archived).
- [x] Search filter matches message title/body and filters results.

## Password Resets (Privacy)
- [x] Student reset request for unknown email shows generic success and does not create a token.
- [x] Teacher reset request for unknown email shows generic success and does not create a token.

## Planner (Stage Setup)
- [x] Admin planner can create an assignment batch (and logs `batch_created`).
- [x] Admin planner can create a reading group for a batch (and logs `group_created`).

## App Security Config
- [x] Startup refuses insecure `SECRET_KEY` outside development/test.
- [ ] Production defaults `SESSION_COOKIE_SECURE=True` when unset.
- [ ] `SESSION_COOKIE_SAMESITE` normalizes invalid values to `Lax`.
