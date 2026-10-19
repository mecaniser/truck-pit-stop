"""Explicit manual CallRail provider bindings and replay-safe receipts.

Revision ID: 182_callrail_manual_inbox
Revises: 181_sms_maintenance_merge
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
revision = '182_callrail_manual_inbox'
down_revision = '181_sms_maintenance_merge'
branch_labels = None
depends_on = None


def base():
    return [sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column('deleted_at', sa.DateTime(timezone=True))]


def fk(name, target, nullable=False):
    return sa.Column(name, postgresql.UUID(as_uuid=True), sa.ForeignKey(target), nullable=nullable)


def upgrade():
    op.create_table('callrail_number_bindings', *base(), fk('tenant_id', 'tenants.id'),
        sa.Column('account_id', sa.String(64), nullable=False), sa.Column('company_id', sa.String(64), nullable=False),
        sa.Column('tracker_id', sa.String(64), nullable=False), sa.Column('sender_phone', sa.String(20), nullable=False),
        sa.Column('credential_ref', sa.String(128), nullable=False), sa.Column('signing_secret_ref', sa.String(128), nullable=False),
        sa.Column('enabled', sa.Boolean, nullable=False, server_default=sa.false()),
        sa.UniqueConstraint('account_id', 'sender_phone'))
    op.create_index('ix_callrail_number_bindings_tenant_id', 'callrail_number_bindings', ['tenant_id'])
    op.create_table('callrail_conversations', *base(), fk('tenant_id', 'tenants.id'), fk('thread_id', 'message_threads.id'),
        fk('binding_id', 'callrail_number_bindings.id'), fk('customer_id', 'customers.id'),
        sa.Column('customer_phone', sa.String(20), nullable=False), sa.Column('provider_conversation_id', sa.String(80)),
        sa.UniqueConstraint('thread_id'), sa.UniqueConstraint('binding_id', 'customer_phone'))
    op.create_index('ix_callrail_conversations_tenant_id', 'callrail_conversations', ['tenant_id'])
    for table in ('sms_messages', 'sms_send_operations'):
        for name, length in [('provider', 16), ('provider_account_id', 64), ('provider_message_id', 80), ('provider_conversation_id', 80)]:
            op.add_column(table, sa.Column(name, sa.String(length), nullable=True))
        op.add_column(table, sa.Column('callrail_binding_id', postgresql.UUID(as_uuid=True), nullable=True))
        op.create_foreign_key(f'fk_{table}_callrail_binding', table, 'callrail_number_bindings', ['callrail_binding_id'], ['id'])
    op.create_table('callrail_message_aliases', *base(), fk('tenant_id', 'tenants.id'),
        sa.Column('account_id', sa.String(64), nullable=False), sa.Column('alias', sa.String(100), nullable=False),
        fk('message_id', 'sms_messages.id'), sa.UniqueConstraint('account_id', 'alias'))
    op.create_table('callrail_quarantine', *base(), fk('tenant_id', 'tenants.id'), fk('binding_id', 'callrail_number_bindings.id'),
        sa.Column('event_hash', sa.String(64), nullable=False), sa.Column('reason', sa.String(64), nullable=False),
        sa.Column('payload', sa.JSON, nullable=False), sa.Column('resolution', sa.Text), sa.UniqueConstraint('binding_id', 'event_hash'))


def downgrade():
    op.drop_table('callrail_quarantine')
    op.drop_table('callrail_message_aliases')
    for table in ('sms_messages', 'sms_send_operations'):
        op.drop_constraint(f'fk_{table}_callrail_binding', table, type_='foreignkey')
        for name in ('callrail_binding_id', 'provider_conversation_id', 'provider_message_id', 'provider_account_id', 'provider'):
            op.drop_column(table, name)
    op.drop_table('callrail_conversations')
    op.drop_table('callrail_number_bindings')
