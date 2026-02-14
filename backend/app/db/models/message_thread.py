from sqlalchemy import Column, String, ForeignKey, DateTime, Text, Integer, UniqueConstraint, Index
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import UUID

from app.db.base import BaseModel


class MessageThread(BaseModel):
    __tablename__ = "message_threads"
    __table_args__ = (
        UniqueConstraint("tenant_id", "customer_id", name="uq_message_threads_tenant_customer"),
        Index("ix_message_threads_tenant_last_message", "tenant_id", "last_message_at"),
    )

    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False, index=True)
    customer_id = Column(UUID(as_uuid=True), ForeignKey("customers.id"), nullable=False, index=True)
    customer_phone = Column(String(20), nullable=True)
    last_message_at = Column(DateTime(timezone=True), nullable=True, index=True)
    last_message_preview = Column(Text, nullable=True)
    unread_count_staff = Column(Integer, nullable=False, default=0)
    archived_at = Column(DateTime(timezone=True), nullable=True, index=True)
    archived_by_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True, index=True)

    tenant = relationship("Tenant", backref="message_threads")
    customer = relationship("Customer", backref="message_threads")
    messages = relationship("SMSMessage", back_populates="thread", cascade="all, delete-orphan")
    archived_by_user = relationship("User", foreign_keys=[archived_by_user_id])
