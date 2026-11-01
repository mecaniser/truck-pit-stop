"""Frozen V1 source-debt collection HTTP payloads; client money is never proof."""
from typing import Literal, Optional
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field

class PreviewRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    source_invoice_id: UUID
    target_customer_id: UUID

class PrepareRequest(PreviewRequest):
    expected_source_capture_sha256: str = Field(min_length=64,max_length=64,pattern='^[a-f0-9]+$')
    expected_source_revision: str = Field(min_length=1,max_length=64)
    acknowledge_dbn_primary: Literal[True]

class VersionRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    expected_version: int = Field(ge=1)

class SourceVersionRequest(VersionRequest):
    expected_source_capture_sha256: str = Field(min_length=64,max_length=64,pattern='^[a-f0-9]+$')
    expected_source_revision: str = Field(min_length=1,max_length=64)

class AcknowledgeRequest(VersionRequest):
    expected_source_revision: str = Field(min_length=1,max_length=64)
    source_allocation_ids: list[str] = Field(min_length=1,max_length=200)
    source_capture_sha256: str = Field(min_length=64,max_length=64,pattern='^[a-f0-9]+$')

class ReconcileRequest(VersionRequest):
    expected_source_revision: str = Field(min_length=1,max_length=64)
    source_capture_sha256: str = Field(min_length=64,max_length=64,pattern='^[a-f0-9]+$')
