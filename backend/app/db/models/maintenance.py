"""DB134 recurring maintenance identity, claims and immutable evidence."""
from uuid import uuid4
from sqlalchemy import BigInteger, CheckConstraint, Column, Date, DateTime, ForeignKey, ForeignKeyConstraint, Index, Integer, JSON, Numeric, String, UniqueConstraint, func, text
from sqlalchemy.dialects.postgresql import UUID
from app.db.base import Base


class MaintenanceRow(Base):
    __abstract__ = True
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey('tenants.id'), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())


class MaintenanceProgram(MaintenanceRow):
    __tablename__ = 'maintenance_programs'
    __table_args__ = (
        UniqueConstraint('tenant_id', 'id', name='uq_maintenance_program_tenant'),
        ForeignKeyConstraint(['tenant_id', 'vehicle_id'], ['vehicles.tenant_id', 'vehicles.id'], name='fk_maintenance_program_vehicle'),
        ForeignKeyConstraint(['tenant_id', 'controlling_completion_id'], ['maintenance_completions.tenant_id', 'maintenance_completions.id'], name='fk_maintenance_program_completion', use_alter=True),
        CheckConstraint("mode IN ('independent','legacy')", name='ck_maintenance_program_mode'),
        CheckConstraint('version >= 1 AND current_cycle >= 1 AND baseline_generation >= 1', name='ck_maintenance_program_versions'),
        CheckConstraint('interval_days IS NULL OR interval_days BETWEEN 1 AND 36500', name='ck_maintenance_program_days'),
        CheckConstraint('interval_miles IS NULL OR interval_miles BETWEEN 1 AND 99999999', name='ck_maintenance_program_miles'),
        CheckConstraint('interval_hours IS NULL OR (interval_hours >= 0.01 AND interval_hours <= 10000000)', name='ck_maintenance_program_hours'),
        CheckConstraint("mode='legacy' OR interval_days IS NOT NULL OR interval_miles IS NOT NULL OR interval_hours IS NOT NULL", name='ck_maintenance_program_enabled'),
        CheckConstraint('target_miles IS NULL OR target_miles BETWEEN 0 AND 99999999', name='ck_maintenance_program_target_miles'),
        CheckConstraint('target_hours IS NULL OR (target_hours >= 0 AND target_hours <= 10000000)', name='ck_maintenance_program_target_hours'),
        Index('ix_maintenance_program_vehicle', 'tenant_id', 'vehicle_id', 'archived_at'),
        Index('uq_maintenance_program_legacy', 'tenant_id', 'vehicle_id', unique=True, postgresql_where=text("mode='legacy'"), sqlite_where=text("mode='legacy'")),
    )
    vehicle_id = Column(UUID(as_uuid=True), nullable=False)
    name = Column(String(120), nullable=False)
    version = Column(BigInteger, nullable=False, default=1)
    mode = Column(String(16), nullable=False, default='independent')
    interval_days = Column(Integer)
    interval_miles = Column(Integer)
    interval_hours = Column(Numeric(12, 2))
    target_due_on = Column(Date)
    target_miles = Column(Integer)
    target_hours = Column(Numeric(12, 2))
    target_provenance = Column(JSON, nullable=False)
    service_id = Column(UUID(as_uuid=True))  # historical catalog identity, never a restrictive FK
    service_snapshot = Column(JSON)
    legacy_package = Column(JSON)
    legacy_snapshot = Column(JSON)
    current_cycle = Column(BigInteger, nullable=False, default=1)
    baseline_generation = Column(BigInteger, nullable=False, default=1)
    baseline_snapshot = Column(JSON)
    controlling_completion_id = Column(UUID(as_uuid=True))
    review_codes = Column(JSON, nullable=False, default=list)
    archived_at = Column(DateTime(timezone=True))
    created_by = Column(UUID(as_uuid=True))  # migration has no invented actor
    updated_by = Column(UUID(as_uuid=True))
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())


class MaintenanceWorkLink(MaintenanceRow):
    __tablename__ = 'maintenance_work_links'
    __table_args__ = (
        UniqueConstraint('tenant_id', 'id', name='uq_maintenance_work_tenant'),
        ForeignKeyConstraint(['tenant_id', 'program_id'], ['maintenance_programs.tenant_id', 'maintenance_programs.id'], name='fk_maintenance_work_program'),
        ForeignKeyConstraint(['tenant_id', 'repair_order_id'], ['repair_orders.tenant_id', 'repair_orders.id'], name='fk_maintenance_work_order'),
        CheckConstraint("state IN ('active','pending_evidence','review_required','completed','detached')", name='ck_maintenance_work_state'),
        CheckConstraint('cycle >= 1 AND version >= 1 AND program_version >= 1', name='ck_maintenance_work_versions'),
        Index('uq_maintenance_work_claim', 'tenant_id', 'program_id', 'cycle', unique=True, postgresql_where=text("state IN ('active','pending_evidence','review_required')"), sqlite_where=text("state IN ('active','pending_evidence','review_required')")),
        Index('ix_maintenance_work_order', 'tenant_id', 'repair_order_id'),
    )
    program_id = Column(UUID(as_uuid=True), nullable=False)
    cycle = Column(BigInteger, nullable=False)
    repair_order_id = Column(UUID(as_uuid=True), nullable=False)
    program_version = Column(BigInteger, nullable=False)
    captured_config = Column(JSON, nullable=False)
    captured_targets = Column(JSON, nullable=False)
    state = Column(String(24), nullable=False, default='active')
    version = Column(BigInteger, nullable=False, default=1)
    restore_state = Column(JSON)
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())


class MaintenanceOperationLink(MaintenanceRow):
    __tablename__ = 'maintenance_operation_links'
    __table_args__ = (
        UniqueConstraint('tenant_id', 'id', name='uq_maintenance_operation_tenant'),
        UniqueConstraint('tenant_id', 'work_link_id', 'operation_id', name='uq_maintenance_operation_identity'),
        ForeignKeyConstraint(['tenant_id', 'work_link_id'], ['maintenance_work_links.tenant_id', 'maintenance_work_links.id'], name='fk_maintenance_operation_work'),
        CheckConstraint("state IN ('active','detached')", name='ck_maintenance_operation_state'),
        CheckConstraint('version >= 1', name='ck_maintenance_operation_version'),
        Index('ix_maintenance_operation_lookup', 'tenant_id', 'operation_id'),
    )
    work_link_id = Column(UUID(as_uuid=True), nullable=False)
    operation_id = Column(UUID(as_uuid=True), nullable=False)  # physical labor deletion retains this evidence
    identity_snapshot = Column(JSON, nullable=False)
    version = Column(BigInteger, nullable=False, default=1)
    state = Column(String(16), nullable=False, default='active')
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())


class MaintenanceProgramEvent(MaintenanceRow):
    __tablename__ = 'maintenance_program_events'
    __table_args__ = (
        UniqueConstraint('tenant_id', 'id', name='uq_maintenance_event_tenant'),
        UniqueConstraint('tenant_id', 'program_id', 'version', name='uq_maintenance_event_version'),
        ForeignKeyConstraint(['tenant_id', 'program_id'], ['maintenance_programs.tenant_id', 'maintenance_programs.id'], name='fk_maintenance_event_program'),
        CheckConstraint('version >= 1', name='ck_maintenance_event_version'),
    )
    program_id = Column(UUID(as_uuid=True), nullable=False)
    version = Column(BigInteger, nullable=False)
    action = Column(String(48), nullable=False)
    actor_id = Column(UUID(as_uuid=True))
    reason = Column(String(500))
    before_values = Column(JSON, nullable=False)
    after_values = Column(JSON, nullable=False)


class MaintenanceCompletion(MaintenanceRow):
    __tablename__ = 'maintenance_completions'
    __table_args__ = (
        UniqueConstraint('tenant_id', 'id', name='uq_maintenance_completion_tenant'),
        UniqueConstraint('tenant_id', 'program_id', 'recognition_key', name='uq_maintenance_completion_source'),
        ForeignKeyConstraint(['tenant_id', 'program_id'], ['maintenance_programs.tenant_id', 'maintenance_programs.id'], name='fk_maintenance_completion_program'),
        ForeignKeyConstraint(['tenant_id', 'work_link_id'], ['maintenance_work_links.tenant_id', 'maintenance_work_links.id'], name='fk_maintenance_completion_work'),
        ForeignKeyConstraint(['tenant_id', 'supersedes_id'], ['maintenance_completions.tenant_id', 'maintenance_completions.id'], name='fk_maintenance_completion_prior'),
        CheckConstraint("action IN ('finalize','pending','resolve_pending','recognize','reaffirm','supersede','revoke')", name='ck_maintenance_completion_action'),
        CheckConstraint("result IN ('advanced','pending_evidence','history_only','reaffirmed','revoked','review_required')", name='ck_maintenance_completion_result'),
        CheckConstraint("action NOT IN ('finalize','pending','resolve_pending') OR (work_link_id IS NOT NULL AND cycle IS NOT NULL AND cycle >= 1 AND source_kind='repair_order' AND source_id IS NOT NULL)", name='ck_maintenance_completion_work_identity'),
        CheckConstraint("action != 'recognize' OR (source_kind IN ('repair_order','external_service') AND source_id IS NOT NULL)", name='ck_maintenance_completion_recognition_identity'),
        Index('uq_maintenance_first_work_evidence', 'tenant_id', 'work_link_id', unique=True, postgresql_where=text("action IN ('finalize','pending')"), sqlite_where=text("action IN ('finalize','pending')")),
        Index('uq_maintenance_work_resolution', 'tenant_id', 'work_link_id', unique=True, postgresql_where=text("action='resolve_pending'"), sqlite_where=text("action='resolve_pending'")),
        Index('uq_maintenance_source_program', 'tenant_id', 'program_id', 'source_kind', 'source_id', unique=True, postgresql_where=text("action IN ('finalize','pending','recognize')"), sqlite_where=text("action IN ('finalize','pending','recognize')")),
        Index('ix_maintenance_completion_source', 'tenant_id', 'source_kind', 'source_id'),
    )
    program_id = Column(UUID(as_uuid=True), nullable=False)
    cycle = Column(BigInteger)
    work_link_id = Column(UUID(as_uuid=True))
    action = Column(String(24), nullable=False)
    result = Column(String(24), nullable=False)
    performed_on = Column(Date)
    readings = Column(JSON, nullable=False)
    source_kind = Column(String(24), nullable=False)
    source_id = Column(UUID(as_uuid=True))
    source_fingerprint = Column(String(64), nullable=False)
    source_snapshot = Column(JSON, nullable=False)
    configuration = Column(JSON, nullable=False)
    previous_targets = Column(JSON, nullable=False)
    next_targets = Column(JSON, nullable=False)
    supersedes_id = Column(UUID(as_uuid=True))
    recognition_key = Column(String(100))
    actor_id = Column(UUID(as_uuid=True), nullable=False)
    request_id = Column(UUID(as_uuid=True), nullable=False)
    request_fingerprint = Column(String(64), nullable=False)


class MaintenanceReading(MaintenanceRow):
    __tablename__ = 'maintenance_readings'
    __table_args__ = (
        UniqueConstraint('tenant_id', 'id', name='uq_maintenance_reading_tenant'),
        UniqueConstraint('tenant_id', 'request_id', name='uq_maintenance_reading_request'),
        ForeignKeyConstraint(['tenant_id', 'vehicle_id'], ['vehicles.tenant_id', 'vehicles.id'], name='fk_maintenance_reading_vehicle'),
        CheckConstraint('odometer_miles IS NOT NULL OR engine_hours IS NOT NULL', name='ck_maintenance_reading_present'),
        CheckConstraint('odometer_miles IS NULL OR odometer_miles BETWEEN 0 AND 99999999', name='ck_maintenance_reading_miles'),
        CheckConstraint('engine_hours IS NULL OR (engine_hours >= 0 AND engine_hours <= 10000000)', name='ck_maintenance_reading_hours'),
        CheckConstraint("source IN ('staff_observed','staff_reported')", name='ck_maintenance_reading_source'),
        Index('ix_maintenance_reading_vehicle', 'tenant_id', 'vehicle_id', 'observed_at'),
    )
    vehicle_id = Column(UUID(as_uuid=True), nullable=False)
    observed_at = Column(DateTime(timezone=True), nullable=False)
    odometer_miles = Column(Integer)
    engine_hours = Column(Numeric(12, 2))
    source = Column(String(24), nullable=False)
    note = Column(String(500))
    actor_id = Column(UUID(as_uuid=True), nullable=False)
    request_id = Column(UUID(as_uuid=True), nullable=False)
