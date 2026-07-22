from sqlalchemy import Boolean, Column, String, Integer, ForeignKey, Text, Float, DateTime, Date
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import UUID
from app.db.base import BaseModel


class Vehicle(BaseModel):
    __tablename__ = "vehicles"
    
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False, index=True)
    tenant = relationship("Tenant", backref="vehicles")
    
    customer_id = Column(UUID(as_uuid=True), ForeignKey("customers.id"), nullable=False, index=True)
    customer = relationship("Customer", back_populates="vehicles")
    
    vin = Column(String(17), nullable=True, index=True)
    unit_number = Column(String(50), nullable=True, index=True)  # Fleet/company unit identifier
    make = Column(String(100), nullable=False)
    model = Column(String(100), nullable=False)
    year = Column(Integer, nullable=True)
    license_plate = Column(String(20), nullable=True, index=True)
    color = Column(String(50), nullable=True)
    mileage = Column(Integer, nullable=True)  # current odometer (miles)
    notes = Column(Text, nullable=True)
    source = Column(String(50), nullable=True, index=True)  # e.g. easy_truck_shop_import
    # Stable id of the source record in Easy Truck Shop, set only on imported
    # rows. Lets the resync tool match a re-scrape to this row idempotently.
    ets_external_id = Column(String(50), nullable=True, index=True)

    # --- Fleet management (used by the internal Fleet board) ---
    # Assigned driver (simple fields; not a managed entity in v1).
    driver_name = Column(String(160), nullable=True)
    driver_phone = Column(String(20), nullable=True)

    # Fleet invoices are addressed to the person responsible for this specific
    # truck, not the shared internal-fleet house-account customer.
    billing_contact_name = Column(String(160), nullable=True)
    billing_contact_email = Column(String(255), nullable=True)
    billing_contact_phone = Column(String(20), nullable=True)
    # Off by default: fleet labor is billed at the garage's internal cost rate.
    # Parts remain at inventory cost in both modes.
    bill_labor_at_customer_rate = Column(Boolean, nullable=False, default=False)

    # Manual status for the idle (no open work order) state — operator sets it
    # from the board. One of: active (on the road), yard, available,
    # out_of_service. NULL = auto (on the road / PM due). An open work order
    # always wins over this.
    status_override = Column(String(20), nullable=True)

    # Dashboard warning lights currently illuminated (comma-separated labels),
    # set from the latest inspection. NULL = none. Cleared by a later inspection
    # marking them off or a completed work order.
    active_warning_lights = Column(String(255), nullable=True)

    # Mileage-based preventive maintenance. pm_remaining = next_pm_miles - mileage.
    pm_interval_miles = Column(Integer, nullable=False, default=25000)
    next_pm_miles = Column(Integer, nullable=True)  # odometer at which next PM is due
    # Date-based preventive maintenance (complements mileage). PM is due when
    # either the odometer or the date threshold is reached.
    pm_interval_days = Column(Integer, nullable=False, default=70)  # ~10 weeks (typical PM cadence)
    pm_due_date = Column(Date, nullable=True)  # date the next PM is due/scheduled

    # Last-known location from telematics (or manual entry). Provider-agnostic:
    # telematics_device_id maps this truck to the external provider's vehicle id.
    telematics_device_id = Column(String(120), nullable=True, index=True)
    last_lat = Column(Float, nullable=True)
    last_lng = Column(Float, nullable=True)
    last_location_label = Column(String(200), nullable=True)
    last_location_city = Column(String(120), nullable=True)
    last_speed_mph = Column(Integer, nullable=True)
    last_heading = Column(String(8), nullable=True)
    last_location_at = Column(DateTime(timezone=True), nullable=True)

    # Persisted NHTSA/vPIC decode snapshot used for normalized labor-memory matching.
    nhtsa_make = Column(String(100), nullable=True)
    nhtsa_model = Column(String(100), nullable=True)
    nhtsa_model_year = Column(Integer, nullable=True)
    nhtsa_vehicle_type = Column(String(100), nullable=True)
    nhtsa_body_class = Column(String(150), nullable=True)
    nhtsa_drive_type = Column(String(100), nullable=True)
    nhtsa_fuel_type = Column(String(100), nullable=True)
    nhtsa_engine_cylinders = Column(Integer, nullable=True)
    nhtsa_engine_displacement_l = Column(Float, nullable=True)
    nhtsa_engine_hp = Column(Integer, nullable=True)
    nhtsa_transmission = Column(String(100), nullable=True)
    nhtsa_gvwr = Column(String(100), nullable=True)
    nhtsa_decoded_at = Column(DateTime(timezone=True), nullable=True)
    
    repair_orders = relationship("RepairOrder", back_populates="vehicle")
    account_relationships = relationship(
        "VehicleCustomerRelationship", back_populates="vehicle", cascade="all, delete-orphan"
    )
    fleet_memberships = relationship(
        "FleetMembership", back_populates="vehicle", cascade="all, delete-orphan"
    )
