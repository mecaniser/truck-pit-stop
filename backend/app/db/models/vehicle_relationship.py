"""Temporal links between a permanent vehicle and changing business accounts."""

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Index, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.db.base import BaseModel


class VehicleCustomerRelationship(BaseModel):
    """A dated business relationship without changing the vehicle's identity.

    ``relationship_type`` is intentionally stored as text so new industry roles
    can be introduced without a PostgreSQL enum migration. Supported values in
    application code are owner, operator, and default_payer.
    """

    __tablename__ = "vehicle_customer_relationships"

    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False, index=True)
    vehicle_id = Column(UUID(as_uuid=True), ForeignKey("vehicles.id", ondelete="CASCADE"), nullable=False, index=True)
    customer_id = Column(UUID(as_uuid=True), ForeignKey("customers.id", ondelete="CASCADE"), nullable=False, index=True)
    relationship_type = Column(String(32), nullable=False, index=True)
    effective_from = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    effective_to = Column(DateTime(timezone=True), nullable=True, index=True)
    is_primary = Column(Boolean, nullable=False, default=False)
    notes = Column(Text, nullable=True)

    vehicle = relationship("Vehicle", back_populates="account_relationships")
    customer = relationship("Customer", back_populates="vehicle_relationships")

    __table_args__ = (
        Index(
            "ix_vehicle_customer_relationship_active",
            "tenant_id",
            "customer_id",
            "relationship_type",
            "effective_to",
        ),
    )


class FleetMembership(BaseModel):
    """A vehicle's dated assignment to an operating company's fleet board."""

    __tablename__ = "fleet_memberships"

    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False, index=True)
    vehicle_id = Column(UUID(as_uuid=True), ForeignKey("vehicles.id", ondelete="CASCADE"), nullable=False, index=True)
    fleet_customer_id = Column(UUID(as_uuid=True), ForeignKey("customers.id", ondelete="CASCADE"), nullable=False, index=True)
    effective_from = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    effective_to = Column(DateTime(timezone=True), nullable=True, index=True)
    notes = Column(Text, nullable=True)

    vehicle = relationship("Vehicle", back_populates="fleet_memberships")
    fleet_customer = relationship("Customer", back_populates="fleet_memberships")

    __table_args__ = (
        Index(
            "ix_fleet_membership_active",
            "tenant_id",
            "fleet_customer_id",
            "effective_to",
        ),
    )
