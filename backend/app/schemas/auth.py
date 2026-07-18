from pydantic import BaseModel, EmailStr, field_serializer
from typing import Dict, Optional, List
from uuid import UUID
from app.db.models.user import UserRole


class ShopOption(BaseModel):
    id: str
    name: str
    slug: str
    logo_url: Optional[str] = None


class Token(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    requires_shop_selection: bool = False
    shops: Optional[List[ShopOption]] = None


class SelectTenantRequest(BaseModel):
    tenant_id: UUID


class TokenData(BaseModel):
    user_id: Optional[str] = None


class UserLogin(BaseModel):
    email: EmailStr
    password: str
    remember_me: bool = False


class UserRegister(BaseModel):
    email: EmailStr
    password: str
    first_name: str
    last_name: str
    phone: Optional[str] = None
    garage_name: Optional[str] = None
    tenant_slug: Optional[str] = None  # For customer registration


class UserResponse(BaseModel):
    id: UUID
    email: str
    first_name: str
    last_name: str
    phone: Optional[str]
    address: Optional[str] = None
    role: UserRole
    is_active: bool
    can_access_messaging: bool = False
    # Settings grants for garage admins (payments/taxes_fees/workforce)
    permissions: Dict[str, bool] = {}
    # Shop-wide switch for the Messages feature; defaults on. The frontend ANDs
    # this with role/grant access to decide whether to show Messaging.
    messaging_enabled: bool = True
    tenant_id: Optional[UUID] = None
    tenant_name: Optional[str] = None
    tenant_slug: Optional[str] = None
    tenant_logo_url: Optional[str] = None
    customer_id: Optional[UUID] = None
    core_hours_target_minutes_override: Optional[int] = None
    shift_start_local_override: Optional[str] = None
    shift_end_local_override: Optional[str] = None

    model_config = {"from_attributes": True}

    @field_serializer('id', 'tenant_id', 'customer_id')
    def serialize_uuid(self, v: Optional[UUID]) -> Optional[str]:
        return str(v) if v else None

    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}"


class TenantBrandingResponse(BaseModel):
    name: Optional[str] = None
    slug: Optional[str] = None
    logo_url: Optional[str] = None


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ForgotPasswordResponse(BaseModel):
    message: str


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str


class ResetPasswordResponse(BaseModel):
    message: str
