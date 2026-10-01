"""DB-036 fixture storage. No provider credentials or production activation."""

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    Float,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import UUID

from app.db.base import BaseModel


class MotiveAccount(BaseModel):
    __tablename__ = "motive_accounts"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_motive_accounts_tenant_id"),
        UniqueConstraint(
            "tenant_id", "provider", name="uq_motive_accounts_tenant_provider"
        ),
        CheckConstraint(
            "provider = 'motive' AND mode = 'fixture'", name="ck_motive_fixture_only"
        ),
    )

    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False)
    provider = Column(
        String(16), nullable=False, default="motive", server_default="motive"
    )
    mode = Column(
        String(16), nullable=False, default="fixture", server_default="fixture"
    )
    external_company_id = Column(String(120), nullable=False)
    enabled = Column(Boolean, nullable=False, default=False, server_default="false")
    connection_state = Column(
        String(32), nullable=False, default="fixture", server_default="fixture"
    )
    granted_scopes = Column(JSON, nullable=False, default=list)
    last_successful_sync_at = Column(DateTime(timezone=True), nullable=True)
    last_sample_sequence = Column(
        BigInteger, nullable=False, default=0, server_default="0"
    )


class MotiveBinding(BaseModel):
    __tablename__ = "motive_bindings"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "account_id", "id", name="uq_motive_bindings_identity"
        ),
        ForeignKeyConstraint(
            ["tenant_id", "account_id"],
            ["motive_accounts.tenant_id", "motive_accounts.id"],
            name="fk_motive_binding_account",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "vehicle_id"],
            ["vehicles.tenant_id", "vehicles.id"],
            name="fk_motive_binding_vehicle",
        ),
        CheckConstraint(
            "valid_to IS NULL OR valid_to > valid_from",
            name="ck_motive_binding_interval",
        ),
        Index(
            "uq_motive_binding_open_external",
            "account_id",
            "provider_vehicle_id",
            unique=True,
            postgresql_where=text("valid_to IS NULL"),
            sqlite_where=text("valid_to IS NULL"),
        ),
        Index(
            "uq_motive_binding_open_gateway",
            "account_id",
            "gateway_id",
            unique=True,
            postgresql_where=text("valid_to IS NULL AND gateway_id IS NOT NULL"),
            sqlite_where=text("valid_to IS NULL AND gateway_id IS NOT NULL"),
        ),
        Index(
            "uq_motive_binding_open_vehicle",
            "tenant_id",
            "vehicle_id",
            unique=True,
            postgresql_where=text("valid_to IS NULL"),
            sqlite_where=text("valid_to IS NULL"),
        ),
    )

    tenant_id = Column(UUID(as_uuid=True), nullable=False)
    account_id = Column(UUID(as_uuid=True), nullable=False)
    vehicle_id = Column(UUID(as_uuid=True), nullable=False)
    provider_vehicle_id = Column(String(120), nullable=False)
    gateway_id = Column(String(120), nullable=True)
    valid_from = Column(DateTime(timezone=True), nullable=False)
    valid_to = Column(DateTime(timezone=True), nullable=True)
    match_basis = Column(String(32), nullable=False, default="manual_review")
    verification_state = Column(String(16), nullable=False, default="verified")
    verified_by_user_id = Column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )


class MotiveLocationSample(BaseModel):
    __tablename__ = "motive_location_samples"
    __table_args__ = (
        UniqueConstraint("account_id", "event_id", name="uq_motive_sample_event"),
        UniqueConstraint(
            "account_id", "ingestion_sequence", name="uq_motive_sample_sequence"
        ),
        UniqueConstraint(
            "tenant_id", "account_id", "id", name="uq_motive_sample_identity"
        ),
        ForeignKeyConstraint(
            ["tenant_id", "account_id", "binding_id"],
            [
                "motive_bindings.tenant_id",
                "motive_bindings.account_id",
                "motive_bindings.id",
            ],
            name="fk_motive_sample_binding",
        ),
        CheckConstraint(
            "lat BETWEEN -90 AND 90 AND lng BETWEEN -180 AND 180",
            name="ck_motive_coordinates",
        ),
        Index(
            "ix_motive_sample_latest",
            "tenant_id",
            "binding_id",
            "located_at",
            "ingestion_sequence",
        ),
    )

    tenant_id = Column(UUID(as_uuid=True), nullable=False)
    account_id = Column(UUID(as_uuid=True), nullable=False)
    binding_id = Column(UUID(as_uuid=True), nullable=False)
    event_id = Column(String(120), nullable=False)
    located_at = Column(DateTime(timezone=True), nullable=False)
    received_at = Column(DateTime(timezone=True), nullable=False)
    ingestion_sequence = Column(BigInteger, nullable=False)
    lat = Column(Float, nullable=False)
    lng = Column(Float, nullable=False)
    speed_mph = Column(Float, nullable=True)
    bearing_degrees = Column(Float, nullable=True)
    virtual_odometer_miles = Column(Float, nullable=True)
    engine_hours = Column(Float, nullable=True)
    source_type = Column(String(32), nullable=False, default="fixture_webhook")
    payload_sha256 = Column(String(64), nullable=False)


class MotiveIngestionReceipt(BaseModel):
    __tablename__ = "motive_ingestion_receipts"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "account_id"],
            ["motive_accounts.tenant_id", "motive_accounts.id"],
            name="fk_motive_receipt_account",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "account_id", "sample_id"],
            [
                "motive_location_samples.tenant_id",
                "motive_location_samples.account_id",
                "motive_location_samples.id",
            ],
            name="fk_motive_receipt_sample",
        ),
        Index(
            "uq_motive_receipt_first_event",
            "account_id",
            "event_id",
            unique=True,
            postgresql_where=text("outcome = 'stored'"),
            sqlite_where=text("outcome = 'stored'"),
        ),
        Index("ix_motive_receipt_retention", "tenant_id", "received_at"),
    )

    tenant_id = Column(UUID(as_uuid=True), nullable=False)
    account_id = Column(UUID(as_uuid=True), nullable=False)
    event_id = Column(String(120), nullable=True)
    sample_id = Column(UUID(as_uuid=True), nullable=True)
    received_at = Column(DateTime(timezone=True), nullable=False)
    signature_state = Column(String(16), nullable=False)
    payload_sha256 = Column(String(64), nullable=False)
    content_sha256 = Column(String(64), nullable=True)
    outcome = Column(String(24), nullable=False)
    reason = Column(String(32), nullable=True)
