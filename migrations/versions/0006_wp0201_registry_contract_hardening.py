"""Harden DatasetDefinition version binding and registry lineage semantics."""
from __future__ import annotations
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision = "0006_wp0201_registry_contract_hardening"
down_revision: str | Sequence[str] | None = "0005_wp0201_dataset_provider_registry"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint("ck_provider_actual_upstream", "provider_definition", type_="check")
    op.drop_column("provider_definition", "actual_upstream")
    op.drop_constraint("provider_capability_dataset_id_fkey", "provider_capability", type_="foreignkey")
    op.drop_constraint("provider_policy_dataset_id_fkey", "provider_policy", type_="foreignkey")
    op.drop_constraint("dataset_definition_pkey", "dataset_definition", type_="primary")
    op.create_primary_key("pk_dataset_definition", "dataset_definition", ["dataset_id", "schema_version"])

    op.execute("ALTER TABLE provider_policy DROP CONSTRAINT IF EXISTS ex_provider_policy_effective_no_overlap")
    op.add_column("provider_capability", sa.Column("dataset_schema_version", sa.String(32), nullable=True))
    op.add_column("provider_policy", sa.Column("dataset_schema_version", sa.String(32), nullable=True))
    op.execute("UPDATE provider_capability SET dataset_schema_version = '1.0.0' WHERE dataset_schema_version IS NULL")
    op.execute("UPDATE provider_policy SET dataset_schema_version = '1.0.0' WHERE dataset_schema_version IS NULL")
    op.alter_column("provider_capability", "dataset_schema_version", nullable=False)
    op.alter_column("provider_policy", "dataset_schema_version", nullable=False)

    op.drop_constraint("provider_capability_pkey", "provider_capability", type_="primary")
    op.create_primary_key("pk_provider_capability", "provider_capability", ["provider_id", "dataset_id", "dataset_schema_version", "market", "frequency"])
    op.execute("ALTER TABLE provider_policy ADD CONSTRAINT ex_provider_policy_effective_no_overlap EXCLUDE USING gist (dataset_id WITH =, dataset_schema_version WITH =, tstzrange(effective_from, COALESCE(effective_to, 'infinity'::timestamptz), '[)'::text) WITH &&)")
    op.create_foreign_key("fk_provider_capability_dataset_version", "provider_capability", "dataset_definition", ["dataset_id", "dataset_schema_version"], ["dataset_id", "schema_version"], ondelete="CASCADE")
    op.create_foreign_key("fk_provider_policy_dataset_version", "provider_policy", "dataset_definition", ["dataset_id", "dataset_schema_version"], ["dataset_id", "schema_version"], ondelete="CASCADE")


def downgrade() -> None:
    duplicate_versions = op.get_bind().execute(sa.text("SELECT dataset_id FROM dataset_definition GROUP BY dataset_id HAVING COUNT(*) > 1 LIMIT 1")).first()
    if duplicate_versions is not None:
        raise RuntimeError("cannot downgrade registry contract while multiple dataset schema versions exist")

    op.execute("ALTER TABLE provider_policy DROP CONSTRAINT IF EXISTS ex_provider_policy_effective_no_overlap")
    op.drop_constraint("fk_provider_capability_dataset_version", "provider_capability", type_="foreignkey")
    op.drop_constraint("fk_provider_policy_dataset_version", "provider_policy", type_="foreignkey")
    op.drop_constraint("pk_provider_capability", "provider_capability", type_="primary")
    op.create_primary_key("provider_capability_pkey", "provider_capability", ["provider_id", "dataset_id", "market", "frequency"])
    op.drop_column("provider_capability", "dataset_schema_version")
    op.drop_column("provider_policy", "dataset_schema_version")
    op.drop_constraint("pk_dataset_definition", "dataset_definition", type_="primary")
    op.create_primary_key("dataset_definition_pkey", "dataset_definition", ["dataset_id"])
    provider_rows = op.get_bind().execute(sa.text("SELECT 1 FROM provider_definition LIMIT 1")).first()
    if provider_rows is not None:
        raise RuntimeError("cannot downgrade registry contract with provider records because 0005 requires an actual_upstream claim")
    op.add_column("provider_definition", sa.Column("actual_upstream", sa.String(255), nullable=True))
    op.create_check_constraint("ck_provider_actual_upstream", "provider_definition", "(provider_kind <> 'AGGREGATOR') OR actual_upstream IS NOT NULL")
    op.create_foreign_key("provider_capability_dataset_id_fkey", "provider_capability", "dataset_definition", ["dataset_id"], ["dataset_id"], ondelete="CASCADE")
    op.create_foreign_key("provider_policy_dataset_id_fkey", "provider_policy", "dataset_definition", ["dataset_id"], ["dataset_id"], ondelete="CASCADE")
    op.execute("ALTER TABLE provider_policy ADD CONSTRAINT ex_provider_policy_effective_no_overlap EXCLUDE USING gist (dataset_id WITH =, tstzrange(effective_from, COALESCE(effective_to, 'infinity'::timestamptz), '[)'::text) WITH &&)")
