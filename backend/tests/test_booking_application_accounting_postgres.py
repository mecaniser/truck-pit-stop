"""Opt-in disposable-schema proof for migration200; never uses application DB."""
import importlib.util
import os
from pathlib import Path
from uuid import uuid4
import pytest
import pytest_asyncio
from sqlalchemy import text, select
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from alembic.migration import MigrationContext
from alembic.operations import Operations
from app.db.base import Base
from app.db.models.booking_application import BookingReceiptApplication,BookingAccountingReviewTask
from tests.test_booking_application_accounting import context,ack
from app.services import booking_application_accounting as accounting

@pytest_asyncio.fixture
async def pg_session():
    url=os.environ.get('BOOKING_APPLICATION_TEST_DATABASE_URL')
    if not url:pytest.skip('Explicit disposable PostgreSQL DSN required')
    engine=create_async_engine(url.replace('postgresql+psycopg://','postgresql+asyncpg://').replace('postgresql://','postgresql+asyncpg://'))
    schema='booking_application_test_'+uuid4().hex
    async with engine.begin() as conn:
        await conn.execute(text(f'CREATE SCHEMA "{schema}"'))
        await conn.execute(text(f'SET LOCAL search_path TO "{schema}"'))
        excluded={'booking_receipt_applications','booking_accounting_review_tasks','booking_accounting_review_events'}
        await conn.run_sync(lambda sync:Base.metadata.create_all(sync,tables=[t for t in Base.metadata.sorted_tables if t.name not in excluded]))
        await conn.execute(text('DROP INDEX IF EXISTS ix_booking_receipt_tenant_received'))
        await conn.execute(text('ALTER TABLE booking_receipts DROP COLUMN version'))
        await conn.execute(text('ALTER TABLE booking_payment_events DROP COLUMN verified_refund_amount_minor'))
        await conn.execute(text('ALTER TABLE booking_payment_events DROP COLUMN verified_refund_delta_minor'))
        await conn.execute(text('ALTER TABLE booking_payment_events DROP COLUMN client_idempotency_key'))
        await conn.execute(text('ALTER TABLE booking_payment_events DROP COLUMN provider_refund_reference'))
        await conn.execute(text('ALTER TABLE booking_payment_events DROP COLUMN request_sha256'))
        await conn.execute(text('ALTER TABLE booking_payment_events DROP COLUMN verified_dispute_amount_minor'))
        path=Path(__file__).parents[1]/'alembic/versions/200_booking_receipt_applications.py'
        spec=importlib.util.spec_from_file_location('migration200',path);migration=importlib.util.module_from_spec(spec);spec.loader.exec_module(migration)
        def upgrade(sync):
            with Operations.context(MigrationContext.configure(sync)):
                migration.upgrade()
        await conn.run_sync(upgrade)
        await conn.execute(text('CREATE TRIGGER verified_booking_confirmation BEFORE INSERT OR UPDATE ON appointments FOR EACH ROW EXECUTE FUNCTION guard_booking_confirmation()'))
    try:
        async with engine.connect() as conn:
            await conn.execute(text(f'SET search_path TO "{schema}"'));await conn.commit()
            async with async_sessionmaker(bind=conn,expire_on_commit=False)() as session:
                session.info['test_engine']=engine;session.info['test_schema']=schema
                yield session
    finally:
        async with engine.begin() as conn:await conn.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        await engine.dispose()

@pytest.mark.asyncio
async def test_pg_migration_ack_permanent_hold(pg_session):
    ctx=await context(pg_session)
    tasks=await accounting.ensure_manual_accounting_tasks(pg_session,receipt=ctx[1],application=ctx[-1])
    await ack(pg_session,ctx,tasks[0]);await ack(pg_session,ctx,tasks[1]);await pg_session.commit()
    assert await accounting.invoice_has_booking_export_hold(pg_session,ctx[0].id,ctx[-2].id)
    assert tasks[1].state=='externally_reconciled'

@pytest.mark.asyncio
@pytest.mark.parametrize('field,value',[('amount_minor',1),('settlement_id',uuid4()),('tenant_id',uuid4())])
async def test_pg_direct_sql_application_immutable(pg_session,field,value):
    ctx=await context(pg_session);await pg_session.commit()
    with pytest.raises(Exception,match='append-only'):
        await pg_session.execute(text(f'UPDATE booking_receipt_applications SET {field}=:value WHERE id=:id'),{'value':value,'id':ctx[-1].id})
    await pg_session.rollback()

@pytest.mark.asyncio
async def test_pg_refund_cannot_spend_applied_liability(pg_session):
    ctx=await context(pg_session);await pg_session.commit()
    with pytest.raises(Exception,match='refund exceeds'):
        await pg_session.execute(text('UPDATE booking_receipts SET refunded_amount_minor=7000,version=version+1 WHERE id=:id'),{'id':ctx[1].id})
    await pg_session.rollback()

@pytest.mark.asyncio
@pytest.mark.parametrize('field,expected',[('settlement_id','invalid booking application binding'),('customer_id','invalid booking application binding'),('amount_minor','overapplication'),('actor_user_id','invalid booking application binding')])
async def test_pg_forged_insert_binding_or_overapplication(pg_session,field,expected):
    from sqlalchemy import insert
    ctx=await context(pg_session);await pg_session.commit()
    original=ctx[-1]
    values={c.name:getattr(original,c.name) for c in BookingReceiptApplication.__table__.columns}
    values.update(id=uuid4(),idempotency_key=str(uuid4()))
    values[field]=7000 if field=='amount_minor' else uuid4()
    with pytest.raises(Exception,match=expected):
        await pg_session.execute(insert(BookingReceiptApplication.__table__).values(**values))
    await pg_session.rollback()


@pytest.mark.asyncio
async def test_pg_task_ack_requires_durable_event(pg_session):
    ctx=await context(pg_session)
    tasks=await accounting.ensure_manual_accounting_tasks(pg_session,receipt=ctx[1],application=ctx[-1])
    await pg_session.commit()
    await pg_session.execute(text("UPDATE booking_accounting_review_tasks SET state='externally_reconciled',version=version+1 WHERE id=:id"),{'id':tasks[0].id})
    with pytest.raises(Exception,match='lacks evidence'):await pg_session.commit()
    await pg_session.rollback()


@pytest.mark.asyncio
async def test_pg_apply_refund_race_serializes_receipt(pg_session):
    import asyncio
    from sqlalchemy import insert
    ctx=await context(pg_session);await pg_session.commit()
    values={c.name:getattr(ctx[-1],c.name) for c in BookingReceiptApplication.__table__.columns}
    values.update(id=uuid4(),idempotency_key=str(uuid4()),amount_minor=6000)
    await pg_session.execute(insert(BookingReceiptApplication.__table__).values(**values))
    engine=pg_session.info['test_engine'];schema=pg_session.info['test_schema']
    async def refund():
        async with engine.connect() as conn:
            await conn.execute(text(f'SET search_path TO "{schema}"'));await conn.commit()
            try:
                await conn.execute(text('UPDATE booking_receipts SET refunded_amount_minor=1000,version=version+1 WHERE id=:id'),{'id':ctx[1].id})
                await conn.commit()
            finally:await conn.rollback()
    second=asyncio.create_task(refund())
    await asyncio.sleep(.1)
    assert not second.done()  # application holds source receipt lock
    await pg_session.commit()
    with pytest.raises(Exception,match='refund exceeds'):await second
    balance=await accounting.receipt_balances(pg_session,ctx[0].id,ctx[1].id)
    assert balance['applied_minor']==10000 and balance['refunded_minor']==0

@pytest.mark.asyncio
async def test_pg_locked_balance_refreshes_cached_receipt_after_refund(pg_session):
    ctx=await context(pg_session);await pg_session.commit()
    receipt=ctx[1]
    assert receipt.refunded_amount_minor==0 and receipt.version==1
    engine=pg_session.info['test_engine'];schema=pg_session.info['test_schema']
    async with engine.begin() as second:
        await second.execute(text(f'SET LOCAL search_path TO "{schema}"'))
        await second.execute(text('UPDATE booking_receipts SET refunded_amount_minor=2000,version=2 WHERE id=:id'),{'id':receipt.id})
    balance=await accounting.receipt_balances(pg_session,ctx[0].id,receipt.id,lock=True)
    assert balance==dict(received_minor=10000,refunded_minor=2000,applied_minor=4000,unapplied_minor=4000,version=2)
    assert receipt.refunded_amount_minor==2000 and receipt.version==2


@pytest.mark.asyncio
async def test_pg_ack_refreshes_cached_task_after_other_transaction(pg_session):
    from app.db.models.booking_payment import BookingPaymentEvent
    from datetime import datetime,timezone
    from app.services.invoice_settlement_service import SettlementDomainError
    ctx=await context(pg_session)
    tasks=await accounting.ensure_manual_accounting_tasks(pg_session,receipt=ctx[1],application=ctx[-1])
    await pg_session.commit()
    assert tasks[0].state=='awaiting_manual_ack' and tasks[0].version==1
    engine=pg_session.info['test_engine'];schema=pg_session.info['test_schema']
    async with engine.connect() as connection:
        await connection.execute(text(f'SET search_path TO "{schema}"'));await connection.commit()
        async with async_sessionmaker(bind=connection,expire_on_commit=False)() as second:
            event=BookingPaymentEvent(id=uuid4(),tenant_id=ctx[0].id,appointment_id=ctx[2].id,
                attempt_id=ctx[1].attempt_id,source='server_retrieval',after_state='payment_received_review',
                provider=ctx[1].provider,provider_account_id=ctx[1].provider_account_id,
                event_at=datetime.now(timezone.utc),proof_sha256='f'*64)
            second.add(event);await second.flush()
            await accounting.mark_manual_accounting_needs_review(second,tenant_id=ctx[0].id,
                receipt_id=ctx[1].id,source_event_id=event.id,reason='Verified dispute evidence')
            await second.commit()
    with pytest.raises(SettlementDomainError) as error:await ack(pg_session,ctx,tasks[0])
    assert error.value.code=='booking_accounting_version_conflict'
    assert tasks[0].state=='needs_review' and tasks[0].version==2


@pytest.mark.asyncio
@pytest.mark.parametrize('work_status',['confirmed','in_progress','completed'])
async def test_pg_verified_refund_fact_preserves_work_and_applied_credit(pg_session,work_status):
    from app.db.models.appointment import AppointmentStatus
    from app.db.models.booking_payment import BookingPaymentEvent
    from app.services.invoice_settlement_service import SettlementDomainError
    from datetime import datetime,timezone
    ctx=await context(pg_session)
    tasks=await accounting.ensure_manual_accounting_tasks(pg_session,receipt=ctx[1],application=ctx[-1])
    apt=ctx[2];apt.status=AppointmentStatus(work_status);await pg_session.flush()
    event=BookingPaymentEvent(id=uuid4(),tenant_id=ctx[0].id,appointment_id=apt.id,attempt_id=ctx[1].attempt_id,
        source='server_retrieval',after_state='refund_pending',provider=ctx[1].provider,
        provider_account_id=ctx[1].provider_account_id,event_at=datetime.now(timezone.utc),
        proof_sha256='f'*64,verified_refund_amount_minor=8000)
    pg_session.add(event);await pg_session.flush()
    ctx[1].refunded_amount_minor=8000;ctx[1].version+=1
    apt.booking_payment_state='refund_pending'
    await pg_session.flush()
    await accounting.mark_manual_accounting_needs_review(pg_session,tenant_id=ctx[0].id,
        receipt_id=ctx[1].id,source_event_id=event.id,reason='Actual verified refund overlaps applied credit')
    await pg_session.commit()
    assert apt.status.value==work_status and ctx[1].refunded_amount_minor==8000
    assert ctx[-1].amount_minor==4000 and all(task.state=='needs_review' for task in tasks)
    with pytest.raises(SettlementDomainError) as error:
        await accounting.receipt_balances(pg_session,ctx[0].id,ctx[1].id,lock=True)
    assert error.value.code=='booking_receipt_balance_invalid'


@pytest.mark.asyncio
async def test_pg_generic_review_status_cannot_bypass_paid_confirmation(pg_session):
    ctx=await context(pg_session);await pg_session.commit()
    with pytest.raises(Exception,match='verified full booking receipt required'):
        await pg_session.execute(text("UPDATE appointments SET booking_payment_state='payment_received_review' WHERE id=:id"),{'id':ctx[2].id})
    await pg_session.rollback()


@pytest.mark.asyncio
@pytest.mark.parametrize('charge_binding',['missing_receipt','missing_attempt','empty_receipt','empty_attempt','mismatch'])
async def test_pg_application_rejects_missing_or_wrong_charge(pg_session,charge_binding):
    with pytest.raises(Exception,match='invalid booking application binding'):
        await context(pg_session,charge_binding=charge_binding)
    await pg_session.rollback()
