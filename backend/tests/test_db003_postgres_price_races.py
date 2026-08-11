from __future__ import annotations

import asyncio
import os
from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api.v1.endpoints import invoices, quotes, repair_orders
from app.db.models.customer import Customer
from app.db.models.inventory import Inventory, PartsUsage
from app.db.models.invoice import Invoice
from app.db.models.labor import Labor, LaborLineType
from app.db.models.quote import Quote
from app.db.models.repair_order import RepairOrder, RepairOrderStatus
from app.db.models.repair_order_history import RepairOrderHistoryEvent
from app.db.models.tenant import Tenant
from app.db.models.user import User, UserRole
from app.db.models.vehicle import Vehicle
from app.schemas.repair_order import PartsUsageCreate


async def _seed_race_context(factory, *, status: RepairOrderStatus, with_quote: bool):
    suffix = uuid4().hex
    async with factory() as db:
        tenant = Tenant(
            name="DB-003 Race Shop",
            slug=f"db003-race-{suffix}",
            email=f"shop-{suffix}@example.com",
            labor_rate=Decimal("100.00"),
        )
        db.add(tenant)
        await db.flush()
        customer = Customer(
            tenant_id=tenant.id,
            first_name="Casey",
            last_name="Concurrency",
            email=f"customer-{suffix}@example.com",
        )
        db.add(customer)
        await db.flush()
        vehicle = Vehicle(
            tenant_id=tenant.id,
            customer_id=customer.id,
            make="Freightliner",
            model="Cascadia",
            year=2023,
        )
        admin = User(
            tenant_id=tenant.id,
            email=f"admin-{suffix}@example.com",
            hashed_password="hashed-password",
            first_name="Shop",
            last_name="Admin",
            role=UserRole.GARAGE_ADMIN,
            is_active=True,
            is_verified=True,
        )
        mechanic = User(
            tenant_id=tenant.id,
            email=f"mechanic-{suffix}@example.com",
            hashed_password="hashed-password",
            first_name="Assigned",
            last_name="Mechanic",
            role=UserRole.MECHANIC,
            is_active=True,
            is_verified=True,
        )
        db.add_all([vehicle, admin, mechanic])
        await db.flush()
        order = RepairOrder(
            tenant_id=tenant.id,
            customer_id=customer.id,
            vehicle_id=vehicle.id,
            assigned_mechanic_id=mechanic.id,
            order_number=f"RO-{suffix[:12]}",
            status=status,
            description="Concurrent price mutation",
            total_parts_cost=Decimal("0.00"),
            total_labor_cost=Decimal("100.00"),
            total_cost=Decimal("100.00"),
            work_started_at=datetime.now(timezone.utc),
            work_completed_at=(
                datetime.now(timezone.utc)
                if status == RepairOrderStatus.PENDING_REVIEW
                else None
            ),
        )
        inventory = Inventory(
            tenant_id=tenant.id,
            sku=f"RACE-{suffix[:8]}",
            name="Concurrent priced part",
            stock_quantity=5,
            on_order_quantity=0,
            reorder_level=0,
            cost=Decimal("25.00"),
            selling_price=Decimal("50.00"),
        )
        db.add_all([order, inventory])
        await db.flush()
        db.add(
            Labor(
                tenant_id=tenant.id,
                repair_order_id=order.id,
                description="Existing authorized labor",
                hours=Decimal("1.00"),
                hourly_rate=Decimal("100.00"),
                total_cost=Decimal("100.00"),
                line_type=LaborLineType.MANUAL,
            )
        )
        quote = None
        if with_quote:
            quote = Quote(
                tenant_id=tenant.id,
                repair_order_id=order.id,
                quote_number=f"Q-{suffix[:12]}",
                total_amount=Decimal("100.00"),
                revision=1,
                authorization_type="initial_estimate",
                previously_authorized_amount=Decimal("0.00"),
                delta_amount=Decimal("100.00"),
                sent_to_customer=False,
                is_approved=False,
                is_declined=False,
            )
            db.add(quote)
        await db.commit()
        return {
            "order_id": order.id,
            "inventory_id": inventory.id,
            "mechanic_id": mechanic.id,
            "admin_id": admin.id,
            "quote_id": quote.id if quote else None,
        }


async def _add_part(factory, context):
    async with factory() as db:
        mechanic = await db.get(User, context["mechanic_id"])
        return await repair_orders.add_parts_to_repair_order(
            order_id=context["order_id"],
            body=PartsUsageCreate(
                inventory_id=context["inventory_id"],
                quantity=Decimal("1.00"),
            ),
            db=db,
            current_user=mechanic,
        )


@pytest.mark.asyncio
@pytest.mark.skipif(
    not os.environ.get("DB003_POSTGRES_URL"),
    reason="requires isolated PostgreSQL 15",
)
async def test_price_mutation_serializes_with_quote_publication(monkeypatch):
    engine = create_async_engine(os.environ["DB003_POSTGRES_URL"])
    factory = async_sessionmaker(engine, expire_on_commit=False)
    context = await _seed_race_context(
        factory,
        status=RepairOrderStatus.QUOTED,
        with_quote=True,
    )
    entered = asyncio.Event()
    release = asyncio.Event()
    original_refresh = repair_orders._refresh_repair_order_totals

    async def _pause_before_price_commit(db, order_id: UUID):
        order = await original_refresh(db, order_id)
        entered.set()
        await release.wait()
        return order

    monkeypatch.setattr(repair_orders, "_refresh_repair_order_totals", _pause_before_price_commit)

    async def _publish():
        async with factory() as db:
            admin = await db.get(User, context["admin_id"])
            try:
                return await quotes.send_quote_to_customer(
                    quote_id=context["quote_id"],
                    db=db,
                    current_user=admin,
                )
            except HTTPException as exc:
                await db.rollback()
                return exc

    try:
        mutation_task = asyncio.create_task(_add_part(factory, context))
        await asyncio.wait_for(entered.wait(), timeout=5)
        publication_task = asyncio.create_task(_publish())
        await asyncio.sleep(0.2)
        assert publication_task.done() is False
        release.set()
        await mutation_task
        publication = await asyncio.wait_for(publication_task, timeout=5)

        assert isinstance(publication, HTTPException)
        assert publication.status_code == 409
        assert "stale" in publication.detail.lower()
        async with factory() as db:
            order = await db.get(RepairOrder, context["order_id"])
            quote = await db.get(Quote, context["quote_id"])
            inventory = await db.get(Inventory, context["inventory_id"])
            part_count = await db.scalar(
                select(func.count(PartsUsage.id)).where(
                    PartsUsage.repair_order_id == context["order_id"]
                )
            )
            history_count = await db.scalar(
                select(func.count(RepairOrderHistoryEvent.id)).where(
                    RepairOrderHistoryEvent.repair_order_id == context["order_id"],
                    RepairOrderHistoryEvent.event_type == "part_added",
                )
            )
        assert order.total_labor_cost == Decimal("100.00")
        assert order.total_parts_cost == Decimal("50.00")
        assert order.total_cost == Decimal("150.00")
        assert quote.sent_to_customer is False
        assert quote.line_items_snapshot is None
        assert part_count == 1
        assert history_count == 1
        assert inventory.stock_quantity == 4
    finally:
        release.set()
        await engine.dispose()


@pytest.mark.asyncio
@pytest.mark.skipif(
    not os.environ.get("DB003_POSTGRES_URL"),
    reason="requires isolated PostgreSQL 15",
)
async def test_price_mutation_serializes_with_invoice_finalization(monkeypatch):
    engine = create_async_engine(os.environ["DB003_POSTGRES_URL"])
    factory = async_sessionmaker(engine, expire_on_commit=False)
    context = await _seed_race_context(
        factory,
        status=RepairOrderStatus.PENDING_REVIEW,
        with_quote=False,
    )
    entered = asyncio.Event()
    release = asyncio.Event()
    original_refresh = repair_orders._refresh_repair_order_totals

    async def _pause_before_price_commit(db, order_id: UUID):
        order = await original_refresh(db, order_id)
        entered.set()
        await release.wait()
        return order

    async def _noop(*_args, **_kwargs):
        return None

    monkeypatch.setattr(repair_orders, "_refresh_repair_order_totals", _pause_before_price_commit)
    monkeypatch.setattr(invoices.settings, "PROVIDER_OUTBOX_ENABLED", True)
    monkeypatch.setattr(invoices, "notify_invoice_created", _noop)
    monkeypatch.setattr(repair_orders, "send_sms", _noop)

    async def _finalize():
        async with factory() as db:
            admin = await db.get(User, context["admin_id"])
            return await repair_orders.approve_completion(
                order_id=context["order_id"],
                body=repair_orders.ApproveCompletionRequest(),
                db=db,
                current_user=admin,
            )

    try:
        mutation_task = asyncio.create_task(_add_part(factory, context))
        await asyncio.wait_for(entered.wait(), timeout=5)
        finalization_task = asyncio.create_task(_finalize())
        await asyncio.sleep(0.2)
        assert finalization_task.done() is False
        release.set()
        await mutation_task
        finalized = await asyncio.wait_for(finalization_task, timeout=8)
        assert finalized.status == RepairOrderStatus.INVOICED

        async with factory() as db:
            order = await db.get(RepairOrder, context["order_id"])
            invoice = (
                await db.execute(
                    select(Invoice).where(Invoice.repair_order_id == context["order_id"])
                )
            ).scalar_one()
            part_count = await db.scalar(
                select(func.count(PartsUsage.id)).where(
                    PartsUsage.repair_order_id == context["order_id"]
                )
            )
        assert order.total_parts_cost == Decimal("50.00")
        assert order.total_labor_cost == Decimal("100.00")
        assert order.total_cost == Decimal("150.00")
        assert invoice.subtotal == Decimal("150.00")
        assert len(invoice.line_items_snapshot["parts"]) == 1
        assert invoice.line_items_snapshot["parts"][0]["total_price"] == "50.00"
        assert part_count == 1
    finally:
        release.set()
        await engine.dispose()
