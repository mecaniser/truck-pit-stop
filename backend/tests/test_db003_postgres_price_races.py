from __future__ import annotations

import asyncio
import os
from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api.v1.endpoints import invoices, quotes, repair_orders
from app.db.models.customer import Customer
from app.db.models.inventory import Inventory, PartsUsage
from app.db.models.invoice import Invoice, InvoiceStatus
from app.db.models.labor import Labor, LaborLineType
from app.db.models.quote import Quote
from app.db.models.repair_order import RepairOrder, RepairOrderStatus
from app.db.models.repair_order_history import RepairOrderHistoryEvent
from app.db.models.repair_order_read_model import RepairOrderReadModel
from app.db.models.provider_outbox import ProviderOutboxEvent
from app.db.models.service import Service, ServicePart
from app.db.models.tenant import Tenant
from app.db.models.user import User, UserRole
from app.db.models.vehicle import Vehicle
from app.schemas.repair_order import (
    LaborCreate,
    PartsUsageCreate,
    PriceBuildFlatServiceRequest,
    PriceBuildRepairOpsApplyRequest,
)
from app.services.repair_operation_library import OperationEstimate


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


@pytest.mark.asyncio
@pytest.mark.skipif(
    not os.environ.get("DB003_POSTGRES_URL"),
    reason="requires isolated PostgreSQL 15",
)
async def test_projection_selects_one_latest_tenant_consistent_quote_and_invoice():
    engine = create_async_engine(os.environ["DB003_POSTGRES_URL"])
    factory = async_sessionmaker(engine, expire_on_commit=False)
    suffix = uuid4().hex
    active_invoice_created_at = datetime(2026, 1, 2, 12, 0, tzinfo=timezone.utc)
    try:
        async with factory() as db:
            tenant = Tenant(
                name="Projection Shop",
                slug=f"projection-{suffix}",
                email=f"projection-{suffix}@example.com",
            )
            other_tenant = Tenant(
                name="Other Projection Shop",
                slug=f"projection-other-{suffix}",
                email=f"projection-other-{suffix}@example.com",
            )
            db.add_all([tenant, other_tenant])
            await db.flush()
            customer = Customer(
                tenant_id=tenant.id,
                first_name="Projection",
                last_name="Customer",
                email=f"projection-customer-{suffix}@example.com",
            )
            db.add(customer)
            await db.flush()
            vehicle = Vehicle(
                tenant_id=tenant.id,
                customer_id=customer.id,
                make="Volvo",
                model="VNL",
                year=2024,
            )
            mechanic = User(
                tenant_id=tenant.id,
                email=f"projection-mechanic-{suffix}@example.com",
                hashed_password="hashed-password",
                first_name="Projection",
                last_name="Mechanic",
                role=UserRole.MECHANIC,
                is_active=True,
                is_verified=True,
            )
            db.add_all([vehicle, mechanic])
            await db.flush()
            order = RepairOrder(
                tenant_id=tenant.id,
                customer_id=customer.id,
                vehicle_id=vehicle.id,
                assigned_mechanic_id=mechanic.id,
                order_number=f"RO-PROJ-{suffix[:8]}",
                status=RepairOrderStatus.QUOTED,
                description="Projection cardinality",
                total_parts_cost=Decimal("0.00"),
                total_labor_cost=Decimal("150.00"),
                total_cost=Decimal("150.00"),
            )
            db.add(order)
            await db.commit()

            quote_one = Quote(
                tenant_id=tenant.id,
                repair_order_id=order.id,
                quote_number=f"Q-PROJ-1-{suffix[:8]}",
                total_amount=Decimal("100.00"),
                revision=1,
                authorization_type="initial_estimate",
                previously_authorized_amount=Decimal("0.00"),
                delta_amount=Decimal("100.00"),
                sent_to_customer=True,
                is_approved=True,
                is_declined=False,
                sent_at=datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc),
            )
            db.add(quote_one)
            await db.commit()
            created_revision = await quotes.create_quote(
                body=quotes.QuoteCreate(repair_order_id=order.id),
                db=db,
                current_user=mechanic,
            )
            assert created_revision.revision == 2
            assert created_revision.authorization_type == "additional_work"
            assert created_revision.previously_authorized_amount == Decimal("100.00")
            assert created_revision.delta_amount == Decimal("50.00")
            quote_two = await db.get(Quote, created_revision.id)

            # A higher revision carrying another tenant must never win.
            db.add(
                Quote(
                    tenant_id=other_tenant.id,
                    repair_order_id=order.id,
                    quote_number=f"Q-PROJ-X-{suffix[:8]}",
                    total_amount=Decimal("999.00"),
                    revision=99,
                    authorization_type="additional_work",
                    previously_authorized_amount=Decimal("0.00"),
                    delta_amount=Decimal("999.00"),
                    sent_to_customer=True,
                    is_approved=True,
                    is_declined=False,
                )
            )
            active_invoice = Invoice(
                tenant_id=tenant.id,
                repair_order_id=order.id,
                invoice_number=f"INV-PROJ-A-{suffix[:8]}",
                status=InvoiceStatus.PAID,
                subtotal=Decimal("150.00"),
                total_amount=Decimal("150.00"),
                created_at=active_invoice_created_at,
            )
            cancelled_invoice = Invoice(
                tenant_id=tenant.id,
                repair_order_id=order.id,
                invoice_number=f"INV-PROJ-C-{suffix[:8]}",
                status=InvoiceStatus.CANCELLED,
                subtotal=Decimal("175.00"),
                total_amount=Decimal("175.00"),
                created_at=datetime(2026, 2, 1, 12, 0, tzinfo=timezone.utc),
            )
            db.add_all([active_invoice, cancelled_invoice])
            await db.commit()

            projection = await db.get(RepairOrderReadModel, order.id)
            assert projection.payload["quote_sent"] is False
            assert projection.payload["quote_approved"] is False
            assert projection.payload["invoice_created_at"].startswith("2026-01-02T12:00:00")
            assert projection.payload["pending_zelle_confirmation"] is False
            assert await db.scalar(
                select(func.count(RepairOrderReadModel.repair_order_id)).where(
                    RepairOrderReadModel.repair_order_id == order.id
                )
            ) == 1
            legacy_items = await repair_orders._list_repair_orders_legacy(
                customer_id=None,
                vehicle_id=None,
                status=None,
                search=None,
                deleted=False,
                skip=0,
                limit=100,
                paginated=False,
                db=db,
                current_user=mechanic,
            )
            legacy_item = next(item for item in legacy_items if item.id == order.id)
            assert legacy_item.quote_sent is False
            assert legacy_item.quote_approved is False
            assert legacy_item.invoice_created_at == active_invoice_created_at

            quote_two.deleted_at = datetime.now(timezone.utc)
            await db.commit()
            await db.refresh(projection)
            assert projection.payload["quote_sent"] is True
            assert projection.payload["quote_approved"] is True

            active_invoice.status = InvoiceStatus.CANCELLED
            await db.commit()
            await db.refresh(projection)
            assert projection.payload["invoice_created_at"] is None
            assert projection.payload["invoice_due_date"] is None
            assert projection.payload["pending_zelle_confirmation"] is False

            await db.execute(text("SELECT refresh_repair_order_read_model(:order_id)"), {"order_id": order.id})
            await db.commit()
            assert await db.scalar(
                select(func.count(RepairOrderReadModel.repair_order_id)).where(
                    RepairOrderReadModel.repair_order_id == order.id
                )
            ) == 1
    finally:
        await engine.dispose()


@pytest.mark.asyncio
@pytest.mark.skipif(
    not os.environ.get("DB003_POSTGRES_URL"),
    reason="requires isolated PostgreSQL 15",
)
async def test_mechanic_rejections_leave_pricing_history_and_stock_unchanged():
    engine = create_async_engine(os.environ["DB003_POSTGRES_URL"])
    factory = async_sessionmaker(engine, expire_on_commit=False)
    context = await _seed_race_context(
        factory,
        status=RepairOrderStatus.QUOTED,
        with_quote=False,
    )
    try:
        async with factory() as db:
            mechanic = await db.get(User, context["mechanic_id"])
            inventory = await db.get(Inventory, context["inventory_id"])
            service = Service(
                tenant_id=mechanic.tenant_id,
                name="Thirty-minute inspection",
                duration_minutes=30,
                is_active=True,
            )
            db.add(service)
            await db.flush()
            db.add(
                ServicePart(
                    tenant_id=mechanic.tenant_id,
                    service_id=service.id,
                    inventory_id=inventory.id,
                    quantity=Decimal("1.00"),
                )
            )
            unassigned = User(
                tenant_id=mechanic.tenant_id,
                email=f"unassigned-{uuid4().hex}@example.com",
                hashed_password="hashed-password",
                first_name="Unassigned",
                last_name="Mechanic",
                role=UserRole.MECHANIC,
                is_active=True,
                is_verified=True,
            )
            other_tenant = Tenant(
                name="Cross Tenant",
                slug=f"cross-{uuid4().hex}",
                email=f"cross-{uuid4().hex}@example.com",
            )
            db.add_all([unassigned, other_tenant])
            await db.flush()
            cross_tenant = User(
                tenant_id=other_tenant.id,
                email=f"cross-mechanic-{uuid4().hex}@example.com",
                hashed_password="hashed-password",
                first_name="Cross",
                last_name="Mechanic",
                role=UserRole.MECHANIC,
                is_active=True,
                is_verified=True,
            )
            db.add(cross_tenant)
            await db.commit()

            await repair_orders.add_price_build_flat_service(
                order_id=context["order_id"],
                body=PriceBuildFlatServiceRequest(service_id=service.id),
                db=db,
                current_user=mechanic,
            )

        async with factory() as db:
            service = await db.get(Service, service.id)
            inventory = await db.get(Inventory, context["inventory_id"])
            service.duration_minutes = 120
            inventory.selling_price = Decimal("75.00")
            await db.commit()

        async def _expect_status(actor_id, operation, expected_status):
            async with factory() as db:
                actor = await db.get(User, actor_id)
                try:
                    await operation(db, actor)
                except HTTPException as exc:
                    assert exc.status_code == expected_status
                    await db.rollback()
                    return
                raise AssertionError(f"Expected HTTP {expected_status}")

        async def _invalid_labor(value):
            async def _run(db, actor):
                return await repair_orders.add_labor_to_repair_order(
                    order_id=context["order_id"],
                    body=LaborCreate.model_construct(
                        description="Invalid mechanic labor",
                        hours=Decimal(value),
                        hourly_rate=Decimal("100.00"),
                        mechanic_id=None,
                        service_code=None,
                        line_type=LaborLineType.MANUAL,
                        provider=None,
                        provider_operation_id=None,
                        auto_recalc_enabled=True,
                        source_service_id=None,
                        vendor_name=None,
                        vendor_cost=None,
                    ),
                    db=db,
                    current_user=actor,
                )

            return _run

        for value in ("-0.50", "0.00", "1000.00", "9999.99", "1.001"):
            await _expect_status(
                context["mechanic_id"],
                await _invalid_labor(value),
                422,
            )

        async def _negative_operation(db, actor):
            return await repair_orders.apply_price_build_repair_operation(
                order_id=context["order_id"],
                body=PriceBuildRepairOpsApplyRequest.model_construct(
                    operation_id="custom:negative-operation",
                    name="Invalid negative operation",
                    estimated_hours=Decimal("-0.25"),
                    auto_recalc_enabled=False,
                ),
                db=db,
                current_user=actor,
            )

        await _expect_status(context["mechanic_id"], _negative_operation, 422)

        async def _extreme_part_with_override(db, actor):
            return await repair_orders.add_parts_to_repair_order(
                order_id=context["order_id"],
                body=PartsUsageCreate.model_construct(
                    inventory_id=context["inventory_id"],
                    quantity=Decimal("9999.99"),
                    unit_price=None,
                    source_service_id=None,
                    source_line_id=None,
                    allow_stock_shortage=True,
                ),
                db=db,
                current_user=actor,
            )

        await _expect_status(
            context["mechanic_id"], _extreme_part_with_override, 422
        )

        async def _duplicate_flat_service(db, actor):
            return await repair_orders.add_price_build_flat_service(
                order_id=context["order_id"],
                body=PriceBuildFlatServiceRequest(service_id=service.id),
                db=db,
                current_user=actor,
            )

        async def _duplicate_via_operation(db, actor):
            return await repair_orders.apply_price_build_repair_operation(
                order_id=context["order_id"],
                body=PriceBuildRepairOpsApplyRequest(operation_id=f"service:{service.id}"),
                db=db,
                current_user=actor,
            )

        await _expect_status(context["mechanic_id"], _duplicate_flat_service, 409)
        await _expect_status(context["mechanic_id"], _duplicate_via_operation, 409)
        async def _valid_labor(db, actor):
            return await repair_orders.add_labor_to_repair_order(
                order_id=context["order_id"],
                body=LaborCreate(
                    description="Authorization boundary labor",
                    hours=Decimal("1.00"),
                    hourly_rate=Decimal("100.00"),
                ),
                db=db,
                current_user=actor,
            )

        async def _cross_tenant_part(db, actor):
            return await repair_orders.add_parts_to_repair_order(
                order_id=context["order_id"],
                body=PartsUsageCreate(
                    inventory_id=context["inventory_id"],
                    quantity=Decimal("1.00"),
                ),
                db=db,
                current_user=actor,
            )

        async def _cross_tenant_flat_service(db, actor):
            return await repair_orders.add_price_build_flat_service(
                order_id=context["order_id"],
                body=PriceBuildFlatServiceRequest(service_id=service.id),
                db=db,
                current_user=actor,
            )

        async def _cross_tenant_repair_operation(db, actor):
            return await repair_orders.apply_price_build_repair_operation(
                order_id=context["order_id"],
                body=PriceBuildRepairOpsApplyRequest(
                    operation_id="custom:cross-tenant",
                    name="Cross tenant operation",
                    estimated_hours=Decimal("1.00"),
                    auto_recalc_enabled=False,
                ),
                db=db,
                current_user=actor,
            )

        await _expect_status(unassigned.id, _valid_labor, 403)
        for operation in (
            _valid_labor,
            _cross_tenant_part,
            _cross_tenant_flat_service,
            _cross_tenant_repair_operation,
        ):
            await _expect_status(cross_tenant.id, operation, 404)

        async with factory() as db:
            order = await db.get(RepairOrder, context["order_id"])
            inventory = await db.get(Inventory, context["inventory_id"])
            labor_rows = (
                await db.execute(
                    select(Labor)
                    .where(Labor.repair_order_id == context["order_id"])
                    .order_by(Labor.created_at, Labor.id)
                )
            ).scalars().all()
            part_rows = (
                await db.execute(
                    select(PartsUsage).where(PartsUsage.repair_order_id == context["order_id"])
                )
            ).scalars().all()
            assert len(labor_rows) == 2
            service_line = next(line for line in labor_rows if line.source_service_id == service.id)
            assert service_line.hours == Decimal("0.50")
            assert service_line.total_cost == Decimal("50.00")
            assert len(part_rows) == 1
            assert part_rows[0].unit_price == Decimal("50.00")
            assert part_rows[0].total_price == Decimal("50.00")
            assert inventory.stock_quantity == 4
            assert order.total_labor_cost == Decimal("150.00")
            assert order.total_parts_cost == Decimal("50.00")
            assert order.total_cost == Decimal("200.00")
            assert await db.scalar(
                select(func.count(RepairOrderHistoryEvent.id)).where(
                    RepairOrderHistoryEvent.repair_order_id == context["order_id"]
                )
            ) == 0
            assert await db.scalar(
                select(func.count(Quote.id)).where(Quote.repair_order_id == context["order_id"])
            ) == 0
    finally:
        await engine.dispose()


async def _run_mechanic_reassignment_race(monkeypatch, *, operation: str) -> None:
    engine = create_async_engine(os.environ["DB003_POSTGRES_URL"])
    factory = async_sessionmaker(engine, expire_on_commit=False)
    context = await _seed_race_context(
        factory,
        status=RepairOrderStatus.QUOTED,
        with_quote=False,
    )
    entered_locked_reload = asyncio.Event()
    release_locked_reload = asyncio.Event()
    original_load_order = repair_orders.price_build_service.load_order

    async def _pause_before_locked_reload(
        db,
        order_id,
        *,
        for_update=False,
        tenant_id=None,
    ):
        if for_update:
            entered_locked_reload.set()
            await release_locked_reload.wait()
        return await original_load_order(
            db,
            order_id,
            for_update=for_update,
            tenant_id=tenant_id,
        )

    monkeypatch.setattr(
        repair_orders.price_build_service,
        "load_order",
        _pause_before_locked_reload,
    )

    try:
        async with factory() as db:
            mechanic = await db.get(User, context["mechanic_id"])
            inventory = await db.get(Inventory, context["inventory_id"])
            replacement = User(
                tenant_id=mechanic.tenant_id,
                email=f"replacement-{uuid4().hex}@example.com",
                hashed_password="hashed-password",
                first_name="Replacement",
                last_name="Mechanic",
                role=UserRole.MECHANIC,
                is_active=True,
                is_verified=True,
            )
            service = Service(
                tenant_id=mechanic.tenant_id,
                name="Race service",
                duration_minutes=30,
                is_active=True,
            )
            db.add_all([replacement, service])
            await db.flush()
            db.add(
                ServicePart(
                    tenant_id=mechanic.tenant_id,
                    service_id=service.id,
                    inventory_id=inventory.id,
                    quantity=Decimal("1.00"),
                )
            )
            await db.commit()
            replacement_id = replacement.id
            service_id = service.id

        async def _attempt_as_original_mechanic():
            async with factory() as db:
                mechanic = await db.get(User, context["mechanic_id"])
                try:
                    if operation == "flat_service":
                        return await repair_orders.add_price_build_flat_service(
                            order_id=context["order_id"],
                            body=PriceBuildFlatServiceRequest(service_id=service_id),
                            db=db,
                            current_user=mechanic,
                        )
                    return await repair_orders.apply_price_build_repair_operation(
                        order_id=context["order_id"],
                        body=PriceBuildRepairOpsApplyRequest(
                            operation_id="custom:reassignment-race",
                            name="Reassignment race operation",
                            estimated_hours=Decimal("1.00"),
                            auto_recalc_enabled=False,
                        ),
                        db=db,
                        current_user=mechanic,
                    )
                except HTTPException as exc:
                    await db.rollback()
                    return exc

        attempt = asyncio.create_task(_attempt_as_original_mechanic())
        await asyncio.wait_for(entered_locked_reload.wait(), timeout=5)

        async with factory() as db:
            order = (
                await db.execute(
                    select(RepairOrder)
                    .where(RepairOrder.id == context["order_id"])
                    .with_for_update()
                )
            ).scalar_one()
            order.assigned_mechanic_id = replacement_id
            await db.commit()

        release_locked_reload.set()
        rejected = await asyncio.wait_for(attempt, timeout=8)
        assert isinstance(rejected, HTTPException)
        assert rejected.status_code == 403
        assert rejected.detail == "Access denied"

        async with factory() as db:
            order = await db.get(RepairOrder, context["order_id"])
            inventory = await db.get(Inventory, context["inventory_id"])
            assert order.assigned_mechanic_id == replacement_id
            assert order.total_labor_cost == Decimal("100.00")
            assert order.total_parts_cost == Decimal("0.00")
            assert order.total_cost == Decimal("100.00")
            assert inventory.stock_quantity == 5
            assert await db.scalar(
                select(func.count(Labor.id)).where(
                    Labor.repair_order_id == context["order_id"]
                )
            ) == 1
            assert await db.scalar(
                select(func.count(PartsUsage.id)).where(
                    PartsUsage.repair_order_id == context["order_id"]
                )
            ) == 0
            assert await db.scalar(
                select(func.count(RepairOrderHistoryEvent.id)).where(
                    RepairOrderHistoryEvent.repair_order_id == context["order_id"]
                )
            ) == 0
            assert await db.scalar(
                select(func.count(Quote.id)).where(
                    Quote.repair_order_id == context["order_id"]
                )
            ) == 0
            assert await db.scalar(
                select(func.count(ProviderOutboxEvent.id)).where(
                    ProviderOutboxEvent.aggregate_id == context["order_id"]
                )
            ) == 0
    finally:
        release_locked_reload.set()
        await engine.dispose()


@pytest.mark.asyncio
@pytest.mark.skipif(
    not os.environ.get("DB003_POSTGRES_URL"),
    reason="requires isolated PostgreSQL 15",
)
async def test_flat_service_rechecks_mechanic_assignment_under_lock(monkeypatch):
    await _run_mechanic_reassignment_race(monkeypatch, operation="flat_service")


@pytest.mark.asyncio
@pytest.mark.skipif(
    not os.environ.get("DB003_POSTGRES_URL"),
    reason="requires isolated PostgreSQL 15",
)
async def test_repair_operation_rechecks_mechanic_assignment_under_lock(monkeypatch):
    await _run_mechanic_reassignment_race(monkeypatch, operation="repair_operation")


async def _seed_generated_recalculation(factory):
    context = await _seed_race_context(
        factory,
        status=RepairOrderStatus.QUOTED,
        with_quote=False,
    )
    async with factory() as db:
        line = (
            await db.execute(
                select(Labor).where(
                    Labor.repair_order_id == context["order_id"]
                )
            )
        ).scalar_one()
        line.line_type = LaborLineType.REPAIR_OPERATION
        line.provider = "test_provider"
        line.provider_operation_id = "generated-recalculation"
        line.auto_recalc_enabled = True
        await db.commit()
        context["line_id"] = line.id
    return context


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "invalid_hours",
    [Decimal("0.00"), Decimal("NaN"), Decimal("1.001"), Decimal("1000.00")],
)
@pytest.mark.skipif(
    not os.environ.get("DB003_POSTGRES_URL"),
    reason="requires isolated PostgreSQL 15",
)
async def test_generated_recalculation_rejects_invalid_hours_atomically(
    monkeypatch,
    invalid_hours,
):
    engine = create_async_engine(os.environ["DB003_POSTGRES_URL"])
    factory = async_sessionmaker(engine, expire_on_commit=False)
    context = await _seed_generated_recalculation(factory)

    async def _invalid_estimate(*_args, **_kwargs):
        return OperationEstimate(
            operation_id="generated-recalculation",
            name="Generated recalculation",
            description="Invalid generated estimate",
            estimated_hours=invalid_hours,
            warnings=[],
            provider="test_provider",
        )

    monkeypatch.setattr(
        repair_orders.price_build_service,
        "_get_operation_estimate",
        _invalid_estimate,
    )
    try:
        async with factory() as db:
            admin = await db.get(User, context["admin_id"])
            with pytest.raises(HTTPException) as exc_info:
                await repair_orders.recalculate_price_build(
                    order_id=context["order_id"],
                    db=db,
                    current_user=admin,
                )
            assert exc_info.value.status_code == 422
            assert exc_info.value.detail == (
                "Labor hours must be finite from 0.01 through 999.99 "
                "with at most two decimal places"
            )
            await db.rollback()

        async with factory() as db:
            order = await db.get(RepairOrder, context["order_id"])
            line = await db.get(Labor, context["line_id"])
            assert line.hours == Decimal("1.00")
            assert line.hourly_rate == Decimal("100.00")
            assert line.total_cost == Decimal("100.00")
            assert order.total_labor_cost == Decimal("100.00")
            assert order.total_parts_cost == Decimal("0.00")
            assert order.total_cost == Decimal("100.00")
            assert await db.scalar(
                select(func.count(RepairOrderHistoryEvent.id)).where(
                    RepairOrderHistoryEvent.repair_order_id == context["order_id"]
                )
            ) == 0
            assert await db.scalar(
                select(func.count(Quote.id)).where(
                    Quote.repair_order_id == context["order_id"]
                )
            ) == 0
            assert await db.scalar(
                select(func.count(ProviderOutboxEvent.id)).where(
                    ProviderOutboxEvent.aggregate_id == context["order_id"]
                )
            ) == 0
    finally:
        await engine.dispose()


@pytest.mark.asyncio
@pytest.mark.skipif(
    not os.environ.get("DB003_POSTGRES_URL"),
    reason="requires isolated PostgreSQL 15",
)
async def test_generated_recalculation_accepts_valid_hours(monkeypatch):
    engine = create_async_engine(os.environ["DB003_POSTGRES_URL"])
    factory = async_sessionmaker(engine, expire_on_commit=False)
    context = await _seed_generated_recalculation(factory)

    async def _valid_estimate(*_args, **_kwargs):
        return OperationEstimate(
            operation_id="generated-recalculation",
            name="Generated recalculation",
            description="Valid generated estimate",
            estimated_hours=Decimal("2.50"),
            warnings=[],
            provider="test_provider",
        )

    monkeypatch.setattr(
        repair_orders.price_build_service,
        "_get_operation_estimate",
        _valid_estimate,
    )
    try:
        async with factory() as db:
            order = await repair_orders.price_build_service.load_order(
                db, context["order_id"]
            )
            result = await repair_orders.price_build_service.recalculate_order(
                db, order
            )
            line = next(
                item for item in result.order.labor_items
                if item.id == context["line_id"]
            )
            assert line.hours == Decimal("2.50")
            assert line.total_cost == Decimal("250.00")
            assert result.order.total_labor_cost == Decimal("250.00")
            assert result.order.total_cost == Decimal("250.00")
    finally:
        await engine.dispose()
