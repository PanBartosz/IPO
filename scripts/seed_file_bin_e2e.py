from __future__ import annotations

import json
from pathlib import Path
from uuid import uuid4

from werkzeug.security import generate_password_hash

from ipo_app import create_app
from ipo_app.extensions import db
from ipo_app.models import AppSetting
from ipo_app.views import SETTING_FILE_BIN_ACCESS_CODE_HASH, SETTING_FILE_BIN_ENABLED


def _set_setting(key: str, value: str) -> None:
    existing = AppSetting.query.filter_by(key=key).first()
    if existing:
        existing.value = value
    else:
        db.session.add(AppSetting(key=key, value=value))


def main() -> None:
    app = create_app()
    output_path = Path("output/e2e_file_bin.json")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    run_id = uuid4().hex[:10]
    code = f"file-bin-e2e-{run_id}"

    with app.app_context():
        _set_setting(SETTING_FILE_BIN_ENABLED, "true")
        _set_setting(SETTING_FILE_BIN_ACCESS_CODE_HASH, generate_password_hash(code))
        db.session.commit()

    payload = {
        "run_id": run_id,
        "code": code,
        "staff_name": "E2E Room Staff",
        "room": f"E2E Room {run_id}",
        "student_identifier": f"E2E Essay {run_id}",
        "note": "E2E emergency transfer",
        "filename": f"file-bin-e2e-{run_id}.txt",
        "content": f"Emergency file bin E2E payload {run_id}\n",
    }
    output_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
