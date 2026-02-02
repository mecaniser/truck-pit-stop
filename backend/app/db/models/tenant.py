from sqlalchemy import Column, String, Boolean, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import UUID
from app.db.base import BaseModel


class Tenant(BaseModel):
    __tablename__ = "tenants"
    
    name = Column(String(255), nullable=False, index=True)
    slug = Column(String(100), unique=True, nullable=False, index=True)
    address = Column(String(500), nullable=True)
    phone = Column(String(20), nullable=True)
    email = Column(String(255), nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    
    # Garage ownership
    owner_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True, index=True)
    owner = relationship("User", foreign_keys=[owner_id], post_update=True)
    
    # Stripe Connect
    stripe_account_id = Column(String(255), unique=True, nullable=True, index=True)
    stripe_onboarding_complete = Column(Boolean, default=False, nullable=False)


