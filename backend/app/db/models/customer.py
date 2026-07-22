from sqlalchemy import Column, String, Text, ForeignKey, Numeric, Boolean, DateTime
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import UUID
from app.db.base import BaseModel


class Customer(BaseModel):
    __tablename__ = "customers"
    
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False, index=True)
    tenant = relationship("Tenant", backref="customers")
    
    first_name = Column(String(100), nullable=False)
    last_name = Column(String(100), nullable=False)
    company_name = Column(String(255), nullable=True, index=True)
    email = Column(String(255), nullable=False, index=True)
    phone = Column(String(20), nullable=True)
    
    billing_address_line1 = Column(String(255), nullable=True)
    billing_address_line2 = Column(String(255), nullable=True)
    billing_city = Column(String(100), nullable=True)
    billing_state = Column(String(50), nullable=True)
    billing_zip = Column(String(20), nullable=True)
    billing_country = Column(String(100), nullable=True, default="USA")
    
    notes = Column(Text, nullable=True)
    source = Column(String(50), nullable=True, index=True)  # e.g. zelle, walk_in, portal
    # Stable id of the source record in Easy Truck Shop, set only on imported
    # rows. Lets the resync tool match a re-scrape to this row idempotently.
    ets_external_id = Column(String(50), nullable=True, index=True)

    # Federal motor carrier identifiers (FMCSA). Optional — most owner-operators
    # have a USDOT number; MC (Motor Carrier) number applies to for-hire carriers.
    usdot_number = Column(String(20), nullable=True, index=True)
    mc_number = Column(String(20), nullable=True, index=True)

    # House account: the garage's own fleet. Vehicles attached here are owned trucks
    # whose repair orders are priced at internal cost (no markup, no customer invoice).
    # Exactly one internal-fleet customer exists per tenant.
    is_internal_fleet = Column(Boolean, nullable=False, default=False, index=True)

    # Whether this company participates in the Fleet Board. This is deliberately
    # independent from ``is_internal_fleet``: customer fleets are normally
    # invoiced, while the shop's own fleet can still use internal-cost pricing.
    fleet_enabled = Column(Boolean, nullable=False, default=False, index=True)

    sms_opt_out = Column(Boolean, nullable=False, default=False, index=True)
    sms_opted_out_at = Column(DateTime(timezone=True), nullable=True)
    sms_opt_out_source = Column(String(50), nullable=True)
    
    # Auto-approve quotes at or below this amount (None = disabled)
    auto_approval_threshold = Column(Numeric(10, 2), nullable=True, default=None)
    
    # Stripe
    stripe_customer_id = Column(String(255), nullable=True, unique=True)

    # QuickBooks (integration pending — column exists so the link status can be
    # surfaced now and populated once the sync is built; null/empty = not linked).
    # Not unique: today this holds a shared placeholder marker ("qb-linked"),
    # not yet a real per-customer QuickBooks id.
    quickbooks_customer_id = Column(String(255), nullable=True)

    vehicles = relationship("Vehicle", back_populates="customer", cascade="all, delete-orphan")
    repair_orders = relationship("RepairOrder", back_populates="customer")
    contacts = relationship("Contact", back_populates="customer", cascade="all, delete-orphan")
    vehicle_relationships = relationship(
        "VehicleCustomerRelationship", back_populates="customer", cascade="all, delete-orphan"
    )
    fleet_memberships = relationship(
        "FleetMembership", back_populates="fleet_customer", cascade="all, delete-orphan"
    )
