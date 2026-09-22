"""Real row-lock regressions; run only against an isolated migrated PostgreSQL DB."""
import asyncio
import os
from decimal import Decimal as D

import pytest
from fastapi import HTTPException
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api.v1.endpoints import repair_orders as ro
from app.db.models.inventory import PartsUsage
from app.db.models.repair_order import RepairOrder
from app.db.models.tenant import Tenant
from app.db.models.user import User
from app.schemas.repair_order import DiscountUpdate, PartsPricingModeRequest
from test_ro_pricing_discounts import _seed_order

pytestmark = [pytest.mark.asyncio, pytest.mark.skipif(
    not os.environ.get('DB003_POSTGRES_URL'), reason='requires isolated migrated PostgreSQL')]


async def test_pricing_loader_locks_order_without_locking_tenant():
    engine = create_async_engine(os.environ['DB003_POSTGRES_URL'])
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with factory() as db:
            tenant, _, order = await _seed_order(db)
            tenant_id, order_id = tenant.id, order.id
            await db.commit()
        async with factory() as tenant_writer, factory() as pricing:
            await tenant_writer.execute(select(Tenant).where(Tenant.id == tenant_id).with_for_update())
            await pricing.execute(text("SET LOCAL lock_timeout = '1000ms'"))
            loaded = await ro._load_pricing_order_for_update(pricing, order_id, tenant_id=tenant_id)
            assert loaded.id == order_id
            # The joined tenant row is deliberately locked elsewhere. A broad
            # FOR UPDATE would time out above (the previous lock inversion).
            async with factory() as competitor:
                await competitor.execute(text("SET LOCAL lock_timeout = '200ms'"))
                from sqlalchemy.exc import DBAPIError
                with pytest.raises(DBAPIError):
                    await competitor.execute(select(RepairOrder).where(RepairOrder.id == order_id).with_for_update())
                await competitor.rollback()
            await pricing.rollback()
            await tenant_writer.rollback()
    finally:
        await engine.dispose()


@pytest.mark.parametrize('first', ['discount', 'stock'])
async def test_same_order_discount_and_stock_repricing_serialize(monkeypatch, first):
    engine = create_async_engine(os.environ['DB003_POSTGRES_URL'])
    factory = async_sessionmaker(engine, expire_on_commit=False)
    entered, release = asyncio.Event(), asyncio.Event()
    tasks = []
    try:
        async with factory() as db:
            _, owner, order = await _seed_order(db)
            owner_id, order_id = owner.id, order.id
            await db.commit()
        original = ro._load_pricing_order_for_update
        first_loader = True

        async def paused_loader(*args, **kwargs):
            nonlocal first_loader
            loaded = await original(*args, **kwargs)
            if first_loader:
                first_loader = False
                entered.set()
                await release.wait()
            return loaded

        monkeypatch.setattr(ro, '_load_pricing_order_for_update', paused_loader)

        async def attempt(kind):
            async with factory() as db:
                actor = await db.get(User, owner_id)
                try:
                    if kind == 'discount':
                        return await ro.update_repair_order_discounts(order_id,
                            DiscountUpdate(order_discount_amount=D('120')), db, actor)
                    return await ro.set_parts_pricing_mode(order_id, PartsPricingModeRequest(mode='stock'), db, actor)
                except HTTPException as exc:
                    await db.rollback()
                    return exc

        tasks.append(asyncio.create_task(attempt(first)))
        await asyncio.wait_for(entered.wait(), 5)
        tasks.append(asyncio.create_task(attempt('stock' if first == 'discount' else 'discount')))
        await asyncio.sleep(.2)
        assert not tasks[1].done(), 'second pricing mutation must wait for the order lock'
        release.set()
        results = await asyncio.wait_for(asyncio.gather(*tasks), 10)
        assert not isinstance(results[0], HTTPException)
        assert isinstance(results[1], HTTPException)
        assert results[1].status_code == 400
        async with factory() as db:
            saved = await db.get(RepairOrder, order_id)
            part = (await db.execute(select(PartsUsage).where(PartsUsage.repair_order_id == order_id))).scalar_one()
            assert saved.total_cost == D('280')
            assert saved.order_discount_amount == (D('120') if first == 'discount' else D('0'))
            assert part.unit_price == (D('100') if first == 'discount' else D('40'))
            assert part.total_price == (D('200') if first == 'discount' else D('80'))
    finally:
        release.set()
        for task in tasks:
            if not task.done():
                task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        await engine.dispose()
