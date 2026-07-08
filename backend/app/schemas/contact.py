from pydantic import BaseModel
from typing import Optional
from datetime import datetime
from uuid import UUID


class ContactBase(BaseModel):
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    role: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    notes: Optional[str] = None
    is_primary: bool = False


class ContactCreate(ContactBase):
    pass


class ContactUpdate(BaseModel):
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    role: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    notes: Optional[str] = None
    is_primary: Optional[bool] = None


class ContactResponse(ContactBase):
    id: UUID
    tenant_id: UUID
    customer_id: UUID
    source: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
