"""Opt-in, separate local database and disposable schemas: genuine two-connection races."""
import asyncio
import os
from uuid import uuid4
from pathlib import Path
import importlib.util
from dataclasses import replace
from datetime import timedelta
import pytest
import pytest_asyncio
from fastapi import HTTPException
from sqlalchemy import text,select,func
from sqlalchemy.ext.asyncio import create_async_engine,async_sessionmaker
from sqlalchemy.engine import make_url
from alembic.migration import MigrationContext
from alembic.operations import Operations
from app.db.base import Base
from app.db.models.appointment import Appointment,AppointmentStatus
from app.db.models.booking_payment import BookingReceipt,BookingPaymentAttempt
from app.services import booking_payments as booking
from app.api.v1.endpoints.appointments import BookingAttemptCreate
from test_verified_booking_flow import setup_booking,result

@pytest_asyncio.fixture
async def pg_booking(monkeypatch):
    url=os.environ.get('BOOKING_POSTGRES_TEST_URL')
    if not url:pytest.skip('Isolated booking concurrency database not configured')
    parsed=make_url(url)
    if parsed.host not in {'127.0.0.1','localhost'} or parsed.database!='booking_concurrency_tests':raise RuntimeError('Only isolated booking concurrency database permitted')
    schema='booking_'+uuid4().hex
    admin=create_async_engine(url)
    async with admin.begin() as connection:await connection.execute(text(f'CREATE SCHEMA {schema}'))
    engine=create_async_engine(url,connect_args={'server_settings':{'search_path':schema}})
    async with engine.begin() as connection:await connection.run_sync(Base.metadata.create_all)
    factory=async_sessionmaker(engine,expire_on_commit=False,autoflush=False)
    async with factory() as db:
        setup=await setup_booking.__wrapped__(db,monkeypatch)
    try:yield factory,setup,engine
    finally:
        await engine.dispose()
        async with admin.begin() as connection:await connection.execute(text(f'DROP SCHEMA {schema} CASCADE'))
        await admin.dispose()

async def race(factory,callbacks):
    async def execute(callback):
        async with factory() as db:
            try:return await callback(db)
            except HTTPException as error:
                await db.rollback();return error
    return await asyncio.gather(*(execute(callback) for callback in callbacks))

@pytest.mark.asyncio
@pytest.mark.parametrize('same_key',[False,True])
async def test_overlapping_reservation_race_never_overbooks(pg_booking,same_key):
    factory,setup,_=pg_booking;actor,body=setup[3:5]
    outcomes=await race(factory,[lambda db:booking.reserve(db,actor,body,'race-reserve-one'),lambda db:booking.reserve(db,actor,body,'race-reserve-one' if same_key else 'race-reserve-two')])
    async with factory() as db:assert await db.scalar(select(func.count(Appointment.id)))==1
    assert any(isinstance(item,Appointment) for item in outcomes)
    assert all(isinstance(item,Appointment) or item.status_code==409 for item in outcomes)

@pytest.mark.asyncio
async def test_browser_and_webhook_success_race_has_one_receipt(pg_booking,monkeypatch):
    factory,setup,_=pg_booking;actor,body=setup[3:5]
    from unittest.mock import AsyncMock
    from app.services.booking_payment_provider import BookingProviderError
    monkeypatch.setattr(booking.provider,'create_booking_payment',AsyncMock(side_effect=BookingProviderError('Unknown',outcome_unknown=True,provider_id='race-provider')))
    async with factory() as db:
        apt=await booking.reserve(db,actor,body,'receipt-race-hold')
        await booking.start_attempt(db,actor,apt.id,BookingAttemptCreate(expected_version=1,price_snapshot_sha256=apt.price_snapshot_sha256,quickbooks_token='synthetic'),'receipt-race-attempt')
        attempt=await db.scalar(select(BookingPaymentAttempt));evidence=result(apt,attempt,provider_id='race-provider');apt_id=apt.id;attempt_id=attempt.id
    outcomes=await race(factory,[lambda db:booking.apply_result(db,apt_id,attempt_id,evidence),lambda db:booking.apply_result(db,apt_id,attempt_id,evidence,source='verified_connect_webhook',event_id='evt-race')])
    async with factory() as db:
        assert await db.scalar(select(func.count(BookingReceipt.id)))==1
        apt=await db.get(Appointment,apt_id);assert apt.status==AppointmentStatus.CONFIRMED

@pytest.mark.asyncio
async def test_pending_attempt_double_click_starts_provider_once(pg_booking,monkeypatch):
    factory,setup,_=pg_booking;actor,body=setup[3:5]
    from unittest.mock import AsyncMock
    from app.services.booking_payment_provider import BookingProviderError
    started=asyncio.Event();release=asyncio.Event()
    async def create(*args,**kwargs):started.set();await release.wait();raise BookingProviderError('Unknown',outcome_unknown=True)
    creator=AsyncMock(side_effect=create);monkeypatch.setattr(booking.provider,'create_booking_payment',creator)
    async with factory() as db:
        apt=await booking.reserve(db,actor,body,'attempt-race-hold');apt_id=apt.id
        request=BookingAttemptCreate(expected_version=1,price_snapshot_sha256=apt.price_snapshot_sha256,quickbooks_token='synthetic')
    async def first():
        async with factory() as db:return await booking.start_attempt(db,actor,apt_id,request,'attempt-race-payment')
    task=asyncio.create_task(first());await asyncio.wait_for(started.wait(),5)
    async with factory() as db:
        second=await booking.start_attempt(db,actor,apt_id,request,'attempt-race-payment')
        assert second['state']=='creating'
    release.set();await task
    creator.assert_awaited_once()

@pytest.mark.asyncio
async def test_additive_198_migration_and_immutable_receipt_trigger(pg_booking,monkeypatch):
    factory,setup,engine=pg_booking
    # Build the exact pre-198 table shape in this disposable schema only.
    async with engine.begin() as connection:
        await connection.execute(text('ALTER TABLE appointments DROP CONSTRAINT fk_booking_confirmed_receipt'))
        await connection.execute(text('ALTER TABLE appointments DROP CONSTRAINT ck_verified_booking_snapshot'))
        for name in ['booking_payment_events','booking_receipts','booking_payment_attempts','visit_requests']:await connection.execute(text(f'DROP TABLE {name} CASCADE'))
        for name in ['booking_kind','booking_payment_version','booking_payment_state','booking_version','hold_expires_at','price_snapshot_sha256','booking_idempotency_key','booking_request_sha256','confirmed_receipt_id','booking_currency','booking_provider_configuration_version','booking_provider_environment']:await connection.execute(text(f'ALTER TABLE appointments DROP COLUMN {name} CASCADE'))
        await connection.execute(text('ALTER TABLE appointments DROP CONSTRAINT uq_booking_appointment_tenant_id'))
        await connection.execute(text('ALTER TABLE services DROP CONSTRAINT uq_booking_service_tenant_id'))
        def upgrade(sync):
            spec=importlib.util.spec_from_file_location('booking_migration',Path(__file__).parents[1]/'alembic/versions/198_verified_booking_payments.py')
            module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
            with Operations.context(MigrationContext.configure(sync)):module.upgrade()
        await connection.run_sync(upgrade)
    async with factory() as db:
        assert await db.scalar(text("SELECT count(*) FROM information_schema.columns WHERE table_schema=current_schema() AND table_name='appointments' AND column_name='hold_expires_at'"))==1
        from unittest.mock import AsyncMock
        from sqlalchemy.exc import DBAPIError
        apt=await booking.reserve(db,setup[3],setup[4],'migration-paid-hold')
        async def create(session,binding,**kwargs):
            attempt=await session.scalar(select(BookingPaymentAttempt));return result(apt,attempt,provider_id='migration-charge')
        monkeypatch.setattr(booking.provider,'create_booking_payment',AsyncMock(side_effect=create))
        await booking.start_attempt(db,setup[3],apt.id,BookingAttemptCreate(expected_version=1,price_snapshot_sha256=apt.price_snapshot_sha256,quickbooks_token='synthetic'),'migration-paid-attempt')
        receipt=await db.scalar(select(BookingReceipt));receipt_id=receipt.id
        with pytest.raises(DBAPIError):await db.execute(text('UPDATE booking_receipts SET amount_received_minor=1 WHERE id=:id'),{'id':receipt_id})
        await db.rollback()
        assert (await db.get(BookingReceipt,receipt_id)).amount_received_minor==12000
        other=await booking.reserve(db,setup[3],setup[4].model_copy(update={'scheduled_at':setup[4].scheduled_at+timedelta(hours=2)}),'migration-unpaid-hold')
        with pytest.raises(DBAPIError):await db.execute(text("UPDATE appointments SET status='confirmed' WHERE id=:id"),{'id':other.id})
        await db.rollback()

@pytest.mark.asyncio
async def test_expiry_rechecks_after_verified_success_commits_between_discovery_and_lock(pg_booking,monkeypatch):
    factory,setup,_=pg_booking;actor,body=setup[3:5]
    from unittest.mock import AsyncMock
    from app.services.booking_payment_provider import BookingProviderError
    monkeypatch.setattr(booking.provider,'create_booking_payment',AsyncMock(side_effect=BookingProviderError('Unknown',outcome_unknown=True,provider_id='expiry-race-provider')))
    async with factory() as db:
        apt=await booking.reserve(db,actor,body,'expiry-success-hold')
        await booking.start_attempt(db,actor,apt.id,BookingAttemptCreate(expected_version=1,price_snapshot_sha256=apt.price_snapshot_sha256,quickbooks_token='synthetic'),'expiry-success-attempt')
        attempt=await db.scalar(select(BookingPaymentAttempt));evidence=result(apt,attempt,provider_id='expiry-race-provider');apt_id=apt.id;attempt_id=attempt.id;expiry=booking.utc(apt.hold_expires_at)
    # The expiry query sees the still-pending committed row. Before it locks,
    # the verified-success transaction commits its receipt/confirmed state.
    original_locks=booking.locks;original_now=booking.now
    async def interleaved_lock(db,tenant_id):
        if asyncio.current_task().get_name()=='expiry-after-discovery':
            async def finalize_success():
                async with factory() as success:
                    await booking.apply_result(success,apt_id,attempt_id,evidence)
            await asyncio.create_task(finalize_success(),name='verified-success-before-expiry-lock')
        await original_locks(db,tenant_id)
    monkeypatch.setattr(booking,'locks',interleaved_lock)
    monkeypatch.setattr(booking,'now',lambda:expiry+timedelta(seconds=1) if asyncio.current_task().get_name()=='expiry-after-discovery' else original_now())
    async def expiry_pass():
        async with factory() as db:return await booking.expire_holds(db)
    assert await asyncio.create_task(expiry_pass(),name='expiry-after-discovery')==0
    async with factory() as db:
        apt=await db.get(Appointment,apt_id)
        assert apt.status==AppointmentStatus.CONFIRMED and apt.booking_payment_state=='paid'
        assert await db.scalar(select(func.count(BookingReceipt.id)))==1

@pytest.mark.asyncio
async def test_cancellation_and_payment_start_race_never_releases_an_unknown_charge(pg_booking,monkeypatch):
    factory,setup,_=pg_booking;actor,body=setup[3:5]
    from unittest.mock import AsyncMock
    from app.services.booking_payment_provider import BookingProviderError
    from app.api.v1.endpoints.appointments import cancel_appointment
    creator=AsyncMock(side_effect=BookingProviderError('Unknown',outcome_unknown=True))
    monkeypatch.setattr(booking.provider,'create_booking_payment',creator)
    async with factory() as db:
        apt=await booking.reserve(db,actor,body,'cancel-race-hold');apt_id=apt.id
        request=BookingAttemptCreate(expected_version=1,price_snapshot_sha256=apt.price_snapshot_sha256,quickbooks_token='synthetic')
    await race(factory,[lambda db:cancel_appointment(apt_id,db,actor),lambda db:booking.start_attempt(db,actor,apt_id,request,'cancel-race-payment')])
    async with factory() as db:
        apt=await db.get(Appointment,apt_id)
        count=await db.scalar(select(func.count(BookingPaymentAttempt.id)))
        if apt.status==AppointmentStatus.CANCELLED:
            assert count==0 and creator.await_count==0
        else:
            assert apt.status==AppointmentStatus.PENDING and apt.booking_payment_state=='payment_processing'
            assert count==1 and creator.await_count==1
        assert await db.scalar(select(func.count(BookingReceipt.id)))==0
