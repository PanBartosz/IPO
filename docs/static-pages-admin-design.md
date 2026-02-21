# Static Pages Admin Module: Design and Implementation Plan

## 1. Goal
Add a simple admin-managed static pages module so organizers can create, edit, and delete rich-text pages and share them by URL.

The pages should:
- be manageable from the admin area,
- use the same rich text editor pattern already used in admin communication,
- be publicly viewable only when someone has a direct URL,
- support optional file attachments (for example PDFs) shown at the bottom of each page,
- render in a clean, branded template.

## 2. Scope
### In scope
- Admin module entry in the admin navigation: `Static pages`.
- CRUD UI for static pages in admin.
- Rich-text editing with TinyMCE.
- Public route for direct-link rendering by slug.
- Basic validation and audit logging.
- Optional file attachments per page (upload/delete, public serving).
- Tests for CRUD + public rendering behavior.

### Out of scope (v1)
- Public listing/index of static pages.
- Page version history.
- Scheduling/publish windows.
- Per-page ACL beyond existing admin/public split.
- HTML sanitization engine (trust admin-authored HTML in v1, same trust model used in existing rich-text areas).

## 3. Existing App Constraints and Conventions
- Stack: Flask, Flask-WTF, SQLAlchemy, Jinja templates, Alembic migrations.
- Admin nav is controlled by `ADMIN_MODULES` in `ipo_app/views.py`.
- Rich text editor already present via TinyMCE in `ipo_app/templates/admin/communications/new.html`.
- Admin auth model: session key `admin_user` and `/admin*` route protection.
- Audit logging convention: `log_activity(...)` + `ActivityLog` table.

## 4. Functional Design
### 4.1 Data model
Add `StaticPage` model in `ipo_app/models.py`.

Proposed fields:
- `id` (PK)
- `title` (`String(200)`, required)
- `slug` (`String(160)`, required, unique, indexed)
- `html_body` (`Text`, required)
- `created_by` (`String(120)`, nullable)
- `updated_by` (`String(120)`, nullable)
- `created_at` / `updated_at` from `TimestampMixin`

Add `StaticPageAttachment` model:
- `id` (PK)
- `page_id` (FK -> `static_pages.id`, cascade delete)
- `original_filename` (`String(255)`, required)
- `stored_filename` (`String(255)`, required, unique)
- `content_type` (`String(120)`, nullable)
- `file_size` (`Integer`, nullable)
- `uploaded_by` (`String(120)`, nullable)
- `created_at` / `updated_at` from `TimestampMixin`

Rationale:
- `slug` provides stable direct URLs.
- `created_by`/`updated_by` aligns with existing auditability style.
- separate attachment records make file lifecycle explicit and auditable.

### 4.2 URL design
- Admin list: `GET /admin/static-pages`
- Admin create: `GET|POST /admin/static-pages/new`
- Admin edit: `GET|POST /admin/static-pages/<int:page_id>/edit`
- Admin delete: `POST /admin/static-pages/<int:page_id>/delete`
- Admin attachment delete: `POST /admin/static-pages/<int:page_id>/attachments/<int:attachment_id>/delete`
- Public page: `GET /pages/<string:slug>`
- Public attachment: `GET /pages/<string:slug>/attachments/<int:attachment_id>`

Why `/pages/<slug>`:
- avoids collisions with existing top-level routes,
- keeps static pages clearly namespaced,
- satisfies “direct link only” (no public index route).

### 4.3 Form design
Add `StaticPageForm` in `ipo_app/forms.py`:
- `title` (`DataRequired`, `Length(max=200)`)
- `slug` (`DataRequired`, `Length(max=160)`)
- `html_body` (`DataRequired`)
- `submit`

Validation rules:
- Normalize slug to lowercase + trimmed.
- Enforce slug format: `^[a-z0-9]+(?:-[a-z0-9]+)*$`
- Enforce slug uniqueness with friendly field error on conflict.

### 4.4 Admin UI design
Templates to add:
- `ipo_app/templates/admin/static_pages/index.html`
- `ipo_app/templates/admin/static_pages/form.html`

Index page:
- Table with: title, slug, updated_at, actions.
- “New static page” button.
- Action links/buttons: edit, delete.
- Attachment count per page.
- Show direct URL preview per row (e.g. `/pages/<slug>`).

Create/edit form:
- Fields: title, slug, body.
- Body uses TinyMCE (`#static-page-editor`) with the same minimal config style as communication compose.
- Attachment upload field (optional).
- Existing attachments list on edit page with delete actions.
- Help text clarifying this content is rendered as page HTML.

Admin nav:
- Add `("Static pages", "web.admin_static_pages")` in `ADMIN_MODULES`.

### 4.5 Public render template
Template to add:
- `ipo_app/templates/static_pages/show.html`

Behavior:
- extend `base.html` for consistent branding,
- render title + rich content in a card container,
- do not expose a public index or discoverability links.

Rendering:
- body rendered with `|safe` (trusted admin-authored HTML model).
- attachments rendered in a dedicated list at the bottom.

### 4.6 Access control and security
- Admin CRUD routes require admin session (`_current_admin()`).
- Public `/pages/<slug>` route is open.
- CSRF on all admin POST actions via Flask-WTF.
- HTML XSS model in v1: trusted admins only; no sanitation layer added yet.

### 4.7 Audit logging
Add activity events:
- `static_page_created`
- `static_page_updated`
- `static_page_deleted`
- `static_page_attachment_added`
- `static_page_attachment_deleted`

Include:
- `object_type="static_page"`
- `object_id`
- key details (`slug`, `title`).

## 5. Technical Implementation Plan
1. **Data layer**
   - Add `StaticPage` and `StaticPageAttachment` models.
   - Create Alembic migration for both tables and attachment indexes.

2. **Form + validation**
   - Add `StaticPageForm`.
   - Add shared slug normalization helper in `views.py` (small local helper).

3. **Admin routes**
   - Add list/create/edit/delete routes in `ipo_app/views.py`.
   - Add unique-slug conflict handling using `IntegrityError` pattern already used elsewhere.
   - Add flash messages and activity logs.

4. **Public route**
   - Add `/pages/<slug>` lookup route.
   - Return `404` if page not found.

5. **Templates + styling**
   - Add admin list and form templates.
   - Add public show template.
   - Add attachment list and upload/delete controls.
   - Add small CSS section for static-page content typography (lists, headings, tables, links, blockquotes) under existing style system.

6. **Admin nav integration**
   - Add module entry to `ADMIN_MODULES`.

7. **Tests**
   - Add `tests/test_admin_static_pages.py`:
     - admin can create/edit/delete page,
     - admin can upload/delete attachments,
     - duplicate slug is rejected,
     - public page resolves by slug,
     - public attachment download works,
     - unknown slug returns 404,
     - activity log entries are written.
   - Update `tests/test_smoke_pages.py` for admin route render (logged in).

8. **Verification**
   - Run targeted tests first, then full test suite if needed.

## 6. UX Notes
- Keep this module intentionally simple and fast to use.
- Keep slug explicit in UI (admins need copyable stable links).
- No WYSIWYG “advanced” plugin set in v1; basic formatting/link/list support is enough.

## 7. Risks and Mitigations
- **Risk:** Admin-authored HTML can inject scripts.
  - **Mitigation (v1):** trusted-admin model; limit admin credentials.
  - **Future option:** whitelist sanitizer if requirements tighten.

- **Risk:** Slug changes can break previously shared links.
  - **Mitigation:** explicit helper text in form (“changing slug changes URL”).
- **Future option:** redirect aliases/history table.

- **Risk:** Attachment files can become orphaned if manually deleted from disk.
  - **Mitigation (v1):** DB-driven links return 404 when missing; deletion endpoints clean up both DB and file.

## 8. Rollout and Backout
### Rollout
- Deploy migration + app changes.
- Create first page in admin and verify direct URL rendering.

### Backout
- Disable nav entry and routes in hotfix if needed.
- Keep table data (non-destructive rollback preferred).

## 9. Acceptance Criteria
- Admin sees `Static pages` in admin nav.
- Admin can create/edit/delete pages with rich text.
- Each page has a stable direct URL under `/pages/<slug>`.
- Pages are not publicly listed anywhere.
- Public page renders in branded template and matches basic styling quality.
- Tests for core behavior pass.
