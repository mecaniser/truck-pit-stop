from sqlalchemy import Column, String, ForeignKey, Text, Enum as SQLEnum, Boolean, DateTime
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import UUID
import enum
from app.db.base import BaseModel


class NotificationType(str, enum.Enum):
    EMAIL = "email"
    SMS = "sms"


class NotificationStatus(str, enum.Enum):
    PENDING = "pending"
    SENT = "sent"
    FAILED = "failed"
    DELIVERED = "delivered"


class Notification(BaseModel):
    __tablename__ = "notifications"
    
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False, index=True)
    tenant = relationship("Tenant", backref="notifications")
    
    type = Column(SQLEnum(NotificationType), nullable=False, index=True)
    status = Column(SQLEnum(NotificationStatus), nullable=False, default=NotificationStatus.PENDING, index=True)
    
    recipient_email = Column(String(255), nullable=True, index=True)
    recipient_phone = Column(String(20), nullable=True, index=True)
    
    subject = Column(String(255), nullable=True)
    body = Column(Text, nullable=False)
    
    template_name = Column(String(100), nullable=True)
    external_id = Column(String(255), nullable=True)  # Twilio/Resend message ID
    
    error_message = Column(Text, nullable=True)
    sent_at = Column(DateTime(timezone=True), nullable=True)
    delivered_at = Column(DateTime(timezone=True), nullable=True)

