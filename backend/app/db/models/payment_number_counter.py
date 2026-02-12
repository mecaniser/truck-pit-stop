from sqlalchemy import Column, Integer, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import UUID

from app.db.base import BaseModel


class PaymentNumberCounter(BaseModel):
    __tablename__ = "payment_number_counters"

    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False, unique=True, index=True)
    tenant = relationship("Tenant", backref="payment_number_counter")

    last_number = Column(Integer, nullable=False, default=0)
