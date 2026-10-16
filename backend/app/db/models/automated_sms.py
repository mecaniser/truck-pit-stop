"""Transactional automated SMS intents; a claimed intent is never retried."""
from sqlalchemy import Column, String, ForeignKey, DateTime, Text, Integer, UniqueConstraint, CheckConstraint
from sqlalchemy.dialects.postgresql import UUID
from app.db.base import BaseModel


class AutomatedSMSOperation(BaseModel):
    __tablename__ = 'automated_sms_operations'
    __table_args__ = (
        UniqueConstraint('tenant_id', 'event_key'),
        UniqueConstraint('notification_id'),
        UniqueConstraint('message_id'),
        CheckConstraint("state IN ('pending','dispatching','accepted','rejected','unknown')"),
        CheckConstraint("recipient_kind IN ('customer','user','tenant_contact')"),
        CheckConstraint('attempt_count BETWEEN 0 AND 1'),
    )
    tenant_id = Column(UUID(as_uuid=True), ForeignKey('tenants.id'), nullable=False, index=True)
    event_key = Column(String(64), nullable=False)
    domain_event_id = Column(String(512), nullable=False)
    template_name = Column(String(100), nullable=False)
    template_version = Column(String(32), nullable=False)
    recipient_kind = Column(String(20), nullable=False)
    recipient_id = Column(UUID(as_uuid=True), nullable=False)
    from_number = Column(String(20), nullable=False)
    to_number = Column(String(20), nullable=False)
    body = Column(Text, nullable=False)
    payload_hash = Column(String(64), nullable=False)
    notification_id = Column(UUID(as_uuid=True), ForeignKey('notifications.id'), nullable=False)
    message_id = Column(UUID(as_uuid=True), ForeignKey('sms_messages.id'))
    provider_message_sid = Column(String(64), unique=True)
    state = Column(String(16), nullable=False, default='pending', index=True)
    attempt_count = Column(Integer, nullable=False, default=0)
    dispatch_started_at = Column(DateTime(timezone=True))
    reconciliation_state = Column(String(16), nullable=False, default='none')
    error_code = Column(String(64))
    delivery_status = Column(String(16), nullable=False, default='pending')
