"""Narrow C1 source-evidence guard, not a financial identity merge."""
from sqlalchemy import select, or_
from app.db.models.customer_pricing import AccountPricingEvent
from app.db.models.repair_order import RepairOrder
from app.db.models.inventory_lifecycle import CounterSale
from app.services.parts_pricing_rules import fail


async def require_removable_pricing_identity(db, customer):
    configured=(customer.pricing_version or 0)>0 or customer.pricing_labor_rate is not None or customer.parts_price_matrix_id is not None
    history=await db.scalar(select(AccountPricingEvent.id).where(AccountPricingEvent.tenant_id==customer.tenant_id,AccountPricingEvent.entity_type=='customer_policy',AccountPricingEvent.entity_id==customer.id).limit(1))
    referenced=False
    for model in (RepairOrder,CounterSale):
        referenced=referenced or bool(await db.scalar(select(model.id).where(model.tenant_id==customer.tenant_id,model.pricing_policy_snapshot['customer_id'].as_string()==str(customer.id)).limit(1)))
    if configured or history or referenced:
        fail('customer_pricing_merge_locked','This customer has saved pricing history. Keep this customer as the retained account, or leave the accounts separate.',409)
