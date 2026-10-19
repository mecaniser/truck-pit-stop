"""Persist inbox workflow, per-user reads and duplicate-safe SMS operations."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '177_shared_inbox'
down_revision = '176_merge_contact_pricing'
branch_labels = None
depends_on = None


def base_columns():
    return [sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True), sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False), sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False), sa.Column('deleted_at', sa.DateTime(timezone=True))]


def ref(name, table, nullable=False):
    return sa.Column(name, postgresql.UUID(as_uuid=True), sa.ForeignKey(table + '.id'), nullable=nullable)


def upgrade():
    op.create_table('conversation_workflows', *base_columns(), ref('tenant_id', 'tenants'), ref('thread_id', 'message_threads'), ref('assignee_id', 'users', True), sa.Column('status', sa.String(16), nullable=False, server_default='open'), sa.Column('version', sa.Integer(), nullable=False, server_default='1'), sa.UniqueConstraint('tenant_id', 'thread_id'), sa.UniqueConstraint('thread_id'), sa.CheckConstraint("status IN ('open','resolved')"))
    op.create_table('conversation_read_watermarks', *base_columns(), ref('tenant_id', 'tenants'), ref('thread_id', 'message_threads'), ref('user_id', 'users'), ref('through_message_id', 'sms_messages'), sa.Column('through_created_at', sa.DateTime(timezone=True), nullable=False), sa.UniqueConstraint('tenant_id', 'thread_id', 'user_id'))
    op.create_table('sms_send_operations', *base_columns(), ref('tenant_id', 'tenants'), ref('thread_id', 'message_threads'), ref('message_id', 'sms_messages'), ref('actor_id', 'users'), sa.Column('idempotency_key', sa.String(128), nullable=False), sa.Column('payload_hash', sa.String(64), nullable=False), sa.Column('channel_account_id', postgresql.UUID(as_uuid=True), nullable=False), sa.Column('contact_identity_id', postgresql.UUID(as_uuid=True), nullable=False), sa.Column('from_number', sa.String(20), nullable=False), sa.Column('to_number', sa.String(20), nullable=False), sa.Column('body', sa.Text(), nullable=False), sa.Column('state', sa.String(16), nullable=False), sa.Column('attempt_count', sa.Integer(), nullable=False), sa.Column('dispatch_started_at', sa.DateTime(timezone=True)), sa.Column('reconciliation_state', sa.String(16), nullable=False), sa.Column('error_code', sa.String(64)), sa.UniqueConstraint('tenant_id', 'idempotency_key'), sa.UniqueConstraint('message_id'), sa.CheckConstraint("state IN ('pending','dispatching','accepted','rejected','unknown')"), sa.CheckConstraint('attempt_count BETWEEN 0 AND 1'))
    for table in ('conversation_workflows', 'conversation_read_watermarks', 'sms_send_operations'):
        for column in ('id', 'tenant_id'):
            op.create_index(f'ix_{table}_{column}', table, [column])
    op.create_index('ix_sms_send_operations_thread_id', 'sms_send_operations', ['thread_id'])
    op.create_index('ix_sms_send_operations_state', 'sms_send_operations', ['state'])


def downgrade():
    # Preserve externally dispatched intents: rollback disables sends, never replays them.
    if op.get_bind().execute(sa.text('SELECT EXISTS (SELECT 1 FROM sms_send_operations)')).scalar():
        raise RuntimeError('Preserve SMS send operations; disable dispatch instead of downgrading populated inbox tables')
    for table in ('sms_send_operations', 'conversation_read_watermarks', 'conversation_workflows'):
        op.drop_table(table)
