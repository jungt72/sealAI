"""Establish the Alembic baseline for the active V2 schema.

Fresh databases are created from the current metadata. Existing pre-Alembic V2
databases are adopted only when every modeled table and column is already
present. This prevents ``create_all``-era drift from being stamped as healthy.

Revision ID: 20260710_0001
Revises: None
"""

from __future__ import annotations

from alembic import op
from sqlalchemy import inspect

import sealai_v2.db.models  # noqa: F401
from sealai_v2.db.engine import Base

revision = "20260710_0001"
down_revision = None
branch_labels = None
depends_on = None


def _validate_existing_schema() -> None:
    bind = op.get_bind()
    db = inspect(bind)
    actual_tables = set(db.get_table_names())
    expected_tables = set(Base.metadata.tables)
    existing_v2 = actual_tables & expected_tables

    if not existing_v2:
        Base.metadata.create_all(bind=bind)
        return

    missing_tables = sorted(expected_tables - actual_tables)
    if missing_tables:
        raise RuntimeError(
            "refusing to baseline a partial V2 schema; missing tables: "
            f"{missing_tables}"
        )

    missing_columns: dict[str, list[str]] = {}
    for table_name, table in Base.metadata.tables.items():
        actual = {column["name"] for column in db.get_columns(table_name)}
        missing = sorted(set(table.columns.keys()) - actual)
        if missing:
            missing_columns[table_name] = missing
    if missing_columns:
        raise RuntimeError(
            "refusing to baseline a drifted V2 schema; missing columns: "
            f"{missing_columns}"
        )


def upgrade() -> None:
    _validate_existing_schema()


def downgrade() -> None:
    Base.metadata.drop_all(bind=op.get_bind())
