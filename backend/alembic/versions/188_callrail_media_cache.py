"""Encrypted CallRail manifest and sanitized image reuse."""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = '188_callrail_media_cache'
down_revision = '187_labor_twilio_merge'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('callrail_media_cache',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('deleted_at', sa.DateTime(timezone=True)),
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('tenants.id'), nullable=False),
        sa.Column('message_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('sms_messages.id'), nullable=False),
        sa.Column('slot', sa.Integer(), nullable=False),
        sa.Column('fingerprint', sa.String(64), nullable=False),
        sa.Column('encrypted_payload', sa.Text(), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint('tenant_id', 'message_id', 'slot', name='uq_cr_media_message_slot'))
    for field in ('id', 'tenant_id', 'expires_at'):
        op.create_index('ix_callrail_media_cache_' + field, 'callrail_media_cache', [field])


def downgrade():
    op.drop_table('callrail_media_cache')
