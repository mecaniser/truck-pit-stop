from sqlalchemy import Column, String, Text, ForeignKey, Boolean
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import UUID
from app.db.base import BaseModel


class Contact(BaseModel):
    """A named person associated with a Customer (company). A customer can have
    multiple contacts (e.g. dispatcher, owner, driver); exactly one may be flagged
    is_primary to drive default invoice/notification recipient behavior."""

    __tablename__ = "contacts"

    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False, index=True)
    tenant = relationship("Tenant", backref="contacts")

    customer_id = Column(UUID(as_uuid=True), ForeignKey("customers.id"), nullable=False, index=True)
    customer = relationship("Customer", back_populates="contacts")

    first_name = Column(String(100), nullable=True)
    last_name = Column(String(100), nullable=True)
    role = Column(String(100), nullable=True)  # e.g. "Owner", "Dispatcher", free text
    email = Column(String(255), nullable=True, index=True)
    phone = Column(String(20), nullable=True)
    notes = Column(Text, nullable=True)

    is_primary = Column(Boolean, nullable=False, default=False, index=True)
    source = Column(String(50), nullable=True, index=True)  # e.g. easy_truck_shop_import
