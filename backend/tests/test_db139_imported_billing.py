"""Imported billing must not infer native settlement or write records."""
from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace as NS
from uuid import uuid4
from unittest.mock import AsyncMock
import pytest
from fastapi import HTTPException
from sqlalchemy.dialects import postgresql
from app.api.v1.endpoints.repair_orders import get_imported_billing
from app.db.models.user import UserRole
from app.services.imported_billing import SOURCE, load_imported_billing, summarize_imported_billing


def invoice(**changes):
    return NS(**(dict(id=uuid4(), tenant_id=uuid4(), invoice_number="ETSINV-9001", status="paid", source=SOURCE, total_amount=Decimal("534.41"), deleted_at=None, updated_at=datetime(2026,10,18,tzinfo=timezone.utc)) | changes))


def payment(inv, **changes):
    return NS(**(dict(invoice_id=inv.id,tenant_id=inv.tenant_id,source=SOURCE,status="completed",amount=inv.total_amount,deleted_at=None) | changes))


def test_paid_example():
    inv=invoice()
    result=summarize_imported_billing([inv],[payment(inv)])
    assert result.payment_status=="unverified" and result.review_required
    assert result.model_dump(mode="json")["total_amount"]=="534.41"
    assert result.recorded_remaining_amount is None
    assert result.recorded_completed_amount is None
    assert result.reconciliation_status=="not_checked"


@pytest.mark.parametrize("amount",["100.00", None])
def test_imported_open_history_cannot_prove_current_source_debt(amount):
    inv=invoice(status="overdue")
    result=summarize_imported_billing([inv],[payment(inv,amount=Decimal(amount))] if amount else [])
    assert result.payment_status=="unverified" and result.review_required
    assert result.recorded_remaining_amount is None
    assert result.recorded_completed_amount is None


@pytest.mark.parametrize("change",[dict(source="native"),dict(deleted_at=datetime.now(timezone.utc)),dict(status="pending"),dict(status="failed"),dict(status="refunded"),dict(quickbooks_refund_id="refund"),dict(quickbooks_refunded_amount=Decimal("1")),dict(amount=Decimal("0")),dict(amount=Decimal("-1")),dict(amount=Decimal("NaN")),dict(amount=Decimal("1.001")),dict(amount=Decimal("535")),dict(invoice_id=uuid4()),dict(tenant_id=uuid4())])
def test_unsafe_payment_evidence(change):
    inv=invoice()
    result=summarize_imported_billing([inv],[payment(inv,**change)])
    assert result.payment_status=="unverified" and result.review_required
    assert result.total_amount==Decimal("534.41")
    assert result.recorded_completed_amount is None and result.recorded_remaining_amount is None
    assert result.review_reasons


@pytest.mark.parametrize("status,amounts",[("paid",[]),("sent",["534.41"]),("draft",[])])
def test_status_mismatch(status,amounts):
    inv=invoice(status=status)
    assert summarize_imported_billing([inv],[payment(inv,amount=Decimal(a)) for a in amounts]).payment_status=="unverified"


@pytest.mark.parametrize("variant",["missing","duplicate","deleted","native","zero","invalid"])
def test_invoice_holds(variant):
    inv=invoice()
    rows={"missing":[],"duplicate":[inv,invoice()],"deleted":[invoice(deleted_at=datetime.now(timezone.utc))],"native":[inv,invoice(source="native",status="cancelled")],"zero":[invoice(total_amount=Decimal("0"))],"invalid":[invoice(total_amount=Decimal("NaN"))]}[variant]
    result=summarize_imported_billing(rows,[])
    assert result.payment_status=="unverified" and result.review_required
    if variant!="zero": assert result.total_amount is None


class ReadOnlyDB:
    def __init__(self,order=None,invoices=(),payments=(),candidates=None):
        self.order,self.rows,self.statements=order,([candidates] if candidates is not None else [])+[invoices,payments],[]
        self.bind=NS(dialect=NS(name="sqlite"))
    async def scalar(self,statement):
        self.statements.append(statement)
        return self.order
    async def scalars(self,statement):
        self.statements.append(statement)
        return NS(all=lambda:self.rows.pop(0))


@pytest.mark.asyncio
async def test_loader_read_only_tenant_scope():
    inv=invoice()
    order=NS(id=uuid4(),tenant_id=inv.tenant_id, source=SOURCE, deleted_at=None, order_number="ETS-7001-8002", customer_id=uuid4(), vehicle_id=uuid4())
    inv.repair_order_id=order.id
    db=ReadOnlyDB(invoices=[inv],payments=[payment(inv)],candidates=[order])
    assert (await load_imported_billing(db,order)).payment_status=="unverified"
    sql=[str(s.compile(dialect=postgresql.dialect(),compile_kwargs={"literal_binds":True})) for s in db.statements]
    assert len(sql)==3 and all(str(order.tenant_id) in q and q.startswith("SELECT") for q in sql)
    assert str(order.id) in sql[1] and str(inv.id) in sql[2]
    assert all("deleted_at IS NULL" not in q for q in sql)


@pytest.mark.asyncio
@pytest.mark.parametrize("kind,code",[("absent",404),("native",409)])
async def test_endpoint_missing_native_before_billing(kind,code):
    tenant=uuid4()
    user=NS(id=uuid4(),tenant_id=tenant,role=UserRole.GARAGE_OWNER)
    order=NS(id=uuid4(),tenant_id=tenant,source=None) if kind=="native" else None
    db=ReadOnlyDB(order=order)
    with pytest.raises(HTTPException) as exc: await get_imported_billing(uuid4(),db,user)
    assert exc.value.status_code==code and len(db.statements)==1
    sql=str(db.statements[0].compile(dialect=postgresql.dialect(),compile_kwargs={"literal_binds":True}))
    assert str(tenant) in sql and "deleted_at IS NULL" in sql


@pytest.mark.asyncio
async def test_mechanic_assignment_guard():
    tenant=uuid4()
    order=NS(id=uuid4(),tenant_id=tenant,source=SOURCE,assigned_mechanic_id=uuid4())
    db=ReadOnlyDB(order=order)
    user=NS(id=uuid4(),tenant_id=tenant,role=UserRole.MECHANIC)
    with pytest.raises(HTTPException) as exc: await get_imported_billing(order.id,db,user)
    assert exc.value.status_code==403 and len(db.statements)==1


@pytest.mark.parametrize("evidence", [
    {"schema_version":1,"observations":[]},
    {"source_read_unavailable_at":"2026-10-18T12:00:00Z","observations":[]},
    {"revision_capacity_exceeded":True,"observations":[]},
    "malformed",
    {"observations":[{"evidence":{"total":{"amount":"534.41","currency":"USD"},"settlement_semantics":"unverified"}}]},
])
def test_newer_source_evidence_cannot_be_ignored(evidence):
    inv=invoice()
    result=summarize_imported_billing([inv],[payment(inv)],evidence)
    assert result.payment_status=="unverified" and result.review_required
    assert result.recorded_remaining_amount is None
    assert result.review_reasons


@pytest.mark.asyncio
async def test_postgres_optional_evidence_read_is_scoped():
    inv=invoice()
    order=NS(id=uuid4(),tenant_id=inv.tenant_id, source=SOURCE, deleted_at=None, order_number="ETS-7001-8002", customer_id=uuid4(), vehicle_id=uuid4())
    inv.repair_order_id=order.id
    class PostgresDB(ReadOnlyDB):
        async def execute(self,statement,parameters):
            self.statements.append(statement)
            assert parameters=={"tenant_id":order.tenant_id,"invoice_ids":[inv.id]}
            assert "to_jsonb(i)" in str(statement)
            return NS(all=lambda:[NS(id=inv.id,evidence={"observations":[]})])
    db=PostgresDB(invoices=[inv],payments=[payment(inv)],candidates=[order])
    db.bind=NS(dialect=NS(name="postgresql"))
    result=await load_imported_billing(db,order)
    assert result.payment_status=="unverified" and result.recorded_remaining_amount is None


from datetime import timedelta
from app.services.imported_billing import trusted_shop_binding, attach_imported_invoice_totals
from app.services.ets_source_evidence import _digest
from app.core.config import settings


def snapshot_fixture(**changes):
    inv=invoice()
    order=NS(id=uuid4(),tenant_id=inv.tenant_id,source=SOURCE,deleted_at=None,order_number="ETS-7001-8002")
    inv.repair_order_id=order.id
    money=lambda x:{"amount":str(x),"currency":"USD"}
    facts=dict(source="easy_truck_shop",schema_version=1,settlement_semantics="unverified",service_id="7001",invoice_id="inv1",invoice_number="9001",service_internal_id="srv1",invoice_service_id="srv1",ets_shop_id="shop1",observed_at_source=datetime.now(timezone.utc).isoformat(),invoice_status="10",currency="USD",total=money("534.41"),balance=money("0.00"),payment_lines_truncated=False,invoice_manifest={"complete":True,"evidence_kind":"verified_source_service_invoice_manifest","service_internal_id":"srv1","invoice_ids":["inv1"]},payment_lines=[{"id":"a1","amount":money("534.41"),"payment":{"id":"p1","status":"20","type":"0","provider":"1","canceled":False,"total":money("534.41"),"credit_total":money("0"),"unapplied_amount":money("0")}}])
    facts.update(changes)
    return inv,order,{"schema_version":1,"observations":[{"evidence":facts,"sha256":_digest(facts)}]}


def test_source_observation_semantics_do_not_grant_settlement():
    inv,order,envelope=snapshot_fixture()
    result=summarize_imported_billing([inv],[payment(inv)],envelope,order=order,shop_id="shop1")
    assert result.payment_status=="paid" and not result.review_required
    assert result.total_amount==Decimal("534.41") and result.recorded_remaining_amount==0
    assert result.evidence_basis=="ets_source_snapshot" and result.reconciliation_status=="not_checked"


@pytest.mark.parametrize("paid,status",[("100.00","partially_paid"),("0.00","unpaid")])
def test_source_open_status(paid,status):
    inv,order,envelope=snapshot_fixture(invoice_status="5",balance={"amount":str(Decimal("534.41")-Decimal(paid)),"currency":"USD"})
    facts=envelope["observations"][0]["evidence"]
    if Decimal(paid): facts["payment_lines"][0]["amount"]["amount"]=paid
    else: facts["payment_lines"]=[]
    envelope["observations"][0]["sha256"]=_digest(facts)
    result=summarize_imported_billing([inv],[],envelope,order=order,shop_id="shop1")
    assert result.payment_status==status and result.recorded_completed_amount==Decimal(paid)


def test_source_total_supersedes_stale_finance_without_writes():
    inv,order,envelope=snapshot_fixture()
    inv.total_amount=Decimal("600.00")
    result=summarize_imported_billing([inv],[],envelope,order=order,shop_id="shop1")
    assert result.payment_status=="paid" and result.total_amount==Decimal("534.41")
    assert result.review_required and "imported_financial_rows_differ" in result.review_reasons
    assert inv.total_amount==Decimal("600.00")


@pytest.mark.parametrize("changes",[
    {"invoice_status":"99"},{"invoice_status":"5"},{"currency":"EUR"},
    {"payment_lines_truncated":True},{"service_id":"1800"},{"invoice_number":"1668"},
    {"invoice_service_id":"different"},{"invoice_manifest":None},
    {"observed_at_source":(datetime.now(timezone.utc)+timedelta(hours=1)).isoformat()},
    {"balance":{"amount":"1.00","currency":"USD"}},
])
def test_invalid_source_state_holds(changes):
    inv,order,envelope=snapshot_fixture(**changes)
    result=summarize_imported_billing([inv],[payment(inv)],envelope,order=order,shop_id="shop1")
    assert result.payment_status=="unverified" and result.recorded_remaining_amount is None


def test_stale_source_keeps_observed_total_without_current_balance():
    inv,order,envelope=snapshot_fixture(observed_at_source=(datetime.now(timezone.utc)-timedelta(hours=25)).isoformat())
    result=summarize_imported_billing([inv],[payment(inv)],envelope,order=order,shop_id="shop1")
    assert result.payment_status=="unverified" and result.total_amount==Decimal("534.41")
    assert result.recorded_remaining_amount is None and "stale_source_observation" in result.review_reasons


@pytest.mark.parametrize("problem", ["digest", "time", "future"])
def test_invalid_confirmation_cannot_resurrect_paid_status(problem):
    inv, order, envelope = snapshot_fixture()
    confirmation = {"sha256": envelope["observations"][-1]["sha256"],
                    "observed_at_source": datetime.now(timezone.utc).isoformat()}
    if problem == "digest":
        confirmation["sha256"] = "wrong-digest"
    elif problem == "time":
        confirmation["observed_at_source"] = "not-a-time"
    else:
        confirmation["observed_at_source"] = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
    envelope["latest_confirmation"] = confirmation
    result = summarize_imported_billing([inv], [payment(inv)], envelope, order=order, shop_id="shop1")
    assert result.payment_status == "unverified"
    assert result.recorded_completed_amount is None and result.recorded_remaining_amount is None


@pytest.mark.parametrize("dedicated,completion,expected",[("{}","{}",None),("bad","{}",None),("[]","{}",None),("{key}","{}","shop1"),("{}","{key}","shop1"),("{key}","{conflict}",None),("{foreign}","{}",None)])
def test_trusted_shop_binding(monkeypatch,dedicated,completion,expected):
    import json
    tenant=uuid4()
    values={"{key}":json.dumps({str(tenant):"shop1"}),"{conflict}":json.dumps({str(tenant):"shop2"}),"{foreign}":json.dumps({str(uuid4()):"shop1"})}
    monkeypatch.setattr(settings,"ETS_IMPORTED_BILLING_SHOPS",values.get(dedicated,dedicated))
    monkeypatch.setattr(settings,"ETS_COMPLETED_OUTCOME_SHOPS",values.get(completion,completion))
    monkeypatch.setattr(settings,"ETS_COMPLETED_OUTCOMES_ENABLED",False)
    assert trusted_shop_binding(tenant)[0]==expected


@pytest.mark.parametrize("change",[dict(source="native"),dict(deleted_at=datetime.now(timezone.utc)),dict(status="pending"),dict(status="failed"),dict(status="refunded"),dict(quickbooks_refund_id="refund"),dict(tenant_id=uuid4())])
def test_source_does_not_hide_financial_ownership_or_reversal_conflicts(change):
    inv,order,envelope=snapshot_fixture()
    result=summarize_imported_billing([inv],[payment(inv,**change)],envelope,order=order,shop_id="shop1")
    assert result.payment_status=="unverified" and result.recorded_remaining_amount is None
    assert result.total_amount==Decimal("534.41") and result.review_required


@pytest.mark.asyncio
async def test_list_totals_batched_not_n_plus_one():
    tenant=uuid4()
    items=[NS(id=uuid4(),tenant_id=tenant,source=SOURCE,deleted_at=None,imported_invoice_total_amount=None, order_number=f"ETS-{7000+n}-8002", customer_id=uuid4(), vehicle_id=uuid4()) for n in range(25)]
    invoices=[invoice(tenant_id=tenant,repair_order_id=item.id) for item in items]
    db=ReadOnlyDB(invoices=invoices,candidates=items)
    actor=NS(tenant_id=tenant,role=UserRole.GARAGE_OWNER)
    await attach_imported_invoice_totals(db,items,actor)
    assert len(db.statements)==3 and all(item.imported_invoice_total_amount==Decimal("534.41") for item in items)
    sql=str(db.statements[1].compile(dialect=postgresql.dialect(),compile_kwargs={"literal_binds":True}))
    assert str(tenant) in sql and all(str(item.id) in sql for item in items)


@pytest.mark.asyncio
async def test_list_total_customer_native_and_foreign_rows_do_not_query():
    tenant=uuid4()
    actor=NS(tenant_id=tenant,role=UserRole.GARAGE_OWNER)
    db=ReadOnlyDB()
    items=[NS(id=uuid4(),tenant_id=tenant,source=None,deleted_at=None),NS(id=uuid4(),tenant_id=uuid4(),source=SOURCE,deleted_at=None)]
    await attach_imported_invoice_totals(db,items,actor)
    actor.role=UserRole.CUSTOMER
    await attach_imported_invoice_totals(db,[NS(id=uuid4(),tenant_id=tenant,source=SOURCE,deleted_at=None)],actor)
    assert db.statements==[]


@pytest.mark.asyncio
@pytest.mark.parametrize("role",[UserRole.CUSTOMER,UserRole.DRIVER,UserRole.SUPER_ADMIN])
async def test_route_dependency_denies_nonstaff(role):
    from app.api.v1.endpoints.repair_orders import require_role
    from app.services.parts_pricing import STAFF
    with pytest.raises(HTTPException) as exc:
        await require_role(*STAFF)(NS(role=role))
    assert exc.value.status_code==403


@pytest.mark.asyncio
async def test_existing_labor_list_does_not_receive_order_billing_enrichment(monkeypatch):
    from app.api.v1.endpoints import repair_orders
    order = NS(id=uuid4(), tenant_id=uuid4())
    labor = NS(description="Existing labor")
    results = [NS(scalar_one_or_none=lambda: order), NS(scalar=lambda: 1),
               NS(scalars=lambda: NS(all=lambda: [labor]))]
    db = NS(execute=AsyncMock(side_effect=results))
    user = NS(role=UserRole.GARAGE_OWNER, tenant_id=order.tenant_id)
    monkeypatch.setattr(repair_orders, "_account_labor_response", lambda *_: labor)
    enrichment = AsyncMock(side_effect=AssertionError("Labor rows are not repair orders"))
    monkeypatch.setattr(repair_orders.imported_billing, "attach_imported_invoice_totals", enrichment)
    response = await repair_orders.list_repair_order_labor(order.id, 0, 100, False, db, user)
    assert response == [labor]
    enrichment.assert_not_awaited()
