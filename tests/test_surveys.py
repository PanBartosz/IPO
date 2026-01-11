from urllib.parse import parse_qs, urlparse

from ipo_app.extensions import db
from ipo_app.models import AppSetting


def _set_setting(key: str, value: str) -> None:
    existing = AppSetting.query.filter_by(key=key).first()
    if existing:
        existing.value = value
    else:
        db.session.add(AppSetting(key=key, value=value))
    db.session.commit()


def test_student_surveys_requires_authentication_redirects_to_login(client):
    response = client.get("/participant/surveys", follow_redirects=False)

    assert response.status_code == 302
    parsed = urlparse(response.headers["Location"])
    assert parsed.path == "/participant/login"
    query = parse_qs(parsed.query)
    next_value = (query.get("next") or [None])[0]
    assert next_value is not None
    assert next_value.startswith("/participant/surveys")


def test_teacher_surveys_requires_portal_enabled_redirects_to_board_login(client):
    response = client.get("/teacher/surveys", follow_redirects=False)

    assert response.status_code == 302
    assert response.headers["Location"].startswith("/board/login")


def test_teacher_surveys_requires_authentication_redirects_to_teacher_login(client):
    with client.application.app_context():
        _set_setting("teacher_portal_enabled", "true")

    response = client.get("/teacher/surveys", follow_redirects=False)

    assert response.status_code == 302
    parsed = urlparse(response.headers["Location"])
    assert parsed.path == "/teacher/login"
    query = parse_qs(parsed.query)
    next_value = (query.get("next") or [None])[0]
    assert next_value is not None
    assert next_value.startswith("/teacher/surveys")

