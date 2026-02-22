import io
import re

from werkzeug.security import generate_password_hash

from ipo_app.extensions import db
from ipo_app.models import DelegationInvite, InvitationBatchDraft, Teacher


def _extract_csrf(html: str, field_name: str) -> str:
    match = re.search(
        rf'name=["\']{re.escape(field_name)}["\'][^>]*value=["\']([^"\']+)["\']',
        html,
    )
    assert match, f"CSRF field {field_name!r} not found"
    return match.group(1)


def _login_admin(client) -> None:
    with client.session_transaction() as session:
        session["admin_user"] = "admin"


def _create_delegation_leader(email: str = "leader@example.test") -> int:
    teacher = Teacher(
        country="Testland",
        first_name="Lead",
        last_name="Teacher",
        email=email,
        school="Test School",
        languages="English",
        meal_preference="No preference",
        tshirt_size="M",
        delegation_leader=True,
        portal_username="leader",
        portal_password_hash=generate_password_hash("pass"),
    )
    db.session.add(teacher)
    db.session.commit()
    return teacher.id


def test_admin_batch_preview_is_dry_run_and_creates_draft(client, monkeypatch):
    _login_admin(client)

    def _fail_if_called(invite, inviter):  # pragma: no cover - safeguard
        raise AssertionError("Email sending should not be called during dry-run preview")

    monkeypatch.setattr("ipo_app.views._send_delegation_invite_email", _fail_if_called)

    page = client.get("/admin/invitations")
    token = _extract_csrf(page.get_data(as_text=True), "batch-upload-csrf_token")

    csv_content = (
        "first_name,last_name,email,role,country\n"
        "Ada,Lovelace,ada.lovelace@example.test,student,Poland\n"
    )
    response = client.post(
        "/admin/invitations/batch/preview",
        data={
            "batch-upload-csrf_token": token,
            "batch-upload-batch_type": "normal",
            "batch-upload-invite_file": (io.BytesIO(csv_content.encode("utf-8")), "normal.csv"),
            "batch-upload-submit_preview": "Validate and preview",
        },
        content_type="multipart/form-data",
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert response.headers["Location"].startswith("/admin/invitations?batch_draft=")

    with client.application.app_context():
        assert DelegationInvite.query.count() == 0
        draft = InvitationBatchDraft.query.first()
        assert draft is not None
        assert draft.status == "preview"
        assert draft.ready_rows == 1
        assert draft.total_rows == 1


def test_admin_batch_execute_creates_invites_and_uses_existing_email_flow(client, monkeypatch):
    _login_admin(client)

    page = client.get("/admin/invitations")
    preview_token = _extract_csrf(page.get_data(as_text=True), "batch-upload-csrf_token")

    csv_content = (
        "first_name,last_name,email,role,country\n"
        "Grace,Hopper,grace.hopper@example.test,teacher,Poland\n"
    )
    preview_response = client.post(
        "/admin/invitations/batch/preview",
        data={
            "batch-upload-csrf_token": preview_token,
            "batch-upload-batch_type": "normal",
            "batch-upload-invite_file": (io.BytesIO(csv_content.encode("utf-8")), "normal.csv"),
            "batch-upload-submit_preview": "Validate and preview",
        },
        content_type="multipart/form-data",
        follow_redirects=False,
    )
    assert preview_response.status_code == 302

    calls = []

    def _fake_send(invite, inviter):
        calls.append((invite.email, inviter.id if inviter else None))
        return True, None

    monkeypatch.setattr("ipo_app.views._send_delegation_invite_email", _fake_send)

    with client.application.app_context():
        draft = InvitationBatchDraft.query.first()
        assert draft is not None
        draft_id = draft.id

    execute_page = client.get(f"/admin/invitations?batch_draft={draft_id}")
    execute_token = _extract_csrf(execute_page.get_data(as_text=True), "batch-exec-csrf_token")

    execute_response = client.post(
        f"/admin/invitations/batch/{draft_id}/execute",
        data={
            "batch-exec-csrf_token": execute_token,
            "batch-exec-draft_id": str(draft_id),
            "batch-exec-confirm": "y",
            "batch-exec-submit_execute": "Execute batch",
        },
        follow_redirects=False,
    )
    assert execute_response.status_code == 302
    assert execute_response.headers["Location"].startswith("/admin/invitations?batch_draft=")

    with client.application.app_context():
        assert DelegationInvite.query.count() == 1
        draft = db.session.get(InvitationBatchDraft, draft_id)
        assert draft is not None
        assert draft.status == "executed"
        execution = (draft.result_payload or {}).get("execution", {})
        assert execution.get("created_rows") == 1
        assert execution.get("email_sent") == 1

    assert calls == [("grace.hopper@example.test", None)]


def test_admin_batch_preview_delegation_mode_resolves_leader_by_email(client):
    _login_admin(client)

    with client.application.app_context():
        leader_id = _create_delegation_leader(email="leader.country@example.test")

    page = client.get("/admin/invitations")
    token = _extract_csrf(page.get_data(as_text=True), "batch-upload-csrf_token")

    csv_content = (
        "first_name,last_name,email,role,delegation_leader_email\n"
        "Marie,Curie,marie.curie@example.test,student,LEADER.COUNTRY@example.test\n"
    )
    response = client.post(
        "/admin/invitations/batch/preview",
        data={
            "batch-upload-csrf_token": token,
            "batch-upload-batch_type": "delegation",
            "batch-upload-invite_file": (io.BytesIO(csv_content.encode("utf-8")), "delegation.csv"),
            "batch-upload-submit_preview": "Validate and preview",
        },
        content_type="multipart/form-data",
        follow_redirects=False,
    )

    assert response.status_code == 302

    with client.application.app_context():
        draft = InvitationBatchDraft.query.first()
        assert draft is not None
        assert draft.ready_rows == 1
        rows = (draft.result_payload or {}).get("rows", [])
        assert rows
        request_payload = rows[0].get("request") or {}
        assert request_payload.get("inviter_id") == leader_id
        assert request_payload.get("country") == "Testland"
