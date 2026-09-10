"""Gross accounting runtime tests. Every provider request is mocked."""
from copy import deepcopy
from decimal import Decimal
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.services import db048_accounting_reconciliation as r
from app.services import db048_qbo_gross_accounting as g
from app.services.db048_qbo_invoice_projection import (
    COMPOSITION_VERSION, InvoiceIdentity, ConfirmedEarnedAttempt, project_gross_invoice,
)


def envelope():
    tenant, invoice_id, attempt_id = uuid4(), uuid4(), uuid4()
    customer_id=uuid4()
    invoice = NS(id=invoice_id, tenant_id=tenant, invoice_number="TPS-001", quickbooks_invoice_id=None,
                 created_at=None, due_date=None)
    attempt = NS(id=attempt_id, tenant_id=tenant, invoice_id=invoice_id, provider="quickbooks_payments",
        rail="card", provider_charge_id="MT123", provider_reference=None,
        applied_principal_amount=Decimal("100"), applied_card_fee_amount=Decimal("3"),
        applied_card_fee_tax_amount=Decimal("0"), provider_charge_amount=Decimal("108"),
        unapplied_amount=Decimal("5"), state="confirmed")
    settlement = NS(id=uuid4(), tenant_id=tenant, invoice_id=invoice_id, principal_total=Decimal("100"),
        accounting_composition_version=COMPOSITION_VERSION, accounting_projection_snapshot={},
        accounting_projection_revision=None, accounting_fee_line_ids={}, qbo_realm_snapshot="realm",customer_id=customer_id)
    return NS(tenant=NS(id=tenant, name="Truck Pit Stop"), invoice=invoice, attempt=attempt,
        customer=NS(id=customer_id,company_name="Elis Logistics", first_name="", last_name="", tenant_id=tenant),
        payment=NS(payment_number="PAY-001", quickbooks_payment_id=None),
        settlement=settlement, connection=NS(realm_id="realm", tenant_id=tenant),
        config=NS(writer_strategy="dieselbridge"), refund=None,
        link=NS(account_mapping_snapshot={"qbp_clearing_account":"clearing"}, provider_deposit_id=None,
                owning_writer="dieselbridge", financial_object_type="invoice_payment"))


def provider(monkeypatch, env):
    db = NS(flush=AsyncMock())
    async def locked(*args): return env.settlement
    async def projection(*args, **kwargs):
        identity = InvoiceIdentity(str(env.tenant.id), "realm", str(env.invoice.id))
        member = ConfirmedEarnedAttempt(identity, str(env.attempt.id), COMPOSITION_VERSION, "card",
            env.attempt.applied_principal_amount, env.attempt.applied_card_fee_amount,
            env.attempt.applied_card_fee_tax_amount, env.attempt.provider_charge_amount,
            env.attempt.unapplied_amount)
        result = project_gross_invoice(identity=identity, composition_version=COMPOSITION_VERSION,
            principal_base=env.settlement.principal_total, attempts=[member])
        return result, {str(env.attempt.id):{"qbo_card_fee_item_id":"fee-item",
            "card_fee_income_account":"income", "qbo_card_fee_tax_code_id":"tax-code",
            "_fee_description":"Card processing fee — QBP MT123"}}
    state = {"invoice":None, "payment":None, "journal":None, "posts":[], "stale":0, "close_date":None,
             "invoice_changes_payment":False, "payment_edit":None,
             "zero_payment_edit":None, "recovery_payment_edit":None}
    async def request(connection, method, path, **kwargs):
        if method == "GET":
            if path == "preferences": return {"Preferences":{"AccountingInfoPrefs":{"BookCloseDate":state["close_date"]}}}
            if path.startswith("journalentry/"):return {"JournalEntry":deepcopy(state["journal"])}
            if path == "item/fee-item": return {"Item":{"Id":"fee-item", "Type":"Service", "IncomeAccountRef":{"value":"income"}}}
            if path == "taxcode/tax-code": return {"TaxCode":{"Id":"tax-code", "SalesTaxRateList":{"TaxRateDetail":[{"TaxRateRef":{"value":"rate"}}]}}}
            if path == "taxrate/rate": return {"TaxRate":{"Id":"rate", "RateValue":5}}
            return {"Invoice" if path.startswith("invoice/") else "Payment":deepcopy(state["invoice" if path.startswith("invoice/") else "payment"])}
        state["posts"].append((path, deepcopy(kwargs)))
        if state["stale"] and path.startswith("invoice?"):
            state["stale"] -= 1
            raise r.QuickBooksAccountingError("QuickBooks Accounting returned HTTP 400", status_code=400, fault_code=5010)
        payload = deepcopy(kwargs["json"])
        if path=="journalentry":
            state["journal"]=dict(payload,Id="journal-1")
            return {"JournalEntry":deepcopy(state["journal"])}
        if path.startswith("invoice"):
            result = dict(state["invoice"] or {}, **payload)
            result.update(Id="invoice-1", SyncToken="1")
            result["TotalAmt"] = sum(line["Amount"] for line in result["Line"]) + result["TxnTaxDetail"]["TotalTax"]
            for index,line in enumerate(result["Line"]):line["Id"] = str(index+1)
            state["invoice"] = result
            if state["invoice_changes_payment"] and state["payment"]:
                receipt=state["payment"]
                receipt["SyncToken"]=str(int(receipt["SyncToken"])+1)
                for line in receipt["Line"]:
                    line["Amount"]=min(line["Amount"],result["TotalAmt"])
                receipt["UnappliedAmt"]=float(Decimal(str(receipt["TotalAmt"]))-sum(Decimal(str(line["Amount"])) for line in receipt["Line"]))
                if state["payment_edit"]:
                    state["payment_edit"](receipt)
            return {"Invoice":deepcopy(result)}
        if path.startswith("payment?") and payload["SyncToken"]!=state["payment"]["SyncToken"]:
            raise r.QuickBooksAccountingError("QuickBooks Accounting returned HTTP 400",status_code=400,fault_code=5010)
        if path=="payment?operation=void":
            payload=dict(state["payment"],TotalAmt=0,Line=[],TxnStatus="Voided")
        result = dict(payload, Id="payment-1", SyncToken="1", TxnDate="2026-09-09")
        result["UnappliedAmt"] = result["TotalAmt"] - sum(line["Amount"] for line in result["Line"])
        if result["TotalAmt"]==0:
            result.pop("DepositToAccountRef",None)  # Observed QBO zero-Payment shape.
            if state["zero_payment_edit"]:state["zero_payment_edit"](result)
        elif path.startswith("payment?") and state["recovery_payment_edit"]:
            state["recovery_payment_edit"](result)
        state["payment"] = result
        return {"Payment":deepcopy(result)}
    async def query(connection, statement):
        if "from Account" in statement:return [{"Id":"ar"}]
        if "from JournalEntry" in statement:return [deepcopy(state["journal"])] if state["journal"] else []
        key = "invoice" if "from Invoice" in statement else "payment"
        return [deepcopy(state[key])] if state[key] else []
    monkeypatch.setattr(g,"_locked_settlement",locked)
    monkeypatch.setattr(g,"_projection",projection)
    monkeypatch.setattr(r,"_request",request)
    monkeypatch.setattr(r,"_query",query)
    monkeypatch.setattr(r,"ensure_customer",AsyncMock(return_value="customer"))
    monkeypatch.setattr(r,"_ensure_service_item",AsyncMock(return_value="base-item"))
    monkeypatch.setattr(r,"_resolve_qbo_account_reference",AsyncMock(side_effect=lambda connection, value:value))
    return db,state


@pytest.mark.asyncio
async def test_gross_invoice_then_receipt_and_exact_replay(monkeypatch):
    env=envelope();db,state=provider(monkeypatch,env)
    assert await g.sync_gross_payment(db,env)=="payment-1"
    assert [path for path,_ in state["posts"]]==["invoice","payment"]
    assert state["invoice"]["TotalAmt"]==103
    assert state["payment"]["TotalAmt"]==108
    assert state["payment"]["Line"][0]["Amount"]==103
    assert state["payment"]["UnappliedAmt"]==5
    assert env.link.provider_deposit_id=="payment-1"
    assert env.settlement.accounting_fee_line_ids=={str(env.attempt.id):"2"}
    await g.sync_gross_payment(db,env)
    assert len(state["posts"])==2
    assert all("ProcessPayment" not in call["json"] for _,call in state["posts"])


@pytest.mark.asyncio
@pytest.mark.parametrize("mutate",["customer","total","allocation","unapplied","deposit","currency","reference","foreign_line","exchange"])
async def test_receipt_adoption_rejects_mismatch(monkeypatch,mutate):
    env=envelope();db,state=provider(monkeypatch,env)
    await g.sync_gross_payment(db,env)
    entity=state["payment"]
    if mutate=="customer":entity["CustomerRef"]["value"]="foreign"
    if mutate=="total":entity["TotalAmt"]=109
    if mutate=="allocation":entity["Line"][0]["Amount"]=102
    if mutate=="unapplied":entity["UnappliedAmt"]=4
    if mutate=="deposit":entity["DepositToAccountRef"]["value"]="foreign"
    if mutate=="currency":entity["CurrencyRef"]={"value":"EUR"}
    if mutate=="reference":entity["PaymentRefNum"]="other"
    if mutate=="foreign_line":entity["Line"][0]["LinkedTxn"][0]["TxnId"]="other"
    if mutate=="exchange":entity["ExchangeRate"]="1.001"
    with pytest.raises(r.DB048ReconciliationError): await g.sync_gross_payment(db,env)
    assert len(state["posts"])==2


@pytest.mark.asyncio
async def test_crash_before_local_identity_adopts_same_provider_objects(monkeypatch):
    env=envelope();db,state=provider(monkeypatch,env)
    await g.sync_gross_payment(db,env)
    env.invoice.quickbooks_invoice_id=None
    env.payment.quickbooks_payment_id=None
    env.settlement.accounting_projection_snapshot={}
    await g.sync_gross_payment(db,env)
    assert len(state["posts"])==2


@pytest.mark.asyncio
@pytest.mark.parametrize("mutation",["item","amount","tax","currency","description","exchange"])
async def test_invoice_external_edit_never_overwritten(monkeypatch,mutation):
    env=envelope();db,state=provider(monkeypatch,env)
    await g.sync_gross_payment(db,env)
    entity=state["invoice"]
    if mutation=="item":entity["Line"][0]["SalesItemLineDetail"]["ItemRef"]["value"]="other"
    if mutation=="amount":entity["Line"][0]["Amount"]=90
    if mutation=="tax":entity["TxnTaxDetail"]["TotalTax"]=1
    if mutation=="currency":entity["CurrencyRef"]["value"]="EUR"
    if mutation=="description":entity["Line"][0]["Description"]="other"
    if mutation=="exchange":entity["ExchangeRate"]="1.001"
    with pytest.raises(r.DB048ReconciliationError): await g.sync_gross_payment(db,env)
    assert len(state["posts"])==2


@pytest.mark.asyncio
async def test_revision_changes_bounded_stale_retry(monkeypatch):
    env=envelope();db,state=provider(monkeypatch,env)
    await g.sync_gross_payment(db,env)
    old=env.settlement.accounting_projection_revision
    env.attempt.applied_card_fee_amount=Decimal("4")
    env.attempt.provider_charge_amount=Decimal("109")
    state["stale"]=1
    await g.ensure_gross_invoice(db,connection=env.connection,invoice=env.invoice,customer=env.customer,settlement=env.settlement,tenant_name=env.tenant.name)
    assert env.settlement.accounting_projection_revision!=old
    assert state["invoice"]["TotalAmt"]==104
    assert state["posts"][-1][1]["params"]!=state["posts"][0][1]["params"]


@pytest.mark.asyncio
@pytest.mark.parametrize("tax,ok",[("0.15",True),("0.16",False)])
async def test_tax_mapping_requires_exact_provider_rate(monkeypatch,tax,ok):
    env=envelope();env.attempt.applied_card_fee_tax_amount=Decimal(tax)
    env.attempt.provider_charge_amount+=Decimal(tax)
    db,state=provider(monkeypatch,env)
    if ok:
        await g.sync_gross_payment(db,env)
        assert state["invoice"]["TxnTaxDetail"]["TotalTax"]==0.15
        assert state["invoice"]["Line"][0]["SalesItemLineDetail"]["TaxCodeRef"]=={"value":"NON"}
        assert state["invoice"]["Line"][1]["SalesItemLineDetail"]["TaxCodeRef"]=={"value":"TAX"}
        assert state["invoice"]["TxnTaxDetail"]["TxnTaxCodeRef"]=={"value":"tax-code"}
    else:
        with pytest.raises(r.DB048ReconciliationError,match="earned tax"):await g.sync_gross_payment(db,env)
        assert not state["posts"]


@pytest.mark.asyncio
@pytest.mark.parametrize("adjustment",["reversal","dispute","closed","closed_zero","recovery_excess","tax_reversal","tax_dispute"])
async def test_real_confirmed_attempt_dispatches_gross_and_append_only_reversal(db_session, monkeypatch,adjustment):
    from sqlalchemy import select
    import test_db048_invoice_settlements as fixtures
    from app.core.config import settings
    from app.db.models.invoice_settlement import PaymentAccountingLink, TenantPaymentProviderConfiguration, PaymentRefund
    from app.db.models.quickbooks_connection import QuickBooksConnection
    from app.services.invoice_settlement_service import get_or_create_settlement, create_attempt, confirm_attempt
    taxed=adjustment.startswith("tax_")
    adjustment=adjustment.removeprefix("tax_")
    config_class = fixtures.TenantPaymentProviderConfiguration
    monkeypatch.setattr(fixtures,"TenantPaymentProviderConfiguration",lambda **kwargs:config_class(
        **kwargs,qbo_card_fee_item_id="fee-item",qbo_card_fee_tax_code_id="tax-code"))
    tenant, owner, customer, invoice = await fixtures._financial_context(db_session,monkeypatch,
        fee=Decimal("0") if adjustment=="closed_zero" else Decimal("3"))
    monkeypatch.setattr(settings,"DB048_GROSS_QBO_ACCOUNTING_ENABLED",True)
    settlement = await get_or_create_settlement(db_session,invoice=invoice,customer_id=customer.id,tenant=tenant)
    if taxed:
        settlement.max_card_fee_tax=Decimal("0.15")
    card = await create_attempt(db_session,invoice=invoice,tenant=tenant,customer_id=customer.id,
        actor=owner,amount=Decimal("100"),rail="card",expected_settlement_version=settlement.version,
        idempotency_key="gross-card",source="customer_portal",subject_type="customer",subject_id=customer.id)
    card.attempt.provider_intent_id="pi_gross"
    result = await confirm_attempt(db_session,attempt_id=card.attempt.id,tenant=tenant,actor=owner,
        expected_attempt_version=card.attempt.version,idempotency_key="gross-confirm",
        received_principal=Decimal("100"),reference="pi_gross",provider_charge_id="ch_gross",provider_event_id="evt_gross")
    link = await db_session.scalar(select(PaymentAccountingLink).where(PaymentAccountingLink.attempt_id==card.attempt.id))
    connection = await db_session.scalar(select(QuickBooksConnection).where(QuickBooksConnection.tenant_id==tenant.id))
    config = await db_session.scalar(select(TenantPaymentProviderConfiguration).where(TenantPaymentProviderConfiguration.tenant_id==tenant.id))
    env = r.AccountingEnvelope(uuid4(),tenant,link,result.attempt,result.payment,invoice,customer,connection,config,settlement)
    real_lock,real_projection = g._locked_settlement,g._projection
    _,state = provider(monkeypatch,env)
    state["invoice_changes_payment"]=taxed
    monkeypatch.setattr(g,"_locked_settlement",real_lock)
    monkeypatch.setattr(g,"_projection",real_projection)
    monkeypatch.setattr(r,"_resolve_qbo_account_reference",AsyncMock(side_effect=lambda connection,value:"income" if value=="Card Fee Income" else value))
    await r.deliver_accounting_envelope(db_session,env)
    expected_gross=100 if adjustment=="closed_zero" else 103.15 if taxed else 103
    assert state["payment"]["TotalAmt"]==expected_gross
    assert state["payment"]["Line"][0]["Amount"]==expected_gross
    assert link.provider_fee_journal_id is None
    assert link.sync_state=="synced"
    # Real reversal ledger is used; only external provider operations are mocks.
    if adjustment in {"dispute","recovery_excess"}:
        await r.record_stripe_dispute(db_session,provider_account_id=tenant.stripe_account_id,
            provider_charge_id="ch_gross",provider_dispute_id="dp_gross",provider_event_id="evt_dispute",
            amount=Decimal(str(expected_gross)),currency="USD",reason="test")
    else:
        await r.reverse_confirmed_attempt(db_session,tenant_id=tenant.id,provider_account_id=tenant.stripe_account_id,
            provider_charge_id="ch_gross",provider_event_id="evt_reversal",reason="test")
    kind="payment_dispute" if adjustment in {"dispute","recovery_excess"} else "payment_reversal"
    reversal_link=await db_session.scalar(select(PaymentAccountingLink).where(
        PaymentAccountingLink.attempt_id==card.attempt.id,PaymentAccountingLink.financial_object_type==kind))
    reversed_env=r.AccountingEnvelope(uuid4(),tenant,reversal_link,result.attempt,result.payment,invoice,customer,connection,config,settlement)
    if adjustment in {"closed","closed_zero"}:
        state["close_date"]="2099-12-31"
        before=len(state["posts"])
        with pytest.raises(r.DB048ReconciliationError,match="closed accounting period"):
            await r.deliver_accounting_envelope(db_session,reversed_env)
        assert len(state["posts"])==before
        return
    await r.deliver_accounting_envelope(db_session,reversed_env)
    assert state["payment"]["TotalAmt"]==0
    assert "DepositToAccountRef" not in state["payment"]
    lines=state["invoice"]["Line"]
    assert [line["Amount"] for line in lines]==[100,3,-3]
    assert state["invoice"]["TotalAmt"]==100
    if taxed:
        assert state["invoice"]["TxnTaxDetail"]["TxnTaxCodeRef"]=={"value":"tax-code"}
        assert state["invoice"]["TxnTaxDetail"]["TotalTax"]==0
        # Tax components are canonically grouped by rate, not ordered by
        # immutable event UUIDs; invoice sales-line order remains asserted.
        assert sorted(line["Amount"] for line in state["invoice"]["TxnTaxDetail"]["TaxLine"])==[-0.15,0.15]
        assert g.invoice_semantics(state["invoice"])["tax_lines"]==[["rate","5","0.00","0.00"]]
        assert [line["SalesItemLineDetail"]["TaxCodeRef"]["value"] for line in lines]==["NON","TAX","TAX"]
    assert len(settlement.accounting_fee_line_ids)==2
    posted=len(state["posts"])
    await g.ensure_gross_invoice(db_session,connection=connection,invoice=invoice,customer=customer,
                                settlement=settlement,tenant_name=tenant.name)
    assert len(state["posts"])==posted
    if adjustment in {"dispute","recovery_excess"}:
        if adjustment=="recovery_excess":
            replacement=await create_attempt(db_session,invoice=invoice,tenant=tenant,customer_id=customer.id,
                actor=owner,amount=Decimal("100"),rail="zelle",expected_settlement_version=settlement.version,
                idempotency_key="replacement",source="staff",subject_type="staff",subject_id=owner.id,
                sender_evidence={"reference_number":"zelle-replacement"})
            await confirm_attempt(db_session,attempt_id=replacement.attempt.id,tenant=tenant,actor=owner,
                expected_attempt_version=replacement.attempt.version,idempotency_key="replacement-confirm",
                received_principal=Decimal("100"),reference="zelle-replacement")
        await r.close_stripe_dispute(db_session,provider_account_id=tenant.stripe_account_id,
            provider_charge_id="ch_gross",provider_dispute_id="dp_gross",provider_event_id="evt_won",
            amount=Decimal(str(expected_gross)),currency="USD",outcome="won")
        recovery_link=await db_session.scalar(select(PaymentAccountingLink).where(
            PaymentAccountingLink.attempt_id==card.attempt.id,PaymentAccountingLink.financial_object_type=="payment_dispute_recovery"))
        recovery_env=r.AccountingEnvelope(uuid4(),tenant,recovery_link,result.attempt,result.payment,invoice,customer,connection,config,settlement)
        await r.deliver_accounting_envelope(db_session,recovery_env)
        assert state["payment"]["TotalAmt"]==expected_gross
        assert state["payment"]["DepositToAccountRef"]=={"value":"Stripe Clearing"}
        if adjustment=="recovery_excess":
            assert state["payment"]["UnappliedAmt"]==103
            assert [line["Amount"] for line in state["invoice"]["Line"]]==[100,3,-3]
            refund=await db_session.scalar(select(PaymentRefund).where(PaymentRefund.source_attempt_id==card.attempt.id))
            await r.finalize_provider_refund(db_session,refund_id=refund.id,tenant_id=tenant.id,
                provider_account_id=tenant.stripe_account_id,provider_reference="re_test",
                provider_event_id="evt_refund",provider_status="succeeded")
            refund_link=await db_session.scalar(select(PaymentAccountingLink).where(PaymentAccountingLink.refund_id==refund.id))
            refund_env=r.AccountingEnvelope(uuid4(),tenant,refund_link,result.attempt,result.payment,invoice,customer,connection,config,settlement,refund)
            await r.deliver_accounting_envelope(db_session,refund_env)
            assert state["journal"]["Line"][0]["Amount"]==103
        else:
            assert [line["Amount"] for line in state["invoice"]["Line"]]==[100,3,-3,3]
            assert state["invoice"]["TotalAmt"]==expected_gross
            if taxed:
                assert state["invoice"]["TxnTaxDetail"]["TotalTax"]==0.15
                assert sorted(line["Amount"] for line in state["invoice"]["TxnTaxDetail"]["TaxLine"])==[-0.15,0.15,0.15]
                assert g.invoice_semantics(state["invoice"])["tax_lines"]==[["rate","5","0.15","3.00"]]
        before=len(state["posts"])
        await g.sync_gross_adjustment(db_session,reversed_env)
        assert len(state["posts"])==before


@pytest.mark.asyncio
async def test_tax_detail_rate_distribution_is_not_just_total(monkeypatch):
    env=envelope();env.attempt.applied_card_fee_tax_amount=Decimal("0.15")
    env.attempt.provider_charge_amount+=Decimal("0.15")
    db,state=provider(monkeypatch,env)
    await g.sync_gross_payment(db,env)
    state["invoice"]["TxnTaxDetail"]["TaxLine"][0]["TaxLineDetail"]["TaxRateRef"]["value"]="foreign"
    before=len(state["posts"])
    with pytest.raises(r.DB048ReconciliationError):await g.sync_gross_payment(db,env)
    assert len(state["posts"])==before


@pytest.mark.asyncio
@pytest.mark.parametrize("code",[None,"foreign"])
async def test_transaction_tax_code_readback_is_strict(monkeypatch,code):
    env=envelope();env.attempt.applied_card_fee_tax_amount=Decimal("0.15")
    env.attempt.provider_charge_amount+=Decimal("0.15")
    db,state=provider(monkeypatch,env)
    await g.sync_gross_payment(db,env)
    if code is None:
        state["invoice"]["TxnTaxDetail"].pop("TxnTaxCodeRef",None)
    else:
        state["invoice"]["TxnTaxDetail"]["TxnTaxCodeRef"]={"value":code}
    before=len(state["posts"])
    with pytest.raises(r.DB048ReconciliationError):await g.sync_gross_payment(db,env)
    assert len(state["posts"])==before


@pytest.mark.asyncio
async def test_distinct_transaction_tax_codes_fail_before_invoice_write(monkeypatch):
    env=envelope();env.attempt.applied_card_fee_tax_amount=Decimal("0.15")
    env.attempt.provider_charge_amount+=Decimal("0.15")
    db,state=provider(monkeypatch,env)
    original=g._projection
    async def mixed(*args,**kwargs):
        projection,mappings=await original(*args,**kwargs)
        member=projection.payments[0]
        mapping=mappings[str(env.attempt.id)]
        mappings["_fee_components"]=[("first",member,mapping),
            ("second",member,dict(mapping,qbo_card_fee_tax_code_id="another-code"))]
        return projection,mappings
    monkeypatch.setattr(g,"_projection",mixed)
    with pytest.raises(r.DB048ReconciliationError,match="single transaction tax code"):
        await g.sync_gross_payment(db,env)
    assert not state["posts"]


@pytest.mark.asyncio
@pytest.mark.parametrize("edit",["customer","total","allocation","unapplied","deposit","reference","foreign_invoice"])
async def test_invoice_side_effect_never_adopts_unrelated_receipt_edits(db_session,monkeypatch,edit):
    import sys
    original_provider=provider
    captured={}
    def edited_provider(patch,env):
        db,state=original_provider(patch,env)
        captured.update(state=state)
        def mutate(receipt):
            if edit=="customer":receipt["CustomerRef"]["value"]="foreign"
            elif edit=="total":receipt["TotalAmt"]=103.16
            elif edit=="unapplied":receipt["UnappliedAmt"]=3.16
            elif edit=="allocation":
                receipt["Line"][0]["Amount"]=99.99
                receipt["UnappliedAmt"]=3.16
            elif edit=="deposit":receipt["DepositToAccountRef"]["value"]="foreign"
            elif edit=="reference":receipt["PaymentRefNum"]="foreign"
            elif edit=="foreign_invoice":receipt["Line"][0]["LinkedTxn"][0]["TxnId"]="foreign"
        state["payment_edit"]=mutate
        return db,state
    monkeypatch.setattr(sys.modules[__name__],"provider",edited_provider)
    with pytest.raises(r.DB048ReconciliationError,match="identity changed|unexpected adjustments"):
        await test_real_confirmed_attempt_dispatches_gross_and_append_only_reversal(db_session,monkeypatch,"tax_dispute")
    assert not any(path.startswith("payment?") for path,_ in captured["state"]["posts"])


def http_fault_transport(monkeypatch,code="5010",errors=None):
    """Actual production parser consumes an HTTPX fault response, no network."""
    import httpx
    from app.services import quickbooks_accounting_service as qbo
    body={"Fault":{"Error":errors if errors is not None else [{
        "code":code,"Message":"private-customer","Detail":"private-access-token"}]}}
    request=AsyncMock(return_value=httpx.Response(400,json=body))
    monkeypatch.setattr(qbo.httpx.AsyncClient,"request",request)
    monkeypatch.setattr(qbo,"decrypt_quickbooks_token",lambda value:"synthetic-token")
    connection=NS(realm_id="realm",encrypted_access_token="synthetic-encrypted")
    return qbo,connection,request


@pytest.mark.asyncio
@pytest.mark.parametrize("code",["5010-secret","٥٠١٠","501050105",None,5010,True,[],{}])
async def test_http_fault_parser_redacts_invalid_code(monkeypatch,code):
    qbo,connection,request=http_fault_transport(monkeypatch,code)
    with pytest.raises(qbo.QuickBooksAccountingError) as error:
        await qbo._request(connection,"POST","invoice",json={})
    assert error.value.fault_code is None
    assert str(error.value)=="QuickBooks Accounting returned HTTP 400"
    assert "private" not in str(vars(error.value))
    assert request.await_count==1


@pytest.mark.asyncio
async def test_http_fault_parser_does_not_guess_among_multiple_errors(monkeypatch):
    qbo,connection,_=http_fault_transport(monkeypatch,errors=[{"code":"5010"},{"code":"2500"}])
    with pytest.raises(qbo.QuickBooksAccountingError) as error:
        await qbo._request(connection,"POST","invoice",json={})
    assert error.value.fault_code is None


@pytest.mark.asyncio
@pytest.mark.parametrize("code,failures,success",[("5010",1,True),("5010",3,False),("2500",1,False),("invalid",1,False)])
async def test_invoice_retry_uses_real_http_fault_parser(monkeypatch,code,failures,success):
    env=envelope();db,state=provider(monkeypatch,env)
    await g.sync_gross_payment(db,env)
    qbo,connection,http=http_fault_transport(monkeypatch,code)
    original=r._request
    attempts=[]
    reads=[]
    async def request(conn,method,path,**kwargs):
        if method=="GET" and path.startswith("invoice/"):
            reads.append(path)
        if method=="POST" and path=="invoice?operation=update":
            attempts.append(deepcopy(kwargs))
            if len(attempts)<=failures:
                return await qbo._request(connection,method,path,**kwargs)
        return await original(conn,method,path,**kwargs)
    monkeypatch.setattr(r,"_request",request)
    env.attempt.applied_card_fee_amount=Decimal("4")
    env.attempt.provider_charge_amount=Decimal("109")
    async def update():
        return await g.ensure_gross_invoice(db,connection=env.connection,invoice=env.invoice,
            customer=env.customer,settlement=env.settlement,tenant_name=env.tenant.name)
    if success:
        await update()
        assert state["invoice"]["TotalAmt"]==104
        assert len(attempts)==2 and len(reads)==3
        assert attempts[0]["params"]==attempts[1]["params"]
    else:
        with pytest.raises(qbo.QuickBooksAccountingError) as error:
            await update()
        assert error.value.fault_code==(int(code) if code.isdigit() else None)
        assert len(attempts)==(3 if code=="5010" else 1)
        assert state["invoice"]["TotalAmt"]==103
    assert http.await_count==min(failures,len(attempts))


@pytest.mark.asyncio
@pytest.mark.parametrize("failures,success",[(1,True),(2,True),(3,False)])
async def test_payment_retry_uses_real_http_fault_parser(db_session,monkeypatch,failures,success):
    import sys
    original_provider=provider
    observed={"faults":0,"gets":0}
    def fault_provider(patch,env):
        db,state=original_provider(patch,env)
        qbo,connection,http=http_fault_transport(patch)
        observed["http"]=http
        original=r._request
        async def request(conn,method,path,**kwargs):
            if method=="GET" and path.startswith("payment/"):
                observed["gets"]+=1
            if method=="POST" and path=="payment?operation=update" and observed["faults"]<failures:
                observed["faults"]+=1
                return await qbo._request(connection,method,path,**kwargs)
            return await original(conn,method,path,**kwargs)
        patch.setattr(r,"_request",request)
        return db,state
    monkeypatch.setattr(sys.modules[__name__],"provider",fault_provider)
    if success:
        await test_real_confirmed_attempt_dispatches_gross_and_append_only_reversal(db_session,monkeypatch,"tax_dispute")
    else:
        with pytest.raises(r.QuickBooksAccountingError) as error:
            await test_real_confirmed_attempt_dispatches_gross_and_append_only_reversal(db_session,monkeypatch,"tax_dispute")
        assert error.value.fault_code==5010
    assert observed["http"].await_count==failures and observed["gets"]>=3


@pytest.mark.asyncio
@pytest.mark.parametrize("stage,edit",[("zero","customer"),("zero","note"),("zero","reference"),
    ("zero","total"),("zero","unapplied"),("zero","line"),("zero","foreign_deposit"),
    ("recovery","missing_deposit"),("recovery","foreign_deposit")])
async def test_zero_deposit_exception_preserves_receipt_identity(db_session,monkeypatch,stage,edit):
    import sys
    original_provider=provider
    def edited_provider(patch,env):
        db,state=original_provider(patch,env)
        def mutate(receipt):
            if edit=="customer":receipt["CustomerRef"]={"value":"foreign"}
            elif edit=="note":receipt["PrivateNote"]="foreign"
            elif edit=="reference":receipt["PaymentRefNum"]="foreign"
            elif edit=="total":receipt["TotalAmt"]=0.01
            elif edit=="unapplied":receipt["UnappliedAmt"]=0.01
            elif edit=="line":receipt["Line"]=[{"Amount":0,"LinkedTxn":[{"TxnId":"foreign","TxnType":"Invoice"}]}]
            elif edit=="foreign_deposit":receipt["DepositToAccountRef"]={"value":"foreign"}
            elif edit=="missing_deposit":receipt.pop("DepositToAccountRef",None)
        state["zero_payment_edit" if stage=="zero" else "recovery_payment_edit"]=mutate
        return db,state
    monkeypatch.setattr(sys.modules[__name__],"provider",edited_provider)
    with pytest.raises(r.DB048ReconciliationError,match="identity changed"):
        await test_real_confirmed_attempt_dispatches_gross_and_append_only_reversal(db_session,monkeypatch,"tax_dispute")


@pytest.mark.parametrize("change",[{"TotalAmt":1},{"UnappliedAmt":1},{"Line":None},
    {"DepositToAccountRef":{}},{"DepositToAccountRef":{"value":""}},
    {"DepositToAccountRef":{"value":"foreign"}}])
def test_zero_deposit_exception_rejects_nonempty_or_malformed_state(change):
    receipt=dict(TotalAmt=0,UnappliedAmt=0,Line=[])
    assert g._receipt_deposit_matches(receipt,"clearing",allow_empty_zero=True)
    assert not g._receipt_deposit_matches(receipt,"clearing")
    for field in ("TotalAmt","UnappliedAmt","Line"):
        incomplete={key:value for key,value in receipt.items() if key!=field}
        assert not g._receipt_deposit_matches(incomplete,"clearing",allow_empty_zero=True)
    receipt.update(change)
    assert not g._receipt_deposit_matches(receipt,"clearing",allow_empty_zero=True)


@pytest.mark.asyncio
async def test_same_tenant_wrong_customer_rejected_before_provider(monkeypatch):
    env=envelope();db,state=provider(monkeypatch,env)
    env.customer.id=uuid4()
    with pytest.raises(r.DB048ReconciliationError):await g.sync_gross_payment(db,env)
    assert not state["posts"]
    r.ensure_customer.assert_not_awaited()


@pytest.mark.asyncio
async def test_three_card_partials_and_zelle_one_canonical_invoice(db_session,monkeypatch):
    """Real domain confirmation/outbox delivery; only the QBO transport is fake."""
    from sqlalchemy import select
    import test_db048_invoice_settlements as fixtures
    from app.core.config import settings
    from app.db.models.invoice_settlement import PaymentAccountingLink,TenantPaymentProviderConfiguration
    from app.db.models.quickbooks_connection import QuickBooksConnection
    from app.services.invoice_settlement_service import get_or_create_settlement,create_attempt,confirm_attempt
    config_class=fixtures.TenantPaymentProviderConfiguration
    monkeypatch.setattr(fixtures,"TenantPaymentProviderConfiguration",lambda **kwargs:config_class(
        **kwargs,qbo_card_fee_item_id="fee-item",qbo_card_fee_tax_code_id="tax-code"))
    tenant,owner,customer,invoice=await fixtures._financial_context(db_session,monkeypatch,
        principal=Decimal("1000"),fee=Decimal("30"))
    monkeypatch.setattr(settings,"DB048_GROSS_QBO_ACCOUNTING_ENABLED",True)
    settlement=await get_or_create_settlement(db_session,invoice=invoice,customer_id=customer.id,tenant=tenant)
    connection=await db_session.scalar(select(QuickBooksConnection).where(QuickBooksConnection.tenant_id==tenant.id))
    config=await db_session.scalar(select(TenantPaymentProviderConfiguration).where(TenantPaymentProviderConfiguration.tenant_id==tenant.id))
    real_lock,real_projection=g._locked_settlement,g._projection
    _,state=provider(monkeypatch,envelope())
    monkeypatch.setattr(g,"_locked_settlement",real_lock)
    monkeypatch.setattr(g,"_projection",real_projection)
    monkeypatch.setattr(r,"_resolve_qbo_account_reference",AsyncMock(side_effect=lambda connection,value:"income" if value=="Card Fee Income" else value))
    single_request,single_query=r._request,r._query
    payments={}
    async def request(connection,method,path,**kwargs):
        if method=="POST" and path=="payment":
            payload=deepcopy(kwargs["json"])
            payment_id=f"payment-{len(payments)+1}"
            payload.update(Id=payment_id,SyncToken="1")
            payload["UnappliedAmt"]=payload["TotalAmt"]-sum(line["Amount"] for line in payload["Line"])
            payments[payment_id]=payload
            state["posts"].append((path,deepcopy(kwargs)))
            return {"Payment":deepcopy(payload)}
        if method=="GET" and path.startswith("payment/"):
            return {"Payment":deepcopy(payments[path.split("/")[1]])}
        response=await single_request(connection,method,path,**kwargs)
        if response.get("Invoice"):
            response["Invoice"]["Balance"]=response["Invoice"]["TotalAmt"]-sum(
                line["Amount"] for payment in payments.values() for line in payment["Line"]
                if line["LinkedTxn"]==[{"TxnId":"invoice-1","TxnType":"Invoice"}])
        return response
    async def query(connection,statement):
        if "from Payment " in statement:
            reference=statement.split("PaymentRefNum = '",1)[1].split("'",1)[0]
            return [deepcopy(payment) for payment in payments.values() if payment["PaymentRefNum"]==reference]
        return await single_query(connection,statement)
    monkeypatch.setattr(r,"_request",request)
    monkeypatch.setattr(r,"_query",query)
    envelopes=[]
    for index,(rail,amount) in enumerate([("card","200"),("card","300"),("card","100"),("zelle","400")]):
        manual=rail=="zelle"
        created=await create_attempt(db_session,invoice=invoice,tenant=tenant,customer_id=customer.id,
            actor=owner,amount=Decimal(amount),rail=rail,expected_settlement_version=settlement.version,
            idempotency_key=f"multi-{index}",source="staff" if manual else "customer_portal",
            subject_type="staff" if manual else "customer",subject_id=owner.id if manual else customer.id,
            **({"sender_evidence":{"reference_number":"zelle-final"}} if manual else {}))
        if not manual:created.attempt.provider_intent_id=f"pi_multi_{index}"
        confirmed=await confirm_attempt(db_session,attempt_id=created.attempt.id,tenant=tenant,actor=owner,
            expected_attempt_version=created.attempt.version,idempotency_key=f"multi-confirm-{index}",
            received_principal=Decimal(amount),reference="zelle-final" if manual else f"pi_multi_{index}",
            **({} if manual else {"provider_charge_id":f"ch_multi_{index}","provider_event_id":f"evt_multi_{index}"}))
        link=await db_session.scalar(select(PaymentAccountingLink).where(PaymentAccountingLink.attempt_id==created.attempt.id))
        env=r.AccountingEnvelope(uuid4(),tenant,link,confirmed.attempt,confirmed.payment,
                                invoice,customer,connection,config,settlement)
        await r.deliver_accounting_envelope(db_session,env)
        envelopes.append(env)
    final=(await request(connection,"GET","invoice/invoice-1"))["Invoice"]
    assert final["TotalAmt"]==1018
    assert final["Balance"]==0
    assert [line["Amount"] for line in final["Line"]]==[1000,6,9,3]
    assert len(payments)==4
    assert [payment["TotalAmt"] for payment in payments.values()]==[206,309,103,400]
    assert all(payment["UnappliedAmt"]==0 for payment in payments.values())
    assert all(payment["Line"][0]["LinkedTxn"]==[{"TxnId":"invoice-1","TxnType":"Invoice"}] for payment in payments.values())
    assert settlement.confirmed_principal==Decimal("1000")
    assert sum(env.payment.amount for env in envelopes)==Decimal("1000")
    assert sum(path=="invoice" for path,_ in state["posts"])==1
    assert not any(path=="journalentry" for path,_ in state["posts"])
    assert all(env.link.provider_fee_journal_id is None for env in envelopes)
    before=len(state["posts"])
    for env in envelopes:await r.deliver_accounting_envelope(db_session,env)
    assert len(state["posts"])==before
