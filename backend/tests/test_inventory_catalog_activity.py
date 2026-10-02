from __future__ import annotations

from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import select

from app.core.security import create_access_token
from app.db.models.inventory import Inventory
from app.db.models.inventory_lifecycle import PartActivityEvent
from app.db.models.tenant import Tenant
from app.db.models.user import User, UserRole


@pytest.mark.asyncio
async def test_catalog_update_records_price_core_and_supplier_activity(client, db_session):
    """A normal catalog edit must commit with one valid activity record per field."""
    suffix = uuid4().hex
    tenant = Tenant(name="Parts activity shop", slug=f"parts-activity-{suffix}", is_active=True)
    owner = User(
        tenant=tenant,
        email=f"parts-activity-{suffix}@example.test",
        hashed_password="x",
        first_name="Parts",
        last_name="Owner",
        role=UserRole.GARAGE_OWNER,
        is_active=True,
        is_verified=True,
    )
    part = Inventory(
        tenant=tenant,
        sku="ACTIVITY-PART",
        name="Activity Part",
        stock_quantity=1,
        reorder_level=0,
        cost=Decimal("10.00"),
        selling_price=Decimal("15.00"),
        core_charge=Decimal("0.00"),
        unit_type="each",
    )
    db_session.add_all([tenant, owner, part])
    await db_session.commit()

    token = create_access_token({"sub": str(owner.id)}, tenant_id=str(tenant.id))
    response = await client.put(
        f"/api/v1/inventory/{part.id}",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "cost": "20.30",
            "selling_price": "51.78",
            "core_charge": "5.00",
            "supplier_name": "Excel Truck Group",
            "supplier_contact": "parts@example.test",
        },
    )

    assert response.status_code == 200, response.text
    assert response.json()["cost"] == "20.30"
    assert response.json()["supplier_name"] == "Excel Truck Group"
    events = (await db_session.execute(
        select(PartActivityEvent).where(PartActivityEvent.inventory_id == part.id)
    )).scalars().all()
    assert {event.event_type for event in events} == {
        "part.cost_changed",
        "part.selling_price_changed",
        "part.core_charge_changed",
        "part.supplier_text_changed",
    }
    assert len(events) == 5
    cost_event = next(event for event in events if event.event_type == "part.cost_changed")
    assert cost_event.before_values == {"cost": "10.00"}
    assert cost_event.after_values == {"cost": "20.30"}
