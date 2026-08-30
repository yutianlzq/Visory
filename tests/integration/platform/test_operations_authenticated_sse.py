from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

import src.auth as auth
from api.app import create_app
from src.repositories.platform import PostgresDatabase, upgrade_database
from src.services.platform.task_control import TaskControlService


TEST_PASSWORD = "local-test-password"


def _reset_auth_state() -> None:
    auth._auth_enabled = None
    auth._session_secret = None
    auth._password_hash_salt = None
    auth._password_hash_stored = None
    auth._rate_limit = {}


def _event_ids(body: str) -> list[str]:
    return [line.removeprefix("id: ") for line in body.splitlines() if line.startswith("id: ")]


def test_authenticated_task_api_and_sse_replay_use_real_asgi_stack(
    isolated_postgres_database: PostgresDatabase,
    tmp_path: Path,
    monkeypatch,
) -> None:
    database = isolated_postgres_database
    upgrade_database(database.engine)

    env_file = tmp_path / ".env"
    env_file.write_text("ADMIN_AUTH_ENABLED=true\n", encoding="utf-8")
    monkeypatch.setenv("ENV_FILE", str(env_file))
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "legacy.db"))
    _reset_auth_state()

    with patch.object(auth, "_get_data_dir", return_value=tmp_path):
        auth.refresh_auth_state()
        assert auth.set_initial_password(TEST_PASSWORD) is None

        app = create_app(static_dir=tmp_path / "missing-static")
        app.state.task_control_service = TaskControlService(database, runtime_root=tmp_path)
        client = TestClient(app)

        unauthenticated = client.get("/api/platform/v1/tasks")
        assert unauthenticated.status_code == 401
        assert unauthenticated.json()["error"]["code"] == "AUTH_REQUIRED"

        login = client.post("/api/v1/auth/login", json={"password": TEST_PASSWORD})
        assert login.status_code == 200
        assert "dsa_session" in client.cookies

        payload = {
            "task_type": "artifact_orphan_dry_run",
            "requested_by": "owner:real-asgi",
            "requirements": {"worker_kind": "maintenance"},
        }
        created = client.post(
            "/api/platform/v1/tasks",
            headers={"Idempotency-Key": "real-asgi-journey-001"},
            json=payload,
        )
        assert created.status_code == 200
        task_id = created.json()["data"]["task_id"]
        assert created.json()["data"]["task_state"] == "QUEUED"

        listed = client.get("/api/platform/v1/tasks?tab=active")
        assert listed.status_code == 200
        assert listed.json()["data"][0]["task_id"] == task_id

        first_stream = client.get("/api/platform/v1/tasks/events")
        assert first_stream.status_code == 200
        first_ids = _event_ids(first_stream.text)
        assert first_ids == [f"{task_id}:1", f"{task_id}:2"]
        assert "heartbeat" in first_stream.text

        cancelled = client.post(f"/api/platform/v1/tasks/{task_id}/cancellations", json={})
        assert cancelled.status_code == 200
        assert cancelled.json()["data"]["task_state"] == "CANCELLED"

        replay = client.get(
            "/api/platform/v1/tasks/events",
            headers={"Last-Event-ID": f"{task_id}:2"},
        )
        assert replay.status_code == 200
        assert _event_ids(replay.text) == [f"{task_id}:3"]
        assert f"{task_id}:1" not in replay.text
        assert f"{task_id}:2" not in replay.text

        query_replay = client.get(
            "/api/platform/v1/tasks/events",
            params={"after_event_id": f"{task_id}:2"},
        )
        assert query_replay.status_code == 200
        assert _event_ids(query_replay.text) == [f"{task_id}:3"]

        logged_out = client.post("/api/v1/auth/logout")
        assert logged_out.status_code == 204
        assert client.get(f"/api/platform/v1/tasks/{task_id}").status_code == 401

        assert database.engine.pool.checkedout() == 0

    _reset_auth_state()
    monkeypatch.delenv("ENV_FILE", raising=False)
    monkeypatch.delenv("DATABASE_PATH", raising=False)
