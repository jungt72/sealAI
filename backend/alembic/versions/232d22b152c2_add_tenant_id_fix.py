"""add_tenant_id_fix

Revision ID: 232d22b152c2
Revises: 8f4c1a2d6c9b
Create Date: 2026-01-13 09:30:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.engine import reflection

# revision identifiers, used by Alembic.
revision = '232d22b152c2'
down_revision = '8f4c1a2d6c9b'
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = reflection.Inspector.from_engine(conn)
    
    # 1. chat_transcripts (Handle existing tenant_id)
    ct_columns = [c['name'] for c in inspector.get_columns('chat_transcripts')]
    if 'tenant_id' not in ct_columns:
        print("Adding tenant_id to chat_transcripts")
        op.add_column('chat_transcripts', sa.Column('tenant_id', sa.String(), nullable=True))
        op.create_index(op.f('ix_chat_transcripts_tenant_id'), 'chat_transcripts', ['tenant_id'], unique=False)
    else:
        print("tenant_id already exists in chat_transcripts - skipping add_column")
        # Ensure index exists?
        indexes = [i['name'] for i in inspector.get_indexes('chat_transcripts')]
        if 'ix_chat_transcripts_tenant_id' not in indexes:
             op.create_index(op.f('ix_chat_transcripts_tenant_id'), 'chat_transcripts', ['tenant_id'], unique=False)

    # 2. form_results
    fr_columns = [c['name'] for c in inspector.get_columns('form_results')]
    if 'tenant_id' not in fr_columns:
        print("Adding tenant_id to form_results (nullable)")
        op.add_column('form_results', sa.Column('tenant_id', sa.String(), nullable=True))
        
        # Backfill
        print("Backfilling form_results.tenant_id from username")
        op.execute("UPDATE form_results SET tenant_id = username WHERE tenant_id IS NULL")
        
        # Set Not Null
        print("Setting form_results.tenant_id NOT NULL")
        op.alter_column('form_results', 'tenant_id', nullable=False)
        
        # Index
        op.create_index(op.f('ix_form_results_tenant_id'), 'form_results', ['tenant_id'], unique=False)

    # 3. chat_messages
    # Check if table exists first (just in case)
    tables = inspector.get_table_names()
    if 'chat_messages' in tables:
        cm_columns = [c['name'] for c in inspector.get_columns('chat_messages')]
        if 'tenant_id' not in cm_columns:
            print("Adding tenant_id to chat_messages (nullable)")
            op.add_column('chat_messages', sa.Column('tenant_id', sa.String(), nullable=True))
            
            # Backfill
            print("Backfilling chat_messages.tenant_id")
            # Logic: COALESCE(username, session_id, 'default')
            op.execute("UPDATE chat_messages SET tenant_id = COALESCE(username, session_id, 'default') WHERE tenant_id IS NULL")
            
            # Set Not Null
            print("Setting chat_messages.tenant_id NOT NULL")
            op.alter_column('chat_messages', 'tenant_id', nullable=False)
            
            # Index
            op.create_index(op.f('ix_chat_messages_tenant_id'), 'chat_messages', ['tenant_id'], unique=False)


def downgrade() -> None:
    # Downgrade logic simplified for safety (drop columns)
    op.drop_index(op.f('ix_chat_messages_tenant_id'), table_name='chat_messages')
    op.drop_column('chat_messages', 'tenant_id')
    
    op.drop_index(op.f('ix_form_results_tenant_id'), table_name='form_results')
    op.drop_column('form_results', 'tenant_id')
    
    op.drop_index(op.f('ix_chat_transcripts_tenant_id'), table_name='chat_transcripts')
    op.drop_column('chat_transcripts', 'tenant_id')
