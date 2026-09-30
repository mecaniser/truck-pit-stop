"""Company-scoped OAuth connector, deliberately separate from fixture storage."""

from sqlalchemy import (
    JSON,
    Column,
    DateTime,
    Float,
    ForeignKey,
    ForeignKeyConstraint,
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
    last_sync_at = Column(DateTime(timezone=True), nullable=True)
    next_sync_at = Column(DateTime(timezone=True), nullable=True)
    last_error_code = Column(String(40), nullable=True)
    last_sync_counts = Column(JSON, nullable=True)
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
    discovered_at = Column(DateTime(timezone=True), nullable=False)
