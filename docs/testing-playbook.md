# IPO Admin Portal – Sequential Test Playbook

A hands-on checklist for exercising every major feature in a realistic order. Work through the steps sequentially: each action sets up the data or state required for the next one. Commands assume you are in the project root and running inside the Docker environment (`docker compose run --rm web …`).

---

## Step 0 – Environment & safety checks
1. **Update code & build images**
   ```bash
   git pull
   docker compose build
   ```
2. **Start database container only (tests run via `docker compose run`)**
   ```bash
   docker compose up -d db
   ```
3. **Ensure `.env` / compose env covers**
   - `DATABASE_URL`, `SECRET_KEY`, `ADMIN_USERS`
   - Persistent `UPLOAD_FOLDER` (default `instance/uploads`)
   - Optional SendGrid keys if email flows are under test
4. **Note admin credentials** from `ADMIN_USERS` (e.g. `admin:dev-password`).

---

## Step 1 – Snapshot database
1. Record current migration state & upgrade (just in case):
   ```bash
   docker compose run --rm web flask db current
   docker compose run --rm web flask db upgrade
   ```
2. Take a backup (adjust command for your DB vendor):
   ```bash
   mysqldump ... > instance/backups/ipo-db-YYYYMMDD-HHMMSS.sql
   ```

---

## Step 2 – Seed mock accounts
1. Populate students & teachers:
   ```bash
   docker compose run --rm web python scripts/seed_mock_data.py --reset
   ```
2. **Admin UI check**
   - Log in at `/admin/login`.
   - Visit **Admin → Students** and **Admin → Teachers**; ensure records exist.

---

## Step 3 – Create Stage 1 batch (manual)
1. Go to **Admin → Planner**.
2. If no Stage 1 batch exists, create one:
   - Click **New batch** → choose *Stage 1* → provide name → save.
3. Add reading groups, members, and assignments as needed.
4. Publish the batch.  
   ✅ Requirement: a published Stage 1 batch must exist before scoring scripts run.

---

## Step 4 – Student portal smoke test
1. Pick one student and reset their upload credentials (**Admin → Students → Actions → Reset upload login**).
2. Log in at `/participant/login` with the supplied username/password.
3. Upload a small PDF manually, preview it, finalize, then confirm a second upload is blocked.
4. Back in **Admin → Stage 1**, confirm the student shows the new timestamp and an audit entry was created.
5. Decide whether to keep this manual essay:
   - If you plan to leave it untouched, skip `--overwrite` or use `--limit` in the next step.
   - If you want the placeholder script to reset everyone (including this student), rerun the upload later.

---

## Step 5 – Attach placeholder essays for remaining students
1. Generate placeholder PDFs (use `--limit`/`--student-id` to avoid overwriting the manual essay if desired):
   ```bash
   docker compose run --rm web python scripts/seed_mock_essays.py --overwrite --finalize
   ```
2. **Verify uploads**
   - **Admin → Stage 1** should list each student as *Finished* (unless you skipped `--finalize` for further portal testing).
   - Spot-check a file via **Scores → Download essay**; ensure the placeholder paragraph fits the page.
   - If you preserved a manually uploaded essay, rerunning the script without `--overwrite` keeps it intact.

---

## Step 6 – Seed Stage 1 scores
1. Run the Stage 1 scoring script (after confirming the batch is published):
   ```bash
   docker compose run --rm web python scripts/seed_stage1_scores.py \
     --overwrite \
     --stage2-target-rate 0.27 \
     --high-spread-rate 0.12 \
     --random-seed 42
   ```
2. **Immediate checks**
   - **Admin → Stage 1** shows `entered/expected` counts populated.
   - Roughly 25–30% students display “Stage 2” status; about 10% flag “Needs extra reader”.
3. **Detailed scoring review**
   - Open a “Needs extra reader” student: confirm reader list, lock toggles, audit behaviour.
   - Unlock a finalized score, adjust value, save → verify logs.

---

## Step 7 – Teacher portal workflow
1. Enable portal (**Admin → Settings → “Enable teacher portal…”**).
2. Generate teacher cards (**Admin → Exports → Teacher portal cards**); inspect credentials.
3. Log in as a teacher at `/teacher/login`:
   - Download assigned packet.
   - Enter a draft Stage 1 score, save, finalize, attempt edit (should be locked).
4. In admin view, unlock the score; have the teacher refresh and edit again to confirm unlock flow.
5. Use the quick message modal to send a note; ensure flash message + log entry appear.

---

## Step 8 – Stage 2 candidate management
1. **Review auto-selected candidates** (**Admin → Stage 2**):
   - Confirm averages/spreads display with two-decimal rounding.
   - Try search/sort via DataTables.
2. Promote a borderline student manually (Stage 1 score page → “Mark as Stage 2 qualified”) and ensure they appear in the Stage 2 list.
3. Assign an extra Stage 2 reader via the Stage 2 score page and enter a test score manually.

---

## Step 9 – Seed Stage 2 scores
1. After manual checks, seed the remaining Stage 2 scores:
   ```bash
   docker compose run --rm web python scripts/seed_stage2_scores.py \
     --overwrite \
     --random-seed 123
   ```
2. Verify:
   - Stage 2 overview shows updated counts/averages.
   - Stage 2 score pages reflect newly populated scores (with finalize/lock behaviour intact).
3. Teacher portal: confirm Stage 2 assignments appear where relevant.

---

## Step 10 – Stage 3 steering packets
1. On a Stage 2 score page, mark several students as “Stage 3 recommended”.
2. Visit **Admin → Stage 2 → Stage 3 packets**:
   - Enter committee members, generate PDF, inspect overlays.
3. Modify recommendations and regenerate to ensure updates flow through.

---

## Step 11 – Grades export scenarios
1. **Standard detailed PDF**: anonymize teachers, include timestamps, Stage 1+2.
2. **Compact PDF/XLSX**: anonymize all, enable compact layout; verify bold averages and landscape orientation.
3. **Country-split workbook**: include countries + group by country; confirm per-country worksheets and compact sheet.
4. **Sort order**: export with `Sort by Stage 2 average` and ensure descending order.

---

## Step 12 – Communications & announcements
1. **Teacher messages**: create, publish, archive, and restore a message; verify display on teacher dashboard.
2. **Communication campaigns**: draft an email targeted at teachers, preview, and (optionally) mark as sent to test recipient status updates.

---

## Step 13 – Survey lifecycle
1. Build a new survey (**Admin → Surveys**), mixing question types; target both teachers and students.
2. Publish the survey; send notifications if email is configured.
3. Complete survey responses as a teacher (portal) and as a student.
4. Review submissions in admin UI and open the response detail view.

---

## Step 14 – Password reset flows
1. **Self-service**: use “Forgot password?” on student login, complete reset, confirm login with new credentials.
2. **Admin-triggered**: reset a teacher password from admin list, note temporary password, verify login, and encourage update.

---

## Step 15 – Audit logs & data exports
1. **Admin → Logs**: filter by recent actions (uploads, score edits, messages), download CSV.
2. **Admin → Exports**: generate latest SQL dump and essay ZIP archive; ensure contents reflect current state.

---

## Step 16 – Cleanup & rerun tips
1. Restore database from backup or rerun `seed_mock_data.py --reset` followed by essay/score scripts with `--overwrite`.
2. Optionally clear generated PDFs:
   ```bash
   rm instance/uploads/student-*.pdf
   ```
3. Collect artefacts (exports, logs, screenshots) for documentation or QA reports.

---

### Quick command reference
```bash
# Seed baseline actors
docker compose run --rm web python scripts/seed_mock_data.py --reset

# Attach essays
docker compose run --rm web python scripts/seed_mock_essays.py --overwrite --finalize

# Stage 1 scores (adjust rates as needed)
docker compose run --rm web python scripts/seed_stage1_scores.py \
  --overwrite --stage2-target-rate 0.27 --high-spread-rate 0.12 --random-seed 42

# Stage 2 scores (after manual checks)
docker compose run --rm web python scripts/seed_stage2_scores.py --overwrite --random-seed 123
```

Keep this playbook handy whenever you need a comprehensive regression of the IPO Admin Portal.
