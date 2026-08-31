"""A part that was never in the catalogue can still go on the order.

PartsUsageCreate requires an inventory_id, so until now a one-off — a hose from
the parts store, something a tech carried in — had no route onto a repair order
at all. The catalogue already models these as placeholders; what was missing was
a way to make one from the job that needs it.
"""
from __future__ import annotations

from decimal import Decimal
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import select

from app.api.v1.endpoints import repair_orders
from app.db.models.customer import Customer
from app.db.models.inventory import Inventory
from app.db.models.repair_order import RepairOrder, RepairOrderStatus
from app.db.models.tenant import Tenant
from app.db.models.user import User, UserRole
from app.db.models.vehicle import Vehicle
from app.schemas.repair_order import AdHocPartCreate


async def _seed(db, *, role: UserRole = UserRole.MECHANIC, assigned: bool = True):
    suffix = uuid4().hex[:8]
    tenant = Tenant(id=uuid4(), name="Ad hoc shop", slug=f"adhoc-{suffix}", is_active=True)
    customer = Customer(
        id=uuid4(), tenant_id=tenant.id, first_name="Pat", last_name="Driver",
        email=f"pat-{suffix}@example.test",
    )
    vehicle = Vehicle(id=uuid4(), tenant_id=tenant.id, customer_id=customer.id, make="Volvo", model="VNL")
    user = User(
        id=uuid4(), tenant_id=tenant.id, email=f"tech-{suffix}@example.test",
        hashed_password="x", first_name="Tech", last_name="One", role=role,
        is_active=True, is_verified=True,
    )
    order = RepairOrder(
        id=uuid4(), tenant_id=tenant.id, customer_id=customer.id, vehicle_id=vehicle.id,
        order_number=f"RO-{suffix}", status=RepairOrderStatus.IN_PROGRESS, is_internal=False,
        total_parts_cost=Decimal("0.00"), total_labor_cost=Decimal("0.00"), total_cost=Decimal("0.00"),
        # A mechanic may only price the job they are on, so the fixture has to
        # respect that boundary for the ordinary case to be exercised at all.
        assigned_mechanic_id=user.id if assigned else None,
    )
    db.add_all([tenant, customer, vehicle, user, order])
    await db.commit()
    return tenant, user, order


@pytest.mark.asyncio
async def test_an_unlisted_part_reaches_the_order_and_stays_in_the_catalogue(db_session):
    _, user, order = await _seed(db_session)

    usage = await repair_orders.add_ad_hoc_part_to_repair_order(
        order_id=order.id,
        body=AdHocPartCreate(
            name="Air hose fitting 3/8 brass",
            quantity=Decimal("2"),
            unit_price=Decimal("18.50"),
            unit_cost=Decimal("11.25"),
        ),
        db=db_session,
        current_user=user,
    )

    assert usage.quantity == Decimal("2.00")
    assert usage.unit_price == Decimal("18.50")

    item = await db_session.get(Inventory, usage.inventory_id)
    # A placeholder, not a stocked part: no stock, but a real catalogue row that
    # keeps its history and can be promoted later by clearing the flag.
    assert item.is_placeholder is True
    assert item.stock_quantity == 0
    assert item.name == "Air hose fitting 3/8 brass"
    assert item.selling_price == Decimal("18.50")
    assert item.cost == Decimal("11.25")
    # It needs a SKU the catalogue's unique index can keep apart from every other.
    assert item.sku.startswith("ADHOC-")


@pytest.mark.asyncio
async def test_a_part_number_already_in_the_catalogue_is_reused_not_duplicated(db_session):
    tenant, user, order = await _seed(db_session)
    existing = Inventory(
        id=uuid4(), tenant_id=tenant.id, sku="ETS-0532668000", name="Hose Heater, Main",
        cost=Decimal("40.00"), selling_price=Decimal("80.00"), stock_quantity=3,
    )
    db_session.add(existing)
    await db_session.commit()

    # Typed by hand, lower case: the same part number, and it must land on the
    # same part rather than minting a second spelling of it.
    usage = await repair_orders.add_ad_hoc_part_to_repair_order(
        order_id=order.id,
        body=AdHocPartCreate(
            name="Typed by hand", sku="ets-0532668000",
            quantity=Decimal("1"), unit_price=Decimal("80.00"),
        ),
        db=db_session,
        current_user=user,
    )

    assert usage.inventory_id == existing.id
    rows = await db_session.execute(
        select(Inventory).where(Inventory.tenant_id == tenant.id, Inventory.deleted_at.is_(None))
    )
    assert len(rows.scalars().all()) == 1, "the catalogue gained a duplicate of a part it already had"


@pytest.mark.asyncio
async def test_a_placeholder_is_added_even_though_nothing_is_in_stock(db_session):
    _, user, order = await _seed(db_session)

    # A part invented for this job has never been stocked. The ordinary add path
    # refuses a shortage; this one must not, or the feature cannot work at all.
    usage = await repair_orders.add_ad_hoc_part_to_repair_order(
        order_id=order.id,
        body=AdHocPartCreate(name="One-off bracket", quantity=Decimal("1"), unit_price=Decimal("12.00")),
        db=db_session,
        current_user=user,
    )

    item = await db_session.get(Inventory, usage.inventory_id)
    assert item.stock_quantity <= 0


@pytest.mark.asyncio
async def test_quantity_and_price_are_validated(db_session):
    with pytest.raises(ValueError):
        AdHocPartCreate(name="Bad", quantity=Decimal("0"), unit_price=Decimal("5"))
    with pytest.raises(ValueError):
        AdHocPartCreate(name="Bad", quantity=Decimal("1"), unit_price=Decimal("-1"))


@pytest.mark.asyncio
async def test_a_mechanic_cannot_invent_a_part_on_someone_elses_job(db_session):
    # The ad-hoc route must not become a way around the boundary that governs
    # every other edit to a repair order.
    _, user, order = await _seed(db_session, assigned=False)

    with pytest.raises(HTTPException) as excinfo:
        await repair_orders.add_ad_hoc_part_to_repair_order(
            order_id=order.id,
            body=AdHocPartCreate(name="Not my job", quantity=Decimal("1"), unit_price=Decimal("9.00")),
            db=db_session,
            current_user=user,
        )

    assert excinfo.value.status_code == 403
