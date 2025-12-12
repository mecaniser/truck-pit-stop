from pydantic import BaseModel, EmailStr, field_serializer
from typing import Optional
from uuid import UUID
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
    first_name: str
    last_name: str
    phone: Optional[str] = None
    tenant_slug: Optional[str] = None  # For customer registration


class UserResponse(BaseModel):
    id: UUID
    email: str
    first_name: str
    last_name: str
    phone: Optional[str]
    role: UserRole
    is_active: bool
    tenant_id: Optional[UUID] = None
    customer_id: Optional[UUID] = None
    
    model_config = {"from_attributes": True}
    
    @field_serializer('id', 'tenant_id', 'customer_id')
    def serialize_uuid(self, v: Optional[UUID]) -> Optional[str]:
        return str(v) if v else None
    
    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}"


