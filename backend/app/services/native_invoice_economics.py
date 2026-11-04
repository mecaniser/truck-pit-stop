"""Read-only native invoice pricing, shared by preview and transaction issuance."""
from dataclasses import dataclass
from decimal import Decimal
from types import SimpleNamespace
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from app.db.models.labor import Labor
from app.db.models.inventory import PartsUsage
from app.services.pricing import get_order_checkout_breakdown
from app.services.customer_tax_exemption import issuance_default
from app.services.booking_payments import digest

@dataclass(frozen=True)
class NativeInvoiceEconomics:
    checkout: dict
    taxable_checkout: dict
    tax_default: dict | None
    line_items_snapshot: dict
    discount_amount: Decimal
    total_amount: Decimal
    principal_total: Decimal
    sha256: str

    def preview(self, available_minor):
        principal=int(self.principal_total*100)
        suggested=min(max(0,available_minor),principal)
        return {'currency':'usd','invoice_total_minor':int(self.total_amount*100),
            'allocatable_principal_minor':principal,'suggested_apply_minor':suggested,
            'remaining_minor':principal-suggested,'invoice_economics_sha256':self.sha256}

async def native_invoice_economics(db, order, tenant, *, discount_amount=Decimal('0.00'), lock=False, require_itemized=True):
    from app.api.v1.endpoints.invoices import _load_line_items, _line_items_snapshot
    from app.services.invoice_settlement_service import invoice_money_snapshot, SettlementDomainError
    if tenant.id!=order.tenant_id:
        raise SettlementDomainError('booking_invoice_identity_mismatch','Invoice identity needs review.')
    labor=(await db.scalars(select(Labor).where(Labor.repair_order_id==order.id,Labor.deleted_at.is_(None)).order_by(Labor.id).execution_options(populate_existing=True))).all()
    parts=(await db.scalars(select(PartsUsage).where(PartsUsage.repair_order_id==order.id,PartsUsage.deleted_at.is_(None)).options(selectinload(PartsUsage.inventory_item)).order_by(PartsUsage.id).execution_options(populate_existing=True))).all()
    if any(row.tenant_id!=tenant.id or row.deleted_at is not None for row in [*labor,*parts]):
        raise SettlementDomainError('booking_invoice_line_identity_invalid','Invoice line identity needs review.')
    if any(not row.inventory_item or row.inventory_item.tenant_id!=tenant.id for row in parts):
        raise SettlementDomainError('booking_invoice_line_identity_invalid','Invoice part identity needs review.')
    # Structured children, rather than a potentially stale cached order total.
    pricing_order=SimpleNamespace(total_parts_cost=sum((Decimal(str(p.total_price)) for p in parts),Decimal(0)),
        total_labor_cost=sum((Decimal(str(l.total_cost)) for l in labor),Decimal(0)),
        labor_discount_amount=order.labor_discount_amount,order_discount_amount=order.order_discount_amount)
    # Existing ordinary issuance supports explicit persisted legacy totals.
    # The dedicated booking writer/preview always require current itemized rows.
    if not require_itemized:pricing_order=order
    tax_default=await issuance_default(db,order,tenant,lock=lock)
    taxable=get_order_checkout_breakdown(pricing_order,tenant)
    checkout=get_order_checkout_breakdown(pricing_order,tenant,tax_exempt=bool(tax_default))
    discount=Decimal(str(discount_amount))
    if not discount.is_finite() or discount<0 or discount!=discount.quantize(Decimal('.01')) or discount>checkout['estimated_card_total']:
        raise SettlementDomainError('invoice_discount_invalid','Review the invoice discount.')
    discount=discount.quantize(Decimal('.01'))
    total=checkout['estimated_card_total']-discount
    principal,*_=invoice_money_snapshot(SimpleNamespace(subtotal=checkout['repair_total'],shop_supplies_amount=checkout['shop_supplies_amount'],service_fee_amount=checkout['service_fee_amount'],tax_amount=checkout['tax_amount'],total_amount=total))
    labor_items,parts_items=await _load_line_items(db,order.id)
    snapshot=_line_items_snapshot(labor_items,parts_items)
    evidence={'version':1,'tenant_id':tenant.id,'repair_order_id':order.id,'customer_id':order.customer_id,
        'vehicle_id':order.vehicle_id,'currency':'usd','checkout':checkout,'tax_default':tax_default,
        'discount_amount':discount,'total_amount':total,'line_items':snapshot,
        'labor_ids':[str(x.id) for x in labor],'parts_ids':[str(x.id) for x in parts]}
    return NativeInvoiceEconomics(checkout,taxable,tax_default,snapshot,discount,total,principal,digest(evidence))
