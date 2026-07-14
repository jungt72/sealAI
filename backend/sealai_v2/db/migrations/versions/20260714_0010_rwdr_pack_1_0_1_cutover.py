"""Clear ephemeral rwdr.v1@1.0.0 interview state for the 1.0.1 cutover.

Revision ID: 20260714_0010
Revises: 20260713_0009

The append-only shadow decision table is deliberately untouched. Open pending
interview state is reconstructable from canonical CaseStateV2 and must not be
silently interpreted under a different pack version.
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "20260714_0010"
down_revision = "20260713_0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    tables = set(sa.inspect(op.get_bind()).get_table_names())
    if "v2_interview_state" not in tables:
        return
    op.execute(
        sa.text(
            "DELETE FROM v2_interview_state "
            "WHERE pack_id = :pack_id AND pack_version = :pack_version"
        ).bindparams(pack_id="rwdr.v1", pack_version="1.0.0")
    )


def downgrade() -> None:
    # Ephemeral pending state is intentionally not reconstructed. Canonical case
    # facts and append-only shadow evidence were never deleted by the upgrade.
    pass
