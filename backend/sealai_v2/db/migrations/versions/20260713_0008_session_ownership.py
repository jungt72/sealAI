"""Bind persisted private user data to a verified Keycloak subject.

Revision ID: 20260713_0008
Revises: 20260712_0007
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "20260713_0008"
down_revision = "20260712_0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    columns = {column["name"] for column in inspector.get_columns("v2_sessions")}
    if "owner_subject" not in columns:
        with op.batch_alter_table("v2_sessions") as batch:
            batch.add_column(sa.Column("owner_subject", sa.String(255), nullable=True))
            batch.create_index(
                "ix_v2_sessions_owner_subject", ["owner_subject"], unique=False
            )
    memory_columns = {
        column["name"] for column in inspector.get_columns("v2_memory_items")
    }
    if "owner_subject" not in memory_columns:
        with op.batch_alter_table("v2_memory_items") as batch:
            batch.add_column(sa.Column("owner_subject", sa.String(255), nullable=True))
            batch.create_index(
                "ix_v2_memory_items_owner_subject", ["owner_subject"], unique=False
            )
    durable_columns = {
        column["name"] for column in inspector.get_columns("v2_durable_facts")
    }
    with op.batch_alter_table("v2_durable_facts") as batch:
        if "owner_subject" not in durable_columns:
            batch.add_column(sa.Column("owner_subject", sa.String(255), nullable=True))
            batch.create_index(
                "ix_v2_durable_facts_owner_subject", ["owner_subject"], unique=False
            )
        if "original_feld" not in durable_columns:
            batch.add_column(sa.Column("original_feld", sa.String(255), nullable=True))


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    durable_indexes = {
        index["name"] for index in inspector.get_indexes("v2_durable_facts")
    }
    durable_columns = {
        column["name"] for column in inspector.get_columns("v2_durable_facts")
    }
    with op.batch_alter_table("v2_durable_facts") as batch:
        if "original_feld" in durable_columns:
            batch.drop_column("original_feld")
        if "owner_subject" in durable_columns:
            if "ix_v2_durable_facts_owner_subject" in durable_indexes:
                batch.drop_index("ix_v2_durable_facts_owner_subject")
            batch.drop_column("owner_subject")
    indexes = {index["name"] for index in inspector.get_indexes("v2_sessions")}
    columns = {column["name"] for column in inspector.get_columns("v2_sessions")}
    if "owner_subject" in columns:
        with op.batch_alter_table("v2_sessions") as batch:
            if "ix_v2_sessions_owner_subject" in indexes:
                batch.drop_index("ix_v2_sessions_owner_subject")
            batch.drop_column("owner_subject")
    memory_indexes = {
        index["name"] for index in inspector.get_indexes("v2_memory_items")
    }
    memory_columns = {
        column["name"] for column in inspector.get_columns("v2_memory_items")
    }
    if "owner_subject" in memory_columns:
        with op.batch_alter_table("v2_memory_items") as batch:
            if "ix_v2_memory_items_owner_subject" in memory_indexes:
                batch.drop_index("ix_v2_memory_items_owner_subject")
            batch.drop_column("owner_subject")
