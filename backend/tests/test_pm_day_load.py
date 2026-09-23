"""PM calendar day load: how many trucks are already scheduled on each day.

A manager rescheduling a PM needs to see which dates are already busy, so the
shop does not book five trucks onto one day and none onto the next.
"""
from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from uuid import uuid4
import os

import pytest

os.environ.setdefault("TWILIO_ACCOUNT_SID", "AC00000000000000000000000000000000")
os.environ.setdefault("TWILIO_AUTH_TOKEN", "test-token")
os.environ.setdefault("TWILIO_PHONE_NUMBER", "+15555550100")

from app.api.v1.endpoints import fleet
from app.db.models.customer import Customer
from app.db.models.tenant import Tenant
from app.db.models.user import User, UserRole
from app.db.models.vehicle import Vehicle
from app.services.internal_fleet import ensure_internal_fleet_customer


async def _seed(db):
    tenant = Tenant(id=uuid4(), name="PM Garage", slug=f"pm-{uuid4().hex[:8]}", labor_rate=Decimal("100.00"))
    db.add(tenant)
    await db.commit()
    fc = await ensure_internal_fleet_customer(db, tenant.id)
    await db.commit()
    user = User(id=uuid4(), tenant_id=tenant.id, email=f"fm-{uuid4().hex[:8]}@x.com",
                hashed_password="x", first_name="Fleet", last_name="Mgr",
                role=UserRole.FLEET_MANAGER, is_active=True, is_verified=True)
    db.add(user)
    await db.commit()
    return tenant, fc, user


def _vehicle(tenant_id, fc_id, **kw):
    base = dict(id=uuid4(), tenant_id=tenant_id, customer_id=fc_id, make="Volvo", model="VNL",
                year=2021, mileage=100000, pm_interval_miles=25000)
    base.update(kw)
    return Vehicle(**base)


async def _join_fleet(db, tenant_id, fc_id, *vehicles):
    from app.services.vehicle_identity import ensure_fleet_membership
    for vehicle in vehicles:
        await ensure_fleet_membership(
            db, tenant_id=tenant_id, vehicle_id=vehicle.id, fleet_customer_id=fc_id)
    await db.commit()


DAY = date(2026, 11, 4)


@pytest.mark.asyncio
async def test_counts_trucks_scheduled_on_each_day(db_session):
    tenant, fc, user = await _seed(db_session)
    a = _vehicle(tenant.id, fc.id, unit_number="603", pm_due_date=DAY)
    b = _vehicle(tenant.id, fc.id, unit_number="412", pm_due_date=DAY)
    c = _vehicle(tenant.id, fc.id, unit_number="118", pm_due_date=DAY + timedelta(days=1))
    db_session.add_all([a, b, c])
    await db_session.commit()
    await _join_fleet(db_session, tenant.id, fc.id, a, b, c)

    out = await fleet.pm_day_load(
        start=DAY, end=DAY + timedelta(days=1), db=db_session, current_user=user)

    by_day = {row.day: row for row in out}
    assert by_day[DAY].count == 2
    assert by_day[DAY + timedelta(days=1)].count == 1


@pytest.mark.asyncio
async def test_names_the_trucks_due_that_day(db_session):
    """The count alone does not tell a manager which trucks are involved."""
    tenant, fc, user = await _seed(db_session)
    a = _vehicle(tenant.id, fc.id, unit_number="603", pm_due_date=DAY)
    b = _vehicle(tenant.id, fc.id, unit_number="412", pm_due_date=DAY)
    db_session.add_all([a, b])
    await db_session.commit()
    await _join_fleet(db_session, tenant.id, fc.id, a, b)

    out = await fleet.pm_day_load(start=DAY, end=DAY, db=db_session, current_user=user)

    assert sorted(out[0].units) == ["412", "603"]


@pytest.mark.asyncio
async def test_omits_days_with_no_scheduled_pm(db_session):
    """Empty days carry no badge, so the response should not pad them."""
    tenant, fc, user = await _seed(db_session)
    a = _vehicle(tenant.id, fc.id, unit_number="603", pm_due_date=DAY)
    db_session.add(a)
    await db_session.commit()
    await _join_fleet(db_session, tenant.id, fc.id, a)

    out = await fleet.pm_day_load(
        start=DAY - timedelta(days=3), end=DAY + timedelta(days=3), db=db_session, current_user=user)

    assert [row.day for row in out] == [DAY]


@pytest.mark.asyncio
async def test_excludes_trucks_outside_the_window(db_session):
    tenant, fc, user = await _seed(db_session)
    inside = _vehicle(tenant.id, fc.id, unit_number="IN", pm_due_date=DAY)
    before = _vehicle(tenant.id, fc.id, unit_number="BEFORE", pm_due_date=DAY - timedelta(days=1))
    after = _vehicle(tenant.id, fc.id, unit_number="AFTER", pm_due_date=DAY + timedelta(days=1))
    db_session.add_all([inside, before, after])
    await db_session.commit()
    await _join_fleet(db_session, tenant.id, fc.id, inside, before, after)

    out = await fleet.pm_day_load(start=DAY, end=DAY, db=db_session, current_user=user)

    assert len(out) == 1
    assert out[0].units == ["IN"]


@pytest.mark.asyncio
async def test_does_not_leak_another_tenants_schedule(db_session):
    """PM load is shop-local: a truck in another shop must never be counted."""
    tenant, fc, user = await _seed(db_session)
    other_tenant, other_fc, _ = await _seed(db_session)
    mine = _vehicle(tenant.id, fc.id, unit_number="MINE", pm_due_date=DAY)
    theirs = _vehicle(other_tenant.id, other_fc.id, unit_number="THEIRS", pm_due_date=DAY)
    db_session.add_all([mine, theirs])
    await db_session.commit()
    await _join_fleet(db_session, tenant.id, fc.id, mine)
    await _join_fleet(db_session, other_tenant.id, other_fc.id, theirs)

    out = await fleet.pm_day_load(start=DAY, end=DAY, db=db_session, current_user=user)

    assert out[0].count == 1
    assert out[0].units == ["MINE"]


@pytest.mark.asyncio
async def test_ignores_deleted_trucks(db_session):
    """A retired truck is not shop load."""
    from datetime import datetime, timezone

    tenant, fc, user = await _seed(db_session)
    live = _vehicle(tenant.id, fc.id, unit_number="LIVE", pm_due_date=DAY)
    gone = _vehicle(tenant.id, fc.id, unit_number="GONE", pm_due_date=DAY,
                    deleted_at=datetime.now(timezone.utc))
    db_session.add_all([live, gone])
    await db_session.commit()
    await _join_fleet(db_session, tenant.id, fc.id, live, gone)

    out = await fleet.pm_day_load(start=DAY, end=DAY, db=db_session, current_user=user)

    assert out[0].count == 1
    assert out[0].units == ["LIVE"]


@pytest.mark.asyncio
async def test_rejects_a_reversed_window(db_session):
    from fastapi import HTTPException

    tenant, fc, user = await _seed(db_session)

    with pytest.raises(HTTPException) as err:
        await fleet.pm_day_load(
            start=DAY, end=DAY - timedelta(days=1), db=db_session, current_user=user)
    assert err.value.status_code == 422


@pytest.mark.asyncio
async def test_rejects_an_unbounded_window(db_session):
    """An open-ended range would scan the whole fleet history."""
    from fastapi import HTTPException

    tenant, fc, user = await _seed(db_session)

    with pytest.raises(HTTPException) as err:
        await fleet.pm_day_load(
            start=DAY, end=DAY + timedelta(days=400), db=db_session, current_user=user)
    assert err.value.status_code == 422


# ---------------------------------------------------------------------------
# Total shop load: PMs plus repair orders already booked that day.
#
# A PM due date says a truck needs service by then; an appointment says a bay is
# actually committed. A manager avoiding a busy day needs both, kept apart so a
# day heavy with corrective work is not mistaken for a day heavy with PMs.
# ---------------------------------------------------------------------------

def _appointment(tenant_id, customer_id, vehicle_id, service_id, when, **kw):
    from app.db.models.appointment import Appointment, AppointmentStatus
    base = dict(
        id=uuid4(), tenant_id=tenant_id, customer_id=customer_id, vehicle_id=vehicle_id,
        service_id=service_id, scheduled_at=when, duration_minutes=90,
        status=AppointmentStatus.CONFIRMED, price=Decimal("100.00"),
        confirmation_number=f"C{uuid4().hex[:8].upper()}",
    )
    base.update(kw)
    return Appointment(**base)


async def _a_service(db, tenant_id):
    from app.db.models.service import Service, ServiceCategory
    cat = ServiceCategory(id=uuid4(), tenant_id=tenant_id, name=f"Cat {uuid4().hex[:4]}", is_pm=False)
    db.add(cat)
    await db.commit()
    svc = Service(id=uuid4(), tenant_id=tenant_id, category_id=cat.id, name="Brake job",
                  base_price=Decimal("100.00"), duration_minutes=90, is_active=True)
    db.add(svc)
    await db.commit()
    return svc


@pytest.mark.asyncio
async def test_counts_booked_repair_work_separately_from_pms(db_session):
    from datetime import datetime, timezone as tz

    tenant, fc, user = await _seed(db_session)
    svc = await _a_service(db_session, tenant.id)
    pm_truck = _vehicle(tenant.id, fc.id, unit_number="603", pm_due_date=DAY)
    booked = _vehicle(tenant.id, fc.id, unit_number="412")
    db_session.add_all([pm_truck, booked])
    await db_session.commit()
    await _join_fleet(db_session, tenant.id, fc.id, pm_truck, booked)
    db_session.add(_appointment(
        tenant.id, fc.id, booked.id, svc.id, datetime(2026, 11, 4, 15, 0, tzinfo=tz.utc)))
    await db_session.commit()

    out = await fleet.pm_day_load(
        start=DAY, end=DAY, include_repair_orders=True, db=db_session, current_user=user)

    assert out[0].count == 1          # PM load stays the PM count
    assert out[0].booked_count == 1   # corrective work is its own number
    assert out[0].units == ["603"]


@pytest.mark.asyncio
async def test_omits_booked_work_when_not_requested(db_session):
    """The PM-only view must not change: it is the default."""
    from datetime import datetime, timezone as tz

    tenant, fc, user = await _seed(db_session)
    svc = await _a_service(db_session, tenant.id)
    booked = _vehicle(tenant.id, fc.id, unit_number="412")
    db_session.add(booked)
    await db_session.commit()
    await _join_fleet(db_session, tenant.id, fc.id, booked)
    db_session.add(_appointment(
        tenant.id, fc.id, booked.id, svc.id, datetime(2026, 11, 4, 15, 0, tzinfo=tz.utc)))
    await db_session.commit()

    out = await fleet.pm_day_load(start=DAY, end=DAY, db=db_session, current_user=user)

    assert out == []


@pytest.mark.asyncio
async def test_ignores_cancelled_and_no_show_appointments(db_session):
    """A cancelled booking is not shop load."""
    from datetime import datetime, timezone as tz
    from app.db.models.appointment import AppointmentStatus

    tenant, fc, user = await _seed(db_session)
    svc = await _a_service(db_session, tenant.id)
    v = _vehicle(tenant.id, fc.id, unit_number="412")
    db_session.add(v)
    await db_session.commit()
    await _join_fleet(db_session, tenant.id, fc.id, v)
    when = datetime(2026, 11, 4, 15, 0, tzinfo=tz.utc)
    db_session.add_all([
        _appointment(tenant.id, fc.id, v.id, svc.id, when, status=AppointmentStatus.CANCELLED),
        _appointment(tenant.id, fc.id, v.id, svc.id, when, status=AppointmentStatus.NO_SHOW),
        _appointment(tenant.id, fc.id, v.id, svc.id, when, status=AppointmentStatus.CONFIRMED),
    ])
    await db_session.commit()

    out = await fleet.pm_day_load(
        start=DAY, end=DAY, include_repair_orders=True, db=db_session, current_user=user)

    assert out[0].booked_count == 1


@pytest.mark.asyncio
async def test_buckets_bookings_by_shop_local_day_not_utc(db_session):
    """A 9pm shop-local booking belongs to that day, not to UTC's tomorrow.

    The shop runs in America/New_York; 2026-11-04 21:00 local is 2026-11-05
    02:00 UTC. Bucketing on the raw timestamp would move the truck to the wrong
    day and make a busy evening look like a free one.
    """
    from datetime import datetime, timezone as tz

    tenant, fc, user = await _seed(db_session)
    tenant.timezone = "America/New_York"
    await db_session.commit()
    svc = await _a_service(db_session, tenant.id)
    v = _vehicle(tenant.id, fc.id, unit_number="412")
    db_session.add(v)
    await db_session.commit()
    await _join_fleet(db_session, tenant.id, fc.id, v)
    db_session.add(_appointment(
        tenant.id, fc.id, v.id, svc.id, datetime(2026, 11, 5, 2, 0, tzinfo=tz.utc)))
    await db_session.commit()

    out = await fleet.pm_day_load(
        start=DAY, end=DAY, include_repair_orders=True, db=db_session, current_user=user)

    assert len(out) == 1
    assert out[0].day == DAY
    assert out[0].booked_count == 1


@pytest.mark.asyncio
async def test_reports_a_day_that_has_only_booked_work(db_session):
    """A day with no PM but three repair jobs is still a busy day."""
    from datetime import datetime, timezone as tz

    tenant, fc, user = await _seed(db_session)
    svc = await _a_service(db_session, tenant.id)
    v = _vehicle(tenant.id, fc.id, unit_number="412")
    db_session.add(v)
    await db_session.commit()
    await _join_fleet(db_session, tenant.id, fc.id, v)
    db_session.add(_appointment(
        tenant.id, fc.id, v.id, svc.id, datetime(2026, 11, 4, 15, 0, tzinfo=tz.utc)))
    await db_session.commit()

    out = await fleet.pm_day_load(
        start=DAY, end=DAY, include_repair_orders=True, db=db_session, current_user=user)

    assert out[0].count == 0
    assert out[0].booked_count == 1


@pytest.mark.asyncio
async def test_does_not_leak_another_tenants_bookings(db_session):
    from datetime import datetime, timezone as tz

    tenant, fc, user = await _seed(db_session)
    other_tenant, other_fc, _ = await _seed(db_session)
    other_svc = await _a_service(db_session, other_tenant.id)
    theirs = _vehicle(other_tenant.id, other_fc.id, unit_number="THEIRS")
    db_session.add(theirs)
    await db_session.commit()
    await _join_fleet(db_session, other_tenant.id, other_fc.id, theirs)
    db_session.add(_appointment(
        other_tenant.id, other_fc.id, theirs.id, other_svc.id,
        datetime(2026, 11, 4, 15, 0, tzinfo=tz.utc)))
    await db_session.commit()

    out = await fleet.pm_day_load(
        start=DAY, end=DAY, include_repair_orders=True, db=db_session, current_user=user)

    assert out == []
