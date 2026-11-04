"""Disposable-schema 199 lifecycle/tenant audit and real competing intake writes."""
import asyncio
import importlib.util
from pathlib import Path
from uuid import uuid4
import pytest
import pytest_asyncio
from sqlalchemy import select,text,func
from sqlalchemy.exc import DBAPIError
from alembic.migration import MigrationContext
from alembic.operations import Operations
from fastapi import HTTPException
from app.db.models.visit_request import VisitRequest
from app.db.models.booking_fulfillment import VisitRequestEvent,BookingRepairOrderLink
from app.db.models.user import User,UserRole
from app.db.models.tenant import Tenant
from app.db.models.user_customer_link import UserCustomerLink
from app.db.models.appointment import Appointment
from app.db.models.invoice import Invoice
from app.db.models.repair_order import RepairOrder
from app.services import booking_fulfillment as fulfillment,booking_payments as booking
from app.api.v1.endpoints.visit_requests import VisitReviewBody,VisitAcceptBody,VisitWithdrawBody,VisitFulfillBody
from app.api.v1.endpoints.appointments import BookingRepairOrderLinkBody
from test_verified_booking_postgres import pg_booking
from test_booking_fulfillment import request,paid,vehicle_order

@pytest_asyncio.fixture
async def pg_fulfillment(pg_booking):
    factory,setup,engine=pg_booking
    async with engine.begin() as db:
        for name in ['visit_request_events','booking_repair_order_links']:await db.execute(text(f'DROP TABLE {name} CASCADE'))
        for name in ['version','accepted_arrival_date','reviewed_by_user_id','reviewed_at','internal_review_note','fulfilled_repair_order_id']:await db.execute(text(f'ALTER TABLE visit_requests DROP COLUMN {name} CASCADE'))
        await db.execute(text('ALTER TABLE visit_requests DROP CONSTRAINT uq_visit_request_tenant_id'))
        await db.execute(text('ALTER TABLE visit_requests DROP CONSTRAINT ck_visit_request_status'))
        await db.execute(text("ALTER TABLE visit_requests ADD CONSTRAINT ck_visit_request_status CHECK(status IN ('requested','availability_review','withdrawn'))"))
        def upgrade(sync):
            spec=importlib.util.spec_from_file_location('migration199',Path(__file__).parents[1]/'alembic/versions/199_booking_fulfillment.py')
            module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
            with Operations.context(MigrationContext.configure(sync)):module.upgrade()
        await db.run_sync(upgrade)
    async with factory() as db:
        actor=User(id=uuid4(),tenant_id=setup[0].id,role=UserRole.GARAGE_OWNER,first_name='Synthetic',last_name='Reviewer',email=f'{uuid4()}@example.test',is_active=True)
        db.add(actor);await db.commit()
    return factory,setup,actor

@pytest.mark.asyncio
async def test_actual_199_date_acceptance_audit_and_selected_shop_customer_withdraw(pg_fulfillment):
    factory,setup,staff=pg_fulfillment
    async with factory() as db:
        row=await request(db,setup);identity=row.id
        response=await fulfillment.request_action(db,staff,identity,'accept',VisitAcceptBody(expected_version=1,arrival_date=booking.now().date()),'pg-date-accept-key')
        assert response['request']['status']=='accepted'
        # Same global customer identity has a different home tenant but a valid
        # selected-shop link: durable audit must accept that actual grant.
        user=await db.get(User,setup[3].id)
        home=Tenant(name='Synthetic other home',slug=f'home-{uuid4()}');db.add(home);await db.flush()
        user.tenant_id=home.id
        db.add(UserCustomerLink(user_id=user.id,tenant_id=setup[0].id,customer_id=setup[1].id));await db.commit()
        response=await fulfillment.request_action(db,setup[3],identity,'withdraw',VisitWithdrawBody(expected_version=2),'pg-shared-user-withdraw')
        assert response['request']['status']=='withdrawn' and 'internal_review_note' not in response['request']
        assert await db.scalar(select(func.count(VisitRequestEvent.id)))==2
        assert await db.scalar(select(func.count(Appointment.id)))==0
        with pytest.raises(DBAPIError):await db.execute(text("UPDATE visit_request_events SET after_status='accepted' WHERE request_id=:id"),{'id':identity})
        await db.rollback()

@pytest.mark.asyncio
async def test_199_rejects_direct_unaudited_status_or_foreign_actor(pg_fulfillment):
    factory,setup,staff=pg_fulfillment
    async with factory() as db:
        row=await request(db,setup);identity=row.id
        with pytest.raises(DBAPIError):await db.execute(text("UPDATE visit_requests SET status='availability_review',version=2 WHERE id=:id"),{'id':identity})
        await db.rollback()
        foreign=Tenant(name='Foreign synthetic shop',slug=f'foreign-{uuid4()}');db.add(foreign);await db.flush()
        staff_row=await db.get(User,staff.id);staff_row.tenant_id=foreign.id;await db.commit()
        with pytest.raises(DBAPIError):await fulfillment.request_action(db,staff,identity,'review',VisitReviewBody(expected_version=1),'pg-foreign-real-actor')
        await db.rollback()
        assert (await db.get(VisitRequest,identity)).version==1
        assert await db.scalar(select(func.count(VisitRequestEvent.id)))==0

@pytest.mark.asyncio
@pytest.mark.parametrize('same_key',[True,False])
async def test_competing_review_actions_append_once(pg_fulfillment,same_key):
    factory,setup,staff=pg_fulfillment
    async with factory() as db:row=await request(db,setup);identity=row.id
    async def one(key):
        async with factory() as db:
            try:return await fulfillment.request_action(db,staff,identity,'review',VisitReviewBody(expected_version=1),key)
            except HTTPException as exc:await db.rollback();return exc
    outcomes=await asyncio.gather(one('pg-review-first'),one('pg-review-first' if same_key else 'pg-review-second'))
    async with factory() as db:
        assert (await db.get(VisitRequest,identity)).version==2
        assert await db.scalar(select(func.count(VisitRequestEvent.id)))==1
    assert any(isinstance(item,dict) for item in outcomes)
    if same_key:assert all(isinstance(item,dict) for item in outcomes)

@pytest.mark.asyncio
async def test_accepted_intake_records_exact_vehicle_and_immutable_ro_identity(pg_fulfillment):
    factory,setup,staff=pg_fulfillment
    async with factory() as db:
        row=await request(db,setup)
        await fulfillment.request_action(db,staff,row.id,'accept',VisitAcceptBody(expected_version=1,arrival_date=booking.now().date()),'pg-accept-intake')
        vehicle,order=await vehicle_order(db,setup)
        response=await fulfillment.request_action(db,staff,row.id,'fulfill',VisitFulfillBody(expected_version=2,repair_order_id=order.id,expected_vehicle_id=vehicle.id,reason='Exact arrival and vehicle reviewed'),'pg-fulfilled-intake')
        assert response['request']['fulfilled_repair_order_id']==str(order.id)
        assert row.vehicle_id is None and order.status.value=='draft'
        with pytest.raises(DBAPIError):await db.execute(text('UPDATE repair_orders SET vehicle_id=:vehicle WHERE id=:order'),{'vehicle':uuid4(),'order':order.id})
        await db.rollback()

@pytest.mark.asyncio
async def test_paid_link_and_ordinary_issuance_race_never_bypass_unapplied_receipt(pg_fulfillment,monkeypatch):
    factory,setup,staff=pg_fulfillment
    async with factory() as db:
        apt=await paid(db,setup,monkeypatch);apt_id=apt.id;version=apt.booking_version
        vehicle,order=await vehicle_order(db,setup);order_id=order.id;vehicle_id=vehicle.id
    from app.services.booking_invoice_guard import require_booking_prepayment_resolved
    from app.services.financial_transaction_lock import lock_tenant_financials
    from app.services.invoice_settlement_service import SettlementDomainError
    async def link():
        async with factory() as db:
            try:return await fulfillment.link_appointment(db,staff,apt_id,BookingRepairOrderLinkBody(expected_booking_version=version,repair_order_id=order_id,expected_vehicle_id=vehicle_id,reason='Verified intake identity'),'pg-link-issue-race')
            except (HTTPException,SettlementDomainError) as exc:await db.rollback();return exc
    async def issue():
        async with factory() as db:
            try:
                await lock_tenant_financials(db,staff.tenant_id)
                await require_booking_prepayment_resolved(db,staff.tenant_id,order_id)
                invoice=Invoice(tenant_id=staff.tenant_id,repair_order_id=order_id,billed_customer_id=setup[1].id,invoice_number=f'PG-{uuid4()}',status='sent',subtotal=120,total_amount=120,accounting_policy='standard')
                db.add(invoice);await db.commit();return invoice.id
            except (HTTPException,SettlementDomainError) as exc:await db.rollback();return exc
    await asyncio.gather(link(),issue())
    async with factory() as db:
        apt=await db.get(Appointment,apt_id)
        invoice_count=await db.scalar(select(func.count(Invoice.id)))
        if apt.repair_order_id is not None:assert invoice_count==0
        else:assert invoice_count in (0,1)
        assert not (apt.repair_order_id is not None and invoice_count)
