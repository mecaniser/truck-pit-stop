from datetime import date, datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4
from zoneinfo import ZoneInfo

import pytest
from fastapi import HTTPException
from sqlalchemy.dialects import postgresql

from app.api.v1.endpoints.appointments import get_available_slots


class Result:
    def __init__(self, value):
        self.value = value

    def scalar_one_or_none(self):
        return self.value

    def scalars(self):
        return self

    def all(self):
        return self.value


def session(appointments=(), zone='America/New_York', service=None):
    tenant_id = uuid4()
    service = service or SimpleNamespace(id=uuid4(), tenant_id=tenant_id, duration_minutes=60)
    db = SimpleNamespace(execute=AsyncMock(side_effect=[Result(service), Result(zone), Result(appointments)]))
    return db, service, SimpleNamespace(tenant_id=tenant_id)


@pytest.mark.asyncio
@pytest.mark.parametrize('scheduled_at', [
    datetime(2026, 11, 4, 14, tzinfo=timezone.utc),
    datetime(2026, 11, 4, 9, tzinfo=ZoneInfo('America/New_York')),
    datetime(2026, 11, 4, 14),  # legacy SQLite/UTC-naive value
])
async def test_confirmed_overlap_normalizes_aware_and_naive_instants(scheduled_at):
    db, service, actor = session([SimpleNamespace(scheduled_at=scheduled_at, duration_minutes=60)])
    slots = await get_available_slots(service.id, date(2026, 11, 4), db, actor)
    available = {slot.time: slot.available for slot in slots}
    assert available['08:00'] is True  # finishes exactly at appointment start
    assert available['08:30'] is False
    assert available['09:00'] is False
    assert available['09:30'] is False
    assert available['10:00'] is True  # begins exactly at appointment end
    assert slots[0].starts_at == datetime(2026, 11, 4, 13, tzinfo=timezone.utc)
    assert slots[0].timezone == 'America/New_York'
    assert len(slots) == 18


@pytest.mark.asyncio
@pytest.mark.parametrize('day,expected_hour', [(date(2026, 3, 8), 12), (date(2026, 11, 1), 13)])
async def test_shop_hours_follow_dst_in_returned_utc_instant(day, expected_hour):
    db, service, actor = session()
    slots = await get_available_slots(service.id, day, db, actor)
    assert slots[0].time == '08:00'
    assert slots[0].starts_at == datetime(day.year, day.month, day.day, expected_hour, tzinfo=timezone.utc)
    assert all(slot.available for slot in slots)


@pytest.mark.asyncio
async def test_overnight_appointment_is_considered_and_query_is_tenant_status_bound():
    # Begins on the previous shop date, extending until 09:30 on the requested date.
    db, service, actor = session([SimpleNamespace(scheduled_at=datetime(2026, 11, 3, 23, tzinfo=ZoneInfo('America/New_York')), duration_minutes=630)])
    slots = await get_available_slots(service.id, date(2026, 11, 4), db, actor)
    assert {slot.time: slot.available for slot in slots}['08:00'] is False
    assert {slot.time: slot.available for slot in slots}['09:30'] is True
    query = db.execute.call_args_list[2].args[0].compile(dialect=postgresql.dialect())
    assert query.params['tenant_id_1'] == service.tenant_id
    assert {status.value for status in query.params['status_1']} == {'confirmed', 'in_progress'}
    assert query.params['scheduled_at_1'] == datetime(2026, 11, 5, 5, tzinfo=timezone.utc)


@pytest.mark.asyncio
async def test_foreign_and_inactive_services_use_exact_tenant_active_lookup():
    db, service, actor = session()
    db.execute.side_effect = [Result(None)]
    with pytest.raises(HTTPException) as error:
        await get_available_slots(service.id, date(2026, 11, 4), db, actor)
    assert error.value.status_code == 404
    assert db.execute.await_count == 1
    query = db.execute.call_args.args[0].compile(dialect=postgresql.dialect())
    assert query.params['tenant_id_1'] == actor.tenant_id
    assert 'services.is_active IS true' in str(query)
    assert 'services.deleted_at IS NULL' in str(query)


@pytest.mark.asyncio
async def test_invalid_shop_timezone_is_explicitly_unavailable():
    db, service, actor = session(zone='invalid/not-a-zone')
    with pytest.raises(HTTPException) as error:
        await get_available_slots(service.id, date(2026, 11, 4), db, actor)
    assert error.value.status_code == 409


@pytest.mark.asyncio
@pytest.mark.parametrize('foreign,inactive,deleted', [(True, False, False), (False, True, False), (False, False, True)])
async def test_database_foreign_inactive_or_deleted_service_is_not_available(db_session, foreign, inactive, deleted):
    from app.db.models.service import Service
    from app.db.models.tenant import Tenant

    own_tenant = Tenant(name='Own appointment test shop', slug=f'own-{uuid4()}')
    other_tenant = Tenant(name='Other appointment test shop', slug=f'other-{uuid4()}')
    db_session.add_all([own_tenant, other_tenant])
    await db_session.flush()
    service = Service(tenant_id=other_tenant.id if foreign else own_tenant.id, name='Private service', is_active=not inactive, duration_minutes=60, deleted_at=datetime.now(timezone.utc) if deleted else None)
    db_session.add(service)
    await db_session.flush()
    with pytest.raises(HTTPException) as error:
        await get_available_slots(service.id, date(2026, 11, 4), db_session, SimpleNamespace(tenant_id=own_tenant.id))
    assert error.value.status_code == 404
