from datetime import datetime, timezone
from ipaddress import ip_address
from typing import Literal
from urllib.parse import urlparse
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field, field_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)


class SMSOnboardingUpdate(StrictModel):
    expected_version: int = Field(ge=0)
    legal_name: str | None = Field(None, max_length=255)
    trade_name: str | None = Field(None, max_length=255)
    website_url: str | None = Field(None, max_length=2048)
    support_email: str | None = Field(None, max_length=255)
    support_phone: str | None = Field(None, pattern=r'^\+[1-9]\d{7,14}$')
    consent_source_url: str | None = Field(None, max_length=2048)
    privacy_url: str | None = Field(None, max_length=2048)
    terms_url: str | None = Field(None, max_length=2048)
    representative_name: str | None = Field(None, max_length=255)
    representative_email: str | None = Field(None, max_length=255)
    message_description: str | None = Field(None, max_length=4000)
    sample_messages: list[str] | None = Field(None, max_length=5)

    @field_validator('website_url', 'consent_source_url', 'privacy_url', 'terms_url')
    @classmethod
    def public_https(cls, value):
        if value is None:
            return value
        parsed = urlparse(value)
        host = parsed.hostname or ''
        if parsed.scheme != 'https' or not host or '.' not in host or parsed.username or parsed.password or parsed.port not in (None,443) or host.endswith(('.localhost','.local','.internal')):
            raise ValueError('A public HTTPS URL is required')
        try:
            ip_address(host)
        except ValueError:
            pass
        else:
            raise ValueError('Use a public website hostname')
        return value

    @field_validator('support_email', 'representative_email')
    @classmethod
    def email(cls, value):
        if value is not None and (value.count('@') != 1 or '.' not in value.rsplit('@',1)[-1] or any(c.isspace() for c in value)):
            raise ValueError('Invalid email')
        return value

    @field_validator('sample_messages')
    @classmethod
    def samples(cls, value):
        if value is not None and any(not s.strip() or len(s)>1600 for s in value):
            raise ValueError('Samples must contain 1-1600 characters')
        return [s.strip() for s in value] if value is not None else None


class SMSReviewRequest(StrictModel):
    expected_version: int = Field(ge=1)


class SMSConnectionSummary(StrictModel):
    status: str
    sender_last4: str | None = None
    registration_status: str | None = None
    verified_at: datetime | None = None


class SMSOnboardingResponse(StrictModel):
    version: int
    status: str
    submission_enabled: Literal[False] = False
    fields: dict
    blockers: list[str]
    connection: SMSConnectionSummary
    rejection_reason: str | None = None


class SMSConsentCreate(StrictModel):
    customer_id: UUID
    status: Literal['granted','withdrawn']
    source: str = Field(min_length=1,max_length=80)
    disclosure_version: str = Field(min_length=1,max_length=80)
    collected_at: datetime

    @field_validator('collected_at')
    @classmethod
    def valid_collection(cls, value):
        if value.tzinfo is None or value > datetime.now(timezone.utc):
            raise ValueError('Collection must be a timezone-aware time in the past')
        return value


class SMSConsentResponse(StrictModel):
    id: UUID
    customer_id: UUID
    phone_last4: str
    purpose: str
    status: str
    source: str
    disclosure_version: str
    collected_at: datetime
    created_at: datetime
