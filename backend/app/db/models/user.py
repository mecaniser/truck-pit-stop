from sqlalchemy import Column, String, Boolean, ForeignKey, Enum as SQLEnum
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import UUID
import enum
from app.db.base import BaseModel


class UserRole(str, enum.Enum):
    SUPER_ADMIN = "super_admin"
    GARAGE_ADMIN = "garage_admin"
    MECHANIC = "mechanic"
    RECEPTIONIST = "receptionist"
    CUSTOMER = "customer"


class User(BaseModel):
    __tablename__ = "users"
    
    email = Column(String(255), unique=True, nullable=False, index=True)
    hashed_password = Column(String(255), nullable=False)
    full_name = Column(String(255), nullable=True)
    phone = Column(String(20), nullable=True)
    role = Column(SQLEnum(UserRole), nullable=False, default=UserRole.CUSTOMER)
    is_active = Column(Boolean, default=True, nullable=False)
    is_verified = Column(Boolean, default=False, nullable=False)
    
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=True, index=True)
    tenant = relationship("Tenant", backref="users")
    
    customer_id = Column(UUID(as_uuid=True), ForeignKey("customers.id"), nullable=True, unique=True)
    customer = relationship("Customer", backref="user", uselist=False)

