"""Durable recommendation provenance; line removal never erases this record."""
from sqlalchemy import Column, DateTime, ForeignKey, Index, Numeric, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from app.db.base import BaseModel


class RecommendationConversion(BaseModel):
    __tablename__ = "recommendation_conversions"
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False, index=True)
    recommendation_id = Column(UUID(as_uuid=True), ForeignKey("recommended_services.id"), nullable=False, index=True)
    source_order_id = Column(UUID(as_uuid=True), ForeignKey("repair_orders.id"), nullable=False)
    source_order_number = Column(String(255), nullable=False)
    source_description = Column(Text, nullable=False)
    source_priority = Column(String(20), nullable=False)
    vehicle_id = Column(UUID(as_uuid=True), ForeignKey("vehicles.id"), nullable=False)
    target_order_id = Column(UUID(as_uuid=True), ForeignKey("repair_orders.id"), nullable=False, index=True)
    target_order_number = Column(String(255), nullable=False)
    # Intentionally an immutable audit UUID, not a cascading FK to deletable Labor.
    target_labor_id = Column(UUID(as_uuid=True), nullable=False)
    request_id = Column(UUID(as_uuid=True), nullable=False)
    request_hash = Column(String(64), nullable=False)
    hours = Column(Numeric(5, 2), nullable=False)
    hourly_rate = Column(Numeric(10, 2), nullable=False)
    created_by_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    superseded_at = Column(DateTime(timezone=True), nullable=True)
    superseded_by_conversion_id = Column(UUID(as_uuid=True), ForeignKey("recommendation_conversions.id"), nullable=True)
    __table_args__ = (
        UniqueConstraint("tenant_id", "request_id", name="uq_rec_conversion_request"),
        UniqueConstraint("tenant_id", "target_labor_id", name="uq_rec_conversion_labor"),
        Index("uq_rec_conversion_current", "tenant_id", "recommendation_id", unique=True,
              postgresql_where=superseded_at.is_(None), sqlite_where=superseded_at.is_(None)),
    )
