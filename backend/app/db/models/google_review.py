"""Tenant-isolated Google Business Profile review records and audit trail."""
import enum
from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from app.db.base import BaseModel


class GoogleReviewStatus(str, enum.Enum):
    NEW = "new"
    AWAITING_APPROVAL = "awaiting_approval"
    PUBLISHING = "publishing"
    PUBLISHED = "published"
    FAILED = "failed"


class GoogleBusinessConnection(BaseModel):
    __tablename__ = "google_business_connections"
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False, unique=True, index=True)
    google_account_id = Column(String(255), nullable=True, index=True)
    location_id = Column(String(255), nullable=True, index=True)
    location_name = Column(String(500), nullable=True)
    status = Column(String(32), nullable=False, default="disconnected", index=True)
    encrypted_access_token = Column(Text, nullable=True)
    encrypted_refresh_token = Column(Text, nullable=True)
    access_token_expires_at = Column(DateTime(timezone=True), nullable=True)
    connected_at = Column(DateTime(timezone=True), nullable=True)
    disconnected_at = Column(DateTime(timezone=True), nullable=True)
    last_token_refresh_at = Column(DateTime(timezone=True), nullable=True)
    last_token_refresh_error = Column(Text, nullable=True)
    last_sync_at = Column(DateTime(timezone=True), nullable=True)
    last_sync_error = Column(Text, nullable=True)
    tenant = relationship("Tenant")


class GoogleBusinessOAuthState(BaseModel):
    __tablename__ = "google_business_oauth_states"
    state_hash = Column(String(64), nullable=False, unique=True)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False, index=True)
    initiated_by_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)
    expires_at = Column(DateTime(timezone=True), nullable=False, index=True)
    consumed_at = Column(DateTime(timezone=True), nullable=True)


class GoogleReviewSettings(BaseModel):
    __tablename__ = "google_review_settings"
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False, unique=True, index=True)
    brand_voice_prompt = Column(Text, nullable=False, default="")
    reply_policy = Column(Text, nullable=False, default="")
    auto_publish_five_star = Column(Boolean, nullable=False, default=False)
    alert_recipients = Column(JSON, nullable=False, default=list)
    tenant = relationship("Tenant")


class GoogleReview(BaseModel):
    __tablename__ = "google_reviews"
    __table_args__ = (UniqueConstraint("tenant_id", "google_review_id", name="uq_google_review_tenant_review"),)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False, index=True)
    connection_id = Column(UUID(as_uuid=True), ForeignKey("google_business_connections.id"), nullable=False, index=True)
    google_review_id = Column(String(512), nullable=False)
    reviewer_name = Column(String(255), nullable=True)
    rating = Column(Integer, nullable=False)
    review_text = Column(Text, nullable=True)
    review_created_at = Column(DateTime(timezone=True), nullable=True, index=True)
    review_updated_at = Column(DateTime(timezone=True), nullable=True)
    raw_payload = Column(JSON, nullable=False, default=dict)
    ai_draft = Column(Text, nullable=True)
    ai_model = Column(String(128), nullable=True)
    ai_metadata = Column(JSON, nullable=False, default=dict)
    reply_text = Column(Text, nullable=True)
    status = Column(String(32), nullable=False, default=GoogleReviewStatus.NEW.value, index=True)
    requires_approval = Column(Boolean, nullable=False, default=True)
    approved_at = Column(DateTime(timezone=True), nullable=True)
    approved_by_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    published_at = Column(DateTime(timezone=True), nullable=True)
    publish_response = Column(JSON, nullable=True)
    publish_failure_reason = Column(Text, nullable=True)
    publish_retry_count = Column(Integer, nullable=False, default=0)
    last_publish_attempt_at = Column(DateTime(timezone=True), nullable=True)
    tenant = relationship("Tenant")


class GoogleReviewAuditEvent(BaseModel):
    __tablename__ = "google_review_audit_events"
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False, index=True)
    review_id = Column(UUID(as_uuid=True), ForeignKey("google_reviews.id"), nullable=True, index=True)
    actor_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    event_type = Column(String(64), nullable=False, index=True)
    metadata_json = Column(JSON, nullable=False, default=dict)
