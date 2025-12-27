"""add chat_transcripts table

Revision ID: b9404c037af5
Revises: 8b7f4c21d3ab
Create Date: 2025-10-02 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "b9404c037af5"
down_revision = "8b7f4c21d3ab"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "chat_transcripts",
        sa.Column("chat_id", sa.String(), primary_key=True),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("contributors", sa.JSON(), nullable=True),
        sa.Column("metadata", sa.JSON(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_chat_transcripts_user_id", "chat_transcripts", ["user_id"])
    op.create_index("ix_chat_transcripts_created_at", "chat_transcripts", ["created_at"])


def downgrade():
    op.drop_index("ix_chat_transcripts_created_at", table_name="chat_transcripts")
    op.drop_index("ix_chat_transcripts_user_id", table_name="chat_transcripts")
    op.drop_table("chat_transcripts")

