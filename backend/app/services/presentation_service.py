"""Authenticated staff presentation resolution and preference persistence."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.metrics import record_presentation_operation
from app.db.models.appearance import UserAppearancePreference, UserPresentationOverride
from app.db.models.tenant import Tenant
from app.db.models.user import User, UserRole
from app.schemas.presentation import (
    AppearanceValues,
    PresentationResponse,
)

PRODUCT_DEFAULTS = AppearanceValues(
    accent="cyan",
    font_family="geist",
    font_size="default",
    density="default",
    notification_position="bottom_right",
    mode="dark",
)
STAFF_ROLES = {
    UserRole.SUPER_ADMIN,
    UserRole.GARAGE_OWNER,
    UserRole.GARAGE_ADMIN,
    UserRole.RECEPTIONIST,
    UserRole.MECHANIC,
    UserRole.FLEET_MANAGER,
}


def _error(code: int, detail: str) -> HTTPException:
    return HTTPException(status_code=code, detail=detail)


def require_staff_context(user: User) -> UUID:
    if user.role not in STAFF_ROLES:
        raise _error(status.HTTP_403_FORBIDDEN, "Staff presentation access required")
    if not user.tenant_id:
        raise _error(status.HTTP_400_BAD_REQUEST, "TENANT_CONTEXT_REQUIRED")
    return user.tenant_id


async def _tenant(db: AsyncSession, tenant_id: UUID) -> Tenant:
    tenant = await db.scalar(select(Tenant).where(Tenant.id == tenant_id, Tenant.deleted_at.is_(None)))
    if not tenant:
        raise _error(status.HTTP_404_NOT_FOUND, "Not found")
    return tenant


async def resolve_presentation(
    db: AsyncSession,
    user: User,
    *,
    tenant_id: Optional[UUID] = None,
    record_metrics: bool = True,
) -> PresentationResponse:
    tenant_id = tenant_id or require_staff_context(user)
    if user.role not in STAFF_ROLES:
        raise _error(status.HTTP_403_FORBIDDEN, "Staff presentation access required")
    tenant = await _tenant(db, tenant_id)
    override = await db.scalar(
        select(UserPresentationOverride).where(
            UserPresentationOverride.tenant_id == tenant_id,
            UserPresentationOverride.user_id == user.id,
            UserPresentationOverride.deleted_at.is_(None),
        )
    )
    preference = await db.scalar(
        select(UserAppearancePreference).where(
            UserAppearancePreference.tenant_id == tenant_id,
            UserAppearancePreference.user_id == user.id,
            UserAppearancePreference.deleted_at.is_(None),
        )
    )
    if settings.AUTHENTICATED_PRESENTATION_FORCE_LEGACY:
        variant, source = "legacy", "global_force_legacy"
    elif override:
        variant, source = override.presentation, "user_override"
    elif tenant.staff_presentation_default in {"legacy", "new"}:
        variant, source = tenant.staff_presentation_default, "tenant_default"
    else:
        variant, source = "legacy", "product_default"
    appearance = PRODUCT_DEFAULTS
    if preference and isinstance(preference.appearance, dict):
        try:
            appearance = AppearanceValues.model_validate(preference.appearance)
        except Exception:
            appearance = PRODUCT_DEFAULTS
    response = PresentationResponse(
        resolved_variant=variant,
        source=source,
        appearance=appearance,
        defaults=PRODUCT_DEFAULTS,
        revision=preference.revision if preference else 0,
        legacy_migration_status=preference.legacy_migration_status if preference else "pending",
        updated_at=preference.updated_at if preference else None,
    )
    if record_metrics:
        record_presentation_operation("resolve", "success", variant=variant, source=source)
    return response


async def get_appearance(db: AsyncSession, user: User) -> PresentationResponse:
    return await resolve_presentation(db, user)


async def update_appearance(
    db: AsyncSession,
    user: User,
    *,
    base_revision: int,
    appearance: AppearanceValues,
    migration_source: Optional[str] = None,
) -> PresentationResponse:
    tenant_id = require_staff_context(user)
    await _tenant(db, tenant_id)
    preference = await db.scalar(
        select(UserAppearancePreference)
        .where(
            UserAppearancePreference.tenant_id == tenant_id,
            UserAppearancePreference.user_id == user.id,
            UserAppearancePreference.deleted_at.is_(None),
        )
        .with_for_update()
    )
    if preference is None:
        if base_revision != 0:
            record_presentation_operation("appearance_put", "revision_conflict")
            raise _error(status.HTTP_409_CONFLICT, "Presentation settings changed elsewhere")
        preference = UserAppearancePreference(
            tenant_id=tenant_id,
            user_id=user.id,
            revision=1,
            appearance=appearance.model_dump(),
            legacy_migration_status="complete",
            legacy_migrated_at=datetime.now(timezone.utc) if migration_source else None,
        )
        db.add(preference)
    else:
        if preference.revision != base_revision:
            record_presentation_operation("appearance_put", "revision_conflict")
            raise _error(status.HTTP_409_CONFLICT, "Presentation settings changed elsewhere")
        preference.revision += 1
        preference.appearance = appearance.model_dump()
        preference.legacy_migration_status = "complete"
        if migration_source:
            preference.legacy_migrated_at = preference.legacy_migrated_at or datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(preference)
    record_presentation_operation("appearance_put", "success")
    return await resolve_presentation(db, user)


async def reset_appearance(db: AsyncSession, user: User, *, base_revision: int) -> PresentationResponse:
    tenant_id = require_staff_context(user)
    preference = await db.scalar(
        select(UserAppearancePreference)
        .where(
            UserAppearancePreference.tenant_id == tenant_id,
            UserAppearancePreference.user_id == user.id,
            UserAppearancePreference.deleted_at.is_(None),
        )
        .with_for_update()
    )
    if preference is None or preference.revision != base_revision:
        record_presentation_operation("appearance_delete", "revision_conflict")
        raise _error(status.HTTP_409_CONFLICT, "Presentation settings changed elsewhere")
    preference.deleted_at = datetime.now(timezone.utc)
    await db.commit()
    record_presentation_operation("appearance_delete", "success")
    return await resolve_presentation(db, user)


async def set_tenant_rollout(db: AsyncSession, tenant_id: UUID, presentation: str) -> None:
    tenant = await db.scalar(select(Tenant).where(Tenant.id == tenant_id, Tenant.deleted_at.is_(None)))
    if not tenant:
        raise _error(status.HTTP_404_NOT_FOUND, "Not found")
    tenant.staff_presentation_default = presentation
    await db.commit()
    record_presentation_operation("tenant_rollout", "success", variant=presentation, source="tenant_default")


async def set_user_rollout(
    db: AsyncSession,
    tenant_id: UUID,
    user_id: UUID,
    presentation_override: Optional[str],
) -> Optional[str]:
    target = await db.scalar(
        select(User).where(
            User.id == user_id,
            User.tenant_id == tenant_id,
            User.deleted_at.is_(None),
            User.is_active.is_(True),
        )
    )
    if not target:
        raise _error(status.HTTP_404_NOT_FOUND, "Not found")
    row = await db.scalar(
        select(UserPresentationOverride)
        .where(
            UserPresentationOverride.tenant_id == tenant_id,
            UserPresentationOverride.user_id == user_id,
            UserPresentationOverride.deleted_at.is_(None),
        )
        .with_for_update()
    )
    if presentation_override is None:
        if row:
            row.deleted_at = datetime.now(timezone.utc)
    elif row:
        row.presentation = presentation_override
    else:
        db.add(UserPresentationOverride(tenant_id=tenant_id, user_id=user_id, presentation=presentation_override))
    await db.commit()
    record_presentation_operation("user_rollout", "success", variant=presentation_override or "legacy", source="user_override")
    return presentation_override
