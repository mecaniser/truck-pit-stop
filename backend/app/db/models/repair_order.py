from sqlalchemy import Column, String, Numeric, ForeignKey, Text, DateTime, Integer, Boolean, Enum as SQLEnum
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import UUID
import enum
from decimal import Decimal
from app.db.base import BaseModel


class RepairOrderStatus(str, enum.Enum):
    DRAFT = "draft"
    QUOTED = "quoted"
    DECLINED = "declined"           # Customer declined quote, needs revision
    APPROVED = "approved"
    ASSIGNED = "assigned"           # Mechanic assigned, awaiting acknowledgment
    ACKNOWLEDGED = "acknowledged"   # Mechanic confirmed assignment
    IN_PROGRESS = "in_progress"     # Work actively being done
    PENDING_REVIEW = "pending_review"  # Mechanic finished, manager needs to verify
    COMPLETED = "completed"         # Manager approved work
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
    po_number = Column(String(100), nullable=True)
    source = Column(String(50), nullable=True, index=True)  # e.g. easy_truck_shop_import
    mileage_in = Column(Integer, nullable=True)
    mileage_out = Column(Integer, nullable=True)
    
    assigned_mechanic_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    assigned_mechanic = relationship("User", foreign_keys=[assigned_mechanic_id])
    
    total_parts_cost = Column(Numeric(10, 2), default=Decimal("0.00"), nullable=False)
    total_labor_cost = Column(Numeric(10, 2), default=Decimal("0.00"), nullable=False)
    total_cost = Column(Numeric(10, 2), default=Decimal("0.00"), nullable=False)

    # Manager-applied dollar discounts (owner dashboard price builder).
    labor_discount_amount = Column(Numeric(10, 2), default=Decimal("0.00"), nullable=False)  # $ off labor
    order_discount_amount = Column(Numeric(10, 2), default=Decimal("0.00"), nullable=False)  # $ off total

    # Per-job time tracking
    work_started_at = Column(DateTime(timezone=True), nullable=True)
    work_completed_at = Column(DateTime(timezone=True), nullable=True)

    # Hold / pause sub-state (while status remains IN_PROGRESS)
    hold_reason = Column(String(100), nullable=True)
    held_at = Column(DateTime(timezone=True), nullable=True)

    # Time tracking: estimated vs actual
    estimated_labor_minutes = Column(Integer, nullable=True)
    actual_tracked_minutes = Column(Integer, nullable=True)
    total_hold_minutes = Column(Integer, nullable=True)

    # Status transition timestamps
    assigned_at = Column(DateTime(timezone=True), nullable=True)
    acknowledged_at = Column(DateTime(timezone=True), nullable=True)
    pricing_locked_at = Column(DateTime(timezone=True), nullable=True)
    pricing_lock_reason = Column(String(64), nullable=True)

    # Cancel / delete audit trail. deleted_at comes from BaseModel; deleting a
    # repair order is a soft delete (hidden, not destroyed) so it can be
    # restored and so there's always a record of who cancelled/deleted it.
    cancelled_at = Column(DateTime(timezone=True), nullable=True)
    cancelled_by_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    cancelled_by_user = relationship("User", foreign_keys=[cancelled_by_user_id])
    deleted_by_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    deleted_by_user = relationship("User", foreign_keys=[deleted_by_user_id])

    # Comeback / warranty tracking
    parent_repair_order_id = Column(UUID(as_uuid=True), ForeignKey("repair_orders.id"), nullable=True)
    is_warranty_repair = Column(Boolean, nullable=False, default=False)

    # Internal fleet repair: parts priced at cost, labor at the tenant internal rate,
    # no customer quote/invoice/payment. Set when the customer is the internal fleet.
    is_internal = Column(Boolean, nullable=False, default=False, index=True)

    # Preventive-maintenance service (internal fleet). Completing a PM advances the
    # vehicle's next_pm_miles. Drives the "PM" kind in the fleet service history.
    is_pm = Column(Boolean, nullable=False, default=False, index=True)

    # One-to-one relationships (Quote and Invoice reference RepairOrder, not vice versa)
    quote = relationship("Quote", back_populates="repair_order", uselist=False)
    invoice = relationship("Invoice", back_populates="repair_order", uselist=False)
    
    parent_repair_order = relationship("RepairOrder", remote_side="RepairOrder.id", foreign_keys=[parent_repair_order_id])

    parts_usage = relationship("PartsUsage", back_populates="repair_order", cascade="all, delete-orphan")
    labor_items = relationship("Labor", back_populates="repair_order", cascade="all, delete-orphan")
    recommended_services = relationship("RecommendedService", back_populates="repair_order",
                                        foreign_keys="RecommendedService.repair_order_id",
                                        cascade="all, delete-orphan")

