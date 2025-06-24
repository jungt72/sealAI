"""add form_results table

Revision ID: 70968fe4c62e
Revises: 963dc293d186
Create Date: 2025-04-24 11:27:46.686028
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '70968fe4c62e'
down_revision = '963dc293d186'
branch_labels = None
depends_on = None

def upgrade():
    op.create_table(
        'form_results',
        sa.Column('id', sa.String(), primary_key=True, index=True),
        sa.Column('username', sa.String(), nullable=False, index=True),
        sa.Column('radial_clearance', sa.Float(), nullable=False),
        sa.Column('tolerance_fit', sa.String(), nullable=False),
        sa.Column('result_text', sa.String(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index('ix_form_results_created_at', 'form_results', ['created_at'])

def downgrade():
    op.drop_index('ix_form_results_created_at', table_name='form_results')
    op.drop_table('form_results')
