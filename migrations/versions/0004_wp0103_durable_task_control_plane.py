"""Create WP-0103 durable task control plane.

Revision ID: 0004_wp0103_durable_task_control_plane
Revises: 0003_wp0102_artifact_registry
Create Date: 2026-08-30
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "0004_wp0103_durable_task_control_plane"
down_revision: str | Sequence[str] | None = "0003_wp0102_artifact_registry"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_TASK_STATES = "'ACCEPTED','QUEUED','BLOCKED','LEASED','RUNNING','RETRY_WAIT','SUCCEEDED','DEGRADED','FAILED','CANCELLED'"
_PRIORITY_CLASSES = "'P0_DATA_CERTIFICATION','P1_FORMAL_SIGNAL','P2_MARKET_REVIEW','P3_USER_INTERACTIVE','P4_RESEARCH','P5_PREVIEW_AND_MAINTENANCE'"
_ATTEMPT_OUTCOMES = "'SUCCEEDED','DEGRADED','FAILED','CANCELLED','BLOCKED','LEASE_LOST'"


def upgrade() -> None:
    # Alembic defaults version_num to VARCHAR(32); this descriptive revision exceeds it.
    op.alter_column(
        "alembic_version",
        "version_num",
        existing_type=sa.String(length=32),
        type_=sa.String(length=64),
        existing_nullable=False,
    )
    op.create_table(
        "platform_task",
        sa.Column("task_id", sa.String(length=64), primary_key=True),
        sa.Column("task_type", sa.String(length=64), nullable=False),
        sa.Column("task_schema_version", sa.String(length=32), nullable=False),
        sa.Column("task_state", sa.String(length=16), nullable=False),
        sa.Column("priority_class", sa.String(length=32), nullable=False),
        sa.Column("priority_value", sa.Integer(), nullable=False),
        sa.Column("idempotency_key", sa.String(length=255), nullable=False),
        sa.Column("task_key", sa.String(length=512), nullable=False),
        sa.Column("canonical_request_hash", sa.String(length=71), nullable=False),
        sa.Column("requested_by", sa.String(length=255), nullable=False),
        sa.Column("request_source", sa.String(length=64), nullable=False),
        sa.Column("input_refs", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("requirements", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("active_attempt_id", sa.String(length=64), nullable=True),
        sa.Column("blocked_reason_code", sa.String(length=64), nullable=True),
        sa.Column("unblock_condition", sa.Text(), nullable=True),
        sa.Column("max_attempts", sa.Integer(), nullable=False),
        sa.Column("cancel_requested_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("result_artifact_id", sa.String(length=64), nullable=True),
        sa.Column("created_from_task_id", sa.String(length=64), nullable=True),
        sa.Column("force_reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("queued_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("terminal_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("failure_code", sa.String(length=64), nullable=True),
        sa.CheckConstraint("task_id ~ '^task_[0-9a-f-]{36}$'", name="ck_platform_task_id"),
        sa.CheckConstraint("task_type ~ '^[a-z][a-z0-9._-]{0,63}$'", name="ck_platform_task_type"),
        sa.CheckConstraint("task_schema_version ~ '^[0-9]+\\.[0-9]+\\.[0-9]+$'", name="ck_platform_task_schema_version"),
        sa.CheckConstraint(f"task_state IN ({_TASK_STATES})", name="ck_platform_task_state"),
        sa.CheckConstraint(f"priority_class IN ({_PRIORITY_CLASSES})", name="ck_platform_task_priority_class"),
        sa.CheckConstraint("priority_value >= 0", name="ck_platform_task_priority_value"),
        sa.CheckConstraint("canonical_request_hash ~ '^sha256:[0-9a-f]{64}$'", name="ck_platform_task_request_hash"),
        sa.CheckConstraint("max_attempts BETWEEN 1 AND 100", name="ck_platform_task_max_attempts"),
        sa.CheckConstraint("active_attempt_id IS NULL OR active_attempt_id ~ '^attempt_[0-9a-f-]{36}$'", name="ck_platform_task_active_attempt_id"),
        sa.CheckConstraint("result_artifact_id IS NULL OR result_artifact_id ~ '^artifact_[0-9a-f-]{36}$'", name="ck_platform_task_result_artifact_id"),
        sa.CheckConstraint("created_from_task_id IS NULL OR created_from_task_id ~ '^task_[0-9a-f-]{36}$'", name="ck_platform_task_created_from_id"),
        sa.CheckConstraint("created_from_task_id IS NULL OR created_from_task_id <> task_id", name="ck_platform_task_lineage_not_self"),
        sa.CheckConstraint("(task_state = 'BLOCKED' AND blocked_reason_code IS NOT NULL AND unblock_condition IS NOT NULL) OR (task_state <> 'BLOCKED' AND blocked_reason_code IS NULL AND unblock_condition IS NULL)", name="ck_platform_task_blocked_fields"),
        sa.CheckConstraint("(task_state = 'FAILED' AND failure_code IS NOT NULL) OR (task_state <> 'FAILED' AND failure_code IS NULL)", name="ck_platform_task_failure_fields"),
        sa.CheckConstraint("(task_state IN ('SUCCEEDED','DEGRADED','FAILED','CANCELLED') AND terminal_at IS NOT NULL) OR (task_state NOT IN ('SUCCEEDED','DEGRADED','FAILED','CANCELLED') AND terminal_at IS NULL)", name="ck_platform_task_terminal_at"),
        sa.CheckConstraint("result_artifact_id IS NULL OR task_state IN ('SUCCEEDED','DEGRADED')", name="ck_platform_task_result_state"),
        sa.CheckConstraint("(task_state IN ('LEASED','RUNNING') AND active_attempt_id IS NOT NULL) OR (task_state NOT IN ('LEASED','RUNNING') AND active_attempt_id IS NULL)", name="ck_platform_task_active_attempt_state"),
        sa.CheckConstraint("force_reason IS NULL OR created_from_task_id IS NOT NULL", name="ck_platform_task_force_lineage"),
        sa.ForeignKeyConstraint(["result_artifact_id"], ["artifact_registry.artifact_id"], name="fk_platform_task_result_artifact", deferrable=True, initially="DEFERRED"),
        sa.ForeignKeyConstraint(["created_from_task_id"], ["platform_task.task_id"], name="fk_platform_task_created_from", deferrable=True, initially="DEFERRED"),
        sa.UniqueConstraint("requested_by", "task_key", name="uq_platform_task_owner_task_key"),
    )
    op.create_index(
        "ix_platform_task_claim_order",
        "platform_task",
        ["priority_class", "priority_value", "queued_at", "task_id"],
        postgresql_where=sa.text("task_state = 'QUEUED' AND cancel_requested_at IS NULL"),
    )

    op.create_table(
        "task_attempt",
        sa.Column("attempt_id", sa.String(length=64), primary_key=True),
        sa.Column("task_id", sa.String(length=64), nullable=False),
        sa.Column("attempt_number", sa.Integer(), nullable=False),
        sa.Column("attempt_phase", sa.String(length=64), nullable=False),
        sa.Column("phase_progress", sa.Float(), nullable=False),
        sa.Column("worker_id", sa.String(length=255), nullable=False),
        sa.Column("worker_capabilities", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("lease_token_hash", sa.String(length=71), nullable=False),
        sa.Column("leased_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("heartbeat_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("checkpoint_ref", sa.String(length=64), nullable=True),
        sa.Column("resource_usage", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("attempt_outcome", sa.String(length=32), nullable=True),
        sa.Column("failure_code", sa.String(length=64), nullable=True),
        sa.Column("retryable", sa.Boolean(), nullable=True),
        sa.Column("diagnostic_artifact_refs", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.CheckConstraint("attempt_id ~ '^attempt_[0-9a-f-]{36}$'", name="ck_task_attempt_id"),
        sa.CheckConstraint("task_id ~ '^task_[0-9a-f-]{36}$'", name="ck_task_attempt_task_id"),
        sa.CheckConstraint("attempt_number >= 1", name="ck_task_attempt_number"),
        sa.CheckConstraint("phase_progress BETWEEN 0 AND 1", name="ck_task_attempt_progress"),
        sa.CheckConstraint("lease_token_hash ~ '^sha256:[0-9a-f]{64}$'", name="ck_task_attempt_lease_hash"),
        sa.CheckConstraint("lease_expires_at > leased_at", name="ck_task_attempt_lease_interval"),
        sa.CheckConstraint("heartbeat_at BETWEEN leased_at AND lease_expires_at", name="ck_task_attempt_heartbeat"),
        sa.CheckConstraint("checkpoint_ref IS NULL OR checkpoint_ref ~ '^checkpoint_[0-9a-f-]{36}$'", name="ck_task_attempt_checkpoint_ref"),
        sa.CheckConstraint(f"attempt_outcome IS NULL OR attempt_outcome IN ({_ATTEMPT_OUTCOMES})", name="ck_task_attempt_outcome"),
        sa.CheckConstraint("(attempt_outcome IS NULL AND finished_at IS NULL AND failure_code IS NULL AND retryable IS NULL) OR (attempt_outcome IS NOT NULL AND finished_at IS NOT NULL)", name="ck_task_attempt_terminal_fields"),
        sa.CheckConstraint("(attempt_outcome IN ('FAILED','LEASE_LOST') AND failure_code IS NOT NULL AND retryable IS NOT NULL) OR (attempt_outcome IS NULL) OR (attempt_outcome NOT IN ('FAILED','LEASE_LOST') AND failure_code IS NULL AND retryable IS NULL)", name="ck_task_attempt_failure_fields"),
        sa.ForeignKeyConstraint(["task_id"], ["platform_task.task_id"], name="fk_task_attempt_task", ondelete="CASCADE"),
        sa.UniqueConstraint("task_id", "attempt_number", name="uq_task_attempt_number"),
    )
    op.create_index(
        "uq_task_attempt_one_active",
        "task_attempt",
        ["task_id"],
        unique=True,
        postgresql_where=sa.text("attempt_outcome IS NULL"),
    )
    op.create_index("ix_task_attempt_expiry", "task_attempt", ["lease_expires_at"], postgresql_where=sa.text("attempt_outcome IS NULL"))

    op.create_foreign_key(
        "fk_platform_task_active_attempt",
        "platform_task",
        "task_attempt",
        ["active_attempt_id"],
        ["attempt_id"],
        deferrable=True,
        initially="DEFERRED",
    )

    op.create_table(
        "task_state_event",
        sa.Column("task_id", sa.String(length=64), nullable=False),
        sa.Column("event_sequence", sa.BigInteger(), nullable=False),
        sa.Column("previous_task_state", sa.String(length=16), nullable=True),
        sa.Column("next_task_state", sa.String(length=16), nullable=False),
        sa.Column("reason_code", sa.String(length=64), nullable=False),
        sa.Column("actor_ref", sa.String(length=255), nullable=False),
        sa.Column("event_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("attempt_id", sa.String(length=64), nullable=True),
        sa.PrimaryKeyConstraint("task_id", "event_sequence", name="pk_task_state_event"),
        sa.CheckConstraint(f"previous_task_state IS NULL OR previous_task_state IN ({_TASK_STATES})", name="ck_task_state_event_previous"),
        sa.CheckConstraint(f"next_task_state IN ({_TASK_STATES})", name="ck_task_state_event_next"),
        sa.CheckConstraint("reason_code ~ '^[A-Z][A-Z0-9_]{2,63}$'", name="ck_task_state_event_reason"),
        sa.ForeignKeyConstraint(["task_id"], ["platform_task.task_id"], name="fk_task_state_event_task", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["attempt_id"], ["task_attempt.attempt_id"], name="fk_task_state_event_attempt", deferrable=True, initially="DEFERRED"),
    )
    op.create_index("ix_task_state_event_time", "task_state_event", ["task_id", "event_at"])

    op.create_table(
        "task_checkpoint",
        sa.Column("checkpoint_id", sa.String(length=64), primary_key=True),
        sa.Column("task_id", sa.String(length=64), nullable=False),
        sa.Column("attempt_id", sa.String(length=64), nullable=False),
        sa.Column("phase", sa.String(length=64), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("resume_token_hash", sa.String(length=71), nullable=False),
        sa.Column("input_hash", sa.String(length=71), nullable=False),
        sa.Column("handler_version", sa.String(length=255), nullable=False),
        sa.Column("storage_backend", sa.String(length=32), nullable=False),
        sa.Column("storage_namespace", sa.String(length=32), nullable=False),
        sa.Column("relative_path", sa.String(length=1024), nullable=False),
        sa.Column("content_hash", sa.String(length=71), nullable=False),
        sa.Column("media_type", sa.String(length=255), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("checkpoint_hash", sa.String(length=71), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("checkpoint_id ~ '^checkpoint_[0-9a-f-]{36}$'", name="ck_task_checkpoint_id"),
        sa.CheckConstraint("task_id ~ '^task_[0-9a-f-]{36}$'", name="ck_task_checkpoint_task_id"),
        sa.CheckConstraint("attempt_id ~ '^attempt_[0-9a-f-]{36}$'", name="ck_task_checkpoint_attempt_id"),
        sa.CheckConstraint("sequence >= 1", name="ck_task_checkpoint_sequence"),
        sa.CheckConstraint("resume_token_hash ~ '^sha256:[0-9a-f]{64}$'", name="ck_task_checkpoint_resume_hash"),
        sa.CheckConstraint("input_hash ~ '^sha256:[0-9a-f]{64}$'", name="ck_task_checkpoint_input_hash"),
        sa.CheckConstraint("storage_backend = 'local_fs'", name="ck_task_checkpoint_backend"),
        sa.CheckConstraint("storage_namespace = 'app'", name="ck_task_checkpoint_namespace"),
        sa.CheckConstraint("relative_path !~ '(^/|\\\\|(^|/)\\.{1,2}(/|$)|//|:)'", name="ck_task_checkpoint_relative_path"),
        sa.CheckConstraint("content_hash ~ '^sha256:[0-9a-f]{64}$'", name="ck_task_checkpoint_content_hash"),
        sa.CheckConstraint("checkpoint_hash = content_hash", name="ck_task_checkpoint_hash"),
        sa.CheckConstraint("size_bytes >= 0", name="ck_task_checkpoint_size"),
        sa.CheckConstraint("expires_at > created_at", name="ck_task_checkpoint_expiry"),
        sa.ForeignKeyConstraint(["task_id"], ["platform_task.task_id"], name="fk_task_checkpoint_task", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["attempt_id"], ["task_attempt.attempt_id"], name="fk_task_checkpoint_attempt", ondelete="CASCADE"),
        sa.UniqueConstraint("attempt_id", "sequence", name="uq_task_checkpoint_attempt_sequence"),
    )
    op.create_index("ix_task_checkpoint_task", "task_checkpoint", ["task_id", "created_at"])

    op.create_table(
        "task_command_idempotency",
        sa.Column("requested_by", sa.String(length=255), nullable=False),
        sa.Column("endpoint", sa.String(length=255), nullable=False),
        sa.Column("idempotency_key", sa.String(length=255), nullable=False),
        sa.Column("request_hash", sa.String(length=71), nullable=False),
        sa.Column("task_id", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("requested_by", "endpoint", "idempotency_key", name="pk_task_command_idempotency"),
        sa.CheckConstraint("request_hash ~ '^sha256:[0-9a-f]{64}$'", name="ck_task_command_request_hash"),
        sa.CheckConstraint("task_id ~ '^task_[0-9a-f-]{36}$'", name="ck_task_command_task_id"),
        sa.ForeignKeyConstraint(["task_id"], ["platform_task.task_id"], name="fk_task_command_task", deferrable=True, initially="DEFERRED", ondelete="CASCADE"),
    )


def downgrade() -> None:
    op.drop_table("task_command_idempotency")
    op.drop_index("ix_task_checkpoint_task", table_name="task_checkpoint")
    op.drop_table("task_checkpoint")
    op.drop_index("ix_task_state_event_time", table_name="task_state_event")
    op.drop_table("task_state_event")
    op.drop_constraint("fk_platform_task_active_attempt", "platform_task", type_="foreignkey")
    op.drop_index("ix_task_attempt_expiry", table_name="task_attempt")
    op.drop_index("uq_task_attempt_one_active", table_name="task_attempt")
    op.drop_table("task_attempt")
    op.drop_index("ix_platform_task_claim_order", table_name="platform_task")
    op.drop_table("platform_task")
