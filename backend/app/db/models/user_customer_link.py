from sqlalchemy import Column, ForeignKey, UniqueConstraint
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import UUID
from app.db.base import BaseModel


class UserCustomerLink(BaseModel):
    """Links a global User identity to a tenant-scoped Customer profile.

    One row per (user, tenant) pair. A customer using the same email at
    multiple shops gets one User row and one UserCustomerLink per shop.
    """

    __tablename__ = "user_customer_links"

    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)
    customer_id = Column(UUID(as_uuid=True), ForeignKey("customers.id"), nullable=False, index=True)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False, index=True)

    user = relationship("User", backref="customer_links")
    customer = relationship("Customer", backref="user_link", uselist=False)
    tenant = relationship("Tenant", backref="customer_links")

    __table_args__ = (
        UniqueConstraint("user_id", "tenant_id", name="uq_user_customer_link_user_tenant"),
    )
