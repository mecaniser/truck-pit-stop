from sqlalchemy import Column, String, Numeric, ForeignKey, Text, Boolean, Enum as SQLEnum
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import UUID
import enum
from app.db.base import BaseModel


class RecommendedServicePriority(str, enum.Enum):
    URGENT = "urgent"
    SOON = "soon"
    MONITOR = "monitor"


class RecommendedService(BaseModel):
    __tablename__ = "recommended_services"

    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False, index=True)
    repair_order_id = Column(UUID(as_uuid=True), ForeignKey("repair_orders.id"), nullable=False, index=True)
    repair_order = relationship("RepairOrder", back_populates="recommended_services",
                                foreign_keys=[repair_order_id])

    description = Column(Text, nullable=False)
    estimated_cost = Column(Numeric(10, 2), nullable=True)
    priority = Column(
        SQLEnum(RecommendedServicePriority, values_callable=lambda e: [m.value for m in e]),
        nullable=False,
        default=RecommendedServicePriority.SOON,
    )
    notes = Column(Text, nullable=True)
    is_resolved = Column(Boolean, nullable=False, default=False)
    resolved_by_repair_order_id = Column(UUID(as_uuid=True), ForeignKey("repair_orders.id"), nullable=True)
