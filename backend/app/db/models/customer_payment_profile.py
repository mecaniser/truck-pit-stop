"""Provider-bound vault identities; never raw card or single-use token storage."""
from sqlalchemy import Column, String, ForeignKey, UniqueConstraint, CheckConstraint, ForeignKeyConstraint, Index, text
from sqlalchemy.dialects.postgresql import UUID
from app.db.base import BaseModel


class CustomerPaymentProfile(BaseModel):
    __tablename__ = 'customer_payment_profiles'
    __table_args__ = (
        UniqueConstraint('tenant_id','customer_id','id',name='uq_customer_vault_tenant_identity'),
        ForeignKeyConstraint(['tenant_id','customer_id'], ['customers.tenant_id','customers.id'],name='fk_customer_vault_customer'),
        UniqueConstraint('tenant_id', 'customer_id', 'provider', 'provider_account_id', 'environment', name='uq_customer_vault_context'),
        UniqueConstraint('provider', 'provider_account_id', 'environment', 'provider_customer_id', name='uq_customer_vault_owner'),
        CheckConstraint("provider IN ('stripe_connect','quickbooks_payments')", name='ck_customer_vault_provider'),
        CheckConstraint("(provider = 'stripe_connect' AND environment IN ('test','live')) OR (provider = 'quickbooks_payments' AND environment IN ('sandbox','production'))", name='ck_customer_vault_provider_environment'),
        CheckConstraint("environment IN ('test','live','sandbox','production')", name='ck_customer_vault_environment'),
    )
    tenant_id = Column(UUID(as_uuid=True), ForeignKey('tenants.id'), nullable=False, index=True)
    customer_id = Column(UUID(as_uuid=True), ForeignKey('customers.id'), nullable=False, index=True)
    provider = Column(String(32), nullable=False)
    provider_account_id = Column(String(255), nullable=False)
    environment = Column(String(16), nullable=False)
    provider_customer_id = Column(String(255), nullable=True)
    default_method_id = Column(String(255), nullable=True)


class SavedCardOperation(BaseModel):
    __tablename__ = 'saved_card_operations'
    __table_args__ = (
        ForeignKeyConstraint(['tenant_id','customer_id','profile_id'], ['customer_payment_profiles.tenant_id','customer_payment_profiles.customer_id','customer_payment_profiles.id'], name='fk_saved_card_operation_owner'),
        UniqueConstraint('profile_id', 'idempotency_key', name='uq_saved_card_operation_key'),
        UniqueConstraint('profile_id', 'token_hash', name='uq_saved_card_operation_token'),
        CheckConstraint("state != 'confirmed' OR provider_card_id IS NOT NULL", name='ck_saved_card_operation_receipt'),
        Index('uq_saved_card_operation_open', 'profile_id', unique=True, postgresql_where=text("state IN ('pending','unconfirmed') AND deleted_at IS NULL"), sqlite_where=text("state IN ('pending','unconfirmed') AND deleted_at IS NULL")),
        CheckConstraint("state IN ('pending','identity_pending','unconfirmed','confirmed','failed')", name='ck_saved_card_operation_state'),
    )
    tenant_id = Column(UUID(as_uuid=True), ForeignKey('tenants.id'), nullable=False, index=True)
    customer_id = Column(UUID(as_uuid=True), ForeignKey('customers.id'), nullable=False, index=True)
    profile_id = Column(UUID(as_uuid=True), ForeignKey('customer_payment_profiles.id'), nullable=False, index=True)
    context_key = Column(String(64), nullable=False)
    idempotency_key = Column(String(64), nullable=False)
    token_hash = Column(String(64), nullable=False)
    state = Column(String(24), nullable=False, default='pending')
    provider_card_id = Column(String(255), nullable=True)
