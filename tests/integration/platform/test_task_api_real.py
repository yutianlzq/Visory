from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from api.app import create_app
from src.repositories.platform import PostgresDatabase, upgrade_database
from src.services.platform.task_control import TaskControlService


def test_real_postgres_task_api_create_query_cancel_and_retry(isolated_postgres_database: PostgresDatabase, tmp_path: Path) -> None:
    database = isolated_postgres_database
    upgrade_database(database.engine)
    app = create_app(static_dir=tmp_path / "missing-static")
    app.state.task_control_service = TaskControlService(database, runtime_root=tmp_path)
    client = TestClient(app)

    payload = {
        "task_type": "artifact_orphan_dry_run",
        "requested_by": "owner:api-integration",
        "requirements": {"worker_kind": "maintenance"},
    }
    created = client.post(
        "/api/platform/v1/tasks",
        headers={"Idempotency-Key": "real-api-command-001"},
        json=payload,
    )
    assert created.status_code == 200
    task_id = created.json()["data"]["task_id"]
    assert created.json()["data"]["task_state"] == "QUEUED"

    replay = client.post(
        "/api/platform/v1/tasks",
        headers={"Idempotency-Key": "real-api-command-001"},
        json=payload,
    )
    assert replay.status_code == 200
    assert replay.json()["data"]["task_id"] == task_id

    queried = client.get(f"/api/platform/v1/tasks/{task_id}")
    assert queried.status_code == 200
    assert queried.json()["data"]["task"]["task_id"] == task_id
    assert len(queried.json()["data"]["state_events"]) == 2

    cancelled = client.post(f"/api/platform/v1/tasks/{task_id}/cancellations", json={})
    assert cancelled.status_code == 200
    assert cancelled.json()["data"]["task_state"] == "CANCELLED"

    retry = client.post(f"/api/platform/v1/tasks/{task_id}/retries", json={})
    assert retry.status_code == 409
    assert retry.json()["error"]["code"] == "TASK_RETRY_NOT_ALLOWED"
