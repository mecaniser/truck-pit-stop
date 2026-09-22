from decimal import Decimal as D
from types import SimpleNamespace as N

import pytest
from pydantic import ValidationError
from fastapi import HTTPException
from app.services.discount_limits import discount_limits, validate_discounts, proposed_part_price
from app.schemas.repair_order import DiscountUpdate, PartsPricingModeRequest
from app.api.v1.endpoints import repair_orders as ro
from test_ro_pricing_discounts import _seed_order
from sqlalchemy import select, func
from app.api.v1.endpoints import quotes
from app.db.models.quote import Quote
from app.db.models.invoice import Invoice
from app.db.models.repair_order import RepairOrder, RepairOrderStatus
from app.db.models.inventory import PartsUsage
from uuid import uuid4


def order():
    return N(tenant=N(internal_labor_rate='50'), labor_discount_amount=0, order_discount_amount=0,
             labor_items=[N(hours='3', total_cost='300', line_type='manual')],
             parts_usage=[N(unit_cost='400', unit_price='700', list_price='700', quantity='1', total_price='700', tenant_id=1, inventory_item=None)])


def test_exact_cost_and_stacked_discounts():
    o = order()
    assert discount_limits(o)['labor_discount_max'] == D('150')
    assert discount_limits(o)['combined_discount_max'] == D('450')
    validate_discounts(o, labor=150, total=300)
    with pytest.raises(ValueError):
        validate_discounts(o, labor='150.01', total=0)
    with pytest.raises(ValueError):
        validate_discounts(o, labor=150, total='300.01')
    with pytest.raises(ValueError):
        validate_discounts(o, labor=150, total=1, mode='stock')


def test_subcent_discounts_are_rejected_before_rounding():
    with pytest.raises(ValidationError):
        DiscountUpdate(labor_discount_amount=D('149.995'), order_discount_amount=D('300.015'))


def test_legacy_list_price_uses_same_tenant_inventory():
    part = order().parts_usage[0]
    part.list_price = None
    part.unit_price = D('400')
    part.inventory_item = N(tenant_id=1, cost=400, selling_price=700)
    assert proposed_part_price(part, 'list') == 700
    part.inventory_item.tenant_id = 2
    assert proposed_part_price(part, 'list') == 400


def test_missing_cost_and_zero_cost_are_distinct():
    o = order()
    o.parts_usage[0].unit_cost = None
    validate_discounts(o, labor=150, total=0)
    with pytest.raises(ValueError):
        validate_discounts(o, total=1)
    o.parts_usage[0].unit_cost = '0'
    assert discount_limits(o)['combined_discount_max'] == D('850')
    o.tenant.internal_labor_rate = 0
    with pytest.raises(ValueError):
        validate_discounts(o, labor=1)
    validate_discounts(o)  # untouched legacy order remains readable


def test_zero_hours_sublet_and_fractional_cost():
    o = order()
    o.labor_items[0].hours = '0'
    assert discount_limits(o)['labor_discount_max'] == 0
    o.labor_items[0].line_type = 'sublet'
    o.labor_items[0].vendor_cost = '250'
    assert discount_limits(o)['labor_discount_max'] == 50
    o.parts_usage[0].unit_cost = '400.001'
    assert discount_limits(o)['combined_discount_max'] == D('349.99')


@pytest.mark.asyncio
async def test_atomic_mode_reset_and_partial_discount_validation(db_session):
    _, owner, o = await _seed_order(db_session)
    await ro.update_repair_order_discounts(o.id, DiscountUpdate(order_discount_amount=D('150')), db_session, owner)
    with pytest.raises(HTTPException):
        await ro.update_repair_order_discounts(o.id, DiscountUpdate(labor_discount_amount=D('100')), db_session, owner)
    with pytest.raises(HTTPException):
        await ro.set_parts_pricing_mode(o.id, PartsPricingModeRequest(mode='stock'), db_session, owner)
    result = await ro.update_repair_order_discounts(o.id, DiscountUpdate(parts_pricing_mode='stock', labor_discount_amount=D('100'), order_discount_amount=D('0')), db_session, owner)
    assert result.total_cost == D('180')  # 100 labor cost + 80 parts cost


@pytest.mark.asyncio
async def test_internal_and_customer_use_same_cost_rate(db_session):
    _, owner, o = await _seed_order(db_session)
    for internal in [False, True]:
        o.is_internal = internal
        await db_session.commit()
        loaded = await ro._load_pricing_order_for_update(db_session, o.id, tenant_id=owner.tenant_id)
        assert discount_limits(loaded)['labor_discount_max'] == D('100')


@pytest.mark.asyncio
async def test_labor_edit_cannot_consume_retained_discount_headroom(db_session):
    _, owner, o = await _seed_order(db_session)
    await ro.update_repair_order_discounts(o.id, DiscountUpdate(labor_discount_amount=D('100')), db_session, owner)
    loaded = await ro._load_pricing_order_for_update(db_session, o.id)
    loaded.labor_items[0].total_cost = D('150')
    with pytest.raises(HTTPException):
        await ro._refresh_repair_order_totals(db_session, o.id)
    await db_session.rollback()


@pytest.mark.asyncio
@pytest.mark.parametrize('action', ['publish', 'finalize'])
async def test_current_rate_increase_blocks_publication_without_side_effects(db_session, action):
    tenant, owner, o = await _seed_order(db_session)
    await ro.update_repair_order_discounts(o.id, DiscountUpdate(labor_discount_amount=D('100')), db_session, owner)
    order_id = o.id
    if action == 'finalize':
        o.status = RepairOrderStatus.PENDING_REVIEW
    quote = Quote(tenant_id=tenant.id, repair_order_id=order_id,
                  quote_number=f'Q-{uuid4().hex}', total_amount=D('300'), revision=1,
                  authorization_type='initial_estimate', previously_authorized_amount=0,
                  delta_amount=D('300'), sent_to_customer=False, is_approved=False, is_declined=False)
    db_session.add(quote)
    tenant.internal_labor_rate = D('75')
    await db_session.commit()
    quote_id = quote.id
    expected_status = o.status
    with pytest.raises(HTTPException) as exc:
        if action == 'publish':
            await quotes.send_quote_to_customer(quote_id=quote_id, db=db_session, current_user=owner)
        else:
            await ro.approve_completion(order_id=order_id, body=ro.ApproveCompletionRequest(),
                                        idempotency_key=None, db=db_session, current_user=owner)
    assert exc.value.status_code == 400
    assert 'discount' in str(exc.value.detail).lower()
    await db_session.rollback()
    saved = await db_session.get(RepairOrder, order_id, populate_existing=True)
    saved_quote = await db_session.get(Quote, quote_id, populate_existing=True)
    assert saved.status == expected_status
    assert saved.labor_discount_amount == D('100')
    assert saved.total_cost == D('300')
    assert not saved_quote.sent_to_customer
    assert await db_session.scalar(select(func.count(Invoice.id)).where(Invoice.repair_order_id == order_id)) == 0


@pytest.mark.asyncio
async def test_invalid_atomic_repricing_rolls_back_all_persisted_fields(db_session):
    _, owner, o = await _seed_order(db_session)
    order_id = o.id
    await ro.update_repair_order_discounts(order_id, DiscountUpdate(order_discount_amount=D('120')), db_session, owner)
    with pytest.raises(HTTPException) as exc:
        await ro.update_repair_order_discounts(order_id,
            DiscountUpdate(parts_pricing_mode='stock', labor_discount_amount=D('100'), order_discount_amount=D('.01')),
            db_session, owner)
    assert exc.value.status_code == 400
    await db_session.rollback()
    saved = await db_session.get(RepairOrder, order_id, populate_existing=True)
    part = (await db_session.execute(select(PartsUsage).where(PartsUsage.repair_order_id == order_id))).scalar_one()
    assert saved.labor_discount_amount == D('0')
    assert saved.order_discount_amount == D('120')
    assert saved.total_cost == D('280')
    assert part.unit_price == D('100')
    assert part.total_price == D('200')
