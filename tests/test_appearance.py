from copy import deepcopy
from datetime import date
from io import BytesIO
import json
from pathlib import Path

from PIL import Image, PngImagePlugin
from pypdf import PdfReader
import pytest

from ipo_app import appearance
from ipo_app.extensions import db
from ipo_app.models import (
    ActivityLog,
    AppSetting,
    AssignmentBatch,
    PlannerStatus,
    Stage,
    Student,
)
import ipo_app.views as views


def _admin(client):
    with client.session_transaction() as session:
        session["admin_user"] = "admin"


def _payload(token, **changes):
    values = deepcopy(appearance.DEFAULTS)
    values.update(changes)
    result = {"csrf_token": token}
    for key, value in values.items():
        if key in {"logos", "partners"}:
            continue
        if isinstance(value, bool):
            if value:
                result[key] = "y"
        else:
            result[key] = value
    return result


def _png(*, size=(24, 16), format="PNG"):
    output = BytesIO()
    image = Image.new("RGBA", size, (31, 96, 130, 128))
    if format == "JPEG":
        image = image.convert("RGB")
    metadata = PngImagePlugin.PngInfo()
    metadata.add_text("Private metadata", "discard this")
    image.save(output, format=format, pnginfo=metadata if format == "PNG" else None)
    output.seek(0)
    return output


def _token(client, csrf_token):
    _admin(client)
    return csrf_token(client.get("/admin/settings/appearance"))


def test_unconfigured_appearance_uses_original_identity_without_writing_settings(
    client,
):
    response = client.get("/")
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "IPO Warsaw 2026" in html
    assert "Welcome to the IPO registration portal" in html
    assert "Please choose the appropriate registration form." in html
    for image in [
        "img/ipo-warsaw-2026/6c.png",
        "img/ipo-warsaw-2026/7.png",
        "img/ptf-logo.png",
        "img/uw-logo.png",
        "img/wfz-logo.png",
        "img/ministry-logo.png",
    ]:
        assert f"/static/{image}" in html
    assert "--brand-purple: #822D80" in html
    assert "--brand-magenta: #E14CE1" in html
    assert "--brand-orange: #DE743B" in html
    with client.application.app_context():
        assert AppSetting.query.count() == 0
        assert appearance.get_config() == appearance.DEFAULTS


def test_saving_defaults_preserves_all_original_values(client, csrf_token):
    token = _token(client, csrf_token)
    response = client.post("/admin/settings/appearance", data=_payload(token))
    assert response.status_code == 302
    with client.application.app_context():
        assert appearance.get_config() == appearance.DEFAULTS
        assert ActivityLog.query.filter_by(action="appearance_updated").count() == 1


@pytest.mark.parametrize("role", [None, "teacher"])
def test_appearance_panel_requires_admin(client, role):
    if role:
        with client.session_transaction() as session:
            session["teacher_portal_id"] = 1
    response = client.get("/admin/settings/appearance")
    assert response.status_code == 302
    assert response.headers["Location"].startswith("/admin/login")


@pytest.mark.parametrize(
    "path",
    [
        "/admin/settings/appearance",
        "/admin/settings/appearance/logos/header",
        "/admin/settings/appearance/partners",
        "/admin/settings/appearance/reset",
    ],
)
def test_appearance_mutations_require_csrf(client, path):
    _admin(client)
    assert (
        client.post(
            path, data={"action": "remove", "partner_id": "ptf", "confirm_reset": "yes"}
        ).status_code
        == 400
    )


def test_identity_palette_and_layout_are_saved_for_public_pages(client, csrf_token):
    token = _token(client, csrf_token)
    response = client.post(
        "/admin/settings/appearance",
        data=_payload(
            token,
            edition_name="IPO Lisbon 2028",
            browser_title="Lisbon Olympiad",
            tagline="Welcome to Portugal",
            hero_title="Meet the next edition",
            hero_intro="A new host.\nThe same Olympiad.",
            primary="#164e63",
            accent="#0f766e",
            highlight="#2563eb",
            page_background="#F4F8FA",
            heading_font="serif",
            body_font="system",
            corners="square",
            gradient_enabled=False,
            contact_email="ipo@example.com",
            contact_url="https://ipo.example.test",
            footer_note="Hosted in Lisbon.",
        ),
    )
    assert response.status_code == 302
    html = client.get("/").get_data(as_text=True)
    assert "<title>Lisbon Olympiad</title>" in html
    assert "IPO Lisbon 2028" in html and "Welcome to Portugal" in html
    assert "Meet the next edition" in html
    assert "--brand-purple: #164E63" in html
    assert "--brand-gradient: #164E63" in html
    assert "--radius-lg: 8px" in html
    assert 'href="mailto:ipo@example.com"' in html
    assert 'href="https://ipo.example.test"' in html
    with client.application.app_context():
        assert appearance.get_config()["partners"] == appearance.DEFAULT_PARTNERS


@pytest.mark.parametrize(
    "changes",
    [
        {"primary": "red"},
        {"accent": "#123456; color:red"},
        {"heading_font": "serif;}</style><script>alert(1)</script>"},
        {"contact_url": "javascript:alert(1)"},
        {"header_logo_width": "900"},
    ],
)
def test_invalid_appearance_is_rejected_atomically(client, csrf_token, changes):
    token = _token(client, csrf_token)
    response = client.post(
        "/admin/settings/appearance",
        data=_payload(token, edition_name="Do not save", **changes),
    )
    assert response.status_code == 400
    with client.application.app_context():
        assert appearance.get_config() == appearance.DEFAULTS
        assert ActivityLog.query.count() == 0


def test_public_identity_text_is_escaped_and_printed_password_is_not_public(
    client, csrf_token
):
    token = _token(client, csrf_token)
    response = client.post(
        "/admin/settings/appearance",
        data=_payload(
            token,
            edition_name='<script>alert("x")</script>',
            footer_note='<img src=x onerror="alert(1)">',
            wifi_password="private-card-only-password",
        ),
    )
    assert response.status_code == 302
    html = client.get("/").get_data(as_text=True)
    assert '<script>alert("x")</script>' not in html
    assert '<img src=x onerror="alert(1)">' not in html
    assert "&lt;script&gt;" in html
    assert "private-card-only-password" not in html


def test_corrupt_or_tampered_stored_config_cannot_inject_css_urls_or_paths(client):
    with client.application.app_context():
        db.session.add(
            AppSetting(
                key=appearance.SETTING_APPEARANCE,
                value=json.dumps(
                    {
                        "primary": "#123456;}</style><script>alert(1)</script>",
                        "body_font": "evil-font",
                        "contact_url": "javascript:alert(1)",
                        "logos": {
                            "header": {"filename": "../../.env", "hidden": False}
                        },
                        "partners": [
                            {"id": "evil", "name": "evil", "static": "../../.env"}
                        ],
                    }
                ),
            )
        )
        db.session.commit()
    html = client.get("/").get_data(as_text=True)
    assert "--brand-purple: #822D80" in html
    assert (
        "evil-font" not in html
        and "javascript:" not in html
        and "../../.env" not in html
    )
    assert "/static/img/ipo-warsaw-2026/6c.png" in html


@pytest.mark.parametrize(
    "format,suffix", [("PNG", "png"), ("JPEG", "jpg"), ("WEBP", "webp")]
)
def test_logo_upload_is_normalized_and_available_to_public(
    client, csrf_token, format, suffix
):
    token = _token(client, csrf_token)
    response = client.post(
        "/admin/settings/appearance/logos/header",
        data={
            "csrf_token": token,
            "action": "upload",
            "image": (_png(format=format), f"custom.{suffix}"),
        },
    )
    assert response.status_code == 302
    with client.application.app_context():
        filename = appearance.get_config()["logos"]["header"]["filename"]
        assert appearance.IMAGE_NAME.fullmatch(filename)
    public = client.application.test_client()
    response = public.get(f"/branding/assets/{filename}")
    assert response.status_code == 200
    assert response.mimetype == "image/png"
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert "immutable" in response.headers["Cache-Control"]
    with Image.open(BytesIO(response.data)) as image:
        assert image.size == (24, 16) and image.mode == "RGBA"
        assert "Private metadata" not in image.info
        if format == "PNG":
            assert image.getpixel((0, 0))[3] == 128
    assert f"/branding/assets/{filename}" in public.get("/").get_data(as_text=True)


def test_invalid_oversize_and_excessive_pixel_images_are_rejected(
    client, csrf_token, monkeypatch
):
    token = _token(client, csrf_token)
    for data in [
        BytesIO(b"<svg><script>alert(1)</script></svg>"),
        BytesIO(b"not an image"),
    ]:
        response = client.post(
            "/admin/settings/appearance/logos/header",
            data={"csrf_token": token, "action": "upload", "image": (data, "logo.png")},
        )
        assert response.status_code == 400
    monkeypatch.setattr(appearance, "MAX_IMAGE_PIXELS", 100)
    response = client.post(
        "/admin/settings/appearance/logos/header",
        data={"csrf_token": token, "action": "upload", "image": (_png(), "logo.png")},
    )
    assert response.status_code == 400
    monkeypatch.setattr(appearance, "MAX_IMAGE_BYTES", 20)
    response = client.post(
        "/admin/settings/appearance/logos/header",
        data={"csrf_token": token, "action": "upload", "image": (_png(), "logo.png")},
    )
    assert response.status_code == 400
    with client.application.app_context():
        assert appearance.get_config()["logos"] == appearance.DEFAULTS["logos"]


def test_logo_can_be_hidden_and_restored_independently(client, csrf_token):
    token = _token(client, csrf_token)
    response = client.post(
        "/admin/settings/appearance/logos/header",
        data={"csrf_token": token, "action": "hide"},
    )
    assert response.status_code == 302
    assert 'class="brand-logo"' not in client.get("/").get_data(as_text=True)
    response = client.post(
        "/admin/settings/appearance/logos/header",
        data={"csrf_token": token, "action": "reset"},
    )
    assert response.status_code == 302
    assert "/static/img/ipo-warsaw-2026/6c.png" in client.get("/").get_data(
        as_text=True
    )


@pytest.mark.parametrize(
    "filename", [".env", "../.env", "%2e%2e%2f.env", "abc.png", "0" * 32 + ".png"]
)
def test_brand_assets_do_not_expose_other_files(client, filename):
    assert client.get(f"/branding/assets/{filename}").status_code == 404


def test_partner_creation_order_visibility_removal_and_restore(client, csrf_token):
    token = _token(client, csrf_token)
    response = client.post(
        "/admin/settings/appearance/partners",
        data={
            "csrf_token": token,
            "action": "save",
            "name": "Future Sponsor",
            "label": "Supported by",
            "website": "https://sponsor.example.test",
            "enabled": "y",
            "image": (_png(), "partner.png"),
        },
    )
    assert response.status_code == 302
    with client.application.app_context():
        partner_id = appearance.get_config()["partners"][-1]["id"]
    html = client.get("/").get_data(as_text=True)
    assert 'href="https://sponsor.example.test"' in html and "Supported by" in html
    assert html.index('alt="Ministry logo"') < html.index('alt="Future Sponsor"')
    response = client.post(
        "/admin/settings/appearance/partners",
        data={"csrf_token": token, "action": "up", "partner_id": partner_id},
    )
    assert response.status_code == 302
    html = client.get("/").get_data(as_text=True)
    assert html.index('alt="Future Sponsor"') < html.index('alt="Ministry logo"')
    response = client.post(
        "/admin/settings/appearance/partners",
        data={
            "csrf_token": token,
            "action": "save",
            "partner_id": partner_id,
            "name": "Future Sponsor",
            "label": "Supported by",
            "website": "https://sponsor.example.test",
        },
    )
    assert response.status_code == 302
    assert "Future Sponsor" not in client.get("/").get_data(as_text=True)
    response = client.post(
        "/admin/settings/appearance/partners",
        data={"csrf_token": token, "action": "remove", "partner_id": partner_id},
    )
    assert response.status_code == 302
    client.post(
        "/admin/settings/appearance/partners",
        data={"csrf_token": token, "action": "remove", "partner_id": "ptf"},
    )
    assert 'alt="Polskie Towarzystwo' not in client.get("/").get_data(as_text=True)
    response = client.post(
        "/admin/settings/appearance/reset",
        data={"csrf_token": token, "section": "partners"},
    )
    assert response.status_code == 302
    with client.application.app_context():
        assert appearance.get_config()["partners"] == appearance.DEFAULT_PARTNERS


@pytest.mark.parametrize(
    "website",
    [
        "javascript:alert(1)",
        "//evil.example",
        "https://user:password@evil.example",
        "https://example.test\\evil",
    ],
)
def test_partner_unsafe_link_is_rejected(client, csrf_token, website):
    token = _token(client, csrf_token)
    response = client.post(
        "/admin/settings/appearance/partners",
        data={
            "csrf_token": token,
            "action": "save",
            "partner_id": "ptf",
            "name": "Changed",
            "website": website,
        },
    )
    assert response.status_code == 400
    with client.application.app_context():
        assert appearance.get_config()["partners"] == appearance.DEFAULT_PARTNERS


def test_restoring_defaults_preserves_competition_settings(client, csrf_token):
    token = _token(client, csrf_token)
    client.post(
        "/admin/settings/appearance",
        data=_payload(token, edition_name="Future edition", primary="#123456"),
    )
    with client.application.app_context():
        db.session.add(AppSetting(key="essay_word_limit", value="2200"))
        db.session.commit()
    response = client.post(
        "/admin/settings/appearance/reset", data={"csrf_token": token, "section": "all"}
    )
    assert response.status_code == 400
    response = client.post(
        "/admin/settings/appearance/reset",
        data={"csrf_token": token, "section": "all", "confirm_reset": "yes"},
    )
    assert response.status_code == 302
    with client.application.app_context():
        assert appearance.get_config() == appearance.DEFAULTS
        assert AppSetting.query.filter_by(key="essay_word_limit").one().value == "2200"


@pytest.mark.parametrize("section", ["identity", "partners"])
def test_settings_exceeding_database_text_limit_fail_without_partial_save(
    client, csrf_token, monkeypatch, section
):
    token = _token(client, csrf_token)
    monkeypatch.setattr(appearance, "MAX_CONFIG_BYTES", 100)
    if section == "identity":
        response = client.post(
            "/admin/settings/appearance",
            data=_payload(token, edition_name="Large configuration"),
        )
    else:
        response = client.post(
            "/admin/settings/appearance/partners",
            data={
                "csrf_token": token,
                "action": "save",
                "partner_id": "ptf",
                "name": "Updated organizer",
                "enabled": "y",
            },
        )
    assert response.status_code == 400
    assert "appearance settings are too long" in response.get_data(as_text=True)
    with client.application.app_context():
        assert appearance.get_config() == appearance.DEFAULTS
        assert ActivityLog.query.count() == 0


def test_pdf_logo_and_card_wifi_follow_edition_settings(client, csrf_token):
    token = _token(client, csrf_token)
    client.post(
        "/admin/settings/appearance/logos/print",
        data={"csrf_token": token, "action": "upload", "image": (_png(), "print.png")},
    )
    client.post(
        "/admin/settings/appearance",
        data=_payload(
            token, wifi_network="IPO-2028", wifi_password="next-venue-network"
        ),
    )
    with client.application.app_context():
        config = appearance.get_config()
        expected = (
            Path(client.application.config["UPLOAD_FOLDER"])
            / "branding"
            / config["logos"]["print"]["filename"]
        )
        for kind in views.PDF_LOGO_ASSETS:
            assert views._pdf_logo_path(kind) == expected
        db.session.add(
            Student(
                country="Testland",
                first_name="Future",
                last_name="Participant",
                email="future@example.test",
                school="School",
                date_of_birth=date(2008, 1, 1),
                essay_language="English",
                keyboard_preference="QWERTY",
                meal_preference="No preference",
            )
        )
        db.session.add(
            AssignmentBatch(
                name="Card test", stage=Stage.STAGE_1, status=PlannerStatus.PUBLISHED
            )
        )
        db.session.commit()
    response = client.get("/admin/students/cards.pdf")
    assert response.status_code == 200
    text = " ".join(
        page.extract_text() or "" for page in PdfReader(BytesIO(response.data)).pages
    )
    assert "IPO-2028" in text and "next-venue-network" in text
    assert "ipowarsaw2026" not in text
    client.post("/admin/settings/appearance", data=_payload(token, wifi_enabled=False))
    response = client.get("/admin/students/cards.pdf")
    text = " ".join(
        page.extract_text() or "" for page in PdfReader(BytesIO(response.data)).pages
    )
    assert "Wi-Fi access" not in text
    client.post(
        "/admin/settings/appearance/logos/print",
        data={"csrf_token": token, "action": "hide"},
    )
    with client.application.app_context():
        assert views._pdf_logo_uri("primary") is None
