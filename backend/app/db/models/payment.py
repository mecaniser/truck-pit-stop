from sqlalchemy import Column, String, ForeignKey, Numeric, Text, Enum as SQLEnum
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import UUID
import enum
from decimal import Decimal
from app.db.base import BaseModel


class PaymentMethod(str, enum.Enum):
    STRIPE = "stripe"
    CASH = "cash"
    CHECK = "check"
    ACH = "ach"
    OTHER = "other"


class PaymentStatus(str, enum.Enum):
    PENDING = "pending"
    COMPLETED = "completed"
    FAILED = "failed"
    REFUNDED = "refunded"


class Payment(BaseModel):
    __tablename__ = "payments"
    
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False, index=True)
    tenant = relationship("Tenant", backref="payments")
    
    invoice_id = Column(UUID(as_uuid=True), ForeignKey("invoices.id"), nullable=False, index=True)
    invoice = relationship("Invoice", back_populates="payments")
    
    payment_number = Column(String(50), unique=True, nullable=False, index=True)
    amount = Column(Numeric(10, 2), nullable=False)
    method = Column(
        SQLEnum(PaymentMethod, values_callable=lambda e: [m.value for m in e]),
        nullable=False
    )
    status = Column(
        SQLEnum(PaymentStatus, values_callable=lambda e: [m.value for m in e]),
        nullable=False,
        default=PaymentStatus.PENDING,
        index=True
    )
    
    stripe_payment_intent_id = Column(String(255), nullable=True, unique=True, index=True)
    stripe_charge_id = Column(String(255), nullable=True)
    
    notes = Column(Text, nullable=True)
    receipt_url = Column(String(500), nullable=True)


