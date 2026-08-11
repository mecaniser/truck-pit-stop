"""Controlled re-encryption path for conversion webhook signing secrets."""
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.paid_invoice_webhook_crypto import reencrypt_paid_invoice_webhook_secret
from app.db.models.tenant import Tenant


async def rotate_paid_invoice_webhook_secrets(db: AsyncSession, *, apply: bool = False) -> int:
    tenants = (await db.execute(select(Tenant).where(Tenant.paid_invoice_webhook_secret_encrypted.is_not(None)).with_for_update())).scalars().all()
    for tenant in tenants:
        rotated = reencrypt_paid_invoice_webhook_secret(tenant.paid_invoice_webhook_secret_encrypted)
        if apply:
            tenant.paid_invoice_webhook_secret_encrypted = rotated
    if apply:
        await db.commit()
    else:
        await db.rollback()
    return len(tenants)
