"""Bounded operational guard tests; no production connection or financial writes."""
import copy
import importlib.util
import json
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location("ets_link_repair", Path(__file__).parents[1]/"scripts/repair_ets_0662_vehicle_link.py")
repair = importlib.util.module_from_spec(spec)
spec.loader.exec_module(repair)


def fixture_state():
    orders = [dict(id=str(n),tenant_id="tenant",source=repair.SOURCE,deleted_at=None,customer_id="customer",vehicle_id="old" if n==0 else "target",order_number=repair.JOB+(["","-2","-3","-4"][n]),updated_at="before") for n in range(4)]
    invoice=dict(id="invoice",tenant_id="tenant",source=repair.SOURCE,deleted_at=None,repair_order_id="0",invoice_number="ETSINV-0625",total_amount=9658,ets_source_evidence={"observations":[{"evidence":{"service_id":"0662","service_internal_id":"348595","invoice_id":"321290","invoice_number":"0625"}}]})
    return dict(orders=orders,vehicles=[dict(id=i,tenant_id="tenant",customer_id="customer",source=repair.SOURCE,deleted_at=None,unit_number="457",vin=None,ets_external_id="106566" if i=="target" else None) for i in ["old","target"]],neighbors=[{"id":"outside","vehicle_id":"old"}],invoices=[invoice],dependencies={"payments":[{"id":"payment","tenant_id":"tenant","amount":100}],"invoice_settlements":[{"id":"settlement","version":2}],"invoice_payment_ledger_events":[{"id":"event","amount":100}]},history=[],projections=[{"repair_order_id":o["id"],"vehicle_id":o["vehicle_id"],"payload":{"vehicle_id":o["vehicle_id"]}} for o in orders],customers=[{"id":"customer","tenant_id":"tenant","ets_external_id":"91612","deleted_at":None}],triggers={n:"AFTER UPDATE" for n in ["repair_order_read_model_repair_order","fleet_board_read_model_repair_order"]})


class Cursor:
    def __init__(self,state): self.state,self.statements=state,[]
    def execute(self,query,params):
        self.statements.append(query)
        if query.startswith("UPDATE"):
            target,owner,tenant,old=params
            row=next(o for o in self.state["orders"] if o["id"]==owner)
            assert row["vehicle_id"]==old and row["tenant_id"]==tenant
            row["vehicle_id"],row["updated_at"]=target,"after"
            projection=next(p for p in self.state["projections"] if p["repair_order_id"]==owner)
            projection["vehicle_id"]=projection["payload"]["vehicle_id"]=target
            self.rowcount=1
        if query.startswith("INSERT"):
            self.state["history"].append(dict(id=params[0],event_type=params[3],detail=params[5]))
    def fetchone(self): return ("garage_owner",True,None)


@pytest.fixture
def setup(monkeypatch):
    state=fixture_state();cur=Cursor(state)
    monkeypatch.setattr(repair,"collect",lambda *_args,**_kwargs:copy.deepcopy(state))
    proof={"test":"reviewed_source"}
    monkeypatch.setattr(repair,"PROOF_SHA",repair.digest(proof))
    plan=repair.make_plan(cur,"tenant",proof)
    return state,cur,plan


def test_plan_is_read_only_and_digest_bound(setup):
    state,cur,plan=setup
    assert all(q.startswith("SELECT") for q in cur.statements)
    assert plan["owner"]=="0" and plan["target_vehicle"]=="target"
    with pytest.raises(ValueError,match="plan_digest_mismatch"):
        repair.apply_plan(cur,plan,"wrong")
    assert not any(q.startswith("UPDATE") for q in cur.statements)


def test_apply_changes_one_link_and_audited_noop_does_not_write(setup):
    state,cur,plan=setup
    protected=copy.deepcopy(state["dependencies"])
    assert repair.apply_plan(cur,plan,repair.digest(plan))=="applied"
    assert state["dependencies"]==protected and len(state["history"])==1
    assert sum(q.startswith("UPDATE") for q in cur.statements)==1
    assert repair.apply_plan(cur,plan,repair.digest(plan))=="already_applied"
    assert sum(q.startswith("UPDATE") for q in cur.statements)==1
    assert len(state["history"])==1


@pytest.mark.parametrize("drift",["payments","invoice_settlements","invoice_payment_ledger_events","neighbors","source","projection"])
def test_drift_aborts_before_mutation(setup,drift):
    state,cur,plan=setup
    if drift in state["dependencies"]: state["dependencies"][drift][0]["changed"]=True
    elif drift=="source": state["invoices"][0]["ets_source_evidence"]["freshness"]="new observation"
    elif drift=="projection":state["projections"][0]["payload"]["changed"]=True
    else: state["neighbors"][0]["changed"]=True
    with pytest.raises(ValueError,match="planned_state_drifted"):
        repair.apply_plan(cur,plan,repair.digest(plan))
    assert not any(q.startswith("UPDATE") for q in cur.statements)


@pytest.mark.parametrize("conflict",["tenant","target_source","sibling","invoice","source_invoice","trigger","dual_reference"])
def test_identity_and_dependency_conflicts_hold(setup,conflict):
    state,cur,plan=setup
    if conflict=="tenant":state["orders"][1]["tenant_id"]="foreign"
    if conflict=="target_source":state["vehicles"][1]["ets_external_id"]="wrong"
    if conflict=="sibling":state["orders"][1]["vehicle_id"]="old"
    if conflict=="invoice":state["invoices"].append(copy.deepcopy(state["invoices"][0]))
    if conflict=="source_invoice":state["invoices"][0]["ets_source_evidence"]["observations"][0]["evidence"]["invoice_id"]="wrong"
    if conflict=="trigger":state["triggers"].clear()
    if conflict=="dual_reference":state["dependencies"]["appointments"]=[{"id":"unexpected"}]
    with pytest.raises(ValueError):repair.apply_plan(cur,plan,repair.digest(plan))
    assert not any(q.startswith("UPDATE") for q in cur.statements)


def test_target_without_audit_cannot_be_treated_as_success(setup):
    state,cur,plan=setup
    state["orders"][0]["vehicle_id"]="target"
    state["projections"][0]["vehicle_id"]=state["projections"][0]["payload"]["vehicle_id"]="target"
    with pytest.raises(ValueError,match="target_state_without_matching_audit"):
        repair.apply_plan(cur,plan,repair.digest(plan))


def test_source_capture_tamper_rejected(tmp_path):
    path=tmp_path/"capture.json";path.write_text("[]")
    with pytest.raises(ValueError,match="source_capture_changed"):repair.source_proof(path)


def test_audited_rollback_is_bounded_and_idempotent(setup):
    state,cur,plan=setup
    token=repair.digest(plan)
    protected=copy.deepcopy(state["dependencies"])
    assert repair.apply_plan(cur,plan,token)=="applied"
    assert repair.rollback_plan(cur,plan,token)=="rolled_back"
    assert state["orders"][0]["vehicle_id"]=="old"
    assert state["dependencies"]==protected
    assert len(state["history"])==2
    assert repair.rollback_plan(cur,plan,token)=="already_rolled_back"
    assert sum(q.startswith("UPDATE") for q in cur.statements)==2


def test_rollback_rejects_changed_financial_state(setup):
    state,cur,plan=setup
    token=repair.digest(plan)
    repair.apply_plan(cur,plan,token)
    state["dependencies"]["payments"][0]["amount"]=101
    with pytest.raises(ValueError,match="rollback_target_state_drifted"):
        repair.rollback_plan(cur,plan,token)
    assert sum(q.startswith("UPDATE") for q in cur.statements)==1


def test_projection_side_effect_is_rejected_before_audit(setup,monkeypatch):
    state,cur,plan=setup
    original=cur.execute
    def unexpected(query,params):
        original(query,params)
        if query.startswith("UPDATE"):
            state["projections"][0]["payload"]["invoice_total"]=999
    monkeypatch.setattr(cur,"execute",unexpected)
    with pytest.raises(ValueError,match="unexpected_projection_mutation"):
        repair.apply_plan(cur,plan,repair.digest(plan))
    assert state["history"]==[]


def test_main_rolls_back_and_never_commits_on_apply_exception(setup,monkeypatch,tmp_path):
    state,cur,plan=setup
    file=tmp_path/"plan.json";file.write_text(json.dumps(plan))
    class Connection:
        def __init__(self):self.commits=0;self.rollbacks=0;self.closed=False
        def set_session(self,**kwargs):assert kwargs==dict(isolation_level="SERIALIZABLE",readonly=False)
        def cursor(self):return self
        def __enter__(self):return self
        def __exit__(self,*_):return None
        def execute(self,*_):pass
        def commit(self):self.commits+=1
        def rollback(self):self.rollbacks+=1
        def close(self):self.closed=True
    connection=Connection()
    monkeypatch.setenv("DATABASE_URL","postgresql://unused")
    monkeypatch.setattr(repair.psycopg2,"connect",lambda _:connection)
    def failure(*_):raise ValueError("protected_rows_changed")
    monkeypatch.setattr(repair,"apply_plan",failure)
    monkeypatch.setattr("sys.argv",["repair","apply","--plan",str(file),"--expected-sha256",repair.digest(plan)])
    with pytest.raises(ValueError,match="protected_rows_changed"):repair.main()
    assert connection.commits==0 and connection.rollbacks==1 and connection.closed
