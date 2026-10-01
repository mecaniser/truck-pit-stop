"""Keep reviewed export grants bound to a stable legal bill-to identity."""

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.customer import Customer
from app.db.models.historical_invoice_export import HistoricalInvoiceMapping


async def guard_mapped_customer_name(db: AsyncSession, customer: Customer, changes: dict) -> None:
    if not any(field in changes and changes[field] != getattr(customer, field)
               for field in ("company_name", "first_name", "last_name")):
        return
    active = (await db.execute(select(HistoricalInvoiceMapping.id).where(
        HistoricalInvoiceMapping.tenant_id == customer.tenant_id,
        HistoricalInvoiceMapping.target_customer_id == customer.id,
    ).limit(1))).scalar_one_or_none()
    if active:
        raise HTTPException(status_code=409,
                            detail="Revoke reviewed historical invoice mappings before changing bill-to identity")
