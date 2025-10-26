import os
import time
from pathlib import Path

from dotenv import load_dotenv
from flask import Flask
from sqlalchemy.exc import OperationalError

from .config import Config, DevelopmentConfig
from .extensions import db, migrate


def create_app(config_object: str | None = None) -> Flask:
    """Application factory for the IPO registration app."""

    load_dotenv()

    app = Flask(__name__, instance_relative_config=True)

    _configure_app(app, config_object)
    _ensure_instance_folder(app)
    _ensure_upload_folder(app)
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


def _ensure_instance_folder(app: Flask) -> None:
    try:
        os.makedirs(app.instance_path, exist_ok=True)
    except OSError:
        pass


def _ensure_upload_folder(app: Flask) -> None:
    upload_path = Path(app.config.get("UPLOAD_FOLDER", Path(app.instance_path) / "uploads"))
    upload_path.mkdir(parents=True, exist_ok=True)


def _register_extensions(app: Flask) -> None:
    db.init_app(app)
    migrate.init_app(app, db)


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


# Allow `wsgi.py`-style usage.
app = create_app()
