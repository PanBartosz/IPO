from __future__ import annotations

from importlib import import_module
from io import BytesIO

import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations
from werkzeug.security import check_password_hash, generate_password_hash

import ipo_app.views as views
from ipo_app.extensions import db
from ipo_app.models import ActivityLog, AppSetting, EssayUpload, FileBinUpload


def _set_setting(key: str, value: str) -> None:
    existing = AppSetting.query.filter_by(key=key).first()
    if existing:
        existing.value = value
    else:
        db.session.add(AppSetting(key=key, value=value))
    db.session.commit()


def _login_admin(client) -> None:
    with client.session_transaction() as session:
        session["admin_user"] = "admin"


def _enable_file_bin(code: str = "emergency-code") -> None:
    _set_setting(views.SETTING_FILE_BIN_ENABLED, "true")
    _set_setting(views.SETTING_FILE_BIN_ACCESS_CODE_HASH, generate_password_hash(code))


def _csrf_from_path(client, csrf_token, path: str) -> str:
    return csrf_token(client.get(path))


def test_file_bin_closed_rejects_upload_without_creating_record(client, csrf_token):
    response = client.get("/file-bin")
    assert response.status_code == 200
    assert "Emergency File Bin is currently unavailable." in response.get_data(as_text=True)

    token = _csrf_from_path(client, csrf_token, "/admin/login")
    response = client.post(
        "/file-bin",
        data={
            "csrf_token": token,
            "access_code": "anything",
            "staff_name": "Room Staff",
            "room": "A1",
            "student_identifier": "Essay 12",
            "note": "Upload failed",
            "file": (BytesIO(b"essay text"), "essay.txt"),
        },
        follow_redirects=False,
        content_type="multipart/form-data",
    )

    assert response.status_code == 302
    with client.application.app_context():
        assert FileBinUpload.query.count() == 0


def test_file_bin_rejects_invalid_code_and_logs_attempt(client, csrf_token):
    with client.application.app_context():
        _enable_file_bin("correct-code")

    page = client.get("/file-bin")
    token = csrf_token(page)
    response = client.post(
        "/file-bin",
        data={
            "csrf_token": token,
            "access_code": "wrong-code",
            "staff_name": "Room Staff",
            "room": "B2",
            "student_identifier": "Essay 17",
            "note": "Upload failed",
            "file": (BytesIO(b"essay text"), "essay.txt"),
        },
        follow_redirects=False,
        content_type="multipart/form-data",
    )

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "Invalid emergency code." in html
    with client.application.app_context():
        assert FileBinUpload.query.count() == 0
        log = ActivityLog.query.filter_by(action="file_bin_upload_rejected").order_by(ActivityLog.id.desc()).first()
        assert log is not None
        assert log.details["student_identifier"] == "Essay 17"


def test_file_bin_valid_upload_is_quarantined_and_not_official_essay(client, csrf_token):
    with client.application.app_context():
        _enable_file_bin("correct-code")

    page = client.get("/file-bin")
    token = csrf_token(page)
    response = client.post(
        "/file-bin",
        data={
            "csrf_token": token,
            "access_code": "correct-code",
            "staff_name": "Room Staff",
            "room": "C3",
            "student_identifier": "Essay 23",
            "note": "Student upload page failed",
            "file": (BytesIO(b"emergency essay content"), "essay.txt"),
        },
        follow_redirects=False,
        content_type="multipart/form-data",
    )

    assert response.status_code == 302
    with client.application.app_context():
        upload = FileBinUpload.query.one()
        assert upload.staff_name == "Room Staff"
        assert upload.room == "C3"
        assert upload.student_identifier == "Essay 23"
        assert upload.original_filename == "essay.txt"
        assert upload.stored_filename.startswith("file-bin-")
        assert not upload.reviewed
        assert EssayUpload.query.count() == 0
        file_path = views._file_bin_upload_path(upload)
        assert file_path.exists()
        assert file_path.read_bytes() == b"emergency essay content"


def test_admin_file_bin_settings_require_code_before_enabling(client, csrf_token):
    _login_admin(client)

    page = client.get("/admin/file-bin")
    token = csrf_token(page)
    response = client.post(
        "/admin/file-bin",
        data={
            "csrf_token": token,
            "action": "settings",
            "enabled": "y",
            "access_code": "",
        },
        follow_redirects=False,
    )

    assert response.status_code == 200
    assert "Set an emergency code before enabling File Bin." in response.get_data(as_text=True)
    with client.application.app_context():
        assert AppSetting.query.filter_by(key=views.SETTING_FILE_BIN_ENABLED).first() is None


def test_admin_can_configure_download_and_mark_file_bin_upload_reviewed(client, csrf_token):
    _login_admin(client)

    page = client.get("/admin/file-bin")
    token = csrf_token(page)
    response = client.post(
        "/admin/file-bin",
        data={
            "csrf_token": token,
            "action": "settings",
            "enabled": "y",
            "access_code": "new-emergency-code",
        },
        follow_redirects=False,
    )
    assert response.status_code == 302

    with client.application.app_context():
        enabled = AppSetting.query.filter_by(key=views.SETTING_FILE_BIN_ENABLED).one()
        code_hash = AppSetting.query.filter_by(key=views.SETTING_FILE_BIN_ACCESS_CODE_HASH).one()
        assert enabled.value == "true"
        assert code_hash.value != "new-emergency-code"
        assert check_password_hash(code_hash.value, "new-emergency-code")

    page = client.get("/file-bin")
    token = csrf_token(page)
    response = client.post(
        "/file-bin",
        data={
            "csrf_token": token,
            "access_code": "new-emergency-code",
            "staff_name": "Room Staff",
            "room": "D4",
            "student_identifier": "Essay 31",
            "note": "Emergency transfer",
            "file": (BytesIO(b"download me"), "essay.txt"),
        },
        follow_redirects=False,
        content_type="multipart/form-data",
    )
    assert response.status_code == 302

    with client.application.app_context():
        upload_id = FileBinUpload.query.one().id

    download = client.get(f"/admin/file-bin/{upload_id}/download")
    assert download.status_code == 200
    assert download.data == b"download me"
    assert "attachment" in download.headers["Content-Disposition"]

    page = client.get("/admin/file-bin")
    token = csrf_token(page)
    response = client.post(
        "/admin/file-bin",
        data={
            "csrf_token": token,
            "action": "mark_reviewed",
            "upload_id": str(upload_id),
            "reviewed": "1",
            "admin_note": "Recovered into official flow manually",
        },
        follow_redirects=False,
    )

    assert response.status_code == 302
    with client.application.app_context():
        upload = db.session.get(FileBinUpload, upload_id)
        assert upload is not None
        assert upload.reviewed is True
        assert upload.reviewed_by == "admin"
        assert upload.reviewed_at is not None
        assert upload.admin_note == "Recovered into official flow manually"


def test_file_bin_migration_creates_and_drops_upload_table(tmp_path, monkeypatch):
    migration = import_module("migrations.versions.b7c9d1e2f3a4_add_file_bin_uploads")
    engine = sa.create_engine(f"sqlite:///{tmp_path / 'migration.db'}")

    with engine.begin() as connection:
        context = MigrationContext.configure(connection)
        monkeypatch.setattr(migration, "op", Operations(context))

        migration.upgrade()
        migration.upgrade()

        inspector = sa.inspect(connection)
        assert "file_bin_uploads" in inspector.get_table_names()
        columns = {column["name"] for column in inspector.get_columns("file_bin_uploads")}
        assert {
            "id",
            "staff_name",
            "student_identifier",
            "original_filename",
            "stored_filename",
            "reviewed",
            "admin_note",
        }.issubset(columns)
        indexes = {index["name"] for index in inspector.get_indexes("file_bin_uploads")}
        assert "ix_file_bin_upload_reviewed" in indexes
        assert "ix_file_bin_upload_created_at" in indexes

        migration.downgrade()

        inspector = sa.inspect(connection)
        assert "file_bin_uploads" not in inspector.get_table_names()
