from sqlalchemy import Column, String, DateTime, ForeignKey, Text, Enum as SQLEnum, JSON, Boolean, Date, Integer
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import UUID
import enum

from app.db.base import BaseModel


class MechanicSessionType(str, enum.Enum):
    REPAIR_ORDER = "repair_order"
    MISC = "misc"


class MiscWorkCategory(str, enum.Enum):
    SHOP_CLEANUP = "shop_cleanup"
    PARTS_RUNNER = "parts_runner"
    ADMIN_PAPERWORK = "admin_paperwork"
    TRAINING = "training"
    SHOP_SUPPORT = "shop_support"
    OTHER = "other"


class MechanicTimeSession(BaseModel):
    __tablename__ = "mechanic_time_sessions"

    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False, index=True)
    tenant = relationship("Tenant", backref="mechanic_time_sessions")

    mechanic_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)
    mechanic = relationship("User", foreign_keys=[mechanic_id], backref="mechanic_time_sessions")

    repair_order_id = Column(UUID(as_uuid=True), ForeignKey("repair_orders.id"), nullable=True, index=True)
    repair_order = relationship("RepairOrder", foreign_keys=[repair_order_id])

    session_type = Column(
        SQLEnum(
            MechanicSessionType,
            values_callable=lambda e: [m.value for m in e],
            name="mechanic_session_type",
        ),
        nullable=False,
        index=True,
    )
    misc_category = Column(
        SQLEnum(
            MiscWorkCategory,
            values_callable=lambda e: [m.value for m in e],
            name="misc_work_category",
        ),
        nullable=True,
        index=True,
    )
    note = Column(Text, nullable=True)

    started_at = Column(DateTime(timezone=True), nullable=False, index=True)
    ended_at = Column(DateTime(timezone=True), nullable=True, index=True)

    started_by_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)
    started_by_user = relationship("User", foreign_keys=[started_by_user_id])

    stopped_by_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True, index=True)
    stopped_by_user = relationship("User", foreign_keys=[stopped_by_user_id])

    stop_reason = Column(String(50), nullable=True)


class MechanicTimeSessionAudit(BaseModel):
    __tablename__ = "mechanic_time_session_audit"

    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False, index=True)
    tenant = relationship("Tenant", backref="mechanic_time_session_audit")

    session_id = Column(UUID(as_uuid=True), ForeignKey("mechanic_time_sessions.id"), nullable=True, index=True)
    session = relationship("MechanicTimeSession", foreign_keys=[session_id], backref="audit_rows")

    mechanic_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)
    mechanic = relationship("User", foreign_keys=[mechanic_id])

    actor_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)
    actor_user = relationship("User", foreign_keys=[actor_user_id])

    actor_role = Column(String(32), nullable=False)
    action = Column(String(50), nullable=False, index=True)
    manager_reason = Column(Text, nullable=True)

    before_snapshot = Column(JSON, nullable=True)
    after_snapshot = Column(JSON, nullable=True)


class MechanicIdleAlertStreak(BaseModel):
    __tablename__ = "mechanic_idle_alert_streaks"

    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False, index=True)
    tenant = relationship("Tenant", backref="mechanic_idle_alert_streaks")

    mechanic_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)
    mechanic = relationship("User", foreign_keys=[mechanic_id], backref="mechanic_idle_alert_streaks")

    local_date = Column(Date, nullable=False, index=True)
    started_at = Column(DateTime(timezone=True), nullable=False)
    alert_sent_at = Column(DateTime(timezone=True), nullable=True)
    resolved_at = Column(DateTime(timezone=True), nullable=True)
    is_active = Column(Boolean, nullable=False, default=True, index=True)


class MechanicAttendanceSession(BaseModel):
    __tablename__ = "mechanic_attendance_sessions"

    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False, index=True)
    tenant = relationship("Tenant", backref="mechanic_attendance_sessions")

    mechanic_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)
    mechanic = relationship("User", foreign_keys=[mechanic_id], backref="mechanic_attendance_sessions")

    local_date = Column(Date, nullable=False, index=True)

    started_at = Column(DateTime(timezone=True), nullable=False, index=True)
    ended_at = Column(DateTime(timezone=True), nullable=True, index=True)

    started_by_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)
    started_by_user = relationship("User", foreign_keys=[started_by_user_id])

    ended_by_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True, index=True)
    ended_by_user = relationship("User", foreign_keys=[ended_by_user_id])

    start_source = Column(String(50), nullable=False, default="manual_clock_in")
    end_source = Column(String(50), nullable=True)
    note = Column(Text, nullable=True)

    snapshot_timezone = Column(String(64), nullable=False)
    snapshot_core_target_minutes = Column(Integer, nullable=False)
    snapshot_shift_start_local = Column(String(5), nullable=False)
    snapshot_shift_end_local = Column(String(5), nullable=False)


class MechanicBreakSession(BaseModel):
    __tablename__ = "mechanic_break_sessions"

    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False, index=True)
    tenant = relationship("Tenant", backref="mechanic_break_sessions")

    mechanic_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)
    mechanic = relationship("User", foreign_keys=[mechanic_id], backref="mechanic_break_sessions")

    attendance_session_id = Column(
        UUID(as_uuid=True),
        ForeignKey("mechanic_attendance_sessions.id"),
        nullable=False,
        index=True,
    )
    attendance_session = relationship(
        "MechanicAttendanceSession",
        foreign_keys=[attendance_session_id],
        backref="break_sessions",
    )

    started_at = Column(DateTime(timezone=True), nullable=False, index=True)
    ended_at = Column(DateTime(timezone=True), nullable=True, index=True)

    started_by_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)
    started_by_user = relationship("User", foreign_keys=[started_by_user_id])

    ended_by_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True, index=True)
    ended_by_user = relationship("User", foreign_keys=[ended_by_user_id])

    start_source = Column(String(50), nullable=False, default="manual_break_start")
    end_source = Column(String(50), nullable=True)
    note = Column(Text, nullable=True)


class MechanicAttendanceAudit(BaseModel):
    __tablename__ = "mechanic_attendance_audit"

    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False, index=True)
    tenant = relationship("Tenant", backref="mechanic_attendance_audit")

    attendance_session_id = Column(
        UUID(as_uuid=True),
        ForeignKey("mechanic_attendance_sessions.id"),
        nullable=True,
        index=True,
    )
    attendance_session = relationship("MechanicAttendanceSession", foreign_keys=[attendance_session_id], backref="audit_rows")

    break_session_id = Column(
        UUID(as_uuid=True),
        ForeignKey("mechanic_break_sessions.id"),
        nullable=True,
        index=True,
    )
    break_session = relationship("MechanicBreakSession", foreign_keys=[break_session_id], backref="audit_rows")

    mechanic_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)
    mechanic = relationship("User", foreign_keys=[mechanic_id])

    actor_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)
    actor_user = relationship("User", foreign_keys=[actor_user_id])

    actor_role = Column(String(32), nullable=False)
    action = Column(String(50), nullable=False, index=True)
    manager_reason = Column(Text, nullable=True)

    before_snapshot = Column(JSON, nullable=True)
    after_snapshot = Column(JSON, nullable=True)
