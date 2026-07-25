from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.api.v1.endpoints import invoices, repair_orders
from app.db.models.customer import Customer
from app.db.models.invoice import Invoice
from app.db.models.labor import Labor, LaborLineType
from app.db.models.provider_outbox import ProviderOutboxEvent, ProviderOutboxStatus
from app.db.models.quote import Quote
from app.db.models.repair_order import RepairOrder, RepairOrderStatus
from app.db.models.tenant import Tenant
from app.db.models.user import User, UserRole
from app.db.models.vehicle import Vehicle


async def _seed_review_order(factory):
    suffix = uuid4().hex
    async with factory() as db:
        tenant = Tenant(name="Finalization Shop", slug=f"finalization-{suffix}")
        db.add(tenant)
        await db.flush()

        customer = Customer(
            tenant_id=tenant.id,
            first_name="Casey",
            last_name="Customer",
            email=f"casey-{suffix}@example.com",
        )
        db.add(customer)
        await db.flush()

        vehicle = Vehicle(
            tenant_id=tenant.id,
            customer_id=customer.id,
            make="Freightliner",
            model="Cascadia",
            year=2022,
        )
        manager = User(
            tenant_id=tenant.id,
            email=f"manager-{suffix}@example.com",
            hashed_password="hashed-password",
            first_name="Shop",
            last_name="Manager",
            role=UserRole.GARAGE_ADMIN,
            is_active=True,
            is_verified=True,
        )
        db.add_all([vehicle, manager])
        await db.flush()

        order = RepairOrder(
            tenant_id=tenant.id,
            customer_id=customer.id,
            vehicle_id=vehicle.id,
            order_number=f"RO-{suffix[:10]}",
            status=RepairOrderStatus.PENDING_REVIEW,
            is_internal=False,
            is_warranty_repair=False,
            is_pm=False,
            total_parts_cost=Decimal("0.00"),
            total_labor_cost=Decimal("225.00"),
            total_cost=Decimal("225.00"),
            work_started_at=datetime.now(timezone.utc),
            work_completed_at=datetime.now(timezone.utc),
        )
        db.add(order)
        await db.flush()
        db.add(
            Labor(
                tenant_id=tenant.id,
                repair_order_id=order.id,
                description="Electrical diagnosis",
                hours=Decimal("1.50"),
                hourly_rate=Decimal("150.00"),
                total_cost=Decimal("225.00"),
                line_type=LaborLineType.MANUAL,
            )
        )
        await db.commit()
        return order.id, manager.id


@pytest.mark.asyncio
async def test_finalization_commits_invoice_snapshot_and_order_state_together(
    _db_engine,
    monkeypatch,
):
    factory = async_sessionmaker(_db_engine, expire_on_commit=False)
    order_id, manager_id = await _seed_review_order(factory)

    async def _noop_notify(*_args, **_kwargs):
        return None

    monkeypatch.setattr(invoices.settings, "PROVIDER_OUTBOX_ENABLED", True)
    monkeypatch.setattr(invoices, "notify_invoice_created", _noop_notify)

    async with factory() as db:
        manager = await db.get(User, manager_id)
        response = await repair_orders.approve_completion(
            order_id=order_id,
            body=repair_orders.ApproveCompletionRequest(review_notes="Verified"),
            db=db,
            current_user=manager,
        )

    assert response.status == RepairOrderStatus.INVOICED

    async with factory() as db:
        order = await db.get(RepairOrder, order_id)
        invoice = (
            await db.execute(select(Invoice).where(Invoice.repair_order_id == order_id))
        ).scalar_one()
        outbox_event = (
            await db.execute(
                select(ProviderOutboxEvent).where(
                    ProviderOutboxEvent.aggregate_type == "invoice",
                    ProviderOutboxEvent.aggregate_id == invoice.id,
                )
            )
        ).scalar_one()

    assert order.status == RepairOrderStatus.INVOICED
    assert order.pricing_lock_reason == "invoice_finalized"
    assert order.pricing_locked_at is not None
    assert invoice.line_items_snapshot["labor"] == [
        {
            "description": "Electrical diagnosis",
            "hours": "1.50",
            "hourly_rate": "150.00",
            "total_cost": "225.00",
        }
    ]
    assert outbox_event.status == ProviderOutboxStatus.PENDING.value
    assert outbox_event.idempotency_key == f"invoice-email:{invoice.id}:created"


@pytest.mark.asyncio
async def test_invoice_failure_rolls_finalization_back_to_quality_review(
    _db_engine,
    monkeypatch,
):
    factory = async_sessionmaker(_db_engine, expire_on_commit=False)
    order_id, manager_id = await _seed_review_order(factory)

    async def _fail_invoice(*_args, **_kwargs):
        raise RuntimeError("invoice persistence failed")

    monkeypatch.setattr(invoices, "auto_create_invoice_for_order", _fail_invoice)

    async with factory() as db:
        manager = await db.get(User, manager_id)
        with pytest.raises(repair_orders.HTTPException) as exc_info:
            await repair_orders.approve_completion(
                order_id=order_id,
                body=repair_orders.ApproveCompletionRequest(review_notes="Verified"),
                db=db,
                current_user=manager,
            )

    assert exc_info.value.status_code == 500
    assert "No changes were saved" in exc_info.value.detail

    async with factory() as db:
        order = await db.get(RepairOrder, order_id)
        invoice = (
            await db.execute(select(Invoice).where(Invoice.repair_order_id == order_id))
        ).scalar_one_or_none()

    assert order.status == RepairOrderStatus.PENDING_REVIEW
    assert order.pricing_locked_at is None
    assert order.pricing_lock_reason is None
    assert invoice is None


@pytest.mark.asyncio
async def test_finalization_blocks_positive_work_above_customer_authorization(_db_engine):
    factory = async_sessionmaker(_db_engine, expire_on_commit=False)
    order_id, manager_id = await _seed_review_order(factory)

    async with factory() as db:
        order = await db.get(RepairOrder, order_id)
        db.add(
            Quote(
                tenant_id=order.tenant_id,
                repair_order_id=order.id,
                quote_number=f"Q-{uuid4().hex[:10]}",
                total_amount=Decimal("175.00"),
                is_approved=True,
                sent_to_customer=True,
                revision=1,
                authorization_type="initial_estimate",
                previously_authorized_amount=Decimal("0.00"),
                delta_amount=Decimal("175.00"),
            )
        )
        await db.commit()

    async with factory() as db:
        manager = await db.get(User, manager_id)
        with pytest.raises(repair_orders.HTTPException) as exc_info:
            await repair_orders.approve_completion(
                order_id=order_id,
                body=repair_orders.ApproveCompletionRequest(),
                db=db,
                current_user=manager,
            )

    assert exc_info.value.status_code == 409
    assert "additional $50.00" in exc_info.value.detail

    async with factory() as db:
        order = await db.get(RepairOrder, order_id)
        assert order.status == RepairOrderStatus.PENDING_REVIEW
        assert order.pricing_locked_at is None
