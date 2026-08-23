from __future__ import annotations

import os
from dataclasses import FrozenInstanceError
from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.security import create_access_token
from app.core.dependencies import RequestUserPrincipal
from app.db.models.customer import Customer
from app.db.models.quote import Quote
from app.db.models.repair_order import RepairOrder, RepairOrderStatus
from app.db.models.repair_order_history import RepairOrderHistoryEvent
from app.db.models.provider_outbox import ProviderOutboxEvent
from app.db.models.tenant import Tenant
from app.db.models.user import User, UserRole
from app.db.models.user_customer_link import UserCustomerLink
from app.db.models.vehicle import Vehicle
from app.db.session import get_db


async def _add_customer_authorization(
    db,
    *,
    tenant: Tenant,
    suffix: str,
    revision: int,
) -> tuple[Customer, RepairOrder, Quote]:
    customer = Customer(
        tenant_id=tenant.id,
        first_name=f"Customer-{suffix}",
        last_name="Principal",
        email=f"customer-{suffix}@example.com",
    )
    db.add(customer)
    await db.flush()
    vehicle = Vehicle(
        tenant_id=tenant.id,
        customer_id=customer.id,
        make="Freightliner",
        model="Cascadia",
        year=2024,
    )
    db.add(vehicle)
    await db.flush()
    order = RepairOrder(
        tenant_id=tenant.id,
        customer_id=customer.id,
        vehicle_id=vehicle.id,
        order_number=f"PRINCIPAL-RO-{suffix}",
        status=RepairOrderStatus.QUOTED,
        total_labor_cost=Decimal("100.00"),
        total_parts_cost=Decimal("0.00"),
        total_cost=Decimal("100.00"),
    )
    db.add(order)
    await db.flush()
    quote = Quote(
        tenant_id=tenant.id,
        repair_order_id=order.id,
        quote_number=f"PRINCIPAL-Q-{suffix}",
        total_amount=Decimal("100.00"),
        revision=revision,
        authorization_type=("initial_estimate" if revision == 1 else "additional_work"),
        previously_authorized_amount=(Decimal("0.00") if revision == 1 else Decimal("90.00")),
        delta_amount=(Decimal("100.00") if revision == 1 else Decimal("10.00")),
        sent_to_customer=True,
        sent_at=datetime.now(timezone.utc),
        approval_token=uuid4().hex + uuid4().hex,
    )
    db.add(quote)
    await db.flush()
    return customer, order, quote


def _headers(user_id, tenant_id) -> dict[str, str]:
    token = create_access_token(
        {"sub": str(user_id)},
        tenant_id=str(tenant_id),
    )
    return {"Authorization": f"Bearer {token}"}


def test_request_principal_rejects_all_attribute_assignment():
    identity = User(
        email="principal-immutable@example.com",
        hashed_password="hashed-password",
        first_name="Immutable",
        last_name="Principal",
        role=UserRole.CUSTOMER,
    )
    tenant_id = uuid4()
    customer_id = uuid4()
    principal = RequestUserPrincipal(
        identity=identity,
        tenant_id=tenant_id,
        customer_id=customer_id,
    )

    assert principal.email == identity.email
    with pytest.raises(FrozenInstanceError):
        principal.tenant_id = uuid4()
    with pytest.raises(FrozenInstanceError):
        principal.customer_id = uuid4()
    with pytest.raises(FrozenInstanceError):
        principal.email = "mutated@example.com"

    assert principal.tenant_id == tenant_id
    assert principal.customer_id == customer_id
    assert identity.tenant_id is None
    assert identity.customer_id is None
    assert identity.email == "principal-immutable@example.com"


@pytest.mark.asyncio
@pytest.mark.skipif(
    not os.environ.get("DB003_POSTGRES_URL"),
    reason="requires isolated PostgreSQL 15",
)
async def test_linked_customer_context_never_persists_through_authorization_commits(
    monkeypatch,
):
    from app.api.v1.endpoints import quotes
    from app.core import dependencies as dependencies_module
    from app.core import redis as redis_module
    from app.middleware import idempotency as idempotency_module
    from app.middleware import throttling as throttling_module
    from app.main import app
    from conftest import FakeRedis

    engine = create_async_engine(os.environ["DB003_POSTGRES_URL"])
    factory = async_sessionmaker(engine, expire_on_commit=False)
    original_override = app.dependency_overrides.get(get_db)
    websocket_events: list[dict] = []
    linked_customer_gate_orders: list[object] = []

    async def _postgres_db():
        async with factory() as db:
            yield db

    async def _capture_websocket(**event):
        websocket_events.append(event)

    original_require_linked_customer = quotes._require_linked_customer

    async def _capture_linked_customer_gate(db, *, current_user, order):
        linked_customer_gate_orders.append(order.id)
        return await original_require_linked_customer(
            db,
            current_user=current_user,
            order=order,
        )

    fake_redis = FakeRedis()

    async def _fake_get_redis():
        return fake_redis

    async def _valid_token_state(_jti, _user_id):
        return False, 0

    monkeypatch.setattr(quotes, "broadcast_quote_event", _capture_websocket)
    monkeypatch.setattr(
        quotes,
        "broadcast_repair_order_update",
        _capture_websocket,
    )
    monkeypatch.setattr(
        quotes,
        "_require_linked_customer",
        _capture_linked_customer_gate,
    )
    monkeypatch.setattr(
        dependencies_module,
        "get_auth_token_state",
        _valid_token_state,
    )
    monkeypatch.setattr(redis_module, "get_redis", _fake_get_redis)
    monkeypatch.setattr(redis_module, "redis_client", fake_redis)
    monkeypatch.setattr(throttling_module, "get_redis", _fake_get_redis)
    monkeypatch.setattr(idempotency_module, "get_redis", _fake_get_redis)
    app.dependency_overrides[get_db] = _postgres_db

    suffix = uuid4().hex[:10]
    try:
        async with factory() as db:
            tenant_a = Tenant(name="Principal shop A", slug=f"principal-a-{suffix}")
            tenant_b = Tenant(name="Principal shop B", slug=f"principal-b-{suffix}")
            db.add_all([tenant_a, tenant_b])
            await db.flush()

            approve_customer, approve_order, approve_quote = (
                await _add_customer_authorization(
                    db,
                    tenant=tenant_a,
                    suffix=f"APPROVE-{suffix}",
                    revision=1,
                )
            )
            collision_customer, collision_order, collision_quote = (
                await _add_customer_authorization(
                    db,
                    tenant=tenant_a,
                    suffix=f"COLLISION-{suffix}",
                    revision=2,
                )
            )
            decline_customer, decline_order, decline_quote = (
                await _add_customer_authorization(
                    db,
                    tenant=tenant_a,
                    suffix=f"DECLINE-{suffix}",
                    revision=1,
                )
            )
            foreign_customer, foreign_order, foreign_quote = (
                await _add_customer_authorization(
                    db,
                    tenant=tenant_b,
                    suffix=f"FOREIGN-{suffix}",
                    revision=1,
                )
            )

            linked_approve = User(
                tenant_id=None,
                customer_id=None,
                email=f"linked-approve-{suffix}@example.com",
                hashed_password="hashed-password",
                first_name="Linked",
                last_name="Approve",
                role=UserRole.CUSTOMER,
                is_active=True,
                is_verified=True,
            )
            linked_collision = User(
                tenant_id=None,
                customer_id=None,
                email=f"linked-collision-{suffix}@example.com",
                hashed_password="hashed-password",
                first_name="Linked",
                last_name="Collision",
                role=UserRole.CUSTOMER,
                is_active=True,
                is_verified=True,
            )
            direct_collision = User(
                tenant_id=tenant_a.id,
                customer_id=collision_customer.id,
                email=f"direct-collision-{suffix}@example.com",
                hashed_password="hashed-password",
                first_name="Direct",
                last_name="Collision",
                role=UserRole.CUSTOMER,
                is_active=True,
                is_verified=True,
            )
            linked_decline = User(
                tenant_id=None,
                customer_id=None,
                email=f"linked-decline-{suffix}@example.com",
                hashed_password="hashed-password",
                first_name="Linked",
                last_name="Decline",
                role=UserRole.CUSTOMER,
                is_active=True,
                is_verified=True,
            )
            db.add_all(
                [
                    linked_approve,
                    linked_collision,
                    direct_collision,
                    linked_decline,
                ]
            )
            await db.flush()
            db.add_all(
                [
                    UserCustomerLink(
                        user_id=linked_approve.id,
                        customer_id=approve_customer.id,
                        tenant_id=tenant_a.id,
                    ),
                    UserCustomerLink(
                        user_id=linked_approve.id,
                        customer_id=foreign_customer.id,
                        tenant_id=tenant_b.id,
                    ),
                    UserCustomerLink(
                        user_id=linked_collision.id,
                        customer_id=collision_customer.id,
                        tenant_id=tenant_a.id,
                    ),
                    UserCustomerLink(
                        user_id=linked_decline.id,
                        customer_id=decline_customer.id,
                        tenant_id=tenant_a.id,
                    ),
                ]
            )
            await db.commit()

            ids = {
                "tenant_a": tenant_a.id,
                "tenant_b": tenant_b.id,
                "linked_approve": linked_approve.id,
                "linked_collision": linked_collision.id,
                "direct_collision": direct_collision.id,
                "collision_customer": collision_customer.id,
                "linked_decline": linked_decline.id,
                "approve_customer": approve_customer.id,
                "approve_order": approve_order.id,
                "approve_quote": approve_quote.id,
                "approve_token": approve_quote.approval_token,
                "collision_quote": collision_quote.id,
                "decline_quote": decline_quote.id,
                "foreign_quote": foreign_quote.id,
                "foreign_order": foreign_order.id,
                "foreign_customer": foreign_customer.id,
            }

        approve_headers = _headers(ids["linked_approve"], ids["tenant_a"])
        collision_headers = _headers(ids["linked_collision"], ids["tenant_a"])
        decline_headers = _headers(ids["linked_decline"], ids["tenant_a"])

        async with factory() as db:
            foreign_quote_before = await db.get(Quote, ids["foreign_quote"])
            foreign_order_before = await db.get(RepairOrder, ids["foreign_order"])
            assert foreign_quote_before is not None
            assert foreign_order_before is not None
            foreign_effects_before = {
                "quote_approved": foreign_quote_before.is_approved,
                "quote_declined": foreign_quote_before.is_declined,
                "quote_total": foreign_quote_before.total_amount,
                "order_total": foreign_order_before.total_cost,
                "history": (
                    await db.execute(
                        select(func.count(RepairOrderHistoryEvent.id)).where(
                            RepairOrderHistoryEvent.repair_order_id
                            == ids["foreign_order"]
                        )
                    )
                ).scalar_one(),
                "outbox": (
                    await db.execute(select(func.count(ProviderOutboxEvent.id)))
                ).scalar_one(),
            }

        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            approved = await client.post(
                f"/api/v1/quotes/{ids['approve_quote']}/approve",
                headers=approve_headers,
            )
            assert approved.status_code == 200
            assert approved.json()["is_approved"] is True

            collision_approved = await client.post(
                f"/api/v1/quotes/{ids['collision_quote']}/approve",
                headers=collision_headers,
            )
            assert collision_approved.status_code == 200
            assert collision_approved.json()["revision"] == 2

            declined = await client.post(
                f"/api/v1/quotes/{ids['decline_quote']}/decline",
                json={"notes": "Customer declined additional work"},
                headers=decline_headers,
            )
            assert declined.status_code == 200
            assert declined.json()["is_declined"] is True
            successful_event_count = len(websocket_events)

            error_response = await client.post(
                f"/api/v1/quotes/{ids['approve_quote']}/decline",
                json={"notes": "Must remain approved"},
                headers=approve_headers,
            )
            assert error_response.status_code == 409
            assert error_response.json()["detail"] == (
                "Cannot decline an already approved quote"
            )

            cross_tenant = await client.post(
                f"/api/v1/quotes/{ids['foreign_quote']}/approve",
                headers=approve_headers,
            )
            assert cross_tenant.status_code == 404
            assert "foreign" not in cross_tenant.text.lower()
            assert len(websocket_events) == successful_event_count
            assert ids["foreign_order"] not in linked_customer_gate_orders

            foreign_history = await client.get(
                f"/api/v1/quotes/repair-order/{ids['foreign_order']}/history",
                headers=approve_headers,
            )
            assert foreign_history.status_code == 404
            assert foreign_history.json()["detail"] == "Repair order not found"
            assert ids["foreign_order"] not in linked_customer_gate_orders

            async with factory() as db:
                denied_quote = await db.get(Quote, ids["foreign_quote"])
                denied_order = await db.get(RepairOrder, ids["foreign_order"])
                assert denied_quote is not None
                assert denied_order is not None
                assert {
                    "quote_approved": denied_quote.is_approved,
                    "quote_declined": denied_quote.is_declined,
                    "quote_total": denied_quote.total_amount,
                    "order_total": denied_order.total_cost,
                    "history": (
                        await db.execute(
                            select(func.count(RepairOrderHistoryEvent.id)).where(
                                RepairOrderHistoryEvent.repair_order_id
                                == ids["foreign_order"]
                            )
                        )
                    ).scalar_one(),
                    "outbox": (
                        await db.execute(select(func.count(ProviderOutboxEvent.id)))
                    ).scalar_one(),
                } == foreign_effects_before
            assert len(websocket_events) == successful_event_count

            selected_b_headers = _headers(ids["linked_approve"], ids["tenant_b"])
            selected_b_history = await client.get(
                f"/api/v1/quotes/repair-order/{ids['foreign_order']}/history",
                headers=selected_b_headers,
            )
            assert selected_b_history.status_code == 200
            assert [item["id"] for item in selected_b_history.json()["revisions"]] == [
                str(ids["foreign_quote"])
            ]

            selected_b_approved = await client.post(
                f"/api/v1/quotes/{ids['foreign_quote']}/approve",
                headers=selected_b_headers,
            )
            assert selected_b_approved.status_code == 200
            assert selected_b_approved.json()["is_approved"] is True

            selected_b_target_a = await client.get(
                f"/api/v1/quotes/repair-order/{ids['approve_order']}/history",
                headers=selected_b_headers,
            )
            assert selected_b_target_a.status_code == 404
            assert selected_b_target_a.json()["detail"] == "Repair order not found"

            async with factory() as db:
                selected_b_link = (
                    await db.execute(
                        select(UserCustomerLink).where(
                            UserCustomerLink.user_id == ids["linked_approve"],
                            UserCustomerLink.tenant_id == ids["tenant_b"],
                        )
                    )
                ).scalar_one()
                selected_b_link.deleted_at = datetime.now(timezone.utc)
                await db.commit()

            deleted_link = await client.get(
                f"/api/v1/quotes/repair-order/{ids['foreign_order']}/history",
                headers=selected_b_headers,
            )
            assert deleted_link.status_code == 403
            assert deleted_link.json()["detail"] == "Shop access denied"

            async with factory() as db:
                selected_b_link = (
                    await db.execute(
                        select(UserCustomerLink).where(
                            UserCustomerLink.user_id == ids["linked_approve"],
                            UserCustomerLink.tenant_id == ids["tenant_b"],
                        )
                    )
                ).scalar_one()
                selected_b_link.deleted_at = None
                selected_b_link.customer_id = ids["approve_customer"]
                await db.commit()

            mismatched_link = await client.get(
                f"/api/v1/quotes/repair-order/{ids['foreign_order']}/history",
                headers=selected_b_headers,
            )
            assert mismatched_link.status_code == 403
            assert mismatched_link.json()["detail"] == "Shop access denied"

            async with factory() as db:
                selected_b_link = (
                    await db.execute(
                        select(UserCustomerLink).where(
                            UserCustomerLink.user_id == ids["linked_approve"],
                            UserCustomerLink.tenant_id == ids["tenant_b"],
                        )
                    )
                ).scalar_one()
                selected_b_link.customer_id = ids["foreign_customer"]
                selected_b_customer = await db.get(Customer, ids["foreign_customer"])
                assert selected_b_customer is not None
                selected_b_customer.deleted_at = datetime.now(timezone.utc)
                await db.commit()

            deleted_customer = await client.get(
                f"/api/v1/quotes/repair-order/{ids['foreign_order']}/history",
                headers=selected_b_headers,
            )
            assert deleted_customer.status_code == 403
            assert deleted_customer.json()["detail"] == "Shop access denied"

            current_identity = await client.get(
                "/api/v1/auth/me",
                headers=approve_headers,
            )
            assert current_identity.status_code == 200
            assert current_identity.json()["tenant_id"] == str(ids["tenant_a"])
            assert current_identity.json()["customer_id"] == str(
                ids["approve_customer"]
            )

            history = await client.get(
                f"/api/v1/quotes/repair-order/{ids['approve_order']}/history",
                headers=approve_headers,
            )
            assert history.status_code == 200
            assert [item["id"] for item in history.json()["revisions"]] == [
                str(ids["approve_quote"])
            ]

            public_quote = await client.get(
                f"/api/v1/quotes/token/{ids['approve_token']}"
            )
            assert public_quote.status_code == 200
            assert public_quote.json()["quote"]["id"] == str(ids["approve_quote"])

        async with factory() as db:
            linked_rows = (
                await db.execute(
                    select(User).where(
                        User.id.in_(
                            (
                                ids["linked_approve"],
                                ids["linked_collision"],
                                ids["linked_decline"],
                            )
                        )
                    )
                )
            ).scalars().all()
            assert len(linked_rows) == 3
            assert {
                (row.tenant_id, row.customer_id) for row in linked_rows
            } == {(None, None)}
            direct = await db.get(User, ids["direct_collision"])
            assert direct is not None
            assert direct.tenant_id == ids["tenant_a"]
            assert direct.customer_id == ids["collision_customer"]
            persisted_foreign = await db.get(Quote, ids["foreign_quote"])
            assert persisted_foreign is not None
            assert persisted_foreign.is_approved is True
            persisted_approved = await db.get(Quote, ids["approve_quote"])
            assert persisted_approved is not None
            assert persisted_approved.is_approved is True
            assert persisted_approved.is_declined is False

            # Both successful selected contexts committed without projecting
            # either shop/customer pair onto the provider-neutral User row.
            selected_identity = await db.get(User, ids["linked_approve"])
            assert selected_identity is not None
            assert selected_identity.tenant_id is None
            assert selected_identity.customer_id is None
            await db.rollback()

        async with factory() as fresh_db:
            fresh_identity = await fresh_db.get(User, ids["linked_approve"])
            assert fresh_identity is not None
            assert fresh_identity.tenant_id is None
            assert fresh_identity.customer_id is None

        assert websocket_events
    finally:
        if original_override is None:
            app.dependency_overrides.pop(get_db, None)
        else:
            app.dependency_overrides[get_db] = original_override
        await engine.dispose()
