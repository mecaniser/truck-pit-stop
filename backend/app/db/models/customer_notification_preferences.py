from sqlalchemy import Boolean, Column, ForeignKey, ForeignKeyConstraint, Integer, UniqueConstraint, CheckConstraint
from sqlalchemy.dialects.postgresql import UUID
from app.db.base import BaseModel


class CustomerNotificationPreferences(BaseModel):
    __tablename__ = "customer_notification_preferences"
    __table_args__ = (
        UniqueConstraint("tenant_id", "customer_id", name="uq_customer_notification_preferences_scope"),
        ForeignKeyConstraint(["tenant_id", "customer_id"], ["customers.tenant_id", "customers.id"], ondelete="CASCADE"),
        CheckConstraint("revision >= 1", name="ck_customer_notification_preferences_revision"),
    )
    tenant_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    customer_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    revision = Column(Integer, nullable=False, default=1)
    invoice_email = Column(Boolean, nullable=False, default=True, server_default="true")
    invoice_sms = Column(Boolean, nullable=False, default=True, server_default="true")
    repair_email = Column(Boolean, nullable=False, default=True, server_default="true")
    repair_sms = Column(Boolean, nullable=False, default=True, server_default="true")
    updated_by_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
