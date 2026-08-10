"""Driver identity, equipment custody, and reviewed accountability records.

Driver profiles are durable domain records.  A linked ``User`` only grants
application access; removing that access must not erase the driver's history.
Custody records establish who was operating equipment at a point in time, but
they deliberately do not establish fault.
"""

from sqlalchemy import (
    CheckConstraint,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship

from app.db.base import BaseModel


class DriverProfile(BaseModel):
    __tablename__ = "driver_profiles"

    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False, index=True)
    # Optional authentication link.  WorkOS identifiers never become domain
    # foreign keys; the local User remains the immutable actor projection.
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True, unique=True, index=True)
    employer_customer_id = Column(
        UUID(as_uuid=True), ForeignKey("customers.id"), nullable=True, index=True
    )

    first_name = Column(String(100), nullable=False)
    last_name = Column(String(100), nullable=False)
    phone = Column(String(20), nullable=True)
    email = Column(String(255), nullable=True)
    employee_number = Column(String(80), nullable=True)
    license_number = Column(String(80), nullable=True)
    license_state = Column(String(2), nullable=True)
    license_expires_on = Column(Date, nullable=True)
    employment_status = Column(String(24), nullable=False, default="active", server_default="active")
    hired_at = Column(DateTime(timezone=True), nullable=True)
    ended_at = Column(DateTime(timezone=True), nullable=True)
    notes = Column(Text, nullable=True)

    user = relationship("User", foreign_keys=[user_id])
    employer_customer = relationship("Customer", foreign_keys=[employer_customer_id])
    custody_sessions = relationship("EquipmentCustodySession", back_populates="driver")

    __table_args__ = (
        CheckConstraint(
            "employment_status IN ('active', 'inactive')",
            name="ck_driver_profiles_employment_status",
        ),
        Index("ix_driver_profiles_tenant_status", "tenant_id", "employment_status"),
        Index(
            "uq_driver_profiles_active_employee_number",
            "tenant_id",
            "employee_number",
            unique=True,
            postgresql_where=text(
                "employee_number IS NOT NULL AND employment_status = 'active' AND deleted_at IS NULL"
            ),
            sqlite_where=text(
                "employee_number IS NOT NULL AND employment_status = 'active' AND deleted_at IS NULL"
            ),
        ),
    )


class FleetTrailer(BaseModel):
    """Canonical trailer identity independent of its current driver or tractor."""

    __tablename__ = "fleet_trailers"

    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False, index=True)
    owner_customer_id = Column(
        UUID(as_uuid=True), ForeignKey("customers.id"), nullable=True, index=True
    )
    vin = Column(String(17), nullable=True, index=True)
    unit_number = Column(String(50), nullable=True, index=True)
    make = Column(String(100), nullable=True)
    model = Column(String(100), nullable=True)
    year = Column(Integer, nullable=True)
    license_plate = Column(String(20), nullable=True, index=True)
    body_type = Column(String(80), nullable=True)
    status = Column(String(24), nullable=False, default="active", server_default="active")
    notes = Column(Text, nullable=True)

    owner_customer = relationship("Customer", foreign_keys=[owner_customer_id])
    custody_assets = relationship("EquipmentCustodyAsset", back_populates="trailer")

    __table_args__ = (
        CheckConstraint(
            "status IN ('active', 'yard', 'out_of_service', 'retired')",
            name="ck_fleet_trailers_status",
        ),
    )


class EquipmentCustodySession(BaseModel):
    """A dated period in which a driver has care of one or more assets."""

    __tablename__ = "equipment_custody_sessions"

    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False, index=True)
    driver_id = Column(
        UUID(as_uuid=True), ForeignKey("driver_profiles.id"), nullable=False, index=True
    )
    assigned_by_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    released_by_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)

    status = Column(String(24), nullable=False, default="assigned", server_default="assigned", index=True)
    starts_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), index=True)
    acknowledged_at = Column(DateTime(timezone=True), nullable=True)
    ends_at = Column(DateTime(timezone=True), nullable=True, index=True)
    dispatch_reference = Column(String(120), nullable=True)
    handoff_notes = Column(Text, nullable=True)

    driver = relationship("DriverProfile", back_populates="custody_sessions")
    assigned_by = relationship("User", foreign_keys=[assigned_by_user_id])
    released_by = relationship("User", foreign_keys=[released_by_user_id])
    assets = relationship(
        "EquipmentCustodyAsset",
        back_populates="custody_session",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        CheckConstraint(
            "status IN ('assigned', 'active', 'closed', 'cancelled')",
            name="ck_equipment_custody_sessions_status",
        ),
        CheckConstraint(
            "ends_at IS NULL OR ends_at >= starts_at",
            name="ck_equipment_custody_sessions_dates",
        ),
        Index(
            "ix_equipment_custody_driver_timeline",
            "tenant_id",
            "driver_id",
            "starts_at",
            "ends_at",
        ),
    )


class EquipmentCustodyAsset(BaseModel):
    """One tractor or trailer attached to a custody session.

    Assets can be released independently, allowing a trailer swap without
    closing the driver's entire duty/custody period.
    """

    __tablename__ = "equipment_custody_assets"

    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False, index=True)
    custody_session_id = Column(
        UUID(as_uuid=True),
        ForeignKey("equipment_custody_sessions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    vehicle_id = Column(UUID(as_uuid=True), ForeignKey("vehicles.id"), nullable=True, index=True)
    trailer_id = Column(
        UUID(as_uuid=True), ForeignKey("fleet_trailers.id"), nullable=True, index=True
    )
    equipment_role = Column(String(24), nullable=False)
    attached_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    released_at = Column(DateTime(timezone=True), nullable=True, index=True)
    start_odometer = Column(Integer, nullable=True)
    end_odometer = Column(Integer, nullable=True)
    checkout_condition = Column(Text, nullable=True)
    checkin_condition = Column(Text, nullable=True)

    custody_session = relationship("EquipmentCustodySession", back_populates="assets")
    vehicle = relationship("Vehicle")
    trailer = relationship("FleetTrailer", back_populates="custody_assets")

    __table_args__ = (
        CheckConstraint(
            "(vehicle_id IS NOT NULL AND trailer_id IS NULL) OR "
            "(vehicle_id IS NULL AND trailer_id IS NOT NULL)",
            name="ck_equipment_custody_assets_exactly_one_asset",
        ),
        CheckConstraint(
            "equipment_role IN ('power_unit', 'trailer')",
            name="ck_equipment_custody_assets_role",
        ),
        CheckConstraint(
            "released_at IS NULL OR released_at >= attached_at",
            name="ck_equipment_custody_assets_dates",
        ),
        CheckConstraint(
            "start_odometer IS NULL OR start_odometer >= 0",
            name="ck_equipment_custody_assets_start_odometer",
        ),
        CheckConstraint(
            "end_odometer IS NULL OR end_odometer >= 0",
            name="ck_equipment_custody_assets_end_odometer",
        ),
        Index(
            "uq_equipment_custody_active_vehicle",
            "vehicle_id",
            unique=True,
            postgresql_where=text(
                "vehicle_id IS NOT NULL AND released_at IS NULL AND deleted_at IS NULL"
            ),
            sqlite_where=text(
                "vehicle_id IS NOT NULL AND released_at IS NULL AND deleted_at IS NULL"
            ),
        ),
        Index(
            "uq_equipment_custody_active_trailer",
            "trailer_id",
            unique=True,
            postgresql_where=text(
                "trailer_id IS NOT NULL AND released_at IS NULL AND deleted_at IS NULL"
            ),
            sqlite_where=text(
                "trailer_id IS NOT NULL AND released_at IS NULL AND deleted_at IS NULL"
            ),
        ),
    )


class FleetAccountabilityReview(BaseModel):
    """Revisioned manager finding; separate from an incident's repair status."""

    __tablename__ = "fleet_accountability_reviews"

    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False, index=True)
    incident_id = Column(
        UUID(as_uuid=True), ForeignKey("fleet_incidents.id"), nullable=False, index=True
    )
    revision = Column(Integer, nullable=False, default=1, server_default="1")
    status = Column(String(32), nullable=False, default="pending", server_default="pending", index=True)
    reviewed_by_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    duty_considered = Column(String(64), nullable=True)
    finding = Column(String(48), nullable=True)
    evidence_summary = Column(Text, nullable=True)
    rationale = Column(Text, nullable=True)
    finalized_at = Column(DateTime(timezone=True), nullable=True)

    incident = relationship("FleetIncident")
    reviewed_by = relationship("User", foreign_keys=[reviewed_by_user_id])
    attributions = relationship(
        "FleetAccountabilityAttribution",
        back_populates="review",
        cascade="all, delete-orphan",
    )
    driver_responses = relationship(
        "FleetDriverReviewResponse",
        back_populates="review",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        UniqueConstraint("incident_id", "revision", name="uq_fleet_accountability_review_revision"),
        CheckConstraint(
            "status IN ('pending', 'in_review', 'awaiting_driver_response', "
            "'disputed', 'finalized', 'reopened', 'voided')",
            name="ck_fleet_accountability_reviews_status",
        ),
        CheckConstraint(
            "finding IS NULL OR finding IN ('not_attributable', 'insufficient_evidence', "
            "'driver_duty_issue', 'shared_responsibility', 'non_driver_issue')",
            name="ck_fleet_accountability_reviews_finding",
        ),
    )


class FleetAccountabilityAttribution(BaseModel):
    __tablename__ = "fleet_accountability_attributions"

    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False, index=True)
    review_id = Column(
        UUID(as_uuid=True),
        ForeignKey("fleet_accountability_reviews.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    driver_id = Column(UUID(as_uuid=True), ForeignKey("driver_profiles.id"), nullable=True, index=True)
    party_type = Column(String(32), nullable=False)
    attribution = Column(String(24), nullable=False)
    rationale = Column(Text, nullable=True)

    review = relationship("FleetAccountabilityReview", back_populates="attributions")
    driver = relationship("DriverProfile")

    __table_args__ = (
        CheckConstraint(
            "party_type IN ('driver', 'maintenance', 'dispatch', 'equipment', "
            "'third_party', 'road_weather', 'unknown')",
            name="ck_fleet_accountability_attributions_party_type",
        ),
        CheckConstraint(
            "attribution IN ('primary', 'contributing', 'not_attributable')",
            name="ck_fleet_accountability_attributions_value",
        ),
        CheckConstraint(
            "(party_type = 'driver' AND driver_id IS NOT NULL) OR "
            "(party_type <> 'driver' AND driver_id IS NULL)",
            name="ck_fleet_accountability_attributions_driver",
        ),
    )


class FleetDriverReviewResponse(BaseModel):
    __tablename__ = "fleet_driver_review_responses"

    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False, index=True)
    review_id = Column(
        UUID(as_uuid=True),
        ForeignKey("fleet_accountability_reviews.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    driver_id = Column(
        UUID(as_uuid=True), ForeignKey("driver_profiles.id"), nullable=False, index=True
    )
    submitted_by_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    response_type = Column(String(24), nullable=False)
    statement = Column(Text, nullable=True)
    submitted_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    review = relationship("FleetAccountabilityReview", back_populates="driver_responses")
    driver = relationship("DriverProfile")
    submitted_by = relationship("User", foreign_keys=[submitted_by_user_id])

    __table_args__ = (
        CheckConstraint(
            "response_type IN ('acknowledged', 'context', 'dispute')",
            name="ck_fleet_driver_review_responses_type",
        ),
    )


class FleetIncidentEvent(BaseModel):
    """Append-only incident activity used for evidence and audit history."""

    __tablename__ = "fleet_incident_events"

    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False, index=True)
    incident_id = Column(
        UUID(as_uuid=True), ForeignKey("fleet_incidents.id"), nullable=False, index=True
    )
    actor_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True, index=True)
    event_type = Column(String(48), nullable=False, index=True)
    reason = Column(Text, nullable=True)
    data_json = Column(JSONB, nullable=False, default=dict, server_default="{}")
    occurred_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), index=True)

    incident = relationship("FleetIncident")
    actor = relationship("User", foreign_keys=[actor_user_id])

    __table_args__ = (
        Index("ix_fleet_incident_events_timeline", "tenant_id", "incident_id", "occurred_at"),
    )
