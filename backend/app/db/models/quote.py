from sqlalchemy import Column, DateTime, ForeignKey, Numeric, Text, Boolean, String, Integer, UniqueConstraint
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import UUID, JSONB
from decimal import Decimal
from app.db.base import BaseModel


class Quote(BaseModel):
    __tablename__ = "quotes"
    __table_args__ = (
        UniqueConstraint("repair_order_id", "revision", name="uq_quotes_repair_order_revision"),
    )
    
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False, index=True)
    tenant = relationship("Tenant", backref="quotes")
    
    repair_order_id = Column(UUID(as_uuid=True), ForeignKey("repair_orders.id"), nullable=False, index=True)
    repair_order = relationship("RepairOrder", back_populates="quotes")
    
    quote_number = Column(String(50), unique=True, nullable=False, index=True)
    total_amount = Column(Numeric(10, 2), nullable=False)
    notes = Column(Text, nullable=True)
    expires_at = Column(DateTime(timezone=True), nullable=True)
    is_approved = Column(Boolean, default=False, nullable=False)
    is_declined = Column(Boolean, default=False, nullable=False)
    decline_notes = Column(Text, nullable=True)
    sent_to_customer = Column(Boolean, default=False, nullable=False)
    sent_at = Column(DateTime(timezone=True), nullable=True)
    sent_by_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    sent_by_user = relationship("User", foreign_keys=[sent_by_user_id])

    # Magic link token for customer approval without login
    approval_token = Column(String(64), unique=True, nullable=True, index=True)

    # An estimate is an immutable authorization snapshot once it is sent.
    # Revision 1 is the initial estimate; later revisions authorize only the
    # positive delta without invalidating earlier customer decisions.
    revision = Column(Integer, nullable=False, default=1)
    authorization_type = Column(String(32), nullable=False, default="initial_estimate")
    previously_authorized_amount = Column(Numeric(10, 2), nullable=False, default=Decimal("0.00"))
    delta_amount = Column(Numeric(10, 2), nullable=False, default=Decimal("0.00"))
    line_items_snapshot = Column(JSONB, nullable=True)
    decision_at = Column(DateTime(timezone=True), nullable=True)
