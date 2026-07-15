"""Stage API lifecycle integrity checks without validating legacy data.

Revision ID: 20260715_0015
Revises: 20260715_0014

PostgreSQL constraints are deliberately ``NOT VALID``. No validation, backfill, row-level-security
activation, role grant, or deletion is authorized by this migration.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260715_0015"
down_revision = "20260715_0014"
branch_labels = None
depends_on = None

_CONSTRAINTS = (
    (
        "v2_contributions",
        "ck_v2_contributions_lifecycle_shadow",
        "lifecycle_state IS NULL OR ("
        "admission_request_id IS NOT NULL AND owner_subject_ref IS NOT NULL AND "
        "policy_authority_ref IS NOT NULL AND "
        "purpose_version IS NOT NULL AND consent_version IS NOT NULL AND "
        "rights_basis IS NOT NULL AND license_id IS NOT NULL AND provenance IS NOT NULL AND "
        "document_type IS NOT NULL AND pii_classification IS NOT NULL AND "
        "prompt_trust = 'untrusted' AND prompt_injection_signal IS NOT NULL AND "
        "content_bytes IS NOT NULL AND content_bytes >= 0)",
    ),
    (
        "v2_leads",
        "ck_v2_leads_lifecycle_shadow",
        "lifecycle_state IS NULL OR (admission_request_id IS NOT NULL AND "
        "content_bytes IS NOT NULL AND content_bytes >= 0 AND "
        "policy_authority_ref IS NOT NULL AND purpose_version IS NOT NULL AND "
        "consent_version IS NOT NULL AND handoff_confirmed IS TRUE AND "
        "pii_classification IS NOT NULL AND prompt_trust = 'untrusted' AND "
        "prompt_injection_signal IS NOT NULL)",
    ),
    (
        "v2_api_lifecycle_windows",
        "ck_v2_api_lifecycle_windows_nonnegative_shadow",
        "admitted_count >= 0 AND denied_count >= 0 AND reserved_bytes >= 0",
    ),
    (
        "v2_api_lifecycle_admissions",
        "ck_v2_api_lifecycle_admission_bytes_shadow",
        "estimated_bytes >= 0",
    ),
    (
        "v2_api_lifecycle_receipts",
        "ck_v2_api_lifecycle_receipt_digest_shadow",
        "length(receipt_digest) = 64",
    ),
    (
        "v2_api_lifecycle_events",
        "ck_v2_api_lifecycle_event_digest_shadow",
        "length(event_digest) = 64",
    ),
)


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    inspector = sa.inspect(bind)
    for table, name, expression in _CONSTRAINTS:
        existing = {item["name"] for item in inspector.get_check_constraints(table)}
        if name not in existing:
            op.execute(
                sa.text(
                    f'ALTER TABLE "{table}" ADD CONSTRAINT "{name}" '
                    f"CHECK ({expression}) NOT VALID"
                )
            )


def downgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return
    for table, name, _ in reversed(_CONSTRAINTS):
        op.execute(sa.text(f'ALTER TABLE "{table}" DROP CONSTRAINT IF EXISTS "{name}"'))
