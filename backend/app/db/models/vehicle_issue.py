"""Standalone truck follow-up metadata. Never an order or financial record."""

from sqlalchemy import (
    Column,
    String,
    Text,
    Integer,
    Date,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    UniqueConstraint,
    CheckConstraint,
    Index,
    JSON,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from app.db.base import BaseModel


class VehicleIssue(BaseModel):
    __tablename__ = "vehicle_issues"
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False)
    vehicle_id = Column(UUID(as_uuid=True), nullable=False)
    description = Column(Text, nullable=False)
    priority = Column(String(16), nullable=False, default="soon", server_default="soon")
    state = Column(String(16), nullable=False, default="open", server_default="open")
    responsible_user_id = Column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT")
    )
    follow_up_on = Column(Date)
    state_reason = Column(String(1000))
    state_changed_at = Column(DateTime(timezone=True))
    state_changed_by = Column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT")
    )
    created_by = Column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    version = Column(Integer, nullable=False, default=1, server_default="1")
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_vehicle_issues_tenant_id"),
        UniqueConstraint(
            "tenant_id", "vehicle_id", "id", name="uq_vehicle_issues_vehicle_id"
        ),
        ForeignKeyConstraint(
            ["tenant_id", "vehicle_id"],
            ["vehicles.tenant_id", "vehicles.id"],
            name="fk_vehicle_issues_vehicle",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "priority IN ('urgent','soon','monitor')", name="ck_vehicle_issues_priority"
        ),
        CheckConstraint(
            "state IN ('open','resolved','dismissed')", name="ck_vehicle_issues_state"
        ),
        CheckConstraint("version >= 1", name="ck_vehicle_issues_version"),
        CheckConstraint(
            "length(trim(description)) BETWEEN 1 AND 2000",
            name="ck_vehicle_issues_description",
        ),
        Index(
            "ix_vehicle_issues_queue",
            "tenant_id",
            "vehicle_id",
            "state",
            "priority",
            "follow_up_on",
            "created_at",
            "id",
        ),
    )


class VehicleIssueLink(BaseModel):
    __tablename__ = "vehicle_issue_links"
    tenant_id = Column(UUID(as_uuid=True), nullable=False)
    vehicle_id = Column(UUID(as_uuid=True), nullable=False)
    issue_id = Column(UUID(as_uuid=True), nullable=False)
    target_order_id = Column(UUID(as_uuid=True), nullable=False)
    order_number = Column(String(50), nullable=False)
    created_by = Column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    ended_at = Column(DateTime(timezone=True))
    ended_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"))
    end_reason = Column(String(1000))
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "issue_id", "id", name="uq_vehicle_issue_links_identity"
        ),
        ForeignKeyConstraint(
            ["tenant_id", "vehicle_id", "issue_id"],
            [
                "vehicle_issues.tenant_id",
                "vehicle_issues.vehicle_id",
                "vehicle_issues.id",
            ],
            name="fk_vehicle_issue_links_issue",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "target_order_id"],
            ["repair_orders.tenant_id", "repair_orders.id"],
            name="fk_vehicle_issue_links_order",
            ondelete="RESTRICT",
        ),
        Index(
            "uq_vehicle_issue_current_link",
            "tenant_id",
            "issue_id",
            unique=True,
            postgresql_where=text("ended_at IS NULL"),
            sqlite_where=text("ended_at IS NULL"),
        ),
    )


class VehicleIssueRequest(BaseModel):
    __tablename__ = "vehicle_issue_requests"
    tenant_id = Column(UUID(as_uuid=True), nullable=False)
    request_id = Column(UUID(as_uuid=True), nullable=False)
    actor_id = Column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    operation = Column(String(20), nullable=False)
    payload_hash = Column(String(64), nullable=False)
    issue_id = Column(UUID(as_uuid=True), nullable=False)
    link_id = Column(UUID(as_uuid=True))
    accepted_version = Column(Integer, nullable=False)
    __table_args__ = (
        UniqueConstraint("tenant_id", "request_id", name="uq_vehicle_issue_request"),
        ForeignKeyConstraint(
            ["tenant_id", "issue_id"],
            ["vehicle_issues.tenant_id", "vehicle_issues.id"],
            name="fk_vehicle_issue_request_issue",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "issue_id", "link_id"],
            [
                "vehicle_issue_links.tenant_id",
                "vehicle_issue_links.issue_id",
                "vehicle_issue_links.id",
            ],
            name="fk_vehicle_issue_request_link",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "accepted_version >= 1", name="ck_vehicle_issue_request_version"
        ),
    )


class VehicleIssueEvent(BaseModel):
    __tablename__ = "vehicle_issue_events"
    tenant_id = Column(UUID(as_uuid=True), nullable=False)
    issue_id = Column(UUID(as_uuid=True), nullable=False)
    actor_id = Column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    operation = Column(String(20), nullable=False)
    version = Column(Integer, nullable=False)
    changes = Column(JSON, nullable=False)
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "issue_id"],
            ["vehicle_issues.tenant_id", "vehicle_issues.id"],
            name="fk_vehicle_issue_event_issue",
            ondelete="RESTRICT",
        ),
        UniqueConstraint(
            "tenant_id", "issue_id", "version", name="uq_vehicle_issue_event_version"
        ),
        CheckConstraint("version >= 1", name="ck_vehicle_issue_event_version"),
    )
