import re
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from ipo_app import create_app
from ipo_app.extensions import db


@pytest.fixture()
def app(tmp_path: Path):
    class TestConfig:
        TESTING = True
        SECRET_KEY = "test-secret-key"
        WTF_CSRF_ENABLED = True
        WTF_CSRF_TIME_LIMIT = None
        SESSION_COOKIE_SECURE = False
        SESSION_COOKIE_SAMESITE = "Lax"

        RATELIMIT_ENABLED = False
        RATELIMIT_STORAGE_URI = "memory://"

        SQLALCHEMY_DATABASE_URI = f"sqlite:///{tmp_path / 'ipo-test.db'}"
        SQLALCHEMY_TRACK_MODIFICATIONS = False

        ADMIN_USERS = "admin:test-password"
        TEACHER_BOARD_PASSWORD = "board-password"

        UPLOAD_FOLDER = str(tmp_path / "uploads")
        STATIC_PAGE_ATTACHMENT_FOLDER = str(tmp_path / "static-page-attachments")
        BACKUP_FOLDER = str(tmp_path / "backups")

        SENDGRID_API_KEY = None
        SENDGRID_FROM_EMAIL = None

    app = create_app(TestConfig)
    yield app
    with app.app_context():
        db.session.remove()
        db.engine.dispose()


@pytest.fixture()
def client(app):
    return app.test_client()


@pytest.fixture()
def csrf_token():
    def _extract(response) -> str:
        html = response.get_data(as_text=True)
        match = re.search(r'name="csrf_token"[^>]*value=["\\\']([^"\\\']+)["\\\']', html)
        assert match, "CSRF token input not found in response HTML"
        return match.group(1)

    return _extract
