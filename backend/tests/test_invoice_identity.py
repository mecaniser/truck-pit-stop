from types import SimpleNamespace as Obj
from uuid import uuid4
from unittest.mock import AsyncMock
import pytest
from app.services.invoice_identity import collection_display_number, load_invoice_display_number, pdf_filename_for_number

@pytest.mark.parametrize('prefix,name,number,expected', [
    ('TPS','Truck Pit Stop','1687','TPS-1687'),
    ('DEL','Another Shop','1687','DEL-1687'),
    (None,'Truck Pit Stop','001687','TPS-001687'),
    ('','', '1687','RO-1687'),
    ('bad"\r\nprefix','Truck Pit Stop','1687','TPS-1687'),
    ('TPS','Truck Pit Stop','<script>',None),
    ('TPS','Truck Pit Stop','1687\r\nBad',None),
])
def test_tenant_customer_number(prefix,name,number,expected):
    assert collection_display_number(Obj(order_number_prefix=prefix,name=name),number)==expected

@pytest.mark.asyncio
async def test_display_identity_is_tenant_bound_and_does_not_change_canonical_keys():
    tenant=Obj(id=uuid4(),name='Truck Pit Stop',order_number_prefix='TPS')
    invoice=Obj(id=uuid4(),tenant_id=tenant.id,source='ets_collection_handoff',source_debt_handoff_id=uuid4(),invoice_number='DBN-COL-INTERNAL')
    db=Obj(scalar=AsyncMock(return_value=Obj(source_invoice_number='1687')))
    assert await load_invoice_display_number(db,invoice,tenant)=='TPS-1687'
    assert invoice.invoice_number=='DBN-COL-INTERNAL'
    query=str(db.scalar.call_args.args[0])
    assert 'tenant_id' in query and 'native_invoice_id' in query
    db.scalar.reset_mock()
    assert await load_invoice_display_number(db,invoice,Obj(id=uuid4()))==''
    db.scalar.assert_not_called()
    invoice.source='native'
    assert await load_invoice_display_number(db,invoice,tenant)=='DBN-COL-INTERNAL'
    db.scalar.assert_not_called()

@pytest.mark.parametrize('number,paid,expected', [('TPS-1687',False,'Invoice-TPS-1687.pdf'),('TPS-1687',True,'Invoice-TPS-1687-PAID.pdf'),('',False,'Invoice.pdf'),('INV-42',False,'Invoice-INV-42.pdf')])
def test_customer_pdf_filename(number,paid,expected):
    assert pdf_filename_for_number(number,paid=paid)==expected


@pytest.mark.asyncio
async def test_real_collection_alias_preserves_original_record(db_session, monkeypatch):
    from datetime import datetime, timedelta, timezone
    from test_db149_source_collection import context
    from app.services import source_debt_handoff as svc
    from app.schemas.source_debt_handoff import SourceVersionRequest
    from app.db.models.invoice import Invoice
    t, actor, customer, original, proof, body = await context(db_session, monkeypatch)
    t.order_number_prefix='TPS'
    original.source='easy_truck_shop_import'
    row=await svc.prepare(db_session,t.id,actor,body,'prepare-identity')
    proof['summary'].observed_at=datetime.now(timezone.utc)+timedelta(seconds=1)
    row,_=await svc.activate(db_session,row,actor,SourceVersionRequest(expected_version=1,expected_source_capture_sha256='a'*64,expected_source_revision='b'*64),'activate-identity')
    native=await db_session.get(Invoice,row.native_invoice_id)
    canonical=native.invoice_number
    summary=await svc.source_collection_for_invoice(db_session,native,viewer_customer_id=customer.id)
    assert summary['display_invoice_number']=='TPS-1687'
    assert summary['customer_display_company'] is None
    assert await load_invoice_display_number(db_session,native,t)=='TPS-1687'
    assert await load_invoice_display_number(db_session,original,t)=='TPS-1687'
    assert native.invoice_number==canonical and canonical.startswith('DBN-COL-')
    assert str(native.total_amount)=='600.00' or native.total_amount==600
    from app.services.source_debt_handoff import collection_email_html
    from app.services.invoice_payment_presentation import InvoicePaymentSummary
    html=collection_email_html(native,summary,InvoicePaymentSummary(state='unpaid',balance_due='600.00'),'https://example.test/invoice',t)
    assert 'TPS-1687' in html and canonical not in html and 'DBN' not in html


@pytest.mark.asyncio
async def test_tampered_review_cannot_supply_customer_display_name(db_session, monkeypatch):
    from datetime import datetime, timedelta, timezone
    from test_db149_source_collection import context
    from app.services import source_debt_handoff as svc
    from app.schemas.source_debt_handoff import SourceVersionRequest
    from app.db.models.invoice import Invoice
    from app.services.invoice_settlement_service import SettlementDomainError
    t, actor, customer, original, proof, body=await context(db_session,monkeypatch)
    row=await svc.prepare(db_session,t.id,actor,body,'prepare-tampered-name')
    proof['summary'].observed_at=datetime.now(timezone.utc)+timedelta(seconds=1)
    row,_=await svc.activate(db_session,row,actor,SourceVersionRequest(expected_version=1,expected_source_capture_sha256='a'*64,expected_source_revision='b'*64),'activate-tampered-name')
    native=await db_session.get(Invoice,row.native_invoice_id)
    row.bill_to_authorization={**row.bill_to_authorization,'original_bill_to_name':'Forged customer'}
    with pytest.raises(SettlementDomainError):
        await svc.source_collection_for_invoice(db_session,native,viewer_customer_id=customer.id)


@pytest.mark.asyncio
async def test_unlinked_import_preserves_established_invoice_number():
    tenant=Obj(id=uuid4(),name='Truck Pit Stop',order_number_prefix='TPS')
    invoice=Obj(id=uuid4(),tenant_id=tenant.id,source='easy_truck_shop_import',invoice_number='ETSINV-42')
    db=Obj(scalar=AsyncMock(return_value=None))
    assert await load_invoice_display_number(db,invoice,tenant)=='ETSINV-42'
    query=str(db.scalar.call_args.args[0])
    assert 'source_dbn_invoice_id' in query and 'tenant_id' in query
