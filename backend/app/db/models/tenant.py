from sqlalchemy import Column, String, Boolean
from app.db.base import BaseModel


class Tenant(BaseModel):
    __tablename__ = "tenants"
    
    name = Column(String(255), nullable=False, index=True)
    slug = Column(String(100), unique=True, nullable=False, index=True)
    address = Column(String(500), nullable=True)
    phone = Column(String(20), nullable=True)
    email = Column(String(255), nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)


