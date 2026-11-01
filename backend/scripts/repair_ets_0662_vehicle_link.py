#!/usr/bin/env python3
"""One-job ETS historical association repair. Default is read-only planning.

Source proof is derived offline from the preserved vehicle-scoped capture. A
reviewed plan binds the exact production before-state. Apply requires its digest;
there is no automatic retry, source refresh, invoice write, or vehicle merge.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
from uuid import UUID, uuid4

import psycopg2
from psycopg2 import sql

SOURCE = "easy_truck_shop_import"
JOB = "ETS-0662-91612"
EVENT = "ets_vehicle_link_repaired"
PROOF_SHA = "ed8e6b53b372e57cba12e13fa5114bdbbd06768d4c9e792fff802f96874164a7"
CAPTURE_SHA = "f72882d175406468af2ba22d80c734b11b0ce818062c6a00dfdab86cfc4a404a"


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def source_proof(path):
    raw = Path(path).read_bytes()
    require(hashlib.sha256(raw).hexdigest() == CAPTURE_SHA, "source_capture_changed")
    matches = []
    for customer in json.loads(raw):
        for vehicle in customer.get("vehicles", []):
            for row in vehicle.get("serviceHistory", []):
                if row and str(row[0]).strip("# ") == "0662":
                    matches.append((str(customer["id"]), str(vehicle["vehicleId"]), row))
    require(len(matches) == 4 and all(c == "91612" and v == "106566" for c, v, _ in matches), "source_binding_conflict")
    return {"capture_sha256": CAPTURE_SHA, "customer": "91612", "vehicle": "106566",
            "service": "0662", "operation_count": 4, "rows_sha256": digest(matches)}


def read_rows(cur, table, condition, params, lock=False):
    query = sql.SQL("SELECT to_jsonb(t) FROM {} t WHERE ").format(sql.Identifier(table)) + condition
    if lock:
        query += sql.SQL(" FOR UPDATE")
    cur.execute(query, params)
    return sorted((row[0] for row in cur.fetchall()), key=lambda row: str(row.get("id", row.get("repair_order_id", row.get("invoice_id", "")))))


def collect(cur, tenant, lock=False):
    orders = read_rows(cur, "repair_orders", sql.SQL("tenant_id=%s AND (order_number=%s OR order_number LIKE %s)"), (tenant, JOB, JOB + "-%"), lock)
    require(len(orders) == 4 and {r["order_number"] for r in orders} == {JOB, JOB+"-2", JOB+"-3", JOB+"-4"}, "job_members_changed")
    ids = [r["id"] for r in orders]
    # Retain both vehicles after apply so audited no-op checks cover the old row.
    vehicles = read_rows(cur, "vehicles", sql.SQL("tenant_id=%s AND (id=ANY(%s::uuid[]) OR (source=%s AND ets_external_id='106566') OR (source=%s AND unit_number='457' AND customer_id=%s))"),
        (tenant, list({r["vehicle_id"] for r in orders}), SOURCE, SOURCE, orders[0]["customer_id"]), lock)
    require(len(vehicles) == 2, "vehicle_candidate_set_changed")
    vids = [v["id"] for v in vehicles]
    neighbors = read_rows(cur, "repair_orders", sql.SQL("vehicle_id=ANY(%s::uuid[]) AND NOT(id=ANY(%s::uuid[]))"), (vids, ids), lock)
    children = read_rows(cur, "repair_orders", sql.SQL("parent_repair_order_id=ANY(%s::uuid[])"), (ids,), lock)
    require(not children, "child_orders_require_review")
    require(len(neighbors) == 7, "neighbor_order_set_changed")
    neighbor_projections = read_rows(cur, "repair_order_read_models", sql.SQL("repair_order_id=ANY(%s::uuid[])"), ([r["id"] for r in neighbors],), lock)
    require(len(neighbor_projections) == 7, "neighbor_projection_set_changed")
    fleet_projections = read_rows(cur, "fleet_board_read_models", sql.SQL("vehicle_id=ANY(%s::uuid[])"), (vids,), lock)
    # This historical pair is outside the fleet board. Creating/altering a fleet
    # projection is outside this one-off repair and must abort the transaction.
    require(not fleet_projections, "fleet_projection_requires_review")
    invoices = read_rows(cur, "invoices", sql.SQL("repair_order_id=ANY(%s::uuid[])"), (ids,), lock)
    invoice_ids = [r["id"] for r in invoices]
    cur.execute("SELECT table_name,array_agg(column_name::text ORDER BY column_name) FROM information_schema.columns WHERE table_schema='public' AND column_name IN ('invoice_id','repair_order_id') GROUP BY table_name ORDER BY table_name")
    dependencies = {}
    for table, cols in cur.fetchall():
        if table in {"repair_order_read_models", "repair_order_history_events"}:
            continue
        clauses, params = [], []
        for col in cols:
            clauses.append(sql.SQL("{}=ANY(%s::uuid[])").format(sql.Identifier(col)))
            params.append(invoice_ids if col == "invoice_id" else ids)
        dependencies[table] = read_rows(cur, table, sql.SQL(" OR ").join(clauses), params, lock)
    history = read_rows(cur, "repair_order_history_events", sql.SQL("repair_order_id=ANY(%s::uuid[])"), (ids,), lock)
    projections = read_rows(cur, "repair_order_read_models", sql.SQL("repair_order_id=ANY(%s::uuid[])"), (ids,), lock)
    customers = read_rows(cur, "customers", sql.SQL("id=ANY(%s::uuid[])"), (list({r["customer_id"] for r in orders}),), lock)
    cur.execute("SELECT tgname,pg_get_triggerdef(oid) FROM pg_trigger WHERE tgrelid='repair_orders'::regclass AND NOT tgisinternal AND tgenabled='O'")
    triggers = dict(cur.fetchall())
    return dict(orders=orders, vehicles=vehicles, neighbors=neighbors, invoices=invoices,
        dependencies=dependencies, history=history, projections=projections, customers=customers, triggers=triggers, neighbor_projections=neighbor_projections, fleet_projections=fleet_projections)


def validate(state, tenant):
    orders = state["orders"]
    owner = next(r for r in orders if r["order_number"] == JOB)
    require(all(r["tenant_id"] == tenant and r["source"] == SOURCE and r["deleted_at"] is None and r["customer_id"] == owner["customer_id"] for r in orders), "order_identity_conflict")
    customers = state["customers"]
    require(len(customers) == 1 and customers[0]["tenant_id"] == tenant and customers[0]["ets_external_id"] == "91612" and customers[0]["deleted_at"] is None, "customer_identity_conflict")
    targets = [v for v in state["vehicles"] if v["ets_external_id"] == "106566"]
    require(len(targets) == 1, "target_source_identity_ambiguous")
    target = targets[0]
    require(all(v["tenant_id"] == tenant and v["source"] == SOURCE and v["deleted_at"] is None and v["customer_id"] == owner["customer_id"] and v["unit_number"] == "457" and not v["vin"] for v in state["vehicles"]), "vehicle_identity_conflict")
    old = next(v for v in state["vehicles"] if v["id"] != target["id"])
    require(old["ets_external_id"] is None, "legacy_source_identity_changed")
    require(all(r["vehicle_id"] == target["id"] for r in orders if r["id"] != owner["id"]), "sibling_link_changed")
    require(owner["vehicle_id"] in {old["id"], target["id"]}, "owner_link_changed")
    require(len(state["invoices"]) == 1, "invoice_set_changed")
    invoice = state["invoices"][0]
    require(invoice["tenant_id"] == tenant and invoice["source"] == SOURCE and invoice["deleted_at"] is None and invoice["repair_order_id"] == owner["id"] and invoice["invoice_number"] == "ETSINV-0625", "invoice_identity_conflict")
    facts = invoice["ets_source_evidence"]["observations"][-1]["evidence"]
    require((facts.get("service_id"),facts.get("service_internal_id"),facts.get("invoice_id"),facts.get("invoice_number")) == ("0662","348595","321290","0625"), "source_invoice_identity_changed")
    for name in ("repair_order_read_model_repair_order", "fleet_board_read_model_repair_order"):
        require(name in state["triggers"] and "UPDATE" in state["triggers"][name], "projection_trigger_unavailable")
    require(len(state["projections"]) == 4, "projection_set_changed")
    by_id = {r["id"]:r for r in orders}
    for row in state["projections"]:
        require(row["vehicle_id"] == by_id[row["repair_order_id"]]["vehicle_id"] and row["payload"]["vehicle_id"] == row["vehicle_id"], "projection_identity_mismatch")
    for table, rows in state["dependencies"].items():
        require(all(r.get("tenant_id", tenant) == tenant for r in rows), "dependent_tenant_conflict")
        if table in {"appointments", "fleet_incidents", "fleet_inspections"}:
            require(not rows, "dual_reference_requires_review")
    return owner, old, target


def fingerprints(state):
    return {key:digest(value) for key,value in state.items() if key not in {"history", "projections"}}


def make_plan(cur, tenant, proof):
    require(digest(proof) == PROOF_SHA, "source_proof_invalid")
    state = collect(cur, tenant)
    owner, old, target = validate(state, tenant)
    require(owner["vehicle_id"] == old["id"], "owner_already_relinked")
    return dict(version=1, tenant=tenant, actor=None, proof=proof, owner=owner["id"], old_vehicle=old["id"], target_vehicle=target["id"],
        baseline=fingerprints(state), history_sha256=digest(state["history"]), projection_sha256=digest(state["projections"]))


def copy_json(value):
    return json.loads(json.dumps(value))


def verify_transition(state, after, owner_id, target_id):
    expected_orders = json.loads(json.dumps(state["orders"]))
    updated = next(r for r in after["orders"] if r["id"] == owner_id)
    for row in expected_orders:
        if row["id"] == owner_id:
            row["vehicle_id"],row["updated_at"] = target_id,updated["updated_at"]
    require(expected_orders == after["orders"], "unexpected_order_mutation")
    before_hashes, after_hashes = fingerprints(state), fingerprints(after)
    require(all(before_hashes[k] == after_hashes[k] for k in before_hashes if k != "orders"), "protected_rows_changed")
    require(state["history"] == after["history"], "unexpected_history_mutation")
    require([r for r in state["projections"] if r["repair_order_id"] != owner_id] == [r for r in after["projections"] if r["repair_order_id"] != owner_id], "sibling_projection_changed")
    expected_projection = copy_json(next(r for r in state["projections"] if r["repair_order_id"] == owner_id))
    actual_projection = next(r for r in after["projections"] if r["repair_order_id"] == owner_id)
    expected_projection["vehicle_id"] = target_id
    expected_projection["payload"]["vehicle_id"] = target_id
    if "updated_at" in expected_projection["payload"]:
        expected_projection["payload"]["updated_at"] = updated["updated_at"]
    if "refreshed_at" in expected_projection:
        expected_projection["refreshed_at"] = actual_projection["refreshed_at"]
    require(expected_projection == actual_projection, "unexpected_projection_mutation")
    return before_hashes, after_hashes


def apply_plan(cur, plan, expected_digest):
    require(digest(plan) == expected_digest, "plan_digest_mismatch")
    require(plan["version"] == 1 and digest(plan["proof"]) == PROOF_SHA, "plan_invalid")
    state = collect(cur, plan["tenant"], lock=True)
    owner, old, target = validate(state, plan["tenant"])
    require((owner["id"],old["id"],target["id"]) == (plan["owner"],plan["old_vehicle"],plan["target_vehicle"]), "plan_identity_changed")
    audits = [r for r in state["history"] if r["event_type"] == EVENT]
    if owner["vehicle_id"] == target["id"]:
        matching = [r for r in audits if json.loads(r["detail"]).get("plan_sha256") == expected_digest]
        require(len(matching) == 1, "target_state_without_matching_audit")
        receipt = json.loads(matching[0]["detail"])
        require(fingerprints(state) == receipt["after"] and digest(state["projections"]) == receipt["after_projection_sha256"], "audited_state_drifted")
        require(digest([r for r in state["history"] if r["id"] != matching[0]["id"]]) == plan["history_sha256"], "audit_history_drifted")
        return "already_applied"
    require(not audits, "prior_repair_requires_review")
    require(fingerprints(state) == plan["baseline"] and digest(state["history"]) == plan["history_sha256"] and digest(state["projections"]) == plan["projection_sha256"], "planned_state_drifted")
    require(plan["actor"] is None, "system_repair_actor_required")
    cur.execute("UPDATE repair_orders SET vehicle_id=%s,updated_at=now() WHERE id=%s AND tenant_id=%s AND vehicle_id=%s", (target["id"],owner["id"],plan["tenant"],old["id"]))
    require(cur.rowcount == 1, "update_cardinality_changed")
    after = collect(cur, plan["tenant"], lock=True)
    validate(after, plan["tenant"])
    before_hashes, after_hashes = verify_transition(state, after, owner["id"], target["id"])
    audit = dict(plan_sha256=expected_digest, source_capture_sha256=CAPTURE_SHA, old_vehicle=old["id"], target_vehicle=target["id"], before=before_hashes, after=after_hashes, after_projection_sha256=digest(after["projections"]))
    cur.execute("INSERT INTO repair_order_history_events (id,tenant_id,repair_order_id,event_type,label,detail,entity_id,actor_user_id,actor_name) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)",
        (str(uuid4()),plan["tenant"],owner["id"],EVENT,"Corrected original ETS vehicle association",json.dumps(audit,sort_keys=True),target["id"],plan["actor"],"Owner-authorized ETS repair"))
    return "applied"


def rollback_plan(cur, plan, expected_digest):
    require(digest(plan) == expected_digest and digest(plan["proof"]) == PROOF_SHA and plan["actor"] is None, "plan_digest_mismatch")
    state = collect(cur, plan["tenant"], lock=True)
    owner, old, target = validate(state, plan["tenant"])
    require((owner["id"],old["id"],target["id"]) == (plan["owner"],plan["old_vehicle"],plan["target_vehicle"]), "plan_identity_changed")
    audits = [r for r in state["history"] if r["event_type"] == EVENT and json.loads(r["detail"]).get("plan_sha256") == expected_digest]
    require(len(audits) == 1, "repair_audit_unavailable")
    rollbacks = [r for r in state["history"] if r["event_type"] == "ets_vehicle_link_rollback"]
    if owner["vehicle_id"] == old["id"]:
        require(len(rollbacks) == 1 and json.loads(rollbacks[0]["detail"])["plan_sha256"] == expected_digest, "rollback_audit_unavailable")
        receipt = json.loads(rollbacks[0]["detail"])
        require(fingerprints(state) == receipt["after"] and digest(state["projections"]) == receipt["after_projection_sha256"], "rollback_state_drifted")
        require(digest([r for r in state["history"] if r["id"] not in {audits[0]["id"],rollbacks[0]["id"]}]) == plan["history_sha256"], "audit_history_drifted")
        return "already_rolled_back"
    require(not rollbacks, "prior_rollback_requires_review")
    receipt = json.loads(audits[0]["detail"])
    require(fingerprints(state) == receipt["after"] and digest(state["projections"]) == receipt["after_projection_sha256"], "rollback_target_state_drifted")
    require(digest([r for r in state["history"] if r["id"] != audits[0]["id"]]) == plan["history_sha256"], "audit_history_drifted")
    cur.execute("UPDATE repair_orders SET vehicle_id=%s,updated_at=now() WHERE id=%s AND tenant_id=%s AND vehicle_id=%s", (old["id"],owner["id"],plan["tenant"],target["id"]))
    require(cur.rowcount == 1, "update_cardinality_changed")
    after = collect(cur, plan["tenant"], lock=True)
    validate(after, plan["tenant"])
    before_hashes, after_hashes = verify_transition(state, after, owner["id"], old["id"])
    detail = dict(plan_sha256=expected_digest, before=before_hashes, after=after_hashes, after_projection_sha256=digest(after["projections"]))
    cur.execute("INSERT INTO repair_order_history_events (id,tenant_id,repair_order_id,event_type,label,detail,entity_id,actor_user_id,actor_name) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)",
        (str(uuid4()),plan["tenant"],owner["id"],"ets_vehicle_link_rollback","Rolled back ETS vehicle association repair",json.dumps(detail,sort_keys=True),old["id"],None,"Owner-authorized ETS repair"))
    return "rolled_back"


def private_write(path, value):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd,"w") as out:
        json.dump(value,out,sort_keys=True)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    commands=parser.add_subparsers(dest="command",required=True)
    proof=commands.add_parser("source-proof");proof.add_argument("--capture",required=True);proof.add_argument("--out",required=True)
    plan=commands.add_parser("plan");plan.add_argument("--proof",required=True);plan.add_argument("--tenant-id",required=True);plan.add_argument("--out",required=True)
    apply=commands.add_parser("apply");apply.add_argument("--plan",required=True);apply.add_argument("--expected-sha256",required=True)
    rollback=commands.add_parser("rollback");rollback.add_argument("--plan",required=True);rollback.add_argument("--expected-sha256",required=True)
    rehearse=commands.add_parser("rehearse");rehearse.add_argument("--plan",required=True);rehearse.add_argument("--expected-sha256",required=True)
    args=parser.parse_args()
    if args.command == "source-proof":
        value=source_proof(args.capture);private_write(args.out,value);print(json.dumps({"source_proof_sha256":digest(value)}));return
    dsn=os.environ["DATABASE_URL"].replace("postgresql+asyncpg://","postgresql://")
    conn=psycopg2.connect(dsn)
    try:
        conn.set_session(isolation_level="SERIALIZABLE",readonly=args.command=="plan")
        with conn.cursor() as cur:
            cur.execute("SET LOCAL lock_timeout='5s'; SET LOCAL statement_timeout='30s'")
            if args.command == "plan":
                value=make_plan(cur,str(UUID(args.tenant_id)),json.loads(Path(args.proof).read_text()))
                private_write(args.out,value);print(json.dumps({"mode":"read_only_plan","plan_sha256":digest(value)}));conn.rollback()
            else:
                result=(apply_plan if args.command in {"apply", "rehearse"} else rollback_plan)(cur,json.loads(Path(args.plan).read_text()),args.expected_sha256)
                if args.command == "rehearse":
                    conn.rollback();result="rehearsed_and_rolled_back"
                else:
                    conn.commit()
                print(json.dumps({"result":result,"plan_sha256":args.expected_sha256}))
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    main()
