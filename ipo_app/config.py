import os
from pathlib import Path


class Config:
    """Base configuration shared across environments."""

    SECRET_KEY = os.getenv("SECRET_KEY", "change-me")
    ADMIN_USERS = os.getenv("ADMIN_USERS", "")
    UPLOAD_FOLDER = os.getenv("UPLOAD_FOLDER", str(Path(__file__).resolve().parent.parent / "instance" / "uploads"))
    MAX_CONTENT_LENGTH = int(os.getenv("MAX_UPLOAD_SIZE", 10 * 1024 * 1024))
    WTF_CSRF_ENABLED = True
    WTF_CSRF_TIME_LIMIT = None
    SQLALCHEMY_DATABASE_URI = os.getenv(
        "DATABASE_URL",
        f"sqlite:///{Path(__file__).parent.parent / 'instance' / 'ipo_app.db'}",
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {"pool_pre_ping": True}
    DASHBOARD_UPLOAD_DEADLINE = os.getenv('DASHBOARD_UPLOAD_DEADLINE')
    DASHBOARD_STAGE2_DEADLINE = os.getenv('DASHBOARD_STAGE2_DEADLINE')
    DASHBOARD_STAGE1_SCORE_SLA_HOURS = int(os.getenv('DASHBOARD_STAGE1_SCORE_SLA_HOURS', 24))
    DASHBOARD_STAGE2_SCORE_SLA_HOURS = int(os.getenv('DASHBOARD_STAGE2_SCORE_SLA_HOURS', 24))
    TEACHER_BOARD_PASSWORD = os.getenv('TEACHER_BOARD_PASSWORD')
    SENDGRID_API_KEY = os.getenv("SENDGRID_API_KEY")
    SENDGRID_FROM_EMAIL = os.getenv("SENDGRID_FROM_EMAIL")


class DevelopmentConfig(Config):
    DEBUG = True


class TestConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
