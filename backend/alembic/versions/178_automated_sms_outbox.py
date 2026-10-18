"""Durable automated SMS outbox. No historic sends are enqueued."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '178_automated_sms_outbox'
down_revision = '177_shared_inbox'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'automated_sms_operations',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('deleted_at', sa.DateTime(timezone=True)),
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('tenants.id'), nullable=False),
        sa.Column('event_key', sa.String(64), nullable=False),
        sa.Column('domain_event_id', sa.String(512), nullable=False),
        sa.Column('template_name', sa.String(100), nullable=False),
        sa.Column('template_version', sa.String(32), nullable=False),
        sa.Column('recipient_kind', sa.String(20), nullable=False),
        sa.Column('recipient_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('from_number', sa.String(20), nullable=False),
        sa.Column('to_number', sa.String(20), nullable=False),
        sa.Column('body', sa.Text(), nullable=False),
        sa.Column('payload_hash', sa.String(64), nullable=False),
        sa.Column('notification_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('notifications.id'), nullable=False),
        sa.Column('message_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('sms_messages.id')),
        sa.Column('provider_message_sid', sa.String(64)),
        sa.Column('state', sa.String(16), nullable=False),
        sa.Column('attempt_count', sa.Integer(), nullable=False),
        sa.Column('dispatch_started_at', sa.DateTime(timezone=True)),
        sa.Column('reconciliation_state', sa.String(16), nullable=False),
        sa.Column('error_code', sa.String(64)),
        sa.Column('delivery_status', sa.String(16), nullable=False),
        sa.UniqueConstraint('tenant_id', 'event_key'), sa.UniqueConstraint('notification_id'),
        sa.UniqueConstraint('message_id'), sa.UniqueConstraint('provider_message_sid'),
        sa.CheckConstraint("state IN ('pending','dispatching','accepted','rejected','unknown')"),
        sa.CheckConstraint("recipient_kind IN ('customer','user','tenant_contact')"),
        sa.CheckConstraint('attempt_count BETWEEN 0 AND 1'),
    )
    for column in ('id', 'tenant_id', 'state'):
        op.create_index(f'ix_automated_sms_operations_{column}', 'automated_sms_operations', [column])


def downgrade():
    if op.get_bind().execute(sa.text('SELECT EXISTS (SELECT 1 FROM automated_sms_operations)')).scalar():
        raise RuntimeError('Preserve automated SMS intents; disable recovery instead of deleting populated outbox')
    op.drop_table('automated_sms_operations')
