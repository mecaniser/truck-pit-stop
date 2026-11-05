"""Disposable PostgreSQL resolution races; caller must supply NEW database URL."""
import asyncio
from decimal import Decimal
from uuid import uuid4
import pytest
from sqlalchemy import select,func
from sqlalchemy.ext.asyncio import async_sessionmaker
from test_booking_readiness_legacy_mirrors_postgres import pg_readiness
from test_payment_attempt_resolution import pending,command
from test_zelle_explicit_confirmation import fictional_zelle_context
from app.services import payment_attempt_resolution as resolution,invoice_settlement_service as domain
from app.db.models.invoice_settlement import InvoicePaymentAttempt as Attempt,InvoicePaymentLedgerEvent as Event

@pytest.mark.asyncio
async def test_pg_cancel_wins_stale_dispatch_cannot_cross_provider_boundary(pg_readiness,monkeypatch):
    db=pg_readiness;assert db.bind.dialect.name=='postgresql'
    ctx=await fictional_zelle_context(db,monkeypatch);a=await pending(db,ctx,rail='card');body=command(a,ctx.settlement);aid=a.id
    sessions=async_sessionmaker(db.bind,expire_on_commit=False,autoflush=False)
    cancellation_written=asyncio.Event();dispatch_attempted=asyncio.Event()
    async def cancel():
        async with sessions() as own:
            await resolution.execute(own,aid,body,'race-cancel-command',actor=ctx.customer_user)
            cancellation_written.set();await asyncio.wait_for(dispatch_attempted.wait(),5)
            await own.commit()
    async def dispatch():
        await cancellation_written.wait()
        async with sessions() as own:
            current=await own.get(Attempt,aid)
            try:
                await resolution.mark_submission_started(own,current,ctx.customer_user)
                raise AssertionError('Dispatch crossed the cancelled request boundary')
            except domain.SettlementDomainError as error:assert error.code=='invoice_busy'
            finally:await own.rollback();dispatch_attempted.set()
    await asyncio.gather(cancel(),dispatch())
    async with sessions() as own:
        current=await own.get(Attempt,aid)
        with pytest.raises(domain.SettlementDomainError):await resolution.mark_submission_started(own,current,ctx.customer_user)
        assert current.state=='failed'
        assert await own.scalar(select(func.count(Event.id)).where(Event.attempt_id==aid,Event.event_type=='card_submission_started'))==0
        assert await own.scalar(select(func.count(Event.id)).where(Event.attempt_id==aid,Event.event_type=='attempt_cancelled'))==1

@pytest.mark.asyncio
async def test_pg_committed_submission_wins_cancel_unknown_stays_reserved(pg_readiness,monkeypatch):
    db=pg_readiness;assert db.bind.dialect.name=='postgresql'
    ctx=await fictional_zelle_context(db,monkeypatch);a=await pending(db,ctx,rail='card');body=command(a,ctx.settlement)
    sessions=async_sessionmaker(db.bind,expire_on_commit=False,autoflush=False)
    async with sessions() as dispatch:
        current=await dispatch.get(Attempt,a.id)
        await resolution.mark_submission_started(dispatch,current,ctx.customer_user)
        await dispatch.rollback()  # A crash after the committed marker cannot erase it.
    async with sessions() as cancel:
        with pytest.raises(domain.SettlementDomainError) as denied:await resolution.execute(cancel,a.id,body,'race-after-dispatch',actor=ctx.customer_user)
        assert denied.value.code=='attempt_resolution_not_allowed'
        current=await cancel.get(Attempt,a.id)
        dto=(await resolution.project_many(cancel,[current],actor=ctx.customer_user))[current.id]
        assert dto.reservation_amount=='168.44' and not dto.can_retry
        assert await cancel.scalar(select(func.count(Event.id)).where(Event.attempt_id==a.id,Event.event_type=='card_submission_started'))==1

@pytest.mark.asyncio
async def test_pg_same_cancel_command_concurrent_replay_releases_once(pg_readiness,monkeypatch):
    db=pg_readiness;assert db.bind.dialect.name=='postgresql'
    ctx=await fictional_zelle_context(db,monkeypatch);a=await pending(db,ctx);body=command(a,ctx.settlement)
    sessions=async_sessionmaker(db.bind,expire_on_commit=False,autoflush=False)
    async def call():
        async with sessions() as own:
            try:
                result=await resolution.execute(own,a.id,body,'same-race-command',actor=ctx.customer_user)
                await own.commit();return result[0].state
            except domain.SettlementDomainError as denied:
                await own.rollback();assert denied.code=='invoice_busy';return 'busy'
    results=await asyncio.gather(call(),call());assert 'failed' in results
    assert await call()=='failed'
    await db.refresh(ctx.settlement)
    assert ctx.settlement.active_pending_principal==Decimal('0.00')
    assert await db.scalar(select(func.count(Event.id)).where(Event.attempt_id==a.id,Event.event_type=='attempt_cancelled'))==1
