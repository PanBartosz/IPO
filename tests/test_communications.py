import ipo_app.views as views
from ipo_app.extensions import db
from ipo_app.models import (
    ActivityLog,
    CommunicationAudience,
    CommunicationCampaign,
    CommunicationRecipient,
    CommunicationRecipientRole,
    CommunicationRecipientStatus,
    CommunicationStatus,
)


def _create_campaign_with_recipients(
    *,
    subject: str,
    recipient_emails: list[str],
    recipient_statuses: list[CommunicationRecipientStatus] | None = None,
    campaign_status: CommunicationStatus = CommunicationStatus.DRAFT,
) -> int:
    if recipient_statuses is None:
        recipient_statuses = [CommunicationRecipientStatus.PENDING for _ in recipient_emails]
    assert len(recipient_emails) == len(recipient_statuses)

    campaign = CommunicationCampaign(
        subject=subject,
        html_body="<p>Hello</p>",
        text_body="Hello",
        audience=CommunicationAudience.BOTH,
        country_filter=None,
        include_absent=False,
        status=campaign_status,
        created_by="admin",
        total_recipients=len(recipient_emails),
        sent_count=0,
        failed_count=0,
    )
    for email, status in zip(recipient_emails, recipient_statuses, strict=True):
        campaign.recipients.append(
            CommunicationRecipient(
                role=CommunicationRecipientRole.TEACHER,
                teacher_id=None,
                email=email,
                first_name="Recipient",
                last_name=email.split("@")[0],
                country="Testland",
                status=status,
            )
        )
    db.session.add(campaign)
    db.session.commit()
    return campaign.id


def test_admin_communication_draft_validates_required_fields(client, csrf_token):
    with client.session_transaction() as session:
        session["admin_user"] = "admin"

    with client.application.app_context():
        before = CommunicationCampaign.query.count()

    token = csrf_token(client.get("/admin/communications/new"))
    response = client.post(
        "/admin/communications/new",
        data={
            "csrf_token": token,
            "audience": "both",
            "html_body": "<p>Hi</p>",
        },
        follow_redirects=False,
    )

    assert response.status_code == 200
    with client.application.app_context():
        after = CommunicationCampaign.query.count()
        assert after == before


def test_admin_communication_preview_does_not_send_emails(client):
    with client.application.app_context():
        campaign_id = _create_campaign_with_recipients(
            subject="Preview-only",
            recipient_emails=["preview.one@example.com", "preview.two@example.com"],
        )

    with client.session_transaction() as session:
        session["admin_user"] = "admin"

    response = client.get(f"/admin/communications/{campaign_id}/preview", follow_redirects=False)
    assert response.status_code == 200

    with client.application.app_context():
        campaign = db.session.get(CommunicationCampaign, campaign_id)
        assert campaign is not None
        assert campaign.status == CommunicationStatus.DRAFT
        assert {recipient.status for recipient in campaign.recipients} == {CommunicationRecipientStatus.PENDING}


def test_admin_communication_send_tracks_success_and_failure(client, csrf_token, monkeypatch):
    client.application.config["SENDGRID_API_KEY"] = "dummy"
    client.application.config["SENDGRID_FROM_EMAIL"] = "noreply@example.com"

    with client.application.app_context():
        campaign_id = _create_campaign_with_recipients(
            subject="Send test",
            recipient_emails=["ok@example.com", "fail@example.com"],
        )

    def _fake_send_email(to_email: str, subject: str, html_content: str, plain_text_content=None):
        if to_email == "ok@example.com":
            return True, "msg-ok", None
        return False, None, "simulated-failure"

    monkeypatch.setattr(views, "_send_email", _fake_send_email)

    with client.session_transaction() as session:
        session["admin_user"] = "admin"

    preview_page = client.get(f"/admin/communications/{campaign_id}/preview")
    token = csrf_token(preview_page)

    response = client.post(
        f"/admin/communications/{campaign_id}/preview",
        data={"csrf_token": token, "confirm": "y", "submit_send": "Send email"},
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert response.headers["Location"] == f"/admin/communications/{campaign_id}"

    with client.application.app_context():
        campaign = db.session.get(CommunicationCampaign, campaign_id)
        assert campaign is not None
        assert campaign.status == CommunicationStatus.FAILED
        assert campaign.total_recipients == 2
        assert campaign.sent_count == 1
        assert campaign.failed_count == 1
        assert campaign.sent_at is not None
        assert campaign.sent_by == "admin"

        recipients_by_email = {recipient.email: recipient for recipient in campaign.recipients}
        assert recipients_by_email["ok@example.com"].status == CommunicationRecipientStatus.SENT
        assert recipients_by_email["ok@example.com"].message_id == "msg-ok"
        assert recipients_by_email["fail@example.com"].status == CommunicationRecipientStatus.FAILED
        assert recipients_by_email["fail@example.com"].error == "simulated-failure"

        log = (
            ActivityLog.query
            .filter_by(action="communication_campaign_sent", object_type="communication_campaign", object_id=str(campaign_id))
            .first()
        )
        assert log is not None


def test_admin_communication_resend_failed_only_retries_failed_recipients(client, csrf_token, monkeypatch):
    client.application.config["SENDGRID_API_KEY"] = "dummy"
    client.application.config["SENDGRID_FROM_EMAIL"] = "noreply@example.com"

    failed_emails = {"failed.one@example.com", "failed.two@example.com"}
    sent_email = "already.sent@example.com"

    with client.application.app_context():
        campaign_id = _create_campaign_with_recipients(
            subject="Retry failed",
            recipient_emails=[sent_email, *sorted(failed_emails)],
            recipient_statuses=[
                CommunicationRecipientStatus.SENT,
                CommunicationRecipientStatus.FAILED,
                CommunicationRecipientStatus.FAILED,
            ],
            campaign_status=CommunicationStatus.FAILED,
        )

    called: list[str] = []

    def _fake_send_email(to_email: str, subject: str, html_content: str, plain_text_content=None):
        called.append(to_email)
        return True, "msg-retry", None

    monkeypatch.setattr(views, "_send_email", _fake_send_email)

    with client.session_transaction() as session:
        session["admin_user"] = "admin"

    detail_page = client.get(f"/admin/communications/{campaign_id}")
    token = csrf_token(detail_page)

    response = client.post(
        f"/admin/communications/{campaign_id}/resend-failed",
        data={"csrf_token": token, "submit_retry": "Retry failed recipients"},
        follow_redirects=False,
    )
    assert response.status_code == 302
    assert response.headers["Location"] == f"/admin/communications/{campaign_id}"

    assert set(called) == failed_emails
    assert sent_email not in called

    with client.application.app_context():
        campaign = db.session.get(CommunicationCampaign, campaign_id)
        assert campaign is not None
        assert campaign.failed_count == 0
        assert campaign.sent_count == 3
        assert campaign.status == CommunicationStatus.SENT


def test_admin_communication_send_is_blocked_without_sendgrid_configuration(client, csrf_token):
    with client.application.app_context():
        campaign_id = _create_campaign_with_recipients(
            subject="Blocked send",
            recipient_emails=["blocked.send@example.com"],
        )

    with client.session_transaction() as session:
        session["admin_user"] = "admin"

    preview_page = client.get(f"/admin/communications/{campaign_id}/preview")
    token = csrf_token(preview_page)
    response = client.post(
        f"/admin/communications/{campaign_id}/preview",
        data={"csrf_token": token, "confirm": "y"},
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert response.headers["Location"] == f"/admin/communications/{campaign_id}/preview"

    with client.application.app_context():
        campaign = db.session.get(CommunicationCampaign, campaign_id)
        assert campaign is not None
        assert campaign.status == CommunicationStatus.DRAFT
        assert {recipient.status for recipient in campaign.recipients} == {CommunicationRecipientStatus.PENDING}


def test_admin_communication_resend_failed_is_blocked_without_sendgrid_configuration(client, csrf_token):
    with client.application.app_context():
        campaign_id = _create_campaign_with_recipients(
            subject="Blocked resend",
            recipient_emails=["blocked.resend@example.com"],
            recipient_statuses=[CommunicationRecipientStatus.FAILED],
            campaign_status=CommunicationStatus.FAILED,
        )

    with client.session_transaction() as session:
        session["admin_user"] = "admin"

    detail_page = client.get(f"/admin/communications/{campaign_id}")
    token = csrf_token(detail_page)

    response = client.post(
        f"/admin/communications/{campaign_id}/resend-failed",
        data={"csrf_token": token},
        follow_redirects=False,
    )
    assert response.status_code == 302
    assert response.headers["Location"] == f"/admin/communications/{campaign_id}"

    with client.application.app_context():
        campaign = db.session.get(CommunicationCampaign, campaign_id)
        assert campaign is not None
        assert campaign.status == CommunicationStatus.FAILED
        assert {recipient.status for recipient in campaign.recipients} == {CommunicationRecipientStatus.FAILED}
