import os
from datetime import timedelta
from pathlib import Path


def _env_bool(name: str, default: bool | None = None) -> bool | None:
    value = os.getenv(name)
    if value is None:
        return default
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    return default


class Config:
    """Base configuration shared across environments."""

    SECRET_KEY = os.getenv("SECRET_KEY", "change-me")
    ADMIN_USERS = os.getenv("ADMIN_USERS", "")
    UPLOAD_FOLDER = os.getenv("UPLOAD_FOLDER", str(Path(__file__).resolve().parent.parent / "instance" / "uploads"))
    MAX_CONTENT_LENGTH = int(os.getenv("MAX_UPLOAD_SIZE", 10 * 1024 * 1024))
    WTF_CSRF_ENABLED = True
    WTF_CSRF_TIME_LIMIT = None
    RATELIMIT_ENABLED = _env_bool("RATELIMIT_ENABLED", True)
    RATELIMIT_STORAGE_URI = os.getenv("RATELIMIT_STORAGE_URI", "memory://")
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = os.getenv("SESSION_COOKIE_SAMESITE", "Lax")
    SESSION_COOKIE_SECURE = _env_bool("SESSION_COOKIE_SECURE")
    PERMANENT_SESSION_LIFETIME = timedelta(hours=int(os.getenv("PERMANENT_SESSION_LIFETIME_HOURS", "72")))
    SQLALCHEMY_DATABASE_URI = os.getenv(
        "DATABASE_URL",
        f"sqlite:///{Path(__file__).parent.parent / 'instance' / 'ipo_app.db'}",
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {"pool_pre_ping": True}
    DASHBOARD_UPLOAD_DEADLINE = os.getenv('DASHBOARD_UPLOAD_DEADLINE')
    DASHBOARD_STAGE2_DEADLINE = os.getenv('DASHBOARD_STAGE2_DEADLINE')
    DASHBOARD_EVENT_END = os.getenv('DASHBOARD_EVENT_END')
    DASHBOARD_STAGE1_SCORE_SLA_HOURS = int(os.getenv('DASHBOARD_STAGE1_SCORE_SLA_HOURS', 24))
    DASHBOARD_STAGE2_SCORE_SLA_HOURS = int(os.getenv('DASHBOARD_STAGE2_SCORE_SLA_HOURS', 24))
    TEACHER_BOARD_PASSWORD = os.getenv('TEACHER_BOARD_PASSWORD')
    SENDGRID_API_KEY = os.getenv("SENDGRID_API_KEY")
    SENDGRID_FROM_EMAIL = os.getenv("SENDGRID_FROM_EMAIL")
    EMAIL_DEV_FAKE_SEND = _env_bool("EMAIL_DEV_FAKE_SEND", False)


class DevelopmentConfig(Config):
    DEBUG = True


class TestConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
