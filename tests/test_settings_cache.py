from sqlalchemy import event

import ipo_app.views as views
from ipo_app.extensions import db
from ipo_app.models import AppSetting


def test_settings_page_reads_settings_once(client):
    with client.session_transaction() as session:
        session["admin_user"] = "admin"

    with client.application.app_context():
        engine = db.engine
    settings_queries = []

    def count_settings_queries(connection, cursor, statement, parameters, context, executemany):
        if statement.lstrip().upper().startswith("SELECT") and "FROM app_settings" in statement:
            settings_queries.append(statement)

    event.listen(engine, "before_cursor_execute", count_settings_queries)
    try:
        response = client.get("/admin/settings")
    finally:
        event.remove(engine, "before_cursor_execute", count_settings_queries)

    assert response.status_code == 200
    assert len(settings_queries) == 1


def test_setting_changes_and_rollbacks_are_visible_in_same_request(app):
    with app.app_context():
        db.session.add(AppSetting(key="review-setting", value="original"))
        db.session.commit()

    with app.test_request_context():
        assert views._get_setting("review-setting") == "original"
        views._set_setting("review-setting", "changed")
        assert views._get_setting("review-setting") == "changed"
        db.session.rollback()
        assert views._get_setting("review-setting") == "original"
        views._set_setting("review-setting", "committed")
        db.session.commit()
        assert views._get_setting("review-setting") == "committed"
        views._set_setting("missing-setting", "new")
        assert views._get_setting("missing-setting") == "new"
        db.session.rollback()
        assert views._get_setting("missing-setting", "fallback") == "fallback"


def test_settings_snapshot_does_not_leak_into_next_request(app):
    with app.app_context():
        db.session.add_all([
            AppSetting(key="review-setting", value="original"),
            AppSetting(key="empty-setting", value=""),
            AppSetting(key="null-setting", value=None),
        ])
        db.session.commit()

        with app.test_request_context():
            assert views._get_setting("review-setting") == "original"
            assert views._get_setting("empty-setting", "fallback") == ""
            assert views._get_setting("null-setting", "fallback") == "fallback"
            assert views._get_setting("missing-setting", "fallback") == "fallback"

        # Keep the outer app context alive, as Flask's test client can do.
        AppSetting.query.filter_by(key="review-setting").update({"value": "updated"})
        db.session.commit()

        with app.test_request_context():
            assert views._get_setting("review-setting") == "updated"
