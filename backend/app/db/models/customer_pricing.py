"""Append-only account and labor pricing evidence; historical identities survive removal."""
import uuid
from sqlalchemy import BigInteger, CheckConstraint, Column, DateTime, ForeignKey, ForeignKeyConstraint, Index, JSON, String, func
from sqlalchemy.dialects.postgresql import UUID
from app.db.base import Base


class AccountPricingEvent(Base):
    __tablename__ = 'account_pricing_events'
    __table_args__ = (
        CheckConstraint("entity_type IN ('customer_policy','labor','counter_policy')", name='ck_account_pricing_entity'),
        ForeignKeyConstraint(['tenant_id','matrix_id'], ['parts_price_matrices.tenant_id','parts_price_matrices.id'], name='fk_account_event_matrix'),
        ForeignKeyConstraint(['tenant_id','revision_id'], ['parts_price_matrix_revisions.tenant_id','parts_price_matrix_revisions.id'], name='fk_account_event_revision'),
        Index('ix_account_pricing_event_entity','tenant_id','entity_type','entity_id','new_version','id'),
        Index('ix_account_pricing_event_customer','tenant_id','customer_id'),
    )
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey('tenants.id'), nullable=False)
    entity_type = Column(String(32), nullable=False)
    entity_id = Column(UUID(as_uuid=True), nullable=False)
    customer_id = Column(UUID(as_uuid=True))
    customer_name = Column(String(255))
    repair_order_id = Column(UUID(as_uuid=True))
    counter_sale_id = Column(UUID(as_uuid=True))
    actor_id = Column(UUID(as_uuid=True), nullable=False)
    actor_name = Column(String(255))
    actor_role = Column(String(32), nullable=False)
    correlation_id = Column(UUID(as_uuid=True), nullable=False, default=uuid.uuid4)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    old_version = Column(BigInteger)
    new_version = Column(BigInteger)
    reason = Column(String(500))
    before_values = Column(JSON, nullable=False, default=dict)
    after_values = Column(JSON, nullable=False, default=dict)
    matrix_id = Column(UUID(as_uuid=True))
    revision_id = Column(UUID(as_uuid=True))
