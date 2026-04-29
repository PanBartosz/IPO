from datetime import datetime
from types import SimpleNamespace

import ipo_app.views as views
from ipo_app.extensions import db
from ipo_app.models import AppSetting


EMAIL_TEMPLATE_FIELDS = (
    "email_student_subject",
    "email_student_body",
    "email_teacher_subject",
    "email_teacher_body",
    "email_student_invite_subject",
    "email_student_invite_body",
    "email_teacher_invite_subject",
    "email_teacher_invite_body",
    "email_message_subject",
    "email_message_body",
    "email_survey_publish_subject",
    "email_survey_publish_body",
    "email_survey_reminder_subject",
    "email_survey_reminder_body",
    "email_student_reset_link_subject",
    "email_student_reset_link_body",
    "email_student_reset_subject",
    "email_student_reset_body",
    "email_teacher_reset_link_subject",
    "email_teacher_reset_link_body",
    "email_teacher_reset_subject",
    "email_teacher_reset_body",
)


def _login_admin_session(client) -> None:
    with client.session_transaction() as session:
        session["admin_user"] = "admin"


def _setting_row(key: str) -> AppSetting | None:
    return AppSetting.query.filter_by(key=key).first()


def _settings_payload(csrf: str, **overrides) -> dict[str, str]:
    payload = {field: "" for field in EMAIL_TEMPLATE_FIELDS}
    payload.update(
        {
            "csrf_token": csrf,
            "event_end_override": "auto",
            "packet_print_mode": "single",
            "essay_word_limit_mode": "soft",
            "submit": "Save settings",
        }
    )
    payload.update(overrides)
    return payload


def test_admin_settings_persists_core_options_and_normalizes_blank_email_templates(client, csrf_token):
    _login_admin_session(client)

    token = csrf_token(client.get("/admin/settings"))
    response = client.post(
        "/admin/settings",
        data=_settings_payload(
            token,
            upload_deadline="2026-04-01T09:15",
            stage2_deadline="2026-04-05T11:45",
            event_end="2026-04-10T18:30",
            event_end_override="force_open",
            stage1_sla="12",
            stage2_sla="36",
            packet_print_mode="double",
            essay_word_limit="2750",
            essay_word_limit_mode="hard",
            stage1_trim_extreme_scores_enabled="y",
            ethics_consent_html="  <p>Ethics</p>  ",
            gdpr_notice_html="  <p>GDPR</p>  ",
            photo_consent_html="  <p>Photo</p>  ",
            assessor_competence_html="  <p>Competence</p>  ",
            accommodation_info_html="  <p>Accommodation</p>  ",
            essay_upload_enabled="y",
            teacher_portal_enabled="y",
            registration_invite_only="y",
            login_email_enabled="y",
            login_folded_alias_enabled="y",
            email_auto_enabled="y",
            email_student_subject="  Student subject  ",
            email_student_body="  Student body  ",
        ),
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/admin/settings")

    with client.application.app_context():
        assert _setting_row(views.SETTING_UPLOAD_DEADLINE).value == "2026-04-01T09:15"
        assert _setting_row(views.SETTING_STAGE2_DEADLINE).value == "2026-04-05T11:45"
        assert _setting_row(views.SETTING_EVENT_END).value == "2026-04-10T18:30"
        assert _setting_row(views.SETTING_EVENT_END_OVERRIDE).value == "force_open"
        assert _setting_row(views.SETTING_STAGE1_SLA).value == "12"
        assert _setting_row(views.SETTING_STAGE2_SLA).value == "36"
        assert _setting_row(views.SETTING_PACKET_PRINT_MODE).value == "double"
        assert _setting_row(views.SETTING_ESSAY_WORD_LIMIT).value == "2750"
        assert _setting_row(views.SETTING_ESSAY_WORD_LIMIT_MODE).value == "hard"
        assert _setting_row(views.SETTING_STAGE1_TRIM_EXTREME_SCORES).value == "true"
        assert _setting_row(views.SETTING_ETHICS_CONSENT_HTML).value == "<p>Ethics</p>"
        assert _setting_row(views.SETTING_GDPR_NOTICE_HTML).value == "<p>GDPR</p>"
        assert _setting_row(views.SETTING_PHOTO_CONSENT_HTML).value == "<p>Photo</p>"
        assert _setting_row(views.SETTING_TEACHER_COMPETENCE_HTML).value == "<p>Competence</p>"
        assert _setting_row(views.SETTING_ACCOMMODATION_INFO_HTML).value == "<p>Accommodation</p>"
        assert _setting_row(views.SETTING_UPLOAD_MODULE_ENABLED).value == "true"
        assert _setting_row(views.SETTING_TEACHER_PORTAL_ENABLED).value == "true"
        assert _setting_row(views.SETTING_REGISTRATION_INVITE_ONLY).value == "true"
        assert _setting_row(views.SETTING_LOGIN_EMAIL_ENABLED).value == "true"
        assert _setting_row(views.SETTING_LOGIN_FOLDED_ALIAS_ENABLED).value == "true"
        assert _setting_row(views.SETTING_EMAIL_AUTOMATION_ENABLED).value == "true"
        assert _setting_row(views.SETTING_EMAIL_STUDENT_SUBJECT).value == "Student subject"
        assert _setting_row(views.SETTING_EMAIL_STUDENT_BODY).value == "Student body"

        blank_subject = _setting_row(views.SETTING_EMAIL_TEACHER_SUBJECT)
        assert blank_subject is not None
        assert blank_subject.value is None


def test_settings_helpers_fall_back_to_safe_defaults_for_invalid_values(client):
    with client.application.app_context():
        views._set_setting(views.SETTING_ESSAY_WORD_LIMIT, "not-a-number")
        views._set_setting(views.SETTING_ESSAY_WORD_LIMIT_MODE, "mystery")
        views._set_setting(views.SETTING_EVENT_END_OVERRIDE, "unknown")
        views._set_setting(views.SETTING_PACKET_PRINT_MODE, "duplex-ish")
        db.session.commit()

        assert views._essay_word_limit() == views.DEFAULT_ESSAY_WORD_LIMIT
        assert views._essay_word_limit_mode() == views.DEFAULT_ESSAY_WORD_LIMIT_MODE
        assert views._event_end_override() == "auto"
        assert views._packets_double_sided() is False

        views._set_setting(views.SETTING_ESSAY_WORD_LIMIT, "0")
        db.session.commit()
        assert views._essay_word_limit() == 1


def test_fold_login_username_handles_non_decomposing_latin_letters():
    assert views._fold_login_username("Żółć-Æsir-Œuvre-ß-Øresund-Đurić-Iı") == "zolc-aesir-oeuvre-ss-oresund-duric-ii"


def test_login_alias_diagnostics_report_student_and_teacher_conflicts(client):
    from ipo_app.models import Student, Teacher

    with client.application.app_context():
        db.session.add(
            Student(
                country="Testland",
                first_name="Student",
                last_name="One",
                email="student.one@example.test",
                school="School",
                date_of_birth=datetime(2000, 1, 1).date(),
                essay_language="English",
                keyboard_preference="QWERTY",
                meal_preference="No preference",
                upload_username="żuk1",
            )
        )
        db.session.add(
            Student(
                country="Testland",
                first_name="Student",
                last_name="Two",
                email="student.two@example.test",
                school="School",
                date_of_birth=datetime(2000, 1, 2).date(),
                essay_language="English",
                keyboard_preference="QWERTY",
                meal_preference="No preference",
                upload_username="źuk1",
            )
        )
        db.session.add(
            Teacher(
                country="Testland",
                first_name="Teacher",
                last_name="One",
                email="teacher.one@example.test",
                school="School",
                languages="English",
                meal_preference="No preference",
                tshirt_size="M",
                portal_username="łukasz1",
            )
        )
        db.session.add(
            Teacher(
                country="Testland",
                first_name="Teacher",
                last_name="Two",
                email="teacher.two@example.test",
                school="School",
                languages="English",
                meal_preference="No preference",
                tshirt_size="M",
                portal_username="lukasz1",
            )
        )
        db.session.commit()

        diagnostics = views._login_alias_diagnostics()

        assert diagnostics["all_safe"] is False
        assert diagnostics["students"]["safe"] is False
        assert diagnostics["students"]["conflicts"][0]["folded_username"] == "zuk1"
        assert [entry["username"] for entry in diagnostics["students"]["conflicts"][0]["entries"]] == ["źuk1", "żuk1"]
        assert diagnostics["teachers"]["safe"] is False
        assert diagnostics["teachers"]["conflicts"][0]["folded_username"] == "lukasz1"
        assert [entry["username"] for entry in diagnostics["teachers"]["conflicts"][0]["entries"]] == ["lukasz1", "łukasz1"]


def test_admin_settings_rejects_enabling_folded_login_when_student_conflicts_exist(client, csrf_token):
    from ipo_app.models import Student

    _login_admin_session(client)

    with client.application.app_context():
        db.session.add(
            Student(
                country="Testland",
                first_name="Student",
                last_name="One",
                email="student.conflict.one@example.test",
                school="School",
                date_of_birth=datetime(2000, 2, 1).date(),
                essay_language="English",
                keyboard_preference="QWERTY",
                meal_preference="No preference",
                upload_username="żuk1",
            )
        )
        db.session.add(
            Student(
                country="Testland",
                first_name="Student",
                last_name="Two",
                email="student.conflict.two@example.test",
                school="School",
                date_of_birth=datetime(2000, 2, 2).date(),
                essay_language="English",
                keyboard_preference="QWERTY",
                meal_preference="No preference",
                upload_username="źuk1",
            )
        )
        db.session.commit()

    token = csrf_token(client.get("/admin/settings"))
    response = client.post(
        "/admin/settings",
        data=_settings_payload(token, login_folded_alias_enabled="y"),
        follow_redirects=False,
    )

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "Cannot enable folded login aliases until all folded student and teacher usernames are unique." in html
    assert "zuk1" in html
    assert "żuk1" in html
    assert "źuk1" in html

    with client.application.app_context():
        assert views._get_setting(views.SETTING_LOGIN_FOLDED_ALIAS_ENABLED) is None


def test_admin_settings_shows_safe_folded_login_diagnostics(client):
    _login_admin_session(client)

    response = client.get("/admin/settings")

    html = response.get_data(as_text=True)
    assert response.status_code == 200
    assert "Folded Username Uniqueness Check" in html
    assert "Students:</strong> 0 usernames checked. No folded conflicts found." in html
    assert "Teachers:</strong> 0 usernames checked. No folded conflicts found." in html


def test_event_access_overrides_control_downloads_and_notice_text(client):
    now = datetime(2026, 4, 1, 12, 0)
    student = SimpleNamespace(uploaded_filename="essay.pdf")

    with client.application.app_context():
        views._set_setting(views.SETTING_EVENT_END, "2026-04-10T18:30")
        views._set_setting(views.SETTING_EVENT_END_OVERRIDE, "force_open")
        db.session.commit()

        access = views._student_essay_access(student, now=now)
        assert access.download_allowed is False
        assert access.event_over is False
        assert access.override == "force_open"
        assert views._essay_download_notice(access) == "Downloads are temporarily locked by the organizing team."

        views._set_setting(views.SETTING_EVENT_END_OVERRIDE, "force_end")
        db.session.commit()

        access = views._student_essay_access(student, now=now)
        assert access.download_allowed is True
        assert access.event_over is True
        assert views._essay_download_notice(access) is None

        views._set_setting(views.SETTING_EVENT_END_OVERRIDE, "broken")
        db.session.commit()

        access = views._student_essay_access(student, now=now)
        assert access.override == "auto"
        assert access.download_allowed is False
        assert views._essay_download_notice(access) == "Downloads unlock after the event ends (2026-04-10 18:30 UTC)."
