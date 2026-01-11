import csv
import io
import zipfile
from datetime import date, datetime
from pathlib import Path
import re

from openpyxl import load_workbook

from ipo_app.extensions import db
from ipo_app.models import ActivityLog, Student, Teacher


def test_admin_export_essays_zip_contains_manifest(client, csrf_token):
    with client.application.app_context():
        student = Student(
            country="Testland",
            first_name="Student",
            last_name="Export",
            email="student.export@example.test",
            school="Test School",
            date_of_birth=date(2000, 1, 1),
            essay_language="English",
            keyboard_preference="QWERTY",
            meal_preference="No preference",
        )
        db.session.add(student)
        db.session.commit()

        student.uploaded_filename = f"student-{student.id}-export.pdf"
        student.uploaded_at = datetime.utcnow()
        db.session.commit()

        upload_folder = Path(client.application.config["UPLOAD_FOLDER"])
        (upload_folder / student.uploaded_filename).write_bytes(b"%PDF-1.4\n% export test\n%%EOF\n")

    with client.session_transaction() as session:
        session["admin_user"] = "admin"

    exports_page = client.get("/admin/exports")
    token = csrf_token(exports_page)

    response = client.post(
        "/admin/exports/essays",
        data={"csrf_token": token},
        follow_redirects=False,
    )

    assert response.status_code == 200
    assert "application/zip" in response.headers.get("Content-Type", "")

    archive = zipfile.ZipFile(io.BytesIO(response.data))
    names = set(archive.namelist())
    assert "manifest.csv" in names

    expected_name = f"essays/{student.id}-{student.last_name}_{student.first_name}.pdf"
    assert expected_name in names

    manifest = archive.read("manifest.csv").decode("utf-8")
    assert str(student.id) in manifest
    assert student.uploaded_filename in manifest


def test_admin_exports_redirects_to_login_for_non_admin(client):
    response = client.get("/admin/exports", follow_redirects=False)
    assert response.status_code == 302
    assert response.headers["Location"].startswith("/admin/login")


def test_admin_export_essays_finalized_only_filters_files(client, csrf_token):
    with client.application.app_context():
        upload_folder = Path(client.application.config["UPLOAD_FOLDER"])

        finalized = Student(
            country="Testland",
            first_name="Student",
            last_name="Final",
            email="student.final@example.test",
            school="Test School",
            date_of_birth=date(2000, 1, 1),
            essay_language="English",
            keyboard_preference="QWERTY",
            meal_preference="No preference",
            uploaded_filename="final.pdf",
            uploaded_at=datetime.utcnow(),
            essay_finalized=True,
            essay_finalized_at=datetime.utcnow(),
        )
        draft = Student(
            country="Testland",
            first_name="Student",
            last_name="Draft",
            email="student.draft@example.test",
            school="Test School",
            date_of_birth=date(2000, 1, 1),
            essay_language="English",
            keyboard_preference="QWERTY",
            meal_preference="No preference",
            uploaded_filename="draft.pdf",
            uploaded_at=datetime.utcnow(),
            essay_finalized=False,
        )
        db.session.add_all([finalized, draft])
        db.session.commit()

        (upload_folder / finalized.uploaded_filename).write_bytes(b"%PDF-1.4\n% finalized\n%%EOF\n")
        (upload_folder / draft.uploaded_filename).write_bytes(b"%PDF-1.4\n% draft\n%%EOF\n")

    with client.session_transaction() as session:
        session["admin_user"] = "admin"

    token = csrf_token(client.get("/admin/exports"))
    response = client.post(
        "/admin/exports/essays",
        data={"csrf_token": token, "finalized_only": "1"},
        follow_redirects=False,
    )

    assert response.status_code == 200
    archive = zipfile.ZipFile(io.BytesIO(response.data))
    names = set(archive.namelist())

    assert f"essays/{finalized.id}-{finalized.last_name}_{finalized.first_name}.pdf" in names
    assert f"essays/{draft.id}-{draft.last_name}_{draft.first_name}.pdf" not in names

    manifest = archive.read("manifest.csv").decode("utf-8")
    reader = csv.DictReader(io.StringIO(manifest))
    exported_ids = [int(row["student_id"]) for row in reader if row.get("student_id")]
    assert exported_ids == [finalized.id]


def test_admin_export_essays_redirects_when_no_essays_available(client, csrf_token):
    with client.session_transaction() as session:
        session["admin_user"] = "admin"

    token = csrf_token(client.get("/admin/exports"))
    response = client.post(
        "/admin/exports/essays",
        data={"csrf_token": token},
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert "No essays available to export." in response.get_data(as_text=True)


def test_admin_export_database_sqlite_creates_backup(client, csrf_token):
    with client.session_transaction() as session:
        session["admin_user"] = "admin"

    token = csrf_token(client.get("/admin/exports"))
    response = client.post(
        "/admin/exports/database",
        data={"csrf_token": token},
        follow_redirects=False,
    )

    assert response.status_code == 200
    assert "application/sql" in response.headers.get("Content-Type", "")

    content_disposition = response.headers.get("Content-Disposition", "")
    match = re.search(r"filename=([^;]+)", content_disposition)
    assert match, "Expected filename in Content-Disposition"
    filename = match.group(1).strip('"')

    backups_folder = Path(client.application.config["BACKUP_FOLDER"])
    assert (backups_folder / filename).exists()


def test_admin_logs_export_csv_respects_limit(client):
    with client.application.app_context():
        db.session.add_all(
            [
                ActivityLog(action="a1", description="one"),
                ActivityLog(action="a2", description="two"),
                ActivityLog(action="a3", description="three"),
            ]
        )
        db.session.commit()

    client.application.config["LOG_EXPORT_LIMIT"] = 2
    with client.session_transaction() as session:
        session["admin_user"] = "admin"

    response = client.get("/admin/logs/export", follow_redirects=False)
    assert response.status_code == 200
    assert response.headers.get("Content-Type") == "text/csv; charset=utf-8"

    lines = response.get_data(as_text=True).strip().splitlines()
    assert lines[0] == "timestamp,actor,action,object_type,object_id,description,details"
    assert len(lines) == 1 + 2


def test_admin_students_export_xlsx_contains_header_row(client):
    with client.application.app_context():
        student = Student(
            country="Testland",
            first_name="Student",
            last_name="Xlsx",
            email="student.xlsx@example.test",
            school="Test School",
            date_of_birth=date(2000, 1, 1),
            essay_language="English",
            keyboard_preference="QWERTY",
            meal_preference="No preference",
        )
        db.session.add(student)
        db.session.commit()

    with client.session_transaction() as session:
        session["admin_user"] = "admin"

    response = client.get("/admin/students/export", follow_redirects=False)
    assert response.status_code == 200
    assert (
        response.headers.get("Content-Type", "")
        == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

    workbook = load_workbook(io.BytesIO(response.data))
    assert "Students" in workbook.sheetnames
    sheet = workbook["Students"]
    assert sheet["A1"].value == "ID"
    assert sheet["B1"].value == "Country"


def test_admin_teachers_export_xlsx_contains_header_row(client):
    with client.application.app_context():
        teacher = Teacher(
            country="Testland",
            first_name="Teacher",
            last_name="Xlsx",
            email="teacher.xlsx@example.test",
            school="Test School",
            languages="English",
            meal_preference="No preference",
            tshirt_size="M",
        )
        db.session.add(teacher)
        db.session.commit()

    with client.session_transaction() as session:
        session["admin_user"] = "admin"

    response = client.get("/admin/teachers/export", follow_redirects=False)
    assert response.status_code == 200
    assert (
        response.headers.get("Content-Type", "")
        == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

    workbook = load_workbook(io.BytesIO(response.data))
    assert "Teachers" in workbook.sheetnames
    sheet = workbook["Teachers"]
    assert sheet["A1"].value == "ID"
    assert sheet["B1"].value == "Country"
