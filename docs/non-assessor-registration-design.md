# Teacher Non-Assessor Registration: Functional Overview and Low-Risk Implementation Plan

## 1. Goal
Introduce a clear teacher registration option for organization members who should be registered in the system but must not assess essays.

The change must be safe for production:
- minimum change to core logic,
- no role-system rewrite,
- no disruption to existing invitations, login, scoring, and communication flows.

## 2. Constraints and Principles
### Business constraints
- Some users register via the same teacher flow but are operationally non-assessors.
- Regular assessors must keep the current mandatory competence confirmation behavior.
- Non-assessors must never be selected by planner or manual extra-reader assignment.

### Technical constraints
- Prefer reusing existing data model (`Teacher.declared_assessor_competence`) instead of adding new tables or roles.
- Keep the teacher account type unchanged to avoid broad regression risk.
- Enforce all critical behavior server-side; client-side JavaScript is UX-only.

### Safety principles
- Preserve default behavior for existing assessor users.
- Make non-assessor path explicit in UI.
- Keep a one-field source of truth for essay-assessment eligibility.

## 3. Current Baseline (Relevant Existing Behavior)
- Teacher registration uses `TeacherRegistrationForm` and route `register_teacher`.
- `declared_assessor_competence` exists in model and form and is currently required in registration.
- Planner and scoring teacher pools mostly filter on `is_absent` and language/country eligibility.
- Extra reader assignment already calls `_teacher_can_grade(...)`.
- Auto-group planner currently does not filter by assessor competence.

Implication: non-assessors can be represented as teachers with `declared_assessor_competence=False`, but assignment entry points must consistently enforce that.

## 4. Proposed Functional Overview
### 4.1 User-facing behavior
Add a new registration checkbox:
- Label: `I am registering as a non-assessing member (I will not assess essays).`
- Form field name (proposed): `non_assessor` (transient form field, not stored as a DB column).

Behavior:
- Default unchecked.
- When unchecked:
  - current assessor path remains unchanged,
  - competence declaration remains required.
- When checked:
  - assessor-specific section is visually hidden/disabled in the form,
  - server stores teacher as non-assessor (`declared_assessor_competence=False`),
  - teacher can still use normal teacher account capabilities not tied to essay assessment.

### 4.2 Dynamic form behavior (UX)
- Add a small script to `register_teacher.html` to react to `non_assessor` checkbox changes.
- When `non_assessor` is checked:
  - hide/disable assessor competence consent UI block,
  - optionally lock `prior_ipo_assessor_level` to `0` (recommended for data consistency).
- When unchecked:
  - restore current assessor UI and required state.

Important:
- Do not rely on this script for security/validation.
- Server-side validation and save rules are mandatory and authoritative.

### 4.3 Server-side validation matrix
Use conditional validation in the form/view:

Case A: `non_assessor=False`
- `declared_assessor_competence` must be true.
- If false/missing, return validation error.
- Existing required consents remain as-is.

Case B: `non_assessor=True`
- Skip assessor competence requirement.
- Force persisted values:
  - `declared_assessor_competence=False`
  - `declared_assessor_competence_at=None`
  - `prior_ipo_assessor_level=0` (recommended normalization)
  - `prior_ipo_assessor=False` (derived from level).

This ensures resilience against forged POST payloads.

### 4.4 Assignment eligibility
Treat `declared_assessor_competence` as the assessment eligibility flag.

Rules:
- Only teachers with `declared_assessor_competence=True` are eligible for:
  - auto-generated planner group membership,
  - manual planner member options,
  - Stage 1 extra reader options,
  - Stage 2 extra reader options,
  - `_teacher_can_grade(...)` pass.
- Existing assignment records remain valid; feature is forward-safe.

## 5. Detailed Implementation Plan
### 5.1 Forms (`ipo_app/forms.py`)
1. Extend `TeacherRegistrationForm`:
   - add `non_assessor = BooleanField(...)`.
2. Move strict assessor requirement from static `InputRequired()` into conditional form validation:
   - implement `validate(self, extra_validators=None)` override, or
   - custom `validate_declared_assessor_competence` with access to `non_assessor`.
3. Keep all other existing field validators unchanged unless explicitly required by the non-assessor path.

Expected effect:
- assessor users keep current mandatory declaration,
- non-assessor users can submit without assessor declaration.

### 5.2 Registration route (`ipo_app/views.py`, `register_teacher`)
1. Read `form.non_assessor.data`.
2. Derive persisted competence values from this flag server-side:
   - if non-assessor -> force false + null timestamp.
   - else -> use current assessor behavior.
3. Normalize veteran/assessor experience fields if non-assessor is checked.
4. Keep invite flow, credentials generation, and confirmation email behavior unchanged.

Expected effect:
- no change to invite semantics,
- clear and deterministic save behavior.

### 5.3 Registration template (`ipo_app/templates/register_teacher.html`)
1. Add new checkbox block for `form.non_assessor`.
2. Wrap assessor-specific UI block with a stable container id/class.
3. Add small inline script (or existing JS bundle hook) to toggle visibility/disabled state.
4. Ensure accessibility:
   - labels remain connected,
   - hidden fields are not focus-trapped,
   - no required-only-in-UI assumptions.

Expected effect:
- explicit UX for non-assessing members,
- predictable behavior with and without JS.

### 5.4 Eligibility enforcement in assignment/planner flows (`ipo_app/views.py`)
Apply consistent filtering where teacher pools are built:

1. `_teacher_can_grade(student, teacher, language)`:
   - add guard: `teacher.declared_assessor_competence is True`.
2. `_planner_teacher_choices(...)`:
   - include only assessors.
3. `_auto_generate_groups_for_batch(...)` teacher query:
   - include only assessors.
4. Stage 1 and Stage 2 available extra-reader queries:
   - include only assessors before calling `_teacher_can_grade`.
5. Batch detail available teacher maps:
   - include only assessors to avoid accidental manual group additions.

Expected effect:
- single operational rule applied consistently across assignment entry points.

### 5.5 Optional admin visibility improvement (recommended)
In admin teachers table, add a clear status indicator:
- `Assessor: Yes/No`

Purpose:
- operational clarity,
- easier support and troubleshooting.

This is optional and does not alter logic.

### 5.6 Existing data impact and one-time audit
No data migration is required, but existing records should be audited once after rollout.

Recommended checks:
1. List teachers with `declared_assessor_competence=False` and verify they are intended non-assessors.
2. Verify no unintended non-assessor is already active in assessment groups.
3. If needed, manually replace unintended non-assessor group members before publishing new batches.

## 6. Files Expected to Change
- `ipo_app/forms.py`
- `ipo_app/views.py`
- `ipo_app/templates/register_teacher.html`
- `ipo_app/templates/admin/teachers.html` (optional UI visibility)
- tests:
  - `tests/test_open_registration.py`
  - `tests/test_invite_acceptance.py`
  - `tests/test_teacher_portal_assignments.py` or planner/scoring tests as appropriate

No migration required in the preferred implementation.

## 7. Test Plan
### 7.1 Registration validation tests
1. Assessor path (default):
   - submit without `non_assessor`,
   - missing competence declaration -> validation error.
2. Assessor path valid:
   - declaration provided -> teacher created with competence true.
3. Non-assessor path:
   - `non_assessor=y`, no competence declaration -> success,
   - persisted competence false and timestamp null,
   - persisted prior assessor level normalized to 0 (if chosen).

### 7.2 Invite-based teacher registration tests
1. Invite + assessor path works exactly as before.
2. Invite + non-assessor path persists non-assessor state and still accepts invite.

### 7.3 Planner/assignment safety tests
1. Non-assessor excluded from auto-group generation candidate pool.
2. Non-assessor excluded from manual planner teacher choices.
3. Non-assessor excluded from Stage 1 extra-reader dropdown.
4. Non-assessor excluded from Stage 2 extra-reader dropdown.
5. Direct POST attempts to add non-assessor reader are rejected by server check.

### 7.4 Regression smoke checks
- Existing teacher registration happy-path unchanged.
- Existing scoring and portal login unaffected.
- Existing invitation acceptance unaffected.

## 8. Rollout Strategy
1. Deploy code changes without migration.
2. Run targeted tests and manual smoke tests:
   - `/register/teacher` assessor and non-assessor variants,
   - planner available teacher lists,
   - Stage 1/2 add reader actions.
3. Monitor for 24h:
   - registration error rates,
   - planner assignment anomalies.

## 9. Backout Strategy
If issues appear:
1. Remove non-assessor UI checkbox and conditional validation logic.
2. Revert eligibility filter additions in planner/scoring entry points.
3. Keep persisted data untouched (teachers with competence false remain safe and non-breaking).

No database rollback required.

## 10. Acceptance Criteria
- A teacher can explicitly register as non-assessor from the registration form.
- Non-assessor registration does not require assessor competence confirmation.
- Regular assessor registration still requires competence confirmation exactly as before.
- Non-assessors cannot be selected for essay assessment in planner or extra-reader flows.
- No schema migration is needed and no existing role/authentication flow is changed.
