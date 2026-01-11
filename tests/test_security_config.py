import pytest

from ipo_app import create_app


def test_create_app_refuses_insecure_secret_key_outside_development(monkeypatch):
    class BadConfig:
        SECRET_KEY = "change-me"
        TESTING = False
        DEBUG = False

    monkeypatch.setenv("FLASK_ENV", "production")

    with pytest.raises(RuntimeError, match="set SECRET_KEY"):
        create_app(BadConfig)

