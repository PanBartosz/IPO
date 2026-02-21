def test_public_pages_render(client):
    assert client.get("/").status_code == 200
    assert client.get("/participant/login").status_code == 200
    assert client.get("/board/login").status_code == 200


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
