"""create outbox table for async task queue

Revision ID: 4c2f8a9d1b73
Revises: 7e9c4a2b8d31
Create Date: 2026-04-19

Purpose
-------
Creates the outbox table -- the durable async task queue for work that
must happen as a consequence of a case mutation but does not block the
mutation itself. Per Founder Decision #1 and Supplement v1 Chapter 34,
case_service.apply_mutation() (Patch 1.5) enqueues tasks here; the
outbox_worker (later sprint per Plan) drains them.

Examples of tasks enqueued to outbox:
- risk_score_recompute -- re-run risk engine after relevant inputs changed
- notify_audit_log -- push mutation to long-term audit store
- project_case_snapshot -- refresh projection cache

Columns
-------
- outbox_id         VARCHAR(36) PK
- case_id           VARCHAR(36) NULL FK -> cases.id ON DELETE CASCADE
                    (nullable: some system tasks have no case context)
- mutation_id       VARCHAR(36) NULL FK -> mutation_events.mutation_id
                    (nullable: some tasks are not triggered by mutations;
                    no cascade: task survives audit-trail archival)
- tenant_id         VARCHAR(255) NULL
- task_type         VARCHAR(64) NOT NULL -- enum in Patch 1.4
- payload           JSONB NOT NULL
- status            VARCHAR(32) NOT NULL DEFAULT 'pending'
                    Constrained: 'pending' | 'in_progress' | 'completed'
                                 | 'failed_retryable' | 'failed_permanent'
- priority          INTEGER NOT NULL DEFAULT 0
                    (higher = earlier; signed int allows future negative priorities)
- attempts          INTEGER NOT NULL DEFAULT 0
- max_attempts      INTEGER NOT NULL DEFAULT 5
- next_attempt_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
- last_error        TEXT NULL
- created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
- completed_at      TIMESTAMPTZ NULL

Constraints
-----------
- valid_status CHECK: only the 5 allowed status values
- FK case_id -> cases.id ON DELETE CASCADE
- FK mutation_id -> mutation_events.mutation_id (no cascade)

Indexes
-------
- idx_outbox_status_priority: (status, priority DESC, next_attempt_at)
  -- worker's primary query: "next pending task by priority"
- idx_outbox_case_id: (case_id) -- case-scoped task lookup
- idx_outbox_tenant_id: (tenant_id) -- tenant-scoped admin/audit views

Type deviations from plan
-------------------------
1. UUID -> VARCHAR(36): consistent with Patch 1.1/1.2 precedent
   (cases.id is VARCHAR(36); avoids Postgres-specific gen_random_uuid())
2. tenant_id UUID -> VARCHAR(255): matches cases.tenant_id pattern
3. cases(case_id) -> cases(id): actual PK column is named 'id'

FK cascade semantics
--------------------
- case_id CASCADE: when a case is deleted, its pending tasks go too
  (GDPR-compatible, consistent with mutation_events cascade)
- mutation_id no cascade: mutations may be archived/tombstoned while
  tasks remain in flight; task remains tied to its own payload and status
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "4c2f8a9d1b73"
down_revision = "7e9c4a2b8d31"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "outbox",
        sa.Column("outbox_id", sa.String(36), primary_key=True),
        sa.Column("case_id", sa.String(36), nullable=True),
        sa.Column("mutation_id", sa.String(36), nullable=True),
        sa.Column("tenant_id", sa.String(255), nullable=True),
        sa.Column("task_type", sa.String(64), nullable=False),
        sa.Column(
            "payload",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column("status", sa.String(32), nullable=False, server_default="pending"),
        sa.Column("priority", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("max_attempts", sa.Integer(), nullable=False, server_default="5"),
        sa.Column(
            "next_attempt_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["case_id"],
            ["cases.id"],
            ondelete="CASCADE",
            name="fk_outbox_case_id",
        ),
        sa.ForeignKeyConstraint(
            ["mutation_id"],
            ["mutation_events.mutation_id"],
            name="fk_outbox_mutation_id",
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'in_progress', 'completed', "
            "'failed_retryable', 'failed_permanent')",
            name="valid_status",
        ),
    )

    # Compound index for worker's hottest query.
    op.create_index(
        "idx_outbox_status_priority",
        "outbox",
        ["status", sa.text("priority DESC"), "next_attempt_at"],
    )
    op.create_index("idx_outbox_case_id", "outbox", ["case_id"])
    op.create_index("idx_outbox_tenant_id", "outbox", ["tenant_id"])


def downgrade() -> None:
    op.drop_index("idx_outbox_tenant_id", table_name="outbox")
    op.drop_index("idx_outbox_case_id", table_name="outbox")
    op.drop_index("idx_outbox_status_priority", table_name="outbox")
    op.drop_table("outbox")
