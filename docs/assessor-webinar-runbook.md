# Assessor Webinar Grading Runbook

This runbook is for the live assessor webinar. It deliberately focuses on the grading workflow only: teachers already know how to log in, complete surveys, and use the basic portal navigation.

Use the demo state from `scripts/bootstrap_assessor_webinar.py`. Rerun the bootstrap before the live webinar if you used the same instance for rehearsal, because saving and finalizing scores changes the demo state.

## What Teachers Should Learn

By the end, assessors should know:

1. How to read the teacher dashboard grading statuses.
2. How to download an assigned essay PDF.
3. How to save a draft score.
4. How to finalize a score.
5. What changes after finalization.
6. What blocked states mean: finalized, locked by admin, and awaiting student finalization.
7. How Stage 2 grading differs from Stage 1 in the portal.
8. What to ask admins to do when a score must be reopened.

Do not spend webinar time on surveys, registration, delegation setup, planner internals, or admin configuration except where it explains what assessors see during grading.

## Demo State

The bootstrap creates:

1. Demo teacher account: `demo-assessor / assess-demo-2026`.
2. Published Stage 1 batch: `Assessor webinar demo batch`.
3. Manual demo group: `Webinar Demo Group`.
4. Stage 1 examples for the demo teacher:
   - `Not started`
   - `Draft saved`
   - `Teacher finalized`
   - `Locked by admin`
   - `Awaiting student finalization`
5. Two Stage 2 examples:
   - one `Not started`
   - one `Draft saved`
6. Optional attendee practice accounts when `--attendee-teachers N` is used:
   - usernames like `webinar-teacher-001`
   - passwords like `webinar-pass-001`
   - unscored Stage 1 assignments for hands-on practice

Essay numbers and database IDs are not stable across repeated bootstraps. During the webinar, choose cards by their visible status labels, not by a hard-coded essay number.

## Verified App Behavior

These details were confirmed in Docker with the local MariaDB-backed app and headless Playwright:

1. The teacher dashboard groups work into `Stage 1 assignments`, `Stage 2 assignments`, and status counts.
2. Assignment cards are ordered by essay label, not by workflow status.
3. `Download essay PDF` triggers a browser file download and leaves the teacher on the scoring page.
4. `Save draft` shows `Draft saved.` and keeps the form editable with the entered score and comments.
5. `Finalize score` shows `Score finalized. Thank you!`, then the score and comment fields become read-only and the save/finalize buttons disappear.
6. A finalized score page tells the teacher to contact the admin team to reopen the score.
7. A locked assignment has no download link on the dashboard, shows an admin-lock message on the scoring page, and disables scoring.
8. An assignment awaiting student finalization has no download link, shows an awaiting-finalization message, and disables scoring.
9. The Stage 2 scoring page uses the same controls as Stage 1, with the stage label changed to `Stage 2`.
10. Admin unlock changes the teacher's finalized score back to `Draft saved`; it preserves the existing score and comments and makes the teacher form editable again.

## Corrections From Rehearsal

The real workflow changed the webinar plan in these ways:

1. Do not rely on a "first pending assignment" script. Cards are sorted by essay label, so choose by visible status.
2. Do not describe admin unlock as a reset. It reopens the existing teacher score as `Draft saved`.
3. Do not say locks may still allow downloads. In the tested locked and awaiting-finalization states, the download action was removed.
4. Do not spend time on surveys or message-board mechanics. They are visible on the dashboard, but this webinar should stay on grading.
5. Rerun bootstrap after rehearsal. The demo state changes as soon as you save, finalize, or unlock.

## Tabs To Prepare

Use separate browser profiles for teacher and admin sessions.

Teacher profile:

1. `/teacher/`
2. A `Not started` Stage 1 assignment.
3. A `Teacher finalized` Stage 1 assignment.
4. A `Locked by admin` Stage 1 assignment.
5. An `Awaiting student finalization` Stage 1 assignment.
6. A `Not started` Stage 2 assignment.

Admin profile:

1. `/admin`
2. The score page for the essay you will finalize and unlock.

Do not run `Admin -> Exports -> Teacher portal cards` during preparation unless you intentionally want to rotate all teacher portal passwords, including the demo account.

If attendees will try the system themselves, distribute generated `webinar-teacher-###` accounts. Do not distribute the `demo-assessor` account, because the presenter needs its staged assignment states to remain predictable.

## Suggested 30 Minute Flow

### 0-2 min: Scope

Say:

```text
This session is only about grading: finding assigned essays, downloading PDFs, saving draft scores, finalizing, and knowing what to do when grading is blocked or a correction is needed.
```

Emphasize:

1. Use only the portal download link for essays.
2. Save drafts while working.
3. Finalize only when the score is ready to submit.
4. Contact admins for reopening or blocked assignments.

### 2-5 min: Teacher Dashboard

Open the teacher dashboard and point to:

1. `Stage 1 assignments` counts.
2. `Stage 2 assignments` counts.
3. Card statuses: `Not started`, `Draft saved`, `Teacher finalized`, `Locked by admin`, and `Awaiting student finalization`.
4. The per-card actions: `Download essay` and `Open scoring page`.

Do not explain surveys or message-board workflow beyond saying that operational notices may appear elsewhere on the dashboard.

### 5-12 min: Draft Scoring

Use a `Not started` Stage 1 card.

1. Click `Open scoring page`.
2. Click `Download essay PDF`.
3. Explain that the PDF downloads through the browser and the scoring page stays open.
4. Enter a score, for example `7.6`.
5. Add a short comment.
6. Click `Save draft`.
7. Point out the `Draft saved.` success message.
8. Return to the dashboard and show that the card is now `Draft saved`.

Say:

```text
A draft is visible as progress, but it is still editable. Use drafts while you are reading or double-checking. Do not treat a draft as your final submission.
```

### 12-16 min: Finalization

Use the same draft assignment or another editable assignment.

1. Open the scoring page.
2. Confirm the score and comment.
3. Click `Finalize score`.
4. Show the `Score finalized. Thank you!` message.
5. Point out that score and comments are now disabled.
6. Point out that `Save draft` and `Finalize score` are gone.
7. Return to the dashboard and show `Teacher finalized`.

Say:

```text
Finalized means submitted. If you made a genuine mistake, do not send the score elsewhere. Ask the admin team to reopen the portal score.
```

### 16-20 min: Blocked States

Show three prepared examples.

Finalized:

1. Open a `Teacher finalized` assignment.
2. Show that it is read-only.
3. Repeat that admins can reopen it when needed.

Locked by admin:

1. Open a `Locked by admin` assignment.
2. Show that the dashboard card has no download link.
3. Show the scoring-page admin-lock message.
4. Show that scoring is disabled.

Awaiting student finalization:

1. Open an `Awaiting student finalization` assignment.
2. Show that the dashboard card has no download link.
3. Show the message that grading unlocks after the student finalizes.
4. Explain that the teacher should wait or contact support if the state looks wrong close to the grading window.

### 20-23 min: Stage 2

Open a `Not started` Stage 2 assignment.

1. Point out the `Stage 2` label.
2. Show that download, draft save, and finalization controls are the same as Stage 1.
3. Explain that assessors should follow the same portal discipline: draft while working, finalize only when ready.

Avoid explaining Stage 2 selection rules or planner logic.

### 23-28 min: Admin Reopen Support

Switch to the admin profile only to show what support can do.

1. Open the score page for the essay you finalized.
2. Find the demo teacher row.
3. Show `Portal status: Teacher finalized`.
4. Click `Unlock`.
5. Show the success message `Teacher score unlocked for editing.`
6. Point out that the row changes back to `Draft saved`.
7. Switch back to the teacher profile and reload the same assignment.
8. Show that the score and comments are preserved and editable again.

Say:

```text
Unlock reopens the existing portal score. It is not a blank reset. After admin unlock, the teacher edits the existing draft and finalizes again.
```

### 28-30 min: Closing Checklist

End with this checklist:

1. Find assignments from the teacher dashboard.
2. Download essays only through the portal.
3. Save drafts while working.
4. Finalize only when the score is ready.
5. Treat finalized scores as submitted.
6. Contact admins for locked assignments, missing downloads, wrong assignment state, or a score that needs reopening.

If attendee accounts were distributed, tell participants that those are disposable dev accounts for practice only. They may save or finalize scores there without affecting the presenter demo account.

## Rehearsal Notes

If you rehearse on the same instance:

1. After saving a draft, the `Not started` count decreases.
2. After finalizing, the `Teacher finalized` count increases.
3. After admin unlock, the same assignment returns to `Draft saved`.
4. Rerun the bootstrap before the live webinar if you want the original clean state.

Useful reset command for local Docker:

```bash
docker compose exec -T web python scripts/bootstrap_assessor_webinar.py \
  --yes \
  --base-url http://localhost:5000
```

Use `docker compose run --rm web ...` instead of `exec -T web ...` if the web container is not already running.
