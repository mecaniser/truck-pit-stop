from sqlalchemy import Boolean, Column, String, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from app.db.base import BaseModel


class Supplier(BaseModel):
    __tablename__ = "suppliers"

    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False, index=True)
    tenant = relationship("Tenant", backref="suppliers")

    name = Column(String(255), nullable=False, index=True)
    normalized_name = Column(String(255), nullable=True, index=True)
    is_active = Column(Boolean, default=True, server_default="true", nullable=False)
    account_reference = Column(String(100), nullable=True)
    email = Column(String(255), nullable=True)
    address = Column(String(500), nullable=True)
    phone = Column(String(30), nullable=True)
    contact_name = Column(String(255), nullable=True)
    notes = Column(String(500), nullable=True)
