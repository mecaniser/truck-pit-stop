"""Customer-facing invoice references. Never use these labels as database keys."""
import re
from app.core.unique_id import derive_order_number_prefix


def collection_display_number(tenant, source_number):
    if tenant is None or source_number is None:
        return None
    prefix = str(getattr(tenant, 'order_number_prefix', None) or '').strip().upper()
    if not re.fullmatch(r'[A-Z0-9]{1,10}', prefix):
        prefix = derive_order_number_prefix(getattr(tenant, 'name', '') or '')
    number = str(source_number)
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]{0,49}', number):
        return None
    return f'{prefix}-{number}'


async def load_invoice_display_number(db, invoice, tenant=None):
    source = getattr(invoice, 'source', None)
    if source not in {'ets_collection_handoff', 'easy_truck_shop_import'}:
        return getattr(invoice, 'invoice_number', '')
    from sqlalchemy import select
    from app.db.models.tenant import Tenant
    from app.db.models.source_debt_handoff import SourceDebtHandoff
    if tenant is None:
        tenant = await db.scalar(select(Tenant).where(Tenant.id == invoice.tenant_id))
    if tenant is None or tenant.id != invoice.tenant_id:
        return ''
    if source == 'easy_truck_shop_import':
        row = await db.scalar(select(SourceDebtHandoff).where(
            SourceDebtHandoff.tenant_id == invoice.tenant_id,
            SourceDebtHandoff.source_dbn_invoice_id == invoice.id,
            SourceDebtHandoff.native_invoice_id.is_not(None),
        ))
        return (collection_display_number(tenant, row.source_invoice_number) or '') if row else invoice.invoice_number
    row = await db.scalar(select(SourceDebtHandoff).where(
        SourceDebtHandoff.id == invoice.source_debt_handoff_id,
        SourceDebtHandoff.tenant_id == invoice.tenant_id,
        SourceDebtHandoff.native_invoice_id == invoice.id,
    ))
    return (collection_display_number(tenant, row.source_invoice_number) or '') if row else ''


def pdf_filename_for_number(number, *, paid=False):
    safe = re.sub(r'[^A-Za-z0-9._-]', '-', number)
    return 'Invoice' + (f'-{safe}' if safe else '') + ('-PAID' if paid else '') + '.pdf'
