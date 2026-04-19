"""create mutation_events table for case state change audit trail

Revision ID: 7e9c4a2b8d31
Revises: 6d8f1b3a9c20
Create Date: 2026-04-19

Purpose
-------
Creates the mutation_events table -- the immutable audit trail for every
state mutation applied to a case. Per Founder Decision #1 and Supplement
v1 Chapter 34, every change to case state MUST produce a mutation_events
row. case_service.apply_mutation() (Patch 1.5) is the single write path.

Columns
-------
- mutation_id          VARCHAR(36) PK -- unique identifier per mutation
- case_id              VARCHAR(36) NOT NULL FK -> cases.id ON DELETE CASCADE
- tenant_id            VARCHAR(255) NULL -- denormalized from cases for
                       query-scope efficiency
- event_type           VARCHAR(64) NOT NULL -- enum string; Python enum
                       defined in Patch 1.4 (MutationEventType)
- payload              JSONB NOT NULL -- the delta (fields changed, new
                       values, etc.); shape depends on event_type
- case_revision_before INTEGER NOT NULL -- revision value before mutation
- case_revision_after  INTEGER NOT NULL -- revision value after mutation
- actor                VARCHAR(128) NOT NULL -- identifier of the actor
                       (user id, service name, etc.)
- actor_type           VARCHAR(32) NOT NULL -- enum string; Python enum
                       defined in Patch 1.4 (ActorType)
- created_at           TIMESTAMPTZ NOT NULL DEFAULT NOW()

Type deviation from plan
------------------------
Plan Patch 1.2 specifies UUID types and `cases(case_id)` FK. Reality:
- cases PK is `id` VARCHAR(36), not `case_id`
- VARCHAR(36) is used throughout Phase 1a per Patch 1.1 precedent
  for consistency with existing cases.id and user_id conventions.

mutation_id defaults are application-generated (SQLAlchemy-side via
Python's uuid.uuid4() in the ORM layer added in Patch 1.4 or 1.5),
not Postgres-side gen_random_uuid(). This keeps schema SQLite-compatible
for test environments.

FK semantics
------------
ON DELETE CASCADE on case_id: when a case is deleted, its mutation
history goes with it. This is correct for GDPR-compatible user data
deletion and consistent with existing cases FK rules (case_state_snapshots,
inquiry_deliveries, inquiry_audit all use CASCADE).

Indexes
-------
Four indexes support Sprint 1-5 query patterns:
- idx_mutation_events_case_id: look up all mutations for a case
- idx_mutation_events_tenant_id: tenant-scoped queries (projection, audit)
- idx_mutation_events_event_type: event-type filtering (analytics, debug)
- idx_mutation_events_created_at DESC: recent-events view (UI, dashboards)

Writes
------
This migration creates an EMPTY table. No data is seeded. Inserts come
via case_service.apply_mutation() (Patch 1.5) -- never directly.
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "7e9c4a2b8d31"
down_revision = "6d8f1b3a9c20"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "mutation_events",
        sa.Column("mutation_id", sa.String(36), primary_key=True),
        sa.Column("case_id", sa.String(36), nullable=False),
        sa.Column("tenant_id", sa.String(255), nullable=True),
        sa.Column("event_type", sa.String(64), nullable=False),
        sa.Column(
            "payload",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("case_revision_before", sa.Integer(), nullable=False),
        sa.Column("case_revision_after", sa.Integer(), nullable=False),
        sa.Column("actor", sa.String(128), nullable=False),
        sa.Column("actor_type", sa.String(32), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["case_id"],
            ["cases.id"],
            ondelete="CASCADE",
            name="fk_mutation_events_case_id",
        ),
    )

    op.create_index(
        "idx_mutation_events_case_id",
        "mutation_events",
        ["case_id"],
    )
    op.create_index(
        "idx_mutation_events_tenant_id",
        "mutation_events",
        ["tenant_id"],
    )
    op.create_index(
        "idx_mutation_events_event_type",
        "mutation_events",
        ["event_type"],
    )
    op.create_index(
        "idx_mutation_events_created_at",
        "mutation_events",
        [sa.text("created_at DESC")],
    )


def downgrade() -> None:
    op.drop_index("idx_mutation_events_created_at", table_name="mutation_events")
    op.drop_index("idx_mutation_events_event_type", table_name="mutation_events")
    op.drop_index("idx_mutation_events_tenant_id", table_name="mutation_events")
    op.drop_index("idx_mutation_events_case_id", table_name="mutation_events")
    op.drop_table("mutation_events")
