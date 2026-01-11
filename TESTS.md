# Manual QA Tests

This document describes manual QA checks for the IPO app. Each test is written
as a short, step-by-step procedure with expected results.

## Conventions
- Steps are numbered.
- Expected results are bullet lists.
- Use a fresh browser session when testing logins.
- Prefer separate private windows per role (Admin / Teacher / Student).

## Test data & credentials
- Admin credentials come from `ADMIN_USERS` (compose default: `admin:dev-password`).
- Teacher board access uses `TEACHER_BOARD_PASSWORD` (unless accessing via the teacher portal session).
- Student/teacher portal credentials come from: seed script output, registration confirmation (if email automation is enabled), or admin-triggered resets.
- Email delivery tests require both SendGrid env vars (`SENDGRID_API_KEY`, `SENDGRID_FROM_EMAIL`) and the in-app toggle (Admin -> Settings -> “Enable automatic emails”).

## External QA setup (no repo/scripts access)
If testers cannot access the repository or run `docker compose`/seed scripts, provide them with a hosted/staging URL and the items below.

### What testers need (minimum)
- App base URL (and whether it is staging or production-like).
- One working admin account (username + password).
- `TEACHER_BOARD_PASSWORD` value (for board-login tests).
- Whether SendGrid is configured and whether automatic emails are enabled (and access to the test inboxes, if email flows are in-scope).
- A small sample PDF for uploads (and optionally a >10MB PDF to test size limit).

### Bootstrap without scripts (critical path)
These steps create enough data to test delegation invites, registration, planner, uploads, and scoring without seed scripts:

1) **Admin enables required modules**
   - Admin -> Settings:
     - Enable “Enable teacher portal…”
     - Enable “Enable essay upload module”

2) **Create (or designate) a delegation leader**
   - Option A (open registration): register a teacher at `/register/teacher` and tick “Yes, this teacher is a delegation leader”.
   - Option B (admin designation): register any teacher, then Admin -> Teachers -> Edit -> enable “Delegation leader”.
   - Option C (invite-only bootstrap): Admin -> Invitation -> “Delegation leader invite” -> create an invite, open the invite link in a private window, complete teacher registration. This works even when “Require invite link for registrations” is enabled.
   - If email automation is disabled, issue teacher portal credentials via:
     - Admin -> Exports -> Teacher portal cards (recommended), or
     - Admin -> Teachers -> Reset password (manual sharing)

3) **Delegation leader creates invitation links**
   - Log in at `/teacher/login`, open “Delegation invites”, create student/teacher invites, and copy the generated invite links.
   - Open invite links in private windows to complete registrations.
   - Note: Admin -> Invitation shows delegation + normal invites across all countries; the “Delegation invites” screen remains the per-delegation working view for delegation leaders.

4) **Admin creates Stage 1 setup**
   - Admin -> Planner: create a Stage 1 batch, add a reading group, add ≥4 active teachers, assign students, publish the batch.

5) **Students upload essays**
   - Use student credentials (admin reset action or participant cards after publishing Stage 1) to log in, upload a PDF, and finalize.

After this, Stage 1/Stage 2 scoring, packets, exports, surveys, messages, communications, and logs can be tested normally via the UI.

## Environment setup
These steps are for local/developer environments. For hosted/staging black-box QA, skip to “Role: Public (Unauthenticated)”.

### E-01 Start the stack
Steps:
1. Run `docker compose up -d --build`.
2. Open the app at `http://localhost:5000`.
Expected:
- Containers start without errors.
- The app responds with a login page or landing page.

### E-02 Apply migrations
Steps:
1. Run `docker compose run --rm --entrypoint flask web db upgrade`.
Expected:
- Alembic finishes without errors.

### E-03 Seed test data (optional but recommended)
Steps:
1. Run `docker compose run --rm web python scripts/seed_mock_data.py --reset` (or `python scripts/seed_mock_data.py --reset` if using a local venv).
2. (Optional) Run `docker compose run --rm web python scripts/seed_mock_essays.py --overwrite --finalize`.
3. (Optional) Run `docker compose run --rm web python scripts/seed_stage1_scores.py --overwrite`.
4. (Optional) Run `docker compose run --rm web python scripts/seed_stage2_scores.py --overwrite`.
Expected:
- Seed scripts finish without errors and print sample credentials.

### E-04 Configure SendGrid + automation (optional)
Steps:
1. Set `SENDGRID_API_KEY` and `SENDGRID_FROM_EMAIL` in the environment (or `.env`) and restart the app.
2. Log in as admin and go to Admin -> Settings.
3. Enable “Enable automatic emails” and save settings.
4. Go to Admin -> Communication and open “New campaign”.
Expected:
- Settings save successfully.
- Communication screens do not warn about missing SendGrid credentials.
- Preview/send actions are available (sending is blocked only when SendGrid is not configured).

### E-05 Teacher portal + board password (optional)
Steps:
1. Set `TEACHER_BOARD_PASSWORD` and restart the app.
2. As admin, go to Admin -> Settings and enable “Enable teacher portal…”.
3. Open `http://localhost:5000/board/login` in a private window.
Expected:
- Teacher portal routes are accessible after enabling the setting.
- Teacher board login accepts the configured password.

## Role: Public (Unauthenticated)
### P-01 Landing page
Steps:
1. Open `http://localhost:5000/`.
Expected:
- The landing page loads without errors.
- Registration links are visible (student and teacher).

### P-02 Access control smoke test
Steps:
1. In a private window, open each URL directly:
   - `http://localhost:5000/admin`
   - `http://localhost:5000/admin/settings`
   - `http://localhost:5000/admin/planner`
   - `http://localhost:5000/admin/invitations`
   - `http://localhost:5000/participant/portal`
   - `http://localhost:5000/teacher/`
2. Observe the response and any redirects.
Expected:
- Admin pages require admin authentication (redirect to `/admin/login` or show HTTP 403).
- Student portal requires student authentication (redirect to `/participant/login`).
- Teacher portal requires teacher authentication (redirect to `/teacher/login`).

### P-03 CSRF protection (optional)
Steps:
1. With no active sessions, attempt a POST to an admin endpoint without a CSRF token (e.g. using `curl`) and note the status code.
Expected:
- POST requests without CSRF tokens are rejected (typically HTTP 400/403).

## Role: Applicant (Registration)
### REG-01 Student registration (open registration)
Steps:
1. Ensure invite-only registration is disabled in Admin -> Settings.
2. Open `http://localhost:5000/register/student`.
3. Submit a valid form (including GDPR + ethics confirmations and photo consent choice).
Expected:
- The registration succeeds.
- Re-submitting with the same email is rejected as a duplicate.

### REG-02 Teacher registration (open registration)
Steps:
1. Ensure invite-only registration is disabled in Admin -> Settings.
2. Open `http://localhost:5000/register/teacher`.
3. Submit a valid form (including GDPR + ethics + assessor competence confirmations).
Expected:
- The registration succeeds.
- The teacher appears in Admin -> Teachers.

### REG-05 Registration confirmation emails (optional)
Steps:
1. Ensure SendGrid is configured and “Enable automatic emails” is enabled in Admin -> Settings.
2. Register a new student and a new teacher (with unique emails).
Expected:
- Confirmation emails are delivered with portal credentials and correct login links.
- If automation is disabled, registrations still succeed but no emails are sent.

### REG-03 Teacher language validation
Steps:
1. Open `http://localhost:5000/register/teacher`.
2. Select languages that do not include English (if the UI allows).
3. Submit the form.
Expected:
- Submission is rejected with an error that English must be selected.

### REG-04 Invite-only registration messaging
Steps:
1. As admin, enable “Require invite link for registrations”.
2. In a private window, open `http://localhost:5000/register/student` and `http://localhost:5000/register/teacher` without an invite token.
Expected:
- Both pages show an invite-only notice and do not allow registration submission.

## Role: Admin (Operations)
### A-01 Admin login
Steps:
1. Open `http://localhost:5000/admin/login`.
2. Log in using a valid admin user (default in compose: `admin` / `dev-password`).
Expected:
- Admin dashboard loads with metrics and alerts.

### A-02 Settings: upload window and locks
Steps:
1. Go to Admin -> Settings.
2. Enable "Essay upload module".
3. Save settings.
4. Go to Admin -> Dashboard.
5. Toggle "Upload lock" on, then off.
Expected:
- Settings save with success flash.
- Upload lock toggle updates and shows success toast.

### A-03 Settings: event end and manual override
Steps:
1. Go to Admin -> Settings.
2. Set Event end to a time in the past.
3. Set Event access override to "Auto (use event end time)".
4. Save settings.
5. Return to Settings and set Event access override to "Force open (keep downloads locked)".
6. Save settings.
Expected:
- Event end is stored and visible on reload.
- Override changes persist and take effect immediately.

### A-04 Invite-only registration
Steps:
1. Go to Admin -> Settings.
2. Enable "Require invite link for registrations".
3. Save settings.
4. Open `http://localhost:5000/register/student` in a private window.
Expected:
- Registration page shows invite-only notice and does not allow submission.

### A-05 Stage lock and teacher portal effect
Steps:
1. Enable teacher portal in Admin -> Settings (if disabled).
2. Go to Admin -> Dashboard and lock Stage 1.
3. Log in as a teacher (assessor).
4. Open an assignment detail page and attempt to download the essay.
Expected:
- Teacher sees a lock message.
- Download is blocked while the stage lock is active.

### A-06 Exports
Steps:
1. Go to Admin -> Exports.
2. Download "Essay archive".
3. Download the database dump (if MySQL/MariaDB).
Expected:
- Files download without server errors.

### A-07 Admin logout
Steps:
1. From any admin page, click “Logout” (or open `http://localhost:5000/admin/logout`).
2. Open `http://localhost:5000/admin` again.
Expected:
- The admin session is cleared.
- Protected admin pages require login again (redirect to `/admin/login` or HTTP 403).

### A-08 Dashboard: metrics, alerts, filters
Steps:
1. Open Admin -> Dashboard.
2. Use the “Essay language” filter and verify the “Students without uploads” table changes.
3. Use the “Alert level” filter and verify the alerts list changes.
Expected:
- Metrics render without errors and values are plausible for the seeded data.
- Alerts link to the expected admin screens.
- Filters update dashboard content without breaking layout (HTMX swap should preserve scroll where applicable).

### A-09 Settings: essay word limit modes
Steps:
1. Go to Admin -> Settings and set a low “Essay word limit” (e.g. 50).
2. Set “Essay word limit mode” to “Soft warning” and save.
3. As a student, upload a PDF that exceeds the limit and observe feedback.
4. Change “Essay word limit mode” to “Hard block finalization” and save.
5. As a student, attempt to finalize an over-limit PDF.
Expected:
- Soft mode shows a warning but allows finalization.
- Hard mode blocks finalization until a shorter PDF is uploaded.

### A-10 Settings: packet print mode (single vs double)
Steps:
1. Go to Admin -> Settings and set “Packet print mode” to “Double-sided”.
2. Generate a packet PDF (Planner reader packet, Stage 2 packet, extra-reader packet, or Stage 3 packets).
3. Repeat with “Single-sided”.
Expected:
- Double-sided mode inserts blank spacer pages so title pages and essays start on fresh front pages.
- Single-sided mode generates packets without spacer pages.

### A-11 Settings: registration consent/statement text blocks
Steps:
1. Go to Admin -> Settings and edit the Ethics/GDPR/Photo consent/Assessor competence HTML fields with recognizable text.
2. Open `http://localhost:5000/register/student` and `http://localhost:5000/register/teacher`.
Expected:
- Updated consent/statement content is visible on the registration pages.
- HTML is rendered safely and does not break the layout.

### A-12 Settings: email automation gating
Steps:
1. With SendGrid not configured or “Enable automatic emails” disabled, publish a survey with “Send notification email” enabled.
2. With SendGrid configured and “Enable automatic emails” enabled, repeat the publish flow.
Expected:
- When automation is disabled, the UI indicates notifications are disabled and no emails are sent.
- When automation is enabled and SendGrid is configured, notification emails are sent (or failures are clearly reported).

### A-13 Settings: deadlines and SLA appear on dashboard
Steps:
1. Go to Admin -> Settings and set upload deadline, Stage 2 deadline, and Stage 1/Stage 2 SLA values.
2. Open Admin -> Dashboard.
Expected:
- Deadlines render with correct UTC timestamps and “Due in … / Overdue by …” messaging.
- SLA values render on the dashboard deadline panel.

### A-14 Admin help page
Steps:
1. Go to Admin -> Help.
Expected:
- The help page loads without errors and provides operator guidance relevant to the current build.

### A-15 Invitations (admin): delegation + normal
Steps:
1. Go to Admin -> Settings and enable “Require invite link for registrations” (invite-only).
2. Go to Admin -> Invitation.
3. Create a “Delegation leader invite” (first name, last name, email, country).
4. Click “Open invite” (or copy the link) and open it in a private window.
5. Verify the invite status changes from Pending → Started.
6. Complete teacher registration using the invite link.
7. Verify the invite status changes to Completed and the teacher appears in Admin -> Teachers with “Delegation leader” = Yes.
8. Create a “Normal invite” (choose Student or Teacher, name/email/country), open the link, and complete registration.
9. If delegation leaders exist, create a “Delegation invite” (select delegation leader, choose Student/Teacher, name/email), open the link, and complete registration.
10. (Optional) Create an invite for an email that already exists as a student/teacher.
11. (Optional) Create a second invite (new email), then use “Revoke” and verify the invite becomes unusable.
12. (Optional) With email automation enabled, use “Resend” on an active invite and verify the Email status updates.
Expected:
- Invite-only registration can still be bootstrapped without disabling invite-only.
- Completed invite creates a teacher record with delegation leader privileges.
- Duplicate-email invite creation is blocked with guidance to use Teachers -> Edit instead.
- Revoked invites show a revoked message on the registration page and cannot be completed.

## Role: Registration Desk (Admin)
### R-01 Edit student and reset portal password
Steps:
1. Go to Admin -> Students.
2. Open a student and click Edit.
3. Update a field (e.g., school) and save.
4. Use the "Reset password" action for the same student.
Expected:
- Student record saves successfully.
- Password reset completes and shows a success flash.

### R-02 Edit teacher and set delegation leader
Steps:
1. Go to Admin -> Teachers.
2. Edit a teacher and enable "Delegation leader".
3. Save changes.
Expected:
- Teacher record updates successfully.
- Teacher can see delegation leader actions in the portal.

### R-03 Mark participants absent and verify effects
Steps:
1. Edit a student and set “Marked absent”, then save.
2. Attempt student login and note the result.
3. Edit a teacher and set “Marked absent”, then save.
4. Attempt teacher portal login and note the result.
Expected:
- Absent students cannot log into the participant portal.
- Absent teachers cannot log into the teacher portal.
- Absent participants are excluded from assignment/scoring lists unless explicitly included by filters.

### R-04 Teacher edit: English language required
Steps:
1. Go to Admin -> Teachers and edit a teacher.
2. Remove “English” from the languages selection and attempt to save.
Expected:
- Saving is rejected with an error that English must be selected.

### R-05 Reset teacher portal password (admin-triggered)
Steps:
1. Go to Admin -> Teachers.
2. Use “Reset password” for a teacher.
3. Attempt teacher portal login using the new password and verify the old password no longer works.
Expected:
- The reset completes with a success/warning message (depending on email automation).
- New credentials work; old credentials do not.

## Role: Admin (Planner)
### PL-01 Create a Stage 1 batch
Steps:
1. Go to Admin -> Planner.
2. Create a new batch (Stage 1) and save.
Expected:
- The new batch appears in the planner list with Draft status.

### PL-02 Create a reading group and add members
Steps:
1. Open the batch detail page.
2. Create a reading group (choose language and group name).
3. Add at least 4 teachers as active members.
Expected:
- The group is created and listed under the batch.
- Members are listed with roles (leader/reader/backup) and active state.

### PL-03 Promote/demote group leader
Steps:
1. In a group with members, promote a different member to “Leader”.
2. Reload the page.
Expected:
- Only one member is marked as Leader; the previous leader becomes a Reader automatically.

### PL-04 Group lock toggles affect assignment actions
Steps:
1. Lock a group in the planner.
2. Attempt to assign a student to the locked group.
3. Unlock the group and try again.
Expected:
- Locked groups reject manual assignment.
- Unlocked groups accept valid assignments.

### PL-05 Manual assignment constraints (language + country)
Steps:
1. Attempt to assign a student whose essay language differs from the group language.
2. Attempt to assign a student from the same country as an active teacher in the group (when “Allow same-country readers” is off).
Expected:
- Language mismatch is rejected.
- Same-country conflicts are rejected unless explicitly allowed.

### PL-06 Manual assignment removal and published-batch immutability
Steps:
1. Add a manual assignment to a draft batch.
2. Remove the assignment.
3. Publish the batch and attempt to remove an assignment again.
Expected:
- Assignments can be removed while the batch is draft.
- Assignments cannot be modified on a published batch.

### PL-07 Auto-generate groups
Steps:
1. On a draft batch, use “Auto-generate groups”.
2. Review the generated groups and members.
Expected:
- Auto-generated groups are created with 4 active members per group where possible.
- Backup teachers are added as inactive backups where applicable.
- Re-running auto-generate replaces previous auto-generated groups but keeps manual groups intact.

### PL-08 Auto-assign essays to groups
Steps:
1. Ensure groups exist and have at least 4 active members.
2. Run “Auto-assign essays”.
Expected:
- Students are assigned to eligible groups based on language/country constraints and target loads.
- Any skipped students are reported and remain unassigned.
- Manual assignments are preserved.

### PL-09 Publish/unpublish batch and active batch switching
Steps:
1. Publish a Stage 1 batch.
2. Publish a different Stage 1 batch.
3. Confirm only one Stage 1 batch remains published (the latest).
4. Unpublish the active batch.
Expected:
- Publishing a batch automatically unpublishes other batches of the same stage.
- Unpublishing returns the batch/groups/assignments to draft state.

### PL-10 Planner PDF exports
Steps:
1. Export the “groups” PDF and “teachers” PDF for the batch.
2. Generate a “reader packet” PDF for a group.
Expected:
- PDFs download without errors.
- Reader packet includes a title page per teacher and essay overlays on first pages.
- Missing uploads (if any) are reported as warnings.

## Role: Admin (Stage 1 uploads & scoring)
### ST1-01 Stage 1 uploads list
Steps:
1. Ensure a Stage 1 batch is published.
2. Go to Admin -> Stage 1.
Expected:
- Students list renders with upload status and Stage 1 scoring status per student.

### ST1-02 Stage 1 essay download
Steps:
1. From Admin -> Stage 1, download a student essay that exists.
2. Attempt to download an essay for a student without an upload.
Expected:
- Existing essays download as PDFs.
- Missing essays are rejected (HTTP 404 or an appropriate error message).

### ST1-03 Scoring page renders reader statuses
Steps:
1. From Admin -> Stage 1, open a student scoring page.
2. Review portal status codes/labels (waiting upload/finalization, pending, draft, finalized, admin-entered/override, locked).
Expected:
- Reader list includes group members plus any extra readers.
- Status labels match the essay/file/finalization/lock state.

### ST1-04 Assign a Stage 1 extra reader
Steps:
1. On a scoring page, assign an additional reader (extra reader).
2. Log in as that teacher and verify the assignment appears in the teacher portal.
Expected:
- Extra reader is added on the scoring page.
- Teacher portal shows the assignment and allows grading once the student has finalized the essay.

### ST1-05 Remove a Stage 1 extra reader
Steps:
1. Remove an extra reader from the scoring page.
Expected:
- The extra reader is removed.
- Any existing score for that extra reader is removed.

### ST1-06 Admin enters/edits scores (validation + flags)
Steps:
1. Enter invalid values (non-numeric, <0, >10) and attempt to save.
2. Enter valid scores and save.
3. If a teacher already submitted a score, change it as admin.
Expected:
- Invalid input is rejected with an error.
- Valid input is saved and timestamps update.
- Changing a teacher-submitted score marks it as an admin override (visible in status labels).

### ST1-07 Unlock teacher-finalized score for editing
Steps:
1. As a teacher, finalize a score.
2. As admin, use the “Unlock” action for that teacher’s score.
3. As teacher, refresh and edit the score.
Expected:
- Unlock clears the teacher-finalized lock and allows further edits.

### ST1-08 Per-assignment Stage 1 lock
Steps:
1. On a scoring page, toggle the Stage 1 lock for the assignment.
2. As teacher, verify download and saving are blocked.
3. Toggle unlock and verify access returns.
Expected:
- Locked assignments show “locked” status and disable teacher downloads/edits.
- Unlock restores access immediately.

### ST1-09 Stage 2 candidate and extra-reading flags
Steps:
1. Toggle “Mark as Stage 2 candidate”.
2. Toggle “Needs extra reading”.
Expected:
- Flags toggle successfully and are mutually exclusive (setting one clears the other).
- Stage 2 candidate status is reflected in Admin -> Stage 2 candidate list.

### ST1-10 Extra-reader packet PDF
Steps:
1. Ensure at least one extra reader is assigned.
2. Generate the extra-reader packet PDF.
Expected:
- PDF downloads and contains a title page plus the essay with overlays per extra reader.
- Duplex setting affects blank spacer pages.

## Role: Admin (Stage 2 scoring)
### ST2-01 Stage 2 overview prerequisites
Steps:
1. With no published Stage 1 batch, open Admin -> Stage 2.
Expected:
- The UI blocks Stage 2 and instructs you to publish a Stage 1 batch first.

### ST2-02 Stage 2 candidate list
Steps:
1. Ensure at least one student is marked as a Stage 2 candidate.
2. Open Admin -> Stage 2.
Expected:
- Candidate list loads and shows Stage 1 and Stage 2 status indicators.

### ST2-03 Assign and remove Stage 2 readers
Steps:
1. Open a Stage 2 scoring page for a candidate.
2. Assign a Stage 2 reader.
3. Remove the Stage 2 reader.
Expected:
- Stage 2 reader assignment is created and removed successfully.
- Teacher portal Stage 2 assignments appear/disappear accordingly.

### ST2-04 Stage 2 score entry (validation + override)
Steps:
1. Enter invalid scores and attempt to save.
2. Enter valid scores and save.
3. If a teacher submitted a score, edit it as admin.
Expected:
- Invalid input is rejected.
- Valid scores are saved and reflected in averages/spreads.
- Admin edits are flagged as admin-entered/admin-override.

### ST2-05 Stage 2 lock and unlock finalized scores
Steps:
1. Toggle the per-assignment Stage 2 lock.
2. As teacher, attempt to download/save and verify it is blocked.
3. As admin, unlock a teacher-finalized score and verify the teacher can edit again.
Expected:
- Lock blocks downloads and edits.
- Unlocking a finalized score re-enables edits for that teacher.

### ST2-06 Stage 3 recommendation flag
Steps:
1. On a Stage 2 scoring page, toggle “Stage 3 recommended”.
2. Open Admin -> Stage 2 -> Stage 3 packets.
Expected:
- Recommended essays appear in the Stage 3 packet selection list.

### ST2-07 Stage 2 packet PDF
Steps:
1. Assign at least one Stage 2 reader to a candidate.
2. Generate the Stage 2 packet PDF for the assignment.
Expected:
- PDF downloads with a title page per Stage 2 reader and an essay overlay.
- Missing uploads or missing readers produce clear warnings/errors.

## Role: Admin (Grades export)
### GR-01 Export grades (XLSX)
Steps:
1. Go to Admin -> Grades export.
2. Select export format “Excel workbook (.xlsx)” and download.
Expected:
- XLSX downloads successfully.
- Output includes per-stage score slots plus average/spread columns and a “recommended” indicator.

### GR-02 Export grades (PDF)
Steps:
1. Go to Admin -> Grades export.
2. Select export format “PDF summary” and download.
Expected:
- PDF downloads successfully and is readable (layout, headers, timestamps according to options).

### GR-03 Grade export filters and options
Steps:
1. Apply filters: countries, stages, “finalized only”, “include absent”, and “Stage 3 recommendations”.
2. Toggle anonymization options for students/teachers.
3. Export XLSX and PDF variants.
Expected:
- Filters change which students/scores appear in the output.
- Anonymization and timestamps options are reflected in the generated report.

## Role: Admin (Messages)
### MSG-01 Create a broadcast message
Steps:
1. Go to Admin -> Messages.
2. Create a message targeted to “All teachers”.
3. Open Teacher Board and a teacher portal dashboard.
Expected:
- Message appears on the teacher board.
- Message appears for teachers on the teacher portal dashboard.

### MSG-02 Create a targeted message
Steps:
1. Create a message targeted to a single teacher.
2. Log in as a different teacher and open the teacher board/portal dashboard.
Expected:
- Target teacher can see the message.
- Other teachers cannot see the message.

### MSG-03 Edit, archive, restore, delete
Steps:
1. Edit an existing message and save.
2. Archive the message and verify it disappears from the teacher board.
3. Restore the message and verify it reappears.
4. Delete the message.
Expected:
- Edit updates content.
- Archive hides the message from active views.
- Restore returns it to active views.
- Delete removes it permanently.

### MSG-04 Message templates
Steps:
1. Go to Admin -> Message templates.
2. Create a template, then use it to prefill a new message.
3. Edit and delete the template.
Expected:
- Templates can be created/edited/deleted.
- Selecting a template pre-fills title/body/category.

### MSG-05 Quick message modal
Steps:
1. From Admin -> Teachers (or another screen with quick message), send a quick message to a teacher.
Expected:
- A success toast appears.
- The teacher receives the message on the teacher board/portal dashboard.

## Role: Admin (Communication campaigns)
### COMM-01 Draft a campaign
Steps:
1. Go to Admin -> Communication -> New campaign.
2. Select audience, optional country filters, and save a draft.
Expected:
- Draft is created with a non-zero recipient count (when matching recipients exist).
- Preview page shows counts and sample recipients.

### COMM-02 Send gating when SendGrid is not configured
Steps:
1. Ensure SendGrid is not configured.
2. Attempt to send a campaign from the preview page.
Expected:
- Sending is blocked with a clear error/warning.
- Campaign remains draft/failed and recipient statuses remain unchanged.

### COMM-03 Send campaign when SendGrid is configured
Steps:
1. Ensure SendGrid is configured.
2. Confirm the send checkbox and submit.
Expected:
- Campaign status transitions to sent (or sent-with-failures).
- Recipient statuses update (sent/failed) and counts match the detail page.

### COMM-04 Resend failed recipients
Steps:
1. Open a campaign with failed recipients.
2. Use “Retry failed recipients”.
Expected:
- Only failed recipients are retried.
- Status counts update accordingly.

## Role: Admin (Surveys)
### SV-01 Create survey draft
Steps:
1. Go to Admin -> Surveys -> New.
2. Create a survey with a title, audience, and optional open/close times.
Expected:
- Draft survey is created and opens the edit screen.

### SV-02 Add/edit/reorder/delete questions
Steps:
1. Add questions of each type (short text, long text, date, radio, select).
2. For radio/select, test validation by providing <2 options.
3. Reorder questions up and down.
4. Edit a question and then delete it.
Expected:
- Options validation rejects invalid option sets.
- Reordering updates the question order and handles boundary cases.
- Deleting a question re-normalizes positions without breaking order.

### SV-03 Publish, notify, close/reopen, unpublish
Steps:
1. Publish a draft survey to selected recipients and optionally notify by email.
2. Close the survey and confirm respondents can no longer submit.
3. Reopen the survey and confirm it accepts submissions again.
4. Attempt to unpublish a survey that already has responses.
Expected:
- Publish creates assignments and (optionally) sends notification emails or reports that automation is disabled.
- Close/reopen changes editability for respondents.
- Unpublish is blocked once responses exist.

### SV-04 Responses review, export, and reminders
Steps:
1. Open Admin -> Surveys -> Responses for a published survey.
2. Filter by audience (teacher/student) and status (completed/outstanding).
3. Export responses to XLSX.
4. Send reminders for outstanding, unlocked assignments.
Expected:
- Filters affect the response list and summary counts.
- XLSX export downloads and includes columns for each question.
- Reminders send only when email automation is enabled; otherwise the UI reports that automation is disabled.

## Role: Admin (Audit logs)
### LOG-01 Filter logs and paginate
Steps:
1. Go to Admin -> Logs.
2. Filter by actor, action, object type, search query, and time range.
3. Navigate pagination links (prev/next).
Expected:
- Filters narrow the results as expected.
- Pagination links preserve filters.

### LOG-02 Export logs CSV
Steps:
1. From Admin -> Logs, export logs to CSV.
Expected:
- CSV downloads and includes timestamp, actor, action, object type/id, description, and details.

## Role: Admin (Exports)
### EX-01 Database export
Steps:
1. Go to Admin -> Exports.
2. Export the database.
Expected:
- Export succeeds for SQLite (file copy) and MySQL/MariaDB (mysqldump) configurations.
- Unsupported DB configurations show a clear “not available” message.

### EX-02 Essay archive export (all vs finalized only)
Steps:
1. Go to Admin -> Exports.
2. Download the essay archive (all essays).
3. Download the essay archive with “finalized only” enabled.
Expected:
- ZIP downloads successfully.
- ZIP includes `manifest.csv` and only the expected essays based on the chosen mode.

### EX-03 Participant and teacher cards (PDF)
Steps:
1. Generate participant cards (Stage 1 batch must be published).
2. Generate teacher portal cards (teacher portal must be enabled).
Expected:
- PDFs download successfully.
- Teacher portal cards reset teacher passwords and include portal + board URLs.

### EX-04 Student/teacher XLSX exports
Steps:
1. Download `http://localhost:5000/admin/students/export`.
2. Download `http://localhost:5000/admin/teachers/export`.
Expected:
- XLSX files download successfully.
- Workbooks contain expected columns and rows for the current database state.

## Role: Delegation Leader
### DL-01 Delegation leader login and navigation
Steps:
1. Open `http://localhost:5000/teacher/login`.
2. Log in using delegation leader credentials.
3. From the dashboard, open "Delegation invites" and "Delegation essays".
Expected:
- Both pages load without errors.

### DL-02 Create a student invite
Steps:
1. Open "Delegation invites".
2. Fill in student first name, last name, and email.
3. Submit the invite form.
4. Copy the invite link and open it in a private window.
Expected:
- Invite row appears with status "Pending".
- Registration form loads with country/email locked to the invite.

### DL-03 Revoke and resend an invite
Steps:
1. On "Delegation invites", click Resend for an active invite.
2. Click Revoke for the same invite and confirm.
Expected:
- Resend updates email status (or shows auto-email disabled warning).
- Revoke changes status to "Revoked" and disables actions.

### DL-04 Delegation essay downloads after event end
Steps:
1. Ask admin to set Event access override to "Force end".
2. Open "Delegation essays".
3. Download a finalized essay.
Expected:
- Download link is visible and works.

### DL-05 Create a teacher invite
Steps:
1. Open "Delegation invites".
2. Fill in the teacher invite form (first name, last name, email) and submit.
3. Copy the invite link and open it in a private window.
Expected:
- Invite row appears with status “Pending”.
- Teacher registration form loads with country/email locked to the invite.
- Delegation leader flag is not available for invite-based teacher registration.

### DL-06 Invite lifecycle: started → completed
Steps:
1. Open an active invite link in a private window (do not submit yet).
2. Return to "Delegation invites" and verify the invite status changes to “Started”.
3. Complete the registration using the invite link.
4. Return to "Delegation invites".
Expected:
- “Started” is shown after the link is opened.
- “Completed” is shown after successful registration and actions (resend/revoke) are disabled.
- Re-opening a completed invite link shows a “already used” message.

### DL-07 Duplicate invite detection
Steps:
1. Create an invite for an email address.
2. Attempt to create another invite for the same email (same role).
Expected:
- The app warns that an active invite already exists and does not create a duplicate.

### DL-08 Delegation essay downloads blocked before event end
Steps:
1. Ask admin to set Event access override to “Force open (keep downloads locked)” (or set Event end to the future with Auto override).
2. Open "Delegation essays" and attempt to download an essay.
Expected:
- Download is blocked with a clear message until the event is over (or override is set to Force end).

### DL-09 Delegation essays status list
Steps:
1. Open "Delegation essays".
2. Verify status labels across students (No upload / Uploaded / Finalized / File missing).
Expected:
- Status labels match the underlying upload/finalization state.
- Download links appear only when the event is over and the student has a finalized essay file.

## Role: Teacher (Assessor)
### T-01 Teacher portal login
Steps:
1. Open `http://localhost:5000/teacher/login`.
2. Log in with teacher portal credentials.
Expected:
- Dashboard loads and shows assigned essays.

### T-02 Download assignment
Steps:
1. From the dashboard, open an assignment detail page.
2. Click "Download essay PDF".
Expected:
- A PDF file downloads successfully.

### T-03 Draft and finalize a score
Steps:
1. On the assignment detail page, enter a score and comments.
2. Click "Save draft".
3. Update the score and click "Finalize".
Expected:
- Draft save shows success message.
- Finalize locks the fields and shows finalized status.

### T-04 Teacher survey response
Steps:
1. Open the Surveys list from the dashboard.
2. Open an outstanding survey.
3. Fill in required fields and submit.
Expected:
- Survey saves and appears as completed.

### T-05 Teacher portal disabled guard
Steps:
1. Ask admin to disable the teacher portal in Admin -> Settings.
2. Open `http://localhost:5000/teacher/login`.
Expected:
- The teacher portal is not accessible and redirects to the teacher board login with an explanatory message.

### T-06 Assignment download gating (locks + finalization)
Steps:
1. Log in to the teacher portal.
2. Open an assignment where the student is not finalized yet and attempt to download.
3. Ask admin to lock Stage 1 or lock the assignment; attempt download again.
Expected:
- Download is blocked until the student finalizes the upload.
- Download is blocked while stage/assignment locks are active.

### T-07 Score validation rules
Steps:
1. Open an assignment detail page.
2. Click “Finalize” with an empty score.
3. Enter a score outside the valid range (e.g. -1 or 11) and attempt to save.
Expected:
- Finalize requires a numeric score.
- Scores outside 0–10 are rejected.

### T-08 Finalize locks editing; admin unlock workflow
Steps:
1. Finalize a score as a teacher.
2. Attempt to edit the score again.
3. Ask admin to unlock the score from the admin scoring page.
4. Refresh and edit the score again.
Expected:
- Finalized scores are read-only for the teacher.
- Admin unlock restores edit capability.

### T-09 Stage 2 assignments (extra reader)
Steps:
1. Ask admin to assign you as a Stage 2 reader for a candidate.
2. Refresh the teacher portal dashboard.
3. Open the Stage 2 assignment, download, and submit a draft/final score.
Expected:
- Stage 2 assignments appear only when you are assigned as an extra Stage 2 reader.
- Stage 2 downloads and scoring behave like Stage 1 (respecting locks and finalization).

### T-10 Teacher password reset (self-service)
Steps:
1. Open `http://localhost:5000/teacher/reset`.
2. Submit your teacher email.
3. If email automation is enabled, use the emailed link to complete the reset and log in with the new password.
Expected:
- Request always shows a generic success message (does not leak account existence).
- Reset links are time-limited; completed links cannot be reused.

### T-11 Teacher board access via portal session
Steps:
1. Log in to the teacher portal.
2. Open `http://localhost:5000/board` without entering the board password.
Expected:
- Access is granted via the teacher portal session.
- The board shows only broadcast messages and messages targeted to the logged-in teacher.

## Role: Student
### S-01 Student login
Steps:
1. Open `http://localhost:5000/participant/login`.
2. Log in with student upload credentials.
Expected:
- Student portal loads with essay status.

### S-02 Upload PDF and finalize
Steps:
1. Open "Essay upload".
2. Upload a valid PDF (under 10 MB).
3. Verify the PDF preview loads.
4. Click "Mark essay as finished" and confirm.
Expected:
- Upload succeeds with success message.
- Preview shows the stored PDF.
- Finalize locks further uploads.

### S-03 Upload history
Steps:
1. Upload a second PDF before finalizing.
2. Scroll to "Upload history".
3. Verify both versions appear with timestamps.
Expected:
- History list shows multiple versions.
- Current version is marked as "Current".

### S-04 Upload lock
Steps:
1. Ask admin to enable Upload lock.
2. Attempt to upload a PDF.
Expected:
- Upload is blocked with a warning or error message.

### S-05 Download after event end
Steps:
1. Ask admin to set Event access override to "Force end".
2. Return to the student portal.
3. Click "Download essay PDF".
Expected:
- Download link is visible on the portal.
- PDF downloads successfully.

### S-06 Student password reset
Steps:
1. Open `http://localhost:5000/participant/reset`.
2. Request a reset with the student email.
3. Use the reset link or ask admin to reset via the Students list.
Expected:
- Reset completes and the new credentials are issued.

### S-07 Student portal dashboard (status + surveys)
Steps:
1. Log in and open `http://localhost:5000/participant/portal`.
2. Review upload status and download notice messaging.
3. Review outstanding surveys and open one from the dashboard.
Expected:
- Upload status reflects whether an essay exists and whether it is finalized.
- Download notice reflects the event end / override settings.
- Outstanding surveys are visible and navigable.

### S-08 Upload module disabled blocks uploads
Steps:
1. Ask admin to disable “Enable essay upload module” in Admin -> Settings.
2. Open `http://localhost:5000/participant/upload` and attempt to upload.
Expected:
- Uploads are blocked with a clear error message.

### S-09 Upload validations (file type + size)
Steps:
1. Attempt to upload a non-PDF file.
2. Attempt to upload a PDF larger than the configured limit (default 10 MB).
Expected:
- Non-PDF files are rejected.
- Oversized files are rejected with a size limit message.

### S-10 Word limit modes (off/soft/hard)
Steps:
1. Ask admin to configure a low word limit and set “Soft warning”.
2. Upload an over-limit PDF and verify you can still finalize.
3. Ask admin to switch to “Hard block finalization”.
4. Attempt to finalize an over-limit PDF.
Expected:
- Soft mode warns but allows finalization.
- Hard mode blocks finalization until a shorter PDF is uploaded.

### S-11 Preview and download access rules
Steps:
1. Upload a PDF and open preview.
2. Try to download the essay before the event end (or when override is “Force open”).
3. After event end (or when override is “Force end”), download the essay.
Expected:
- Preview is available as long as an upload exists.
- Downloads are blocked until the event is over (unless forced).

### S-12 Upload history downloads
Steps:
1. Upload multiple versions before finalizing.
2. Before event end, confirm history downloads are not available.
3. After event end, download a prior upload version.
Expected:
- History shows versions with timestamps and marks the current one.
- History downloads are available only when downloads are allowed.

### S-13 Student surveys: locked vs editable states
Steps:
1. Open `http://localhost:5000/participant/surveys`.
2. Submit a response to an outstanding survey.
3. If the survey is configured with “Allow respondents to edit after submission” turned off, attempt to edit again.
Expected:
- Required question validation works (including date format and option validation).
- Completed surveys are editable only when allow-edit is enabled and the survey is open.

## Role: Teacher Board (Shared)
### B-01 Teacher board login
Steps:
1. Open `http://localhost:5000/board/login`.
2. Log in using the TEACHER_BOARD_PASSWORD.
Expected:
- Access granted and board view loads.

### B-02 Message visibility
Steps:
1. As admin, create a new message (Admin -> Messages).
2. Reload the teacher board.
Expected:
- New message appears on the board.

### B-03 Teacher portal session grants board access
Steps:
1. Log in to the teacher portal as a teacher.
2. Open `http://localhost:5000/board` without entering the board password.
Expected:
- Access is granted based on the portal session.

### B-04 Targeted messages on the board
Steps:
1. Create a message targeted to Teacher A and another targeted to Teacher B.
2. Log in as Teacher A and open the teacher board.
3. Log in as Teacher B and open the teacher board.
Expected:
- Each teacher sees broadcast messages and only messages targeted to themselves.

### B-05 Board filters (priority/category/search)
Steps:
1. On the teacher board, filter by priority and by category.
2. Use the search box to find text in message title/body.
Expected:
- Filters narrow the message list correctly.
- Clearing filters restores the full visible set for the current user.

### B-06 Board logout
Steps:
1. Log in via `http://localhost:5000/board/login`.
2. Click “Logout” (or open `http://localhost:5000/board/logout`).
3. Open `http://localhost:5000/board`.
Expected:
- Board session ends and access requires login again (unless you are signed into the teacher portal).

## Role: Steering Committee (Admin)
### SC-01 Stage 3 packets
Steps:
1. Go to Admin -> Stage 2 -> Stage 3 packets.
2. Provide committee member names and select essays.
3. Generate the PDF packet.
Expected:
- PDF downloads successfully and contains the selected essays.

### SC-02 Stage 3 packet variations (label, duplex, missing uploads)
Steps:
1. Set a custom committee label and provide multiple member names (one per line).
2. Ensure at least one selected essay is missing an upload (optional) and generate packets.
3. Repeat with “Packet print mode” set to Double-sided.
Expected:
- Packets include a title page per committee member and essay overlays on first pages.
- Missing uploads are reported as warnings and omitted from the packet.
- Double-sided mode inserts blank spacer pages so printed packets align correctly.

## Cross-cutting: HTMX regression (optional)
### HX-01 Dashboard HTMX actions
Steps:
1. On Admin -> Dashboard, toggle Stage locks and Upload lock.
2. Watch for full page reloads vs partial swaps.
Expected:
- Actions update the dashboard content area without losing scroll position.
- Toast messages appear consistently.

### HX-02 Planner HTMX actions
Steps:
1. On Admin -> Planner, add/remove a member and add/remove an assignment.
2. Run auto-generate and auto-assign actions.
Expected:
- Planner updates feel “in-place” (no disruptive full reloads).
- Errors are shown as toasts and the page stays on the current batch view.

### HX-03 Scoring HTMX actions
Steps:
1. On Admin -> Stage 1 scoring, add/remove an extra reader and save score updates.
2. On Admin -> Stage 2 scoring, add/remove Stage 2 readers and save score updates.
Expected:
- Scoring tables update without full page reload.
- Status badges and counts refresh immediately after actions.

### HX-04 Survey authoring HTMX actions
Steps:
1. On Admin -> Surveys -> Edit, add a question, delete a question, and reorder questions.
Expected:
- The edit screen updates inline and preserves the current section/anchor.

## Cross-cutting: Security & access control
### SEC-01 Admin-only route protection
Steps:
1. In a private window (not logged in), attempt to access:
   - `http://localhost:5000/admin`
   - `http://localhost:5000/admin/students`
   - `http://localhost:5000/admin/uploads`
   - `http://localhost:5000/admin/planner`
   - `http://localhost:5000/admin/invitations`
   - `http://localhost:5000/admin/exports`
   - `http://localhost:5000/admin/logs`
2. Attempt to POST to admin actions without a valid admin session.
Expected:
- Admin screens require authentication and do not disclose private data to unauthenticated users.
- POST actions are rejected without a valid admin session and CSRF token.

### SEC-02 Object-level access checks (IDOR)
Steps:
1. As Student A, attempt to access Student B resources:
   - `/participant/upload/preview`
   - `/participant/upload/history/<id>/download`
2. As Teacher A, attempt to download an assignment not assigned to Teacher A.
3. As Delegation Leader, attempt to download a non-delegation student essay (different country).
Expected:
- Requests are rejected (HTTP 403/404) and no cross-user data is leaked.

### SEC-03 Open redirect protection (next parameter)
Steps:
1. Attempt to pass an external URL via the `next` query string on login pages (student/teacher).
Expected:
- The app should ignore unsafe `next` values (e.g. `https://…`) and redirect to a safe internal page.

### SEC-04 Export endpoint protection
Steps:
1. In a private window, attempt to access:
   - `http://localhost:5000/admin/students/export`
   - `http://localhost:5000/admin/teachers/export`
   - `http://localhost:5000/admin/students/cards.pdf`
   - `http://localhost:5000/admin/teachers/cards.pdf`
Expected:
- Export endpoints are restricted to admin users and do not leak personal data to unauthenticated users.

## Automated tests (future)
- Add pytest coverage for core helpers: `_essay_event_state`, `_student_essay_access`, `_apply_stage_one_rules`, `_parse_survey_submission`, `_auto_assign_essays`.
- Add Flask test-client integration tests for the main flows (registration, login, upload/finalize, scoring save/finalize, survey publish/respond, exports access control).
- Use `ipo_app.config.TestConfig` with in-memory SQLite for fast test runs.
