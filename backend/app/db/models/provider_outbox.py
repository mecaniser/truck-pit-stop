"""Durable hand-off records for provider delivery work.

An outbox row is committed with the business change that caused it. A worker
claims the row later, so a slow or unavailable provider cannot keep an API
request or database transaction open.
"""
from __future__ import annotations

import enum

from sqlalchemy import Column, DateTime, ForeignKey, Index, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.db.base import BaseModel


class ProviderOutboxStatus(str, enum.Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    SUCCEEDED = "succeeded"
    DEAD = "dead"
    # Terminal privacy-policy state. Provider outbox status is intentionally a
    # string column, so this additive value requires no database migration.
    EXPIRED = "expired"


class ProviderOutboxEvent(BaseModel):
    __tablename__ = "provider_outbox"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "event_type",
            "idempotency_key",
            name="uq_provider_outbox_tenant_event_idempotency",
        ),
        Index("ix_provider_outbox_due", "status", "available_at"),
        Index("ix_provider_outbox_tenant_created", "tenant_id", "created_at"),
    )

    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False, index=True)
    tenant = relationship("Tenant", backref="provider_outbox_events")

    # Keep this a string rather than a database enum so new event types can be
    # added in a deploy without an enum-alter migration.
    event_type = Column(String(100), nullable=False, index=True)
    aggregate_type = Column(String(100), nullable=False)
    aggregate_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    payload = Column(JSON, nullable=False, default=dict)
    idempotency_key = Column(String(255), nullable=False)

    status = Column(String(20), nullable=False, default=ProviderOutboxStatus.PENDING.value, index=True)
    attempt_count = Column(Integer, nullable=False, default=0)
    available_at = Column(DateTime(timezone=True), nullable=False)
    locked_at = Column(DateTime(timezone=True), nullable=True)
    locked_until = Column(DateTime(timezone=True), nullable=True, index=True)
    lock_token = Column(String(64), nullable=True, index=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    provider_message_id = Column(String(255), nullable=True)
    last_error = Column(Text, nullable=True)
    last_attempt_at = Column(DateTime(timezone=True), nullable=True)
    last_response_code = Column(Integer, nullable=True)
