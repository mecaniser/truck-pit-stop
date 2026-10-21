"""Append-only owner management-cost evidence, separate from source writers."""
from uuid import uuid4
from sqlalchemy import Column, String, Integer, DateTime, ForeignKey, UniqueConstraint, CheckConstraint, JSON, func, event
from sqlalchemy.dialects.postgresql import UUID
from app.db.base import Base


class TechnicianCostPolicyRevision(Base):
    __tablename__ = "technician_cost_policy_revisions"
    __table_args__ = (UniqueConstraint("tenant_id", "mechanic_id", "version", name="uq_cost_policy_version"),
                     UniqueConstraint("tenant_id", "idempotency_key", name="uq_cost_policy_key"),
                     CheckConstraint("version > 0", name="ck_cost_policy_version"))
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False, index=True)
    mechanic_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)
    version = Column(Integer, nullable=False)
    supersedes_id = Column(UUID(as_uuid=True), ForeignKey("technician_cost_policy_revisions.id"), nullable=True, unique=True)
    policy = Column(JSON, nullable=False)
    request_sha256 = Column(String(64), nullable=False)
    idempotency_key = Column(UUID(as_uuid=True), nullable=False)
    approved_by_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())


class JobCostReview(Base):
    __tablename__ = "job_cost_reviews"
    __table_args__ = (UniqueConstraint("tenant_id", "order_id", "version", name="uq_job_cost_review_version"),
                     UniqueConstraint("tenant_id", "idempotency_key", name="uq_job_cost_review_key"),
                     CheckConstraint("version > 0", name="ck_job_cost_review_version"),
                     CheckConstraint("business_classification IN ('real','test','unknown')", name="ck_job_cost_classification"),
                     CheckConstraint("time_capture IN ('complete','incomplete','no_internal_labor')", name="ck_job_cost_time_capture"))
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False, index=True)
    order_id = Column(UUID(as_uuid=True), ForeignKey("repair_orders.id"), nullable=False, index=True)
    version = Column(Integer, nullable=False)
    supersedes_id = Column(UUID(as_uuid=True), ForeignKey("job_cost_reviews.id"), nullable=True, unique=True)
    business_classification = Column(String(16), nullable=False)
    approved_by_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    reason = Column(String(500), nullable=False)
    source_fingerprint = Column(String(64), nullable=False)
    policy_heads_digest = Column(String(64), nullable=False)
    calculation_version = Column(String(32), nullable=False)
    time_capture = Column(String(32), nullable=False)
    reviewed_exception_ids = Column(JSON, nullable=False)
    snapshot = Column(JSON, nullable=False)
    request_sha256 = Column(String(64), nullable=False)
    idempotency_key = Column(UUID(as_uuid=True), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())


def _immutable(*_):
    raise ValueError("A1 evidence is append-only")


for _model in (TechnicianCostPolicyRevision, JobCostReview):
    event.listen(_model, "before_update", _immutable)
    event.listen(_model, "before_delete", _immutable)
