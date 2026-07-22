from sqlalchemy import Column, DateTime, ForeignKey, Integer, func
from sqlalchemy.dialects.postgresql import JSONB, UUID

from app.db.base import Base


class FleetBoardReadModel(Base):
    """One compact, transactionally maintained row for each fleet-board card.

    The payloads deliberately retain identifiers, not copied user/service names.
    That lets the board resolve the few mutable display values in bounded reads
    without recalculating operational state from every repair order.
    """

    __tablename__ = "fleet_board_read_models"

    vehicle_id = Column(
        UUID(as_uuid=True), ForeignKey("vehicles.id", ondelete="CASCADE"), primary_key=True
    )
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False, index=True)
    vehicle_data = Column(JSONB, nullable=False)
    urgent_work_order = Column(JSONB, nullable=True)
    pm_work_order = Column(JSONB, nullable=True)
    open_work_order_count = Column(Integer, nullable=False, default=0)
    open_incident_count = Column(Integer, nullable=False, default=0)
    refreshed_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
