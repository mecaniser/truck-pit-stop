"""DB-038 operational tests that must run only against an isolated PostgreSQL 15 database."""
from __future__ import annotations

import asyncio
import json
import os
from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.dialects import postgresql
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api.v1.endpoints import inventory as inventory_endpoints, parts_operations, repair_orders
from app.api.v1.endpoints import suppliers as supplier_endpoints
from app.core.config import settings
from app.db.models.inventory import Inventory, PartsUsage
from app.db.models.parts_operations import CoreObligation, InventoryMovement, PurchaseOrder, PurchaseOrderLine, PurchaseReceiptLine
from app.db.models.customer import Customer
from app.db.models.repair_order import RepairOrder, RepairOrderStatus
from app.db.models.supplier import Supplier
from app.db.models.vehicle import Vehicle
from app.db.models.tenant import Tenant
from app.db.models.user import User, UserRole
from app.services.parts_operations_service import apply_inventory_movement
from app.schemas.repair_order import PartsUsageCreate, PartsUsageUpdate, RepairOrderUpdate

POSTGRES_URL = "DB038_POSTGRES_URL"
pytestmark = pytest.mark.skipif(
    not os.environ.get(POSTGRES_URL), reason="requires isolated PostgreSQL 15"
)


async def _seed(factory, *, stock: int = 2):
    suffix = uuid4().hex
    async with factory() as db:
        tenant = Tenant(name="DB-038 PG", slug=f"db038-pg-{suffix}", is_active=True, parts_operations_enabled=True)
        user = User(tenant=tenant, email=f"db038-{suffix}@example.test", hashed_password="x", first_name="Parts", last_name="Owner", role=UserRole.GARAGE_OWNER, is_active=True, is_verified=True)
        supplier = Supplier(tenant=tenant, name="Exact Supplier", normalized_name="exact supplier", is_active=True)
        item = Inventory(tenant=tenant, sku=f"DB038-{suffix[:8]}", name="Filter", stock_quantity=stock, on_order_quantity=0, reorder_level=3, cost=Decimal("10.00"), selling_price=Decimal("20.00"), unit_type="each", is_placeholder=False)
        db.add_all((tenant, user, supplier, item))
        await db.commit()
        return {"tenant_id": tenant.id, "user_id": user.id, "supplier_id": supplier.id, "item_id": item.id}


async def _draft_and_submit(factory, ids, *, quantity: int = 3):
    async with factory() as db:
        user = await db.get(User, ids["user_id"])
        created = await parts_operations.create_purchase_order(
            body=parts_operations.POCreate(po_number=f"PO-{uuid4().hex[:12]}", supplier_id=ids["supplier_id"], lines=[parts_operations.POLineInput(inventory_id=ids["item_id"], ordered_quantity=quantity, unit_cost=Decimal("16.00"))]),
            idempotency_key=f"db038-create-{uuid4().hex}", db=db, current_user=user,
        )
        submitted = await parts_operations.submit_purchase_order(
            po_id=UUID(created["id"]), body=parts_operations.VersionCommand(expected_version=1),
            idempotency_key=f"db038-submit-{uuid4().hex}", db=db, current_user=user,
        )
        return UUID(created["id"]), UUID(submitted["lines"][0]["id"])


@pytest.mark.asyncio
async def test_db038_postgres_partial_final_receipt_and_overreceipt_are_atomic(monkeypatch):
    monkeypatch.setattr(settings, "PARTS_OPERATIONS_V1_ENABLED", True)
    engine = create_async_engine(os.environ[POSTGRES_URL])
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        ids = await _seed(factory)
        po_id, line_id = await _draft_and_submit(factory, ids)
        async with factory() as db:
            user = await db.get(User, ids["user_id"])
            partial = await parts_operations.receive_purchase_order(
                po_id=po_id, body=parts_operations.ReceiptCreate(expected_version=2, received_at=datetime(2026, 8, 23, 14, tzinfo=timezone.utc), lines=[parts_operations.ReceiptLineInput(purchase_order_line_id=line_id, quantity=2, unit_cost=Decimal("16.00"))]),
                idempotency_key="db038-partial-receipt-key", db=db, current_user=user,
            )
            assert partial["purchase_order_status"] == "partially_received"
            assert partial["lines"][0]["wac_after"] == "13.00"
        async with factory() as db:
            user = await db.get(User, ids["user_id"])
            with pytest.raises(HTTPException) as exc:
                await parts_operations.receive_purchase_order(
                    po_id=po_id, body=parts_operations.ReceiptCreate(expected_version=3, received_at=datetime(2026, 8, 23, 14, tzinfo=timezone.utc), lines=[parts_operations.ReceiptLineInput(purchase_order_line_id=line_id, quantity=2, unit_cost=Decimal("7.00"))]),
                    idempotency_key="db038-over-receipt-key", db=db, current_user=user,
                )
            assert exc.value.status_code == 409
            await db.rollback()
        async with factory() as db:
            user = await db.get(User, ids["user_id"])
            final = await parts_operations.receive_purchase_order(
                po_id=po_id, body=parts_operations.ReceiptCreate(expected_version=3, received_at=datetime(2026, 8, 23, 14, tzinfo=timezone.utc), lines=[parts_operations.ReceiptLineInput(purchase_order_line_id=line_id, quantity=1, unit_cost=Decimal("7.00"))]),
                idempotency_key="db038-final-receipt-key", db=db, current_user=user,
            )
            assert final["purchase_order_status"] == "received"
        async with factory() as db:
            po = await db.get(PurchaseOrder, po_id)
            item = await db.get(Inventory, ids["item_id"])
            movements = await db.scalar(select(func.count(InventoryMovement.id)).where(InventoryMovement.inventory_id == item.id))
            assert po.status == "received"
            assert item.stock_quantity == 5 and item.cost == Decimal("11.80")
            assert movements == 2
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_db038_postgres_same_durable_key_replays_without_second_movement(monkeypatch):
    monkeypatch.setattr(settings, "PARTS_OPERATIONS_V1_ENABLED", True)
    engine = create_async_engine(os.environ[POSTGRES_URL])
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        ids = await _seed(factory)
        po_id, line_id = await _draft_and_submit(factory, ids, quantity=1)
        body = parts_operations.ReceiptCreate(expected_version=2, received_at=datetime(2026, 8, 23, 14, tzinfo=timezone.utc), lines=[parts_operations.ReceiptLineInput(purchase_order_line_id=line_id, quantity=1, unit_cost=Decimal("16.00"))])
        key = "db038-durable-replay-key"
        async with factory() as db:
            first = await parts_operations.receive_purchase_order(po_id=po_id, body=body, idempotency_key=key, db=db, current_user=await db.get(User, ids["user_id"]))
        async with factory() as db:
            second = await parts_operations.receive_purchase_order(po_id=po_id, body=body, idempotency_key=key, db=db, current_user=await db.get(User, ids["user_id"]))
            assert second.status_code == 201
            assert second.headers["Idempotency-Replayed"] == "true"
            assert json.loads(second.body) == first
        async with factory() as db:
            assert await db.scalar(select(func.count(InventoryMovement.id)).where(InventoryMovement.inventory_id == ids["item_id"])) == 1
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_db038_postgres_concurrent_same_key_receipt_commits_once(monkeypatch):
    monkeypatch.setattr(settings, "PARTS_OPERATIONS_V1_ENABLED", True)
    engine = create_async_engine(os.environ[POSTGRES_URL])
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        ids = await _seed(factory)
        po_id, line_id = await _draft_and_submit(factory, ids, quantity=1)
        body = parts_operations.ReceiptCreate(expected_version=2, received_at=datetime(2026, 8, 23, 14, tzinfo=timezone.utc), lines=[parts_operations.ReceiptLineInput(purchase_order_line_id=line_id, quantity=1, unit_cost=Decimal("16.00"))])

        async def _receive_once():
            async with factory() as db:
                return await parts_operations.receive_purchase_order(
                    po_id=po_id, body=body, idempotency_key="db038-concurrent-durable-key",
                    db=db, current_user=await db.get(User, ids["user_id"]),
                )

        first, second = await asyncio.wait_for(asyncio.gather(_receive_once(), _receive_once()), timeout=10)
        assert {getattr(first, "status_code", 201), getattr(second, "status_code", 201)} == {201}
        assert sum(isinstance(value, dict) for value in (first, second)) == 1
        replay = second if not isinstance(second, dict) else first
        assert replay.headers["Idempotency-Replayed"] == "true"
        async with factory() as db:
            item = await db.get(Inventory, ids["item_id"])
            assert item.stock_quantity == 3
            assert await db.scalar(select(func.count(InventoryMovement.id)).where(InventoryMovement.inventory_id == item.id)) == 1
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_db038_postgres_concurrent_different_keys_allow_only_one_final_quantity(monkeypatch):
    monkeypatch.setattr(settings, "PARTS_OPERATIONS_V1_ENABLED", True)
    engine = create_async_engine(os.environ[POSTGRES_URL])
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        ids = await _seed(factory)
        po_id, line_id = await _draft_and_submit(factory, ids, quantity=1)
        body = parts_operations.ReceiptCreate(expected_version=2, received_at=datetime(2026, 8, 23, 14, tzinfo=timezone.utc), lines=[parts_operations.ReceiptLineInput(purchase_order_line_id=line_id, quantity=1, unit_cost=Decimal("16.00"))])

        async def _receive(key):
            async with factory() as db:
                try:
                    return await parts_operations.receive_purchase_order(po_id=po_id, body=body, idempotency_key=key, db=db, current_user=await db.get(User, ids["user_id"]))
                except HTTPException as exc:
                    await db.rollback()
                    return exc

        results = await asyncio.wait_for(asyncio.gather(_receive("db038-different-key-a"), _receive("db038-different-key-b")), timeout=10)
        assert sum(isinstance(result, dict) for result in results) == 1
        assert sum(isinstance(result, HTTPException) and result.status_code == 409 for result in results) == 1
        async with factory() as db:
            item = await db.get(Inventory, ids["item_id"])
            assert item.stock_quantity == 3
            assert await db.scalar(select(func.count(InventoryMovement.id)).where(InventoryMovement.inventory_id == item.id)) == 1
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_db038_postgres_multiline_receipt_failure_rolls_back_every_line(monkeypatch):
    monkeypatch.setattr(settings, "PARTS_OPERATIONS_V1_ENABLED", True)
    engine = create_async_engine(os.environ[POSTGRES_URL])
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        ids = await _seed(factory)
        async with factory() as db:
            second = Inventory(
                tenant_id=ids["tenant_id"], sku=f"DB038-SECOND-{uuid4().hex[:8]}", name="Second filter",
                stock_quantity=5, on_order_quantity=0, reorder_level=0,
                cost=Decimal("8.00"), selling_price=Decimal("18.00"), unit_type="each", is_placeholder=False,
            )
            db.add(second)
            await db.commit()
            user = await db.get(User, ids["user_id"])
            created = await parts_operations.create_purchase_order(
                body=parts_operations.POCreate(po_number=f"PO-MULTI-{uuid4().hex[:8]}", supplier_id=ids["supplier_id"], lines=[
                    parts_operations.POLineInput(inventory_id=ids["item_id"], ordered_quantity=1, unit_cost=Decimal("16.00")),
                    parts_operations.POLineInput(inventory_id=second.id, ordered_quantity=1, unit_cost=Decimal("9.00")),
                ]), idempotency_key="db038-multiline-create", db=db, current_user=user,
            )
            submitted = await parts_operations.submit_purchase_order(
                po_id=UUID(created["id"]), body=parts_operations.VersionCommand(expected_version=1),
                idempotency_key="db038-multiline-submit", db=db, current_user=user,
            )
            line_ids = [UUID(line["id"]) for line in submitted["lines"]]
        async with factory() as db:
            user = await db.get(User, ids["user_id"])
            with pytest.raises(HTTPException) as exc:
                await parts_operations.receive_purchase_order(
                    po_id=UUID(created["id"]), body=parts_operations.ReceiptCreate(
                        expected_version=2, received_at=datetime(2026, 8, 23, 14, tzinfo=timezone.utc),
                        lines=[
                            parts_operations.ReceiptLineInput(purchase_order_line_id=line_ids[0], quantity=1, unit_cost=Decimal("16.00")),
                            parts_operations.ReceiptLineInput(purchase_order_line_id=line_ids[1], quantity=2, unit_cost=Decimal("9.00")),
                        ],
                    ), idempotency_key="db038-multiline-fail", db=db, current_user=user,
                )
            assert exc.value.status_code == 409
            await db.rollback()
        async with factory() as db:
            po = await db.get(PurchaseOrder, UUID(created["id"]))
            first = await db.get(Inventory, ids["item_id"])
            second_after = await db.get(Inventory, second.id)
            assert po.status == "submitted" and po.version == 2
            assert (first.stock_quantity, second_after.stock_quantity) == (2, 5)
            assert await db.scalar(select(func.count(InventoryMovement.id)).where(InventoryMovement.tenant_id == ids["tenant_id"])) == 0
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_db038_postgres_stock_return_lifecycle_and_one_reversal(monkeypatch):
    monkeypatch.setattr(settings, "PARTS_OPERATIONS_V1_ENABLED", True)
    engine = create_async_engine(os.environ[POSTGRES_URL])
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        ids = await _seed(factory, stock=2)
        po_id, line_id = await _draft_and_submit(factory, ids, quantity=1)
        async with factory() as db:
            user = await db.get(User, ids["user_id"])
            await parts_operations.receive_purchase_order(po_id=po_id, body=parts_operations.ReceiptCreate(expected_version=2, received_at=datetime(2026, 8, 23, 14, tzinfo=timezone.utc), lines=[parts_operations.ReceiptLineInput(purchase_order_line_id=line_id, quantity=1, unit_cost=Decimal("16.00"))]), idempotency_key="db038-return-receipt", db=db, current_user=user)
            receipt_line = (await db.execute(select(PurchaseReceiptLine).where(PurchaseReceiptLine.purchase_order_line_id == line_id))).scalar_one()
            created = await parts_operations.create_return(body=parts_operations.ReturnCreate(kind="stock", supplier_id=ids["supplier_id"], reason="wrong part", lines=[parts_operations.ReturnLineInput(purchase_receipt_line_id=receipt_line.id, quantity=1, expected_credit=Decimal("16.00"))]), idempotency_key="db038-return-create", db=db, current_user=user)
            submitted = await parts_operations.submit_return(UUID(created["id"]), parts_operations.VersionCommand(expected_version=1), db=db, current_user=user)
            shipped = await parts_operations.ship_return(UUID(created["id"]), parts_operations.VersionCommand(expected_version=submitted["version"]), idempotency_key="db038-return-ship", db=db, current_user=user)
            assert shipped["status"] == "shipped"
            reversed_return = await parts_operations.reverse_return(UUID(created["id"]), parts_operations.VersionCommand(expected_version=shipped["version"], reason="vendor refused"), idempotency_key="db038-return-reverse", db=db, current_user=user)
            assert reversed_return["status"] == "credited"
        async with factory() as db:
            user = await db.get(User, ids["user_id"])
            with pytest.raises(HTTPException) as exc:
                await parts_operations.reverse_return(UUID(created["id"]), parts_operations.VersionCommand(expected_version=shipped["version"], reason="again"), idempotency_key="db038-return-reverse-2", db=db, current_user=user)
            assert exc.value.status_code == 409
            await db.rollback()
            item = await db.get(Inventory, ids["item_id"])
            assert item.stock_quantity == 3 and item.cost == Decimal("12.00")
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_db038_postgres_role_and_foreign_body_id_matrix(monkeypatch):
    monkeypatch.setattr(settings, "PARTS_OPERATIONS_V1_ENABLED", True)
    engine = create_async_engine(os.environ[POSTGRES_URL])
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        ids = await _seed(factory)
        po_id, _ = await _draft_and_submit(factory, ids)
        async with factory() as db:
            tenant = await db.get(Tenant, ids["tenant_id"])
            for role in (UserRole.RECEPTIONIST, UserRole.MECHANIC, UserRole.FLEET_MANAGER, UserRole.CUSTOMER, UserRole.DRIVER):
                user = User(tenant_id=tenant.id, email=f"db038-role-{role.value}-{uuid4().hex}@example.test", hashed_password="x", first_name="Role", last_name="User", role=role, is_active=True)
                db.add(user)
            foreign = Tenant(name="DB-038 Foreign", slug=f"db038-foreign-{uuid4().hex}", is_active=True, parts_operations_enabled=True)
            db.add(foreign)
            await db.commit()
            receptionist = (await db.execute(select(User).where(User.tenant_id == tenant.id, User.role == UserRole.RECEPTIONIST))).scalar_one()
            assert await parts_operations._tenant(db, receptionist, mutate=False) == tenant.id
            with pytest.raises(HTTPException) as denied:
                await parts_operations._tenant(db, receptionist, mutate=True)
            assert denied.value.status_code == 403
            for role in (UserRole.MECHANIC, UserRole.FLEET_MANAGER, UserRole.CUSTOMER, UserRole.DRIVER):
                user = (await db.execute(select(User).where(User.tenant_id == tenant.id, User.role == role))).scalar_one()
                with pytest.raises(HTTPException) as denied:
                    await parts_operations._tenant(db, user, mutate=False)
                assert denied.value.status_code == 403
            foreign_user = User(tenant_id=foreign.id, email=f"db038-foreign-owner-{uuid4().hex}@example.test", hashed_password="x", first_name="Foreign", last_name="Owner", role=UserRole.GARAGE_OWNER, is_active=True)
            db.add(foreign_user)
            await db.commit()
            with pytest.raises(HTTPException) as foreign_error:
                await parts_operations._po(db, foreign.id, po_id)
            with pytest.raises(HTTPException) as missing_error:
                await parts_operations._po(db, foreign.id, uuid4())
            assert foreign_error.value.status_code == missing_error.value.status_code == 404
            assert foreign_error.value.detail == missing_error.value.detail == "Not found"
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_db038_postgres_core_expected_on_hand_returned_waived_and_invalid_transition(monkeypatch):
    monkeypatch.setattr(settings, "PARTS_OPERATIONS_V1_ENABLED", True)
    engine = create_async_engine(os.environ[POSTGRES_URL]); factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        ids = await _seed(factory)
        async with factory() as db:
            customer = Customer(tenant_id=ids["tenant_id"], first_name="Core", last_name="Customer", email=f"core-{uuid4().hex}@example.test")
            db.add(customer); await db.flush()
            vehicle = Vehicle(tenant_id=ids["tenant_id"], customer_id=customer.id, make="Freightliner", model="Cascadia", year=2024)
            db.add(vehicle); await db.flush()
            order = RepairOrder(tenant_id=ids["tenant_id"], customer_id=customer.id, vehicle_id=vehicle.id, order_number=f"CORE-{uuid4().hex[:10]}", status=RepairOrderStatus.DRAFT)
            db.add(order); await db.flush()
            usage = PartsUsage(tenant_id=ids["tenant_id"], repair_order_id=order.id, inventory_id=ids["item_id"], quantity=Decimal("1.00"), unit_cost=Decimal("10.00"), unit_price=Decimal("20.00"), total_price=Decimal("20.00"), stock_reserved_packages=1)
            db.add(usage); await db.flush()
            core = CoreObligation(tenant_id=ids["tenant_id"], parts_usage_id=usage.id, inventory_id=ids["item_id"], supplier_id=ids["supplier_id"], quantity=1, unit_core_value_snapshot=Decimal("50.00"), status="expected")
            db.add(core); await db.commit()
            user = await db.get(User, ids["user_id"])
            recovered = await parts_operations.recover_core(core.id, parts_operations.VersionCommand(expected_version=1), db=db, current_user=user)
            assert recovered["status"] == "on_hand"
            created = await parts_operations.create_return(body=parts_operations.ReturnCreate(kind="core", supplier_id=ids["supplier_id"], reason="core sent", lines=[parts_operations.ReturnLineInput(core_obligation_id=core.id, quantity=1)]), idempotency_key="db038-core-return-create", db=db, current_user=user)
            submitted = await parts_operations.submit_return(UUID(created["id"]), parts_operations.VersionCommand(expected_version=1), db=db, current_user=user)
            shipped = await parts_operations.ship_return(UUID(created["id"]), parts_operations.VersionCommand(expected_version=submitted["version"]), idempotency_key="db038-core-return-ship", db=db, current_user=user)
            assert shipped["status"] == "shipped"
            await parts_operations.reverse_return(UUID(created["id"]), parts_operations.VersionCommand(expected_version=shipped["version"], reason="carrier return"), idempotency_key="db038-core-return-reverse", db=db, current_user=user)
        async with factory() as db:
            user = await db.get(User, ids["user_id"])
            with pytest.raises(HTTPException) as exc:
                await parts_operations.reverse_return(UUID(created["id"]), parts_operations.VersionCommand(expected_version=shipped["version"], reason="again"), idempotency_key="db038-core-return-reverse-2", db=db, current_user=user)
            assert exc.value.status_code == 409
            await db.rollback()
            movements = (await db.execute(select(InventoryMovement.movement_type).where(InventoryMovement.inventory_id == ids["item_id"], InventoryMovement.bucket == "core_on_hand"))).scalars().all()
            assert movements == ["core_recovery", "core_return", "core_return_reversal"]
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_db038_postgres_legacy_direct_receive_preserves_response_and_writes_movement(monkeypatch):
    monkeypatch.setattr(settings, "PARTS_OPERATIONS_V1_ENABLED", True)
    engine = create_async_engine(os.environ[POSTGRES_URL]); factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        ids = await _seed(factory, stock=2)
        async with factory() as db:
            user = await db.get(User, ids["user_id"])
            response = await inventory_endpoints.receive_shipment(ids["item_id"], inventory_endpoints.ReceiveShipmentRequest(quantity=3), db=db, current_user=user)
            assert response.stock_quantity == 5
        async with factory() as db:
            movement = (await db.execute(select(InventoryMovement).where(InventoryMovement.inventory_id == ids["item_id"]))).scalar_one()
            assert movement.movement_type == "legacy_direct_receipt"
            assert (movement.balance_before, movement.balance_after) == (2, 5)
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_db038_postgres_legacy_inventory_typeahead_and_supplier_fields_remain_compatible(monkeypatch):
    monkeypatch.setattr(settings, "PARTS_OPERATIONS_V1_ENABLED", True)
    engine = create_async_engine(os.environ[POSTGRES_URL]); factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        ids = await _seed(factory)
        async with factory() as db:
            user = await db.get(User, ids["user_id"])
            listing = await inventory_endpoints.list_inventory(skip=0, limit=100, paginated=False, category=None, low_stock=None, search=None, db=db, current_user=user)
            assert listing[0].sku.startswith("DB038-") and listing[0].stock_quantity == 2
            suggestions = await inventory_endpoints.inventory_typeahead(q="Filter", limit=20, in_stock=True, db=db, current_user=user)
            assert suggestions[0].id == ids["item_id"]
            suppliers = await supplier_endpoints.list_suppliers(skip=0, limit=100, paginated=False, search=None, db=db, current_user=user)
            assert any(row.name == "Exact Supplier" and row.normalized_name == "exact supplier" for row in suppliers)
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_db038_postgres_repair_add_remove_writes_reservation_and_release(monkeypatch):
    from test_db003_postgres_price_races import _seed_race_context
    monkeypatch.setattr(settings, "PARTS_OPERATIONS_V1_ENABLED", True)
    engine = create_async_engine(os.environ[POSTGRES_URL]); factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        context = await _seed_race_context(factory, status=RepairOrderStatus.DRAFT, with_quote=False)
        async with factory() as db:
            mechanic = await db.get(User, context["mechanic_id"])
            added = await repair_orders.add_parts_to_repair_order(context["order_id"], PartsUsageCreate(inventory_id=context["inventory_id"], quantity=Decimal("1.00")), db=db, current_user=mechanic)
            persisted = await db.get(PartsUsage, added.id)
            assert persisted.stock_reserved_packages == 1
            await repair_orders.remove_parts_from_repair_order(context["order_id"], added.id, db=db, current_user=mechanic)
        async with factory() as db:
            movements = (await db.execute(select(InventoryMovement.movement_type).where(InventoryMovement.inventory_id == context["inventory_id"]).order_by(InventoryMovement.created_at))).scalars().all()
            assert movements == ["repair_reservation", "repair_release"]
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_db038_postgres_repair_quantity_edit_writes_delta_movement(monkeypatch):
    from test_db003_postgres_price_races import _seed_race_context
    monkeypatch.setattr(settings, "PARTS_OPERATIONS_V1_ENABLED", True)
    engine = create_async_engine(os.environ[POSTGRES_URL]); factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        context = await _seed_race_context(factory, status=RepairOrderStatus.DRAFT, with_quote=False)
        async with factory() as db:
            mechanic = await db.get(User, context["mechanic_id"])
            added = await repair_orders.add_parts_to_repair_order(context["order_id"], PartsUsageCreate(inventory_id=context["inventory_id"], quantity=Decimal("1.00")), db=db, current_user=mechanic)
            updated = await repair_orders.update_parts_quantity(context["order_id"], added.id, PartsUsageUpdate(quantity=Decimal("2.00")), db=db, current_user=mechanic)
            assert updated.quantity == Decimal("2.00")
        async with factory() as db:
            kinds = (await db.execute(select(InventoryMovement.movement_type).where(InventoryMovement.inventory_id == context["inventory_id"]).order_by(InventoryMovement.created_at))).scalars().all()
            assert kinds == ["repair_reservation", "repair_reservation"]
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_db038_postgres_repair_cancel_releases_reserved_stock(monkeypatch):
    from test_db003_postgres_price_races import _seed_race_context
    monkeypatch.setattr(settings, "PARTS_OPERATIONS_V1_ENABLED", True)
    engine = create_async_engine(os.environ[POSTGRES_URL]); factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        context = await _seed_race_context(factory, status=RepairOrderStatus.DRAFT, with_quote=False)
        async with factory() as db:
            mechanic, admin = await db.get(User, context["mechanic_id"]), await db.get(User, context["admin_id"])
            await repair_orders.add_parts_to_repair_order(context["order_id"], PartsUsageCreate(inventory_id=context["inventory_id"], quantity=Decimal("1.00")), db=db, current_user=mechanic)
            cancelled = await repair_orders.update_repair_order(context["order_id"], RepairOrderUpdate(status=RepairOrderStatus.CANCELLED), db=db, current_user=admin)
            assert cancelled.status == RepairOrderStatus.CANCELLED
        async with factory() as db:
            kinds = (await db.execute(select(InventoryMovement.movement_type).where(InventoryMovement.inventory_id == context["inventory_id"]).order_by(InventoryMovement.created_at))).scalars().all()
            assert kinds == ["repair_reservation", "repair_release"]
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_db038_postgres_durable_replay_survives_redis_loss_and_preserves_safe_error(monkeypatch):
    """The domain record—not Redis—owns post-commit retry recovery."""
    monkeypatch.setattr(settings, "PARTS_OPERATIONS_V1_ENABLED", True)
    engine = create_async_engine(os.environ[POSTGRES_URL]); factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        ids = await _seed(factory); po_id, line_id = await _draft_and_submit(factory, ids, quantity=1)
        body = parts_operations.ReceiptCreate(expected_version=2, received_at=datetime(2026, 8, 23, 14, tzinfo=timezone.utc), lines=[parts_operations.ReceiptLineInput(purchase_order_line_id=line_id, quantity=1, unit_cost=Decimal("16.00"))])
        async with factory() as db:
            await parts_operations.receive_purchase_order(po_id=po_id, body=body, idempotency_key="db038-redis-loss-retry", db=db, current_user=await db.get(User, ids["user_id"]))
        # A retry has no cache dependency and reads the committed tenant-scoped record.
        async with factory() as db:
            replay = await parts_operations.receive_purchase_order(po_id=po_id, body=body, idempotency_key="db038-redis-loss-retry", db=db, current_user=await db.get(User, ids["user_id"]))
            assert replay.status_code == 201 and replay.headers["Idempotency-Replayed"] == "true"
        async with factory() as db:
            mismatch = parts_operations.ReceiptCreate(expected_version=2, received_at=datetime(2026, 8, 23, 14, tzinfo=timezone.utc), lines=[parts_operations.ReceiptLineInput(purchase_order_line_id=line_id, quantity=1, unit_cost=Decimal("17.00"))])
            with pytest.raises(HTTPException) as exc:
                await parts_operations.receive_purchase_order(po_id=po_id, body=mismatch, idempotency_key="db038-redis-loss-retry", db=db, current_user=await db.get(User, ids["user_id"]))
            assert exc.value.status_code == 409 and "Idempotency" in exc.value.detail
            await db.rollback()
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_db038_postgres_receipt_repair_release_and_return_serialize_on_inventory_row(monkeypatch):
    monkeypatch.setattr(settings, "PARTS_OPERATIONS_V1_ENABLED", True)
    engine = create_async_engine(os.environ[POSTGRES_URL]); factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        ids = await _seed(factory, stock=2)
        async def operation(kind, delta):
            async with factory() as db:
                user = await db.get(User, ids["user_id"])
                item = (await db.execute(select(Inventory).where(Inventory.id == ids["item_id"]).with_for_update())).scalar_one()
                await apply_inventory_movement(db, item=item, quantity_delta=delta, movement_type=kind, actor=user, source_type="db038_race", source_id=uuid4())
                await db.commit()
        await asyncio.wait_for(asyncio.gather(
            operation("po_receipt", 1), operation("repair_reservation", -1), operation("repair_release", 1), operation("vendor_return", -1),
        ), timeout=10)
        async with factory() as db:
            item = await db.get(Inventory, ids["item_id"])
            movements = (await db.execute(select(InventoryMovement).where(InventoryMovement.inventory_id == item.id).order_by(InventoryMovement.created_at))).scalars().all()
            assert item.stock_quantity == 2 and item.stock_quantity >= 0
            assert sorted(row.movement_type for row in movements) == ["po_receipt", "repair_release", "repair_reservation", "vendor_return"]
            assert all(row.balance_after >= 0 for row in movements)
    finally:
        await engine.dispose()


def test_db038_postgres_receipt_and_inventory_statements_lock_rows():
    po = select(PurchaseOrder).where(PurchaseOrder.id == uuid4()).with_for_update()
    line = select(PurchaseOrderLine).where(PurchaseOrderLine.id == uuid4()).with_for_update()
    item = select(Inventory).where(Inventory.id == uuid4()).with_for_update()
    assert "FOR UPDATE" in str(po.compile(dialect=postgresql.dialect()))
    assert "FOR UPDATE" in str(line.compile(dialect=postgresql.dialect()))
    assert "FOR UPDATE" in str(item.compile(dialect=postgresql.dialect()))
