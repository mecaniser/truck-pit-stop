"""Explicit manual-only provider bindings; never infer a shop from a phone match."""
from sqlalchemy import Column, String, ForeignKey, Boolean, Text, JSON, UniqueConstraint
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


class CallRailConversation(BaseModel):
    __tablename__ = 'callrail_conversations'
    __table_args__ = (UniqueConstraint('thread_id'), UniqueConstraint('binding_id', 'customer_phone'))
    tenant_id = Column(UUID(as_uuid=True), ForeignKey('tenants.id'), nullable=False, index=True)
    thread_id = Column(UUID(as_uuid=True), ForeignKey('message_threads.id'), nullable=False)
    binding_id = Column(UUID(as_uuid=True), ForeignKey('callrail_number_bindings.id'), nullable=False)
    customer_id = Column(UUID(as_uuid=True), ForeignKey('customers.id'), nullable=False)
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
