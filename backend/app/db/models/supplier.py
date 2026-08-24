from sqlalchemy import Boolean, CheckConstraint, Column, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from app.db.base import BaseModel


class Supplier(BaseModel):
    __tablename__ = "suppliers"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_suppliers_tenant_id_id_db038"),
        CheckConstraint(
            "default_lead_time_days IS NULL OR (default_lead_time_days >= 0 AND default_lead_time_days <= 365)",
            name="ck_supplier_default_lead_time_days",
        ),
        CheckConstraint(
            "minimum_order_amount IS NULL OR minimum_order_amount >= 0",
            name="ck_supplier_minimum_order_amount",
        ),
    )

    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False, index=True)
    tenant = relationship("Tenant", backref="suppliers")

    name = Column(String(255), nullable=False, index=True)
    normalized_name = Column(String(255), nullable=True, index=True)
    is_active = Column(Boolean, default=True, server_default="true", nullable=False)
    account_reference = Column(String(100), nullable=True)
    email = Column(String(255), nullable=True)
    payment_terms = Column(String(100), nullable=True)
    default_lead_time_days = Column(Integer, nullable=True)
    minimum_order_amount = Column(Numeric(12, 2), nullable=True)
    purchasing_notes = Column(Text, nullable=True)
    address = Column(String(500), nullable=True)
    phone = Column(String(30), nullable=True)
    contact_name = Column(String(255), nullable=True)
    notes = Column(String(500), nullable=True)
