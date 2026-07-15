"""Install non-validating reviewer-governance shadow constraints.

Revision ID: 20260715_0015
Revises: 20260715_0014

PostgreSQL protects new writes without scanning legacy records. Profiling,
quarantine population, validation, role cutover, and feature activation remain
explicit GATE-06/GATE-07/GATE-08 operations. SQLite stays the hermetic lane.
"""

from __future__ import annotations

from alembic import op

revision = "20260715_0015"
down_revision = "20260715_0014"
branch_labels = None
depends_on = None

_CONSTRAINTS = (
    (
        "v2_identity_affiliation_revisions",
        "ck_v2_affiliation_revision_shadow",
        "CHECK (revision >= 1 AND id ~ '^[0-9a-f]{64}$' "
        "AND record_sha256 ~ '^[0-9a-f]{64}$' "
        "AND btrim(subject_ref) <> '' AND btrim(organization_ref) <> '' "
        "AND relationship IN ('employee', 'owner', 'board_member', 'contractor', "
        "'advisor', 'auditor') "
        "AND authority_source IN ('owner_attested_identity_roster', "
        "'independent_hr_register', 'contractual_affiliation_register') "
        "AND btrim(authority_reference) <> '' AND btrim(authority_version) <> '' "
        "AND btrim(recorded_by) <> '' AND recorded_by <> subject_ref "
        "AND status IN ('active', 'revoked', 'quarantined'))",
    ),
    (
        "v2_governance_snapshots",
        "ck_v2_governance_snapshot_shadow",
        "CHECK (resource_version >= 1 AND id ~ '^[0-9a-f]{64}$' "
        "AND btrim(subject_ref) <> '' AND btrim(resource_ref) <> '')",
    ),
    (
        "v2_governance_decisions",
        "ck_v2_governance_decision_shadow",
        "CHECK (resource_version >= 1 AND id ~ '^[0-9a-f]{64}$' "
        "AND first_snapshot_id ~ '^[0-9a-f]{64}$' "
        "AND second_snapshot_id ~ '^[0-9a-f]{64}$' "
        "AND outcome IN ('allow', 'block'))",
    ),
    (
        "v2_governance_quarantine",
        "ck_v2_governance_quarantine_shadow",
        "CHECK (record_fingerprint ~ '^[0-9a-f]{64}$' "
        "AND resolution_status IN ('unresolved', 'resolved', 'rejected'))",
    ),
)

_SNAPSHOT_FOREIGN_KEYS = (
    ("fk_v2_governance_decision_first_snapshot", "first_snapshot_id"),
    ("fk_v2_governance_decision_second_snapshot", "second_snapshot_id"),
)

_IMMUTABLE_TABLES = (
    "v2_identity_affiliation_revisions",
    "v2_governance_snapshots",
    "v2_governance_decisions",
)


def upgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return
    for table, name, expression in _CONSTRAINTS:
        op.execute(
            f'ALTER TABLE "{table}" ADD CONSTRAINT "{name}" {expression} NOT VALID'
        )
    for name, column in _SNAPSHOT_FOREIGN_KEYS:
        op.execute(
            f'ALTER TABLE "v2_governance_decisions" ADD CONSTRAINT "{name}" '
            f'FOREIGN KEY ("{column}") REFERENCES "v2_governance_snapshots" ("id") '
            "NOT VALID"
        )
    op.execute(
        """
        CREATE OR REPLACE FUNCTION sealai_v2_reviewer_governance_immutable()
        RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
          RAISE EXCEPTION 'reviewer-governance authority and audit rows are append-only'
            USING ERRCODE = '55000';
        END;
        $$
        """
    )
    for table in _IMMUTABLE_TABLES:
        op.execute(
            f'CREATE TRIGGER "trg_{table}_immutable" '
            f'BEFORE UPDATE OR DELETE ON "{table}" FOR EACH ROW '
            "EXECUTE FUNCTION sealai_v2_reviewer_governance_immutable()"
        )


def downgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return
    for table in reversed(_IMMUTABLE_TABLES):
        op.execute(f'DROP TRIGGER IF EXISTS "trg_{table}_immutable" ON "{table}"')
    op.execute("DROP FUNCTION IF EXISTS sealai_v2_reviewer_governance_immutable()")
    for name, _column in reversed(_SNAPSHOT_FOREIGN_KEYS):
        op.execute(
            f'ALTER TABLE "v2_governance_decisions" '
            f'DROP CONSTRAINT IF EXISTS "{name}"'
        )
    for table, name, _expression in reversed(_CONSTRAINTS):
        op.execute(f'ALTER TABLE "{table}" DROP CONSTRAINT IF EXISTS "{name}"')
