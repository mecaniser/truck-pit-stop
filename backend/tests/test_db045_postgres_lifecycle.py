"""DB-045 invariants that require an isolated PostgreSQL 15 database."""
from __future__ import annotations

import asyncio
import os
from decimal import Decimal
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import func, select, text
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db.models.inventory import Inventory
from app.db.models.inventory_lifecycle import (
    CounterSale,
    CounterSalePaymentAttempt,
    CounterSaleReservation,
    PartActivityBackfillRun,
    PartActivityEvent,
)
from app.db.models.parts_operations import InventoryMovement
from app.db.models.tenant import Tenant
from app.db.models.user import User, UserRole
from app.services.counter_sale_service import (
    create_or_replace_draft,
    finalize_checkout_success,
    prepare_checkout,
)
from app.services.part_activity_backfill import backfill_tenant_activity
from app.services.parts_operations_service import apply_inventory_movement


POSTGRES_URL = "DB045_POSTGRES_URL"
pytestmark = pytest.mark.skipif(
    not os.environ.get(POSTGRES_URL), reason="requires isolated PostgreSQL 15"
)


async def _seed(factory, *, stock: int = 1):
    suffix = uuid4().hex
    async with factory() as db:
        tenant = Tenant(
            name="DB-045 PostgreSQL",
            slug=f"db045-pg-{suffix}",
            is_active=True,
            parts_operations_enabled=True,
            counter_sales_enabled=False,
            sales_tax_rate=Decimal("7.2500"),
            service_fee_rate=Decimal("3.0000"),
        )
        owner = User(
            tenant=tenant,
            email=f"db045-{suffix}@example.test",
            hashed_password="x",
            first_name="Counter",
            last_name="Owner",
            role=UserRole.GARAGE_OWNER,
            is_active=True,
            is_verified=True,
        )
        item = Inventory(
            tenant=tenant,
            sku=f"DB045-{suffix[:8]}",
            name="Counter-sale filter",
            stock_quantity=stock,
            on_order_quantity=0,
            reorder_level=0,
            cost=Decimal("10.00"),
            selling_price=Decimal("20.00"),
            unit_type="each",
            is_placeholder=False,
        )
        db.add_all((tenant, owner, item))
        await db.commit()
        return tenant.id, owner.id, item.id


async def _draft(factory, tenant_id, owner_id, item_id):
    async with factory() as db:
        tenant = await db.get(Tenant, tenant_id)
        owner = await db.get(User, owner_id)
        sale, _lines = await create_or_replace_draft(
            db,
            tenant=tenant,
            actor=owner,
            sale=None,
            customer_id=None,
            buyer_name="Walk-in",
            buyer_email=None,
            buyer_phone=None,
            line_inputs=[{"inventory_id": item_id, "quantity": 1}],
        )
        await db.commit()
        return sale.id, sale.version


@pytest.mark.asyncio
async def test_db045_postgres_concurrent_checkout_cannot_oversell():
    engine = create_async_engine(os.environ[POSTGRES_URL])
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        tenant_id, owner_id, item_id = await _seed(factory, stock=1)
        first_sale = await _draft(factory, tenant_id, owner_id, item_id)
        second_sale = await _draft(factory, tenant_id, owner_id, item_id)

        async def reserve(sale_id, version, key):
            async with factory() as db:
                try:
                    sale, _lines, attempt = await prepare_checkout(
                        db,
                        tenant=await db.get(Tenant, tenant_id),
                        sale_id=sale_id,
                        actor=await db.get(User, owner_id),
                        expected_version=version,
                        tender="cash",
                        idempotency_key=key,
                    )
                    # Keep the physical-inventory row locked long enough for the
                    # competing checkout to block and then observe this hold.
                    await asyncio.sleep(0.05)
                    await db.commit()
                    return sale.id, attempt.id
                except HTTPException as exc:
                    await db.rollback()
                    return exc

        outcomes = await asyncio.wait_for(
            asyncio.gather(
                reserve(*first_sale, "db045-pg-checkout-a"),
                reserve(*second_sale, "db045-pg-checkout-b"),
            ),
            timeout=10,
        )
        winners = [result for result in outcomes if isinstance(result, tuple)]
        losers = [
            result for result in outcomes
            if isinstance(result, HTTPException) and result.status_code == 409
        ]
        assert len(winners) == 1
        assert len(losers) == 1

        winner_sale_id, attempt_id = winners[0]
        async with factory() as db:
            owner = await db.get(User, owner_id)
            attempt = await db.get(CounterSalePaymentAttempt, attempt_id)
            await finalize_checkout_success(
                db,
                tenant_id=tenant_id,
                sale_id=winner_sale_id,
                attempt_id=attempt_id,
                provider_amount=attempt.amount,
                currency="USD",
                provider_status="completed",
                provider_object_id=None,
                actor=owner,
            )
            await db.commit()

        async with factory() as db:
            item = await db.get(Inventory, item_id)
            sales = list((await db.execute(select(CounterSale).where(
                CounterSale.tenant_id == tenant_id,
            ))).scalars().all())
            reservations = list((await db.execute(select(CounterSaleReservation).where(
                CounterSaleReservation.tenant_id == tenant_id,
            ))).scalars().all())
            assert item.stock_quantity == 0
            assert sorted(sale.status for sale in sales) == ["completed", "draft"]
            assert [reservation.state for reservation in reservations] == ["consumed"]
            assert await db.scalar(select(func.count(InventoryMovement.id)).where(
                InventoryMovement.inventory_id == item_id,
                InventoryMovement.movement_type == "counter_sale",
            )) == 1
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_db045_postgres_backfill_reruns_reconcile_and_activity_is_immutable():
    engine = create_async_engine(os.environ[POSTGRES_URL])
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        tenant_id, owner_id, item_id = await _seed(factory, stock=2)
        async with factory() as db:
            item = await db.get(Inventory, item_id)
            owner = await db.get(User, owner_id)
            await apply_inventory_movement(
                db,
                item=item,
                quantity_delta=1,
                movement_type="adjustment",
                actor=owner,
                reason_code="postgres_backfill_proof",
                idempotency_key="db045-pg-movement-v1",
            )
            await db.commit()

        async with factory() as db:
            first = await backfill_tenant_activity(db, tenant_id, batch_size=1)
        async with factory() as db:
            second = await backfill_tenant_activity(db, tenant_id, batch_size=1)

        assert first.state == second.state == "verified"
        assert first.source_counts["baseline"] == 1
        assert first.source_counts["movement"] == 1
        assert second.source_counts == first.source_counts
        assert second.checksum == first.checksum

        async with factory() as db:
            assert await db.scalar(select(func.count(PartActivityEvent.id)).where(
                PartActivityEvent.tenant_id == tenant_id,
            )) == 2
            assert await db.scalar(select(func.count(PartActivityBackfillRun.id)).where(
                PartActivityBackfillRun.tenant_id == tenant_id,
                PartActivityBackfillRun.state == "verified",
            )) == 2
            event_id = await db.scalar(select(PartActivityEvent.id).where(
                PartActivityEvent.tenant_id == tenant_id,
            ).limit(1))

        async with factory() as db:
            with pytest.raises(DBAPIError, match="append-only"):
                await db.execute(
                    text("UPDATE part_activity_events SET note='forbidden' WHERE id=:id"),
                    {"id": event_id},
                )
            await db.rollback()
        async with factory() as db:
            with pytest.raises(DBAPIError, match="append-only"):
                await db.execute(
                    text("DELETE FROM part_activity_events WHERE id=:id"),
                    {"id": event_id},
                )
            await db.rollback()

        other_tenant_id, _other_owner_id, other_item_id = await _seed(factory, stock=1)
        async with factory() as db:
            with pytest.raises(IntegrityError, match="fk_part_activity_tenant_inventory"):
                await db.execute(
                    text(
                        """
                        INSERT INTO part_activity_events (
                          id, tenant_id, inventory_id, category, event_type,
                          correlation_id, part_sku_snapshot, part_name_snapshot,
                          actor_name_snapshot, origin, idempotency_key
                        ) VALUES (
                          :id, :tenant_id, :inventory_id, 'catalog', 'part.baseline',
                          :correlation_id, 'FOREIGN', 'Foreign part', 'System',
                          'baseline', 'db045-cross-tenant-must-fail'
                        )
                        """
                    ),
                    {
                        "id": uuid4(),
                        "tenant_id": tenant_id,
                        "inventory_id": other_item_id,
                        "correlation_id": uuid4(),
                    },
                )
            await db.rollback()
        assert other_tenant_id != tenant_id
    finally:
        await engine.dispose()
