"""Versioned price policy and immutable evidence, independent of rollout flags."""
import uuid
from sqlalchemy import BigInteger, Boolean, CheckConstraint, Column, DateTime, ForeignKey, ForeignKeyConstraint, Index, Integer, JSON, String, UniqueConstraint, func, text
from sqlalchemy.dialects.postgresql import UUID
from app.db.base import Base


class PartsPriceMatrix(Base):
    __tablename__ = 'parts_price_matrices'
    __table_args__ = (
        UniqueConstraint('tenant_id', 'id', name='uq_parts_price_matrices_tenant_id'),
        CheckConstraint('version >= 1 AND current_revision >= 1', name='ck_parts_matrix_version'),
        Index('uq_parts_matrix_active_name', 'tenant_id', func.lower(text('name')), unique=True, postgresql_where=text('archived_at IS NULL'), sqlite_where=text('archived_at IS NULL')),
    )
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey('tenants.id'), nullable=False)
    name = Column(String(120), nullable=False)
    current_revision = Column(Integer, nullable=False, default=1)
    version = Column(BigInteger, nullable=False, default=1, server_default='1')
    archived_at = Column(DateTime(timezone=True))
    archived_by = Column(UUID(as_uuid=True), ForeignKey('users.id'))
    created_by = Column(UUID(as_uuid=True), ForeignKey('users.id'), nullable=False)
    updated_by = Column(UUID(as_uuid=True), ForeignKey('users.id'), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())


class PartsPriceMatrixRevision(Base):
    __tablename__ = 'parts_price_matrix_revisions'
    __table_args__ = (
        UniqueConstraint('tenant_id', 'id', name='uq_parts_price_revisions_tenant_id'),
        UniqueConstraint('tenant_id', 'matrix_id', 'revision', name='uq_parts_price_revision_number'),
        ForeignKeyConstraint(['tenant_id', 'matrix_id'], ['parts_price_matrices.tenant_id', 'parts_price_matrices.id'], name='fk_parts_price_revision_matrix'),
    )
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey('tenants.id'), nullable=False)
    matrix_id = Column(UUID(as_uuid=True), nullable=False)
    revision = Column(Integer, nullable=False)
    name_snapshot = Column(String(120), nullable=False)
    bands = Column(JSON, nullable=False)
    created_by = Column(UUID(as_uuid=True), ForeignKey('users.id'), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())


class PartsPricingPolicy(Base):
    __tablename__ = 'parts_pricing_policies'
    __table_args__ = (
        CheckConstraint('generation >= 0', name='ck_parts_pricing_generation'),
        ForeignKeyConstraint(['tenant_id', 'default_matrix_id'], ['parts_price_matrices.tenant_id', 'parts_price_matrices.id'], name='fk_parts_pricing_policy_matrix'),
    )
    tenant_id = Column(UUID(as_uuid=True), ForeignKey('tenants.id'), primary_key=True)
    default_matrix_id = Column(UUID(as_uuid=True))
    generation = Column(BigInteger, nullable=False, default=0, server_default='0')
    updated_by = Column(UUID(as_uuid=True), ForeignKey('users.id'))
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())


class PartsPricingEvent(Base):
    __tablename__ = 'parts_pricing_events'
    __table_args__ = (
        *[ForeignKeyConstraint(['tenant_id', column], [table + '.tenant_id', table + '.id'], name='fk_pricing_event_' + column)
          for column, table in (('matrix_id', 'parts_price_matrices'), ('revision_id', 'parts_price_matrix_revisions'), ('inventory_id', 'inventory'), ('counter_sale_id', 'counter_sales'), ('counter_line_id', 'counter_sale_lines'))],
        Index('ix_parts_pricing_event_entity', 'tenant_id', 'entity_type', 'entity_id', 'created_at', 'id'),
        Index('ix_parts_pricing_event_tenant', 'tenant_id', 'created_at', 'id'),
    )
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey('tenants.id'), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    entity_type = Column(String(32), nullable=False)
    # Physically removable usage identity is historical evidence, never a live FK.
    entity_id = Column(UUID(as_uuid=True), nullable=False)
    event_type = Column(String(64), nullable=False)
    actor_id = Column(UUID(as_uuid=True), ForeignKey('users.id'), nullable=False)
    correlation_id = Column(UUID(as_uuid=True), nullable=False, default=uuid.uuid4)
    old_version = Column(BigInteger)
    new_version = Column(BigInteger)
    reason = Column(String(500))
    identity_snapshot = Column(JSON, nullable=False, default=dict)
    before_values = Column(JSON, nullable=False, default=dict)
    after_values = Column(JSON, nullable=False, default=dict)
    matrix_id = Column(UUID(as_uuid=True))
    revision_id = Column(UUID(as_uuid=True))
    inventory_id = Column(UUID(as_uuid=True))
    counter_sale_id = Column(UUID(as_uuid=True))
    counter_line_id = Column(UUID(as_uuid=True))
