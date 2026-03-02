from sqlalchemy import Column, String, Numeric, ForeignKey, Text, DateTime, UniqueConstraint
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import UUID
from app.db.base import BaseModel


class MotorOperationCache(BaseModel):
    __tablename__ = "motor_operation_cache"
    __table_args__ = (
        UniqueConstraint("tenant_id", "vehicle_fingerprint", "operation_key", name="uq_motor_cache_key"),
    )

    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False, index=True)
    tenant = relationship("Tenant", backref="motor_operation_cache_entries")

    vehicle_fingerprint = Column(String(255), nullable=False, index=True)
    operation_key = Column(String(255), nullable=False, index=True)
    normalized_hours = Column(Numeric(5, 2), nullable=False)
    payload_json = Column(Text, nullable=False)
    last_synced_at = Column(DateTime(timezone=True), nullable=False)
