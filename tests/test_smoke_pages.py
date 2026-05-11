import ipo_app.views as views
from ipo_app.extensions import db


def test_public_pages_render(client):
    assert client.get("/").status_code == 200
    assert client.get("/participant/login").status_code == 200
    assert client.get("/board/login").status_code == 200


def test_homepage_hides_topics_until_visibility_toggle_is_enabled(client):
    with client.application.app_context():
        views._set_setting(views.SETTING_ESSAY_TOPICS_HTML, "<p><strong>Question A</strong></p>")
        views._set_setting(views.SETTING_ESSAY_TOPICS_VISIBLE, "false")
        db.session.commit()

    hidden_response = client.get("/")
    hidden_html = hidden_response.get_data(as_text=True)
    assert "Question A" not in hidden_html
    assert "Welcome to the IPO registration portal" in hidden_html

    with client.application.app_context():
        views._set_setting(views.SETTING_ESSAY_TOPICS_VISIBLE, "true")
        db.session.commit()

    visible_response = client.get("/")
    visible_html = visible_response.get_data(as_text=True)
    assert "<strong>Question A</strong>" in visible_html
    assert "Welcome to the IPO registration portal" not in visible_html
    assert "Register a student" not in visible_html


def test_homepage_sanitizes_enabled_topic_html(client):
    with client.application.app_context():
        views._set_setting(
            views.SETTING_ESSAY_TOPICS_HTML,
            '<p>Safe topic</p><script>alert(1)</script><a href="javascript:bad()">Unsafe link</a>',
        )
        views._set_setting(views.SETTING_ESSAY_TOPICS_VISIBLE, "true")
        db.session.commit()

    html = client.get("/").get_data(as_text=True)
    assert "Safe topic" in html
    assert "Unsafe link" in html
    assert "alert" not in html
    assert "javascript:" not in html


def test_admin_pages_render_when_logged_in(client):
    with client.session_transaction() as session:
        session["admin_user"] = "admin"

    assert client.get("/admin").status_code == 200
    assert client.get("/admin/settings").status_code == 200
    assert client.get("/admin/exports").status_code == 200
    assert client.get("/admin/logs").status_code == 200
    assert client.get("/admin/static-pages").status_code == 200


def test_rate_limits_disabled_do_not_block_repeated_logins(client, csrf_token):
    login_page = client.get("/admin/login")
    token = csrf_token(login_page)

    for _ in range(20):
        response = client.post(
            "/admin/login",
            data={
                "csrf_token": token,
                "username": "admin",
                "password": "wrong-password",
                "submit": "Sign in",
            },
            follow_redirects=False,
        )
        assert response.status_code != 429
