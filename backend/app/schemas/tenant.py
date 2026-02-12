from pydantic import BaseModel, Field, field_validator
from uuid import UUID
from datetime import datetime
from typing import Optional


class TenantBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=255, description="Garage/shop name")
    slug: str = Field(..., min_length=1, max_length=100, description="URL-friendly identifier")
    address: Optional[str] = Field(None, max_length=500)
    phone: Optional[str] = Field(None, max_length=20)
    email: Optional[str] = Field(None, max_length=255)
    sms_phone_number: Optional[str] = Field(None, max_length=20)
    sms_phone_sid: Optional[str] = Field(None, max_length=64)
    sms_enabled: bool = False
    sms_messaging_service_sid: Optional[str] = Field(None, max_length=64)
    
    @field_validator('slug')
    @classmethod
    def validate_slug(cls, v: str) -> str:
        """Ensure slug is lowercase and URL-friendly"""
        import re
        if not re.match(r'^[a-z0-9-]+$', v):
            raise ValueError('Slug must contain only lowercase letters, numbers, and hyphens')
        return v


class TenantCreate(TenantBase):
    """Schema for creating a new tenant (garage)"""
    owner_email: str = Field(..., description="Email for the garage owner account")
    owner_first_name: str = Field(..., min_length=1, max_length=100)
    owner_last_name: str = Field(..., min_length=1, max_length=100)
    owner_phone: Optional[str] = Field(None, max_length=20)
    owner_password: str = Field(..., min_length=8, description="Password for owner account")


class TenantUpdate(BaseModel):
    """Schema for updating tenant information"""
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    address: Optional[str] = Field(None, max_length=500)
    phone: Optional[str] = Field(None, max_length=20)
    email: Optional[str] = Field(None, max_length=255)
    is_active: Optional[bool] = None
    stripe_account_id: Optional[str] = None
    stripe_onboarding_complete: Optional[bool] = None
    sms_phone_number: Optional[str] = Field(None, max_length=20)
    sms_phone_sid: Optional[str] = Field(None, max_length=64)
    sms_enabled: Optional[bool] = None
    sms_messaging_service_sid: Optional[str] = Field(None, max_length=64)


class TenantResponse(TenantBase):
    """Schema for tenant response"""
    id: UUID
    is_active: bool
    owner_id: Optional[UUID] = None
    stripe_account_id: Optional[str] = None
    stripe_onboarding_complete: bool
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True


class TenantWithOwnerResponse(TenantResponse):
    """Extended tenant response with owner information"""
    owner_email: Optional[str] = None
    owner_name: Optional[str] = None
    owner_phone: Optional[str] = None
