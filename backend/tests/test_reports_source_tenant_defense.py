from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4

import pytest

from app.api.v1.endpoints.reports import (
    get_reports_internal,
    get_reports_service_types,
)
from app.db.models.customer import Customer
from app.db.models.invoice import Invoice, InvoiceStatus
from app.db.models.labor import Labor, LaborLineType
from app.db.models.repair_order import RepairOrder, RepairOrderStatus
from app.db.models.service import Service
from app.db.models.tenant import Tenant
from app.db.models.user import User, UserRole
from app.db.models.vehicle import Vehicle


@pytest.mark.asyncio
async def test_report_service_joins_never_resolve_cross_tenant_source_names(db_session):
    suffix = uuid4().hex
    # Pin both tenants to UTC. The reports resolve "this month" against the
    # tenant's own timezone (default America/New_York), while this test stamps
    # paid_at with datetime.now(timezone.utc). Between 00:00 and 04:00 UTC the
    # UTC date is already the next day in New York, so paid_at landed past the
    # range end and the report correctly returned nothing — the test failed for
    # four hours a day depending only on when CI happened to run. This test is
    # about tenant isolation, so take the timezone out of it.
    tenant = Tenant(name="Report shop", slug=f"report-{suffix}", timezone="UTC")
    foreign_tenant = Tenant(name="Foreign shop", slug=f"foreign-{suffix}", timezone="UTC")
    db_session.add_all([tenant, foreign_tenant])
    await db_session.flush()
    customer = Customer(
        tenant_id=tenant.id,
        first_name="Report",
        last_name="Customer",
        email=f"report-{suffix}@example.com",
    )
    db_session.add(customer)
    await db_session.flush()
    vehicle = Vehicle(
        tenant_id=tenant.id,
        customer_id=customer.id,
        make="Volvo",
        model="VNL",
        year=2024,
    )
    owner = User(
        tenant_id=tenant.id,
        email=f"owner-{suffix}@example.com",
        hashed_password="hashed-password",
        first_name="Report",
        last_name="Owner",
        role=UserRole.GARAGE_OWNER,
        is_active=True,
        is_verified=True,
    )
    foreign_service = Service(
        tenant_id=foreign_tenant.id,
        name="FOREIGN SERVICE NAME MUST NOT LEAK",
        duration_minutes=60,
        is_active=True,
    )
    db_session.add_all([vehicle, owner, foreign_service])
    await db_session.flush()

    external_order = RepairOrder(
        tenant_id=tenant.id,
        customer_id=customer.id,
        vehicle_id=vehicle.id,
        order_number=f"RO-EXT-{suffix[:8]}",
        status=RepairOrderStatus.PAID,
        is_internal=False,
        total_labor_cost=Decimal("100.00"),
        total_parts_cost=Decimal("0.00"),
        total_cost=Decimal("100.00"),
    )
    internal_order = RepairOrder(
        tenant_id=tenant.id,
        customer_id=customer.id,
        vehicle_id=vehicle.id,
        order_number=f"RO-INT-{suffix[:8]}",
        status=RepairOrderStatus.PAID,
        is_internal=True,
        total_labor_cost=Decimal("75.00"),
        total_parts_cost=Decimal("0.00"),
        total_cost=Decimal("75.00"),
    )
    db_session.add_all([external_order, internal_order])
    await db_session.flush()
    now = datetime.now(timezone.utc)
    db_session.add_all(
        [
            Labor(
                tenant_id=tenant.id,
                repair_order_id=external_order.id,
                description="Tenant external labor",
                hours=Decimal("1.00"),
                hourly_rate=Decimal("100.00"),
                total_cost=Decimal("100.00"),
                line_type=LaborLineType.MANUAL,
                source_service_id=foreign_service.id,
            ),
            Labor(
                tenant_id=tenant.id,
                repair_order_id=internal_order.id,
                description="Tenant internal labor",
                hours=Decimal("1.00"),
                hourly_rate=Decimal("75.00"),
                total_cost=Decimal("75.00"),
                line_type=LaborLineType.MANUAL,
                source_service_id=foreign_service.id,
            ),
            Invoice(
                tenant_id=tenant.id,
                repair_order_id=external_order.id,
                invoice_number=f"INV-EXT-{suffix[:8]}",
                status=InvoiceStatus.PAID,
                is_internal=False,
                subtotal=Decimal("100.00"),
                total_amount=Decimal("100.00"),
                paid_at=now,
            ),
            Invoice(
                tenant_id=tenant.id,
                repair_order_id=internal_order.id,
                invoice_number=f"INV-INT-{suffix[:8]}",
                status=InvoiceStatus.PAID,
                is_internal=True,
                subtotal=Decimal("75.00"),
                total_amount=Decimal("75.00"),
                paid_at=now,
            ),
        ]
    )
    await db_session.commit()

    external = await get_reports_service_types(
        range="this_month",
        from_date=None,
        to_date=None,
        db=db_session,
        current_user=owner,
    )
    internal = await get_reports_internal(
        range="this_month",
        from_date=None,
        to_date=None,
        db=db_session,
        current_user=owner,
    )

    assert [row.name for row in external.rows] == ["Tenant external labor"]
    assert [row.name for row in internal.service_rows] == ["Tenant internal labor"]
