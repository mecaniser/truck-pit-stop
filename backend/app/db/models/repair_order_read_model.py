from sqlalchemy import Boolean, Column, DateTime, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID

from app.db.base import Base


class RepairOrderReadModel(Base):
    """Transactionally maintained projection for the repair-order list.

    List screens need a fixed, self-contained row. Keeping the rendered
    payload here prevents a growing tenant from turning each list request into
    joins and follow-up lookups across customers, vehicles, quotes, and
    invoices.
    """

    __tablename__ = "repair_order_read_models"

    repair_order_id = Column(
        UUID(as_uuid=True),
        ForeignKey("repair_orders.id", ondelete="CASCADE"),
        primary_key=True,
    )
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False, index=True)
    customer_id = Column(UUID(as_uuid=True), ForeignKey("customers.id"), nullable=False)
    vehicle_id = Column(UUID(as_uuid=True), ForeignKey("vehicles.id"), nullable=False)
    status = Column(String(32), nullable=False)
    is_internal = Column(Boolean, nullable=False, default=False)
    is_deleted = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime(timezone=True), nullable=False)
    # The searchable display values are stored independently from payload so
    # the list can filter without reopening customer and vehicle tables.
    search_document = Column(Text, nullable=False, default="")
    search_compact = Column(Text, nullable=False, default="")
    payload = Column(JSONB, nullable=False)
    refreshed_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
