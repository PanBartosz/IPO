from __future__ import annotations

import io
from pathlib import Path

from ipo_app.extensions import db
from ipo_app.models import ActivityLog, StaticPage, StaticPageAttachment


def _create_page(*, slug: str, title: str = "Static page", html_body: str = "<p>Body</p>") -> int:
    page = StaticPage(
        title=title,
        slug=slug,
        html_body=html_body,
        created_by="admin",
        updated_by="admin",
    )
    db.session.add(page)
    db.session.commit()
    return page.id


def _create_attachment_file(app, filename: str, content: bytes) -> Path:
    folder = Path(app.config["STATIC_PAGE_ATTACHMENT_FOLDER"])
    folder.mkdir(parents=True, exist_ok=True)
    file_path = folder / filename
    file_path.write_bytes(content)
    return file_path


def test_admin_can_create_static_page_with_attachment(client, csrf_token):
    with client.session_transaction() as session:
        session["admin_user"] = "admin"

    token = csrf_token(client.get("/admin/static-pages/new"))
    response = client.post(
        "/admin/static-pages/new",
        data={
            "csrf_token": token,
            "title": "Travel details",
            "slug": "travel-details",
            "html_body": "<p>Info for delegates.</p>",
            "attachment": (io.BytesIO(b"%PDF-1.4\nfake-pdf\n"), "travel-info.pdf"),
            "submit": "Save static page",
        },
        content_type="multipart/form-data",
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert response.headers["Location"] == "/admin/static-pages"

    with client.application.app_context():
        page = StaticPage.query.filter_by(slug="travel-details").first()
        assert page is not None
        assert page.title == "Travel details"
        assert page.html_body == "<p>Info for delegates.</p>"
        assert len(page.attachments) == 1
        attachment = page.attachments[0]
        assert attachment.original_filename == "travel-info.pdf"

        file_path = Path(client.application.config["STATIC_PAGE_ATTACHMENT_FOLDER"]) / attachment.stored_filename
        assert file_path.exists()

        log = ActivityLog.query.filter_by(
            action="static_page_created",
            object_type="static_page",
            object_id=str(page.id),
        ).first()
        assert log is not None


def test_admin_static_page_duplicate_slug_is_rejected(client, csrf_token):
    with client.application.app_context():
        _create_page(slug="faq")

    with client.session_transaction() as session:
        session["admin_user"] = "admin"

    token = csrf_token(client.get("/admin/static-pages/new"))
    response = client.post(
        "/admin/static-pages/new",
        data={
            "csrf_token": token,
            "title": "Another FAQ",
            "slug": "faq",
            "html_body": "<p>Duplicate</p>",
            "submit": "Save static page",
        },
        follow_redirects=False,
    )

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "A page with this slug already exists." in html

    with client.application.app_context():
        assert StaticPage.query.filter_by(slug="faq").count() == 1


def test_admin_can_edit_static_page_and_add_attachment(client, csrf_token):
    with client.application.app_context():
        page_id = _create_page(slug="delegation-guide", title="Guide", html_body="<p>v1</p>")

    with client.session_transaction() as session:
        session["admin_user"] = "admin"

    token = csrf_token(client.get(f"/admin/static-pages/{page_id}/edit"))
    response = client.post(
        f"/admin/static-pages/{page_id}/edit",
        data={
            "csrf_token": token,
            "title": "Delegation guide",
            "slug": "delegation-guide-2026",
            "html_body": "<p>Updated content.</p>",
            "attachment": (io.BytesIO(b"Sample attachment"), "guide.txt"),
            "submit": "Save static page",
        },
        content_type="multipart/form-data",
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert response.headers["Location"] == "/admin/static-pages"

    with client.application.app_context():
        page = db.session.get(StaticPage, page_id)
        assert page is not None
        assert page.title == "Delegation guide"
        assert page.slug == "delegation-guide-2026"
        assert page.html_body == "<p>Updated content.</p>"
        assert len(page.attachments) == 1

        log = ActivityLog.query.filter_by(
            action="static_page_updated",
            object_type="static_page",
            object_id=str(page_id),
        ).first()
        assert log is not None


def test_public_static_page_renders_and_serves_attachment(client):
    with client.application.app_context():
        page = StaticPage(
            title="Rules",
            slug="rules",
            html_body="<p>Competition rules.</p>",
            created_by="admin",
            updated_by="admin",
        )
        db.session.add(page)
        db.session.flush()
        attachment = StaticPageAttachment(
            page_id=page.id,
            original_filename="rules.pdf",
            stored_filename="rules-file.pdf",
            content_type="application/pdf",
            file_size=17,
            uploaded_by="admin",
        )
        db.session.add(attachment)
        db.session.commit()

        _create_attachment_file(client.application, "rules-file.pdf", b"%PDF-1.4\nrules\n")
        attachment_id = attachment.id

    page_response = client.get("/pages/rules")
    assert page_response.status_code == 200
    page_html = page_response.get_data(as_text=True)
    assert "Competition rules." in page_html
    assert "rules.pdf" in page_html

    attachment_response = client.get(f"/pages/rules/attachments/{attachment_id}")
    assert attachment_response.status_code == 200
    assert attachment_response.data.startswith(b"%PDF-1.4")

    assert client.get("/pages/missing-slug").status_code == 404


def test_admin_can_delete_static_page_attachment(client, csrf_token):
    with client.application.app_context():
        page_id = _create_page(slug="agenda", title="Agenda")
        attachment = StaticPageAttachment(
            page_id=page_id,
            original_filename="agenda.pdf",
            stored_filename="agenda-file.pdf",
            content_type="application/pdf",
            file_size=10,
            uploaded_by="admin",
        )
        db.session.add(attachment)
        db.session.commit()
        attachment_id = attachment.id

        file_path = _create_attachment_file(client.application, "agenda-file.pdf", b"agenda")

    with client.session_transaction() as session:
        session["admin_user"] = "admin"

    token = csrf_token(client.get(f"/admin/static-pages/{page_id}/edit"))
    response = client.post(
        f"/admin/static-pages/{page_id}/attachments/{attachment_id}/delete",
        data={"csrf_token": token},
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert response.headers["Location"] == f"/admin/static-pages/{page_id}/edit"

    with client.application.app_context():
        assert db.session.get(StaticPageAttachment, attachment_id) is None
        assert db.session.get(StaticPage, page_id) is not None
        assert not file_path.exists()


def test_admin_can_delete_static_page_and_cleanup_attachments(client, csrf_token):
    with client.application.app_context():
        page_id = _create_page(slug="city-map", title="City map")
        attachment = StaticPageAttachment(
            page_id=page_id,
            original_filename="map.pdf",
            stored_filename="map-file.pdf",
            content_type="application/pdf",
            file_size=11,
            uploaded_by="admin",
        )
        db.session.add(attachment)
        db.session.commit()
        file_path = _create_attachment_file(client.application, "map-file.pdf", b"map-content")

    with client.session_transaction() as session:
        session["admin_user"] = "admin"

    token = csrf_token(client.get("/admin/static-pages"))
    response = client.post(
        f"/admin/static-pages/{page_id}/delete",
        data={"csrf_token": token},
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert response.headers["Location"] == "/admin/static-pages"

    with client.application.app_context():
        assert db.session.get(StaticPage, page_id) is None
        assert StaticPageAttachment.query.filter_by(page_id=page_id).count() == 0
        assert not file_path.exists()
