"""Review-only business registration and immutable tenant SMS connections."""
from sqlalchemy import Column, String, Text, Integer, Boolean, DateTime, ForeignKey, Index, CheckConstraint, JSON
from sqlalchemy.dialects.postgresql import UUID
from app.db.base import BaseModel


class MessagingBusiness(BaseModel):
    __tablename__ = 'messaging_businesses'
    tenant_id = Column(UUID(as_uuid=True), ForeignKey('tenants.id'), nullable=False, unique=True)
    legal_name = Column(String(255))
    trade_name = Column(String(255))
    website_url = Column(String(2048))
    support_email = Column(String(255))
    support_phone = Column(String(20))
    consent_source_url = Column(String(2048))
    privacy_url = Column(String(2048))
    terms_url = Column(String(2048))
    representative_name = Column(String(255))
    representative_email = Column(String(255))
    message_description = Column(Text)
    sample_messages = Column(JSON, nullable=False, default=list)
    version = Column(Integer, nullable=False, default=1)
    status = Column(String(24), nullable=False, default='draft')
    rejection_reason = Column(Text)
    updated_by_id = Column(UUID(as_uuid=True), ForeignKey('users.id'))
    __table_args__ = (CheckConstraint("status IN ('draft','ready_for_review','submitted','in_review','approved','rejected','suspended')"),)


class TenantSMSBinding(BaseModel):
    __tablename__ = 'tenant_sms_bindings'
    tenant_id = Column(UUID(as_uuid=True), ForeignKey('tenants.id'), nullable=False, index=True)
    business_id = Column(UUID(as_uuid=True), ForeignKey('messaging_businesses.id'), nullable=False)
    account_sid = Column(String(34), nullable=False)
    customer_profile_sid = Column(String(34), nullable=False)
    brand_sid = Column(String(34), nullable=False)
    campaign_sid = Column(String(34), nullable=False)
    messaging_service_sid = Column(String(34), nullable=False)
    sender_sid = Column(String(34), nullable=False)
    sender_phone = Column(String(20), nullable=False)
    credential_ref = Column(String(128), nullable=False)
    registration_status = Column(String(24), nullable=False)
    enabled = Column(Boolean, nullable=False, default=False)
    verified_at = Column(DateTime(timezone=True))
    revision = Column(Integer, nullable=False)
    retired_at = Column(DateTime(timezone=True))
    __table_args__ = (
        Index('uq_tenant_sms_current', 'tenant_id', unique=True, postgresql_where=retired_at.is_(None), sqlite_where=retired_at.is_(None)),
        Index('uq_tenant_sms_sender_current', 'sender_phone', unique=True, postgresql_where=retired_at.is_(None), sqlite_where=retired_at.is_(None)),
    )


class SMSConsentEvidence(BaseModel):
    __tablename__ = 'sms_consent_evidence'
    tenant_id = Column(UUID(as_uuid=True), ForeignKey('tenants.id'), nullable=False, index=True)
    recipient_kind = Column(String(24), nullable=False)
    recipient_id = Column(UUID(as_uuid=True), nullable=False)
    phone = Column(String(20), nullable=False)
    purpose = Column(String(40), nullable=False, default='service_notifications')
    status = Column(String(16), nullable=False)
    source = Column(String(80), nullable=False)
    disclosure_version = Column(String(80), nullable=False)
    collected_at = Column(DateTime(timezone=True), nullable=False)
    actor_id = Column(UUID(as_uuid=True), ForeignKey('users.id'), nullable=False)
    __table_args__ = (CheckConstraint("status IN ('granted','withdrawn')"), Index('ix_sms_consent_recipient', 'tenant_id','recipient_kind','recipient_id','phone','purpose'))


class SMSConfigurationAudit(BaseModel):
    __tablename__ = 'sms_configuration_audits'
    tenant_id = Column(UUID(as_uuid=True), ForeignKey('tenants.id'), nullable=False, index=True)
    actor_id = Column(UUID(as_uuid=True), ForeignKey('users.id'))
    action = Column(String(64), nullable=False)
    business_version = Column(Integer)
    binding_id = Column(UUID(as_uuid=True), ForeignKey('tenant_sms_bindings.id'))
