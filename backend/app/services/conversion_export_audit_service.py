"""PII-minimized audit helpers for conversion-export security events."""
from __future__ import annotations

from typing import Optional
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.conversion_export_audit import ConversionExportAudit


def record_conversion_audit(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    action: str,
    target_type: str,
    target_id: Optional[UUID] = None,
    actor_user_id: Optional[UUID] = None,
    actor_api_key_id: Optional[UUID] = None,
    metadata: Optional[dict] = None,
) -> ConversionExportAudit:
    """Append an audit event without customer contact or webhook payload data."""
    row = ConversionExportAudit(
        tenant_id=tenant_id,
        actor_user_id=actor_user_id,
        actor_api_key_id=actor_api_key_id,
        action=action,
        target_type=target_type,
        target_id=target_id,
        metadata_json=metadata or {},
    )
    db.add(row)
    return row
