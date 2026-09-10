"""Independent gross-credit gate; provider requests are entirely mocked."""
from copy import deepcopy
from decimal import Decimal as D
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from app.services import db048_gross_credit_accounting as c
from app.services import db048_qbo_gross_accounting as g
from app.services import db048_accounting_reconciliation as r


def fixture(monkeypatch, allocations=None):
    tenant, customer, invoice, attempt_id = [uuid4() for _ in range(4)]
    attempt = NS(id=attempt_id,tenant_id=tenant,customer_id=customer,invoice_id=invoice,
        provider='quickbooks_payments',provider_charge_id='MT123',rail='card',state='confirmed',
        applied_principal_amount=D('100'),applied_card_fee_amount=D('3'),
        applied_card_fee_tax_amount=D('.15'),provider_charge_amount=D('113.15'))
    settlement = NS(id=uuid4(),qbo_realm_snapshot='realm',accounting_composition_version='gross_invoice_v1',
        accounting_projection_snapshot={})
    attempt.settlement_id=settlement.id
    source=NS(id=invoice,quickbooks_invoice_id='source',invoice_number='TPS-001')
    customer_row=NS(id=customer,quickbooks_customer_id='customer')
    env=NS(tenant=NS(id=tenant,name='Shop'),source_attempt=attempt,
        connection=NS(realm_id='realm'),config=NS(writer_strategy='dieselbridge'),
        source_payment=NS(quickbooks_payment_id='receipt',payment_number='PAY-1'),
        source_accounting_link=NS(provider_deposit_id='receipt',owning_writer='dieselbridge',
            qbo_realm_snapshot='realm',account_mapping_snapshot={'qbp_clearing_account':'clearing'}))
    async def scalar(query):
        name=query.column_descriptions[0]['entity'].__name__
        return {'InvoiceSettlement':settlement,'Invoice':source,'Customer':customer_row}.get(name)
    db=NS(scalar=AsyncMock(side_effect=scalar),flush=AsyncMock(),
        execute=AsyncMock(return_value=NS(scalars=lambda:NS(all=lambda:[]))))
    state={'payment':{'Id':'receipt','SyncToken':'0','CustomerRef':{'value':'customer'},
        'PaymentRefNum':'QBP MT123','PrivateNote':f'attempt={attempt_id}','TxnDate':'2026-09-01',
        'DepositToAccountRef':{'value':'clearing'},'CurrencyRef':{'value':'USD'},
        'TotalAmt':113.15,'UnappliedAmt':10,
        'Line':[{'Amount':103.15,'LinkedTxn':[{'TxnType':'Invoice','TxnId':'source'}]}]},
        'posts':[],'stale':0,'bad_readback':False,'close_date':None}
    async def request(connection,method,path,**kwargs):
        if method=='GET' and path=='preferences':
            return {'Preferences':{'AccountingInfoPrefs':{'BookCloseDate':state['close_date']}}}
        if method=='POST':
            state['posts'].append(deepcopy(kwargs))
            if state['stale']:
                state['stale']-=1
                raise r.QuickBooksAccountingError('5010 stale object',status_code=400)
            if not state['bad_readback']:
                state['payment'].update(deepcopy(kwargs['json']))
                state['payment']['UnappliedAmt']=float(D(str(state['payment']['TotalAmt']))-sum((D(str(x['Amount'])) for x in state['payment']['Line']),D(0)))
        return {'Payment':deepcopy(state['payment'])}
    monkeypatch.setattr(r,'_request',request)
    monkeypatch.setattr(r,'_resolve_qbo_account_reference',AsyncMock(side_effect=lambda connection,value:value))
    monkeypatch.setattr(c,'gross_credit_allocations',AsyncMock(side_effect=lambda *args,**kwargs:deepcopy(allocations or {'target-a':D('4'),'target-b':D('6')})))
    monkeypatch.setattr(g,'_attempt_changes',AsyncMock(return_value=[]))
    return db,env,settlement,state


@pytest.mark.asyncio
async def test_credit_preserves_fee_tax_and_multiple_allocations_idempotently(monkeypatch):
    db,env,settlement,state=fixture(monkeypatch)
    assert await c.sync_gross_credit_application(db,env,settlement)=='receipt'
    assert state['payment']['TotalAmt']==113.15
    assert state['payment']['UnappliedAmt']==0
    assert {x['LinkedTxn'][0]['TxnId']:x['Amount'] for x in state['payment']['Line']}=={'source':103.15,'target-a':4,'target-b':6}
    await c.sync_gross_credit_application(db,env,settlement)
    assert len(state['posts'])==1
    assert 'ProcessPayment' not in state['posts'][0]['json']


@pytest.mark.asyncio
async def test_fee_is_not_available_credit(monkeypatch):
    db,env,settlement,state=fixture(monkeypatch,{'target':D('10.01')})
    with pytest.raises(r.DB048ReconciliationError,match='actual excess'):
        await c.sync_gross_credit_application(db,env,settlement)
    assert not state['posts']


@pytest.mark.asyncio
@pytest.mark.parametrize('refund_state',['succeeded','pending','manual_action_required','failed'])
async def test_refund_reserved_excess_cannot_be_allocated(monkeypatch,refund_state):
    db,env,settlement,state=fixture(monkeypatch)
    db.execute=AsyncMock(return_value=NS(scalars=lambda:NS(all=lambda:[NS(amount=D('1'),state=refund_state)])))
    with pytest.raises(r.DB048ReconciliationError,match='actual excess'):
        await c.sync_gross_credit_application(db,env,settlement)
    assert not state['posts']


@pytest.mark.asyncio
async def test_refund_reservation_and_remaining_credit_can_coexist(monkeypatch):
    db,env,settlement,state=fixture(monkeypatch,{'target':D('9')})
    db.execute=AsyncMock(return_value=NS(scalars=lambda:NS(all=lambda:[NS(amount=D('1'),state='succeeded')])))
    await c.sync_gross_credit_application(db,env,settlement)
    assert state['payment']['UnappliedAmt']==1


@pytest.mark.asyncio
@pytest.mark.parametrize('change',['customer','currency','exchange','reference','note','deposit','total','line','unapplied'])
async def test_external_receipt_changes_are_not_overwritten(monkeypatch,change):
    db,env,settlement,state=fixture(monkeypatch)
    p=state['payment']
    if change=='customer':p['CustomerRef']['value']='other'
    if change=='currency':p['CurrencyRef']['value']='EUR'
    if change=='exchange':p['ExchangeRate']='1.001'
    if change=='reference':p['PaymentRefNum']='other'
    if change=='note':p['PrivateNote']='unrelated'
    if change=='deposit':p['DepositToAccountRef']['value']='other'
    if change=='total':p['TotalAmt']=120
    if change=='line':p['Line'][0]['Amount']=99
    if change=='unapplied':p['UnappliedAmt']=11
    with pytest.raises(r.DB048ReconciliationError):
        await c.sync_gross_credit_application(db,env,settlement)
    assert not state['posts']


@pytest.mark.asyncio
@pytest.mark.parametrize('change',['realm','writer','receipt'])
async def test_source_identity_fences(monkeypatch,change):
    db,env,settlement,state=fixture(monkeypatch)
    if change=='realm':settlement.qbo_realm_snapshot='other'
    if change=='writer':env.source_accounting_link.owning_writer='intuit_native'
    if change=='receipt':env.source_payment.quickbooks_payment_id='other'
    with pytest.raises(r.DB048ReconciliationError,match='identity'):
        await c.sync_gross_credit_application(db,env,settlement)
    assert not state['posts']


@pytest.mark.asyncio
async def test_bounded_stale_retry_reuses_request_identity(monkeypatch):
    db,env,settlement,state=fixture(monkeypatch)
    state['stale']=1
    await c.sync_gross_credit_application(db,env,settlement)
    assert len(state['posts'])==2
    assert state['posts'][0]['params']==state['posts'][1]['params']


@pytest.mark.asyncio
async def test_provider_readback_must_match(monkeypatch):
    db,env,settlement,state=fixture(monkeypatch)
    state['bad_readback']=True
    with pytest.raises(r.DB048ReconciliationError):
        await c.sync_gross_credit_application(db,env,settlement)
    assert len(state['posts'])==3
    assert settlement.accounting_projection_snapshot=={}


@pytest.mark.asyncio
async def test_closed_period_credit_update_rejected_without_write(monkeypatch):
    db,env,settlement,state=fixture(monkeypatch)
    state['close_date']='2026-09-02'
    with pytest.raises(r.DB048ReconciliationError,match='closed accounting period'):
        await c.sync_gross_credit_application(db,env,settlement)
    assert not state['posts']


@pytest.mark.asyncio
async def test_closed_period_exact_credit_replay_does_not_write(monkeypatch):
    db,env,settlement,state=fixture(monkeypatch)
    await c.sync_gross_credit_application(db,env,settlement)
    state['close_date']='2026-09-02'
    await c.sync_gross_credit_application(db,env,settlement)
    assert len(state['posts'])==1


@pytest.mark.asyncio
async def test_recovered_dispute_uses_immutable_adjustment_net(monkeypatch):
    db,env,settlement,state=fixture(monkeypatch)
    monkeypatch.setattr(g,'_attempt_changes',AsyncMock(return_value=[
        {'principal':D('-20'),'fee':D('-.60'),'tax':D('-.03'),'gross':D('-20.63')},
        {'principal':D('10'),'fee':D('.30'),'tax':D('.02'),'gross':D('10.32')}]))
    # Original source becomes93.15? Exact component net is 103.15-20.63+10.32=92.84.
    state['payment']['TotalAmt']=102.84
    state['payment']['Line'][0]['Amount']=92.84
    settlement.accounting_projection_snapshot={'payments':{str(env.source_attempt.id):
        {'total':'102.84','lines':[('source','92.84')],'unapplied':'10.00'}}}
    await c.sync_gross_credit_application(db,env,settlement)
    assert state['payment']['TotalAmt']==102.84
    assert state['payment']['Line'][0]['Amount']==92.84
    assert state['payment']['UnappliedAmt']==0


@pytest.mark.asyncio
async def test_gross_dispatch_and_native_writer_guard(monkeypatch):
    db,env,settlement,state=fixture(monkeypatch)
    assert await r.sync_db048_credit_application(db,env)=='receipt'
    env.config.writer_strategy='intuit_native';env.link=NS(sync_state=None)
    with pytest.raises(r.DB048ReconciliationError,match='Intuit-native'):
        await r.sync_db048_credit_application(db,env)
    assert env.link.sync_state=='awaiting_native_import'


async def ledger(db,monkeypatch):
    from test_db048_invoice_settlements import _financial_context,_add_eligible_invoice
    from app.services.invoice_settlement_service import get_or_create_settlement,create_attempt
    from app.db.models.invoice_settlement import PaymentOverpayment,CustomerCreditEntry
    tenant,owner,customer,invoice=await _financial_context(db,monkeypatch)
    customer.quickbooks_customer_id='qb-customer'
    settlement=await get_or_create_settlement(db,invoice=invoice,customer_id=customer.id,tenant=tenant)
    creation=await create_attempt(db,invoice=invoice,tenant=tenant,customer_id=customer.id,
        actor=owner,amount=D('100'),rail='card',expected_settlement_version=settlement.version,
        idempotency_key='credit-qa-create',source='customer_portal',subject_type='customer',subject_id=customer.id)
    excess=PaymentOverpayment(tenant_id=tenant.id,invoice_id=invoice.id,settlement_id=settlement.id,
        source_attempt_id=creation.attempt.id,customer_id=customer.id,amount=D('10'),state='credited')
    db.add(excess);await db.flush()
    def entry(kind,amount,source=None,target=None):
        return CustomerCreditEntry(tenant_id=tenant.id,customer_id=customer.id,entry_type=kind,
            amount=D(amount),origin_overpayment_id=excess.id if kind=='issued' else None,
            source_entry_id=source,target_invoice_id=target,actor_name_snapshot='QA',
            idempotency_key=uuid4().hex,request_hash='0'*64)
    origin=entry('issued','10');db.add(origin);await db.flush()
    targets=[]
    for _ in range(2):
        target=await _add_eligible_invoice(db,tenant=tenant,customer=customer,reference_invoice=invoice,with_shadow_settlement=False)
        target_settlement=await get_or_create_settlement(db,invoice=target,customer_id=customer.id,tenant=tenant)
        target_settlement.qbo_realm_snapshot=settlement.qbo_realm_snapshot
        target_settlement.initial_provider_configuration_version=1
        targets.append((target,target_settlement))
    applications=[entry('applied','4',origin.id,targets[0][0].id),entry('applied','6',origin.id,targets[1][0].id)]
    db.add_all(applications);await db.flush()
    monkeypatch.setattr(r,'_ensure_db048_qbo_invoice',AsyncMock(side_effect=lambda **kw:('qb-customer',str(kw['invoice'].id))))
    return NS(tenant=tenant,customer=customer,attempt=creation.attempt,targets=targets,
        applications=applications,entry=entry,connection=NS(realm_id=settlement.qbo_realm_snapshot))


@pytest.mark.asyncio
async def test_real_ledger_multiple_targets_and_recovery(db_session,monkeypatch):
    x=await ledger(db_session,monkeypatch)
    kwargs=dict(attempt=x.attempt,tenant=x.tenant,connection=x.connection)
    assert await c.gross_credit_allocations(db_session,**kwargs)=={str(x.targets[0][0].id):D('4'),str(x.targets[1][0].id):D('6')}
    reverse=x.entry('reversed','3',x.applications[0].id)
    db_session.add(reverse);await db_session.flush()
    recovery=x.entry('applied','2',reverse.id,x.targets[0][0].id)
    db_session.add(recovery);await db_session.flush()
    assert (await c.gross_credit_allocations(db_session,**kwargs))[str(x.targets[0][0].id)]==D('3')


@pytest.mark.asyncio
@pytest.mark.parametrize('bad',['tenant','customer','realm'])
async def test_real_ledger_target_fences(db_session,monkeypatch,bad):
    x=await ledger(db_session,monkeypatch)
    if bad=='tenant':x.tenant=NS(id=uuid4(),name='foreign')
    elif bad=='customer':x.attempt=NS(id=x.attempt.id,customer_id=uuid4())
    else:x.connection.realm_id='other'
    kwargs=dict(attempt=x.attempt,tenant=x.tenant,connection=x.connection)
    if bad=='realm':
        with pytest.raises(r.DB048ReconciliationError,match='realm'):
            await c.gross_credit_allocations(db_session,**kwargs)
    else:
        assert await c.gross_credit_allocations(db_session,**kwargs)=={}
    r._ensure_db048_qbo_invoice.assert_not_awaited()


@pytest.mark.asyncio
async def test_real_ledger_recovery_cannot_exceed_reversal(db_session,monkeypatch):
    x=await ledger(db_session,monkeypatch)
    reverse=x.entry('reversed','2',x.applications[0].id)
    db_session.add(reverse);await db_session.flush()
    db_session.add(x.entry('applied','3',reverse.id,x.targets[0][0].id));await db_session.flush()
    with pytest.raises(r.DB048ReconciliationError,match='recovery exceeds'):
        await c.gross_credit_allocations(db_session,attempt=x.attempt,tenant=x.tenant,connection=x.connection)
