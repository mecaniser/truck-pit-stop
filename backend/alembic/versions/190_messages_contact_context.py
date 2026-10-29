"""Add Messages CRM context without changing transport or existing data."""
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as pg
from alembic import op
revision = '190_messages_contact_context'
down_revision = '189_trip_reviewed_binding'
branch_labels = None
depends_on = None


def upgrade():
    def base():
        return [sa.Column('id', pg.UUID(as_uuid=True), primary_key=True),
                sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
                sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
                sa.Column('deleted_at', sa.DateTime(timezone=True))]
    def fk(name, table):
        return sa.Column(name, pg.UUID(as_uuid=True), sa.ForeignKey(table + '.id'), nullable=False)
    op.create_table('conversation_contact_links', *base(), fk('tenant_id', 'tenants'), fk('thread_id', 'message_threads'), fk('customer_id', 'customers'), fk('contact_id', 'contacts'), fk('actor_id', 'users'), sa.Column('version', sa.Integer(), nullable=False), sa.UniqueConstraint('tenant_id', 'thread_id'))
    op.create_table('contact_repair_links', *base(), fk('tenant_id', 'tenants'), fk('contact_id', 'contacts'), fk('repair_order_id', 'repair_orders'), fk('actor_id', 'users'), sa.UniqueConstraint('tenant_id', 'contact_id', 'repair_order_id'))
    op.create_table('conversation_context_mutations', *base(), fk('tenant_id', 'tenants'), fk('actor_id', 'users'), fk('thread_id', 'message_threads'), sa.Column('idempotency_key', pg.UUID(as_uuid=True), nullable=False), sa.Column('operation', sa.String(200), nullable=False), sa.Column('payload_hash', sa.String(64), nullable=False), sa.Column('result', sa.JSON(), nullable=False), sa.Column('previous_target', sa.JSON()), sa.UniqueConstraint('tenant_id', 'actor_id', 'idempotency_key'))


def downgrade():
    for table in ('conversation_context_mutations', 'contact_repair_links', 'conversation_contact_links'):
        op.drop_table(table)
