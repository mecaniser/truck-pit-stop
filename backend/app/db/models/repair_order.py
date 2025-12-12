from sqlalchemy import Column, String, Numeric, ForeignKey, Text, Enum as SQLEnum
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import UUID
import enum
from decimal import Decimal
from app.db.base import BaseModel


class RepairOrderStatus(str, enum.Enum):
    DRAFT = "draft"
    QUOTED = "quoted"
    APPROVED = "approved"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    INVOICED = "invoiced"
    PAID = "paid"
    CANCELLED = "cancelled"


class RepairOrder(BaseModel):
    __tablename__ = "repair_orders"
    
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False, index=True)
    tenant = relationship("Tenant", backref="repair_orders")
    
    customer_id = Column(UUID(as_uuid=True), ForeignKey("customers.id"), nullable=False, index=True)
    customer = relationship("Customer", back_populates="repair_orders")
    
    vehicle_id = Column(UUID(as_uuid=True), ForeignKey("vehicles.id"), nullable=False, index=True)
    vehicle = relationship("Vehicle", back_populates="repair_orders")
    
    order_number = Column(String(50), unique=True, nullable=False, index=True)
    status = Column(
        SQLEnum(RepairOrderStatus, values_callable=lambda e: [m.value for m in e]),
        nullable=False,
        default=RepairOrderStatus.DRAFT,
        index=True
    )
    
    description = Column(Text, nullable=True)
    customer_notes = Column(Text, nullable=True)
    internal_notes = Column(Text, nullable=True)
    
    assigned_mechanic_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    assigned_mechanic = relationship("User", foreign_keys=[assigned_mechanic_id])
    
    total_parts_cost = Column(Numeric(10, 2), default=Decimal("0.00"), nullable=False)
    total_labor_cost = Column(Numeric(10, 2), default=Decimal("0.00"), nullable=False)
    total_cost = Column(Numeric(10, 2), default=Decimal("0.00"), nullable=False)
    
    # One-to-one relationships (Quote and Invoice reference RepairOrder, not vice versa)
    quote = relationship("Quote", back_populates="repair_order", uselist=False)
    invoice = relationship("Invoice", back_populates="repair_order", uselist=False)
    
    parts_usage = relationship("PartsUsage", back_populates="repair_order", cascade="all, delete-orphan")
    labor_items = relationship("Labor", back_populates="repair_order", cascade="all, delete-orphan")


