from datetime import datetime,timedelta,timezone
from uuid import uuid4
import pytest
from app.services.booking_financial_reporting import booking_prepayments_for_period
from tests.test_booking_application_accounting import context
from app.db.models.payment import Payment
from sqlalchemy import select,func

@pytest.mark.asyncio
async def test_receipt_liability_and_application_are_separate_no_new_cash(db_session):
    t,r,apt,owner,inv,application=await context(db_session)
    now=datetime.now(timezone.utc)
    block=await booking_prepayments_for_period(db_session,t.id,now-timedelta(days=1),now+timedelta(days=1))
    assert block.period_received_gross=='100.00' and block.period_receipt_count==1
    assert block.period_applied_to_invoices=='40.00' and block.period_application_count==1
    assert block.current_unapplied_liability=='60.00'
    assert block.classification=='prepaid_liability'
    assert await db_session.scalar(select(func.count()).select_from(Payment))==0

@pytest.mark.asyncio
async def test_application_period_is_separate_from_receipt_period(db_session):
    now=datetime.now(timezone.utc)
    t,r,*_=await context(db_session,application_created_at=now+timedelta(days=2))
    first=await booking_prepayments_for_period(db_session,t.id,now-timedelta(days=1),now+timedelta(days=1))
    later=await booking_prepayments_for_period(db_session,t.id,now+timedelta(days=1),now+timedelta(days=3))
    assert first.period_received_gross=='100.00' and first.period_applied_to_invoices=='0.00'
    assert later.period_received_gross=='0.00' and later.period_applied_to_invoices=='40.00'
    assert later.current_unapplied_liability=='60.00'  # current, not an as-of historical reconstruction

@pytest.mark.asyncio
async def test_current_refunds_are_receipt_cohort_not_refund_period(db_session):
    t,r,*_=await context(db_session)
    r.refunded_amount_minor=2000;r.version+=1;await db_session.flush()
    now=datetime.now(timezone.utc)
    report=await booking_prepayments_for_period(db_session,t.id,now-timedelta(days=1),now+timedelta(days=1))
    outside=await booking_prepayments_for_period(db_session,t.id,now+timedelta(days=1),now+timedelta(days=2))
    assert report.period_received_gross=='100.00' and report.period_received_refunded_to_date=='20.00'
    assert report.current_unapplied_liability=='40.00'
    assert outside.period_received_refunded_to_date=='0.00' and outside.current_unapplied_liability=='40.00'

@pytest.mark.asyncio
async def test_overapplied_actual_refund_requires_review_not_false_zero(db_session):
    t,r,*_=await context(db_session)
    r.refunded_amount_minor=8000;r.version+=1;await db_session.flush()
    now=datetime.now(timezone.utc)
    report=await booking_prepayments_for_period(db_session,t.id,now-timedelta(days=1),now+timedelta(days=1))
    assert report.period_received_gross=='100.00' and report.period_received_refunded_to_date=='80.00'
    assert report.current_unapplied_liability is None and report.reconciliation_required_count==1

@pytest.mark.asyncio
async def test_tenant_isolation_and_empty_results(db_session):
    await context(db_session)
    now=datetime.now(timezone.utc)
    report=await booking_prepayments_for_period(db_session,uuid4(),now-timedelta(days=1),now+timedelta(days=1))
    assert report.period_received_gross=='0.00' and report.period_applied_to_invoices=='0.00'
    assert report.current_unapplied_liability=='0.00' and report.period_receipt_count==0

@pytest.mark.asyncio
async def test_half_open_receipt_boundaries(db_session):
    t,r,*_=await context(db_session)
    received=r.received_at.replace(tzinfo=r.received_at.tzinfo or timezone.utc)
    included=await booking_prepayments_for_period(db_session,t.id,received,received+timedelta(days=1))
    excluded=await booking_prepayments_for_period(db_session,t.id,received-timedelta(days=1),received)
    assert included.period_receipt_count==1 and excluded.period_receipt_count==0

@pytest.mark.asyncio
async def test_reports_dashboard_discloses_deposit_without_inflating_revenue(db_session):
    from app.api.v1.endpoints.reports import get_reports_dashboard
    t,r,apt,owner,invoice,application=await context(db_session)
    today=datetime.now(timezone.utc).date()
    report=await get_reports_dashboard(range='custom',from_date=today-timedelta(days=1),
        to_date=today+timedelta(days=1),db=db_session,current_user=owner)
    assert report.revenue.value=='0.00'
    assert report.booking_prepayments.period_received_gross=='100.00'
    assert report.booking_prepayments.period_applied_to_invoices=='40.00'

@pytest.mark.asyncio
async def test_unverified_provenance_does_not_become_zero_or_verified_money(db_session):
    t,r,*_=await context(db_session)
    r.proof_sha256='';await db_session.flush()
    now=datetime.now(timezone.utc)
    report=await booking_prepayments_for_period(db_session,t.id,now-timedelta(days=1),now+timedelta(days=1))
    assert report.period_received_gross=='0.00' and report.period_unverified_receipt_gross=='100.00'
    assert report.current_unapplied_liability is None and report.unverified_receipt_count==1


@pytest.mark.asyncio
@pytest.mark.parametrize('charge_binding',['missing_receipt','missing_attempt','mismatch'])
async def test_wrong_charge_is_disclosed_unverified_not_verified_cash(db_session,charge_binding):
    # Malformed evidence is inserted only in this disposable fixture; reporting
    # must retain the unverified gross disclosure without trusting its binding.
    from tests.test_booking_invoice_guard import seed
    t,ro=await seed(db_session,'succeeded',0,charge_binding=charge_binding)
    now=datetime.now(timezone.utc)
    report=await booking_prepayments_for_period(db_session,t.id,now-timedelta(days=1),now+timedelta(days=1))
    assert report.period_received_gross=='0.00' and report.period_unverified_receipt_gross=='100.00'
    assert report.current_unapplied_liability is None
    assert report.unverified_receipt_count==1 and report.reconciliation_required_count==1
