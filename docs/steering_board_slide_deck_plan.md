# Steering Board Slide Deck Plan (IPO App)

This document outlines a **10–15 slide** presentation plan for the steering board, including **what to highlight** and **what screenshots to capture**. You will add the screenshots yourself and drop them into the slides where indicated.

---

## Slide 1 — Purpose & Scope

**Key points**
- End-to-end support for IPO essays: registration, uploads, multi-stage scoring, communication, surveys, exports, audit.
- Web-based system with three interfaces: **Admin panel**, **Student portal**, **Teacher portal**.

**Screenshots to capture**
- A clean “overview” screen: home/landing page, or `Admin → Help` if it summarizes the system well.

---

## Slide 2 — Dashboards (Fast Operational Overview)

**Key points**
- Clean, role-tailored dashboards reduce operational load during the competition window:
  - Students immediately see upload/finalization status and outstanding surveys.
  - Teachers see assignments, what is blocked vs ready, and their own progress.
  - Admin can monitor overall readiness, locks, and workflow state at a glance.
- Designed for “what do I need to do next?” rather than deep navigation.

**Screenshots to capture**
- Student portal dashboard (status cards visible).
- Teacher portal dashboard (assignment table + summary counts visible).
- Optional: an Admin landing/dashboard screen if you have one; otherwise use a representative admin summary page (e.g., Stage 1 list with filters + status columns).

---

## Slide 3 — Roles & Access Model (Governance)

**Key points**
- Roles: **Administrator**, **Student**, **Teacher** (including “delegation leader” as a teacher attribute).
- Governance controls:
  - “Absent” status excludes people from logins/assignments/mailings unless explicitly included.
  - Global module toggles and stage locks restrict what portals can do.

**Screenshots to capture**
- `Admin → Students` list (columns visible: country, presence/absence if shown, etc.).
- `Admin → Teachers` list (show “Delegation leader” column if visible).

---

## Slide 4 — Registration Flow (Step-by-Step, End-to-End)

**Key points**
- Public registration forms exist for both students and teachers.
- Upon acceptance, the system generates **portal credentials** (username/password) and can optionally email them.
- Admin can edit records, reset credentials, and export lists (XLSX).

**Screenshots to capture**
- Student registration form.
- Teacher registration form.
- The confirmation state after submission **or** Admin view showing the newly created record.

---

## Slide 5 — Gender Field (Risk/Clarity: Avoid Unnecessary Controversy)

**Key points**
- Gender is a controlled selection with options:
  - `Female`, `Male`, `Other`, `Prefer not to say`.
- Collected consistently (students and teachers) for reporting/operations, without extra “policy” logic.

**Screenshots to capture**
- Registration form showing the **Gender** dropdown open (options visible).
- Admin list/table view showing the stored gender value.

---

## Slide 6 — Login & Password Reset

**Key points**
- Separate logins for student and teacher portals.
- Password reset uses a **one-time link valid for 24 hours**.

**Screenshots to capture**
- Teacher portal login page (`/teacher/login`).
- Student portal login page (if separate).
- “Forgot password?” / reset request page and the reset-token page (either portal is fine).

---

## Slide 7 — Student Portal (Post-Registration Experience)

**Key points**
- Student sees: upload status (uploaded/finalized + timestamps) and survey status.
- Student can upload/replace PDF until finalization; after finalization, changes are blocked.

**Screenshots to capture**
- Student portal dashboard (tiles/cards for “Essay status” and “Surveys”).

---

## Slide 8 — Essay Upload (Competition Day Workflow)

**Key points**
- Upload constraints: **PDF-only**, size limit, and in-app preview.
- “Finalize” step creates a clear cut-off; after finalization, additional uploads are blocked.
- Admin can disable uploads globally or temporarily lock uploads/finalization.

**Screenshots to capture**
- Student essay upload page **before** finalization (upload widget + preview).
- Finalization confirmation dialog/modal (“Mark essay as finished”).
- Upload page **after** finalization with timestamp.
- Optional: “uploads disabled/locked” banner state.

---

## Slide 9 — Teacher Portal: Assignments & Essay Access

**Key points**
- Teachers see Stage 1 and Stage 2 assignments with statuses (e.g., “Awaiting student finalization”, “Locked”, “Scored”).
- Essay download becomes available only after student finalization and when admin locks permit.

**Screenshots to capture**
- Teacher dashboard listing assignments, with at least one entry showing each of:
  - Awaiting student finalization
  - Download available
  - Locked (if possible)

---

## Slide 10 — Remote Scoring: Draft vs Finalized

**Key points**
- Score entry supports saving drafts and finalizing.
- Score scale is **0–10**; optional comment can be included.
- Locks can pause grading/edits (global or per stage/task).

**Screenshots to capture**
- Teacher assignment detail with scoring form visible (score input + comment).
- A finalized state (show “Finalized” with timestamp).
- Optional: a locked state message if available.

---

## Slide 11 — Admin: Planning & Publishing Assignments (Stage 1/2)

**Key points**
- Assignment configurations: draft vs published; only one active configuration per stage.
- Publishing is the “freeze” point that drives what teachers can see and act on.

**Screenshots to capture**
- `Admin → Planner` (or assignment configuration screen) showing:
  - draft/published state
  - publish action
  - stage selection (Stage 1 vs Stage 2)

---

## Slide 12 — Admin: Scoring Oversight & Stage Progression

**Key points**
- Stage 1 admin view: readers list, add/remove extra reader, unlock finalization, manual adjustments, flags:
  - “Stage 2 candidate”
  - “Needs extra reader”
- Automatic rule logic (as decision support):
  - compute average/spread once complete
  - spread > 3 ⇒ request additional reader
  - average ≥ 7 ⇒ Stage 2 candidate
- Stage 2: assignments, overrides, locks, Stage 3 recommendation.

**Screenshots to capture**
- `Admin → Stage 1` student detail showing readers + scores + flags.
- Optional: `Admin → Stage 2` detail showing recommendation/lock controls.

---

## Slide 13 — Communication & Contact (Organizers ↔ Teachers/Students)

**Key points**
- Teacher message board:
  - publish to all or selected teachers
  - prioritize/categorize
  - archive/restore
- Email campaigns:
  - target audience (students/teachers/both)
  - filters (country, presence)
  - delivery status tracking and retry for failed recipients
- Surveys:
  - build surveys with mixed question types and time windows
  - fill in portals
  - admin review/filter/export responses

**Screenshots to capture**
- `Admin → Communications` showing:
  - teacher messages list + message editor
  - campaign builder/preview (audience selection + filters)
- `Admin → Surveys` list + survey editor.
- Portal survey list (student or teacher) + a survey detail page.

---

## Slide 14 — Results, Post-IPO Access, Exports & Audit

**Key points**
- Reporting:
  - filter by country/stage/recommendations
  - optional anonymization (students/teachers)
  - timestamps included
  - outputs in XLSX/PDF
- Exports:
  - ZIP of essays (including “finalized only” variant)
  - credential cards (student/teacher logins)
  - reader packs for stages
- Audit log:
  - logins, registrations, score changes, publication of assignments, exports
  - filter and CSV export

**Screenshots to capture**
- `Admin → Exports` showing:
  - report options (filters, anonymize toggles)
  - “finalized only” option (if present)
- `Admin → Logs` showing filters and example entries (uploads, score edits, assignment publication).

**Steering-board decision prompt (optional)**
- Student portal currently focuses on upload and surveys; if you want **self-service access to final results** for students/delegation leaders, treat it as a defined roadmap item (scope, permissions, and data visibility rules).

---

## Optional Add-on Slides (if you need 15–16 total)

### Slide 15 — Security & Data Protection (1-slide version)
**Key points**
- Admin panel requires authentication; portals respect lock/presence rules.
- Uploads are restricted to PDF, stored safely (no direct unauthenticated access).
- Audit logging supports traceability of key actions.

**Screenshots to capture**
- Any “Settings” screen with security-related toggles.
- A representative audit-log view filtered to a specific action type.

### Slide 16 — Operational Readiness (Demo Narrative)
**Key points**
- “Competition day” runbook in one minute:
  - enable uploads → students finalize → publish assignments → teachers download/score → locks when needed → export reports/packs.
- What can be handled quickly in support:
  - credential resets
  - correcting registration data
  - handling absent participants

**Screenshots to capture**
- A settings page with upload/portal enable toggles.
- A stage lock/unlock control.
