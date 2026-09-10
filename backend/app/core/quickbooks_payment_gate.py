"""Tenant-scoped admission for new QBP charges, not historical reconciliation."""
from uuid import UUID

from app.core.config import settings


def quickbooks_payments_enabled_for_tenant(tenant_id: UUID | str | None) -> bool:
    if not settings.QUICKBOOKS_PAYMENTS_INVOICE_PAYMENTS_APPROVED:
        return False
    try:
        tenant = UUID(str(tenant_id))
    except (ValueError, TypeError, AttributeError):
        return False
    raw = settings.QUICKBOOKS_PAYMENTS_APPROVED_TENANT_IDS.strip()
    if not raw:
        return (
            settings.ENVIRONMENT.strip().lower() != "production"
            and settings.QUICKBOOKS_PAYMENTS_ENVIRONMENT.strip().lower() == "sandbox"
        )
    try:
        # Reject the whole configuration on any malformed or empty entry.
        approved = {UUID(value.strip()) for value in raw.split(",")}
    except (ValueError, TypeError, AttributeError):
        return False
    return tenant in approved
