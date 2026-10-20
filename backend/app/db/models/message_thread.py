from sqlalchemy import Column, String, ForeignKey, DateTime, Text, Integer, UniqueConstraint, Index, Boolean, CheckConstraint, text
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import UUID

from app.db.base import BaseModel


class MessageThread(BaseModel):
    __tablename__ = "message_threads"
    __table_args__ = (
        UniqueConstraint("tenant_id", "customer_id", name="uq_message_threads_tenant_customer"),
        Index("ix_message_threads_tenant_last_message", "tenant_id", "last_message_at"),
        CheckConstraint("(thread_kind = 'customer' AND customer_id IS NOT NULL AND inquiry_binding_id IS NULL) OR (thread_kind = 'inquiry' AND customer_id IS NULL AND inquiry_binding_id IS NOT NULL AND customer_phone IS NOT NULL)", name='ck_thread_identity_kind'),
        Index('uq_callrail_inquiry_identity', 'tenant_id', 'inquiry_binding_id', 'customer_phone', unique=True,
              postgresql_where=text("thread_kind = 'inquiry' AND deleted_at IS NULL"), sqlite_where=text("thread_kind = 'inquiry' AND deleted_at IS NULL")),
    )

    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False, index=True)
    thread_kind = Column(String(16), nullable=False, default='customer', server_default='customer')
    inquiry_binding_id = Column(UUID(as_uuid=True), ForeignKey('callrail_number_bindings.id'), nullable=True)
    inquiry_opted_out = Column(Boolean, nullable=False, default=False, server_default='false')
    customer_id = Column(UUID(as_uuid=True), ForeignKey("customers.id"), nullable=True, index=True)
    customer_phone = Column(String(20), nullable=True)
    last_message_at = Column(DateTime(timezone=True), nullable=True, index=True)
    last_message_preview = Column(Text, nullable=True)
    unread_count_staff = Column(Integer, nullable=False, default=0)
    archived_at = Column(DateTime(timezone=True), nullable=True, index=True)
    archived_by_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True, index=True)

    tenant = relationship("Tenant", backref="message_threads")
    # No backref to Customer: nothing in the codebase uses `customer.message_threads`,
    # and having it caused SQLAlchemy's unit-of-work to null out this FK on unrelated
    # MessageThread rows during the customer-merge flow's `db.delete(loser)` flush
    # (see the customer merge endpoint) — a nullable=False column can't hold that.
    customer = relationship("Customer")
    messages = relationship("SMSMessage", back_populates="thread", cascade="all, delete-orphan")
    archived_by_user = relationship("User", foreign_keys=[archived_by_user_id])
