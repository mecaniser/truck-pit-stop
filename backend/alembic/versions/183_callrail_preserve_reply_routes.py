"""Keep historical inbound routes separate from the selected outbound sender."""
from alembic import op
import sqlalchemy as sa
revision = '183_callrail_reply_routes'
down_revision = '182_callrail_manual_inbox'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('callrail_conversations', sa.Column('selected_for_sending', sa.Boolean(), nullable=False, server_default=sa.true()))
    op.drop_constraint('callrail_conversations_thread_id_key', 'callrail_conversations', type_='unique')
    op.create_unique_constraint('uq_callrail_thread_binding', 'callrail_conversations', ['thread_id', 'binding_id'])
    op.create_index('uq_callrail_selected_thread', 'callrail_conversations', ['thread_id'], unique=True,
                    postgresql_where=sa.text('selected_for_sending AND deleted_at IS NULL'))


def downgrade():
    # Never delete preserved inbound routes to squeeze them into the old schema.
    connection = op.get_bind()
    if connection.scalar(sa.text('SELECT EXISTS (SELECT 1 FROM callrail_conversations GROUP BY thread_id HAVING count(*) > 1)')):
        raise RuntimeError('Cannot downgrade CallRail while multiple preserved reply routes exist; retain schema and disable bindings instead.')
    op.drop_index('uq_callrail_selected_thread', table_name='callrail_conversations')
    op.drop_constraint('uq_callrail_thread_binding', 'callrail_conversations', type_='unique')
    op.create_unique_constraint('callrail_conversations_thread_id_key', 'callrail_conversations', ['thread_id'])
    op.drop_column('callrail_conversations', 'selected_for_sending')
