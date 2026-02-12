import enum

from sqlalchemy import Column, String, ForeignKey, DateTime, Text, Enum as SQLEnum, Index
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import UUID

from app.db.base import BaseModel


class SMSMessageDirection(str, enum.Enum):
    INBOUND = "inbound"
    OUTBOUND = "outbound"


class SMSMessageSource(str, enum.Enum):
    INBOUND = "inbound"
    MANUAL = "manual"
    AUTOMATED = "automated"


class SMSDeliveryStatus(str, enum.Enum):
    PENDING = "pending"
    QUEUED = "queued"
    SENT = "sent"
    DELIVERED = "delivered"
    UNDELIVERED = "undelivered"
    FAILED = "failed"


class SMSMessage(BaseModel):
    __tablename__ = "sms_messages"
    __table_args__ = (
        Index("ix_sms_messages_thread_created_at", "thread_id", "created_at"),
    )

    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False, index=True)
    thread_id = Column(UUID(as_uuid=True), ForeignKey("message_threads.id"), nullable=False, index=True)
    customer_id = Column(UUID(as_uuid=True), ForeignKey("customers.id"), nullable=False, index=True)
    created_by_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True, index=True)

    direction = Column(
        SQLEnum(
            SMSMessageDirection,
            name="sms_message_direction",
            values_callable=lambda e: [m.value for m in e],
        ),
        nullable=False,
        index=True,
    )
    source = Column(
        SQLEnum(
            SMSMessageSource,
            name="sms_message_source",
            values_callable=lambda e: [m.value for m in e],
        ),
        nullable=False,
        index=True,
    )
    body = Column(Text, nullable=False)
    from_number = Column(String(20), nullable=True)
    to_number = Column(String(20), nullable=True)
    twilio_message_sid = Column(String(64), nullable=True, unique=True, index=True)

    delivery_status = Column(
        SQLEnum(
            SMSDeliveryStatus,
            name="sms_delivery_status",
            values_callable=lambda e: [m.value for m in e],
        ),
        nullable=False,
        default=SMSDeliveryStatus.PENDING,
        index=True,
    )
    error_code = Column(String(32), nullable=True)
    error_message = Column(Text, nullable=True)
    sent_at = Column(DateTime(timezone=True), nullable=True)
    delivered_at = Column(DateTime(timezone=True), nullable=True)
    failed_at = Column(DateTime(timezone=True), nullable=True)

    tenant = relationship("Tenant", backref="sms_messages")
    thread = relationship("MessageThread", back_populates="messages")
    customer = relationship("Customer", backref="sms_messages")
    created_by_user = relationship("User", foreign_keys=[created_by_user_id])
