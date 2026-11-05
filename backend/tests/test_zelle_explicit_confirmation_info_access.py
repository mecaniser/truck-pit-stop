"""Read-only Zelle destination access over real fictional ownership/handoff rows."""
from datetime import datetime,timezone
from uuid import uuid4
from unittest.mock import AsyncMock
import hashlib,json
import httpx,pytest
from fastapi import FastAPI
from sqlalchemy import select
from app.api.v1.endpoints import payments
from app.core.dependencies import get_db,get_current_active_user
from app.db.models.user import User,UserRole
from app.db.models.tenant import Tenant
from app.db.models.customer import Customer
from app.db.models.invoice import Invoice
from app.db.models.invoice_settlement import InvoiceSettlement,InvoicePaymentAttempt,InvoicePaymentLedgerEvent
from app.db.models.payment import Payment
from app.db.models.source_debt_handoff import SourceDebtHandoff,SourceDebtEvent
from test_zelle_explicit_confirmation import fictional_zelle_context

async def fingerprint(db):
    state={}
    for model in (Tenant,Invoice,InvoiceSettlement,InvoicePaymentAttempt,InvoicePaymentLedgerEvent,Payment,SourceDebtHandoff,SourceDebtEvent):
        rows=(await db.execute(select(model.__table__))).mappings().all()
        state[model.__tablename__]=sorted([dict(r) for r in rows],key=lambda r:str(r.get('id')))
    return hashlib.sha256(json.dumps(state,sort_keys=True,default=str).encode()).hexdigest()

async def read(db,actor,invoice_id,monkeypatch):
    before=await fingerprint(db)
    from app.services import invoice_settlement_service as domain,quickbooks_payments_service as qbp
    forbidden=AsyncMock(side_effect=AssertionError('Read-only Zelle instructions must not initialize/write/send'))
    with monkeypatch.context() as scoped:
        for name in ('commit','flush'):scoped.setattr(db,name,forbidden)
        scoped.setattr(domain,'get_or_create_settlement',forbidden)
        scoped.setattr(payments,'send_pending_zelle_submission_alert',forbidden)
        scoped.setattr(qbp,'create_charge',forbidden);scoped.setattr(qbp,'get_charge',forbidden)
        scoped.setattr(payments.stripe.PaymentIntent,'create',forbidden)
        app=FastAPI();app.include_router(payments.router,prefix='/api/v1/payments')
        async def database():yield db
        app.dependency_overrides[get_db]=database
        app.dependency_overrides[get_current_active_user]=lambda:actor
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://testserver') as client:
            response=await client.get(f'/api/v1/payments/zelle-info/{invoice_id}')
        forbidden.assert_not_called()
    assert await fingerprint(db)==before
    assert not db.new and not db.dirty and not db.deleted
    return response

@pytest.mark.asyncio
@pytest.mark.parametrize('collection',[False,True])
async def test_ordinary_and_reviewed_payer_can_read_without_writes(db_session,monkeypatch,collection):
    ctx=await fictional_zelle_context(db_session,monkeypatch,collection=collection)
    ctx.tenant.zelle_qr_image='fictional-zelle-qr';await db_session.commit()
    if collection:
        assert ctx.original_customer.id!=ctx.customer.id
        assert ctx.invoice.repair_order.customer_id==ctx.original_customer.id
        assert ctx.original.repair_order.deleted_at is not None
    response=await read(db_session,ctx.customer_user,ctx.invoice.id,monkeypatch)
    assert response.status_code==200,response.text
    assert response.json()=={'zelle_email':'fictional-zelle@example.test','zelle_phone':'+15005550000','zelle_qr_image':'fictional-zelle-qr','garage_name':ctx.tenant.name,'stripe_payments_available':bool(ctx.tenant.stripe_account_id and ctx.tenant.stripe_onboarding_complete)}

async def principal(db,ctx,*,customer_id=None,role=UserRole.CUSTOMER,foreign_tenant=False):
    tenant=ctx.tenant
    if foreign_tenant:
        tenant=Tenant(name='Other fictional shop',slug=str(uuid4()));db.add(tenant);await db.flush()
    user=User(tenant_id=tenant.id,customer_id=customer_id,first_name='Fictional',last_name='Principal',email=f'{uuid4()}@example.test',role=role,is_active=True)
    db.add(user);await db.commit();return user

@pytest.mark.asyncio
@pytest.mark.parametrize('kind',['original_service_customer','other_customer','foreign_tenant','foreign_staff'])
async def test_nonpayer_or_foreign_principal_cannot_read_destinations(db_session,monkeypatch,kind):
    ctx=await fictional_zelle_context(db_session,monkeypatch,collection=True)
    if kind=='original_service_customer':who=await principal(db_session,ctx,customer_id=ctx.original_customer.id)
    elif kind=='other_customer':
        c=Customer(tenant_id=ctx.tenant.id,first_name='Other',last_name='Customer',email=f'{uuid4()}@example.test');db_session.add(c);await db_session.flush()
        who=await principal(db_session,ctx,customer_id=c.id)
    elif kind=='foreign_tenant':
        # Even a mismatched principal presenting the exact payer UUID may not
        # cross the independently enforced selected-tenant boundary.
        from types import SimpleNamespace
        other=Tenant(name='Foreign fictional tenant',slug=str(uuid4()));db_session.add(other);await db_session.commit()
        who=SimpleNamespace(role=UserRole.CUSTOMER,tenant_id=other.id,customer_id=ctx.customer.id)
    else:who=await principal(db_session,ctx,role=UserRole.GARAGE_OWNER,foreign_tenant=True)
    response=await read(db_session,who,ctx.invoice.id,monkeypatch)
    assert response.status_code==404,response.text
    assert ctx.tenant.zelle_email not in response.text and ctx.tenant.zelle_phone not in response.text

@pytest.mark.asyncio
@pytest.mark.parametrize('corruption',['missing','closed','source_conflict','forged_hash','wrong_native_invoice','foreign_order_tenant'])
async def test_missing_inactive_or_forged_handoff_cannot_expose_destinations(db_session,monkeypatch,corruption):
    ctx=await fictional_zelle_context(db_session,monkeypatch,collection=True)
    if corruption=='missing':ctx.handoff.deleted_at=datetime.now(timezone.utc)
    elif corruption in {'closed','source_conflict'}:ctx.handoff.state=corruption
    elif corruption=='forged_hash':ctx.handoff.bill_to_authorization_sha256='0'*64
    elif corruption=='wrong_native_invoice':ctx.handoff.native_invoice_id=ctx.original.id
    else:
        other=Tenant(name='Unrelated fictional tenant',slug=str(uuid4()));db_session.add(other);await db_session.flush()
        ctx.original.repair_order.tenant_id=other.id
    await db_session.commit()
    response=await read(db_session,ctx.customer_user,ctx.invoice.id,monkeypatch)
    assert response.status_code==404,response.text
    assert ctx.tenant.zelle_email not in response.text

@pytest.mark.asyncio
@pytest.mark.parametrize('role',[UserRole.GARAGE_OWNER,UserRole.GARAGE_ADMIN,UserRole.RECEPTIONIST,UserRole.MECHANIC])
@pytest.mark.parametrize('collection',[False,True])
async def test_existing_same_tenant_staff_read_contract_preserved(db_session,monkeypatch,role,collection):
    ctx=await fictional_zelle_context(db_session,monkeypatch,collection=collection)
    who=await principal(db_session,ctx,role=role)
    response=await read(db_session,who,ctx.invoice.id,monkeypatch)
    assert response.status_code==200 and response.json()['zelle_email']==ctx.tenant.zelle_email

@pytest.mark.asyncio
async def test_missing_destinations_keep_nullable_dto_and_missing_invoice_is_denied(db_session,monkeypatch):
    ctx=await fictional_zelle_context(db_session,monkeypatch)
    ctx.tenant.zelle_email=None;ctx.tenant.zelle_phone=None;ctx.tenant.zelle_qr_image=None
    await db_session.commit()
    response=await read(db_session,ctx.customer_user,ctx.invoice.id,monkeypatch)
    assert response.status_code==200
    assert all(response.json()[field] is None for field in ['zelle_email','zelle_phone','zelle_qr_image'])
    missing=await read(db_session,ctx.customer_user,uuid4(),monkeypatch)
    assert missing.status_code==404
