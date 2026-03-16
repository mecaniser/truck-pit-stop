from sqlalchemy import Column, DateTime, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.db.base import BaseModel


class LaborOperationMemory(BaseModel):
    __tablename__ = "labor_operation_memory"
    __table_args__ = (
        UniqueConstraint("tenant_id", "vehicle_signature", "operation_key", name="uq_labor_operation_memory_key"),
    )

    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False, index=True)
    tenant = relationship("Tenant", backref="labor_operation_memory_entries")

    vehicle_signature = Column(String(255), nullable=False, index=True)
    operation_key = Column(String(255), nullable=False, index=True)
    operation_name = Column(String(255), nullable=False)
    operation_description = Column(Text, nullable=True)
    provider_operation_id = Column(String(120), nullable=True, index=True)
    source_provider = Column(String(50), nullable=False, default="internal_memory")
    normalized_hours = Column(Numeric(5, 2), nullable=False)
    usage_count = Column(Integer, nullable=False, default=1)
    last_used_at = Column(DateTime(timezone=True), nullable=False)
