# HTMX opportunities (prioritized)

This is a list of screens where HTMX can replace full page reloads with partial
updates. Priorities are ordered by how annoying a reload is for the end user
(frequency, scroll loss, and wait time).

Priority legend:
- P0: very high annoyance, frequent small actions, long pages
- P1: medium annoyance, periodic actions or lists
- P2: low annoyance or optional

P1 (medium impact)
- Completed.

P2 (low impact or optional)
- `ipo_app/templates/admin/settings.html`
  - Actions: large save form.
  - HTMX: optional section-level save to avoid a full page reload.
- `ipo_app/templates/admin/messages_edit.html`,
  `ipo_app/templates/admin/message_template_form.html`,
  `ipo_app/templates/admin/surveys/question_edit.html`,
  `ipo_app/templates/admin/surveys/publish.html`,
  `ipo_app/templates/admin/surveys/response_detail.html`,
  `ipo_app/templates/admin/communications/new.html`,
  `ipo_app/templates/admin/communications/preview.html`
  - Actions: single form submissions; full reload is usually fine.
- Public and auth flows:
  `ipo_app/templates/register_student.html`,
  `ipo_app/templates/register_teacher.html`,
  `ipo_app/templates/admin/login.html`,
  `ipo_app/templates/student/login.html`,
  `ipo_app/templates/student/reset_request.html`,
  `ipo_app/templates/student/reset_token.html`,
  `ipo_app/templates/teacher_portal/login.html`,
  `ipo_app/templates/teacher_portal/reset_request.html`,
  `ipo_app/templates/teacher_portal/reset_token.html`,
  `ipo_app/templates/teacher_board/login.html`
  - Actions: login/reset/registration; HTMX could show inline validation, but
    impact is low.
- Survey response forms:
  `ipo_app/templates/student/survey_detail.html`,
  `ipo_app/templates/teacher_portal/survey_detail.html`
  - Actions: submit survey; optional autosave with HTMX, but not critical.
- Download-heavy screens:
  `ipo_app/templates/admin/exports.html`,
  `ipo_app/templates/admin/grades/export.html`,
  `ipo_app/templates/admin/stage2/stage3_packets.html`
  - Actions: file generation/download; HTMX adds little value.
- PDF templates:
  `ipo_app/templates/admin/pdf/*`,
  `ipo_app/templates/admin/planner/pdf/*`,
  `ipo_app/templates/admin/grades/pdf/*`
  - No interactive updates; not HTMX targets.


## HTMX implementation approach (short)
- Wrap the swap region in a stable container with an id and
  `data-preserve-scroll="true"`.
- Use `hx-post`/`hx-get` on actions and set `hx-target` + `hx-swap="outerHTML"`to update only that container.
- For HTMX requests (`HX-Request`), render a partial; for full loads render the full template.
- When flashes are needed on HTMX responses, prepend
  `partials/toast_messages.html` with `oob=true`.

## Lessons learned
- `hx-swap-oob="beforeend:#toast-stack"` must be on a wrapper, not the `.toast` root, or the toast loses its styling/animation.
- Keep a single toast system; do not mix "flash" markup with toast markup.
- Preserve scroll via `data-preserve-scroll` on the HTMX swap root; avoid custom auto-scroll hacks.
- HTMX partials should not read flashes directly; the response wrapper should inject the OOB toast markup.
- Boosted requests default to targeting `body`; set `hx-target` explicitly when you want a scoped swap.
