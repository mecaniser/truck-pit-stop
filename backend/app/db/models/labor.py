from sqlalchemy import Column, String, Numeric, Integer, ForeignKey, Text, Boolean, Enum as SQLEnum
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import UUID
from decimal import Decimal
import enum
from app.db.base import BaseModel


class LaborLineType(str, enum.Enum):
    FLAT_SERVICE = "flat_service"
    REPAIR_OPERATION = "repair_operation"
    MANUAL = "manual"
    SUBLET = "sublet"


class Labor(BaseModel):
    __tablename__ = "labor"
    
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False, index=True)
    tenant = relationship("Tenant", backref="labor")
    
    repair_order_id = Column(UUID(as_uuid=True), ForeignKey("repair_orders.id"), nullable=False, index=True)
    repair_order = relationship("RepairOrder", back_populates="labor_items")
    
    service_code = Column(String(50), nullable=True)
    description = Column(Text, nullable=False)
    hours = Column(Numeric(5, 2), nullable=False)
    hourly_rate = Column(Numeric(10, 2), nullable=False)
    total_cost = Column(Numeric(10, 2), nullable=False)
    line_type = Column(
        SQLEnum(LaborLineType, values_callable=lambda e: [m.value for m in e]),
        nullable=False,
        default=LaborLineType.MANUAL,
        index=True,
    )
    provider = Column(String(50), nullable=True)
    provider_operation_id = Column(String(120), nullable=True)
    auto_recalc_enabled = Column(Boolean, nullable=False, default=True)
    source_service_id = Column(UUID(as_uuid=True), ForeignKey("services.id"), nullable=True, index=True)

    vendor_name = Column(String(255), nullable=True)
    vendor_cost = Column(Numeric(10, 2), nullable=True)

    mechanic_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    mechanic = relationship("User", foreign_keys=[mechanic_id])
    source_service = relationship("Service", foreign_keys=[source_service_id])

