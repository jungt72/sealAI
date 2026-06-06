"""create outcome_records table (V1.8 §6.5 — the moat)

Revision ID: d1e2f3a4b5c6
Revises: c7d8e9f0a1b2
Create Date: 2026-06-06

Purpose
-------
Tenant-scoped persistence for V1.8 §6.5 Outcome-Records — the third and most
valuable knowledge source (cross-manufacturer field data per application
profile, §4.3). Raw outcomes are tenant-scoped (``tenant_id`` NOT NULL, like the
hardened cases/mutation_events tables); only aggregated, anonymized richtwerte
reach the global layer above a minimum count (§8 governance, later patch).

An outcome is an observation — ``suspected_cause`` is a hypothesis, never a
verdict (Safety-Formel). No FK to cases: outcomes survive the case lifecycle so
the field-data record (the moat) is preserved for aggregation; ``case_id`` is a
plain scoping column.

Columns
-------
- outcome_id            VARCHAR(36) PK
- case_id               VARCHAR(36) NULL (scoping only, no FK)
- tenant_id             VARCHAR(255) NOT NULL  (raw outcomes are tenant-scoped)
- position_id           VARCHAR(64)  NOT NULL DEFAULT 'pos_1'  (§6.6 vorsorge)
- solution_ref          VARCHAR(64)  NULL
- event                 VARCHAR(32)  NOT NULL DEFAULT 'incident'
                        CHECK installed|in_operation|incident|replaced|closed
- installed_at          VARCHAR(32)  NULL
- runtime_hours_estimate INTEGER     NULL
- outcome_pattern       VARCHAR(128) NULL
- suspected_cause       VARCHAR(255) NULL
- evidence_refs         JSONB        NOT NULL DEFAULT '[]'
- confidence            VARCHAR(16)  NOT NULL DEFAULT 'medium'
                        CHECK low|medium|high
- created_at            TIMESTAMPTZ  NOT NULL DEFAULT NOW()
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "d1e2f3a4b5c6"
down_revision = "c7d8e9f0a1b2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "outcome_records",
        sa.Column("outcome_id", sa.String(36), primary_key=True),
        sa.Column("case_id", sa.String(36), nullable=True),
        sa.Column("tenant_id", sa.String(255), nullable=False),
        sa.Column("position_id", sa.String(64), nullable=False, server_default="pos_1"),
        sa.Column("solution_ref", sa.String(64), nullable=True),
        sa.Column("event", sa.String(32), nullable=False, server_default="incident"),
        sa.Column("installed_at", sa.String(32), nullable=True),
        sa.Column("runtime_hours_estimate", sa.Integer(), nullable=True),
        sa.Column("outcome_pattern", sa.String(128), nullable=True),
        sa.Column("suspected_cause", sa.String(255), nullable=True),
        sa.Column(
            "evidence_refs",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("confidence", sa.String(16), nullable=False, server_default="medium"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "event IN ('installed', 'in_operation', 'incident', "
            "'replaced', 'closed')",
            name="valid_outcome_event",
        ),
        sa.CheckConstraint(
            "confidence IN ('low', 'medium', 'high')",
            name="valid_outcome_confidence",
        ),
    )
    op.create_index("idx_outcome_records_tenant_id", "outcome_records", ["tenant_id"])
    op.create_index("idx_outcome_records_case_id", "outcome_records", ["case_id"])
    op.create_index(
        "idx_outcome_records_pattern", "outcome_records", ["outcome_pattern"]
    )


def downgrade() -> None:
    op.drop_index("idx_outcome_records_pattern", table_name="outcome_records")
    op.drop_index("idx_outcome_records_case_id", table_name="outcome_records")
    op.drop_index("idx_outcome_records_tenant_id", table_name="outcome_records")
    op.drop_table("outcome_records")
