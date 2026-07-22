from sqlalchemy import Column, DateTime, ForeignKey, Integer, Numeric, String, func
from sqlalchemy.dialects.postgresql import UUID

from app.db.base import Base


class CustomerReadModel(Base):
    """Transactionally maintained projection for customer list screens.

    The customer list is an operational view, not a reporting query. Keeping
    its small, frequently-used aggregates here makes reads predictable as a
    tenant accumulates invoices, payments, and vehicles.
    """

    __tablename__ = "customer_read_models"

    customer_id = Column(
        UUID(as_uuid=True), ForeignKey("customers.id", ondelete="CASCADE"), primary_key=True
    )
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False, index=True)
    vehicle_count = Column(Integer, nullable=False, default=0)
    single_vehicle_license_plate = Column(String(20), nullable=True)
    invoice_total = Column(Numeric(12, 2), nullable=False, default=0)
    payment_total = Column(Numeric(12, 2), nullable=False, default=0)
    refreshed_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
