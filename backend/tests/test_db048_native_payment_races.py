"""Real two-session financial mutations; run only on a disposable migrated PG DB."""
import asyncio
import os
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db.models.invoice_settlement import InvoicePaymentAttempt, InvoiceSettlement, CustomerCreditEntry
from app.services import invoice_settlement_service as svc
from tests.test_db048_cash import context
from tests.test_db048_invoice_settlements import _financial_context, _add_eligible_invoice
from tests.test_db048_tax_exemption_postgres import load

pytestmark = pytest.mark.skipif(not os.environ.get('DB048_POSTGRES_URL'), reason='requires disposable migrated PostgreSQL')


def database():
    url = os.environ['DB048_POSTGRES_URL']
    assert 'local_e2e' not in url and 'production' not in url, 'Never run against business data'
    engine = create_async_engine(url)
    return engine, async_sessionmaker(engine, expire_on_commit=False)


async def make(db, ctx, amount='100', key='create'):
    return await svc.create_attempt(db, invoice=ctx[3], tenant=ctx[0], customer_id=ctx[2].id,
        actor=ctx[1], amount=Decimal(amount), rail='check', expected_settlement_version=ctx[4].version,
        idempotency_key=key, source='staff', subject_type='staff', subject_id=ctx[1].id)


async def confirm(db, ctx, attempt_id, amount=None):
    return await svc.confirm_attempt(db, attempt_id=attempt_id, tenant=ctx[0], actor=ctx[1],
        expected_attempt_version=1, idempotency_key='confirm', received_principal=amount, reference='check-123')


async def busy(operation):
    with pytest.raises(svc.SettlementDomainError) as error:
        await asyncio.wait_for(operation, timeout=2)
    assert error.value.code == 'invoice_busy'
    assert error.value.status_code == 409


@pytest.mark.asyncio
@pytest.mark.parametrize('release', ['commit', 'rollback'])
async def test_lazy_creation_retries_after_transaction_release(monkeypatch, release):
    engine, sessions = database()
    try:
        async with sessions() as seed:
            tenant, owner, customer, invoice = await _financial_context(seed, monkeypatch)
            ids = tenant.id, owner.id, invoice.id
            await seed.commit()
        async with sessions() as a, sessions() as b:
            ca, cb = await load(a, ids), await load(b, ids)
            first = await svc.get_or_create_settlement(a, invoice=ca[3], tenant=ca[0], customer_id=ca[2].id)
            await busy(svc.get_or_create_settlement(b, invoice=cb[3], tenant=cb[0], customer_id=cb[2].id))
            await b.rollback()
            first_id = first.id
            await getattr(a, release)()
            cb = await load(b, ids)
            retry = await svc.get_or_create_settlement(b, invoice=cb[3], tenant=cb[0], customer_id=cb[2].id)
            if release == 'commit': assert retry.id == first_id
            await b.commit()
        async with sessions() as check:
            assert await check.scalar(select(func.count()).select_from(InvoiceSettlement).where(InvoiceSettlement.invoice_id == ids[2])) == 1
    finally:
        await engine.dispose()


@pytest.mark.asyncio
@pytest.mark.parametrize('loser', ['fail', 'expiry'])
async def test_confirm_vs_failure_or_expiry_never_releases_confirmed_principal(monkeypatch, loser):
    engine, sessions = database()
    try:
        async with sessions() as seed:
            ctx = await context(seed, monkeypatch)
            made = await make(seed, ctx)
            made.attempt.expires_at = datetime.now(timezone.utc) - timedelta(hours=1)
            ids, aid = (ctx[0].id, ctx[1].id, ctx[3].id), made.attempt.id
            await seed.commit()
        async with sessions() as a, sessions() as b:
            ca, cb = await load(a, ids), await load(b, ids)
            await confirm(a, ca, aid)
            async def fail():
                return await svc.fail_attempt(b, attempt_id=aid, tenant_id=ids[0], actor=cb[1], expected_attempt_version=1,
                    failure_code='test', idempotency_key='fail')
            if loser == 'fail':
                await busy(fail())
            else:
                # Worker skips a busy tenant, leaving API ownership intact.
                assert await asyncio.wait_for(svc.expire_due_attempts(b, tenant_id=ids[0]), 2) == 0
            await b.rollback()
            await a.commit()
            cb = await load(b, ids)
            if loser == 'fail':
                with pytest.raises(svc.SettlementDomainError) as error: await fail()
                assert error.value.code == 'attempt_transition_conflict'
            else:
                assert await svc.expire_due_attempts(b, tenant_id=ids[0]) == 0
            await b.rollback()
        async with sessions() as check:
            c = await load(check, ids)
            attempt = await check.get(InvoicePaymentAttempt, aid)
            assert attempt.state == 'confirmed'
            assert c[4].confirmed_principal == Decimal('100')
            assert c[4].active_pending_principal == 0
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_other_tenant_progress_and_stale_preloaded_settlement_refresh(monkeypatch):
    engine, sessions = database()
    try:
        async with sessions() as seed:
            first = await context(seed, monkeypatch)
            other = await context(seed, monkeypatch)
            ids = (first[0].id, first[1].id, first[3].id)
            other_ids = (other[0].id, other[1].id, other[3].id)
            await seed.commit()
        async with sessions() as a, sessions() as b, sessions() as independent:
            ca, cb, cc = await load(a, ids), await load(b, ids), await load(independent, other_ids)
            await make(a, ca, '60')
            await asyncio.wait_for(make(independent, cc), 2)
            await independent.commit()
            await a.commit()
            assert cb[4].version == 1  # ORM object was loaded before the winning commit.
            with pytest.raises(svc.SettlementDomainError) as error:
                await make(b, cb, '60', 'second')
            assert error.value.code == 'stale_settlement_version'
            assert cb[4].active_pending_principal == Decimal('60')
            await b.rollback()
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_savepoint_rollback_does_not_leave_false_lock_ownership():
    from app.services.financial_transaction_lock import lock_tenant_financials
    engine, sessions = database()
    tenant_id = uuid4()
    try:
        async with sessions() as a, sessions() as b:
            await a.begin()
            nested = await a.begin_nested()
            await lock_tenant_financials(a, tenant_id)
            await nested.rollback()
            await lock_tenant_financials(b, tenant_id)
            await busy(lock_tenant_financials(a, tenant_id))
            await b.rollback()
            await lock_tenant_financials(a, tenant_id)
            await a.commit()
    finally:
        await engine.dispose()


async def consent(db, ctx, oid, key='consent'):
    return await svc.record_credit_consent(db, overpayment_id=oid, tenant_id=ctx[0].id, actor=ctx[1],
        subject_customer_id=ctx[2].id, channel='in_person', note='Keep excess', idempotency_key=key)


@pytest.mark.asyncio
@pytest.mark.parametrize('winner', ['consent', 'refund'])
async def test_manual_refund_and_credit_consent_have_one_resolution(monkeypatch, winner):
    engine, sessions = database()
    try:
        async with sessions() as seed:
            ctx = await context(seed, monkeypatch)
            made = await make(seed, ctx)
            paid = await confirm(seed, ctx, made.attempt.id, Decimal('110'))
            ids = ctx[0].id, ctx[1].id, ctx[3].id
            oid, rid = paid.overpayment.id, paid.refund.id
            await seed.commit()
        async with sessions() as a, sessions() as b:
            ca, cb = await load(a, ids), await load(b, ids)
            async def refund(db, c):
                return await svc.confirm_manual_refund(db, refund_id=rid, tenant_id=c[0].id,
                    actor=c[1], reference='returned-check-excess', idempotency_key='refund-confirm')
            if winner == 'consent':
                issued = await consent(a, ca, oid)
                await a.flush()
                issued_id = issued.id
                await busy(refund(b, cb))
            else:
                await refund(a, ca)
                await busy(consent(b, cb, oid))
            await b.rollback()
            await a.commit()
            cb = await load(b, ids)
            with pytest.raises(svc.SettlementDomainError) as conflict:
                if winner == 'consent': await refund(b, cb)
                else: await consent(b, cb, oid)
            assert conflict.value.code in {'refund_in_progress', 'refund_already_submitted', 'overpayment_already_resolved'}
            await b.rollback()
            if winner == 'consent':
                cb = await load(b, ids)
                assert (await consent(b, cb, oid)).id == issued_id
                with pytest.raises(svc.SettlementDomainError) as duplicate:
                    await consent(b, cb, oid, 'different-key')
                assert duplicate.value.code == 'overpayment_already_resolved'
                await b.rollback()
        async with sessions() as check:
            count = await check.scalar(select(func.count()).select_from(CustomerCreditEntry).where(CustomerCreditEntry.origin_overpayment_id == oid))
            assert count == (1 if winner == 'consent' else 0)
            c = await load(check, ids)
            assert c[4].refund_pending == 0 and c[4].unapplied_credit == 0
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_customer_credit_cannot_be_spent_on_two_invoices_concurrently(monkeypatch):
    engine, sessions = database()
    try:
        async with sessions() as seed:
            ctx = await context(seed, monkeypatch)
            made = await make(seed, ctx)
            paid = await confirm(seed, ctx, made.attempt.id, Decimal('110'))
            credit = await consent(seed, ctx, paid.overpayment.id)
            await seed.flush()
            cid = credit.id
            one = await _add_eligible_invoice(seed, tenant=ctx[0], customer=ctx[2], reference_invoice=ctx[3], with_shadow_settlement=True)
            two = await _add_eligible_invoice(seed, tenant=ctx[0], customer=ctx[2], reference_invoice=ctx[3], with_shadow_settlement=True)
            ids = (ctx[0].id, ctx[1].id, one.id), (ctx[0].id, ctx[1].id, two.id)
            await seed.commit()
        async with sessions() as a, sessions() as b:
            ca, cb = await load(a, ids[0]), await load(b, ids[1])
            async def spend(db, c, key):
                return await svc.apply_customer_credit(db, credit_id=cid, invoice=c[3], tenant=c[0], customer_id=c[2].id,
                    amount=Decimal('10'), expected_settlement_version=1, actor=c[1], idempotency_key=key)
            first, _ = await spend(a, ca, 'spend-a')
            await a.flush()
            first_id = first.id
            await busy(spend(b, cb, 'spend-b'))
            await b.rollback()
            await a.commit()
            cb = await load(b, ids[1])
            with pytest.raises(svc.SettlementDomainError) as exhausted: await spend(b, cb, 'spend-b')
            assert exhausted.value.code == 'insufficient_credit'
            await b.rollback()
            ca = await load(a, ids[0])
            assert (await spend(a, ca, 'spend-a'))[0].id == first_id
            await a.rollback()
        async with sessions() as check:
            applied = await check.scalar(select(func.sum(CustomerCreditEntry.amount)).where(CustomerCreditEntry.source_entry_id == cid, CustomerCreditEntry.entry_type == 'applied'))
            assert applied == Decimal('10')
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_void_loses_to_confirmation_and_cannot_void_paid_invoice(monkeypatch):
    from fastapi import HTTPException
    from app.api.v1.endpoints.invoices import void_invoice, InvoiceVoidRequest
    engine, sessions = database()
    try:
        async with sessions() as seed:
            ctx = await context(seed, monkeypatch)
            made = await make(seed, ctx)
            ids, aid = (ctx[0].id, ctx[1].id, ctx[3].id), made.attempt.id
            await seed.commit()
        async with sessions() as a, sessions() as b:
            ca, cb = await load(a, ids), await load(b, ids)
            await confirm(a, ca, aid)
            await busy(void_invoice(ids[2], InvoiceVoidRequest(reason='Revise invoice'), b, cb[1]))
            await b.rollback()
            await a.commit()
            cb = await load(b, ids)
            with pytest.raises(HTTPException) as error:
                await void_invoice(ids[2], InvoiceVoidRequest(reason='Revise invoice'), b, cb[1])
            assert error.value.status_code == 409 and 'Paid' in error.value.detail
            assert cb[3].voided_at is None
            await b.rollback()
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_outbox_defers_busy_financial_transaction_without_spending_retry(monkeypatch):
    from app.db.models.provider_outbox import ProviderOutboxEvent
    from app.services import db048_accounting_reconciliation as worker
    engine, sessions = database()
    try:
        async with sessions() as seed:
            ctx = await context(seed, monkeypatch)
            event = ProviderOutboxEvent(tenant_id=ctx[0].id, event_type=worker.PAYMENT_ACCOUNTING_EVENT,
                aggregate_type='invoice', aggregate_id=ctx[3].id, idempotency_key=str(uuid4()),
                status='pending', attempt_count=2, available_at=datetime(1900, 1, 1, tzinfo=timezone.utc))
            seed.add(event)
            await seed.flush()
            ids, eid = (ctx[0].id, ctx[1].id, ctx[3].id), event.id
            await seed.commit()
        async def no_provider(*args, **kwargs):
            raise AssertionError('Contended worker must not reach provider preparation')
        monkeypatch.setattr(worker, 'load_accounting_envelope', no_provider)
        async with sessions() as a:
            ca = await load(a, ids)
            await make(a, ca)
            result = await asyncio.wait_for(worker.process_due_db048_outbox_events(session_factory=sessions, batch_size=1), 3)
            assert result['claimed'] == 1 and result['retried'] == 1 and result['dead'] == 0
            async with sessions() as check:
                event = await check.get(ProviderOutboxEvent, eid)
                assert event.status == 'pending' and event.attempt_count == 2
                assert event.lock_token is None and event.locked_until is None
            await a.rollback()
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_wrong_tenant_confirmation_does_not_mutate_attempt(monkeypatch):
    engine, sessions = database()
    try:
        async with sessions() as seed:
            ctx = await context(seed, monkeypatch)
            other = await context(seed, monkeypatch)
            made = await make(seed, ctx)
            aid = made.attempt.id
            foreign_ids = other[0].id, other[1].id, other[3].id
            await seed.commit()
        async with sessions() as db:
            foreign = await load(db, foreign_ids)
            with pytest.raises(svc.SettlementDomainError) as error:
                await confirm(db, foreign, aid)
            assert error.value.status_code == 404
            await db.rollback()
        async with sessions() as check:
            assert (await check.get(InvoicePaymentAttempt, aid)).state == 'pending'
    finally:
        await engine.dispose()
