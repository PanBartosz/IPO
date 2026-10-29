import os
import time
from pathlib import Path

from dotenv import load_dotenv
from flask import Flask
from sqlalchemy.exc import OperationalError
from werkzeug.local import LocalProxy

# Configuration classes read environment variables when they are imported.
load_dotenv()

from .config import Config, DevelopmentConfig
from .extensions import csrf, db, limiter, migrate


def create_app(config_object: str | None = None) -> Flask:
    """Application factory for the IPO registration app."""

    load_dotenv()

    app = Flask(__name__, instance_relative_config=True)

    _configure_app(app, config_object)
    _configure_security(app)
    _ensure_instance_folder(app)
    _ensure_upload_folder(app)
    _ensure_static_page_attachment_folder(app)
    _register_extensions(app)
    _register_blueprints(app)
    _initialize_database(app)

    return app


def _configure_app(app: Flask, config_object: str | None) -> None:
    if config_object:
        app.config.from_object(config_object)
        return

    config_name = os.getenv("FLASK_CONFIG")
    if config_name:
        app.config.from_object(config_name)
    else:
        env = app.config.get("ENV")
        if env == "development":
            app.config.from_object(DevelopmentConfig)
        else:
            app.config.from_object(Config)


def _is_development_mode(app: Flask) -> bool:
    if app.debug or app.testing:
        return True
    env = os.getenv("FLASK_ENV", "").strip().lower()
    if env:
        return env == "development"
    config_env = str(app.config.get("ENV") or "").strip().lower()
    return config_env == "development"


def _configure_security(app: Flask) -> None:
    secret_key = app.config.get("SECRET_KEY")
    insecure_values = {"", None, "change-me", "dev-secret-key"}
    if secret_key in insecure_values and not _is_development_mode(app):
        raise RuntimeError("Refusing to start: set SECRET_KEY to a strong random value.")

    if app.config.get("SESSION_COOKIE_SECURE") is None:
        app.config["SESSION_COOKIE_SECURE"] = not _is_development_mode(app)

    samesite_raw = app.config.get("SESSION_COOKIE_SAMESITE")
    normalized = str(samesite_raw or "").strip().lower()
    if normalized not in {"lax", "strict", "none"}:
        normalized = "lax"
    app.config["SESSION_COOKIE_SAMESITE"] = normalized.title()


def _ensure_instance_folder(app: Flask) -> None:
    try:
        os.makedirs(app.instance_path, exist_ok=True)
    except OSError:
        pass


def _ensure_upload_folder(app: Flask) -> None:
    upload_path = Path(app.config.get("UPLOAD_FOLDER", Path(app.instance_path) / "uploads"))
    upload_path.mkdir(parents=True, exist_ok=True)


def _ensure_static_page_attachment_folder(app: Flask) -> None:
    attachment_path = Path(
        app.config.get(
            "STATIC_PAGE_ATTACHMENT_FOLDER",
            Path(app.config.get("UPLOAD_FOLDER", Path(app.instance_path) / "uploads")) / "static-pages",
        )
    )
    attachment_path.mkdir(parents=True, exist_ok=True)


def _register_extensions(app: Flask) -> None:
    db.init_app(app)
    migrate.init_app(app, db)
    csrf.init_app(app)
    limiter.init_app(app)


def _register_blueprints(app: Flask) -> None:
    from .views import web_bp, teacher_portal_bp

    app.register_blueprint(web_bp)
    app.register_blueprint(teacher_portal_bp)


def _initialize_database(app: Flask) -> None:
    attempts = int(os.getenv("DB_SETUP_MAX_RETRIES", 5))
    delay_seconds = float(os.getenv("DB_SETUP_RETRY_INTERVAL", 2))

    for attempt in range(attempts):
        try:
            with app.app_context():
                db.create_all()
            break
        except OperationalError:
            if attempt == attempts - 1:
                raise
            time.sleep(delay_seconds)


_wsgi_app: Flask | None = None


def _get_wsgi_app() -> Flask:
    global _wsgi_app
    if _wsgi_app is None:
        _wsgi_app = create_app()
    return _wsgi_app


# Allow `gunicorn ipo_app:app` without side effects at import time.
app = LocalProxy(_get_wsgi_app)
