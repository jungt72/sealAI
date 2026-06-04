"""extend mutation_events with v0.4 audit fields

Revision ID: aa7c1d9e2f43
Revises: f6a7b8c9d0e1
Create Date: 2026-04-26

Purpose
-------
ADR-002 requires key CaseEvent audit fields to be first-class columns, not
only buried in payload JSON. This migration is additive and nullable-safe for
existing rows while new writes populate the fields from case_service.
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "aa7c1d9e2f43"
down_revision = "f6a7b8c9d0e1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    json_type = postgresql.JSONB(astext_type=sa.Text())
    op.add_column(
        "mutation_events",
        sa.Column("source_turn_id", sa.String(64), nullable=True),
    )
    op.add_column(
        "mutation_events",
        sa.Column("source_document_id", sa.String(64), nullable=True),
    )
    op.add_column(
        "mutation_events",
        sa.Column(
            "proposed_delta",
            json_type,
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )
    op.add_column(
        "mutation_events",
        sa.Column(
            "accepted_delta",
            json_type,
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )
    op.add_column(
        "mutation_events",
        sa.Column(
            "rejected_delta",
            json_type,
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )
    op.add_column(
        "mutation_events",
        sa.Column(
            "rejection_reasons",
            json_type,
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )
    op.add_column(
        "mutation_events",
        sa.Column("ruleset_version", sa.String(64), nullable=True),
    )
    op.add_column(
        "mutation_events",
        sa.Column("model_id", sa.String(128), nullable=True),
    )

    op.execute(
        """
        UPDATE mutation_events
        SET
          source_turn_id = COALESCE(payload->>'source_turn_id', payload->>'turn_id'),
          source_document_id = COALESCE(payload->>'source_document_id', payload->>'document_id'),
          proposed_delta = COALESCE(payload->'proposed_delta', payload->'proposed_case_delta', '{}'::jsonb),
          accepted_delta = COALESCE(payload->'accepted_delta', '{}'::jsonb),
          rejected_delta = COALESCE(payload->'rejected_delta', '{}'::jsonb),
          rejection_reasons = COALESCE(payload->'rejection_reasons', '{}'::jsonb),
          ruleset_version = COALESCE(
            payload->>'ruleset_version',
            payload->'run_meta'->>'ruleset_version',
            payload->'snapshot'->>'ruleset_version'
          ),
          model_id = COALESCE(
            payload->>'model_id',
            payload->'run_meta'->>'model_id',
            payload->'snapshot'->>'model_id',
            payload->'snapshot'->>'model_version'
          )
        """
    )

    op.create_index(
        "idx_mutation_events_source_turn_id",
        "mutation_events",
        ["source_turn_id"],
    )
    op.create_index(
        "idx_mutation_events_source_document_id",
        "mutation_events",
        ["source_document_id"],
    )
    op.create_index(
        "idx_mutation_events_ruleset_version",
        "mutation_events",
        ["ruleset_version"],
    )
    op.create_index(
        "idx_mutation_events_model_id",
        "mutation_events",
        ["model_id"],
    )


def downgrade() -> None:
    op.drop_index("idx_mutation_events_model_id", table_name="mutation_events")
    op.drop_index("idx_mutation_events_ruleset_version", table_name="mutation_events")
    op.drop_index(
        "idx_mutation_events_source_document_id", table_name="mutation_events"
    )
    op.drop_index("idx_mutation_events_source_turn_id", table_name="mutation_events")
    op.drop_column("mutation_events", "model_id")
    op.drop_column("mutation_events", "ruleset_version")
    op.drop_column("mutation_events", "rejection_reasons")
    op.drop_column("mutation_events", "rejected_delta")
    op.drop_column("mutation_events", "accepted_delta")
    op.drop_column("mutation_events", "proposed_delta")
    op.drop_column("mutation_events", "source_document_id")
    op.drop_column("mutation_events", "source_turn_id")
