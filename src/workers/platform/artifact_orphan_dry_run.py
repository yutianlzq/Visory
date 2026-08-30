from __future__ import annotations

import json
from typing import Any

from src.artifacts.orphan import ArtifactOrphanSweeper
from src.schemas.platform import (
    ArtifactPublishRequest,
    ArtifactPublishResult,
    ArtifactVisibility,
    ResourceRef,
    ResourceType,
    RetentionClass,
    TaskLease,
    TaskState,
    generate_resource_id,
)
from src.services.platform.artifact_publisher import ArtifactPublisherService
from src.services.platform.task_control import TaskControlError, TaskControlService


class ArtifactOrphanDryRunTaskWorker:
    """Execute the first low-risk durable maintenance task end to end."""

    def __init__(
        self,
        task_control: TaskControlService,
        sweeper: ArtifactOrphanSweeper,
        publisher: ArtifactPublisherService,
    ) -> None:
        self.task_control = task_control
        self.sweeper = sweeper
        self.publisher = publisher

    @staticmethod
    def _payload(value: Any) -> bytes:
        return (
            json.dumps(
                value.model_dump(mode="json"),
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False,
            )
            + "\n"
        ).encode("utf-8")

    def execute(self, lease: TaskLease) -> ArtifactPublishResult:
        if lease.task.task_type != "artifact_orphan_dry_run":
            raise TaskControlError(
                "TASK_TYPE_UNSUPPORTED",
                "Worker does not support this task type.",
                status_code=422,
            )
        self.task_control.start_attempt(lease.attempt.attempt_id, lease.lease_token)
        current = self.task_control.get_task(lease.task.task_id).task
        if current.cancel_requested_at is not None:
            self.task_control.acknowledge_cancel(lease.attempt.attempt_id, lease.lease_token)
            raise TaskControlError("TASK_CANCEL_PENDING", "Cancelled task cannot publish a result.")

        dry_run = self.sweeper.dry_run()
        content = self._payload(dry_run)
        artifact_id = generate_resource_id(ResourceType.ARTIFACT)
        request = ArtifactPublishRequest(
            artifact_id=artifact_id,
            artifact_type="artifact_orphan_dry_run",
            owner_resource_ref=ResourceRef(
                resource_type=ResourceType.TASK,
                resource_id=lease.task.task_id,
            ),
            attempt_id=lease.attempt.attempt_id,
            payload_filename="result.json",
            media_type="application/json",
            expected_content_hash=None,
            expected_size_bytes=len(content),
            schema_version="1.0.0",
            retention_class=RetentionClass.AUDIT,
            visibility=ArtifactVisibility.OWNER,
        )
        try:
            return self.publisher.publish(
                request,
                content,
                after_register=lambda session, record: self.task_control.complete_with_artifact_in_session(
                    session,
                    attempt_id=lease.attempt.attempt_id,
                    lease_token=lease.lease_token,
                    artifact_id=record.artifact_id,
                ),
            )
        except Exception as exc:
            if isinstance(exc, (KeyboardInterrupt, SystemExit)):
                raise
            try:
                current = self.task_control.get_task(lease.task.task_id).task
                if current.task_state is TaskState.RUNNING and current.cancel_requested_at is not None:
                    self.task_control.acknowledge_cancel(lease.attempt.attempt_id, lease.lease_token)
                else:
                    self.task_control.record_failure(
                        lease.attempt.attempt_id,
                        lease.lease_token,
                        failure_code="TASK_ARTIFACT_PUBLISH_FAILED",
                        retryable=True,
                    )
            except TaskControlError as lease_error:
                if lease_error.error_code != "TASK_LEASE_LOST":
                    raise
            raise
