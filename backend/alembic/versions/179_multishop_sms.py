"""Multi-shop SMS drafts, immutable bindings and explicit consent. No backfill."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision='179_multishop_sms'
down_revision='178_automated_sms_outbox'
branch_labels=None
depends_on=None


def base():
    return [sa.Column('id',postgresql.UUID(as_uuid=True),primary_key=True),sa.Column('created_at',sa.DateTime(timezone=True),server_default=sa.func.now(),nullable=False),sa.Column('updated_at',sa.DateTime(timezone=True),server_default=sa.func.now(),nullable=False),sa.Column('deleted_at',sa.DateTime(timezone=True))]


def fk(name,table,nullable=True):
    return sa.Column(name,postgresql.UUID(as_uuid=True),sa.ForeignKey(f'{table}.id'),nullable=nullable)


def upgrade():
    op.create_table('messaging_businesses',*base(),fk('tenant_id','tenants',False),*[sa.Column(n,sa.String(255)) for n in ('legal_name','trade_name','support_email','representative_name','representative_email')],*[sa.Column(n,sa.String(2048)) for n in ('website_url','consent_source_url','privacy_url','terms_url')],sa.Column('support_phone',sa.String(20)),sa.Column('message_description',sa.Text()),sa.Column('sample_messages',sa.JSON(),nullable=False),sa.Column('version',sa.Integer(),nullable=False),sa.Column('status',sa.String(24),nullable=False),sa.Column('rejection_reason',sa.Text()),fk('updated_by_id','users'),sa.UniqueConstraint('tenant_id'),sa.CheckConstraint("status IN ('draft','ready_for_review','submitted','in_review','approved','rejected','suspended')"))
    op.create_table('tenant_sms_bindings',*base(),fk('tenant_id','tenants',False),fk('business_id','messaging_businesses',False),*[sa.Column(n,sa.String(34),nullable=False) for n in ('account_sid','customer_profile_sid','brand_sid','campaign_sid','messaging_service_sid','sender_sid')],sa.Column('sender_phone',sa.String(20),nullable=False),sa.Column('credential_ref',sa.String(128),nullable=False),sa.Column('registration_status',sa.String(24),nullable=False),sa.Column('enabled',sa.Boolean(),nullable=False),sa.Column('verified_at',sa.DateTime(timezone=True)),sa.Column('revision',sa.Integer(),nullable=False),sa.Column('retired_at',sa.DateTime(timezone=True)))
    op.create_index('ix_tenant_sms_bindings_tenant_id','tenant_sms_bindings',['tenant_id'])
    op.create_index('uq_tenant_sms_current','tenant_sms_bindings',['tenant_id'],unique=True,postgresql_where=sa.text('retired_at IS NULL'))
    op.create_index('uq_tenant_sms_sender_current','tenant_sms_bindings',['sender_phone'],unique=True,postgresql_where=sa.text('retired_at IS NULL'))
    op.create_table('sms_consent_evidence',*base(),fk('tenant_id','tenants',False),sa.Column('recipient_kind',sa.String(24),nullable=False),sa.Column('recipient_id',postgresql.UUID(as_uuid=True),nullable=False),sa.Column('phone',sa.String(20),nullable=False),sa.Column('purpose',sa.String(40),nullable=False),sa.Column('status',sa.String(16),nullable=False),sa.Column('source',sa.String(80),nullable=False),sa.Column('disclosure_version',sa.String(80),nullable=False),sa.Column('collected_at',sa.DateTime(timezone=True),nullable=False),fk('actor_id','users',False),sa.CheckConstraint("status IN ('granted','withdrawn')"))
    op.create_index('ix_sms_consent_evidence_tenant_id','sms_consent_evidence',['tenant_id'])
    op.create_index('ix_sms_consent_recipient','sms_consent_evidence',['tenant_id','recipient_kind','recipient_id','phone','purpose'])
    op.create_table('sms_configuration_audits',*base(),fk('tenant_id','tenants',False),fk('actor_id','users'),sa.Column('action',sa.String(64),nullable=False),sa.Column('business_version',sa.Integer()),fk('binding_id','tenant_sms_bindings'))
    op.create_index('ix_sms_configuration_audits_tenant_id','sms_configuration_audits',['tenant_id'])
    for table in ('sms_send_operations','automated_sms_operations','sms_messages'):
        op.add_column(table,sa.Column('binding_id',postgresql.UUID(as_uuid=True),nullable=True))
        op.create_foreign_key(f'fk_{table}_sms_binding',table,'tenant_sms_bindings',['binding_id'],['id'])
        op.add_column(table,sa.Column('twilio_account_sid',sa.String(34),nullable=True))
        op.add_column(table,sa.Column('messaging_service_sid',sa.String(34),nullable=True))

    op.drop_constraint('automated_sms_operations_provider_message_sid_key','automated_sms_operations',type_='unique')
    op.create_unique_constraint('uq_automated_sms_account_sid','automated_sms_operations',['twilio_account_sid','provider_message_sid'])
    op.create_index('uq_automated_sms_legacy_sid','automated_sms_operations',['provider_message_sid'],unique=True,postgresql_where=sa.text('twilio_account_sid IS NULL'))
    # Original schema used a unique index for this indexed column.
    op.drop_index('ix_sms_messages_twilio_message_sid',table_name='sms_messages')
    op.create_index('ix_sms_messages_twilio_message_sid','sms_messages',['twilio_message_sid'])
    op.create_unique_constraint('uq_sms_messages_account_sid','sms_messages',['twilio_account_sid','twilio_message_sid'])
    op.create_index('uq_sms_messages_legacy_sid','sms_messages',['twilio_message_sid'],unique=True,postgresql_where=sa.text('twilio_account_sid IS NULL'))


def downgrade():
    if op.get_bind().execute(sa.text('SELECT EXISTS (SELECT 1 FROM tenant_sms_bindings UNION ALL SELECT 1 FROM sms_consent_evidence UNION ALL SELECT 1 FROM messaging_businesses)')).scalar():
        raise RuntimeError('Preserve SMS registration and consent evidence; disable routing instead')
    op.drop_index('uq_automated_sms_legacy_sid',table_name='automated_sms_operations')
    op.drop_constraint('uq_automated_sms_account_sid','automated_sms_operations',type_='unique')
    op.create_unique_constraint('automated_sms_operations_provider_message_sid_key','automated_sms_operations',['provider_message_sid'])
    op.drop_index('uq_sms_messages_legacy_sid',table_name='sms_messages')
    op.drop_constraint('uq_sms_messages_account_sid','sms_messages',type_='unique')
    op.drop_index('ix_sms_messages_twilio_message_sid',table_name='sms_messages')
    op.create_index('ix_sms_messages_twilio_message_sid','sms_messages',['twilio_message_sid'],unique=True)
    for table in ('sms_send_operations','automated_sms_operations','sms_messages'):
        op.drop_constraint(f'fk_{table}_sms_binding',table,type_='foreignkey')
        for column in ('binding_id','twilio_account_sid','messaging_service_sid'):
            op.drop_column(table,column)
    for table in ('sms_configuration_audits','sms_consent_evidence','tenant_sms_bindings','messaging_businesses'):
        op.drop_table(table)
