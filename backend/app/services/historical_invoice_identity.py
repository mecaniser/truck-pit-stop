"""Keep reviewed export grants bound to a stable legal bill-to identity."""

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.customer import Customer
from app.db.models.historical_invoice_export import HistoricalInvoiceEvidence, HistoricalInvoiceMapping


async def guard_mapped_customer_name(db: AsyncSession, customer: Customer, changes: dict) -> None:
    name_changed = any(field in changes and changes[field] != getattr(customer, field)
                       for field in ("company_name", "first_name", "last_name"))
    email_changed = "email" in changes and (changes["email"] or "").strip().casefold() != (customer.email or "").strip().casefold()
    if not name_changed and not email_changed:
        return
    query = select(HistoricalInvoiceMapping.id).where(
        HistoricalInvoiceMapping.tenant_id == customer.tenant_id,
        HistoricalInvoiceMapping.target_customer_id == customer.id,
    )
    if not name_changed:
        query = query.join(HistoricalInvoiceEvidence,
            (HistoricalInvoiceEvidence.id == HistoricalInvoiceMapping.evidence_id)
            & (HistoricalInvoiceEvidence.tenant_id == HistoricalInvoiceMapping.tenant_id)
        ).where(HistoricalInvoiceEvidence.identity_proof.is_not(None))
    active = (await db.execute(query.limit(1))).scalar_one_or_none()
    if active:
        raise HTTPException(status_code=409,
                            detail="Revoke reviewed historical invoice mappings before changing bill-to identity")
