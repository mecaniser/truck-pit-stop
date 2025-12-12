from sqlalchemy import Column, String, DateTime, ForeignKey, Numeric, Text, Enum as SQLEnum
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import UUID
import enum
from decimal import Decimal
from app.db.base import BaseModel


class InvoiceStatus(str, enum.Enum):
    DRAFT = "draft"
    SENT = "sent"
    PAID = "paid"
    OVERDUE = "overdue"
    CANCELLED = "cancelled"


class Invoice(BaseModel):
    __tablename__ = "invoices"
    
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False, index=True)
    tenant = relationship("Tenant", backref="invoices")
    
    repair_order_id = Column(UUID(as_uuid=True), ForeignKey("repair_orders.id"), nullable=False, unique=True)
    repair_order = relationship("RepairOrder", back_populates="invoice")
    
    invoice_number = Column(String(50), unique=True, nullable=False, index=True)
    status = Column(
        SQLEnum(InvoiceStatus, values_callable=lambda e: [m.value for m in e]),
        nullable=False,
        default=InvoiceStatus.DRAFT,
        index=True
    )
    
    subtotal = Column(Numeric(10, 2), nullable=False)
    tax_amount = Column(Numeric(10, 2), default=Decimal("0.00"), nullable=False)
    discount_amount = Column(Numeric(10, 2), default=Decimal("0.00"), nullable=False)
    total_amount = Column(Numeric(10, 2), nullable=False)
    
    due_date = Column(DateTime(timezone=True), nullable=True)
    paid_at = Column(DateTime(timezone=True), nullable=True)
    notes = Column(Text, nullable=True)
    
    payments = relationship("Payment", back_populates="invoice", cascade="all, delete-orphan")


