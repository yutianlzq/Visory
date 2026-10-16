from __future__ import annotations

from pathlib import Path
from datetime import datetime, timedelta, timezone
import json

from fastapi import FastAPI
from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator

from api.app import create_app
from api.middlewares.error_handler import add_error_handlers
from api.platform.router import router
from src.artifacts.hashing import compute_bytes_hash
from src.artifacts.namespace import StorageNamespaceResolver
from src.repositories.platform import PostgresDatabase, upgrade_database
from src.schemas.platform import StorageRef
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


def test_postgres_task_http_projection_keeps_worker_verifiers_private(isolated_postgres_database, tmp_path, monkeypatch):
    def forbidden_startup(*args):
        raise AssertionError("WP-0207 API regression must not start remote index refresh")

    monkeypatch.setattr("api.app._schedule_stock_index_background_refresh", forbidden_startup)
    upgrade_database(isolated_postgres_database.engine)
    service = TaskControlService(isolated_postgres_database, runtime_root=tmp_path)
    app = FastAPI()
    app.include_router(router, prefix="/api")
    add_error_handlers(app)
    app.state.task_control_service = service
    with TestClient(app) as client:
        created = client.post("/api/platform/v1/tasks", headers={"Idempotency-Key": "wp0207-public-checkpoint"}, json={
            "task_type": "artifact_orphan_dry_run", "requested_by": "owner:fixture-only",
            "requirements": {"worker_kind": "maintenance", "diagnostic": '{"apiKey":"fixture-secret"}'},
        })
        assert created.status_code == 200
        assert "fixture-secret" not in created.text
        task_id = created.json()["data"]["task_id"]
        lease = service.lease_next(worker_id="fixture-worker", worker_capabilities=("artifact_orphan_dry_run",), task_id=task_id)
        assert lease is not None
        service.start_attempt(lease.attempt.attempt_id, lease.lease_token)
        content = b'{"fixture_only":true,"cursor":1}\n'
        storage = StorageRef(
            storage_backend="local_fs", storage_namespace="app", relative_path="checkpoints/fixture-only/cursor.json",
            content_hash=compute_bytes_hash(content), media_type="application/json", size_bytes=len(content),
        )
        path = StorageNamespaceResolver(tmp_path).resolve(storage)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        checkpoint, resume_token = service.save_checkpoint(
            lease.attempt.attempt_id, lease.lease_token, phase="SCANNING", input_hash="sha256:" + "7" * 64,
            handler_version="fixture-only@1.0.0", storage_ref=storage,
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        )
        response = client.get(f"/api/platform/v1/tasks/{task_id}")
    assert response.status_code == 200
    public = response.json()["data"]
    assert len(public["attempts"]) == len(public["checkpoints"]) == 1
    for private in ("lease_token_hash", "resume_token_hash", "fixture-secret", lease.lease_token, resume_token):
        assert private not in response.text
    internal = service.get_task(task_id)
    assert internal.attempts[0].lease_token_hash == lease.attempt.lease_token_hash
    assert internal.checkpoints[0].resume_token_hash == checkpoint.resume_token_hash
    assert service.validate_checkpoint(
        checkpoint.checkpoint_id, resume_token=resume_token,
        input_hash=checkpoint.input_hash, handler_version=checkpoint.handler_version,
    ) == checkpoint
    schema = Path(__file__).resolve().parents[3] / "schemas/platform/C-010.TaskDetails.schema.json"
    Draft202012Validator(json.loads(schema.read_text(encoding="utf-8"))).validate(public)
