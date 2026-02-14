from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field


class MessageCustomerSummary(BaseModel):
    id: UUID
    first_name: str
    last_name: str
    email: str
    phone: Optional[str] = None
    sms_opt_out: bool = False

    class Config:
        from_attributes = True


class MessageThreadResponse(BaseModel):
    id: UUID
    tenant_id: UUID
    customer_id: UUID
    customer_phone: Optional[str] = None
    unread_count_staff: int
    last_message_at: Optional[datetime] = None
    last_message_preview: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    customer: MessageCustomerSummary

    class Config:
        from_attributes = True


class SMSMessageResponse(BaseModel):
    id: UUID
    tenant_id: UUID
    thread_id: UUID
    customer_id: UUID
    created_by_user_id: Optional[UUID] = None
    direction: str
    source: str
    body: str
    from_number: Optional[str] = None
    to_number: Optional[str] = None
    twilio_message_sid: Optional[str] = None
    delivery_status: str
    error_code: Optional[str] = None
    error_message: Optional[str] = None
    sent_at: Optional[datetime] = None
    delivered_at: Optional[datetime] = None
    failed_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class SendSMSRequest(BaseModel):
    customer_id: UUID
    body: str = Field(..., min_length=1, max_length=1600)
    thread_id: Optional[UUID] = None


class StartThreadRequest(BaseModel):
    customer_id: UUID
    body: str = Field(..., min_length=1, max_length=1600)


class CursorPageMessageThreads(BaseModel):
    items: list[MessageThreadResponse]
    next_cursor: Optional[str] = None
    has_more: bool = False


class CursorPageSMSMessages(BaseModel):
    items: list[SMSMessageResponse]
    next_cursor: Optional[str] = None
    has_more: bool = False


class UnreadSMSCountResponse(BaseModel):
    unread_count_staff: int = 0
