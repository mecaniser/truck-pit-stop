"""Explicit owner-only reply approvals; empty and disabled by default."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
revision = '186_twilio_reply_routes'
down_revision = '185_callrail_inquiry_main_merge'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('twilio_reply_routes',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('deleted_at', sa.DateTime(timezone=True)),
        sa.Column('account_sid', sa.String(34), nullable=False),
        sa.Column('to_number', sa.String(20), nullable=False),
        sa.Column('from_number', sa.String(20), nullable=False),
        *[sa.Column(name, postgresql.UUID(as_uuid=True), sa.ForeignKey(target, ondelete='RESTRICT'), nullable=False)
          for name, target in [('tenant_id','tenants.id'), ('customer_id','customers.id'), ('thread_id','message_threads.id'), ('approving_actor_id','users.id')]],
        sa.Column('approval_reference', sa.String(128), nullable=False),
        sa.Column('approved_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('enabled', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('revoked_at', sa.DateTime(timezone=True)),
        sa.Column('revocation_reason', sa.String(255)),
        sa.CheckConstraint('expires_at > approved_at', name='ck_twilio_reply_approval_window'),
        sa.CheckConstraint("account_sid ~ '^AC[0-9a-fA-F]{32}$' AND to_number ~ '^\\+[1-9][0-9]{7,14}$' AND from_number ~ '^\\+[1-9][0-9]{7,14}$'", name='ck_twilio_reply_canonical'),
        sa.CheckConstraint("length(trim(approval_reference)) > 0", name='ck_twilio_reply_reference'))
    op.create_index('ix_twilio_reply_receiver','twilio_reply_routes',['to_number'])
    op.create_index('uq_twilio_reply_active_pair','twilio_reply_routes',['account_sid','to_number','from_number'], unique=True,
                    postgresql_where=sa.text('enabled AND revoked_at IS NULL AND deleted_at IS NULL'))
    op.add_column('sms_messages', sa.Column('twilio_reply_route_id', postgresql.UUID(as_uuid=True)))
    op.create_foreign_key('fk_sms_twilio_reply_route','sms_messages','twilio_reply_routes',['twilio_reply_route_id'],['id'], ondelete='RESTRICT')
    # Approval identity is write-once. Historical receiver reservations cannot be erased.
    op.execute("""CREATE FUNCTION guard_twilio_reply_route() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN
      IF TG_OP = 'DELETE' THEN RAISE EXCEPTION 'Reply route history cannot be deleted'; END IF;
      IF ROW(NEW.account_sid,NEW.to_number,NEW.from_number,NEW.tenant_id,NEW.customer_id,NEW.thread_id,
             NEW.approving_actor_id,NEW.approval_reference,NEW.approved_at,NEW.expires_at)
         IS DISTINCT FROM ROW(OLD.account_sid,OLD.to_number,OLD.from_number,OLD.tenant_id,OLD.customer_id,OLD.thread_id,
             OLD.approving_actor_id,OLD.approval_reference,OLD.approved_at,OLD.expires_at)
      THEN RAISE EXCEPTION 'Reply route approval is immutable'; END IF;
      RETURN NEW;
    END $$""")
    op.execute('CREATE TRIGGER twilio_reply_route_identity BEFORE UPDATE OR DELETE ON twilio_reply_routes FOR EACH ROW EXECUTE FUNCTION guard_twilio_reply_route()')


def downgrade():
    if op.get_bind().execute(sa.text('SELECT EXISTS(SELECT 1 FROM twilio_reply_routes)')).scalar():
        raise RuntimeError('Refusing to erase reply route history')
    op.drop_constraint('fk_sms_twilio_reply_route','sms_messages',type_='foreignkey')
    op.drop_column('sms_messages','twilio_reply_route_id')
    op.drop_table('twilio_reply_routes')
    op.execute('DROP FUNCTION guard_twilio_reply_route()')
