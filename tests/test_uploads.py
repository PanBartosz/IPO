import io
from datetime import date, datetime
from pathlib import Path

from werkzeug.security import generate_password_hash

from ipo_app.extensions import db
from ipo_app.models import AppSetting, EssayUpload, Student


def _set_setting(key: str, value: str) -> None:
    existing = AppSetting.query.filter_by(key=key).first()
    if existing:
        existing.value = value
    else:
        db.session.add(AppSetting(key=key, value=value))
    db.session.commit()


def _create_student(username: str, password: str) -> int:
    student = Student(
        country="Testland",
        first_name="Student",
        last_name="Uploader",
        email=f"{username}@example.test",
        school="Test School",
        date_of_birth=date(2000, 1, 1),
        essay_language="English",
        keyboard_preference="QWERTY",
        meal_preference="No preference",
        upload_username=username,
        upload_password_hash=generate_password_hash(password),
    )
    db.session.add(student)
    db.session.commit()
    return student.id


def _login_student(client, csrf_token, username: str, password: str) -> None:
    login_page = client.get("/participant/login")
    token = csrf_token(login_page)
    response = client.post(
        "/participant/login",
        data={
            "csrf_token": token,
            "username": username,
            "password": password,
            "submit": "Sign in",
        },
        follow_redirects=False,
    )
    assert response.status_code == 302


def test_student_upload_stores_file_and_creates_upload_row(client, csrf_token):
    with client.application.app_context():
        _set_setting("essay_upload_enabled", "true")
        student_id = _create_student("student-uploader", "student-pass")

    _login_student(client, csrf_token, "student-uploader", "student-pass")

    upload_page = client.get("/participant/upload")
    token = csrf_token(upload_page)

    pdf_bytes = b"%PDF-1.4\n% test\n1 0 obj\n<<>>\nendobj\ntrailer\n<<>>\n%%EOF\n"

    response = client.post(
        "/participant/upload",
        data={
            "csrf_token": token,
            "essay": (io.BytesIO(pdf_bytes), "essay.pdf"),
            "submit": "Upload essay",
        },
        content_type="multipart/form-data",
        follow_redirects=False,
    )

    assert response.status_code == 302

    with client.application.app_context():
        refreshed = db.session.get(Student, student_id)
        assert refreshed is not None
        assert refreshed.uploaded_filename

        uploads = EssayUpload.query.filter_by(student_id=student_id).all()
        assert len(uploads) == 1

        upload_folder = Path(client.application.config["UPLOAD_FOLDER"])
        assert (upload_folder / refreshed.uploaded_filename).exists()


def test_student_upload_rejects_oversize_file(client, csrf_token, monkeypatch):
    import ipo_app.views as views

    monkeypatch.setattr(views, "MAX_UPLOAD_SIZE", 10)

    with client.application.app_context():
        _set_setting("essay_upload_enabled", "true")
        student_id = _create_student("student-oversize", "student-pass")

    _login_student(client, csrf_token, "student-oversize", "student-pass")

    upload_page = client.get("/participant/upload")
    token = csrf_token(upload_page)

    response = client.post(
        "/participant/upload",
        data={
            "csrf_token": token,
            "essay": (io.BytesIO(b"x" * 11), "essay.pdf"),
            "submit": "Upload essay",
        },
        content_type="multipart/form-data",
        follow_redirects=False,
    )

    assert response.status_code == 302

    with client.application.app_context():
        refreshed = db.session.get(Student, student_id)
        assert refreshed is not None
        assert refreshed.uploaded_filename is None

        uploads = EssayUpload.query.filter_by(student_id=student_id).all()
        assert uploads == []


def test_student_upload_is_blocked_when_module_disabled(client, csrf_token):
    with client.application.app_context():
        student_id = _create_student("student-disabled", "student-pass")

    _login_student(client, csrf_token, "student-disabled", "student-pass")

    token = csrf_token(client.get("/participant/login"))
    response = client.post(
        "/participant/upload",
        data={
            "csrf_token": token,
            "essay": (io.BytesIO(b"%PDF-1.4\n%%EOF\n"), "essay.pdf"),
            "submit": "Upload essay",
        },
        content_type="multipart/form-data",
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert response.headers["Location"].startswith("/participant/upload")

    with client.application.app_context():
        refreshed = db.session.get(Student, student_id)
        assert refreshed is not None
        assert refreshed.uploaded_filename is None
        assert EssayUpload.query.filter_by(student_id=student_id).all() == []

    upload_folder = Path(client.application.config["UPLOAD_FOLDER"])
    assert list(upload_folder.glob("*.pdf")) == []


def test_student_finalize_is_blocked_when_module_disabled(client, csrf_token):
    with client.application.app_context():
        student_id = _create_student("student-disabled-finalize", "student-pass")
        student = db.session.get(Student, student_id)
        assert student is not None
        student.uploaded_filename = f"student-{student_id}-finalize.pdf"
        db.session.commit()

    _login_student(client, csrf_token, "student-disabled-finalize", "student-pass")

    token = csrf_token(client.get("/participant/login"))
    response = client.post(
        "/participant/upload",
        data={"csrf_token": token, "action": "finalize"},
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert response.headers["Location"].startswith("/participant/upload")

    with client.application.app_context():
        refreshed = db.session.get(Student, student_id)
        assert refreshed is not None
        assert refreshed.essay_finalized is False


def test_student_upload_is_blocked_when_upload_locked(client, csrf_token):
    with client.application.app_context():
        _set_setting("essay_upload_enabled", "true")
        _set_setting("upload_locked", "true")
        student_id = _create_student("student-locked", "student-pass")

    _login_student(client, csrf_token, "student-locked", "student-pass")

    token = csrf_token(client.get("/participant/login"))
    response = client.post(
        "/participant/upload",
        data={
            "csrf_token": token,
            "essay": (io.BytesIO(b"%PDF-1.4\n%%EOF\n"), "essay.pdf"),
            "submit": "Upload essay",
        },
        content_type="multipart/form-data",
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert response.headers["Location"].startswith("/participant/upload")

    with client.application.app_context():
        refreshed = db.session.get(Student, student_id)
        assert refreshed is not None
        assert refreshed.uploaded_filename is None
        assert EssayUpload.query.filter_by(student_id=student_id).all() == []

    upload_folder = Path(client.application.config["UPLOAD_FOLDER"])
    assert list(upload_folder.glob("*.pdf")) == []


def test_student_finalize_is_blocked_when_upload_locked(client, csrf_token):
    with client.application.app_context():
        _set_setting("essay_upload_enabled", "true")
        _set_setting("upload_locked", "true")
        student_id = _create_student("student-locked-finalize", "student-pass")
        student = db.session.get(Student, student_id)
        assert student is not None
        student.uploaded_filename = f"student-{student_id}-finalize.pdf"
        db.session.commit()

    _login_student(client, csrf_token, "student-locked-finalize", "student-pass")

    token = csrf_token(client.get("/participant/login"))
    response = client.post(
        "/participant/upload",
        data={"csrf_token": token, "action": "finalize"},
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert response.headers["Location"].startswith("/participant/upload")

    with client.application.app_context():
        refreshed = db.session.get(Student, student_id)
        assert refreshed is not None
        assert refreshed.essay_finalized is False


def test_student_upload_rejects_non_pdf_extension(client, csrf_token):
    with client.application.app_context():
        _set_setting("essay_upload_enabled", "true")
        student_id = _create_student("student-nonpdf", "student-pass")

    _login_student(client, csrf_token, "student-nonpdf", "student-pass")

    upload_page = client.get("/participant/upload")
    token = csrf_token(upload_page)

    response = client.post(
        "/participant/upload",
        data={
            "csrf_token": token,
            "essay": (io.BytesIO(b"not-a-pdf"), "essay.txt"),
            "submit": "Upload essay",
        },
        content_type="multipart/form-data",
        follow_redirects=False,
    )

    assert response.status_code == 200
    assert "PDF only" in response.get_data(as_text=True)

    with client.application.app_context():
        refreshed = db.session.get(Student, student_id)
        assert refreshed is not None
        assert refreshed.uploaded_filename is None
        assert EssayUpload.query.filter_by(student_id=student_id).all() == []


def test_student_finalize_requires_prior_upload(client, csrf_token):
    with client.application.app_context():
        _set_setting("essay_upload_enabled", "true")
        student_id = _create_student("student-finalize", "student-pass")

    _login_student(client, csrf_token, "student-finalize", "student-pass")

    upload_page = client.get("/participant/upload")
    token = csrf_token(upload_page)

    response = client.post(
        "/participant/upload",
        data={"csrf_token": token, "action": "finalize"},
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert response.headers["Location"].startswith("/participant/upload")

    with client.application.app_context():
        refreshed = db.session.get(Student, student_id)
        assert refreshed is not None
        assert refreshed.essay_finalized is False


def test_student_finalize_sets_essay_finalized(client, csrf_token):
    with client.application.app_context():
        _set_setting("essay_upload_enabled", "true")
        student_id = _create_student("student-finalize-success", "student-pass")

    _login_student(client, csrf_token, "student-finalize-success", "student-pass")

    upload_page = client.get("/participant/upload")
    token = csrf_token(upload_page)

    response = client.post(
        "/participant/upload",
        data={
            "csrf_token": token,
            "essay": (io.BytesIO(b"%PDF-1.4\n%%EOF\n"), "essay.pdf"),
            "submit": "Upload essay",
        },
        content_type="multipart/form-data",
        follow_redirects=False,
    )
    assert response.status_code == 302

    finalize_page = client.get("/participant/upload")
    token = csrf_token(finalize_page)

    response = client.post(
        "/participant/upload",
        data={"csrf_token": token, "action": "finalize"},
        follow_redirects=False,
    )
    assert response.status_code == 302

    with client.application.app_context():
        refreshed = db.session.get(Student, student_id)
        assert refreshed is not None
        assert refreshed.essay_finalized is True
        assert refreshed.essay_finalized_at is not None

        upload_entry = (
            EssayUpload.query
            .filter_by(student_id=student_id, filename=refreshed.uploaded_filename)
            .first()
        )
        assert upload_entry is not None
        assert upload_entry.finalized_at is not None


def test_student_hard_word_limit_blocks_finalization(client, csrf_token):
    with client.application.app_context():
        _set_setting("essay_upload_enabled", "true")
        _set_setting("essay_word_limit_mode", "hard")
        _set_setting("essay_word_limit_words", "1")
        student_id = _create_student("student-wordlimit", "student-pass")
        student = db.session.get(Student, student_id)
        assert student is not None
        student.uploaded_filename = f"student-{student_id}-wordlimit.pdf"
        student.uploaded_at = datetime.utcnow()
        student.essay_word_count = 2
        db.session.commit()

    _login_student(client, csrf_token, "student-wordlimit", "student-pass")

    upload_page = client.get("/participant/upload")
    token = csrf_token(upload_page)

    response = client.post(
        "/participant/upload",
        data={"csrf_token": token, "action": "finalize"},
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert response.headers["Location"].startswith("/participant/upload")

    with client.application.app_context():
        refreshed = db.session.get(Student, student_id)
        assert refreshed is not None
        assert refreshed.essay_finalized is False
        assert refreshed.essay_finalized_at is None


def test_student_preview_is_allowed_after_upload(client, csrf_token):
    with client.application.app_context():
        student_id = _create_student("student-preview", "student-pass")
        student = db.session.get(Student, student_id)
        assert student is not None
        student.uploaded_filename = f"student-{student_id}-preview.pdf"
        db.session.commit()

        upload_folder = Path(client.application.config["UPLOAD_FOLDER"])
        (upload_folder / student.uploaded_filename).write_bytes(b"%PDF-1.4\n% preview\n%%EOF\n")

    _login_student(client, csrf_token, "student-preview", "student-pass")

    response = client.get("/participant/upload/preview", follow_redirects=False)
    assert response.status_code == 200
    assert "application/pdf" in response.headers.get("Content-Type", "")
    assert response.headers.get("Cache-Control") == "no-store"


def test_student_download_is_blocked_before_event_end(client, csrf_token):
    with client.application.app_context():
        student_id = _create_student("student-download-blocked", "student-pass")
        student = db.session.get(Student, student_id)
        assert student is not None
        student.uploaded_filename = f"student-{student_id}-download.pdf"
        db.session.commit()

        upload_folder = Path(client.application.config["UPLOAD_FOLDER"])
        (upload_folder / student.uploaded_filename).write_bytes(b"%PDF-1.4\n% download\n%%EOF\n")

    _login_student(client, csrf_token, "student-download-blocked", "student-pass")

    response = client.get("/participant/upload/download", follow_redirects=False)
    assert response.status_code == 403


def test_student_download_is_allowed_after_event_end_override(client, csrf_token):
    with client.application.app_context():
        _set_setting("event_end_override", "force_end")
        student_id = _create_student("student-download-open", "student-pass")
        student = db.session.get(Student, student_id)
        assert student is not None
        student.uploaded_filename = f"student-{student_id}-download.pdf"
        db.session.commit()

        upload_folder = Path(client.application.config["UPLOAD_FOLDER"])
        (upload_folder / student.uploaded_filename).write_bytes(b"%PDF-1.4\n% download\n%%EOF\n")

    _login_student(client, csrf_token, "student-download-open", "student-pass")

    response = client.get("/participant/upload/download", follow_redirects=False)
    assert response.status_code == 200
    assert "application/pdf" in response.headers.get("Content-Type", "")
    assert "attachment" in response.headers.get("Content-Disposition", "")


def test_student_upload_history_download_returns_404_for_wrong_student(client, csrf_token):
    with client.application.app_context():
        _set_setting("event_end_override", "force_end")
        owner_id = _create_student("student-history-owner", "student-pass")
        other_id = _create_student("student-history-other", "student-pass")

        owner = db.session.get(Student, owner_id)
        other = db.session.get(Student, other_id)
        assert owner is not None
        assert other is not None

        owner.uploaded_filename = f"student-{owner_id}-current.pdf"
        other.uploaded_filename = f"student-{other_id}-current.pdf"
        db.session.add(EssayUpload(student_id=owner_id, filename=f"student-{owner_id}-v1.pdf"))
        db.session.commit()

        upload = EssayUpload.query.filter_by(student_id=owner_id).first()
        assert upload is not None
        upload_id = upload.id

    _login_student(client, csrf_token, "student-history-other", "student-pass")

    response = client.get(f"/participant/upload/history/{upload_id}/download", follow_redirects=False)
    assert response.status_code == 404
