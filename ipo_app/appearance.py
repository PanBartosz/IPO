"""Edition identity, theme settings and locally stored public brand images."""

from copy import deepcopy
from io import BytesIO
from itertools import groupby
import json
from pathlib import Path
import re
import secrets
from urllib.parse import urlsplit

from flask import (
    Blueprint,
    abort,
    current_app,
    flash,
    redirect,
    render_template,
    request,
    send_from_directory,
    url_for,
)
from flask_wtf import FlaskForm
from flask_wtf.file import FileAllowed, FileField
from PIL import Image, ImageOps, UnidentifiedImageError
from wtforms import (
    BooleanField,
    IntegerField,
    SelectField,
    StringField,
    SubmitField,
    TextAreaField,
)
from wtforms.validators import (
    DataRequired,
    Email,
    Length,
    NumberRange,
    Optional,
    Regexp,
    ValidationError,
)

from .extensions import db


appearance_bp = Blueprint("appearance", __name__)
SETTING_APPEARANCE = "edition_appearance_v1"
MAX_IMAGE_BYTES = 3 * 1024 * 1024
MAX_IMAGE_PIXELS = 16_000_000
MAX_PARTNERS = 30
# AppSetting.value is a MySQL TEXT column, whose limit is measured in bytes.
MAX_CONFIG_BYTES = 60 * 1024
IMAGE_NAME = re.compile(r"[0-9a-f]{32}\.png\Z")
HEX_COLOR = re.compile(r"#[0-9a-fA-F]{6}\Z")

COLOR_FIELDS = {
    "primary": ("Primary", "#822D80"),
    "accent": ("Accent", "#E14CE1"),
    "highlight": ("Highlight", "#DE743B"),
    "page_background": ("Page background", "#FFFFFF"),
    "surface": ("Cards and forms", "#FFFFFF"),
    "text": ("Main text", "#121212"),
    "button_text": ("Button text", "#FFFFFF"),
    "header_background": ("Header background", "#121212"),
    "header_text": ("Header text", "#FFFFFF"),
    "footer_background": ("Footer background", "#121212"),
    "footer_text": ("Footer text", "#FFFFFF"),
}
FONT_STACKS = {
    "raleway": '"Raleway", system-ui, -apple-system, "Segoe UI", sans-serif',
    "condensed": '"Roboto Condensed", "Arial Narrow", system-ui, -apple-system, "Segoe UI", sans-serif',
    "system": 'system-ui, -apple-system, "Segoe UI", sans-serif',
    "serif": 'Georgia, "Times New Roman", serif',
}
FONT_CHOICES = [
    ("raleway", "Raleway"),
    ("condensed", "Roboto Condensed"),
    ("system", "System sans serif"),
    ("serif", "Classic serif"),
]
CORNER_STYLES = {"current": (12, 16, 22), "square": (3, 5, 8), "rounded": (18, 24, 32)}
LOGO_SLOTS = {
    "header": ("Header logo", "img/ipo-warsaw-2026/6c.png"),
    "footer": ("Footer logo", "img/ipo-warsaw-2026/7.png"),
    "login": ("Portal login logo", "img/ipo-official-logo.png"),
    "favicon": ("Browser icon · light mode", "img/ipo-warsaw-2026/6.png"),
    "favicon_dark": ("Browser icon · dark mode", "img/ipo-warsaw-2026/6c.png"),
    "hero": ("Homepage decorative image", "img/ipo-warsaw-2026/7.png"),
    "print": ("PDF documents and printed cards", "pdfgen_img_assets/logos/a.png"),
}
DEFAULT_PARTNERS = [
    {
        "id": "ptf",
        "name": "Polskie Towarzystwo Filozoficzne (PTF) logo",
        "static": "img/ptf-logo.png",
    },
    {"id": "uw", "name": "University of Warsaw (UW) logo", "static": "img/uw-logo.png"},
    {"id": "wfz", "name": "Wydział Filozofii (WFZ) logo", "static": "img/wfz-logo.png"},
    {"id": "ministry", "name": "Ministry logo", "static": "img/ministry-logo.png"},
]
for _partner in DEFAULT_PARTNERS:
    _partner.update(label="Organized by", website="", filename=None, enabled=True)

DEFAULTS = {
    "edition_name": "IPO Warsaw 2026",
    "tagline": "International Philosophy Olympiad portal",
    "browser_title": "IPO Registration",
    "hero_title": "Welcome to the IPO registration portal",
    "hero_intro": "Please choose the appropriate registration form.",
    "copyright": "International Philosophy Olympiad",
    "footer_note": "",
    "contact_email": "",
    "contact_url": "",
    "body_font": "raleway",
    "heading_font": "condensed",
    "corners": "current",
    "font_size": "standard",
    "gradient_enabled": True,
    "decorations_enabled": True,
    "partners_enabled": True,
    "footer_enabled": True,
    "header_logo_width": 56,
    "partner_logo_height": 80,
    "wifi_network": "ipo2026",
    "wifi_password": "ipowarsaw2026",
    "wifi_enabled": True,
    **{key: default for key, (_, default) in COLOR_FIELDS.items()},
    "logos": {slot: {"filename": None, "hidden": False} for slot in LOGO_SLOTS},
    "partners": DEFAULT_PARTNERS,
}
PALETTES = {
    "warsaw": {
        "label": "Warsaw 2026 · current default",
        "colors": {key: value for key, (_, value) in COLOR_FIELDS.items()},
    },
    "ocean": {
        "label": "Ocean · navy and teal",
        "colors": {
            "primary": "#164E63",
            "accent": "#0F766E",
            "highlight": "#2563EB",
            "page_background": "#F4F8FA",
            "header_background": "#102A43",
            "footer_background": "#102A43",
        },
    },
    "forest": {
        "label": "Forest · green and gold",
        "colors": {
            "primary": "#24563D",
            "accent": "#38704A",
            "highlight": "#946C25",
            "page_background": "#F6F8F2",
            "header_background": "#18382A",
            "footer_background": "#18382A",
        },
    },
    "burgundy": {
        "label": "Burgundy · wine and terracotta",
        "colors": {
            "primary": "#782F45",
            "accent": "#9D3D56",
            "highlight": "#9D582F",
            "page_background": "#FBF6F3",
            "header_background": "#34202B",
            "footer_background": "#34202B",
        },
    },
}


def _safe_website(value: str) -> bool:
    if not value:
        return True
    if "\\" in value or any(ord(char) < 33 for char in value):
        return False
    try:
        parsed = urlsplit(value)
        return (
            parsed.scheme in {"https", "http"}
            and bool(parsed.hostname)
            and not parsed.username
            and not parsed.password
        )
    except ValueError:
        return False


def _website_validator(form, field):
    if not _safe_website(field.data or ""):
        raise ValidationError("Use a complete http:// or https:// address.")


class AppearanceForm(FlaskForm):
    edition_name = StringField(
        "Edition name", validators=[DataRequired(), Length(max=80)]
    )
    tagline = StringField("Header subtitle", validators=[Optional(), Length(max=160)])
    browser_title = StringField(
        "Homepage browser title", validators=[DataRequired(), Length(max=100)]
    )
    hero_title = StringField(
        "Homepage heading", validators=[DataRequired(), Length(max=180)]
    )
    hero_intro = TextAreaField(
        "Homepage introduction", validators=[Optional(), Length(max=1000)]
    )
    copyright = StringField(
        "Copyright owner", validators=[DataRequired(), Length(max=140)]
    )
    footer_note = TextAreaField(
        "Additional footer text", validators=[Optional(), Length(max=400)]
    )
    contact_email = StringField(
        "Contact email", validators=[Optional(), Email(), Length(max=255)]
    )
    contact_url = StringField(
        "Event website", validators=[Optional(), Length(max=500), _website_validator]
    )
    body_font = SelectField("Body font", choices=FONT_CHOICES)
    heading_font = SelectField("Heading font", choices=FONT_CHOICES)
    corners = SelectField(
        "Card and button corners",
        choices=[
            ("current", "Current · softly rounded"),
            ("square", "Almost square"),
            ("rounded", "More rounded"),
        ],
    )
    font_size = SelectField(
        "Text size",
        choices=[
            ("small", "Small · 15 px"),
            ("standard", "Current · 16 px"),
            ("large", "Large · 18 px"),
        ],
    )
    gradient_enabled = BooleanField("Use the three-color gradient")
    decorations_enabled = BooleanField("Show decorative shapes and homepage image")
    partners_enabled = BooleanField("Show partner and sponsor logos")
    footer_enabled = BooleanField("Show the page footer")
    header_logo_width = IntegerField(
        "Header logo width (px)", validators=[NumberRange(min=32, max=140)]
    )
    partner_logo_height = IntegerField(
        "Maximum partner logo height (px)", validators=[NumberRange(min=24, max=120)]
    )
    wifi_enabled = BooleanField("Print Wi-Fi information on access cards")
    wifi_network = StringField(
        "Wi-Fi network on printed cards", validators=[Optional(), Length(max=100)]
    )
    wifi_password = StringField(
        "Wi-Fi password on printed cards", validators=[Optional(), Length(max=100)]
    )
    submit = SubmitField("Save appearance")


for _key, (_label, _default) in COLOR_FIELDS.items():
    setattr(
        AppearanceForm,
        _key,
        StringField(
            _label,
            validators=[
                DataRequired(),
                Regexp(
                    r"^#[0-9A-Fa-f]{6}$",
                    message="Use a six-digit hex color, for example #822D80.",
                ),
            ],
        ),
    )


class LogoForm(FlaskForm):
    image = FileField(
        "Image",
        validators=[
            Optional(),
            FileAllowed(["png", "jpg", "jpeg", "webp"], "Use PNG, JPEG or WebP."),
        ],
    )


class PartnerForm(LogoForm):
    name = StringField(
        "Name / alternative text", validators=[DataRequired(), Length(max=140)]
    )
    label = StringField("Group label", validators=[Optional(), Length(max=60)])
    website = StringField(
        "Website", validators=[Optional(), Length(max=500), _website_validator]
    )
    enabled = BooleanField("Visible")


TEXT_LIMITS = {
    key: next(
        (
            validator.max
            for validator in getattr(AppearanceForm, key).kwargs.get("validators", [])
            if isinstance(validator, Length)
        ),
        1000,
    )
    for key, value in DEFAULTS.items()
    if isinstance(value, str)
}


def get_config() -> dict:
    from .views import _get_setting

    config = deepcopy(DEFAULTS)
    raw = _get_setting(SETTING_APPEARANCE)
    if not raw:
        return config
    try:
        saved = json.loads(raw)
    except (TypeError, ValueError):
        return config
    if not isinstance(saved, dict):
        return config
    for key, default in DEFAULTS.items():
        value = saved.get(key)
        if key in COLOR_FIELDS:
            if isinstance(value, str) and HEX_COLOR.fullmatch(value):
                config[key] = value.upper()
        elif isinstance(default, bool):
            if isinstance(value, bool):
                config[key] = value
        elif isinstance(default, int):
            maximum = 140 if key == "header_logo_width" else 120
            minimum = 32 if key == "header_logo_width" else 24
            if type(value) is int and minimum <= value <= maximum:
                config[key] = value
        elif isinstance(default, str) and isinstance(value, str):
            config[key] = value[: TEXT_LIMITS.get(key, 1000)]
    for key, allowed in [
        ("body_font", FONT_STACKS),
        ("heading_font", FONT_STACKS),
        ("corners", CORNER_STYLES),
        ("font_size", {"small", "standard", "large"}),
    ]:
        if config[key] not in allowed:
            config[key] = DEFAULTS[key]
    if not _safe_website(config["contact_url"]):
        config["contact_url"] = ""
    if not re.fullmatch(r"[^\s@<>]+@[^\s@<>]+\.[^\s@<>]+", config["contact_email"]):
        config["contact_email"] = ""
    if isinstance(saved.get("logos"), dict):
        for slot in LOGO_SLOTS:
            value = saved["logos"].get(slot)
            if isinstance(value, dict):
                filename = value.get("filename")
                config["logos"][slot] = {
                    "filename": filename
                    if isinstance(filename, str) and IMAGE_NAME.fullmatch(filename)
                    else None,
                    "hidden": value.get("hidden") is True,
                }
    if isinstance(saved.get("partners"), list):
        partners = []
        known_ids = set()
        for partner in saved["partners"][:MAX_PARTNERS]:
            if not isinstance(partner, dict):
                continue
            partner_id = partner.get("id", "")
            if (
                not isinstance(partner_id, str)
                or not re.fullmatch(r"[a-z0-9-]{1,40}", partner_id)
                or partner_id in known_ids
            ):
                continue
            static = next(
                (
                    item["static"]
                    for item in DEFAULT_PARTNERS
                    if item["id"] == partner_id
                ),
                None,
            )
            filename = partner.get("filename")
            filename = (
                filename
                if isinstance(filename, str) and IMAGE_NAME.fullmatch(filename)
                else None
            )
            if not static and not filename:
                continue
            known_ids.add(partner_id)
            website = str(partner.get("website") or "")[:500]
            partners.append(
                {
                    "id": partner_id,
                    "name": str(partner.get("name") or "Partner")[:140],
                    "label": str(partner.get("label") or "")[:60],
                    "website": website if _safe_website(website) else "",
                    "enabled": partner.get("enabled", True) is True,
                    "static": static,
                    "filename": filename,
                }
            )
        config["partners"] = partners
    return config


def image_folder() -> Path:
    return Path(current_app.config["UPLOAD_FOLDER"]) / "branding"


def custom_image_path(filename: str | None) -> Path | None:
    if not filename or not IMAGE_NAME.fullmatch(filename):
        return None
    path = image_folder() / filename
    return path if path.is_file() else None


def _image_url(filename: str | None, static: str | None) -> str | None:
    if custom_image_path(filename):
        return url_for("appearance.brand_image", filename=filename)
    return url_for("static", filename=static) if static else None


def logo_path(slot: str) -> Path | None:
    state = get_config()["logos"][slot]
    if state["hidden"]:
        return None
    return custom_image_path(state["filename"])


def css_variables(config: dict) -> dict[str, str]:
    def rgb(key):
        color = config[key].lstrip("#")
        return ", ".join(str(int(color[index : index + 2], 16)) for index in (0, 2, 4))

    result = {
        "--brand-purple": config["primary"],
        "--brand-magenta": config["accent"],
        "--brand-orange": config["highlight"],
        "--brand-black": config["text"],
        "--text": config["text"],
        "--page-bg": config["page_background"],
        "--surface": f"rgba({rgb('surface')}, 0.94)",
        "--text-muted": f"rgba({rgb('text')}, 0.72)",
        "--border": f"rgba({rgb('text')}, 0.14)",
        "--border-strong": f"rgba({rgb('text')}, 0.22)",
        "--font-body": FONT_STACKS[config["body_font"]],
        "--font-heading": FONT_STACKS[config["heading_font"]],
        "--header-bg": config["header_background"],
        "--header-text": config["header_text"],
        "--footer-bg": config["footer_background"],
        "--button-text": config["button_text"],
        "--header-logo-width": f"{config['header_logo_width']}px",
        "--partner-logo-height": f"{config['partner_logo_height']}px",
    }
    for key in (
        "primary",
        "accent",
        "highlight",
        "text",
        "surface",
        "header_text",
        "footer_text",
    ):
        result["--" + key.replace("_", "-") + "-rgb"] = rgb(key)
    for name, radius in zip(("sm", "md", "lg"), CORNER_STYLES[config["corners"]]):
        result[f"--radius-{name}"] = f"{radius}px"
    if config["font_size"] != "standard":
        result["font-size"] = "15px" if config["font_size"] == "small" else "18px"
    if not config["gradient_enabled"]:
        result["--brand-gradient"] = config["primary"]
        result["--page-background"] = config["page_background"]
    return result


def get_appearance() -> dict:
    config = get_config()
    appearance = {
        key: value for key, value in config.items() if not key.startswith("wifi_")
    }
    appearance["logo_urls"] = {
        slot: None
        if config["logos"][slot]["hidden"]
        else _image_url(config["logos"][slot]["filename"], static)
        for slot, (_, static) in LOGO_SLOTS.items()
    }
    appearance["css_variables"] = css_variables(config)
    hero = appearance["logo_urls"]["hero"]
    appearance["css_variables"]["--hero-image"] = f'url("{hero}")' if hero else "none"
    appearance["partner_groups"] = []
    visible = []
    for partner in config["partners"]:
        if partner["enabled"]:
            url = _image_url(partner["filename"], partner["static"])
            if url:
                visible.append({**partner, "image_url": url})
    for label, partners in groupby(visible, key=lambda item: item["label"]):
        appearance["partner_groups"].append(
            {"label": label, "partners": list(partners)}
        )
    return appearance


def _require_admin():
    from .views import _current_admin

    if not _current_admin():
        return redirect(url_for("web.admin_login", next=url_for("appearance.settings")))
    return None


def _save_config(config: dict | None, section: str, **details):
    from .views import _set_setting, log_activity

    value = json.dumps(config, ensure_ascii=False) if config is not None else None
    if value is not None and len(value.encode("utf-8")) > MAX_CONFIG_BYTES:
        raise ValueError(
            "These appearance settings are too long. Shorten some descriptions or partner links and try again."
        )
    _set_setting(SETTING_APPEARANCE, value)
    log_activity(
        "appearance_updated",
        f"Edition appearance updated: {section}",
        object_type="appearance",
        details={"section": section, **details},
    )
    db.session.commit()


def _render_settings(form=None, *, error=None, status=200):
    config = get_config()
    partners = [
        {
            **partner,
            "image_url": _image_url(partner["filename"], partner["static"]),
            "form": PartnerForm(formdata=None, data=partner),
        }
        for partner in config["partners"]
    ]
    return render_template(
        "admin/appearance.html",
        form=form or AppearanceForm(formdata=None, data=config),
        logo_form=LogoForm(formdata=None),
        partner_form=PartnerForm(
            formdata=None, data={"enabled": True, "label": "Partners"}
        ),
        partners=partners,
        appearance_config=config,
        logo_slots=LOGO_SLOTS,
        color_fields=COLOR_FIELDS,
        palettes=PALETTES,
        error=error,
        default_edition=DEFAULTS["edition_name"],
    ), status


def _save_image(upload) -> str:
    data = upload.stream.read(MAX_IMAGE_BYTES + 1)
    if len(data) > MAX_IMAGE_BYTES:
        raise ValueError("Choose an image smaller than 3 MB.")
    try:
        with Image.open(BytesIO(data)) as image:
            if image.format not in {"PNG", "JPEG", "WEBP"}:
                raise ValueError("Use a PNG, JPEG or WebP image.")
            if image.width * image.height > MAX_IMAGE_PIXELS:
                raise ValueError(
                    "This image is too large. Use at most 16 million pixels."
                )
            image.verify()
        with Image.open(BytesIO(data)) as image:
            normalized = ImageOps.exif_transpose(image).convert("RGBA")
            normalized.thumbnail((2400, 2400))
            output = BytesIO()
            normalized.save(output, format="PNG")
        if output.tell() > 8 * 1024 * 1024:
            raise ValueError(
                "Choose a smaller image; the processed image exceeds 8 MB."
            )
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as exc:
        raise ValueError("The file could not be read as a valid image.") from exc
    folder = image_folder()
    folder.mkdir(parents=True, exist_ok=True)
    filename = secrets.token_hex(16) + ".png"
    with (folder / filename).open("xb") as destination:
        destination.write(output.getvalue())
    return filename


@appearance_bp.route("/admin/settings/appearance", methods=["GET", "POST"])
def settings():
    guard = _require_admin()
    if guard:
        return guard
    if request.method == "POST":
        form = AppearanceForm()
        if form.validate_on_submit():
            config = get_config()
            for key in DEFAULTS:
                if key not in {"logos", "partners"}:
                    value = getattr(form, key).data
                    config[key] = value.strip() if isinstance(value, str) else value
            try:
                _save_config(config, "identity, palette and layout")
            except ValueError as exc:
                return _render_settings(form, error=str(exc), status=400)
            flash(
                "Appearance saved. The new identity is now visible throughout the portal.",
                "success",
            )
            return redirect(url_for("appearance.settings"))
        return _render_settings(form, status=400)
    return _render_settings()


@appearance_bp.route("/admin/settings/appearance/logos/<slot>", methods=["POST"])
def update_logo(slot):
    guard = _require_admin()
    if guard:
        return guard
    if slot not in LOGO_SLOTS:
        abort(404)
    form = LogoForm()
    action = request.form.get("action")
    if not form.validate_on_submit() or action not in {
        "upload",
        "reset",
        "hide",
        "show",
    }:
        return _render_settings(
            error="Choose a PNG, JPEG or WebP image and try again.", status=400
        )
    config = get_config()
    try:
        if action == "upload":
            if not form.image.data:
                raise ValueError("Choose an image to upload.")
            config["logos"][slot] = {
                "filename": _save_image(form.image.data),
                "hidden": False,
            }
        elif action == "reset":
            config["logos"][slot] = deepcopy(DEFAULTS["logos"][slot])
        else:
            config["logos"][slot]["hidden"] = action == "hide"
        _save_config(config, "logo", slot=slot, action=action)
    except ValueError as exc:
        return _render_settings(error=str(exc), status=400)
    flash(f"{LOGO_SLOTS[slot][0]} updated.", "success")
    return redirect(url_for("appearance.settings", _anchor="appearance-logos"))


@appearance_bp.route("/admin/settings/appearance/partners", methods=["POST"])
def update_partner():
    guard = _require_admin()
    if guard:
        return guard
    config = get_config()
    partner_id = request.form.get("partner_id")
    action = request.form.get("action", "save")
    partner = next(
        (item for item in config["partners"] if item["id"] == partner_id), None
    )
    if partner_id and not partner:
        abort(404)
    if action in {"up", "down", "remove"}:
        if not partner:
            abort(400)
        index = config["partners"].index(partner)
        if action == "remove":
            config["partners"].pop(index)
        else:
            destination = index + (-1 if action == "up" else 1)
            if 0 <= destination < len(config["partners"]):
                config["partners"][index], config["partners"][destination] = (
                    config["partners"][destination],
                    config["partners"][index],
                )
    elif action == "save":
        form = PartnerForm()
        if not form.validate_on_submit():
            return _render_settings(
                error="Check the partner name, website (http/https), and image format.",
                status=400,
            )
        if not partner and len(config["partners"]) >= MAX_PARTNERS:
            return _render_settings(error="You can add up to 30 partners.", status=400)
        if not partner and not form.image.data:
            return _render_settings(
                error="Choose a logo for the new partner.", status=400
            )
        partner = partner or {
            "id": secrets.token_hex(8),
            "static": None,
            "filename": None,
        }
        try:
            if form.image.data:
                partner["filename"] = _save_image(form.image.data)
        except ValueError as exc:
            return _render_settings(error=str(exc), status=400)
        partner.update(
            name=form.name.data.strip(),
            label=(form.label.data or "").strip(),
            website=(form.website.data or "").strip(),
            enabled=bool(form.enabled.data),
        )
        if not partner_id:
            config["partners"].append(partner)
    else:
        abort(400)
    try:
        _save_config(config, "partners", action=action)
    except ValueError as exc:
        return _render_settings(error=str(exc), status=400)
    flash("Partner list updated.", "success")
    return redirect(url_for("appearance.settings", _anchor="appearance-partners"))


@appearance_bp.route("/admin/settings/appearance/reset", methods=["POST"])
def reset():
    guard = _require_admin()
    if guard:
        return guard
    section = request.form.get("section", "all")
    if section == "partners":
        config = get_config()
        config["partners"] = deepcopy(DEFAULT_PARTNERS)
        config["partners_enabled"] = True
        _save_config(config, "restore original partners")
    elif section == "all":
        if request.form.get("confirm_reset") != "yes":
            return _render_settings(
                error="Confirm restoring the original appearance before continuing.",
                status=400,
            )
        _save_config(None, "restore original appearance")
    else:
        abort(400)
    flash(
        "Original appearance restored. Competition settings and participant data were not changed.",
        "success",
    )
    return redirect(url_for("appearance.settings"))


@appearance_bp.route("/branding/assets/<filename>")
def brand_image(filename):
    if not custom_image_path(filename):
        abort(404)
    response = send_from_directory(
        image_folder(), filename, mimetype="image/png", max_age=31536000
    )
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.cache_control.immutable = True
    return response
