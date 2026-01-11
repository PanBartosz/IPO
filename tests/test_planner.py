from ipo_app.extensions import db
from ipo_app.models import ActivityLog, AssignmentBatch, PlannerStatus, ReadingGroup, Stage


def test_admin_planner_create_batch_creates_row_and_log(client, csrf_token):
    with client.session_transaction() as session:
        session["admin_user"] = "admin"

    token = csrf_token(client.get("/admin/planner"))
    response = client.post(
        "/admin/planner",
        data={
            "csrf_token": token,
            "name": "Batch 1",
            "stage": Stage.STAGE_1.value,
            "notes": "",
            "submit": "Create batch",
        },
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert response.headers["Location"].startswith("/admin/planner/batches/")

    with client.application.app_context():
        batch = AssignmentBatch.query.filter_by(name="Batch 1").first()
        assert batch is not None
        assert batch.stage == Stage.STAGE_1
        assert batch.status == PlannerStatus.DRAFT

        log = ActivityLog.query.filter_by(
            action="batch_created",
            object_type="assignment_batch",
            object_id=str(batch.id),
        ).first()
        assert log is not None


def test_admin_planner_add_group_creates_row_and_log(client, csrf_token):
    with client.application.app_context():
        batch = AssignmentBatch(name="Batch 1", stage=Stage.STAGE_1, status=PlannerStatus.DRAFT)
        db.session.add(batch)
        db.session.commit()
        batch_id = batch.id

    with client.session_transaction() as session:
        session["admin_user"] = "admin"

    token = csrf_token(client.get(f"/admin/planner/batches/{batch_id}"))
    response = client.post(
        f"/admin/planner/batches/{batch_id}/groups",
        data={
            "csrf_token": token,
            "name": "Group 1",
            "language": "English",
            "target_essay_load": "4",
            "allow_same_country": "y",
            "auto_generated": "y",
            "submit": "Save group",
        },
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert response.headers["Location"] == f"/admin/planner/batches/{batch_id}"

    with client.application.app_context():
        group = ReadingGroup.query.filter_by(batch_id=batch_id, name="Group 1").first()
        assert group is not None
        assert group.language == "English"
        assert group.target_essay_load == 4
        assert group.allow_same_country is True
        assert group.auto_generated is True
        assert group.stage == Stage.STAGE_1

        log = ActivityLog.query.filter_by(
            action="group_created",
            object_type="reading_group",
            object_id=str(group.id),
        ).first()
        assert log is not None

