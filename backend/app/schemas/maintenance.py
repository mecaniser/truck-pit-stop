"""Strict DB134 commands. Monetary/actor/source facts are always server-owned."""
from datetime import date, datetime
from decimal import Decimal
import re
from typing import Annotated, Literal, Union
from uuid import UUID
from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, StrictBool, StrictInt, field_validator, model_validator


def decimal_string(value, *, maximum=Decimal("10000000")):
    if not isinstance(value, str) or not re.fullmatch(r'(0|[1-9]\d*)(\.\d{1,2})?', value):
        raise ValueError('Use a non-negative plain decimal string with at most two decimal places')
    parsed = Decimal(value)
    if parsed > maximum:
        raise ValueError('Reading exceeds supported range')
    return value


def date_string(value):
    if not isinstance(value, str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}', value):
        raise ValueError('Use an ISO calendar date')
    return value


def instant_string(value):
    if not isinstance(value, str):
        raise ValueError('Use a timezone-bearing timestamp')
    parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError('Timestamp must have an offset')
    return value


Hours = Annotated[str, BeforeValidator(decimal_string)]
Miles = Annotated[StrictInt, Field(ge=0, le=99999999)]
Version = Annotated[StrictInt, Field(ge=1)]
DateOnly = Annotated[date, BeforeValidator(date_string)]
Instant = Annotated[datetime, BeforeValidator(instant_string)]
Channel = Literal['shop', 'fleet']
Meter = Literal['odometer_miles', 'engine_hours']
Reason = Annotated[str, Field(min_length=3, max_length=500)]


class Input(BaseModel):
    model_config = ConfigDict(extra='forbid')

    @field_validator('name', 'reason', 'note', 'description', check_fields=False, mode='before')
    @classmethod
    def strip_text(cls, value):
        return value.strip() if isinstance(value, str) else value


class Intervals(Input):
    days: Annotated[StrictInt, Field(ge=1, le=36500)] | None
    miles: Annotated[StrictInt, Field(ge=1, le=99999999)] | None
    engine_hours: Hours | None

    @field_validator('engine_hours')
    @classmethod
    def positive_hours(cls, value):
        if value is not None and Decimal(value) <= 0:
            raise ValueError('Interval must be positive')
        return value


class Targets(Input):
    due_on: DateOnly | None
    odometer_miles: Miles | None
    engine_hours: Hours | None


class ProgramRef(Input):
    program_id: UUID
    expected_version: Version


class Config(Input):
    name: str = Field(min_length=1, max_length=120)
    intervals: Intervals
    service_id: UUID | None


class ManualServiceReading(Input):
    kind: Literal['manual']
    value: Annotated[str, BeforeValidator(lambda value: decimal_string(value, maximum=Decimal("99999999")))]
    basis: Literal['staff_observed', 'staff_reported']
    note: str | None = Field(max_length=500)


class SelectedServiceReading(Input):
    kind: Literal['source']
    meter: Meter
    source_kind: Literal['telemetry', 'maintenance_reading', 'repair_order', 'external_service']
    source_id: str = Field(min_length=1, max_length=200)


ReadingInput = Annotated[Union[ManualServiceReading, SelectedServiceReading], Field(discriminator='kind')]


class ServiceReadings(Input):
    odometer_miles: ReadingInput | None
    engine_hours: ReadingInput | None


class Attestation(Input):
    performed_on: DateOnly
    readings: ServiceReadings
    confirm_actual_service_readings: StrictBool

    @field_validator('confirm_actual_service_readings')
    @classmethod
    def explicitly_confirmed(cls, value):
        if value is not True:
            raise ValueError('Confirm actual service readings')
        return value


class ExplicitSeed(Input):
    kind: Literal['explicit']
    targets: Targets


class BaselineSeed(Input):
    kind: Literal['baseline']
    attestation: Attestation


TargetSeed = Annotated[Union[ExplicitSeed, BaselineSeed], Field(discriminator='kind')]


class PreserveTargets(Input):
    kind: Literal['preserve']


class ReplaceTargets(Input):
    kind: Literal['replace', 'recalculate', 'rebaseline', 'convert_legacy']
    seed: TargetSeed
    expected_target_fingerprint: str = Field(min_length=1, max_length=200)
    reason: Reason | None


TargetChange = Annotated[Union[PreserveTargets, ReplaceTargets], Field(discriminator='kind')]


class ProgramCreate(Input):
    channel: Channel
    config: Config
    targets: TargetChange


class ProgramUpdate(ProgramCreate):
    expected_version: Version


class ArchiveCommand(Input):
    channel: Channel
    expected_version: Version


class ReadingCreate(Input):
    channel: Channel
    observed_at: Instant
    odometer_miles: Miles | None
    engine_hours: Hours | None
    source: Literal['staff_observed', 'staff_reported']
    note: str | None = Field(max_length=500)

    @model_validator(mode='after')
    def reading_present(self):
        if self.odometer_miles is None and self.engine_hours is None:
            raise ValueError('Provide at least one actual reading')
        return self


class CompletionEntry(Input):
    work_link_id: UUID
    expected_link_version: Version
    program: ProgramRef
    attestation: Attestation | None


class MaintenanceReview(Input):
    request_id: UUID
    expected_review_fingerprint: str = Field(min_length=1, max_length=200)
    expected_target_fingerprint: str = Field(min_length=1, max_length=200)
    entries: list[CompletionEntry] = Field(min_length=1, max_length=30)


class SourceRef(Input):
    kind: Literal['repair_order', 'external_service']
    id: UUID


class ResolvePending(Input):
    action: Literal['resolve_pending']
    work_link_id: UUID
    expected_link_version: Version
    attestation: Attestation


class Recognize(Input):
    action: Literal['recognize']
    source: SourceRef
    attestation: Attestation


class CorrectEvidence(Input):
    action: Literal['reaffirm', 'revoke']
    completion_id: UUID
    reason: Reason
    acknowledged_work_link_ids: list[UUID] = Field(max_length=100)


class SupersedeEvidence(Input):
    action: Literal['supersede']
    completion_id: UUID
    attestation: Attestation
    reason: Reason
    acknowledged_work_link_ids: list[UUID] = Field(max_length=100)


EvidenceIntent = Annotated[Union[ResolvePending, Recognize, CorrectEvidence, SupersedeEvidence], Field(discriminator='action')]


class ConfigPreview(Input):
    purpose: Literal['configuration']
    channel: Channel
    program: ProgramRef | None
    config: Config
    action: Literal['create', 'replace', 'recalculate', 'rebaseline', 'convert_legacy']
    seed: TargetSeed
    reason: Reason | None


class CompletionPreview(Input):
    purpose: Literal['completion']
    channel: Channel
    repair_order_id: UUID
    expected_review_fingerprint: str = Field(min_length=1, max_length=200)
    entries: list[CompletionEntry] = Field(min_length=1, max_length=30)


class EvidencePreview(Input):
    purpose: Literal['evidence']
    channel: Channel
    program: ProgramRef
    evidence: EvidenceIntent


TargetPreviewRequest = Annotated[Union[ConfigPreview, CompletionPreview, EvidencePreview], Field(discriminator='purpose')]


class EvidenceCommit(Input):
    channel: Channel
    program: ProgramRef
    evidence: EvidenceIntent
    expected_target_fingerprint: str = Field(min_length=1, max_length=200)


class NewOperation(Input):
    kind: Literal['new']


class ExistingOperation(Input):
    kind: Literal['existing']
    labor_id: UUID
    expected_operation_version: Annotated[StrictInt, Field(ge=0)]


class CoverageGroup(Input):
    key: str = Field(min_length=1, max_length=80)
    program_ids: list[UUID] = Field(min_length=1, max_length=30)
    service_id: UUID
    operation: Annotated[Union[NewOperation, ExistingOperation], Field(discriminator='kind')]

    @field_validator('program_ids')
    @classmethod
    def unique_programs(cls, value):
        if len(value) != len(set(value)):
            raise ValueError('Program IDs must be distinct')
        return value


class ExistingTarget(Input):
    kind: Literal['existing']
    repair_order_id: UUID


class NewTarget(Input):
    kind: Literal['new']
    bill_to_customer_id: UUID
    description: str | None = Field(max_length=500)


WorkTarget = Annotated[Union[ExistingTarget, NewTarget], Field(discriminator='kind')]


class WorkRequest(Input):
    channel: Channel
    programs: list[ProgramRef] = Field(min_length=1, max_length=30)
    target: WorkTarget
    coverage: list[CoverageGroup] = Field(min_length=1, max_length=30)

    @model_validator(mode='after')
    def distinct_groups(self):
        if len({p.program_id for p in self.programs}) != len(self.programs):
            raise ValueError('Program IDs must be distinct')
        if len({g.key for g in self.coverage}) != len(self.coverage) or len({g.service_id for g in self.coverage}) != len(self.coverage):
            raise ValueError('Group keys and service IDs must be distinct')
        return self


class WorkCommit(WorkRequest):
    expected_work_fingerprint: str = Field(min_length=1, max_length=200)


class DetachWork(ArchiveCommand):
    work_link_id: UUID
    expected_link_version: Version


class MaintenanceResultItem(Input):
    program_id: UUID
    work_link_id: UUID
    result: Literal['advanced', 'pending_evidence', 'history_only', 'reaffirmed', 'revoked', 'review_required']
    missing: list[Literal['attestation', 'date', 'odometer_miles', 'engine_hours']]


class MaintenanceResult(Input):
    schema_version: Literal[1]
    items: list[MaintenanceResultItem]
