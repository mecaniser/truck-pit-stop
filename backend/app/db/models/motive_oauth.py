"""Company-scoped OAuth connector, deliberately separate from fixture storage."""

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID

from app.db.base import BaseModel


class MotiveConnection(BaseModel):
    __tablename__ = "motive_connections"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "fleet_customer_id", name="uq_motive_connection_company"
        ),
        UniqueConstraint("tenant_id", "id", name="uq_motive_connection_identity"),
        UniqueConstraint(
            "tenant_id", "provider_company_id", name="uq_motive_provider_company"
        ),
        ForeignKeyConstraint(
            ["tenant_id", "fleet_customer_id"], ["customers.tenant_id", "customers.id"]
        ),
    )
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False)
    fleet_customer_id = Column(UUID(as_uuid=True), nullable=False)
    provider_company_id = Column(String(120), nullable=True)
    provider_company_name = Column(String(255), nullable=True)
    status = Column(String(32), nullable=False, default="disconnected")
    generation = Column(Integer, nullable=False, default=0)
    encrypted_tokens = Column(Text, nullable=True)
    token_key_version = Column(String(32), nullable=True)
    token_expires_at = Column(DateTime(timezone=True), nullable=True)
    scopes = Column(String(500), nullable=False, default="")
    connected_at = Column(DateTime(timezone=True), nullable=True)
    reconciliation_cutoff_at = Column(DateTime(timezone=True), nullable=True)
    last_reconciled_at = Column(DateTime(timezone=True), nullable=True)
    last_sync_at = Column(DateTime(timezone=True), nullable=True)
    next_sync_at = Column(DateTime(timezone=True), nullable=True)
    last_error_code = Column(String(40), nullable=True)
    last_sync_counts = Column(JSON, nullable=True)
    webhook_id = Column(UUID(as_uuid=True), nullable=True, unique=True)
    webhook_generation = Column(Integer, nullable=False, default=0, server_default="0")
    encrypted_webhook_secret = Column(Text, nullable=True)
    webhook_enabled = Column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    webhook_last_received_at = Column(DateTime(timezone=True), nullable=True)
    webhook_verified_at = Column(DateTime(timezone=True), nullable=True)
    failure_count = Column(Integer, nullable=False, default=0)


class MotiveAuthorization(BaseModel):
    __tablename__ = "motive_authorizations"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "connection_id"],
            ["motive_connections.tenant_id", "motive_connections.id"],
        ),
    )
    tenant_id = Column(UUID(as_uuid=True), nullable=False)
    connection_id = Column(UUID(as_uuid=True), nullable=False)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    state_hash = Column(String(64), nullable=False, unique=True)
    session_hash = Column(String(64), nullable=False)
    generation = Column(Integer, nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    consumed_at = Column(DateTime(timezone=True), nullable=True)


class MotiveRemoteVehicle(BaseModel):
    __tablename__ = "motive_remote_vehicles"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "connection_id", "id", name="uq_motive_remote_identity"
        ),
        UniqueConstraint(
            "connection_id", "provider_vehicle_id", name="uq_motive_remote_vehicle"
        ),
        UniqueConstraint("tenant_id", "vehicle_id", name="uq_motive_remote_mapping"),
        ForeignKeyConstraint(
            ["tenant_id", "connection_id"],
            ["motive_connections.tenant_id", "motive_connections.id"],
        ),
        ForeignKeyConstraint(
            ["tenant_id", "vehicle_id"], ["vehicles.tenant_id", "vehicles.id"]
        ),
    )
    tenant_id = Column(UUID(as_uuid=True), nullable=False)
    connection_id = Column(UUID(as_uuid=True), nullable=False)
    provider_vehicle_id = Column(String(120), nullable=False)
    number = Column(String(120), nullable=True)
    vin = Column(String(17), nullable=True)
    vehicle_id = Column(UUID(as_uuid=True), nullable=True)
    mapped_by_user_id = Column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    mapped_at = Column(DateTime(timezone=True), nullable=True)
    located_at = Column(DateTime(timezone=True), nullable=True)
    received_at = Column(DateTime(timezone=True), nullable=True)
    lat = Column(Float, nullable=True)
    lng = Column(Float, nullable=True)
    speed_mph = Column(Float, nullable=True)
    bearing = Column(Float, nullable=True)
    gateway_id = Column(String(120), nullable=True)
    gateway_identifier = Column(String(120), nullable=True)
    gateway_model = Column(String(120), nullable=True)
    provider_status = Column(String(24), nullable=True)
    metrics_received_at = Column(DateTime(timezone=True), nullable=True)
    faults_synced_at = Column(DateTime(timezone=True), nullable=True)
    metrics_observed_at = Column(DateTime(timezone=True), nullable=True)
    virtual_odometer_miles = Column(Float, nullable=True)
    true_odometer_miles = Column(Float, nullable=True)
    virtual_engine_hours = Column(Float, nullable=True)
    true_engine_hours = Column(Float, nullable=True)
    history_cursor_at = Column(DateTime(timezone=True), nullable=True)
    fault_cursor_at = Column(DateTime(timezone=True), nullable=True)
    discovered_at = Column(DateTime(timezone=True), nullable=False)


class MotiveFleetAdminGrant(BaseModel):
    __tablename__ = "motive_fleet_admin_grants"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "fleet_customer_id", "user_id", name="uq_motive_fleet_admin"
        ),
        ForeignKeyConstraint(
            ["tenant_id", "fleet_customer_id"], ["customers.tenant_id", "customers.id"]
        ),
    )
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False)
    fleet_customer_id = Column(UUID(as_uuid=True), nullable=False)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    granted_by_user_id = Column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    revoked_by_user_id = Column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    revoked_at = Column(DateTime(timezone=True), nullable=True)


class MotiveHistorySample(BaseModel):
    __tablename__ = "motive_history_samples"
    __table_args__ = (
        UniqueConstraint(
            "remote_vehicle_id", "provider_location_id", name="uq_motive_history_event"
        ),
        ForeignKeyConstraint(
            ["tenant_id", "connection_id", "remote_vehicle_id"],
            [
                "motive_remote_vehicles.tenant_id",
                "motive_remote_vehicles.connection_id",
                "motive_remote_vehicles.id",
            ],
        ),
        Index(
            "ix_motive_history_observation", "remote_vehicle_id", "observed_at", "id"
        ),
    )
    tenant_id = Column(UUID(as_uuid=True), nullable=False)
    connection_id = Column(UUID(as_uuid=True), nullable=False)
    remote_vehicle_id = Column(UUID(as_uuid=True), nullable=False)
    provider_location_id = Column(String(120), nullable=False)
    mapping_epoch = Column(DateTime(timezone=True), nullable=False)
    observed_at = Column(DateTime(timezone=True), nullable=False)
    received_at = Column(DateTime(timezone=True), nullable=False)
    lat = Column(Float, nullable=True)
    lng = Column(Float, nullable=True)
    speed_mph = Column(Float, nullable=True)
    bearing_degrees = Column(Float, nullable=True)
    virtual_odometer_miles = Column(Float, nullable=True)
    true_odometer_miles = Column(Float, nullable=True)
    virtual_engine_hours = Column(Float, nullable=True)
    true_engine_hours = Column(Float, nullable=True)
    content_sha256 = Column(String(64), nullable=False)


class MotiveFault(BaseModel):
    __tablename__ = "motive_faults"
    __table_args__ = (
        UniqueConstraint(
            "connection_id", "provider_fault_id", name="uq_motive_fault_event"
        ),
        ForeignKeyConstraint(
            ["tenant_id", "connection_id", "remote_vehicle_id"],
            [
                "motive_remote_vehicles.tenant_id",
                "motive_remote_vehicles.connection_id",
                "motive_remote_vehicles.id",
            ],
        ),
        Index("ix_motive_fault_vehicle", "remote_vehicle_id", "last_observed_at"),
    )
    tenant_id = Column(UUID(as_uuid=True), nullable=False)
    connection_id = Column(UUID(as_uuid=True), nullable=False)
    remote_vehicle_id = Column(UUID(as_uuid=True), nullable=False)
    provider_fault_id = Column(String(120), nullable=False)
    mapping_epoch = Column(DateTime(timezone=True), nullable=False)
    code_label = Column(String(120), nullable=True)
    fmi = Column(String(40), nullable=True)
    code = Column(String(120), nullable=True)
    description = Column(String(1000), nullable=True)
    status = Column(String(16), nullable=False)
    first_observed_at = Column(DateTime(timezone=True), nullable=False)
    last_observed_at = Column(DateTime(timezone=True), nullable=False)
    received_at = Column(DateTime(timezone=True), nullable=False)
    content_sha256 = Column(String(64), nullable=False)


class MotiveWebhookReceipt(BaseModel):
    __tablename__ = "motive_webhook_receipts"
    __table_args__ = (
        UniqueConstraint(
            "connection_id",
            "webhook_generation",
            "payload_sha256",
            name="uq_motive_webhook_delivery",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "connection_id"],
            ["motive_connections.tenant_id", "motive_connections.id"],
        ),
        Index("ix_motive_inbox_pending", "connection_id", "status", "received_at"),
    )
    tenant_id = Column(UUID(as_uuid=True), nullable=False)
    connection_id = Column(UUID(as_uuid=True), nullable=False)
    connection_generation = Column(Integer, nullable=False)
    webhook_generation = Column(Integer, nullable=False)
    action = Column(String(48), nullable=False)
    provider_vehicle_id = Column(String(120), nullable=True)
    provider_object_id = Column(String(120), nullable=True)
    payload_sha256 = Column(String(64), nullable=False)
    received_at = Column(DateTime(timezone=True), nullable=False)
    processed_at = Column(DateTime(timezone=True), nullable=True)
    next_attempt_at = Column(DateTime(timezone=True), nullable=True)
    attempts = Column(Integer, nullable=False, default=0)
    status = Column(String(24), nullable=False, default="pending")
    error_code = Column(String(48), nullable=True)
