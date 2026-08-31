from sqlalchemy import Column, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID

from app.db.base import BaseModel


class RepairOrderHistoryEvent(BaseModel):
    """Durable audit entries for changes made to a repair order's line items."""

    __tablename__ = "repair_order_history_events"

    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False, index=True)
    repair_order_id = Column(UUID(as_uuid=True), ForeignKey("repair_orders.id", ondelete="CASCADE"), nullable=False, index=True)
    event_type = Column(String(50), nullable=False, index=True)
    label = Column(String(255), nullable=False)
    detail = Column(Text, nullable=True)
    entity_id = Column(UUID(as_uuid=True), nullable=True, index=True)
    actor_name = Column(String(255), nullable=True)
    # Who wrote it, by identity rather than by display name — a note's author
    # must survive a rename, and two people can share a name.
    actor_user_id = Column(UUID(as_uuid=True), nullable=True, index=True)
