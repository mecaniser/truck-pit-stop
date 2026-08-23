from __future__ import annotations

import os
from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import event, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api.v1.endpoints import quotes
from app.db.models.customer import Customer
from app.db.models.provider_outbox import ProviderOutboxEvent
from app.db.models.quote import Quote
from app.db.models.repair_order import RepairOrder, RepairOrderStatus
from app.db.models.tenant import Tenant
from app.db.models.user import User, UserRole
from app.db.models.user_customer_link import UserCustomerLink
from app.db.models.vehicle import Vehicle


@pytest.mark.asyncio
@pytest.mark.skipif(
    not os.environ.get("DB003_POSTGRES_URL"),
    reason="requires isolated PostgreSQL 15",
)
async def test_postgres_draft_quote_role_matrix_authorizes_before_quote_read():
    engine = create_async_engine(os.environ["DB003_POSTGRES_URL"])
    factory = async_sessionmaker(engine, expire_on_commit=False)
    suffix = uuid4().hex
    try:
        async with factory() as db:
            tenant = Tenant(
                name="PG quote role tenant",
                slug=f"pg-quote-role-{suffix}",
            )
            db.add(tenant)
            await db.flush()
            customer = Customer(
                tenant_id=tenant.id,
                first_name="Private",
                last_name="Customer",
                email=f"private-{suffix}@example.com",
            )
            db.add(customer)
            await db.flush()
            vehicle = Vehicle(
                tenant_id=tenant.id,
                customer_id=customer.id,
                make="Private Freightliner",
                model="Cascadia",
                year=2024,
            )
            db.add(vehicle)
            await db.flush()

            users = {
                role: User(
                    tenant_id=tenant.id,
                    email=f"{role.value}-{suffix}@example.com",
                    hashed_password="hashed-password",
                    first_name=role.value,
                    last_name="Actor",
                    role=role,
                    is_active=True,
                    is_verified=True,
                )
                for role in (
                    UserRole.GARAGE_OWNER,
                    UserRole.GARAGE_ADMIN,
                    UserRole.RECEPTIONIST,
                    UserRole.FLEET_MANAGER,
                    UserRole.DRIVER,
                    UserRole.SUPER_ADMIN,
                )
            }
            assigned_mechanic = User(
                tenant_id=tenant.id,
                email=f"assigned-{suffix}@example.com",
                hashed_password="hashed-password",
                first_name="Assigned",
                last_name="Mechanic",
                role=UserRole.MECHANIC,
                is_active=True,
                is_verified=True,
            )
            unassigned_mechanic = User(
                tenant_id=tenant.id,
                email=f"unassigned-{suffix}@example.com",
                hashed_password="hashed-password",
                first_name="Unassigned",
                last_name="Mechanic",
                role=UserRole.MECHANIC,
                is_active=True,
                is_verified=True,
            )
            direct_customer = User(
                tenant_id=tenant.id,
                customer_id=customer.id,
                email=f"direct-{suffix}@example.com",
                hashed_password="hashed-password",
                first_name="Direct",
                last_name="Customer",
                role=UserRole.CUSTOMER,
                is_active=True,
                is_verified=True,
            )
            linked_customer = User(
                tenant_id=None,
                customer_id=None,
                email=f"linked-{suffix}@example.com",
                hashed_password="hashed-password",
                first_name="Linked",
                last_name="Customer",
                role=UserRole.CUSTOMER,
                is_active=True,
                is_verified=True,
            )
            db.add_all(
                [
                    *users.values(),
                    assigned_mechanic,
                    unassigned_mechanic,
                    direct_customer,
                    linked_customer,
                ]
            )
            await db.flush()
            order = RepairOrder(
                tenant_id=tenant.id,
                customer_id=customer.id,
                vehicle_id=vehicle.id,
                assigned_mechanic_id=assigned_mechanic.id,
                order_number=f"PG-PRIVATE-RO-{suffix[:12]}",
                status=RepairOrderStatus.QUOTED,
                total_labor_cost=Decimal("100.00"),
                total_parts_cost=Decimal("0.00"),
                total_cost=Decimal("100.00"),
            )
            db.add(order)
            await db.flush()
            db.add(
                UserCustomerLink(
                    user_id=linked_customer.id,
                    customer_id=customer.id,
                    tenant_id=tenant.id,
                )
            )
            sent_quote = Quote(
                tenant_id=tenant.id,
                repair_order_id=order.id,
                quote_number=f"PG-PRIVATE-SENT-{suffix[:12]}",
                total_amount=Decimal("90.00"),
                revision=1,
                sent_to_customer=True,
            )
            draft_quote = Quote(
                tenant_id=tenant.id,
                repair_order_id=order.id,
                quote_number=f"PG-PRIVATE-DRAFT-{suffix[:12]}",
                total_amount=Decimal("100.00"),
                revision=2,
                sent_to_customer=False,
            )
            outbox = ProviderOutboxEvent(
                tenant_id=tenant.id,
                event_type="boundary.seed",
                aggregate_type="repair_order",
                aggregate_id=order.id,
                payload={"private": suffix},
                idempotency_key=f"pg-quote-role-boundary:{order.id}",
                status="pending",
                attempt_count=0,
                available_at=datetime.now(timezone.utc),
            )
            db.add_all([sent_quote, draft_quote, outbox])
            await db.commit()

            baseline = (
                await db.scalar(select(RepairOrder.total_cost).where(RepairOrder.id == order.id)),
                await db.scalar(select(Quote.total_amount).where(Quote.id == draft_quote.id)),
                await db.scalar(
                    select(ProviderOutboxEvent.attempt_count).where(
                        ProviderOutboxEvent.id == outbox.id
                    )
                ),
            )
            allowed = (
                users[UserRole.GARAGE_OWNER],
                users[UserRole.GARAGE_ADMIN],
                users[UserRole.RECEPTIONIST],
                assigned_mechanic,
            )
            denied = (
                (users[UserRole.FLEET_MANAGER], "Insufficient permissions"),
                (users[UserRole.DRIVER], "Insufficient permissions"),
                (users[UserRole.SUPER_ADMIN], "Insufficient permissions"),
                (unassigned_mechanic, "Access denied"),
                (direct_customer, "Insufficient permissions"),
                (linked_customer, "Insufficient permissions"),
            )

            for actor in allowed:
                response = await quotes.get_quote_by_repair_order(
                    repair_order_id=order.id,
                    db=db,
                    current_user=actor,
                )
                assert response is not None
                assert response.id == draft_quote.id
                assert response.total_amount == Decimal("100.00")

            for actor, expected_detail in denied:
                statements: list[str] = []

                def _capture_statement(_conn, _cursor, statement, *_args):
                    statements.append(statement.lower())

                event.listen(
                    engine.sync_engine,
                    "before_cursor_execute",
                    _capture_statement,
                )
                try:
                    with pytest.raises(HTTPException) as exc_info:
                        await quotes.get_quote_by_repair_order(
                            repair_order_id=order.id,
                            db=db,
                            current_user=actor,
                        )
                finally:
                    event.remove(
                        engine.sync_engine,
                        "before_cursor_execute",
                        _capture_statement,
                    )
                assert exc_info.value.status_code == 403
                assert exc_info.value.detail == expected_detail
                assert draft_quote.quote_number not in str(exc_info.value.detail)
                assert all(" from quotes" not in statement for statement in statements)

            assert (
                await db.scalar(select(RepairOrder.total_cost).where(RepairOrder.id == order.id)),
                await db.scalar(select(Quote.total_amount).where(Quote.id == draft_quote.id)),
                await db.scalar(
                    select(ProviderOutboxEvent.attempt_count).where(
                        ProviderOutboxEvent.id == outbox.id
                    )
                ),
            ) == baseline
    finally:
        await engine.dispose()
