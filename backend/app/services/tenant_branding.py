"""Shared sender-name lookup for tenant-facing notifications."""
from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.tenant import Tenant


async def get_tenant_display_name(db: AsyncSession, tenant_id: UUID) -> str:
    """Return the tenant's current shop name without falling back to platform branding."""
    name = await db.scalar(select(Tenant.name).where(Tenant.id == tenant_id))
    return name.strip() if name and name.strip() else "Your repair shop"
