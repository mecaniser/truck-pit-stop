#!/usr/bin/env python3
"""Finite, source-reviewed historical ETS vehicle-link repair; no money writes.

Build a private manifest from the read-only census and preserved source capture,
review its digest, then plan/rehearse/apply one connected vehicle component at a
time. No dynamically discovered additions, retry loop, merge or importer run.
"""
import argparse
import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
from uuid import UUID, uuid4

import psycopg2
from psycopg2 import sql

from repair_ets_0662_vehicle_link import CAPTURE_SHA, digest, require, private_write

SOURCE = "easy_truck_shop_import"
EVENT = "ets_legacy_vehicle_link_repaired"
ROLLBACK = "ets_legacy_vehicle_link_rollback"
EXCLUDED_JOB = "ETS-0662-91612"
SCOPE_COLUMNS = {"repair_order_id", "parent_repair_order_id", "invoice_id", "vehicle_id", "canonical_vehicle_id", "duplicate_vehicle_id"}


def build_manifest(census, classification, raw):
    require(hashlib.sha256(raw).hexdigest() == CAPTURE_SHA, "source_capture_changed")
    source = {}
    for customer in json.loads(raw):
        for vehicle in customer.get("vehicles", []):
            for row in vehicle.get("serviceHistory", []):
                service = str(row[0]).strip("# ") if row else ""
                if service.isdigit():
                    source.setdefault(service, []).append((str(customer["id"]), str(vehicle["vehicleId"]), row))
    orders = {r["id"]: r for r in census["orders"]}
    vehicles = {v["id"]: v for v in census["vehicles"]}
    customers = {c["id"]: c for c in census["customers"]}
    groups = []
    for selected in classification["groups"]:
        if selected["holds"]:
            continue
        job = selected["job"]
        require(job != EXCLUDED_JOB, "prior_repair_excluded")
        _, service, customer_external = job.split("-")
        facts = source.get(service, [])
        bindings = {(c, v) for c, v, _ in facts}
        require(len(bindings) == 1, "source_service_not_exclusive")
        customer_id, external_vehicle = next(iter(bindings))
        require(customer_id == customer_external, "source_customer_mismatch")
        members = [r for r in orders.values() if r["order_number"] == job or r["order_number"].startswith(job+"-")]
        require(len(facts) == len(members) == selected["order_count"], "source_operation_count_mismatch")
        local_customers = {r["customer_id"] for r in members}
        require(len(local_customers) == 1, "customer_conflict")
        local_customer = next(iter(local_customers))
        customer = customers[local_customer]
        require(customer["source"] == SOURCE and customer["ets_external_id"] == customer_external and customer["deleted_at"] is None, "customer_source_unproven")
        targets = [v for v in vehicles.values() if v["source"] == SOURCE and v["ets_external_id"] == external_vehicle and v["deleted_at"] is None]
        require(len(targets) == 1 and targets[0]["customer_id"] == local_customer, "target_identity_unproven")
        target = targets[0]
        changes = []
        for row in members:
            old = vehicles[row["vehicle_id"]]
            if old["id"] == target["id"]:
                continue
            require(old["source"] == SOURCE and old["ets_external_id"] is None and old["deleted_at"] is None and old["customer_id"] == local_customer, "legacy_identity_unproven")
            require(old["unit_number"] and old["unit_number"] == target["unit_number"], "unit_conflict")
            require(not old["vin_sha256"] or not target["vin_sha256"] or old["vin_sha256"] == target["vin_sha256"], "vin_conflict")
            changes.append(dict(order_id=row["id"], order_number=row["order_number"], old_vehicle_id=old["id"], target_vehicle_id=target["id"]))
        require(changes and {(x["order_id"],x["old_vehicle_id"],x["target_vehicle_id"]) for x in changes} == {(x["order_id"],x["old_vehicle_id"],x["target_vehicle_id"]) for x in selected["changes"]}, "candidate_manifest_changed")
        invoices = [i for i in census["invoices"] if i["repair_order_id"] in {r["id"] for r in members}]
        active = [i for i in invoices if i["status"] != "cancelled" and i["deleted_at"] is None]
        require(len(active) == 1 and active[0]["source"] == SOURCE, "active_invoice_identity_unproven")
        inv = active[0]; identity = inv["source_identity"]
        require(identity.get("service_id") == service and identity.get("invoice_service_id") == identity.get("service_internal_id") and identity.get("service_internal_id") and identity.get("invoice_id") and identity.get("ets_shop_id") and inv["invoice_number"] == "ETSINV-"+identity["invoice_number"], "source_invoice_identity_unproven")
        groups.append(dict(job=job, customer_id=local_customer, source_customer_id=customer_external, source_vehicle_id=external_vehicle,
            target_vehicle_id=target["id"], source_rows_sha256=digest(facts), operation_count=len(facts),
            members=sorted([dict(id=r["id"], order_number=r["order_number"], vehicle_id=r["vehicle_id"]) for r in members],key=lambda r:r["id"]),
            changes=sorted(changes,key=lambda r:r["order_id"]), invoice_ids=sorted(i["id"] for i in invoices),
            active_invoice_id=inv["id"], active_invoice_owner_id=inv["repair_order_id"], source_invoice_identity={k:identity[k] for k in ["service_id","service_internal_id","invoice_service_id","invoice_id","invoice_number","ets_shop_id"]},
            existing_review_reasons=selected["current_review_reasons"]))
    groups.sort(key=lambda g:g["job"])
    require(len(groups) == 243 and sum(len(g["changes"]) for g in groups) == 243, "reviewed_candidate_count_changed")
    parent = {}
    def root(v):
        parent.setdefault(v,v)
        if parent[v] != v: parent[v] = root(parent[v])
        return parent[v]
    for group in groups:
        for change in group["changes"]:
            parent[root(change["old_vehicle_id"])] = root(change["target_vehicle_id"])
    components = {}
    for group in groups:
        components.setdefault(root(group["target_vehicle_id"]), []).append(group)
    ordered = sorted(components.values(),key=lambda gs:gs[0]["job"])
    require(len(ordered) == 193 and max(map(len,ordered)) <= 5, "reviewed_component_count_changed")
    return dict(version=1, tenant_id=str(UUID(census["tenant_id"])), source_capture_sha256=CAPTURE_SHA,
        excluded_job=EXCLUDED_JOB, groups=groups, components=[dict(id=f"component-{n+1:03}", jobs=[g["job"] for g in gs]) for n,gs in enumerate(ordered)])


def trusted_shop(tenant):
    mappings = [json.loads(os.environ.get(key,"{}")) for key in ["ETS_IMPORTED_BILLING_SHOPS","ETS_COMPLETED_OUTCOME_SHOPS"]]
    require(all(isinstance(m,dict) for m in mappings), "shop_mapping_invalid")
    values = {m[tenant] for m in mappings if tenant in m}
    require(len(values) == 1, "shop_mapping_missing_or_conflicting")
    return next(iter(values))


def metadata(cur):
    cur.execute("""SELECT c.table_name,array_agg(c.column_name::text ORDER BY c.column_name)
        FROM information_schema.columns c JOIN information_schema.tables t
        ON t.table_schema=c.table_schema AND t.table_name=c.table_name
        WHERE c.table_schema='public' AND t.table_type='BASE TABLE'
        AND c.column_name=ANY(%s) GROUP BY c.table_name ORDER BY c.table_name""",(sorted(SCOPE_COLUMNS),))
    tables = dict(cur.fetchall())
    cur.execute("SELECT tgname,pg_get_triggerdef(oid) FROM pg_trigger WHERE tgrelid='repair_orders'::regclass AND NOT tgisinternal AND tgenabled='O' ORDER BY tgname")
    triggers = dict(cur.fetchall())
    for name in ["repair_order_read_model_repair_order","fleet_board_read_model_repair_order"]:
        require(name in triggers and "UPDATE" in triggers[name], "required_trigger_unavailable")
    return dict(tables=tables,triggers=triggers)


def rows(cur, table, condition, params, lock=False):
    query = sql.SQL("SELECT to_jsonb(t) FROM {} t WHERE ").format(sql.Identifier(table))+condition
    # Deterministic lock order avoids opposing component repair deadlocks.
    query += sql.SQL(" ORDER BY to_jsonb(t)::text")
    if lock: query += sql.SQL(" FOR UPDATE")
    cur.execute(query,params)
    return sorted((r[0] for r in cur.fetchall()),key=lambda r:json.dumps(r,sort_keys=True))


def component_groups(manifest, component):
    selected = next((c for c in manifest["components"] if c["id"] == component),None)
    require(selected is not None,"unknown_component")
    return [g for g in manifest["groups"] if g["job"] in selected["jobs"]]


def collect(cur, manifest, component, meta, lock=False):
    groups = component_groups(manifest,component)
    tenant = manifest["tenant_id"]
    vids = sorted({x[k] for g in groups for x in g["changes"] for k in ["old_vehicle_id","target_vehicle_id"]})
    # Lock vehicle parents first, then order/invoice parents, then dependencies.
    vehicles = rows(cur,"vehicles",sql.SQL("id=ANY(%s::uuid[]) OR (tenant_id=%s AND source=%s AND ets_external_id=ANY(%s))"),
        (vids,tenant,SOURCE,[g["source_vehicle_id"] for g in groups]),lock)
    orders = rows(cur,"repair_orders",sql.SQL("vehicle_id=ANY(%s::uuid[]) OR (tenant_id=%s AND (regexp_match(order_number,'^(ETS-[0-9]+-[0-9]+)(-[0-9]+)?$'))[1]=ANY(%s))"),
        (vids,tenant,[g["job"] for g in groups]),lock)
    ids = [r["id"] for r in orders]
    planned_ids = [m["id"] for g in groups for m in g["members"]]
    children = rows(cur,"repair_orders",sql.SQL("parent_repair_order_id=ANY(%s::uuid[])"),(planned_ids,),lock)
    require(not children,"child_order_requires_review")
    invoices = rows(cur,"invoices",sql.SQL("repair_order_id=ANY(%s::uuid[])"),(ids,),lock)
    invoice_ids = [r["id"] for r in invoices]
    # One bounded UNION round trip captures each scope relation once, including
    # empty sets, neighboring orders, telemetry, memberships and immutable logs.
    queries,params = [],[]
    for table,cols in meta["tables"].items():
        if table in {"repair_orders","invoices"}: continue
        clauses=[]
        for col in cols:
            values = invoice_ids if col == "invoice_id" else vids if col.endswith("vehicle_id") else ids
            clauses.append(sql.SQL("{}=ANY(%s::uuid[])").format(sql.Identifier(col)));params.append(values)
        q=sql.SQL("SELECT to_jsonb(t) AS row FROM {} t WHERE ").format(sql.Identifier(table))+sql.SQL(" OR ").join(clauses)+sql.SQL(" ORDER BY to_jsonb(t)::text")
        if lock:q+=sql.SQL(" FOR UPDATE")
        queries.append(sql.SQL("SELECT {} AS name,coalesce(jsonb_agg(s.row),'[]'::jsonb) AS records FROM (").format(sql.Literal(table))+q+sql.SQL(") s"))
    cur.execute(sql.SQL(" UNION ALL ").join(queries),params)
    dependencies={table:sorted(rs,key=lambda r:json.dumps(r,sort_keys=True)) for table,rs in cur.fetchall()}
    customers=rows(cur,"customers",sql.SQL("id=ANY(%s::uuid[])"),(sorted({g["customer_id"] for g in groups}),),lock)
    changed_ids=[c["order_id"] for g in groups for c in g["changes"]]
    cur.execute("""SELECT r.id::text,v.id::text,jsonb_build_object(
        'vehicle_make',coalesce(v.make,''),'vehicle_model',coalesce(v.model,''),
        'vehicle_year',v.year,'vehicle_unit_number',v.unit_number,'vehicle_vin',v.vin),
        concat_ws(' ',r.order_number,r.description,c.first_name,c.last_name,c.company_name,
          c.email,c.phone,c.usdot_number,c.mc_number,c.fleet_enabled,v.vin,v.unit_number,v.make,v.model),
        regexp_replace(concat_ws(' ',r.order_number,v.vin,v.unit_number),'[^[:alnum:]]','','g')
        FROM repair_orders r JOIN customers c ON c.id=r.customer_id
        JOIN vehicles v ON v.customer_id=r.customer_id AND v.tenant_id=r.tenant_id
        WHERE r.id=ANY(%s::uuid[]) AND v.id=ANY(%s::uuid[]) ORDER BY r.id,v.id""",(changed_ids,vids))
    expected_identity=[dict(order_id=oid,vehicle_id=vid,payload=payload,search_document=doc,search_compact=compact)
        for oid,vid,payload,doc,compact in cur.fetchall()]
    return dict(vehicles=vehicles,orders=orders,invoices=invoices,customers=customers,dependencies=dependencies,metadata=meta,expected_identity=expected_identity)


def validate(state,manifest,component,after=False):
    tenant=manifest["tenant_id"];groups=component_groups(manifest,component)
    vehicles={v["id"]:v for v in state["vehicles"]};orders={r["id"]:r for r in state["orders"]};customers={c["id"]:c for c in state["customers"]}
    require(all(r["tenant_id"]==tenant for r in state["orders"]+state["vehicles"]+state["invoices"]+state["customers"]),"scope_tenant_conflict")
    require(not state["dependencies"].get("fleet_board_read_models"),"fleet_projection_requires_review")
    expected_vids={x[k] for g in groups for x in g["changes"] for k in ["old_vehicle_id","target_vehicle_id"]}
    require(set(vehicles)==expected_vids,"vehicle_scope_changed")
    planned_ids={m["id"] for g in groups for m in g["members"]}
    for table in ["appointments","fleet_incidents","fleet_inspections"]:
        require(not any(r.get("repair_order_id") in planned_ids for r in state["dependencies"].get(table,[])),"dual_reference_requires_review")
    require(not any(r.get("parent_repair_order_id") in planned_ids for r in state["orders"]),"child_order_requires_review")
    projections={r["repair_order_id"]:r for r in state["dependencies"].get("repair_order_read_models",[])}
    require(set(projections)==set(orders),"projection_scope_changed")
    for g in groups:
        customer=customers[g["customer_id"]]
        require(customer["source"]==SOURCE and customer["deleted_at"] is None and customer["ets_external_id"]==g["source_customer_id"],"customer_identity_changed")
        target=vehicles[g["target_vehicle_id"]]
        require(target["source"]==SOURCE and target["deleted_at"] is None and target["ets_external_id"]==g["source_vehicle_id"] and target["customer_id"]==g["customer_id"],"target_identity_changed")
        require(sum(v["ets_external_id"]==g["source_vehicle_id"] and v["deleted_at"] is None for v in vehicles.values())==1,"target_identity_ambiguous")
        actual=[r for r in state["orders"] if r["order_number"]==g["job"] or r["order_number"].startswith(g["job"]+"-")]
        require({r["id"] for r in actual}=={m["id"] for m in g["members"]} and len(actual)==g["operation_count"],"group_members_changed")
        changes={c["order_id"]:c for c in g["changes"]}
        for member in g["members"]:
            r=orders[member["id"]]
            expected=g["target_vehicle_id"] if after and r["id"] in changes else member["vehicle_id"]
            require(r["order_number"]==member["order_number"] and r["customer_id"]==g["customer_id"] and r["source"]==SOURCE and r["deleted_at"] is None and r["vehicle_id"]==expected,"order_identity_changed")
            p=projections[r["id"]]
            require(p["vehicle_id"]==r["vehicle_id"] and p["payload"]["vehicle_id"]==r["vehicle_id"],"projection_identity_changed")
        for c in g["changes"]:
            old=vehicles[c["old_vehicle_id"]]
            require(old["source"]==SOURCE and old["deleted_at"] is None and old["ets_external_id"] is None and old["customer_id"]==g["customer_id"] and old["unit_number"] and old["unit_number"]==target["unit_number"],"legacy_identity_changed")
            require(not old["vin"] or not target["vin"] or old["vin"].strip().upper()==target["vin"].strip().upper(),"vin_conflict")
        invoices=[i for i in state["invoices"] if i["repair_order_id"] in {m["id"] for m in g["members"]}]
        require(sorted(i["id"] for i in invoices)==g["invoice_ids"],"invoice_set_changed")
        require([i["id"] for i in invoices if i["status"]!="cancelled" and i["deleted_at"] is None]==[g["active_invoice_id"]],"active_invoice_set_changed")
        inv=next(i for i in invoices if i["id"]==g["active_invoice_id"])
        require(inv["repair_order_id"]==g["active_invoice_owner_id"] and inv["source"]==SOURCE and inv["deleted_at"] is None and inv["status"]!="cancelled","active_invoice_changed")
        observations=inv["ets_source_evidence"]["observations"]
        require(observations,"source_evidence_missing")
        facts=observations[-1]["evidence"]
        require(observations[-1]["sha256"]==digest(facts),"source_digest_invalid")
        require({k:facts.get(k) for k in g["source_invoice_identity"]}==g["source_invoice_identity"] and facts.get("ets_shop_id")==trusted_shop(tenant),"source_invoice_identity_changed")
    for table,rs in state["dependencies"].items():
        require(all(r.get("tenant_id",tenant)==tenant for r in rs),"dependent_tenant_conflict")


def protected(state):
    result={k:digest(v) for k,v in state.items() if k!="dependencies"}
    result.update({"table:"+table:digest(rs) for table,rs in state["dependencies"].items() if table!="repair_order_history_events"})
    return result


def history(state):return state["dependencies"].get("repair_order_history_events",[])


def make_plan(cur,manifest,manifest_sha,component,meta):
    require(digest(manifest)==manifest_sha and manifest["source_capture_sha256"]==CAPTURE_SHA,"manifest_digest_mismatch")
    state=collect(cur,manifest,component,meta)
    validate(state,manifest,component)
    require(not any(r["event_type"] in {EVENT,ROLLBACK} for r in history(state)),"existing_component_audit_requires_review")
    return dict(version=1,manifest_sha256=manifest_sha,component=component,before=protected(state),history_sha256=digest(history(state)))


def verify_transition(before,after,manifest,component,reverse=False):
    changes={c["order_id"]:c for g in component_groups(manifest,component) for c in g["changes"]}
    actual_orders={r["id"]:r for r in after["orders"]}
    expected=copy.deepcopy(before)
    for row in expected["orders"]:
        if row["id"] in changes:
            row["vehicle_id"]=changes[row["id"]]["old_vehicle_id" if reverse else "target_vehicle_id"]
            row["updated_at"]=actual_orders[row["id"]]["updated_at"]
    actual_projections={r["repair_order_id"]:r for r in after["dependencies"]["repair_order_read_models"]}
    for projection in expected["dependencies"]["repair_order_read_models"]:
        oid=projection["repair_order_id"]
        if oid in changes:
            projection["vehicle_id"]=projection["payload"]["vehicle_id"]=changes[oid]["old_vehicle_id" if reverse else "target_vehicle_id"]
            projection["payload"]["updated_at"]=actual_orders[oid]["updated_at"]
            identity=next(r for r in before["expected_identity"] if r["order_id"]==oid and r["vehicle_id"]==projection["vehicle_id"])
            projection["payload"].update(identity["payload"])
            projection["search_document"]=identity["search_document"]
            projection["search_compact"]=identity["search_compact"]
            projection["refreshed_at"]=actual_projections[oid]["refreshed_at"]
    # Canonical JSON sorting may change after a permitted field change.
    expected["orders"].sort(key=lambda r:json.dumps(r,sort_keys=True))
    expected["dependencies"]["repair_order_read_models"].sort(key=lambda r:json.dumps(r,sort_keys=True))
    require(expected==after,"protected_or_unexpected_projection_mutation")


def mutate(cur,manifest,manifest_sha,plan,plan_sha,meta,reverse=False):
    require(digest(manifest)==manifest_sha==plan["manifest_sha256"] and digest(plan)==plan_sha,"reviewed_digest_mismatch")
    component=plan["component"]
    state=collect(cur,manifest,component,meta,lock=True)
    event=ROLLBACK if reverse else EVENT
    audits=[r for r in history(state) if r["event_type"]==event and json.loads(r["detail"]).get("plan_sha256")==plan_sha]
    if audits:
        require(len(audits)==1,"duplicate_component_audit")
        receipt=json.loads(audits[0]["detail"])
        validate(state,manifest,component,after=not reverse)
        require(protected(state)==receipt["after"] and digest([r for r in history(state) if r["id"]!=audits[0]["id"]])==receipt["previous_history_sha256"],"audited_state_drifted")
        return "already_rolled_back" if reverse else "already_applied"
    validate(state,manifest,component,after=reverse)
    if reverse:
        forward=[r for r in history(state) if r["event_type"]==EVENT and json.loads(r["detail"]).get("plan_sha256")==plan_sha]
        require(len(forward)==1,"forward_audit_missing")
        receipt=json.loads(forward[0]["detail"])
        require(protected(state)==receipt["after"] and digest([r for r in history(state) if r["id"]!=forward[0]["id"]])==plan["history_sha256"],"rollback_state_drifted")
    else:
        require(protected(state)==plan["before"] and digest(history(state))==plan["history_sha256"],"planned_state_drifted")
    changes=sorted([c for g in component_groups(manifest,component) for c in g["changes"]],key=lambda c:c["order_id"])
    for c in changes:
        old,new=(c["target_vehicle_id"],c["old_vehicle_id"]) if reverse else (c["old_vehicle_id"],c["target_vehicle_id"])
        cur.execute("UPDATE repair_orders SET vehicle_id=%s,updated_at=now() WHERE id=%s AND tenant_id=%s AND vehicle_id=%s AND source=%s AND deleted_at IS NULL",(new,c["order_id"],manifest["tenant_id"],old,SOURCE))
        require(cur.rowcount==1,"update_cardinality_changed")
    after=collect(cur,manifest,component,meta,lock=True)
    validate(after,manifest,component,after=not reverse)
    verify_transition(state,after,manifest,component,reverse)
    receipt=dict(manifest_sha256=manifest_sha,plan_sha256=plan_sha,component=component,source_capture_sha256=CAPTURE_SHA,changes=changes,before=protected(state),after=protected(after),previous_history_sha256=digest(history(state)))
    # One durable component audit anchored to its first corrected RO; its detail
    # pins every changed row. No arbitrary staff identity is impersonated.
    cur.execute("INSERT INTO repair_order_history_events (id,tenant_id,repair_order_id,event_type,label,detail,actor_user_id,actor_name) VALUES (%s,%s,%s,%s,%s,%s,NULL,%s)",
        (str(uuid4()),manifest["tenant_id"],changes[0]["order_id"],event,"Rolled back historical ETS vehicle links" if reverse else "Corrected historical ETS vehicle links",json.dumps(receipt,sort_keys=True),"Owner-authorized ETS repair"))
    return "rolled_back" if reverse else "applied"


def main():
    parser=argparse.ArgumentParser(description=__doc__);commands=parser.add_subparsers(dest="command",required=True)
    build=commands.add_parser("build-manifest")
    for name in ["census","classification","capture","out"]:build.add_argument("--"+name,required=True)
    for action in ["plan","rehearse","apply","rollback"]:
        cmd=commands.add_parser(action);cmd.add_argument("--manifest",required=True);cmd.add_argument("--manifest-sha256",required=True)
        if action=="plan":cmd.add_argument("--component",required=True);cmd.add_argument("--out",required=True)
        else:cmd.add_argument("--plan",required=True);cmd.add_argument("--plan-sha256",required=True)
    args=parser.parse_args()
    if args.command=="build-manifest":
        manifest=build_manifest(json.loads(Path(args.census).read_text()),json.loads(Path(args.classification).read_text()),Path(args.capture).read_bytes())
        private_write(args.out,manifest);print(json.dumps({"manifest_sha256":digest(manifest),"groups":len(manifest["groups"]),"components":len(manifest["components"])}));return
    manifest=json.loads(Path(args.manifest).read_text())
    conn=psycopg2.connect(os.environ["DATABASE_URL"].replace("postgresql+asyncpg://","postgresql://"))
    try:
        conn.set_session(isolation_level="SERIALIZABLE",readonly=args.command=="plan")
        with conn.cursor() as cur:
            cur.execute("SET LOCAL lock_timeout='5s'; SET LOCAL statement_timeout='45s'")
            meta=metadata(cur)
            if args.command=="plan":
                plan=make_plan(cur,manifest,args.manifest_sha256,args.component,meta);private_write(args.out,plan);conn.rollback()
                print(json.dumps({"result":"read_only_plan","component":args.component,"plan_sha256":digest(plan)}))
            else:
                plan=json.loads(Path(args.plan).read_text())
                if args.command=="rehearse":
                    results=[mutate(cur,manifest,args.manifest_sha256,plan,args.plan_sha256,meta),mutate(cur,manifest,args.manifest_sha256,plan,args.plan_sha256,meta),mutate(cur,manifest,args.manifest_sha256,plan,args.plan_sha256,meta,True),mutate(cur,manifest,args.manifest_sha256,plan,args.plan_sha256,meta,True)]
                    conn.rollback();print(json.dumps({"result":"rehearsed_and_rolled_back","sequence":results,"component":plan["component"]}))
                else:
                    result=mutate(cur,manifest,args.manifest_sha256,plan,args.plan_sha256,meta,args.command=="rollback")
                    conn.commit();print(json.dumps({"result":result,"component":plan["component"]}))
    except Exception:
        conn.rollback();raise
    finally:conn.close()


if __name__=="__main__":main()
