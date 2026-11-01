"""Finite-manifest repair guards; local fixtures, no provider or production I/O."""
import copy
import importlib.util
import json
import sys
from pathlib import Path

import pytest

SCRIPTS=Path(__file__).parents[1]/"scripts"
sys.path.insert(0,str(SCRIPTS))
import repair_ets_legacy_vehicle_links as repair
sys.path.remove(str(SCRIPTS))


def fixture():
    tenant="tenant"
    fact=dict(service_id="100",service_internal_id="internal",invoice_service_id="internal",invoice_id="sourceinv",invoice_number="300",ets_shop_id="shop")
    change=dict(order_id="one",order_number="ETS-100-200",old_vehicle_id="old",target_vehicle_id="target")
    group=dict(job="ETS-100-200",customer_id="customer",source_customer_id="200",source_vehicle_id="sourcevehicle",target_vehicle_id="target",operation_count=2,
        members=[dict(id="one",order_number="ETS-100-200",vehicle_id="old"),dict(id="two",order_number="ETS-100-200-2",vehicle_id="target")],changes=[change],invoice_ids=["invoice"],active_invoice_id="invoice",active_invoice_owner_id="two",source_invoice_identity=fact)
    manifest=dict(version=1,tenant_id=tenant,source_capture_sha256=repair.CAPTURE_SHA,groups=[group],components=[dict(id="component-001",jobs=[group["job"]])])
    orders=[dict(id=m["id"],tenant_id=tenant,source=repair.SOURCE,deleted_at=None,customer_id="customer",vehicle_id=m["vehicle_id"],order_number=m["order_number"],updated_at="before") for m in group["members"]]
    vehicles=[dict(id=i,tenant_id=tenant,source=repair.SOURCE,deleted_at=None,customer_id="customer",ets_external_id="sourcevehicle" if i=="target" else None,unit_number="X",vin=None) for i in ["old","target"]]
    identity=[dict(order_id="one",vehicle_id=v,payload={"vehicle_make":v},search_document=v,search_compact=v) for v in ["old","target"]]
    projections=[dict(repair_order_id=o["id"],vehicle_id=o["vehicle_id"],payload=dict(vehicle_id=o["vehicle_id"],updated_at="before",vehicle_make=o["vehicle_id"]),search_document=o["vehicle_id"],search_compact=o["vehicle_id"],refreshed_at="before") for o in orders]
    invoice=dict(id="invoice",tenant_id=tenant,repair_order_id="two",source=repair.SOURCE,deleted_at=None,status="sent",ets_source_evidence={"observations":[{"evidence":fact,"sha256":repair.digest(fact)}]})
    state=dict(orders=orders,vehicles=vehicles,invoices=[invoice],customers=[dict(id="customer",tenant_id=tenant,source=repair.SOURCE,deleted_at=None,ets_external_id="200")],expected_identity=identity,metadata={},
        dependencies={"repair_order_read_models":projections,"repair_order_history_events":[],"fleet_board_read_models":[],"payments":[dict(id="pay",tenant_id=tenant,amount=100)],"invoice_settlements":[dict(id="settlement",tenant_id=tenant,version=2)],"vehicle_source_aliases":[]})
    return manifest,state


class Cursor:
    def __init__(self,state):self.state=state;self.statements=[];self.tick=0
    def execute(self,query,params):
        self.statements.append(query)
        if query.startswith("UPDATE"):
            new,oid,tenant,old,source=params
            order=next(o for o in self.state["orders"] if o["id"]==oid)
            assert order["vehicle_id"]==old and order["tenant_id"]==tenant and order["source"]==source
            self.tick+=1;stamp=str(self.tick)
            order["vehicle_id"]=new;order["updated_at"]=stamp
            p=next(p for p in self.state["dependencies"]["repair_order_read_models"] if p["repair_order_id"]==oid)
            p["vehicle_id"]=p["payload"]["vehicle_id"]=new;p["payload"]["updated_at"]=stamp;p["refreshed_at"]=stamp
            expected=next(i for i in self.state["expected_identity"] if i["order_id"]==oid and i["vehicle_id"]==new)
            p["payload"].update(expected["payload"]);p["search_document"]=expected["search_document"];p["search_compact"]=expected["search_compact"]
            self.rowcount=1
        if query.startswith("INSERT"):
            self.state["dependencies"]["repair_order_history_events"].append(dict(id=params[0],event_type=params[3],detail=params[5]))


@pytest.fixture
def setup(monkeypatch):
    manifest,state=fixture();cur=Cursor(state)
    def collect(*_,**__):
        out=copy.deepcopy(state)
        out["orders"].sort(key=lambda r:json.dumps(r,sort_keys=True))
        for rs in out["dependencies"].values():rs.sort(key=lambda r:json.dumps(r,sort_keys=True))
        return out
    monkeypatch.setattr(repair,"collect",collect)
    monkeypatch.setattr(repair,"trusted_shop",lambda _:"shop")
    token=repair.digest(manifest);plan=repair.make_plan(cur,manifest,token,"component-001",{})
    return manifest,state,cur,token,plan,repair.digest(plan)


def test_nonowner_relink_preserves_invoice_and_supports_both_noops(setup):
    manifest,state,cur,token,plan,psha=setup
    before_invoice=copy.deepcopy(state["invoices"])
    assert repair.mutate(cur,manifest,token,plan,psha,{})=="applied"
    assert state["invoices"]==before_invoice
    assert state["orders"][0]["vehicle_id"]=="target"
    assert repair.mutate(cur,manifest,token,plan,psha,{})=="already_applied"
    assert repair.mutate(cur,manifest,token,plan,psha,{},True)=="rolled_back"
    assert repair.mutate(cur,manifest,token,plan,psha,{},True)=="already_rolled_back"
    assert sum(q.startswith("UPDATE") for q in cur.statements)==2
    assert len(state["dependencies"]["repair_order_history_events"])==2


@pytest.mark.parametrize("drift",["payment","settlement","alias","source","neighbor_projection"])
def test_drift_aborts_before_writes(setup,drift):
    manifest,state,cur,token,plan,psha=setup
    if drift=="payment":state["dependencies"]["payments"][0]["amount"]+=1
    if drift=="settlement":state["dependencies"]["invoice_settlements"][0]["version"]+=1
    if drift=="alias":state["dependencies"]["vehicle_source_aliases"].append({"id":"new"})
    if drift=="source":state["invoices"][0]["ets_source_evidence"]["latest_confirmation"]="fresh"
    if drift=="neighbor_projection":state["dependencies"]["repair_order_read_models"][1]["payload"]["unrelated"]="changed"
    with pytest.raises(ValueError,match="planned_state_drifted"):repair.mutate(cur,manifest,token,plan,psha,{})
    assert cur.statements==[]


@pytest.mark.parametrize("conflict",["tenant","source_digest","source_shop","target","fleet","new_member"])
def test_identity_and_new_fleet_conflicts_fail_closed(setup,conflict,monkeypatch):
    manifest,state,cur,token,plan,psha=setup
    if conflict=="tenant":state["orders"][0]["tenant_id"]="other"
    if conflict=="source_digest":state["invoices"][0]["ets_source_evidence"]["observations"][0]["sha256"]="wrong"
    if conflict=="source_shop":monkeypatch.setattr(repair,"trusted_shop",lambda _:"other")
    if conflict=="target":state["vehicles"][1]["ets_external_id"]="different"
    if conflict=="fleet":state["dependencies"]["fleet_board_read_models"].append({"id":"board"})
    if conflict=="new_member":state["orders"].append(dict(state["orders"][1],id="three",order_number="ETS-100-200-3"))
    with pytest.raises(ValueError):repair.mutate(cur,manifest,token,plan,psha,{})
    assert cur.statements==[]


def test_projection_money_change_rolls_back_before_audit(setup,monkeypatch):
    manifest,state,cur,token,plan,psha=setup
    execute=cur.execute
    def extra(query,params):
        execute(query,params)
        if query.startswith("UPDATE"):state["dependencies"]["repair_order_read_models"][0]["payload"]["total_cost"]=999
    monkeypatch.setattr(cur,"execute",extra)
    with pytest.raises(ValueError,match="protected_or_unexpected_projection_mutation"):repair.mutate(cur,manifest,token,plan,psha,{})
    assert state["dependencies"]["repair_order_history_events"]==[]


def test_manifest_tamper_and_wrong_component_plan_rejected(setup):
    manifest,state,cur,token,plan,psha=setup
    manifest["groups"][0]["changes"][0]["target_vehicle_id"]="other"
    with pytest.raises(ValueError,match="reviewed_digest_mismatch"):repair.mutate(cur,manifest,token,plan,psha,{})
    assert cur.statements==[]


def test_missing_audit_is_not_idempotent_success(setup):
    manifest,state,cur,token,plan,psha=setup
    repair.mutate(cur,manifest,token,plan,psha,{})
    state["dependencies"]["repair_order_history_events"].clear()
    with pytest.raises(ValueError):repair.mutate(cur,manifest,token,plan,psha,{})
    assert sum(q.startswith("UPDATE") for q in cur.statements)==1


def test_source_capture_tamper_before_manifest_construction():
    with pytest.raises(ValueError,match="source_capture_changed"):repair.build_manifest({}, {}, b"[]")


def test_main_rolls_back_exception_and_does_not_commit(setup,monkeypatch,tmp_path):
    manifest,state,cur,token,plan,psha=setup
    mf=tmp_path/"manifest";pf=tmp_path/"plan";mf.write_text(json.dumps(manifest));pf.write_text(json.dumps(plan))
    class Connection:
        commits=0;rollbacks=0;closed=False
        def set_session(self,**kwargs):assert kwargs==dict(isolation_level="SERIALIZABLE",readonly=False)
        def cursor(self):return self
        def __enter__(self):return self
        def __exit__(self,*_):pass
        def execute(self,*_):pass
        def commit(self):self.commits+=1
        def rollback(self):self.rollbacks+=1
        def close(self):self.closed=True
    conn=Connection()
    monkeypatch.setenv("DATABASE_URL","postgresql://unused")
    monkeypatch.setattr(repair.psycopg2,"connect",lambda _:conn)
    monkeypatch.setattr(repair,"metadata",lambda _: {})
    def fail(*_):raise ValueError("planned_state_drifted")
    monkeypatch.setattr(repair,"mutate",fail)
    monkeypatch.setattr(sys,"argv",["repair","apply","--manifest",str(mf),"--manifest-sha256",token,"--plan",str(pf),"--plan-sha256",psha])
    with pytest.raises(ValueError,match="planned_state_drifted"):repair.main()
    assert conn.commits==0 and conn.rollbacks==1 and conn.closed


def test_second_active_invoice_rejected_even_at_plan_time(setup):
    manifest,state,cur,token,plan,psha=setup
    extra=copy.deepcopy(state["invoices"][0]);extra["id"]="copy";extra["status"]="cancelled"
    state["invoices"].append(extra)
    manifest["groups"][0]["invoice_ids"].append("copy");manifest["groups"][0]["invoice_ids"].sort()
    token=repair.digest(manifest)
    repair.make_plan(cur,manifest,token,"component-001",{})
    extra["status"]="paid"
    with pytest.raises(ValueError,match="active_invoice_set_changed"):
        repair.make_plan(cur,manifest,token,"component-001",{})
    assert cur.statements==[]
