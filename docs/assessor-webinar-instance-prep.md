# Assessor Webinar Instance Preparation

This checklist prepares a dev or staging instance for a short webinar for IPO assessors. It assumes the app is already deployed through Docker Compose and that you have shell access to the instance.

Use a non-production database. The turn-key bootstrap command below purges participant, planner, scoring, survey, invitation, communication, and teacher-message data before creating the demo state. It preserves runtime settings and message templates unless you explicitly purge activity logs.

This setup was validated against the Docker Compose MariaDB stack with headless Playwright. Prefer a Docker-backed smoke test over a lightweight SQLite-only check, because MariaDB enforces schema details that SQLite may not catch.

## 1. Confirm The Target Instance

1. Confirm the public base URL you will share or screen-share.
2. Confirm you are on the dev/staging host, not production.
3. Confirm the Docker Compose project points at the intended database.
4. Confirm these environment values are set:
   - `DATABASE_URL`
   - `SECRET_KEY`
   - `ADMIN_USERS`
   - `TEACHER_BOARD_PASSWORD`
   - `EMAIL_DEV_FAKE_SEND=1` or no real email automation for the demo

For the local compose setup in this repo, the defaults are:

```bash
docker compose up -d --build
```

The app is then normally available at `http://localhost:5000`.

## 2. Back Up First

For a hosted dev instance, take a database backup before replacing the demo data.

For MariaDB/MySQL, use your normal backup command. The exact command depends on how the database is exposed, but the goal is to keep a dated SQL dump outside the container.

For a local throwaway instance, you can skip this and rely on reseeding.

## 3. Apply Migrations

Run migrations before bootstrapping the demo state:

```bash
docker compose run --rm --entrypoint flask web db upgrade
```

If this fails, stop and fix the migration/deployment issue before the webinar setup.

## 4. Run The Turn-Key Bootstrap

Recommended command when the stack is already running:

```bash
docker compose exec -T web python scripts/bootstrap_assessor_webinar.py \
  --yes \
  --base-url https://your-dev-instance.example.org
```

Use `docker compose run --rm web ...` instead if the web container is not already running:

```bash
docker compose run --rm web python scripts/bootstrap_assessor_webinar.py \
  --yes \
  --base-url https://your-dev-instance.example.org
```

For local development:

```bash
docker compose run --rm web python scripts/bootstrap_assessor_webinar.py \
  --yes \
  --base-url http://localhost:5000
```

If teachers should receive their own hands-on test accounts, add attendee accounts:

```bash
docker compose exec -T web python scripts/bootstrap_assessor_webinar.py \
  --yes \
  --base-url https://your-dev-instance.example.org \
  --attendee-teachers 20 \
  --attendee-credentials-file output/webinar-attendee-credentials.csv
```

Use the fixed `demo-assessor` account for the presenter. Give generated `webinar-teacher-###` accounts to attendees only if you want them to try grading on the dev instance.

What the script does:

1. Purges participant/demo operational data.
2. Seeds realistic mock teachers and students.
3. Marks seeded teachers as assessor-eligible for planning.
4. Creates a fixed demo teacher account.
5. Enables the teacher portal and essay upload module.
6. Generates finalized placeholder essay PDFs.
7. Creates and publishes a Stage 1 batch.
8. Creates a manual "Webinar Demo Group" for the demo teacher.
9. Optionally creates attendee practice teacher accounts and reading groups.
10. Auto-generates the remaining reading groups and assignments.
11. Seeds non-demo Stage 1 scores while leaving attendee accounts unscored.
12. Shapes demo teacher assignments into useful states: not started, draft, finalized, locked, and awaiting student finalization.
13. Adds a small Stage 2 demo state.
14. Adds teacher-board messages and a short teacher survey.
15. Prints the demo credentials, optional attendee credentials, and URLs.

The script does not modify core app code. It uses the existing app factory, models, seed helpers, and planner helpers.

Rerun this command before the live webinar if you used the same instance for rehearsal. The teacher workflow intentionally mutates the demo state when you save drafts, finalize scores, and unlock finalized scores.

## 5. Record The Printed Credentials

The script prints:

```text
Demo teacher: demo-assessor / assess-demo-2026
Teacher board password: ...
Admin usernames from ADMIN_USERS: ...
```

With `--attendee-teachers N`, it also prints `N` attendee accounts such as:

```text
Webinar Teacher 001: webinar-teacher-001 / webinar-pass-001
```

With `--attendee-credentials-file`, the same attendee credentials are written to CSV. Treat that file as temporary dev credentials and delete it after the webinar.

The admin password still comes from `ADMIN_USERS`. In the default local compose setup it is `admin / dev-password`.

Do not run **Admin -> Exports -> Teacher portal cards** after this unless you intentionally want to rotate all teacher portal passwords. That export resets every teacher password, including the demo account.

## 6. Smoke Test The Grading Workflow

Use two separate browser profiles or private windows.

Admin smoke test:

1. Open `/admin/login`.
2. Log in with the admin account.
3. Open Admin -> Dashboard.
4. Verify Stage 1 is open for grading.
5. Verify the dashboard shows a high Stage 1 completion count and the demo teacher in the assessor progress area.

Teacher smoke test:

1. Open `/teacher/login`.
2. Log in as `demo-assessor`.
3. Confirm the dashboard shows Stage 1 and Stage 2 assignments.
4. Confirm Stage 1 has examples for `Not started`, `Draft saved`, `Teacher finalized`, `Locked by admin`, and `Awaiting student finalization`.
5. Open a `Not started` Stage 1 assignment.
6. Click `Download essay PDF` and confirm the browser downloads a PDF.
7. Enter a score and comment, then click `Save draft`.
8. Confirm the page shows `Draft saved.` and remains editable.
9. Click `Finalize score`.
10. Confirm the page shows `Score finalized. Thank you!` and the form becomes read-only.
11. In the admin profile, open that essay's score page and click `Unlock` on the demo teacher row.
12. Return to the teacher profile, reload the assignment, and confirm the score is back to `Draft saved`, still has the entered score/comment, and is editable.
13. Open the locked and awaiting-finalization examples and confirm both disable scoring and remove the download action.
14. Open a Stage 2 assignment and confirm it uses the same grading controls as Stage 1.
15. If attendee accounts were generated, log in with `webinar-teacher-001` and confirm it shows unscored Stage 1 assignments.

Surveys and the teacher board may be present in the demo data, but they are outside the webinar scope for this assessor-grading session.

## 7. Prepare Browser Tabs

Before the webinar, open these tabs:

1. Teacher portal dashboard: `/teacher/`
2. A `Not started` Stage 1 assignment from the demo teacher dashboard.
3. A `Teacher finalized` Stage 1 assignment from the demo teacher dashboard.
4. A `Locked by admin` Stage 1 assignment from the demo teacher dashboard.
5. An `Awaiting student finalization` Stage 1 assignment from the demo teacher dashboard.
6. A `Not started` Stage 2 assignment from the demo teacher dashboard.
7. Admin dashboard: `/admin`
8. Admin score page for the essay you will finalize and unlock.

Keep the admin and teacher sessions in separate browser profiles so that switching roles is clean.

## 8. If The Bootstrap Fails

Common causes:

1. Migrations were not applied.
2. The database container is not reachable from the `web` container.
3. The command was pointed at a real database and refused to purge because `--yes` was omitted.
4. There are not enough seeded students or teachers because `--students` was set too low.
5. The web container is not running but you used `docker compose exec`; use `docker compose run --rm web ...` or start the stack.

Rerun migrations and then rerun the bootstrap command. For a full reset:

```bash
docker compose run --rm web python scripts/bootstrap_assessor_webinar.py \
  --yes \
  --base-url http://localhost:5000
```
