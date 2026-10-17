from sqlalchemy import Column, String, Numeric, Integer, ForeignKey, Text, Boolean, DateTime, CheckConstraint, JSON, Enum as SQLEnum
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
    __table_args__ = (
        CheckConstraint("pricing_source IS NULL OR pricing_source IN ('default','manual')", name='ck_labor_pricing_source'),
        CheckConstraint("execution_status IS NULL OR execution_status IN ('pending', 'completed')", name="ck_labor_execution_status"),
        CheckConstraint("execution_version >= 0", name="ck_labor_execution_version"),
    )
    # Null explicitly represents legacy scope; production creation enrolls new work.
    execution_status = Column(String(16), nullable=True)
    execution_version = Column(Integer, nullable=False, default=0, server_default="0")
    completed_at = Column(DateTime(timezone=True), nullable=True)
    completed_by_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    completed_by_name = Column(String(255), nullable=True)

    
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False, index=True)
    tenant = relationship("Tenant", backref="labor")
    
    repair_order_id = Column(UUID(as_uuid=True), ForeignKey("repair_orders.id"), nullable=False, index=True)
    repair_order = relationship("RepairOrder", back_populates="labor_items")
    
    pricing_snapshot = Column(JSON(none_as_null=True))
    pricing_source = Column(String(16))

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

