"""Isolated-database regressions for fail-closed appointment payment routes."""
from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import select
from app.api.v1.endpoints import appointments
from app.db.base import Base
from app.db.models.appointment import Appointment, AppointmentStatus
from app.db.models.customer import Customer
from app.db.models.service import Service
from app.db.models.tenant import Tenant
from app.db.models.user import UserRole

ENDPOINTS = [appointments.create_appointment_payment, appointments.confirm_appointment_payment]
STAFF = [UserRole.GARAGE_OWNER, UserRole.GARAGE_ADMIN, UserRole.RECEPTIONIST]

async def seed(db):
    tenant = Tenant(name='Payment guard test', slug=f'payment-guard-{uuid4()}')
    db.add(tenant)
    await db.flush()
    customer = Customer(tenant_id=tenant.id, first_name='Synthetic', last_name='Customer', email=f'{uuid4()}@example.test')
    service = Service(tenant_id=tenant.id, name='Synthetic service', duration_minutes=60)
    db.add_all([customer, service])
    await db.flush()
    apt = Appointment(tenant_id=tenant.id, customer_id=customer.id, service_id=service.id,
        scheduled_at=datetime(2026, 11, 4, 14, tzinfo=timezone.utc), duration_minutes=60,
        status=AppointmentStatus.PENDING, price=Decimal('123.45'), confirmation_number=f'TEST-{uuid4().hex[:12]}',
        stripe_payment_intent_id=f'pi_historical_{uuid4().hex}', customer_notes='Preserve history')
    db.add(apt)
    await db.flush()
    return tenant, customer, apt

async def snapshot(db):
    tables = [t for t in sorted(Base.metadata.tables.values(), key=lambda table: table.name) if any(word in t.name for word in ('appointment', 'payment', 'invoice', 'receipt', 'audit', 'outbox'))]
    result = []
    for table in tables:
        rows = (await db.execute(select(table).execution_options(autoflush=False))).all()
        result.append((table.name, tuple(sorted(repr(tuple(row)) for row in rows))))
    return tuple(result)

def block_writers(monkeypatch, db):
    from app.services import stripe_service
    import stripe
    provider = Mock(side_effect=AssertionError('No provider calls'))
    monkeypatch.setattr(stripe_service, 'create_payment_intent', provider)
    monkeypatch.setattr(stripe.PaymentIntent, 'create', provider)
    monkeypatch.setattr(stripe.PaymentIntent, 'retrieve', provider)
    monkeypatch.setattr(stripe.Refund, 'create', provider)
    commit = AsyncMock(side_effect=AssertionError('No commits'))
    flush = AsyncMock(side_effect=AssertionError('No flushes'))
    monkeypatch.setattr(db, 'commit', commit)
    monkeypatch.setattr(db, 'flush', flush)
    return provider, commit, flush

def assert_no_calls(writers):
    provider, commit, flush = writers
    provider.assert_not_called()
    commit.assert_not_awaited()
    flush.assert_not_awaited()

@pytest.mark.asyncio
@pytest.mark.parametrize('endpoint', ENDPOINTS)
@pytest.mark.parametrize('role', [UserRole.CUSTOMER, *STAFF])
async def test_admitted_actor_gets_structured_409_without_writes(db_session, monkeypatch, endpoint, role):
    tenant, customer, apt = await seed(db_session)
    before = await snapshot(db_session)
    writers = block_writers(monkeypatch, db_session)
    actor = SimpleNamespace(role=role, tenant_id=tenant.id, customer_id=customer.id if role == UserRole.CUSTOMER else None)
    with pytest.raises(HTTPException) as error:
        await endpoint(apt.id, db_session, actor)
    assert error.value.status_code == 409
    assert error.value.detail == {'code': 'appointment_payment_verification_unavailable', 'message': 'Online payment for this appointment is unavailable. Contact the shop for help.'}
    assert await snapshot(db_session) == before
    assert not db_session.new and not db_session.dirty and not db_session.deleted
    assert_no_calls(writers)

@pytest.mark.asyncio
@pytest.mark.parametrize('endpoint', ENDPOINTS)
@pytest.mark.parametrize('role', [UserRole.CUSTOMER, *STAFF])
async def test_foreign_tenant_has_no_admission_even_with_matching_customer(db_session, monkeypatch, endpoint, role):
    _, customer, apt = await seed(db_session)
    before = await snapshot(db_session)
    writers = block_writers(monkeypatch, db_session)
    with pytest.raises(HTTPException) as error:
        await endpoint(apt.id, db_session, SimpleNamespace(role=role, tenant_id=uuid4(), customer_id=customer.id))
    assert error.value.status_code == 404
    assert error.value.detail == 'Appointment not found'
    assert await snapshot(db_session) == before
    assert_no_calls(writers)

@pytest.mark.asyncio
@pytest.mark.parametrize('endpoint', ENDPOINTS)
@pytest.mark.parametrize('case', ['other_customer', 'missing_customer', 'missing_tenant', 'mechanic', 'fleet_manager', 'driver', 'super_admin', 'missing_appointment', 'deleted_appointment'])
async def test_unrelated_principals_and_unavailable_records_get_404(db_session, monkeypatch, endpoint, case):
    tenant, customer, apt = await seed(db_session)
    actor = SimpleNamespace(role=UserRole.CUSTOMER, tenant_id=tenant.id, customer_id=customer.id)
    appointment_id = apt.id
    if case == 'other_customer': actor.customer_id = uuid4()
    elif case == 'missing_customer': actor.customer_id = None
    elif case == 'missing_tenant': actor.tenant_id = None
    elif case == 'missing_appointment': appointment_id = uuid4()
    elif case == 'deleted_appointment':
        apt.deleted_at = datetime.now(timezone.utc)
        await db_session.flush()
    else: actor.role = UserRole(case)
    before = await snapshot(db_session)
    writers = block_writers(monkeypatch, db_session)
    with pytest.raises(HTTPException) as error:
        await endpoint(appointment_id, db_session, actor)
    assert error.value.status_code == 404
    assert await snapshot(db_session) == before
    assert_no_calls(writers)

@pytest.mark.asyncio
@pytest.mark.parametrize('endpoint', ENDPOINTS)
@pytest.mark.parametrize('status', [AppointmentStatus.CONFIRMED, AppointmentStatus.COMPLETED, AppointmentStatus.CANCELLED])
async def test_historical_status_and_payment_evidence_stay_unchanged(db_session, monkeypatch, endpoint, status):
    tenant, customer, apt = await seed(db_session)
    apt.status = status
    apt.paid_at = datetime(2026, 11, 1, 14, tzinfo=timezone.utc)
    await db_session.flush()
    before = await snapshot(db_session)
    writers = block_writers(monkeypatch, db_session)
    with pytest.raises(HTTPException) as error:
        await endpoint(apt.id, db_session, SimpleNamespace(role=UserRole.CUSTOMER, tenant_id=tenant.id, customer_id=customer.id))
    assert error.value.status_code == 409
    assert await snapshot(db_session) == before
    assert_no_calls(writers)
