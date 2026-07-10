"""Freeze the pre-Alembic V2 schema as an immutable baseline.

Existing installations are adopted only when the complete baseline is present.
Fresh databases are created from explicit operations; this revision deliberately
does not import live ORM metadata, so later model changes cannot rewrite history.

Revision ID: 20260710_0001
Revises: None
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "20260710_0001"
down_revision = None
branch_labels = None
depends_on = None

_EXPECTED_COLUMNS = {
    "v2_contributions": {
        "id",
        "anonym",
        "tenant_ref",
        "subject_ref",
        "situation",
        "case_state_json",
        "recommendation",
        "outcome",
        "created_at",
        "status",
        "review_note",
    },
    "v2_derived": {"tenant_id", "session_id", "slice_json"},
    "v2_durable_facts": {"tenant_id", "feld", "wert", "provenance", "as_of_turn"},
    "v2_facts": {"tenant_id", "session_id", "feld", "wert", "provenance", "as_of_turn"},
    "v2_hersteller_partner": {
        "hersteller",
        "firmenname",
        "aktiv",
        "lead_email",
        "website",
        "beschreibung",
        "standort",
        "kontakt_oeffentlich",
        "partner_seit",
        "plan",
        "werkstoffe",
        "bauformen",
        "groessen",
        "zertifikate",
    },
    "v2_leads": {
        "id",
        "partner_id",
        "firmenname",
        "lead_email",
        "tenant_id",
        "session_id",
        "briefing_title",
        "briefing_body",
        "created_at",
        "status",
    },
    "v2_legal_acceptance": {
        "tenant_id",
        "company_name",
        "business_email",
        "role",
        "vat_id",
        "legal_basis_accepted",
        "dpa_accepted",
        "business_user_confirmed",
        "accepted_terms_version",
        "accepted_privacy_version",
        "accepted_dpa_version",
        "accepted_at",
        "accepted_ip_hash",
        "accepted_user_agent",
    },
    "v2_memory_events": {
        "id",
        "memory_item_id",
        "tenant_id",
        "event_type",
        "from_status",
        "to_status",
        "actor",
        "note",
        "created_at",
    },
    "v2_memory_items": {
        "id",
        "tenant_id",
        "scope",
        "scope_id",
        "workspace_id",
        "project_id",
        "case_id",
        "user_id",
        "session_id",
        "type",
        "status",
        "content",
        "semantic_key",
        "version",
        "qdrant_sync_state",
        "qdrant_synced_version",
        "qdrant_synced_at",
        "confidence",
        "sensitivity",
        "subject_hash",
        "supersedes_memory_id",
        "deprecated_by_memory_id",
        "created_at",
        "updated_at",
        "deleted_at",
        "purge_after",
    },
    "v2_memory_outbox": {
        "id",
        "memory_item_id",
        "tenant_id",
        "event_type",
        "target",
        "payload",
        "status",
        "attempts",
        "last_error",
        "created_at",
        "processed_at",
        "next_attempt_at",
    },
    "v2_memory_sources": {
        "id",
        "memory_item_id",
        "kind",
        "session_id",
        "turn_id",
        "note",
        "source_ref",
        "message_id",
        "document_id",
        "case_snapshot_id",
        "created_at",
    },
    "v2_messages": {"tenant_id", "session_id", "idx", "role", "text"},
    "v2_sessions": {
        "tenant_id",
        "session_id",
        "turns",
        "title",
        "created_at",
        "updated_at",
    },
}


def _create_schema() -> None:
    op.create_table(
        "v2_contributions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("anonym", sa.Boolean(), nullable=False),
        sa.Column("tenant_ref", sa.String(255), nullable=False),
        sa.Column("subject_ref", sa.String(255), nullable=False),
        sa.Column("situation", sa.Text(), nullable=False),
        sa.Column("case_state_json", sa.JSON(), nullable=False),
        sa.Column("recommendation", sa.Text(), nullable=False),
        sa.Column("outcome", sa.Text(), nullable=False),
        sa.Column("created_at", sa.String(32), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("review_note", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "v2_derived",
        sa.Column("tenant_id", sa.String(255), nullable=False),
        sa.Column("session_id", sa.String(255), nullable=False),
        sa.Column("slice_json", sa.JSON(), nullable=False),
        sa.PrimaryKeyConstraint("tenant_id", "session_id"),
    )
    for name in ("v2_durable_facts", "v2_facts"):
        columns = [
            sa.Column("tenant_id", sa.String(255), nullable=False),
        ]
        if name == "v2_facts":
            columns.append(sa.Column("session_id", sa.String(255), nullable=False))
        columns.extend(
            [
                sa.Column("feld", sa.String(255), nullable=False),
                sa.Column("wert", sa.Text(), nullable=False),
                sa.Column("provenance", sa.String(64), nullable=False),
                sa.Column("as_of_turn", sa.Integer(), nullable=False),
            ]
        )
        primary_key = (
            ("tenant_id", "session_id", "feld")
            if name == "v2_facts"
            else ("tenant_id", "feld")
        )
        op.create_table(name, *columns, sa.PrimaryKeyConstraint(*primary_key))
    op.create_table(
        "v2_hersteller_partner",
        sa.Column("hersteller", sa.String(255), nullable=False),
        sa.Column("firmenname", sa.String(255), nullable=False),
        sa.Column("aktiv", sa.Boolean(), nullable=False),
        sa.Column("lead_email", sa.String(320), nullable=False),
        sa.Column("website", sa.String(500), nullable=False),
        sa.Column("beschreibung", sa.Text(), nullable=False),
        sa.Column("standort", sa.String(255), nullable=False),
        sa.Column("kontakt_oeffentlich", sa.String(320), nullable=False),
        sa.Column("partner_seit", sa.String(32), nullable=False),
        sa.Column("plan", sa.String(64), nullable=False),
        sa.Column("werkstoffe", sa.JSON(), nullable=False),
        sa.Column("bauformen", sa.JSON(), nullable=False),
        sa.Column("groessen", sa.String(255), nullable=False),
        sa.Column("zertifikate", sa.JSON(), nullable=False),
        sa.PrimaryKeyConstraint("hersteller"),
    )
    op.create_table(
        "v2_leads",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("partner_id", sa.String(255), nullable=False),
        sa.Column("firmenname", sa.String(255), nullable=False),
        sa.Column("lead_email", sa.String(320), nullable=False),
        sa.Column("tenant_id", sa.String(255), nullable=False),
        sa.Column("session_id", sa.String(255), nullable=False),
        sa.Column("briefing_title", sa.Text(), nullable=False),
        sa.Column("briefing_body", sa.Text(), nullable=False),
        sa.Column("created_at", sa.String(32), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "v2_legal_acceptance",
        sa.Column("tenant_id", sa.String(255), nullable=False),
        sa.Column("company_name", sa.String(255), nullable=False),
        sa.Column("business_email", sa.String(320), nullable=False),
        sa.Column("role", sa.String(128), nullable=False),
        sa.Column("vat_id", sa.String(64), nullable=False),
        sa.Column("legal_basis_accepted", sa.Boolean(), nullable=False),
        sa.Column("dpa_accepted", sa.Boolean(), nullable=False),
        sa.Column("business_user_confirmed", sa.Boolean(), nullable=False),
        sa.Column("accepted_terms_version", sa.String(32), nullable=False),
        sa.Column("accepted_privacy_version", sa.String(32), nullable=False),
        sa.Column("accepted_dpa_version", sa.String(32), nullable=False),
        sa.Column("accepted_at", sa.String(32), nullable=False),
        sa.Column("accepted_ip_hash", sa.String(64), nullable=False),
        sa.Column("accepted_user_agent", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("tenant_id"),
    )
    op.create_table(
        "v2_memory_events",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("memory_item_id", sa.String(64), nullable=False),
        sa.Column("tenant_id", sa.String(255), nullable=False),
        sa.Column("event_type", sa.String(32), nullable=False),
        sa.Column("from_status", sa.String(32), nullable=True),
        sa.Column("to_status", sa.String(32), nullable=False),
        sa.Column("actor", sa.String(255), nullable=False),
        sa.Column("note", sa.Text(), nullable=False),
        sa.Column("created_at", sa.String(32), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_v2_memory_events_memory_item_id", "v2_memory_events", ["memory_item_id"]
    )
    op.create_index("ix_v2_memory_events_tenant_id", "v2_memory_events", ["tenant_id"])
    op.create_table(
        "v2_memory_items",
        sa.Column("id", sa.String(64), nullable=False),
        sa.Column("tenant_id", sa.String(255), nullable=False),
        sa.Column("scope", sa.String(32), nullable=False),
        sa.Column("scope_id", sa.String(255), nullable=False),
        sa.Column("workspace_id", sa.String(255), nullable=True),
        sa.Column("project_id", sa.String(255), nullable=True),
        sa.Column("case_id", sa.String(255), nullable=True),
        sa.Column("user_id", sa.String(255), nullable=True),
        sa.Column("session_id", sa.String(255), nullable=True),
        sa.Column("type", sa.String(32), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("semantic_key", sa.String(512), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("qdrant_sync_state", sa.String(32), nullable=False),
        sa.Column("qdrant_synced_version", sa.Integer(), nullable=True),
        sa.Column("qdrant_synced_at", sa.String(32), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("sensitivity", sa.String(64), nullable=False),
        sa.Column("subject_hash", sa.String(128), nullable=True),
        sa.Column("supersedes_memory_id", sa.String(64), nullable=True),
        sa.Column("deprecated_by_memory_id", sa.String(64), nullable=True),
        sa.Column("created_at", sa.String(32), nullable=False),
        sa.Column("updated_at", sa.String(32), nullable=False),
        sa.Column("deleted_at", sa.String(32), nullable=True),
        sa.Column("purge_after", sa.String(32), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    for column in (
        "case_id",
        "project_id",
        "semantic_key",
        "session_id",
        "status",
        "subject_hash",
        "tenant_id",
        "user_id",
        "workspace_id",
    ):
        op.create_index(f"ix_v2_memory_items_{column}", "v2_memory_items", [column])
    op.create_table(
        "v2_memory_outbox",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("memory_item_id", sa.String(64), nullable=False),
        sa.Column("tenant_id", sa.String(255), nullable=False),
        sa.Column("event_type", sa.String(32), nullable=False),
        sa.Column("target", sa.String(32), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=True),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("last_error", sa.Text(), nullable=False),
        sa.Column("created_at", sa.String(32), nullable=False),
        sa.Column("processed_at", sa.String(32), nullable=True),
        sa.Column("next_attempt_at", sa.String(32), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    for column in ("memory_item_id", "next_attempt_at", "status", "tenant_id"):
        op.create_index(f"ix_v2_memory_outbox_{column}", "v2_memory_outbox", [column])
    op.create_table(
        "v2_memory_sources",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("memory_item_id", sa.String(64), nullable=False),
        sa.Column("kind", sa.String(64), nullable=False),
        sa.Column("session_id", sa.String(255), nullable=True),
        sa.Column("turn_id", sa.String(255), nullable=True),
        sa.Column("note", sa.Text(), nullable=False),
        sa.Column("source_ref", sa.String(500), nullable=True),
        sa.Column("message_id", sa.String(255), nullable=True),
        sa.Column("document_id", sa.String(255), nullable=True),
        sa.Column("case_snapshot_id", sa.String(255), nullable=True),
        sa.Column("created_at", sa.String(32), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_v2_memory_sources_memory_item_id", "v2_memory_sources", ["memory_item_id"]
    )
    op.create_table(
        "v2_messages",
        sa.Column("tenant_id", sa.String(255), nullable=False),
        sa.Column("session_id", sa.String(255), nullable=False),
        sa.Column("idx", sa.Integer(), nullable=False),
        sa.Column("role", sa.String(16), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("tenant_id", "session_id", "idx"),
    )
    op.create_table(
        "v2_sessions",
        sa.Column("tenant_id", sa.String(255), nullable=False),
        sa.Column("session_id", sa.String(255), nullable=False),
        sa.Column("turns", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(200), nullable=True),
        sa.Column("created_at", sa.String(32), nullable=True),
        sa.Column("updated_at", sa.String(32), nullable=True),
        sa.PrimaryKeyConstraint("tenant_id", "session_id"),
    )
    op.create_index("ix_v2_sessions_updated_at", "v2_sessions", ["updated_at"])


def _validate_existing_schema(inspector: sa.Inspector) -> bool:
    existing = set(inspector.get_table_names()) & set(_EXPECTED_COLUMNS)
    if not existing:
        return False
    missing_tables = sorted(set(_EXPECTED_COLUMNS) - set(inspector.get_table_names()))
    missing_columns = {
        table: sorted(columns - {c["name"] for c in inspector.get_columns(table)})
        for table, columns in _EXPECTED_COLUMNS.items()
        if table in set(inspector.get_table_names())
        and columns - {c["name"] for c in inspector.get_columns(table)}
    }
    if missing_tables or missing_columns:
        raise RuntimeError(
            "refusing to baseline a partial V2 schema or drifted V2 schema; "
            f"missing tables={missing_tables}, missing columns={missing_columns}"
        )
    return True


def upgrade() -> None:
    if not _validate_existing_schema(sa.inspect(op.get_bind())):
        _create_schema()


def downgrade() -> None:
    for table in reversed(tuple(_EXPECTED_COLUMNS)):
        op.drop_table(table)
