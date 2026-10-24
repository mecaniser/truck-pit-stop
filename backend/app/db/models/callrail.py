"""Explicit manual-only provider bindings; never infer a shop from a phone match."""
from sqlalchemy import Column, String, ForeignKey, Boolean, Text, JSON, UniqueConstraint, Index, text, DateTime, Integer
from sqlalchemy.dialects.postgresql import UUID
from app.db.base import BaseModel


class CallRailNumberBinding(BaseModel):
    __tablename__ = 'callrail_number_bindings'
    __table_args__ = (UniqueConstraint('account_id', 'sender_phone'),)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey('tenants.id'), nullable=False, index=True)
    account_id = Column(String(64), nullable=False)
    company_id = Column(String(64), nullable=False)
    tracker_id = Column(String(64), nullable=False)
    sender_phone = Column(String(20), nullable=False)
    credential_ref = Column(String(128), nullable=False)
    signing_secret_ref = Column(String(128), nullable=False)
    enabled = Column(Boolean, nullable=False, default=False, server_default='false')
    accept_new_inquiries = Column(Boolean, nullable=False, default=False, server_default='false')


class CallRailConversation(BaseModel):
    __tablename__ = 'callrail_conversations'
    __table_args__ = (UniqueConstraint('thread_id', 'binding_id', name='uq_callrail_thread_binding'),
        UniqueConstraint('binding_id', 'customer_phone'),
        Index('uq_callrail_selected_thread', 'thread_id', unique=True,
              postgresql_where=text('selected_for_sending AND deleted_at IS NULL'),
              sqlite_where=text('selected_for_sending AND deleted_at IS NULL')))
    selected_for_sending = Column(Boolean, nullable=False, default=True, server_default='true')
    tenant_id = Column(UUID(as_uuid=True), ForeignKey('tenants.id'), nullable=False, index=True)
    thread_id = Column(UUID(as_uuid=True), ForeignKey('message_threads.id'), nullable=False)
    binding_id = Column(UUID(as_uuid=True), ForeignKey('callrail_number_bindings.id'), nullable=False)
    customer_id = Column(UUID(as_uuid=True), ForeignKey('customers.id'), nullable=True)
    customer_phone = Column(String(20), nullable=False)
    provider_conversation_id = Column(String(80))


class CallRailMessageAlias(BaseModel):
    __tablename__ = 'callrail_message_aliases'
    __table_args__ = (UniqueConstraint('account_id', 'alias'),)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey('tenants.id'), nullable=False)
    account_id = Column(String(64), nullable=False)
    alias = Column(String(100), nullable=False)
    message_id = Column(UUID(as_uuid=True), ForeignKey('sms_messages.id'), nullable=False)


class CallRailQuarantine(BaseModel):
    __tablename__ = 'callrail_quarantine'
    __table_args__ = (UniqueConstraint('binding_id', 'event_hash'),)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey('tenants.id'), nullable=False)
    binding_id = Column(UUID(as_uuid=True), ForeignKey('callrail_number_bindings.id'), nullable=False)
    event_hash = Column(String(64), nullable=False)
    reason = Column(String(64), nullable=False)
    payload = Column(JSON, nullable=False)
    resolution = Column(Text)


class CallRailMediaCache(BaseModel):
    """Encrypted validated identities or sanitized PNGs; never provider locators."""
    __tablename__ = 'callrail_media_cache'
    __table_args__ = (UniqueConstraint('tenant_id', 'message_id', 'slot', name='uq_cr_media_message_slot'),)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey('tenants.id'), nullable=False, index=True)
    message_id = Column(UUID(as_uuid=True), ForeignKey('sms_messages.id'), nullable=False)
    slot = Column(Integer, nullable=False)  # -1 manifest; 0..9 clean image
    fingerprint = Column(String(64), nullable=False)
    encrypted_payload = Column(Text, nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False, index=True)
