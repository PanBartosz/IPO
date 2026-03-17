from pathlib import Path

from sqlalchemy.exc import OperationalError

import ipo_app
from ipo_app import create_app
from ipo_app.extensions import db


def _build_config(tmp_path: Path, **overrides):
    attrs = {
        "SECRET_KEY": "test-secret-key",
        "TESTING": False,
        "DEBUG": False,
        "ADMIN_USERS": "admin:test-password",
        "RATELIMIT_ENABLED": False,
        "SQLALCHEMY_DATABASE_URI": f"sqlite:///{tmp_path / 'ipo-test.db'}",
        "SQLALCHEMY_TRACK_MODIFICATIONS": False,
        "UPLOAD_FOLDER": str(tmp_path / "uploads"),
        "STATIC_PAGE_ATTACHMENT_FOLDER": str(tmp_path / "static-page-attachments"),
    }
    attrs.update(overrides)
    return type("FactoryTestConfig", (), attrs)


def _dispose_app(app) -> None:
    with app.app_context():
        db.session.remove()
        db.engine.dispose()


def test_create_app_defaults_secure_cookie_in_production_when_unset(tmp_path, monkeypatch):
    config = _build_config(tmp_path, SESSION_COOKIE_SECURE=None)

    monkeypatch.setenv("FLASK_ENV", "production")

    app = create_app(config)
    try:
        assert app.config["SESSION_COOKIE_SECURE"] is True
        assert Path(app.config["UPLOAD_FOLDER"]).is_dir()
        assert Path(app.config["STATIC_PAGE_ATTACHMENT_FOLDER"]).is_dir()
    finally:
        _dispose_app(app)


def test_create_app_normalizes_invalid_samesite_to_lax(tmp_path, monkeypatch):
    config = _build_config(
        tmp_path,
        SESSION_COOKIE_SECURE=False,
        SESSION_COOKIE_SAMESITE=" not-a-real-mode ",
    )

    monkeypatch.setenv("FLASK_ENV", "production")

    app = create_app(config)
    try:
        assert app.config["SESSION_COOKIE_SAMESITE"] == "Lax"
    finally:
        _dispose_app(app)


def test_create_app_preserves_valid_samesite_with_title_case(tmp_path, monkeypatch):
    config = _build_config(
        tmp_path,
        SESSION_COOKIE_SECURE=False,
        SESSION_COOKIE_SAMESITE="strict",
    )

    monkeypatch.setenv("FLASK_ENV", "production")

    app = create_app(config)
    try:
        assert app.config["SESSION_COOKIE_SAMESITE"] == "Strict"
    finally:
        _dispose_app(app)


def test_create_app_retries_database_initialization_on_transient_operational_errors(tmp_path, monkeypatch):
    config = _build_config(tmp_path)
    attempts: list[str] = []
    sleep_calls: list[float] = []

    def flaky_create_all() -> None:
        attempts.append("create_all")
        if len(attempts) == 1:
            raise OperationalError("SELECT 1", {}, RuntimeError("database not ready"))

    monkeypatch.setenv("DB_SETUP_MAX_RETRIES", "2")
    monkeypatch.setenv("DB_SETUP_RETRY_INTERVAL", "0.25")
    monkeypatch.setattr(ipo_app.db, "create_all", flaky_create_all)
    monkeypatch.setattr(ipo_app.time, "sleep", lambda seconds: sleep_calls.append(seconds))

    app = create_app(config)
    try:
        assert attempts == ["create_all", "create_all"]
        assert sleep_calls == [0.25]
    finally:
        _dispose_app(app)
