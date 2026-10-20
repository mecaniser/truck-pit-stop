"""Explicit, expiring reply-only approval. No provisioning or outbound routing."""
from sqlalchemy import Column, String, ForeignKey, DateTime, Boolean, CheckConstraint, Index, text
from sqlalchemy.dialects.postgresql import UUID
from app.db.base import BaseModel


class TwilioReplyRoute(BaseModel):
    __tablename__ = 'twilio_reply_routes'
    __table_args__ = (
        CheckConstraint('expires_at > approved_at', name='ck_twilio_reply_approval_window'),
        CheckConstraint("account_sid ~ '^AC[0-9a-fA-F]{32}$' AND to_number ~ '^\\+[1-9][0-9]{7,14}$' AND from_number ~ '^\\+[1-9][0-9]{7,14}$'", name='ck_twilio_reply_canonical').ddl_if(dialect='postgresql'),
        CheckConstraint("length(trim(approval_reference)) > 0", name='ck_twilio_reply_reference'),
        Index('ix_twilio_reply_receiver', 'to_number'),
        Index('uq_twilio_reply_active_pair', 'account_sid', 'to_number', 'from_number', unique=True,
              postgresql_where=text('enabled AND revoked_at IS NULL AND deleted_at IS NULL'),
              sqlite_where=text('enabled AND revoked_at IS NULL AND deleted_at IS NULL')),
    )
    account_sid = Column(String(34), nullable=False)
    to_number = Column(String(20), nullable=False)
    from_number = Column(String(20), nullable=False)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey('tenants.id', ondelete='RESTRICT'), nullable=False)
    customer_id = Column(UUID(as_uuid=True), ForeignKey('customers.id', ondelete='RESTRICT'), nullable=False)
    thread_id = Column(UUID(as_uuid=True), ForeignKey('message_threads.id', ondelete='RESTRICT'), nullable=False)
    approving_actor_id = Column(UUID(as_uuid=True), ForeignKey('users.id', ondelete='RESTRICT'), nullable=False)
    approval_reference = Column(String(128), nullable=False)
    approved_at = Column(DateTime(timezone=True), nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    enabled = Column(Boolean, nullable=False, default=False, server_default='false')
    revoked_at = Column(DateTime(timezone=True), nullable=True)
    revocation_reason = Column(String(255), nullable=True)
