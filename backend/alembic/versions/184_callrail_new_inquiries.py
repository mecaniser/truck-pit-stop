"""Customer-free, explicitly typed CallRail inquiry threads."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
revision = '184_callrail_inquiries'
down_revision = '183_callrail_reply_routes'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('callrail_number_bindings', sa.Column('accept_new_inquiries', sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column('message_threads', sa.Column('thread_kind', sa.String(16), nullable=False, server_default='customer'))
    op.add_column('message_threads', sa.Column('inquiry_binding_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('callrail_number_bindings.id')))
    op.add_column('message_threads', sa.Column('inquiry_opted_out', sa.Boolean(), nullable=False, server_default=sa.false()))
    for table in ('message_threads', 'sms_messages', 'callrail_conversations'):
        op.alter_column(table, 'customer_id', existing_type=postgresql.UUID(as_uuid=True), nullable=True)
    op.create_check_constraint('ck_thread_identity_kind', 'message_threads', "(thread_kind = 'customer' AND customer_id IS NOT NULL AND inquiry_binding_id IS NULL) OR (thread_kind = 'inquiry' AND customer_id IS NULL AND inquiry_binding_id IS NOT NULL AND customer_phone IS NOT NULL)")
    op.create_check_constraint('ck_sms_customer_or_inquiry', 'sms_messages', "customer_id IS NOT NULL OR (provider IS NOT NULL AND provider = 'callrail' AND callrail_binding_id IS NOT NULL)")
    op.create_index('uq_callrail_inquiry_identity', 'message_threads', ['tenant_id', 'inquiry_binding_id', 'customer_phone'], unique=True,
        postgresql_where=sa.text("thread_kind = 'inquiry' AND deleted_at IS NULL"))


def downgrade():
    if op.get_bind().scalar(sa.text("SELECT EXISTS(SELECT 1 FROM message_threads WHERE thread_kind = 'inquiry')")):
        raise RuntimeError('Cannot downgrade while CallRail inquiries exist; disable new intake and retain history instead.')
    op.drop_index('uq_callrail_inquiry_identity', table_name='message_threads')
    op.drop_constraint('ck_sms_customer_or_inquiry', 'sms_messages', type_='check')
    op.drop_constraint('ck_thread_identity_kind', 'message_threads', type_='check')
    for table in ('callrail_conversations', 'sms_messages', 'message_threads'):
        op.alter_column(table, 'customer_id', existing_type=postgresql.UUID(as_uuid=True), nullable=False)
    for name in ('inquiry_opted_out', 'inquiry_binding_id', 'thread_kind'):
        op.drop_column('message_threads', name)
    op.drop_column('callrail_number_bindings', 'accept_new_inquiries')
