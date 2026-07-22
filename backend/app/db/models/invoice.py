from sqlalchemy import Column, String, DateTime, ForeignKey, Numeric, Text, Enum as SQLEnum, Integer, Boolean, Index, text
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import UUID, JSONB
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
    __table_args__ = (
        Index(
            "ux_invoices_active_repair_order_id",
            "repair_order_id",
            unique=True,
            postgresql_where=text("status <> 'cancelled'"),
            sqlite_where=text("status <> 'cancelled'"),
        ),
    )
    
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False, index=True)
    tenant = relationship("Tenant", backref="invoices")
    
    repair_order_id = Column(UUID(as_uuid=True), ForeignKey("repair_orders.id"), nullable=False, index=True)
    repair_order = relationship("RepairOrder", back_populates="invoices")
    
    invoice_number = Column(String(50), unique=True, nullable=False, index=True)
    # Internal fleet invoice: a cost record for the garage's own work orders —
    # no customer billing, tax, or markup.
    is_internal = Column(Boolean, default=False, nullable=False, index=True)
    # Immutable recipient snapshot for billable fleet work orders. Normal
    # customer invoices keep these null and use their linked customer record.
    recipient_name = Column(String(160), nullable=True)
    recipient_email = Column(String(255), nullable=True)
    recipient_phone = Column(String(20), nullable=True)
    status = Column(
        SQLEnum(InvoiceStatus, values_callable=lambda e: [m.value for m in e]),
        nullable=False,
        default=InvoiceStatus.DRAFT,
        index=True
    )
    
    subtotal = Column(Numeric(10, 2), nullable=False)
    shop_supplies_amount = Column(Numeric(10, 2), default=Decimal("0.00"), nullable=False)
    service_fee_amount = Column(Numeric(10, 2), default=Decimal("0.00"), nullable=False)
    tax_amount = Column(Numeric(10, 2), default=Decimal("0.00"), nullable=False)
    discount_amount = Column(Numeric(10, 2), default=Decimal("0.00"), nullable=False)
    total_amount = Column(Numeric(10, 2), nullable=False)
    # Immutable labor/parts captured when the invoice is finalized. PDFs,
    # emails, and resends render from this snapshot rather than live RO rows.
    line_items_snapshot = Column(JSONB, nullable=True)
    
    due_date = Column(DateTime(timezone=True), nullable=True)
    paid_at = Column(DateTime(timezone=True), nullable=True)
    notes = Column(Text, nullable=True)
    source = Column(String(50), nullable=True, index=True)  # e.g. easy_truck_shop_import
    created_by_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    created_by_user = relationship("User", foreign_keys=[created_by_user_id])

    # Invoice revisions are preserved rather than deleted. A replacement can
    # point to the voided invoice it supersedes, keeping the financial trail
    # explicit while allowing another invoice for the same repair order.
    voided_at = Column(DateTime(timezone=True), nullable=True)
    voided_by_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    voided_by_user = relationship("User", foreign_keys=[voided_by_user_id])
    void_reason = Column(Text, nullable=True)
    supersedes_invoice_id = Column(UUID(as_uuid=True), ForeignKey("invoices.id"), nullable=True, index=True)
    supersedes_invoice = relationship("Invoice", remote_side="Invoice.id", foreign_keys=[supersedes_invoice_id])

    # Pending Zelle confirmation tracking (customer marked as sent, staff must confirm receipt)
    zelle_pending_submitted_at = Column(DateTime(timezone=True), nullable=True, index=True)
    zelle_pending_sender_email = Column(String(255), nullable=True)
    zelle_pending_sender_phone = Column(String(20), nullable=True)
    zelle_pending_last_reminder_at = Column(DateTime(timezone=True), nullable=True)
    zelle_pending_reminder_count = Column(Integer, default=0, nullable=False)
    
    # Reminder tracking for overdue invoices
    last_reminder_sent_at = Column(DateTime(timezone=True), nullable=True)
    reminder_count = Column(Integer, default=0, nullable=False)
    
    payments = relationship("Payment", back_populates="invoice", cascade="all, delete-orphan")

    @property
    def pending_zelle_confirmation(self) -> bool:
        return self.status != InvoiceStatus.PAID and self.zelle_pending_submitted_at is not None
