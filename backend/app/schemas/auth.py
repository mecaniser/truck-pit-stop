from pydantic import BaseModel, EmailStr
from typing import Optional
from app.db.models.user import UserRole


class Token(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class TokenData(BaseModel):
    user_id: Optional[str] = None


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class UserRegister(BaseModel):
    email: EmailStr
    password: str
    full_name: Optional[str] = None
    phone: Optional[str] = None
    tenant_slug: Optional[str] = None  # For customer registration


class UserResponse(BaseModel):
    id: str
    email: str
    full_name: Optional[str]
    phone: Optional[str]
    role: UserRole
    is_active: bool
    tenant_id: Optional[str]
    customer_id: Optional[str]
    
    class Config:
        from_attributes = True

