"""Manual, local-only DB-135 migration/trigger rehearsal on a disposable DB.

Run from backend/ with its approved local configuration. Never targets the
configured database itself; creates and drops a uniquely named sibling.
"""

import datetime as dt
import json
import os
import subprocess
import uuid

from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

from app.core.config import settings


def _id():
    return str(uuid.uuid4())


def _stamp(value):
    return value.strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def main():
    url = make_url(settings.DATABASE_URL)
    if url.host not in {"localhost", "127.0.0.1"} or url.database != "truckpitstop":
        raise RuntimeError("DB-135 rehearsal requires the known local development server")
    admin = create_engine(url.set(drivername="postgresql+psycopg2", database="postgres"), isolation_level="AUTOCOMMIT")
    name = "db135_attest_rehearsal_" + uuid.uuid4().hex[:8]
    with admin.connect() as conn:
        conn.execute(text("CREATE DATABASE " + name))
    try:
        env = os.environ.copy()
        env["DATABASE_URL"] = url.set(database=name).render_as_string(hide_password=False)
        alembic = os.path.join(os.path.dirname(os.sys.executable), "alembic")
        subprocess.run([alembic, "upgrade", "head"], env=env, check=True, capture_output=True)
        engine = create_engine(url.set(drivername="postgresql+psycopg2", database=name))
        keys = {key: _id() for key in ("tenant", "reviewer", "executor", "customer", "vehicle", "order", "invoice", "run", "attestation")}
        now = dt.datetime.now(dt.timezone.utc)
        reviewed, expiry = now - dt.timedelta(hours=1), now + dt.timedelta(days=1)
        digest = "a" * 64
        entry = {
            "decision": "verified_open", "repair_order_id": keys["order"], "customer_id": keys["customer"],
            "principal_total_cents": "10000", "confirmed_principal_cents": "0", "source_fingerprint": digest,
            "evidence_digest": digest, "fingerprint_version": "v1", "version": "1", "supersedes_id": "",
            "reviewed_at": _stamp(reviewed), "valid_until": _stamp(expiry), "audit_reference": "local-synthetic",
        }
        with engine.begin() as conn:
            conn.execute(text("INSERT INTO tenants (id,name,slug,sms_enabled,timezone,default_core_hours_minutes,default_shift_start_local,default_shift_end_local,internal_labor_rate) VALUES (:id,'Local test','db135-synthetic',false,'America/New_York',480,'08:00','17:00',0)"), {"id": keys["tenant"]})
            for actor in ("reviewer", "executor"):
                conn.execute(text("INSERT INTO users (id,tenant_id,email,role,first_name,last_name,is_active,permissions) VALUES (:id,:tenant,:email,'garage_owner','Local','Tester',true,'{}')"), {"id": keys[actor], "tenant": keys["tenant"], "email": actor + "@example.invalid"})
            conn.execute(text("INSERT INTO customers (id,tenant_id,first_name,last_name,email,sms_opt_out,is_internal_fleet) VALUES (:id,:tenant,'Synthetic','Customer','synthetic@example.invalid',false,false)"), {"id": keys["customer"], "tenant": keys["tenant"]})
            conn.execute(text("INSERT INTO vehicles (id,tenant_id,customer_id,make,model,pm_interval_miles) VALUES (:id,:tenant,:customer,'Test','Truck',10000)"), {"id": keys["vehicle"], "tenant": keys["tenant"], "customer": keys["customer"]})
            conn.execute(text("INSERT INTO repair_orders (id,tenant_id,customer_id,vehicle_id,order_number,status,is_internal,is_pm,labor_discount_amount,order_discount_amount) VALUES (:id,:tenant,:customer,:vehicle,'DB135-SYNTH','completed',false,false,0,0)"), {"id": keys["order"], "tenant": keys["tenant"], "customer": keys["customer"], "vehicle": keys["vehicle"]})
            conn.execute(text("INSERT INTO invoices (id,tenant_id,repair_order_id,invoice_number,status,subtotal,total_amount,zelle_pending_reminder_count) VALUES (:id,:tenant,:ro,'DB135-SYNTH','overdue',100,100,0)"), {"id": keys["invoice"], "tenant": keys["tenant"], "ro": keys["order"]})
            conn.execute(text("INSERT INTO invoice_receivable_attestation_runs (id,tenant_id,manifest_digest,invoice_ids,approved_entries,fingerprint_version,expected_insert_count,authorization_reference,reviewer_user_id,executor_user_id,state) VALUES (:id,:tenant,:digest,CAST(:invoice_ids AS jsonb),CAST(:entries AS jsonb),'v1',1,'local synthetic approval',:reviewer,:executor,'applied')"), {"id": keys["run"], "tenant": keys["tenant"], "digest": digest, "invoice_ids": json.dumps([keys["invoice"]]), "entries": json.dumps({keys["invoice"]: entry}), "reviewer": keys["reviewer"], "executor": keys["executor"]})
            conn.execute(text("INSERT INTO invoice_receivable_attestations (id,tenant_id,invoice_id,repair_order_id,customer_id,run_id,version,supersedes_id,decision,currency,principal_total_cents,confirmed_principal_cents,source_fingerprint,fingerprint_version,evidence_digest,manifest_digest,reviewer_user_id,executor_user_id,reviewed_at,applied_at,valid_until,audit_reference) VALUES (:id,:tenant,:invoice,:ro,:customer,:run,1,NULL,'verified_open','USD',10000,0,:digest,'v1',:digest,:digest,:reviewer,:executor,:reviewed,clock_timestamp(),:expiry,'local-synthetic')"), {"id": keys["attestation"], "tenant": keys["tenant"], "invoice": keys["invoice"], "ro": keys["order"], "customer": keys["customer"], "run": keys["run"], "digest": digest, "reviewer": keys["reviewer"], "executor": keys["executor"], "reviewed": reviewed, "expiry": expiry})
        print("exact approved synthetic insert: pass")
        with engine.begin() as conn:
            for label, sql in (
                ("immutable", "UPDATE invoice_receivable_attestations SET audit_reference='tampered' WHERE id=:id"),
                ("unapproved successor", "INSERT INTO invoice_receivable_attestations (id,tenant_id,invoice_id,repair_order_id,customer_id,run_id,version,supersedes_id,decision,currency,principal_total_cents,confirmed_principal_cents,source_fingerprint,fingerprint_version,evidence_digest,manifest_digest,reviewer_user_id,executor_user_id,reviewed_at,applied_at,valid_until,audit_reference) SELECT gen_random_uuid(),tenant_id,invoice_id,repair_order_id,customer_id,run_id,2,id,decision,currency,principal_total_cents,confirmed_principal_cents,source_fingerprint,fingerprint_version,evidence_digest,manifest_digest,reviewer_user_id,executor_user_id,reviewed_at,clock_timestamp(),valid_until,audit_reference FROM invoice_receivable_attestations WHERE id=:id"),
            ):
                try:
                    with conn.begin_nested():
                        conn.execute(text(sql), {"id": keys["attestation"]})
                except Exception as exc:
                    assert "DB135 attestation evidence is immutable" in str(exc) if label == "immutable" else "DB135 run lineage mismatch" in str(exc)
                    print(label + " rejection: pass")
                else:
                    raise AssertionError(label + " unexpectedly succeeded")
        try:
            with engine.begin() as conn:
                conn.execute(text("INSERT INTO invoice_receivable_attestation_runs (id,tenant_id,manifest_digest,invoice_ids,approved_entries,fingerprint_version,expected_insert_count,authorization_reference,reviewer_user_id,executor_user_id,state) VALUES (:id,:tenant,:digest,CAST(:invoice_ids AS jsonb),CAST(:entries AS jsonb),'v1',1,'local synthetic approval',:reviewer,:executor,'applied')"), {"id": _id(), "tenant": keys["tenant"], "digest": "b" * 64, "invoice_ids": json.dumps([keys["invoice"]]), "entries": json.dumps({keys["invoice"]: entry}), "reviewer": keys["reviewer"], "executor": keys["executor"]})
        except Exception as exc:
            assert "DB135 run insert count mismatch" in str(exc)
            print("incomplete run rollback: pass")
        else:
            raise AssertionError("run without an attestation unexpectedly committed")
        try:
            with engine.begin() as conn:
                conn.execute(text("UPDATE users SET is_active=false WHERE id=:id"), {"id": keys["reviewer"]})
                conn.execute(text("INSERT INTO invoice_receivable_attestation_runs (id,tenant_id,manifest_digest,invoice_ids,approved_entries,fingerprint_version,expected_insert_count,authorization_reference,reviewer_user_id,executor_user_id,state) VALUES (:id,:tenant,:digest,CAST(:invoice_ids AS jsonb),CAST(:entries AS jsonb),'v1',1,'local synthetic approval',:reviewer,:executor,'applied')"), {"id": _id(), "tenant": keys["tenant"], "digest": "c" * 64, "invoice_ids": json.dumps([keys["invoice"]]), "entries": json.dumps({keys["invoice"]: entry}), "reviewer": keys["reviewer"], "executor": keys["executor"]})
        except Exception as exc:
            assert "DB135 reviewer/executor tenant or role mismatch" in str(exc)
            print("inactive reviewer rejection: pass")
        else:
            raise AssertionError("inactive reviewer unexpectedly approved a run")
        for confirmed in (0, 5000):
            try:
                with engine.begin() as conn:
                    conn.execute(text("UPDATE invoices SET status='paid' WHERE id=:id"), {"id": keys["invoice"]})
                    bad_entry = dict(entry, decision="verified_paid_tender", version="2", supersedes_id=keys["attestation"], confirmed_principal_cents=str(confirmed))
                    bad_run, bad_digest = _id(), ("b" if confirmed == 0 else "c") * 64
                    conn.execute(text("INSERT INTO invoice_receivable_attestation_runs (id,tenant_id,manifest_digest,invoice_ids,approved_entries,fingerprint_version,expected_insert_count,authorization_reference,reviewer_user_id,executor_user_id,state) VALUES (:id,:tenant,:digest,CAST(:invoice_ids AS jsonb),CAST(:entries AS jsonb),'v1',1,'local synthetic approval',:reviewer,:executor,'applied')"), {"id": bad_run, "tenant": keys["tenant"], "digest": bad_digest, "invoice_ids": json.dumps([keys["invoice"]]), "entries": json.dumps({keys["invoice"]: bad_entry}), "reviewer": keys["reviewer"], "executor": keys["executor"]})
                    conn.execute(text("INSERT INTO invoice_receivable_attestations (id,tenant_id,invoice_id,repair_order_id,customer_id,run_id,version,supersedes_id,decision,currency,principal_total_cents,confirmed_principal_cents,source_fingerprint,fingerprint_version,evidence_digest,manifest_digest,reviewer_user_id,executor_user_id,reviewed_at,applied_at,valid_until,audit_reference) VALUES (gen_random_uuid(),:tenant,:invoice,:ro,:customer,:run,2,:prior,'verified_paid_tender','USD',10000,:confirmed,:source,'v1',:source,:digest,:reviewer,:executor,:reviewed,clock_timestamp(),:expiry,'local-synthetic')"), {"tenant": keys["tenant"], "invoice": keys["invoice"], "ro": keys["order"], "customer": keys["customer"], "run": bad_run, "prior": keys["attestation"], "confirmed": confirmed, "source": digest, "digest": bad_digest, "reviewer": keys["reviewer"], "executor": keys["executor"], "reviewed": reviewed, "expiry": expiry})
            except Exception as exc:
                assert "ck_db135_attestation_decision_amount" in str(exc)
                print(f"unsupported paid tender {confirmed}/10000 rejection: pass")
            else:
                raise AssertionError("unsupported paid tender unexpectedly committed")
        try:
            subprocess.run([alembic, "downgrade", "178_merge_maintenance_bindings"], env=env, check=True, capture_output=True)
        except subprocess.CalledProcessError as exc:
            assert b"DB135 downgrade refused" in exc.stderr
            print("downgrade with evidence rejection: pass")
        else:
            raise AssertionError("downgrade unexpectedly erased evidence")
    finally:
        with admin.connect() as conn:
            conn.execute(text("DROP DATABASE " + name + " WITH (FORCE)"))
        print("disposable database removed")


if __name__ == "__main__":
    main()
