"""Strict owner-input schemas. No request accepts monetary outcomes."""
from datetime import datetime, timezone
from decimal import Decimal
import re
from typing import Literal
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field, StrictInt, field_validator


def utc(value: str) -> datetime:
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(?:\.\d{1,6})?(?:Z|\+00:00)", value):
        raise ValueError("UTC RFC3339 required")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return parsed.astimezone(timezone.utc)


class StrictBody(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class CostSegment(StrictBody):
    effective_from: str
    effective_to: str | None
    hourly_cost: str
    inclusions: str

    @field_validator("effective_from", "effective_to")
    @classmethod
    def timestamp(cls, value):
        if value is not None:
            utc(value)
        return value

    @field_validator("hourly_cost")
    @classmethod
    def rate(cls, value):
        if not re.fullmatch(r"(?:0|[1-9]\d{0,4})(?:\.\d{1,4})?", value) or not Decimal("0.0001") <= Decimal(value) <= Decimal("10000"):
            raise ValueError("Invalid loaded direct rate")
        return value

    @field_validator("inclusions")
    @classmethod
    def text(cls, value):
        value = value.strip()
        if not 1 <= len(value) <= 500:
            raise ValueError("Required text")
        return value


class RateRequest(StrictBody):
    expected_version: StrictInt = Field(ge=0)
    policy_version: StrictInt
    currency: Literal["USD"]
    basis: Literal["owner_declared_loaded_direct"]
    segments: list[CostSegment] = Field(max_length=100)
    reason: str

    @field_validator("policy_version")
    @classmethod
    def version(cls, value):
        if value != 1:
            raise ValueError("Unsupported policy")
        return value

    @field_validator("reason")
    @classmethod
    def reason_text(cls, value):
        return CostSegment.text(value)


class ReviewRequest(StrictBody):
    expected_version: StrictInt = Field(ge=0)
    source_fingerprint: str
    policy_heads_digest: str
    business_classification: Literal["real", "test", "unknown"]
    time_capture: Literal["complete", "incomplete", "no_internal_labor"]
    reviewed_exception_ids: list[str] = Field(max_length=500)
    reason: str

    @field_validator("source_fingerprint", "policy_heads_digest")
    @classmethod
    def digest(cls, value):
        if not re.fullmatch(r"[0-9a-f]{64}", value):
            raise ValueError("Invalid source identity")
        return value

    @field_validator("reviewed_exception_ids")
    @classmethod
    def ids(cls, values):
        if len(set(values)) != len(values) or any(str(UUID(value)) != value for value in values):
            raise ValueError("Invalid exception identities")
        return sorted(values)

    @field_validator("reason")
    @classmethod
    def reason_text(cls, value):
        return CostSegment.text(value)
