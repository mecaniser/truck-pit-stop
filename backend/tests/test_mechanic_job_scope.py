from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4

import pytest

from app.api.v1.endpoints import mechanics
from app.db.models.customer import Customer
from app.db.models.labor import Labor, LaborLineType
from app.db.models.repair_order import RepairOrder, RepairOrderStatus
from app.db.models.tenant import Tenant
from app.db.models.user import User, UserRole
from app.db.models.vehicle import Vehicle


@pytest.mark.asyncio
async def test_mechanic_jobs_show_structured_labor_scope(db_session):
    tenant_id = uuid4()
    customer_id = uuid4()
    vehicle_id = uuid4()
    mechanic_id = uuid4()
    order_id = uuid4()
    now = datetime.now(timezone.utc)

    tenant = Tenant(id=tenant_id, name="Scope Garage", slug=f"scope-{uuid4().hex[:8]}")
    customer = Customer(
        id=customer_id,
        tenant_id=tenant_id,
        first_name="Fleet",
        last_name="Owner",
        email="fleet@example.com",
    )
    vehicle = Vehicle(
        id=vehicle_id,
        tenant_id=tenant_id,
        customer_id=customer_id,
        year=2021,
        make="Freightliner",
        model="Cascadia",
    )
    mechanic = User(
        id=mechanic_id,
        tenant_id=tenant_id,
        email="tech@example.com",
        first_name="Taylor",
        last_name="Tech",
        role=UserRole.MECHANIC,
        hashed_password="hashed",
    )
    order = RepairOrder(
        id=order_id,
        tenant_id=tenant_id,
        customer_id=customer_id,
        vehicle_id=vehicle_id,
        order_number="RO-SCOPE-1",
        status=RepairOrderStatus.ASSIGNED,
        assigned_mechanic_id=mechanic_id,
        description="Customer complaint: low air pressure",
        total_parts_cost=Decimal("0.00"),
        total_labor_cost=Decimal("250.00"),
        total_cost=Decimal("250.00"),
        created_at=now,
        updated_at=now,
    )
    labor = Labor(
        id=uuid4(),
        tenant_id=tenant_id,
        repair_order_id=order_id,
        description="Diagnose and repair air brake leak",
        hours=Decimal("2.50"),
        hourly_rate=Decimal("100.00"),
        total_cost=Decimal("250.00"),
        line_type=LaborLineType.REPAIR_OPERATION,
    )

    db_session.add_all([tenant, customer, vehicle, mechanic, order, labor])
    await db_session.commit()

    jobs = await mechanics.get_my_jobs(skip=0, limit=100, paginated=False, db=db_session, current_user=mechanic)
    assert len(jobs) == 1
    assert jobs[0].services_count == 1

    detail = await mechanics.get_my_job_detail(order_id=order_id, db=db_session, current_user=mechanic)
    assert [service.name for service in detail.services] == ["Diagnose and repair air brake leak"]
