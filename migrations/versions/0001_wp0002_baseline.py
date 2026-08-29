"""Establish the PostgreSQL Alembic baseline without Legacy business tables.

Revision ID: 0001_wp0002_baseline
Revises:
Create Date: 2026-08-29
"""
from __future__ import annotations

from collections.abc import Sequence


revision: str = "0001_wp0002_baseline"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create only Alembic's version state; business tables start in later Work Packages."""


def downgrade() -> None:
    """Return to the pre-baseline state without touching Legacy SQLite."""
