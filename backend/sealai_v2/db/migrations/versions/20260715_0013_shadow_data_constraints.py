"""Install non-validating shadow constraints for ownership and case boundaries.

Revision ID: 20260715_0013
Revises: 20260715_0012

PostgreSQL ``NOT VALID`` constraints protect new writes without scanning or rewriting legacy data.
Constraint validation, ownership profiling/backfill/quarantine, RLS policies, application/worker role
cutover, and FORCE ROW LEVEL SECURITY are intentionally absent: each is an explicit GATE-07 step.
SQLite is the hermetic unit-test lane and cannot represent PostgreSQL NOT VALID semantics, so it is
left unchanged and covered by source-contract tests.
"""

from __future__ import annotations

from alembic import op

revision = "20260715_0013"
down_revision = "20260715_0012"
branch_labels = None
depends_on = None

_CONSTRAINTS = (
    (
        "v2_sessions",
        "ck_v2_sessions_boundary_shadow",
        "CHECK (case_revision >= 0 AND turns >= 0 "
        "AND (owner_subject IS NULL OR btrim(owner_subject) <> '') "
        "AND (ownership_state IS NULL OR ownership_state IN ('owned', 'quarantined')))",
    ),
    (
        "v2_durable_facts",
        "ck_v2_durable_facts_owner_shadow",
        "CHECK ((owner_subject IS NULL OR btrim(owner_subject) <> '') "
        "AND (ownership_state IS NULL OR ownership_state IN ('owned', 'quarantined')))",
    ),
    (
        "v2_memory_items",
        "ck_v2_memory_items_owner_shadow",
        "CHECK ((owner_subject IS NULL OR btrim(owner_subject) <> '') "
        "AND (ownership_state IS NULL OR ownership_state IN ('owned', 'quarantined')))",
    ),
    (
        "v2_leads",
        "ck_v2_leads_case_owner_shadow",
        "CHECK (((owner_subject IS NULL) = (case_id IS NULL)) "
        "AND ((case_id IS NULL) = (case_revision IS NULL)) "
        "AND (owner_subject IS NULL OR btrim(owner_subject) <> '') "
        "AND (case_id IS NULL OR btrim(case_id) <> '') "
        "AND (case_revision IS NULL OR case_revision >= 0) "
        "AND (ownership_state IS NULL OR ownership_state IN ('owned', 'quarantined')))",
    ),
)

_FOREIGN_KEYS = (
    ("v2_messages", "fk_v2_messages_session_shadow", "session_id"),
    ("v2_facts", "fk_v2_facts_session_shadow", "session_id"),
    ("v2_derived", "fk_v2_derived_session_shadow", "session_id"),
    ("v2_interview_state", "fk_v2_interview_state_session_shadow", "session_id"),
    ("v2_leads", "fk_v2_leads_case_shadow", "case_id"),
)


def upgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return
    for table, name, expression in _CONSTRAINTS:
        op.execute(
            f'ALTER TABLE "{table}" ADD CONSTRAINT "{name}" {expression} NOT VALID'
        )
    for table, name, case_column in _FOREIGN_KEYS:
        op.execute(
            f'ALTER TABLE "{table}" ADD CONSTRAINT "{name}" '
            f'(tenant_id, "{case_column}") REFERENCES "v2_sessions" '
            "(tenant_id, session_id) NOT VALID"
        )


def downgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return
    for table, name, _case_column in reversed(_FOREIGN_KEYS):
        op.execute(f'ALTER TABLE "{table}" DROP CONSTRAINT IF EXISTS "{name}"')
    for table, name, _expression in reversed(_CONSTRAINTS):
        op.execute(f'ALTER TABLE "{table}" DROP CONSTRAINT IF EXISTS "{name}"')
