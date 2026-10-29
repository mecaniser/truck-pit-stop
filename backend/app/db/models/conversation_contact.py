"""CRM context is deliberately separate from immutable messaging transport identity."""
from sqlalchemy import Column, ForeignKey, Integer, String, JSON, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from app.db.base import BaseModel


class ConversationContactLink(BaseModel):
    __tablename__ = 'conversation_contact_links'
    __table_args__ = (UniqueConstraint('tenant_id', 'thread_id'),)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey('tenants.id'), nullable=False)
    thread_id = Column(UUID(as_uuid=True), ForeignKey('message_threads.id'), nullable=False)
    customer_id = Column(UUID(as_uuid=True), ForeignKey('customers.id'), nullable=False)
    contact_id = Column(UUID(as_uuid=True), ForeignKey('contacts.id'), nullable=False)
    actor_id = Column(UUID(as_uuid=True), ForeignKey('users.id'), nullable=False)
    version = Column(Integer, nullable=False, default=1)


class ContactRepairLink(BaseModel):
    __tablename__ = 'contact_repair_links'
    __table_args__ = (UniqueConstraint('tenant_id', 'contact_id', 'repair_order_id'),)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey('tenants.id'), nullable=False)
    contact_id = Column(UUID(as_uuid=True), ForeignKey('contacts.id'), nullable=False)
    repair_order_id = Column(UUID(as_uuid=True), ForeignKey('repair_orders.id'), nullable=False)
    actor_id = Column(UUID(as_uuid=True), ForeignKey('users.id'), nullable=False)


class ConversationContextMutation(BaseModel):
    __tablename__ = 'conversation_context_mutations'
    __table_args__ = (UniqueConstraint('tenant_id', 'actor_id', 'idempotency_key'),)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey('tenants.id'), nullable=False)
    actor_id = Column(UUID(as_uuid=True), ForeignKey('users.id'), nullable=False)
    thread_id = Column(UUID(as_uuid=True), ForeignKey('message_threads.id'), nullable=False)
    idempotency_key = Column(UUID(as_uuid=True), nullable=False)
    operation = Column(String(200), nullable=False)
    payload_hash = Column(String(64), nullable=False)
    result = Column(JSON, nullable=False)
    previous_target = Column(JSON, nullable=True)
