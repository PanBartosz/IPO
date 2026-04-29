import pytest

from ipo_app.models import AppSetting


def _get_setting_value(key: str) -> str | None:
    setting = AppSetting.query.filter_by(key=key).first()
    if not setting:
        return None
    return setting.value


@pytest.mark.parametrize(
    ("path", "data"),
    [
        ("/admin/uploads/lock", {"state": "lock"}),
        ("/admin/uploads/1/override", {"reason": "rescue", "confirm": "y", "finalize_current": "Finalize current upload"}),
        ("/admin/grading/lock", {"stage": "stage_1", "state": "lock"}),
        ("/admin/planner", {}),
        ("/admin/exports/essays", {}),
        ("/admin/exports/database", {}),
        ("/admin/messages/quick", {}),
        ("/admin/surveys/new", {}),
        ("/admin/invitations/normal", {}),
        ("/admin/invitations/batch/preview", {}),
        ("/admin/invitations/batch/1/execute", {}),
        ("/admin/invitations/batch/1/discard", {}),
    ],
)
def test_admin_post_without_csrf_is_rejected_across_modules(client, path, data):
    with client.session_transaction() as session:
        session["admin_user"] = "admin"

    response = client.post(path, data=data, follow_redirects=False)
    assert response.status_code == 400


def test_admin_upload_lock_toggle_succeeds_with_csrf(client, csrf_token):
    with client.session_transaction() as session:
        session["admin_user"] = "admin"

    exports_page = client.get("/admin/exports")
    token = csrf_token(exports_page)

    response = client.post(
        "/admin/uploads/lock",
        data={"csrf_token": token, "state": "lock"},
        follow_redirects=False,
    )
    assert response.status_code == 302

    with client.application.app_context():
        assert _get_setting_value("upload_locked") == "true"

    exports_page = client.get("/admin/exports")
    token = csrf_token(exports_page)

    response = client.post(
        "/admin/uploads/lock",
        data={"csrf_token": token, "state": "unlock"},
        follow_redirects=False,
    )
    assert response.status_code == 302

    with client.application.app_context():
        assert _get_setting_value("upload_locked") == "false"


def test_admin_grading_lock_toggle_succeeds_with_csrf(client, csrf_token):
    with client.session_transaction() as session:
        session["admin_user"] = "admin"

    exports_page = client.get("/admin/exports")
    token = csrf_token(exports_page)

    response = client.post(
        "/admin/grading/lock",
        data={"csrf_token": token, "stage": "stage_1", "state": "lock"},
        follow_redirects=False,
    )
    assert response.status_code == 302

    with client.application.app_context():
        assert _get_setting_value("grading_stage1_locked") == "true"

    exports_page = client.get("/admin/exports")
    token = csrf_token(exports_page)

    response = client.post(
        "/admin/grading/lock",
        data={"csrf_token": token, "stage": "stage_1", "state": "unlock"},
        follow_redirects=False,
    )
    assert response.status_code == 302

    with client.application.app_context():
        assert _get_setting_value("grading_stage1_locked") == "false"
