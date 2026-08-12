from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


PresentationVariant = Literal["legacy", "new"]
PresentationSource = Literal[
    "global_force_legacy", "user_override", "tenant_default", "product_default"
]
LegacyMigrationStatus = Literal["pending", "complete"]


class AppearanceValues(BaseModel):
    model_config = ConfigDict(extra="forbid")

    accent: Literal["cyan", "indigo", "emerald", "rose", "amber"]
    font_family: Literal["geist", "dm-sans", "jakarta", "inter"]
    font_size: Literal["small", "default", "large"]
    density: Literal["compact", "default", "comfortable", "large"]
    notification_position: Literal["top_right", "bottom_right", "top_center"]
    mode: Literal["light", "dark", "high_contrast"]


class PresentationResponse(BaseModel):
    schema_version: Literal[1] = 1
    resolved_variant: PresentationVariant
    source: PresentationSource
    appearance: AppearanceValues
    defaults: AppearanceValues
    revision: int = Field(ge=0)
    legacy_migration_status: LegacyMigrationStatus
    updated_at: Optional[datetime] = None


class AppearanceUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1]
    base_revision: int = Field(ge=0)
    appearance: AppearanceValues
    migration_source: Optional[Literal["legacy_local_v1"]] = None


class AppearanceResetRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1]
    base_revision: int = Field(ge=0)


class TenantPresentationRolloutRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1]
    presentation: PresentationVariant


class UserPresentationRolloutRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1]
    presentation_override: Optional[PresentationVariant]


class TenantPresentationRolloutResponse(BaseModel):
    schema_version: Literal[1] = 1
    tenant_id: str
    presentation: PresentationVariant


class UserPresentationRolloutResponse(BaseModel):
    schema_version: Literal[1] = 1
    tenant_id: str
    user_id: str
    presentation_override: Optional[PresentationVariant]
