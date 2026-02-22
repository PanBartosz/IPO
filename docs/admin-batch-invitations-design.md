# Admin Batch Invitations (CSV/XLSX): Design and Implementation Plan

## 1. Goal
Add an **admin-only** batch invitation feature that supports uploading CSV/XLSX files for:
- delegation leader invites,
- delegation invites,
- normal invites.

The batch flow must:
- use the **same invite creation + email sending mechanism** as current single-row admin invites,
- provide a **preview/dry-run** step before any invite is created,
- be safe and hard to misuse,
- preserve all existing invitation workflows (no replacement, only additive).

## 2. Requirements and Constraints
### Functional requirements
- Available in Admin panel (`/admin/invitations`) only.
- Not available in teacher/delegation leader portal invite screens.
- Accept `.csv` and `.xlsx` files.
- Support 3 batch modes: `delegation_leader`, `delegation`, `normal`.
- Dry-run preview must show row-by-row outcomes and summary counts.
- Final execution must create invites and send emails using existing tested logic.

### Non-functional requirements
- Do not break existing routes/forms/UI for single invites.
- Preserve existing invite/audit semantics.
- Handle large but realistic files safely (limits, validation, clear errors).
- Be idempotent against accidental double-submit.

## 3. Current Baseline (Existing System)
Current invitation flow is in `ipo_app/views.py`:
- `POST /admin/invitations/delegation-leader`
- `POST /admin/invitations/delegation`
- `POST /admin/invitations/normal`

All 3 create `DelegationInvite` rows and send email through:
- `_send_delegation_invite_email(invite, inviter)`

Current data model:
- `DelegationInvite` in `ipo_app/models.py`

Current forms:
- `DelegationLeaderInviteForm`
- `AdminDelegationInvitationForm`
- `AdminInvitationForm`

Admin invitation UI:
- `ipo_app/templates/admin/partials/invitations_content.html`
- tabbed view rendered by `ipo_app/templates/admin/invitations.html`

Important behavioral rules already implemented and must be preserved:
- Email is lowercased/trimmed.
- Existing registered participant checks (`Student`/`Teacher`).
- Existing active invite checks (`_active_invite_for_email`).
- Delegation invite uses selected leader country.
- Same auto-email behavior (`_auto_email_enabled()` + `_send_delegation_invite_email`).

## 4. Scope
### In scope
- New batch upload tab/section in admin invitations.
- Batch preview (dry-run) and batch execute steps.
- CSV/XLSX parsing and schema validation.
- Reuse of existing invitation creation/email path.
- Batch summary + row-level result visibility.
- Tests for parser, preview, execute, regressions.

### Out of scope (v1)
- Teacher portal batch invites.
- Background job queue for sending (execution stays synchronous like current flow).
- Editing rows in UI after upload (fix in file and re-upload instead).
- New email templates specifically for batch mode.

## 5. UX Design
### 5.1 Entry point
Keep existing single-invite tabs unchanged. Add a 4th tab: `Batch upload`.

### 5.2 Batch upload form
Fields:
- `Batch type` (`delegation_leader`, `delegation`, `normal`)
- `File` (`.csv`, `.xlsx`)
- `Submit` button: `Validate and preview`

Helper actions:
- `Download template CSV`
- `Download template XLSX`

### 5.3 Dry-run preview screen (same page)
Show:
- file metadata (name, mode, row count),
- summary counters:
  - ready to create,
  - validation errors,
  - duplicates/registered skips,
  - rows that would send email,
  - rows that would create invite but not send because auto-email is disabled,
- row table with:
  - source row number,
  - normalized input values,
  - outcome (`ready`, `skip`, `error`),
  - detailed reason.

Actions:
- `Execute batch` (enabled only when at least one row is ready).
- `Discard preview`.

### 5.4 Execute result
After execute, show:
- created invites count,
- email sent count,
- email failed count,
- skipped count,
- row-level final statuses.

## 6. File Format and Validation
### 6.1 Common parsing rules
- Header row must exist in row 1.
- Header normalization: lowercase, trim, spaces/hyphens to underscore.
- Empty trailing rows are ignored.
- Required fields cannot be blank.
- Names are trimmed; email is trimmed + lowercased.
- CSV decoding order: UTF-8 BOM, UTF-8, fallback ISO-8859-1 with warning.
- XLSX: read first worksheet only.

Safety limits (configurable constants):
- max file size: 2 MB,
- max rows: 1000,
- max cell length: 500.

### 6.2 Required columns by batch type
| Batch type | Required columns |
|---|---|
| `delegation_leader` | `first_name`, `last_name`, `email`, `country` |
| `delegation` | `first_name`, `last_name`, `email`, `role`, `delegation_leader_email` |
| `normal` | `first_name`, `last_name`, `email`, `role`, `country` |

Role parsing:
- accepted values: `student`, `teacher` (case-insensitive).

Delegation mode specifics:
- `delegation_leader_email` must resolve to an existing `Teacher` with `delegation_leader=True`.
- Country is derived from resolved leader (not from file).

### 6.3 Row validation outcomes
Row status categories:
- `ready`: can be executed.
- `skip`: valid input but business rule blocks creation (already registered, duplicate active invite, invalid leader reference).
- `error`: invalid input format/schema (missing required field, invalid email, unknown role, etc.).

## 7. Architecture and Code Changes
### 7.1 Reuse existing invite/email mechanism
Introduce internal service-level helpers that become the single source of truth for admin invite creation logic.

Proposed helpers (in `ipo_app/views.py` or extracted service module):
- `_admin_prepare_invite_request(...)`
- `_admin_validate_invite_business_rules(...)`
- `_admin_create_invite_and_send(...)`

Behavior:
- Existing single-row routes call these helpers.
- Batch execute calls the same helpers.
- Email sending remains `_send_delegation_invite_email(...)` only.

This guarantees batch uses exactly the same mechanism as current tested invites.

### 7.2 Batch draft persistence
Add persistent batch draft records so preview and execute are separated safely.

New model: `InvitationBatchDraft`
- `id` (PK)
- `created_by` (`String(120)`)
- `batch_type` (`String(32)`)
- `source_filename` (`String(255)`)
- `file_sha256` (`String(64)`)
- `status` (`String(20)`: `preview`, `executing`, `executed`, `discarded`)
- `total_rows`, `ready_rows`, `skip_rows`, `error_rows`
- `result_payload` (`JSON`) row-level preview and execution result data
- `executed_at` (`DateTime`, nullable)
- `created_at`/`updated_at`

Reasoning:
- avoids storing large preview payload in client session cookies,
- supports idempotent execute,
- keeps auditability and reproducibility of what was previewed.

Retention:
- cleanup old drafts (e.g., older than 14 days) opportunistically on admin invitation page load.

### 7.3 Routes
Add routes:
- `POST /admin/invitations/batch/preview`
- `POST /admin/invitations/batch/<int:draft_id>/execute`
- `POST /admin/invitations/batch/<int:draft_id>/discard`
- `GET /admin/invitations/batch/template/<string:batch_type>.<string:fmt>`

All routes:
- require `_current_admin()`.
- use CSRF-protected Flask-WTF forms.

No routes added under teacher portal.

### 7.4 Forms
Add forms in `ipo_app/forms.py`:
- `AdminInvitationBatchUploadForm`
  - `batch_type` select
  - `file` file field
  - `submit_preview`
- `AdminInvitationBatchExecuteForm`
  - hidden `draft_id`
  - confirmation checkbox
  - `submit_execute`

### 7.5 Templates
Update:
- `ipo_app/templates/admin/partials/invitations_content.html`
  - add `Batch upload` tab panel
  - render upload form
  - render preview/results panel

Potentially add partial:
- `ipo_app/templates/admin/partials/invitation_batch_preview.html`

Update tab JS in:
- `ipo_app/templates/admin/invitations.html`
  - include `batch` tab in keyboard/click flow (existing generic logic already supports additional tab ids).

### 7.6 Logging and audit
Keep existing per-invite logs (`invitation_created`).
Add batch-level logs:
- `invitation_batch_previewed`
- `invitation_batch_executed`
- `invitation_batch_discarded`

Batch log details:
- `batch_type`, `source_filename`, `total_rows`, `ready_rows`, `executed_rows`, `created_invites`, `email_sent`, `email_failed`.

## 8. Preview and Execute Algorithms
### 8.1 Preview (dry-run)
1. Validate form + file type/size.
2. Parse rows based on file format.
3. Normalize headers/values.
4. For each row, run:
   - schema validation,
   - business validation mirroring single-row routes.
5. Build row outcomes and summary counters.
6. Persist `InvitationBatchDraft(status='preview')`.
7. Render preview results.

Guarantee:
- no `DelegationInvite` insert,
- no email send,
- no side effects except batch draft persistence + audit log.

### 8.2 Execute
1. Load draft by id and admin owner.
2. Ensure status is `preview` (prevent duplicate runs).
3. Mark status `executing`.
4. Process only rows marked `ready` in preview.
5. For each row, run creation helper with normal send path.
6. Record per-row final outcomes in `result_payload`.
7. Mark draft `executed` with final counters.
8. Commit and render final summary.

Runtime safety:
- Re-check business rules at execution time (data may have changed since preview).
- If row becomes invalid meanwhile, mark as skipped/error and continue.

## 9. Foolproof Safeguards
- Explicit templates per batch mode.
- Strict schema validation with row numbers and concrete errors.
- Duplicate detection inside uploaded file (`email + role + mode` per batch).
- Prevent execute with zero ready rows.
- Execute idempotency via draft status transition.
- Clear warning when auto-email is disabled.
- Hard limits for rows/file size.
- Keep single invite forms untouched and still first-class.

## 10. Regression-Safe Delivery Strategy
Implement in phases:

1. **Refactor-only phase**
- Extract existing admin single-invite logic into shared helper(s).
- Verify existing invitation tests still pass unchanged.

2. **Batch preview phase**
- Add parser + upload UI + preview only.
- No execute yet.
- Test dry-run correctness.

3. **Batch execute phase**
- Add execute route and final result reporting.
- Ensure helper path is reused for creation + email.

4. **Hardening phase**
- Add row/file limits, stale draft cleanup, idempotency guard.
- Add extra tests for malformed files and race-like state changes.

## 11. Testing Plan
### 11.1 New tests
Add `tests/test_admin_invitation_batch.py` covering:
- admin-only access (403 without admin session),
- CSV preview success for all 3 modes,
- XLSX preview success for all 3 modes,
- dry-run creates no `DelegationInvite` rows,
- execute creates expected invites,
- execute uses same email path (mock `_send_delegation_invite_email`),
- delegation mode leader resolution by email,
- duplicate active invite handling,
- already registered participant handling,
- invalid headers / missing columns,
- max-row/max-size limit handling,
- execute idempotency (second execution blocked/no-op).

### 11.2 Regression tests
- Keep and run existing invitation tests (`tests/test_invitations.py`).
- Update CSRF coverage in `tests/test_csrf.py` for new batch POST endpoints.
- Confirm teacher portal delegation invite flows unchanged.

### 11.3 Manual verification
- Admin single invite tabs still behave exactly as before.
- Batch preview with mixed valid/invalid rows is understandable.
- Execute result counts match DB state and UI list updates.
- Auto-email disabled scenario shows manual-share warning.

## 12. Migration Plan
Add Alembic migration:
- create `invitation_batch_drafts` table,
- indexes on `created_by`, `status`, `created_at`.

No migration to existing invitation tables required.

## 13. Rollout and Backout
### Rollout
- Deploy migration + app code.
- Smoke-test single invites.
- Smoke-test one small batch per mode in staging.

### Backout
- Hide/remove batch tab and routes.
- Keep existing single routes untouched.
- `invitation_batch_drafts` table can remain (non-breaking) until cleanup migration.

## 14. Acceptance Criteria
- Admin can upload CSV/XLSX and preview batch invites for all 3 modes.
- Preview is true dry-run (no invites, no emails sent).
- Execute sends invites using the same mechanism as existing normal invites.
- Feature is admin-only; teacher/delegation leader portal flows are unchanged.
- Existing single invite workflow remains intact.
- Automated tests for batch + invitation regressions pass.
