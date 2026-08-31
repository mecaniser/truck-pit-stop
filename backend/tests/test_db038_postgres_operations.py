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
from sqlalchemy import func, select, text
from sqlalchemy.dialects import postgresql
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api.v1.endpoints import inventory as inventory_endpoints, parts_operations, repair_orders
from app.api.v1.endpoints import suppliers as supplier_endpoints
from app.core.config import settings
from app.db.models.inventory import Inventory, PartsUsage
from app.db.models.parts_operations import (
    CoreObligation,
    InventoryMovement,
    InventorySupplierSource,
    PartsOperationIdempotency,
    PurchaseOrder,
    PurchaseOrderLine,
    PurchaseReceiptLine,
)
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
            submitted = await parts_operations.submit_return(UUID(created["id"]), parts_operations.VersionCommand(expected_version=1), idempotency_key="db038-return-submit", db=db, current_user=user)
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
            recovered = await parts_operations.recover_core(core.id, parts_operations.VersionCommand(expected_version=1), idempotency_key="db038-core-recover", db=db, current_user=user)
            assert recovered["status"] == "on_hand"
            created = await parts_operations.create_return(body=parts_operations.ReturnCreate(kind="core", supplier_id=ids["supplier_id"], reason="core sent", lines=[parts_operations.ReturnLineInput(core_obligation_id=core.id, quantity=1)]), idempotency_key="db038-core-return-create", db=db, current_user=user)
            submitted = await parts_operations.submit_return(UUID(created["id"]), parts_operations.VersionCommand(expected_version=1), idempotency_key="db038-core-return-submit", db=db, current_user=user)
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
        foreign_ids = await _seed(factory)
        async with factory() as db:
            user = await db.get(User, ids["user_id"])
            supplier = await db.get(Supplier, ids["supplier_id"])
            supplier.payment_terms = "Net 30"
            supplier.default_lead_time_days = 3
            supplier.minimum_order_amount = Decimal("125.00")
            supplier.purchasing_notes = "Protected commercial profile"
            mechanic = User(
                tenant_id=ids["tenant_id"],
                email=f"db038-pg-supplier-mechanic-{uuid4().hex}@example.test",
                hashed_password="x",
                first_name="Supplier",
                last_name="Mechanic",
                role=UserRole.MECHANIC,
                is_active=True,
                is_verified=True,
            )
            tenantless_owner = User(
                tenant_id=None,
                email=f"db038-pg-supplier-tenantless-{uuid4().hex}@example.test",
                hashed_password="x",
                first_name="Tenantless",
                last_name="Owner",
                role=UserRole.GARAGE_OWNER,
                is_active=True,
                is_verified=True,
            )
            db.add_all((mechanic, tenantless_owner))
            await db.commit()
            listing = await inventory_endpoints.list_inventory(skip=0, limit=100, paginated=False, category=None, low_stock=None, search=None, db=db, current_user=user)
            assert listing[0].sku.startswith("DB038-") and listing[0].stock_quantity == 2
            suggestions = await inventory_endpoints.inventory_typeahead(q="Filter", limit=20, in_stock=True, db=db, current_user=user)
            assert suggestions[0].id == ids["item_id"]
            suppliers = await supplier_endpoints.list_suppliers(skip=0, limit=100, paginated=False, search=None, db=db, current_user=user)
            assert any(row.name == "Exact Supplier" and row.normalized_name == "exact supplier" for row in suppliers)
            assert len(suppliers) == 1
            commercial_fields = {
                "payment_terms", "default_lead_time_days",
                "minimum_order_amount", "purchasing_notes",
            }
            assert commercial_fields.isdisjoint(suppliers[0].model_dump())
            mechanic_suppliers = await supplier_endpoints.list_suppliers(
                skip=0, limit=100, paginated=False, search=None,
                db=db, current_user=mechanic,
            )
            assert len(mechanic_suppliers) == 1
            assert commercial_fields.isdisjoint(mechanic_suppliers[0].model_dump())
            with pytest.raises(HTTPException) as tenantless:
                await supplier_endpoints.list_suppliers(
                    skip=0, limit=100, paginated=False, search=None,
                    db=db, current_user=tenantless_owner,
                )
            assert tenantless.value.status_code == 403
            with pytest.raises(HTTPException) as mechanic_mutation:
                await supplier_endpoints.update_supplier(
                    supplier_id=str(ids["supplier_id"]),
                    data=supplier_endpoints.SupplierUpdate(payment_terms="Leaked"),
                    db=db,
                    current_user=mechanic,
                )
            assert mechanic_mutation.value.status_code == 403
            foreign_owner = await db.get(User, foreign_ids["user_id"])
            with pytest.raises(HTTPException) as foreign:
                await supplier_endpoints.update_supplier(
                    supplier_id=str(ids["supplier_id"]),
                    data=supplier_endpoints.SupplierUpdate(payment_terms="Leaked"),
                    db=db,
                    current_user=foreign_owner,
                )
            with pytest.raises(HTTPException) as missing:
                await supplier_endpoints.update_supplier(
                    supplier_id=str(uuid4()),
                    data=supplier_endpoints.SupplierUpdate(payment_terms="Leaked"),
                    db=db,
                    current_user=foreign_owner,
                )
            assert foreign.value.status_code == missing.value.status_code == 404
            assert foreign.value.detail == missing.value.detail == "Not found"
            await db.refresh(supplier)
            assert supplier.payment_terms == "Net 30"
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


async def _db038_stock_return(factory, ids):
    """Create one independent draft stock return with a durable receipt origin."""
    po_id, line_id = await _draft_and_submit(factory, ids, quantity=1)
    async with factory() as db:
        user = await db.get(User, ids["user_id"])
        await parts_operations.receive_purchase_order(
            po_id=po_id,
            body=parts_operations.ReceiptCreate(
                expected_version=2,
                received_at=datetime(2026, 8, 23, 14, tzinfo=timezone.utc),
                lines=[parts_operations.ReceiptLineInput(
                    purchase_order_line_id=line_id, quantity=1, unit_cost=Decimal("16.00"),
                )],
            ),
            idempotency_key=f"db038-return-origin-{uuid4().hex}", db=db, current_user=user,
        )
        receipt_line = (await db.execute(
            select(PurchaseReceiptLine).where(PurchaseReceiptLine.purchase_order_line_id == line_id)
        )).scalar_one()
        created = await parts_operations.create_return(
            body=parts_operations.ReturnCreate(
                kind="stock", supplier_id=ids["supplier_id"], reason="wrong part",
                lines=[parts_operations.ReturnLineInput(
                    purchase_receipt_line_id=receipt_line.id, quantity=1,
                    expected_credit=Decimal("16.00"),
                )],
            ),
            idempotency_key=f"db038-return-create-{uuid4().hex}", db=db, current_user=user,
        )
        return UUID(created["id"])


async def _db038_return_snapshot(factory, ids, return_id):
    async with factory() as db:
        row = await db.get(parts_operations.VendorReturn, return_id)
        item = await db.get(Inventory, ids["item_id"])
        movement_count = await db.scalar(select(func.count(InventoryMovement.id)).where(
            InventoryMovement.tenant_id == ids["tenant_id"],
            InventoryMovement.inventory_id == item.id,
        ))
        return (row.status, row.version, row.shipped_at, row.credited_at,
                item.stock_quantity, item.cost, item.stock_version, movement_count)


async def _db038_assert_durable_replay(factory, ids, *, invoke, snapshot, changed):
    """Exercise a committed endpoint retry in a fresh session without cache help."""
    first = await invoke()
    assert isinstance(first, dict)
    after_first = await snapshot()
    assert after_first == changed
    replay = await invoke()
    assert replay.headers["Idempotency-Replayed"] == "true"
    assert replay.status_code in {200, 201}
    assert json.loads(replay.body) == first
    assert await snapshot() == after_first


@pytest.mark.asyncio
async def test_db038_postgres_return_transition_replays_are_durable_and_conflict_safe(monkeypatch):
    """Every return transition stores its response atomically with the state change."""
    monkeypatch.setattr(settings, "PARTS_OPERATIONS_V1_ENABLED", True)
    engine = create_async_engine(os.environ[POSTGRES_URL]); factory = async_sessionmaker(engine, expire_on_commit=False)

    async def invoke(ids, return_id, route, body, key):
        async with factory() as db:
            user = await db.get(User, ids["user_id"])
            return await getattr(parts_operations, route)(
                return_id, body, idempotency_key=key, db=db, current_user=user,
            )

    async def state(ids, return_id):
        return await _db038_return_snapshot(factory, ids, return_id)

    async def assert_conflict(ids, return_id, route, body, key, expected):
        async with factory() as db:
            user = await db.get(User, ids["user_id"])
            with pytest.raises(HTTPException) as conflict:
                await getattr(parts_operations, route)(
                    return_id, body, idempotency_key=key, db=db, current_user=user,
                )
            assert conflict.value.status_code == 409
            await db.rollback()
        assert await state(ids, return_id) == expected

    try:
        ids = await _seed(factory, stock=10)
        # Draft -> submitted: no stock mutation, timestamp/version remain frozen on replay.
        return_id = await _db038_stock_return(factory, ids)
        submit = parts_operations.VersionCommand(expected_version=1)
        await _db038_assert_durable_replay(
            factory, ids,
            invoke=lambda: invoke(ids, return_id, "submit_return", submit, "db038-return-submit-replay-key"),
            snapshot=lambda: state(ids, return_id),
            changed=("submitted", 2, (await state(ids, return_id))[2], (await state(ids, return_id))[3],
                     (await state(ids, return_id))[4], (await state(ids, return_id))[5],
                     (await state(ids, return_id))[6], (await state(ids, return_id))[7]),
        )
        await assert_conflict(ids, return_id, "submit_return", parts_operations.VersionCommand(expected_version=99), "db038-return-submit-replay-key", await state(ids, return_id))

        # Draft -> cancelled is durable and has the same no-second-write guarantee.
        return_id = await _db038_stock_return(factory, ids)
        cancel = parts_operations.VersionCommand(expected_version=1, reason="supplier closed")
        before = await state(ids, return_id)
        await _db038_assert_durable_replay(
            factory, ids,
            invoke=lambda: invoke(ids, return_id, "cancel_return", cancel, "db038-return-cancel-replay-key"),
            snapshot=lambda: state(ids, return_id),
            changed=("cancelled", 2, before[2], before[3], before[4], before[5], before[6], before[7]),
        )
        await assert_conflict(ids, return_id, "cancel_return", parts_operations.VersionCommand(expected_version=99), "db038-return-cancel-replay-key", await state(ids, return_id))

        # Submitted -> shipped: replay cannot create another negative stock movement.
        return_id = await _db038_stock_return(factory, ids)
        await invoke(ids, return_id, "submit_return", parts_operations.VersionCommand(expected_version=1), "db038-return-ship-setup-key")
        before = await state(ids, return_id)
        first = await invoke(ids, return_id, "ship_return", parts_operations.VersionCommand(expected_version=2), "db038-return-ship-replay-key")
        after = await state(ids, return_id)
        assert after[:2] == ("shipped", 3)
        assert after[2] is not None and after[3] == before[3]
        assert after[4:] == (before[4] - 1, before[5], before[6] + 1, before[7] + 1)
        replay = await invoke(ids, return_id, "ship_return", parts_operations.VersionCommand(expected_version=2), "db038-return-ship-replay-key")
        assert replay.headers["Idempotency-Replayed"] == "true" and json.loads(replay.body) == first
        assert await state(ids, return_id) == after
        await assert_conflict(ids, return_id, "ship_return", parts_operations.VersionCommand(expected_version=99), "db038-return-ship-replay-key", after)

        # Shipped -> credited has no ledger write, and replay keeps its original credited timestamp.
        return_id = await _db038_stock_return(factory, ids)
        await invoke(ids, return_id, "submit_return", parts_operations.VersionCommand(expected_version=1), "db038-return-credit-submit-key")
        await invoke(ids, return_id, "ship_return", parts_operations.VersionCommand(expected_version=2), "db038-return-credit-ship-key")
        before = await state(ids, return_id)
        first = await invoke(ids, return_id, "credit_return", parts_operations.VersionCommand(expected_version=3), "db038-return-credit-replay-key")
        after = await state(ids, return_id)
        assert after[:2] == ("credited", 4) and after[4:] == before[4:]
        replay = await invoke(ids, return_id, "credit_return", parts_operations.VersionCommand(expected_version=3), "db038-return-credit-replay-key")
        assert replay.headers["Idempotency-Replayed"] == "true" and json.loads(replay.body) == first
        assert await state(ids, return_id) == after
        await assert_conflict(ids, return_id, "credit_return", parts_operations.VersionCommand(expected_version=99), "db038-return-credit-replay-key", after)

        # Shipped -> reversal is 201; its retry returns the same immutable reversal identity.
        return_id = await _db038_stock_return(factory, ids)
        await invoke(ids, return_id, "submit_return", parts_operations.VersionCommand(expected_version=1), "db038-return-reverse-submit-key")
        await invoke(ids, return_id, "ship_return", parts_operations.VersionCommand(expected_version=2), "db038-return-reverse-ship-key")
        before = await state(ids, return_id)
        first = await invoke(ids, return_id, "reverse_return", parts_operations.VersionCommand(expected_version=3, reason="carrier refused"), "db038-return-reverse-replay-key")
        after = await state(ids, return_id)
        assert after[:4] == before[:4]
        assert after[4:] == (before[4] + 1, before[5], before[6] + 1, before[7] + 1)
        replay = await invoke(ids, return_id, "reverse_return", parts_operations.VersionCommand(expected_version=3, reason="carrier refused"), "db038-return-reverse-replay-key")
        assert replay.status_code == 201 and replay.headers["Idempotency-Replayed"] == "true"
        assert json.loads(replay.body) == first and await state(ids, return_id) == after
        await assert_conflict(ids, return_id, "reverse_return", parts_operations.VersionCommand(expected_version=99, reason="carrier refused"), "db038-return-reverse-replay-key", after)
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_db038_postgres_return_transition_same_key_concurrency_commits_once(monkeypatch):
    """Two fresh PostgreSQL sessions see one transition and one durable replay."""
    monkeypatch.setattr(settings, "PARTS_OPERATIONS_V1_ENABLED", True)
    engine = create_async_engine(os.environ[POSTGRES_URL]); factory = async_sessionmaker(engine, expire_on_commit=False)

    async def call(ids, return_id, method, body, key):
        async with factory() as db:
            return await getattr(parts_operations, method)(
                return_id, body, idempotency_key=key, db=db,
                current_user=await db.get(User, ids["user_id"]),
            )

    try:
        ids = await _seed(factory, stock=10)
        # The three material return transition forms cover no-ledger, ledger, and 201 reversal response replay.
        cases = []
        submitted = await _db038_stock_return(factory, ids)
        cases.append((submitted, "submit_return", parts_operations.VersionCommand(expected_version=1), "db038-concurrent-return-submit"))
        cancelled = await _db038_stock_return(factory, ids)
        cases.append((cancelled, "cancel_return", parts_operations.VersionCommand(expected_version=1), "db038-concurrent-return-cancel"))
        shipped = await _db038_stock_return(factory, ids)
        await call(ids, shipped, "submit_return", parts_operations.VersionCommand(expected_version=1), "db038-concurrent-ship-setup")
        cases.append((shipped, "ship_return", parts_operations.VersionCommand(expected_version=2), "db038-concurrent-return-ship"))
        credited = await _db038_stock_return(factory, ids)
        await call(ids, credited, "submit_return", parts_operations.VersionCommand(expected_version=1), "db038-concurrent-credit-submit")
        await call(ids, credited, "ship_return", parts_operations.VersionCommand(expected_version=2), "db038-concurrent-credit-ship")
        cases.append((credited, "credit_return", parts_operations.VersionCommand(expected_version=3), "db038-concurrent-return-credit"))
        reversed_id = await _db038_stock_return(factory, ids)
        await call(ids, reversed_id, "submit_return", parts_operations.VersionCommand(expected_version=1), "db038-concurrent-reverse-submit")
        await call(ids, reversed_id, "ship_return", parts_operations.VersionCommand(expected_version=2), "db038-concurrent-reverse-ship")
        cases.append((reversed_id, "reverse_return", parts_operations.VersionCommand(expected_version=3, reason="carrier refused"), "db038-concurrent-return-reverse"))
        for return_id, method, body, key in cases:
            results = await asyncio.wait_for(asyncio.gather(
                call(ids, return_id, method, body, key), call(ids, return_id, method, body, key),
            ), timeout=10)
            first = next(result for result in results if isinstance(result, dict))
            replay = next(result for result in results if not isinstance(result, dict))
            assert replay.headers["Idempotency-Replayed"] == "true"
            assert json.loads(replay.body) == first
            if method == "reverse_return":
                assert replay.status_code == 201
    finally:
        await engine.dispose()


async def _db038_expected_core(factory, ids):
    async with factory() as db:
        customer = Customer(tenant_id=ids["tenant_id"], first_name="Core", last_name="Replay", email=f"core-replay-{uuid4().hex}@example.test")
        db.add(customer); await db.flush()
        vehicle = Vehicle(tenant_id=ids["tenant_id"], customer_id=customer.id, make="Freightliner", model="Cascadia", year=2024)
        db.add(vehicle); await db.flush()
        order = RepairOrder(tenant_id=ids["tenant_id"], customer_id=customer.id, vehicle_id=vehicle.id, order_number=f"CORE-REPLAY-{uuid4().hex[:10]}", status=RepairOrderStatus.DRAFT)
        db.add(order); await db.flush()
        usage = PartsUsage(tenant_id=ids["tenant_id"], repair_order_id=order.id, inventory_id=ids["item_id"], quantity=Decimal("1.00"), unit_cost=Decimal("10.00"), unit_price=Decimal("20.00"), total_price=Decimal("20.00"), stock_reserved_packages=1)
        db.add(usage); await db.flush()
        core = CoreObligation(tenant_id=ids["tenant_id"], parts_usage_id=usage.id, inventory_id=ids["item_id"], supplier_id=ids["supplier_id"], quantity=1, unit_core_value_snapshot=Decimal("50.00"), status="expected")
        db.add(core); await db.commit()
        return core.id


@pytest.mark.asyncio
async def test_db038_postgres_po_and_core_transition_replays_are_serial_and_concurrent(monkeypatch):
    """Submit/cancel/recover/waive share the same durable-key contract under real sessions."""
    monkeypatch.setattr(settings, "PARTS_OPERATIONS_V1_ENABLED", True)
    engine = create_async_engine(os.environ[POSTGRES_URL]); factory = async_sessionmaker(engine, expire_on_commit=False)

    async def draft_po(ids):
        async with factory() as db:
            user = await db.get(User, ids["user_id"])
            created = await parts_operations.create_purchase_order(
                body=parts_operations.POCreate(
                    po_number=f"PO-TRANSITION-{uuid4().hex[:10]}", supplier_id=ids["supplier_id"],
                    lines=[parts_operations.POLineInput(inventory_id=ids["item_id"], ordered_quantity=1, unit_cost=Decimal("16.00"))],
                ), idempotency_key=f"db038-transition-po-create-{uuid4().hex}", db=db, current_user=user,
            )
            return UUID(created["id"])

    async def po_call(ids, po_id, method, body, key):
        async with factory() as db:
            return await getattr(parts_operations, method)(po_id, body, idempotency_key=key, db=db, current_user=await db.get(User, ids["user_id"]))

    async def core_call(ids, core_id, method, body, key):
        async with factory() as db:
            return await getattr(parts_operations, method)(core_id, body, idempotency_key=key, db=db, current_user=await db.get(User, ids["user_id"]))

    async def assert_pair(call):
        first = await call()
        replay = await call()
        assert isinstance(first, dict)
        assert replay.headers["Idempotency-Replayed"] == "true"
        assert json.loads(replay.body) == first
        return first

    async def assert_concurrent(call):
        results = await asyncio.wait_for(asyncio.gather(call(), call()), timeout=10)
        first = next(result for result in results if isinstance(result, dict))
        replay = next(result for result in results if not isinstance(result, dict))
        assert replay.headers["Idempotency-Replayed"] == "true"
        assert json.loads(replay.body) == first

    try:
        ids = await _seed(factory)
        # Serial PO submit/cancel replay does not advance optimistic versions a second time.
        po_id = await draft_po(ids)
        submitted = await assert_pair(lambda: po_call(ids, po_id, "submit_purchase_order", parts_operations.VersionCommand(expected_version=1), "db038-po-submit-replay-key"))
        async with factory() as db:
            po = await db.get(PurchaseOrder, po_id)
            assert (po.status, po.version) == ("submitted", submitted["version"])
            user = await db.get(User, ids["user_id"])
            with pytest.raises(HTTPException) as conflict:
                await parts_operations.submit_purchase_order(po_id, parts_operations.VersionCommand(expected_version=99), idempotency_key="db038-po-submit-replay-key", db=db, current_user=user)
            assert conflict.value.status_code == 409
            await db.rollback()
        po_id = await draft_po(ids)
        cancelled = await assert_pair(lambda: po_call(ids, po_id, "cancel_purchase_order", parts_operations.VersionCommand(expected_version=1, reason="supplier closed"), "db038-po-cancel-replay-key"))
        async with factory() as db:
            po = await db.get(PurchaseOrder, po_id)
            assert (po.status, po.version) == ("cancelled", cancelled["version"])
            user = await db.get(User, ids["user_id"])
            with pytest.raises(HTTPException) as conflict:
                await parts_operations.cancel_purchase_order(po_id, parts_operations.VersionCommand(expected_version=99), idempotency_key="db038-po-cancel-replay-key", db=db, current_user=user)
            assert conflict.value.status_code == 409
            await db.rollback()

        # Concurrent sessions serialize all four state transitions through the tenant/family/key advisory lock.
        po_id = await draft_po(ids)
        await assert_concurrent(lambda: po_call(ids, po_id, "submit_purchase_order", parts_operations.VersionCommand(expected_version=1), "db038-po-submit-concurrent-key"))
        po_id = await draft_po(ids)
        await assert_concurrent(lambda: po_call(ids, po_id, "cancel_purchase_order", parts_operations.VersionCommand(expected_version=1), "db038-po-cancel-concurrent-key"))
        core_id = await _db038_expected_core(factory, ids)
        recovered = await assert_pair(lambda: core_call(ids, core_id, "recover_core", parts_operations.VersionCommand(expected_version=1), "db038-core-recover-replay-key"))
        async with factory() as db:
            core = await db.get(CoreObligation, core_id)
            movement_count = await db.scalar(select(func.count(InventoryMovement.id)).where(InventoryMovement.source_id == core_id))
            assert (core.status, core.version, movement_count) == ("on_hand", recovered["version"], 1)
            user = await db.get(User, ids["user_id"])
            with pytest.raises(HTTPException) as conflict:
                await parts_operations.recover_core(core_id, parts_operations.VersionCommand(expected_version=99), idempotency_key="db038-core-recover-replay-key", db=db, current_user=user)
            assert conflict.value.status_code == 409
            await db.rollback()
        core_id = await _db038_expected_core(factory, ids)
        waived = await assert_pair(lambda: core_call(ids, core_id, "waive_core", parts_operations.VersionCommand(expected_version=1, reason="supplier waiver"), "db038-core-waive-replay-key"))
        async with factory() as db:
            core = await db.get(CoreObligation, core_id)
            assert (core.status, core.version, core.reason) == ("waived", waived["version"], "supplier waiver")
        core_id = await _db038_expected_core(factory, ids)
        await assert_concurrent(lambda: core_call(ids, core_id, "recover_core", parts_operations.VersionCommand(expected_version=1), "db038-core-recover-concurrent-key"))
        core_id = await _db038_expected_core(factory, ids)
        await assert_concurrent(lambda: core_call(ids, core_id, "waive_core", parts_operations.VersionCommand(expected_version=1, reason="supplier waiver"), "db038-core-waive-concurrent-key"))

        # A reused key with another request body is always a conflict before the domain row is touched.
        async with factory() as db:
            user = await db.get(User, ids["user_id"])
            with pytest.raises(HTTPException) as conflict:
                await parts_operations.waive_core(
                    core_id, parts_operations.VersionCommand(expected_version=1, reason="different reason"),
                    idempotency_key="db038-core-waive-concurrent-key", db=db, current_user=user,
                )
            assert conflict.value.status_code == 409
            await db.rollback()
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_db038_postgres_read_contract_fixture_and_tenant_filter_denial(monkeypatch):
    from test_db038_read_contract import FROZEN, _seed_read_contract

    monkeypatch.setattr(settings, "PARTS_OPERATIONS_V1_ENABLED", True)
    monkeypatch.setattr(parts_operations, "_utc_now", lambda: FROZEN)
    engine = create_async_engine(os.environ[POSTGRES_URL]); factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with factory() as db:
            context = await _seed_read_contract(db)
        async with factory() as db:
            owner = await db.get(User, context["owner"].id)
            result = await parts_operations.demand(
                state=None, supplier_id=None, search=None, skip=0, limit=50, paginated=True,
                db=db, current_user=owner,
            )
            expected = context["fixture"]["read_contract"]["expected_oil_filter_demand"]
            assert next(item for item in result["items"] if item["inventory_id"] == expected["inventory_id"]) == expected
            assert result["total"] == 3
            v2_expected = context["fixture"]["v2_read_contract"]
            parts = await parts_operations.list_parts(
                view="active", attention=None, supplier_id=None, search=None,
                sort_by="catalog", skip=0, limit=50, paginated=True,
                db=db, current_user=owner,
            )
            assert parts["total"] == v2_expected["active_part_count"]
            oil = next(row for row in parts["items"] if row["id"] == v2_expected["expected_oil_filter"]["id"])
            assert oil["image_url"] == v2_expected["expected_oil_filter"]["image_url"]
            assert oil["location"] == v2_expected["expected_oil_filter"]["location"]
            assert {source["source_id"] for source in oil["supplier_sources"]} == {
                v2_expected["expected_oil_filter"]["preferred_source_id"],
                v2_expected["expected_oil_filter"]["alternate_source_id"],
            }
            archived = await parts_operations.get_part_detail(
                inventory_id=UUID(v2_expected["archived_part_id"]),
                db=db,
                current_user=owner,
            )
            assert archived["is_archived"] is True
            assert archived["recent_movements"][0]["id"] == v2_expected["archived_movement_id"]
            with pytest.raises(HTTPException) as foreign:
                await parts_operations.demand(
                    state=None, supplier_id=context["foreign_supplier"].id, search=None,
                    skip=0, limit=50, paginated=False, db=db, current_user=owner,
                )
            assert foreign.value.status_code == 404 and foreign.value.detail == "Not found"
            await db.rollback()
        async with factory() as db:
            receptionist = await db.get(User, context["receptionist"].id)
            mechanic = await db.get(User, context["mechanic"].id)
            assert isinstance(await parts_operations.demand(
                state="open", supplier_id=None, search=None, skip=0, limit=50, paginated=False,
                db=db, current_user=receptionist,
            ), list)
            with pytest.raises(HTTPException) as denied:
                await parts_operations.demand(
                    state=None, supplier_id=None, search=None, skip=0, limit=50, paginated=False,
                    db=db, current_user=mechanic,
                )
            assert denied.value.status_code == 403
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_db041_postgres_parts_sorting_is_numeric_stable_and_tenant_safe(monkeypatch):
    monkeypatch.setattr(settings, "PARTS_OPERATIONS_V1_ENABLED", True)
    engine = create_async_engine(os.environ[POSTGRES_URL])
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        ids = await _seed(factory)
        foreign_ids = await _seed(factory)
        async with factory() as db:
            user = await db.get(User, ids["user_id"])
            base = await db.get(Inventory, ids["item_id"])
            base.sku = "BASE-SHELF"
            base.name = "Shelf need"
            base.location = "B-02"

            customer = Customer(
                tenant_id=ids["tenant_id"],
                first_name="DB041",
                last_name="Sort",
                email=f"db041-pg-{uuid4().hex}@example.test",
            )
            db.add(customer)
            await db.flush()
            vehicle = Vehicle(
                tenant_id=ids["tenant_id"],
                customer_id=customer.id,
                make="Freightliner",
                model="Cascadia",
                year=2025,
            )
            db.add(vehicle)
            await db.flush()
            order = RepairOrder(
                tenant_id=ids["tenant_id"],
                customer_id=customer.id,
                vehicle_id=vehicle.id,
                order_number=f"DB041-{uuid4().hex[:10]}",
                status=RepairOrderStatus.IN_PROGRESS,
            )
            db.add(order)
            await db.flush()

            def part(
                sku: str,
                name: str,
                *,
                stock: int,
                reorder: int,
                cost: str,
                location: str | None,
                on_order: int = 0,
                placeholder: bool = False,
                retired: bool = False,
                deleted: bool = False,
            ) -> Inventory:
                return Inventory(
                    tenant_id=ids["tenant_id"],
                    sku=sku,
                    name=name,
                    stock_quantity=stock,
                    on_order_quantity=on_order,
                    reorder_level=reorder,
                    cost=Decimal(cost),
                    selling_price=Decimal("20.00"),
                    unit_type="each",
                    location=location,
                    is_placeholder=placeholder,
                    ets_retired_at=(datetime(2026, 8, 1, tzinfo=timezone.utc) if retired else None),
                    deleted_at=(datetime(2026, 8, 2, tzinfo=timezone.utc) if deleted else None),
                )

            repair_shortage = part(
                "REPAIR-ONLY", "Repair only shortage", stock=10, reorder=0,
                cost="12.00", location="R-01",
            )
            threshold_equal = part(
                "THRESHOLD", "Threshold equality", stock=2, reorder=2,
                cost="2.00", location="E-01",
            )
            incoming_covered = part(
                "COVERED", "Covered incoming", stock=0, reorder=4,
                cost="100.00", location="C-01", on_order=4,
            )
            placeholder = part(
                "PLACEHOLDER", "Placeholder urgency", stock=0, reorder=9,
                cost="3.00", location="P-01", placeholder=True,
            )
            archived = part(
                "ARCHIVED", "Archived urgency", stock=0, reorder=9,
                cost="30.00", location="Z-01", retired=True,
            )
            deleted = part(
                "DELETED", "Deleted urgency", stock=0, reorder=9,
                cost="40.00", location="D-01", deleted=True,
            )
            equal_rows = [
                part(
                    f"TIE-{index:03d}", "Equal key", stock=5, reorder=0,
                    cost="7.00", location=f"T-{index:02d}",
                )
                for index in (3, 1, 2)
            ]
            null_location = part(
                "LOC-NULL", "Null location", stock=6, reorder=0,
                cost="8.00", location=None,
            )
            blank_location = part(
                "LOC-BLANK", "Blank location", stock=7, reorder=0,
                cost="9.00", location="",
            )
            whitespace_location = part(
                "LOC-SPACE", "Whitespace location", stock=8, reorder=0,
                cost="11.00", location="   ",
            )
            db.add_all((
                repair_shortage, threshold_equal, incoming_covered, placeholder,
                archived, deleted, *equal_rows, null_location, blank_location,
                whitespace_location,
            ))
            await db.flush()
            db.add(PartsUsage(
                tenant_id=ids["tenant_id"],
                repair_order_id=order.id,
                inventory_id=repair_shortage.id,
                quantity=Decimal("2.00"),
                unit_cost=repair_shortage.cost,
                unit_price=Decimal("20.00"),
                total_price=Decimal("40.00"),
                stock_reserved_packages=0,
                stock_shortage_override=True,
            ))
            foreign = await db.get(Inventory, foreign_ids["item_id"])
            foreign.sku = "FOREIGN-FIRST"
            foreign.name = "Foreign urgency"
            foreign.stock_quantity = 0
            foreign.reorder_level = 999
            foreign.cost = Decimal("999.00")
            await db.commit()

            async def listed(
                sort_by: str,
                direction: str | None,
                *,
                view: str = "active",
                attention: str | None = None,
                search: str | None = None,
                skip: int = 0,
                limit: int = 100,
                paginated: bool = False,
            ):
                return await parts_operations.list_parts(
                    view=view,
                    attention=attention,
                    supplier_id=None,
                    search=search,
                    sort_by=sort_by,
                    direction=direction,
                    skip=skip,
                    limit=limit,
                    paginated=paginated,
                    db=db,
                    current_user=user,
                )

            rows = await listed("catalog", "asc")
            active_ids = {row["id"] for row in rows}
            assert str(archived.id) not in active_ids
            assert str(deleted.id) not in active_ids
            assert str(foreign.id) not in active_ids

            def expected_order(values: list[dict], sort_by: str, direction: str) -> list[str]:
                if sort_by == "catalog":
                    fallback = lambda row: (row["name"].casefold(), row["id"])
                    primary = lambda row: row["sku"].casefold()
                elif sort_by == "name":
                    fallback = lambda row: (row["sku"].casefold(), row["id"])
                    primary = lambda row: row["name"].casefold()
                else:
                    fallback = lambda row: (
                        row["name"].casefold(), row["sku"].casefold(), row["id"],
                    )
                    primary = {
                        "available": lambda row: row["available_packages"],
                        "cost": lambda row: Decimal(row["average_unit_cost"]),
                        "reorder": lambda row: row["recommended_order_packages"],
                    }.get(sort_by)
                ordered = sorted(values, key=fallback)
                if sort_by == "location":
                    located = [row for row in ordered if (row["location"] or "").strip()]
                    unset = [row for row in ordered if not (row["location"] or "").strip()]
                    located.sort(
                        key=lambda row: row["location"].strip().casefold(),
                        reverse=direction == "desc",
                    )
                    return [row["id"] for row in (*located, *unset)]
                ordered.sort(key=primary, reverse=direction == "desc")
                return [row["id"] for row in ordered]

            defaults = {
                "catalog": "asc", "name": "asc", "available": "asc",
                "location": "asc", "cost": "desc", "reorder": "desc",
            }
            for sort_by, default_direction in defaults.items():
                for direction in ("asc", "desc"):
                    sorted_rows = await listed(sort_by, direction)
                    assert {row["id"] for row in sorted_rows} == active_ids
                    assert [row["id"] for row in sorted_rows] == expected_order(
                        sorted_rows, sort_by, direction,
                    )
                assert await listed(sort_by, None) == await listed(sort_by, default_direction)

            for direction in ("asc", "desc"):
                location_rows = await listed("location", direction)
                unset = [row for row in location_rows if not (row["location"] or "").strip()]
                assert {row["location"] for row in unset} >= {None, "", "   "}
                assert location_rows[-len(unset):] == unset

            cost_rows = await listed("cost", "desc")
            costs = [Decimal(row["average_unit_cost"]) for row in cost_rows]
            assert costs == sorted(costs, reverse=True)
            assert costs.index(Decimal("100.00")) < costs.index(Decimal("12.00"))

            first = await listed(
                "cost", "asc", search="equal key", skip=0, limit=2, paginated=True,
            )
            second = await listed(
                "cost", "asc", search="equal key", skip=2, limit=2, paginated=True,
            )
            assert first["total"] == second["total"] == 3
            paged = first["items"] + second["items"]
            assert [row["sku"] for row in paged] == ["TIE-001", "TIE-002", "TIE-003"]
            assert len({row["id"] for row in paged}) == 3

            needs = await listed("reorder", "desc", attention="needs_reorder")
            assert {row["id"] for row in needs} == {str(base.id), str(repair_shortage.id)}
            repair_value = next(row for row in needs if row["id"] == str(repair_shortage.id))
            assert repair_value["recommended_order_packages"] == 2
            assert (await listed("available", "desc", attention="out_of_stock", search="covered"))[0]["id"] == str(incoming_covered.id)
            assert (await listed("location", "desc", attention="incoming", search="covered"))[0]["id"] == str(incoming_covered.id)
            archived_values = await listed("reorder", "desc", view="archived", search="archived")
            assert [row["id"] for row in archived_values] == [str(archived.id)]
            assert archived_values[0]["recommended_order_packages"] == 0
            placeholder_value = next(row for row in rows if row["id"] == str(placeholder.id))
            assert placeholder_value["recommended_order_packages"] == 0
            threshold_value = next(row for row in rows if row["id"] == str(threshold_equal.id))
            covered_value = next(row for row in rows if row["id"] == str(incoming_covered.id))
            assert threshold_value["recommended_order_packages"] == 0
            assert covered_value["recommended_order_packages"] == 0
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_db038_postgres_grouped_po_keys_and_numbers_are_concurrency_safe(monkeypatch):
    from test_db038_read_contract import load_db038_fixture

    monkeypatch.setattr(settings, "PARTS_OPERATIONS_V1_ENABLED", True)
    concurrency = load_db038_fixture()["grouped_purchasing"]["concurrent_number_allocation"]
    engine = create_async_engine(os.environ[POSTGRES_URL])
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        ids = await _seed(factory)
        async with factory() as db:
            user = await db.get(User, ids["user_id"])
            source = await parts_operations.create_supplier_source(
                inventory_id=ids["item_id"],
                body=parts_operations.SupplierSourceCreate(
                    supplier_id=ids["supplier_id"],
                    supplier_part_number="PG-SOURCE-01",
                    is_preferred=True,
                ),
                idempotency_key="db038-pg-source-create",
                db=db,
                current_user=user,
            )
        source_id = UUID(source["source_id"])
        body = parts_operations.POBatchCreate(groups=[
            parts_operations.BatchPOGroupInput(
                supplier_id=ids["supplier_id"],
                lines=[parts_operations.BatchPOLineInput(
                    inventory_id=ids["item_id"],
                    source_id=source_id,
                    ordered_quantity=1,
                    unit_cost=Decimal("14.00"),
                )],
            ),
        ])

        async def invoke(key: str):
            async with factory() as db:
                return await parts_operations.create_purchase_order_batch(
                    body=body,
                    idempotency_key=key,
                    db=db,
                    current_user=await db.get(User, ids["user_id"]),
                )

        same_key_results = await asyncio.wait_for(asyncio.gather(
            invoke("db038-batch-concurrent-same"),
            invoke("db038-batch-concurrent-same"),
        ), timeout=10)

        def payload(value):
            return value if isinstance(value, dict) else json.loads(value.body)

        same_payloads = [payload(value) for value in same_key_results]
        assert same_payloads[0] == same_payloads[1]
        assert same_payloads[0]["unassigned"] == []

        distinct_results = await asyncio.wait_for(asyncio.gather(*(
            invoke(key) for key in concurrency["idempotency_keys"]
        )), timeout=10)
        distinct_payloads = [payload(value) for value in distinct_results]
        distinct_numbers = {
            value["purchase_orders"][0]["po_number"] for value in distinct_payloads
        }
        assert len(distinct_numbers) == concurrency["expected_unique_numbers"]
        assert all(number.startswith(concurrency["po_number_prefix"]) for number in distinct_numbers)

        async with factory() as db:
            orders = list((await db.execute(select(PurchaseOrder).where(
                PurchaseOrder.tenant_id == ids["tenant_id"],
            ))).scalars().all())
            assert len(orders) == 3
            assert len({order.po_number for order in orders}) == 3
            assert await db.scalar(select(func.count(PartsOperationIdempotency.id)).where(
                PartsOperationIdempotency.tenant_id == ids["tenant_id"],
                PartsOperationIdempotency.operation_family == "po_batch_create",
            )) == 3
            lines = list((await db.execute(select(PurchaseOrderLine).where(
                PurchaseOrderLine.tenant_id == ids["tenant_id"],
            ))).scalars().all())
            assert len(lines) == 3
            assert all(line.supplier_source_id == source_id for line in lines)
            assert all(line.supplier_part_number_snapshot == "PG-SOURCE-01" for line in lines)
            persisted_source = await db.get(InventorySupplierSource, source_id)
            assert persisted_source.is_preferred is True
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_db038_postgres_parts_pagination_detail_and_tenant_source_constraint(monkeypatch):
    monkeypatch.setattr(settings, "PARTS_OPERATIONS_V1_ENABLED", True)
    engine = create_async_engine(os.environ[POSTGRES_URL])
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        ids = await _seed(factory)
        foreign_ids = await _seed(factory)
        async with factory() as db:
            user = await db.get(User, ids["user_id"])
            for index in range(3):
                db.add(Inventory(
                    tenant_id=ids["tenant_id"],
                    sku=f"PG-PAGE-{uuid4().hex[:8]}",
                    name=f"Page part {index}",
                    stock_quantity=10,
                    on_order_quantity=0,
                    reorder_level=0,
                    cost=Decimal("5.00"),
                    selling_price=Decimal("10.00"),
                    unit_type="each",
                    is_placeholder=False,
                ))
            db.add(Inventory(
                tenant_id=ids["tenant_id"],
                sku=f"PG-ARCH-{uuid4().hex[:8]}",
                name="Archived PG part",
                stock_quantity=0,
                on_order_quantity=0,
                reorder_level=0,
                cost=Decimal("5.00"),
                selling_price=Decimal("10.00"),
                unit_type="each",
                is_placeholder=False,
                ets_retired_at=datetime(2026, 8, 24, tzinfo=timezone.utc),
            ))
            await db.commit()
            source = await parts_operations.create_supplier_source(
                inventory_id=ids["item_id"],
                body=parts_operations.SupplierSourceCreate(
                    supplier_id=ids["supplier_id"],
                    supplier_part_number="PG-SEARCH-01",
                    is_preferred=True,
                ),
                idempotency_key="db038-pg-pagination-source",
                db=db,
                current_user=user,
            )
            first = await parts_operations.list_parts(
                view="active", attention=None, supplier_id=None, search=None,
                sort_by="catalog", skip=0, limit=2, paginated=True,
                db=db, current_user=user,
            )
            second = await parts_operations.list_parts(
                view="active", attention=None, supplier_id=None, search=None,
                sort_by="catalog", skip=2, limit=2, paginated=True,
                db=db, current_user=user,
            )
            assert first["total"] == second["total"] == 4
            assert len(first["items"]) == len(second["items"]) == 2
            assert {row["id"] for row in first["items"]}.isdisjoint(
                {row["id"] for row in second["items"]}
            )
            searched = await parts_operations.list_parts(
                view="active", attention=None, supplier_id=None, search="pg-search",
                sort_by="catalog", skip=0, limit=50, paginated=True,
                db=db, current_user=user,
            )
            assert [row["id"] for row in searched["items"]] == [str(ids["item_id"])]

            batch = await parts_operations.create_purchase_order_batch(
                body=parts_operations.POBatchCreate(groups=[
                    parts_operations.BatchPOGroupInput(
                        supplier_id=ids["supplier_id"],
                        lines=[parts_operations.BatchPOLineInput(
                            inventory_id=ids["item_id"],
                            source_id=UUID(source["source_id"]),
                            ordered_quantity=1,
                            unit_cost=Decimal("12.00"),
                        )],
                    ),
                ]),
                idempotency_key="db038-pg-detail-batch",
                db=db,
                current_user=user,
            )
            detail = await parts_operations.get_part_detail(
                inventory_id=ids["item_id"], db=db, current_user=user,
            )
            assert detail["open_purchase_order_lines"][0]["purchase_order_id"] == batch["purchase_orders"][0]["id"]
            assert detail["open_purchase_order_lines"][0]["supplier_source_id"] == source["source_id"]

        async with factory() as db:
            db.add(InventorySupplierSource(
                tenant_id=ids["tenant_id"],
                inventory_id=ids["item_id"],
                supplier_id=foreign_ids["supplier_id"],
                minimum_order_quantity=1,
                pack_quantity=1,
                is_active=True,
            ))
            with pytest.raises(IntegrityError):
                await db.flush()
            await db.rollback()
            db_constraint_names = set((await db.execute(text("""
                SELECT conname
                  FROM pg_constraint
                 WHERE conname IN (
                    'fk_inventory_supplier_sources_tenant_inventory',
                    'fk_inventory_supplier_sources_tenant_supplier',
                    'uq_inventory_supplier_sources_tenant_id_id_db038',
                    'uq_inventory_tenant_id_id_db038',
                    'uq_suppliers_tenant_id_id_db038'
                 )
            """))).scalars().all())
            metadata_constraint_names = {
                constraint.name
                for table in (
                    InventorySupplierSource.__table__,
                    Inventory.__table__,
                    Supplier.__table__,
                )
                for constraint in table.constraints
                if constraint.name and constraint.name.endswith((
                    "tenant_inventory",
                    "tenant_supplier",
                    "tenant_id_id_db038",
                ))
            }
            assert db_constraint_names == metadata_constraint_names == {
                "fk_inventory_supplier_sources_tenant_inventory",
                "fk_inventory_supplier_sources_tenant_supplier",
                "uq_inventory_supplier_sources_tenant_id_id_db038",
                "uq_inventory_tenant_id_id_db038",
                "uq_suppliers_tenant_id_id_db038",
            }
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_db038_postgres_po_line_source_is_bound_to_tenant_and_inventory(monkeypatch):
    """The database rejects source provenance outside the line's tenant/item."""
    monkeypatch.setattr(settings, "PARTS_OPERATIONS_V1_ENABLED", True)
    engine = create_async_engine(os.environ[POSTGRES_URL])
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        ids = await _seed(factory)
        foreign_ids = await _seed(factory)

        async with factory() as db:
            second_item = Inventory(
                tenant_id=ids["tenant_id"],
                sku=f"DB038-SECOND-{uuid4().hex[:8]}",
                name="Second tenant-local item",
                stock_quantity=0,
                on_order_quantity=0,
                reorder_level=0,
                cost=Decimal("8.00"),
                selling_price=Decimal("16.00"),
                unit_type="each",
                is_placeholder=False,
            )
            valid_source = InventorySupplierSource(
                tenant_id=ids["tenant_id"],
                inventory_id=ids["item_id"],
                supplier_id=ids["supplier_id"],
                supplier_part_number="DB038-VALID-SOURCE",
                minimum_order_quantity=1,
                pack_quantity=1,
                is_active=True,
            )
            foreign_source = InventorySupplierSource(
                tenant_id=foreign_ids["tenant_id"],
                inventory_id=foreign_ids["item_id"],
                supplier_id=foreign_ids["supplier_id"],
                supplier_part_number="DB038-FOREIGN-SOURCE",
                minimum_order_quantity=1,
                pack_quantity=1,
                is_active=True,
            )
            purchase_order = PurchaseOrder(
                tenant_id=ids["tenant_id"],
                po_number=f"PO-SOURCE-BOUNDARY-{uuid4().hex[:10]}",
                supplier_id=ids["supplier_id"],
                status="draft",
                version=1,
                created_by_user_id=ids["user_id"],
            )
            db.add_all((second_item, valid_source, foreign_source, purchase_order))
            await db.commit()
            second_item_id = second_item.id
            valid_source_id = valid_source.id
            foreign_source_id = foreign_source.id
            purchase_order_id = purchase_order.id

        def po_line(*, inventory_id: UUID, supplier_source_id: UUID, sku: str):
            return PurchaseOrderLine(
                tenant_id=ids["tenant_id"],
                purchase_order_id=purchase_order_id,
                inventory_id=inventory_id,
                supplier_source_id=supplier_source_id,
                supplier_part_number_snapshot=sku,
                sku_snapshot=sku,
                description_snapshot="Supplier provenance boundary",
                unit_type_snapshot="each",
                unit_cost_snapshot=Decimal("10.00"),
                core_charge_snapshot=Decimal("0.00"),
                ordered_quantity=1,
                received_quantity=0,
            )

        async with factory() as db:
            valid_line = po_line(
                inventory_id=ids["item_id"],
                supplier_source_id=valid_source_id,
                sku="VALID-SOURCE-LINE",
            )
            db.add(valid_line)
            await db.commit()
            valid_line_id = valid_line.id

        async with factory() as db:
            db.add(po_line(
                inventory_id=ids["item_id"],
                supplier_source_id=foreign_source_id,
                sku="FOREIGN-SOURCE-LINE",
            ))
            with pytest.raises(IntegrityError):
                await db.flush()
            await db.rollback()

        async with factory() as db:
            db.add(po_line(
                inventory_id=second_item_id,
                supplier_source_id=valid_source_id,
                sku="WRONG-INVENTORY-SOURCE-LINE",
            ))
            with pytest.raises(IntegrityError):
                await db.flush()
            await db.rollback()

        expected_constraints = {
            "uq_inventory_supplier_sources_tenant_id_id_db038",
            "uq_inventory_supplier_sources_tenant_id_id_inventory_db038",
            "fk_po_lines_tenant_supplier_source",
            "fk_po_lines_supplier_source_inventory",
        }
        async with factory() as db:
            persisted_lines = list((await db.execute(select(PurchaseOrderLine).where(
                PurchaseOrderLine.purchase_order_id == purchase_order_id,
            ))).scalars().all())
            assert [line.id for line in persisted_lines] == [valid_line_id]
            assert persisted_lines[0].tenant_id == ids["tenant_id"]
            assert persisted_lines[0].inventory_id == ids["item_id"]
            assert persisted_lines[0].supplier_source_id == valid_source_id

            db_constraint_names = set((await db.execute(text("""
                SELECT conname
                  FROM pg_constraint
                 WHERE conname IN (
                    'uq_inventory_supplier_sources_tenant_id_id_db038',
                    'uq_inventory_supplier_sources_tenant_id_id_inventory_db038',
                    'fk_po_lines_tenant_supplier_source',
                    'fk_po_lines_supplier_source_inventory'
                 )
            """))).scalars().all())
            metadata_constraint_names = {
                constraint.name
                for table in (
                    InventorySupplierSource.__table__,
                    PurchaseOrderLine.__table__,
                )
                for constraint in table.constraints
                if constraint.name in expected_constraints
            }
            assert db_constraint_names == metadata_constraint_names == expected_constraints
    finally:
        await engine.dispose()


async def _order_with_part_and_core(factory, ids, *, core_status: str):
    """A repair order carrying one part that has a core obligation against it."""
    from app.db.models.repair_order import RepairOrder, RepairOrderStatus
    from app.db.models.customer import Customer
    from app.db.models.vehicle import Vehicle

    suffix = uuid4().hex[:8]
    async with factory() as db:
        customer = Customer(tenant_id=ids["tenant_id"], first_name="Pat", last_name="Driver", email=f"core-{suffix}@example.test")
        db.add(customer); await db.flush()
        vehicle = Vehicle(tenant_id=ids["tenant_id"], customer_id=customer.id, make="Volvo", model="VNL")
        db.add(vehicle); await db.flush()
        order = RepairOrder(
            tenant_id=ids["tenant_id"], customer_id=customer.id, vehicle_id=vehicle.id,
            order_number=f"RO-CORE-{suffix}", status=RepairOrderStatus.IN_PROGRESS, is_internal=False,
            total_parts_cost=Decimal("0.00"), total_labor_cost=Decimal("0.00"), total_cost=Decimal("0.00"),
        )
        db.add(order); await db.flush()
        pu = PartsUsage(
            tenant_id=ids["tenant_id"], repair_order_id=order.id, inventory_id=ids["item_id"],
            quantity=Decimal("1"), unit_cost=Decimal("10.00"), unit_price=Decimal("20.00"),
            list_price=Decimal("20.00"), total_price=Decimal("20.00"),
        )
        db.add(pu); await db.flush()
        db.add(CoreObligation(
            tenant_id=ids["tenant_id"], parts_usage_id=pu.id, inventory_id=ids["item_id"],
            supplier_id=ids["supplier_id"], quantity=1,
            unit_core_value_snapshot=Decimal("50.00"), status=core_status,
        ))
        await db.commit()
        return order.id, pu.id


@pytest.mark.asyncio
@pytest.mark.parametrize("core_status", ["expected", "cancelled", "waived", "returned", "credited"])
async def test_db038_postgres_removing_a_part_releases_its_core_obligation(monkeypatch, core_status):
    """Deleting a part whose core obligation still points at it must not 500.

    core_obligations.parts_usage_id is ON DELETE NO ACTION, so marking the
    obligation cancelled while leaving the row in place still holds the key:
    Postgres refuses the delete with a ForeignKeyViolationError, which reached
    the operator as a 500 both when removing the part and when removing the
    service line above it. Only PostgreSQL enforces this — SQLite would pass
    against the bug.
    """
    engine = create_async_engine(os.environ[POSTGRES_URL])
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        ids = await _seed(factory)
        order_id, pu_id = await _order_with_part_and_core(factory, ids, core_status=core_status)

        async with factory() as db:
            user = await db.get(User, ids["user_id"])
            await repair_orders.remove_parts_from_repair_order(
                order_id=order_id, parts_usage_id=pu_id, db=db, current_user=user,
            )

        async with factory() as db:
            assert (await db.execute(select(func.count()).select_from(PartsUsage).where(PartsUsage.id == pu_id))).scalar() == 0
            # The obligation goes with the part. parts_usage_id is NOT NULL and
            # the FK is ON DELETE NO ACTION, so it cannot be kept pointing at a
            # row that no longer exists — and a core owed on a part that was
            # never really used is not owed at all. What survives is the
            # history event recording the removal.
            assert (await db.execute(select(func.count()).select_from(CoreObligation).where(
                CoreObligation.parts_usage_id == pu_id
            ))).scalar() == 0
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_db038_postgres_an_on_hand_core_still_blocks_removing_the_part(monkeypatch):
    """The one status that must keep refusing: the core is physically held."""
    engine = create_async_engine(os.environ[POSTGRES_URL])
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        ids = await _seed(factory)
        order_id, pu_id = await _order_with_part_and_core(factory, ids, core_status="on_hand")

        async with factory() as db:
            user = await db.get(User, ids["user_id"])
            with pytest.raises(HTTPException) as exc:
                await repair_orders.remove_parts_from_repair_order(
                    order_id=order_id, parts_usage_id=pu_id, db=db, current_user=user,
                )
            assert exc.value.status_code == 409

        async with factory() as db:
            assert (await db.execute(select(func.count()).select_from(PartsUsage).where(PartsUsage.id == pu_id))).scalar() == 1
    finally:
        await engine.dispose()
