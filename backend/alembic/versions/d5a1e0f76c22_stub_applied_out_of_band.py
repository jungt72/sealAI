"""Stub for revision applied out-of-band (not in original repo).

Revision ID: d5a1e0f76c22
Revises: 8f4c1a2d6c9b
Create Date: 2026-03-06

This revision was applied to the sealai_v2 database but its migration file was
never committed to the repository. The schema changes it introduced (audit_log,
store_items tables) are already present in the database. This stub re-anchors the
revision chain so that subsequent migrations (cbc544453b98 and beyond) can apply
cleanly via alembic upgrade head.
"""

revision = "d5a1e0f76c22"
down_revision = "8f4c1a2d6c9b"
branch_labels = None
depends_on = None

from alembic import op


def upgrade() -> None:
    # Schema already present in DB — no DDL to run.
    pass


def downgrade() -> None:
    # Intentionally left empty; downgrade not supported for out-of-band stub.
    pass
