"""Additive shared inbox workflow and durable, never blindly retried send intents."""
from sqlalchemy import Column, String, ForeignKey, DateTime, Text, Integer, UniqueConstraint, CheckConstraint
from sqlalchemy.dialects.postgresql import UUID
from app.db.base import BaseModel


class ConversationWorkflow(BaseModel):
    __tablename__ = 'conversation_workflows'
    __table_args__ = (UniqueConstraint('tenant_id', 'thread_id'), CheckConstraint("status IN ('open','resolved')"))
    tenant_id = Column(UUID(as_uuid=True), ForeignKey('tenants.id'), nullable=False, index=True)
    thread_id = Column(UUID(as_uuid=True), ForeignKey('message_threads.id'), nullable=False, unique=True)
    status = Column(String(16), nullable=False, default='open', server_default='open')
    assignee_id = Column(UUID(as_uuid=True), ForeignKey('users.id'))
    version = Column(Integer, nullable=False, default=1, server_default='1')


class ConversationReadWatermark(BaseModel):
    __tablename__ = 'conversation_read_watermarks'
    __table_args__ = (UniqueConstraint('tenant_id', 'thread_id', 'user_id'),)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey('tenants.id'), nullable=False, index=True)
    thread_id = Column(UUID(as_uuid=True), ForeignKey('message_threads.id'), nullable=False)
    user_id = Column(UUID(as_uuid=True), ForeignKey('users.id'), nullable=False)
    through_created_at = Column(DateTime(timezone=True), nullable=False)
    through_message_id = Column(UUID(as_uuid=True), ForeignKey('sms_messages.id'), nullable=False)


class SMSSendOperation(BaseModel):
    __tablename__ = 'sms_send_operations'
    __table_args__ = (
        UniqueConstraint('tenant_id', 'idempotency_key'),
        CheckConstraint("state IN ('pending','dispatching','accepted','rejected','unknown')"),
        CheckConstraint('attempt_count BETWEEN 0 AND 1'),
    )
    provider = Column(String(16), nullable=True)
    provider_account_id = Column(String(64), nullable=True)
    provider_message_id = Column(String(80), nullable=True)
    provider_conversation_id = Column(String(80), nullable=True)
    callrail_binding_id = Column(UUID(as_uuid=True), ForeignKey('callrail_number_bindings.id'), nullable=True)
    binding_id = Column(UUID(as_uuid=True), ForeignKey('tenant_sms_bindings.id'), nullable=True)
    twilio_account_sid = Column(String(34), nullable=True)
    messaging_service_sid = Column(String(34), nullable=True)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey('tenants.id'), nullable=False, index=True)
    thread_id = Column(UUID(as_uuid=True), ForeignKey('message_threads.id'), nullable=False, index=True)
    message_id = Column(UUID(as_uuid=True), ForeignKey('sms_messages.id'), nullable=False, unique=True)
    actor_id = Column(UUID(as_uuid=True), ForeignKey('users.id'), nullable=False)
    idempotency_key = Column(String(128), nullable=False)
    payload_hash = Column(String(64), nullable=False)
    channel_account_id = Column(UUID(as_uuid=True), nullable=False)
    contact_identity_id = Column(UUID(as_uuid=True), nullable=False)
    from_number = Column(String(20), nullable=False)
    to_number = Column(String(20), nullable=False)
    body = Column(Text, nullable=False)
    state = Column(String(16), nullable=False, default='pending', index=True)
    attempt_count = Column(Integer, nullable=False, default=0)
    dispatch_started_at = Column(DateTime(timezone=True))
    reconciliation_state = Column(String(16), nullable=False, default='none')
    error_code = Column(String(64))
