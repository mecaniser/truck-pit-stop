"""Provider/account/environment bound customer card vaults and save receipts."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
revision = '201_customer_payment_profiles'
down_revision = '200'
branch_labels = None
depends_on = None


def base_columns():
    return [sa.Column('id',postgresql.UUID(as_uuid=True),primary_key=True),
        sa.Column('created_at',sa.DateTime(timezone=True),nullable=False,server_default=sa.func.now()),
        sa.Column('updated_at',sa.DateTime(timezone=True),nullable=False,server_default=sa.func.now()),
        sa.Column('deleted_at',sa.DateTime(timezone=True),nullable=True)]


def upgrade():
    op.create_table('customer_payment_profiles',*base_columns(),
        sa.Column('tenant_id',postgresql.UUID(as_uuid=True),sa.ForeignKey('tenants.id'),nullable=False),
        sa.Column('customer_id',postgresql.UUID(as_uuid=True),sa.ForeignKey('customers.id'),nullable=False),
        sa.Column('provider',sa.String(32),nullable=False),sa.Column('provider_account_id',sa.String(255),nullable=False),
        sa.Column('environment',sa.String(16),nullable=False),sa.Column('provider_customer_id',sa.String(255)),sa.Column('default_method_id',sa.String(255)),
        sa.UniqueConstraint('tenant_id','customer_id','id',name='uq_customer_vault_tenant_identity'),
        sa.ForeignKeyConstraint(['tenant_id','customer_id'],['customers.tenant_id','customers.id'],name='fk_customer_vault_customer'),
        sa.UniqueConstraint('tenant_id','customer_id','provider','provider_account_id','environment',name='uq_customer_vault_context'),
        sa.UniqueConstraint('provider','provider_account_id','environment','provider_customer_id',name='uq_customer_vault_owner'),
        sa.CheckConstraint("provider IN ('stripe_connect','quickbooks_payments')",name='ck_customer_vault_provider'),
        sa.CheckConstraint("(provider = 'stripe_connect' AND environment IN ('test','live')) OR (provider = 'quickbooks_payments' AND environment IN ('sandbox','production'))",name='ck_customer_vault_provider_environment'),
        sa.CheckConstraint("environment IN ('test','live','sandbox','production')",name='ck_customer_vault_environment'))
    op.create_table('saved_card_operations',*base_columns(),
        sa.Column('tenant_id',postgresql.UUID(as_uuid=True),sa.ForeignKey('tenants.id'),nullable=False),
        sa.Column('customer_id',postgresql.UUID(as_uuid=True),sa.ForeignKey('customers.id'),nullable=False),
        sa.Column('profile_id',postgresql.UUID(as_uuid=True),sa.ForeignKey('customer_payment_profiles.id'),nullable=False),
        sa.Column('context_key',sa.String(64),nullable=False),sa.Column('idempotency_key',sa.String(64),nullable=False),
        sa.Column('token_hash',sa.String(64),nullable=False),sa.Column('state',sa.String(24),nullable=False),sa.Column('provider_card_id',sa.String(255)),
        sa.ForeignKeyConstraint(['tenant_id','customer_id','profile_id'],['customer_payment_profiles.tenant_id','customer_payment_profiles.customer_id','customer_payment_profiles.id'],name='fk_saved_card_operation_owner'),
        sa.UniqueConstraint('profile_id','idempotency_key',name='uq_saved_card_operation_key'),
        sa.UniqueConstraint('profile_id','token_hash',name='uq_saved_card_operation_token'),
        sa.CheckConstraint("state != 'confirmed' OR provider_card_id IS NOT NULL",name='ck_saved_card_operation_receipt'),
        sa.CheckConstraint("state IN ('pending','identity_pending','unconfirmed','confirmed','failed')",name='ck_saved_card_operation_state'))
    op.create_index('uq_saved_card_operation_open','saved_card_operations',['profile_id'],unique=True,postgresql_where=sa.text("state IN ('pending','unconfirmed') AND deleted_at IS NULL"))
    for table, columns in [('customer_payment_profiles',['id','tenant_id','customer_id']),('saved_card_operations',['id','tenant_id','customer_id','profile_id'])]:
        for column in columns:
            op.create_index(f'ix_{table}_{column}',table,[column])


def downgrade():
    op.drop_table('saved_card_operations')
    op.drop_table('customer_payment_profiles')
