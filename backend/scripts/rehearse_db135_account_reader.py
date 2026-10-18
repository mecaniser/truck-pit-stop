"""Local-only disposable PostgreSQL rehearsal of the DB-135 account reader.

Requires DATABASE_URL for the isolated, empty truckpitstop_db135 development
database. Creates a uniquely named sibling, migrates it, inserts synthetic
evidence, exercises REPEATABLE READ READ ONLY, then drops the sibling.
"""
from __future__ import annotations

import asyncio
import json
import os
import subprocess
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.core.config import settings
from app.services.customer_receivables import account_snapshot
from app.services.receivable_attestation_fingerprint import FINGERPRINT_VERSION
from app.services.receivable_attestation_reader import compute_manifest_digest
from app.services.receivable_attestation_source import load_receivable_source
from app.api.v1.endpoints.customer_receivables import render_statement_pdf
from scripts.db135_private_source_review import collect_source_review


def stamp(value: datetime) -> str:
    return value.strftime("%Y-%m-%dT%H:%M:%S.%fZ")


async def read_snapshot(url, tenant_id, customer_id, invoice_id=None):
    engine = create_async_engine(url.render_as_string(hide_password=False))
    try:
        async with AsyncSession(engine, expire_on_commit=False) as db:
            await db.execute(text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY"))
            assert (await db.execute(text("SHOW transaction_read_only"))).scalar_one() == "on"
            if invoice_id is not None:
                result = await load_receivable_source(db, tenant_id=tenant_id, invoice_id=invoice_id)
            else:
                result = await account_snapshot(db, tenant_id=tenant_id, customer_id=customer_id)
            await db.rollback()
            return result
    finally:
        await engine.dispose()


async def read_source_review(url, tenant_id):
    engine = create_async_engine(url.render_as_string(hide_password=False))
    try:
        async with AsyncSession(engine, expire_on_commit=False) as db:
            try:
                return await collect_source_review(db, tenant_id=tenant_id, expected_count=1)
            finally:
                await db.rollback()
    finally:
        await engine.dispose()


def main():
    url = make_url(settings.DATABASE_URL)
    if url.host not in {"localhost", "127.0.0.1"} or url.database != "truckpitstop_db135":
        raise RuntimeError("DB-135 account rehearsal requires isolated local truckpitstop_db135")
    admin = create_engine(url.set(drivername="postgresql+psycopg2", database="postgres"), isolation_level="AUTOCOMMIT")
    name = "db135_account_rehearsal_" + uuid4().hex[:8]
    with admin.connect() as conn:
        conn.execute(text("CREATE DATABASE " + name))
    try:
        disposable = url.set(database=name)
        env = os.environ.copy()
        env["DATABASE_URL"] = disposable.render_as_string(hide_password=False)
        alembic = os.path.join(os.path.dirname(os.sys.executable), "alembic")
        subprocess.run([alembic, "upgrade", "179_db135_receivables"], env=env, check=True, capture_output=True)
        engine = create_engine(disposable.set(drivername="postgresql+psycopg2"))
        ids = {key: uuid4() for key in ("tenant", "reviewer", "executor", "customer", "vehicle", "order", "invoice", "run", "approval")}
        with engine.begin() as conn:
            conn.execute(text("INSERT INTO tenants (id,name,slug,sms_enabled,timezone,default_core_hours_minutes,default_shift_start_local,default_shift_end_local,internal_labor_rate) VALUES (:id,'Synthetic reader','db135-account-synthetic',false,'UTC',480,'08:00','17:00',0)"), {"id": ids["tenant"]})
            for actor in ("reviewer", "executor"):
                conn.execute(text("INSERT INTO users (id,tenant_id,email,role,first_name,last_name,is_active,permissions) VALUES (:id,:tenant,:email,'garage_owner','Local','Synthetic',true,'{}')"), {"id": ids[actor], "tenant": ids["tenant"], "email": actor + "@example.invalid"})
            conn.execute(text("INSERT INTO customers (id,tenant_id,first_name,last_name,email,sms_opt_out,is_internal_fleet) VALUES (:id,:tenant,'Synthetic','Customer','reader@example.invalid',false,false)"), {"id": ids["customer"], "tenant": ids["tenant"]})
            conn.execute(text("INSERT INTO vehicles (id,tenant_id,customer_id,make,model,pm_interval_miles) VALUES (:id,:tenant,:customer,'Test','Truck',10000)"), {"id": ids["vehicle"], "tenant": ids["tenant"], "customer": ids["customer"]})
            conn.execute(text("INSERT INTO repair_orders (id,tenant_id,customer_id,vehicle_id,order_number,status,is_internal,is_pm,labor_discount_amount,order_discount_amount) VALUES (:id,:tenant,:customer,:vehicle,'DB135-READER','completed',false,false,0,0)"), {"id": ids["order"], "tenant": ids["tenant"], "customer": ids["customer"], "vehicle": ids["vehicle"]})
            conn.execute(text("INSERT INTO invoices (id,tenant_id,repair_order_id,invoice_number,status,subtotal,total_amount,due_date,zelle_pending_reminder_count) VALUES (:id,:tenant,:order,'DB135-READER','overdue',100,100,now() - interval '91 days',0)"), {"id": ids["invoice"], "tenant": ids["tenant"], "order": ids["order"]})
        source = asyncio.run(read_snapshot(disposable, ids["tenant"], ids["customer"], ids["invoice"]))
        review = asyncio.run(read_source_review(disposable, ids["tenant"]))
        assert review["read_only"] is True and review["invoice_count"] == 1
        assert review["review_paths"] == {"open_operator_review": 1}
        assert review["rows"][0]["disposition"] == "unresolved"
        assert review["rows"][0]["potential_bucket"] == "days_90_plus"
        print("PostgreSQL read-only private source review: pass")
        reviewed = datetime.now(timezone.utc) - timedelta(hours=1)
        expiry = reviewed + timedelta(days=2)
        entry = {"repair_order_id": str(ids["order"]), "customer_id": str(ids["customer"]),
                 "decision": "verified_open", "principal_total_cents": "10000",
                 "confirmed_principal_cents": "0", "source_fingerprint": source.fingerprint,
                 "evidence_digest": "b" * 64, "fingerprint_version": FINGERPRINT_VERSION,
                 "version": "1", "supersedes_id": "", "reviewed_at": stamp(reviewed),
                 "valid_until": stamp(expiry), "audit_reference": "local-synthetic-only"}
        invoice_ids = [str(ids["invoice"])]
        entries = {invoice_ids[0]: entry}
        digest = compute_manifest_digest(tenant_id=ids["tenant"], invoice_ids=invoice_ids,
            approved_entries=entries, fingerprint_version=FINGERPRINT_VERSION,
            reviewer_user_id=ids["reviewer"], executor_user_id=ids["executor"],
            authorization_reference="local-synthetic-only", expected_insert_count=1)
        with engine.begin() as conn:
            conn.execute(text("INSERT INTO invoice_receivable_attestation_runs (id,tenant_id,manifest_digest,invoice_ids,approved_entries,fingerprint_version,expected_insert_count,authorization_reference,reviewer_user_id,executor_user_id,state) VALUES (:id,:tenant,:digest,CAST(:invoice_ids AS jsonb),CAST(:entries AS jsonb),:version,1,'local-synthetic-only',:reviewer,:executor,'applied')"),
                {"id": ids["run"], "tenant": ids["tenant"], "digest": digest,
                 "invoice_ids": json.dumps(invoice_ids), "entries": json.dumps(entries),
                 "version": FINGERPRINT_VERSION, "reviewer": ids["reviewer"], "executor": ids["executor"]})
            conn.execute(text("INSERT INTO invoice_receivable_attestations (id,tenant_id,invoice_id,repair_order_id,customer_id,run_id,version,supersedes_id,decision,currency,principal_total_cents,confirmed_principal_cents,source_fingerprint,fingerprint_version,evidence_digest,manifest_digest,reviewer_user_id,executor_user_id,reviewed_at,applied_at,valid_until,audit_reference) VALUES (:id,:tenant,:invoice,:order,:customer,:run,1,NULL,'verified_open','USD',10000,0,:source,:version,:evidence,:digest,:reviewer,:executor,:reviewed,clock_timestamp(),:expiry,'local-synthetic-only')"),
                {"id": ids["approval"], "tenant": ids["tenant"], "invoice": ids["invoice"],
                 "order": ids["order"], "customer": ids["customer"], "run": ids["run"],
                 "source": source.fingerprint, "version": FINGERPRINT_VERSION, "evidence": "b" * 64,
                 "digest": digest, "reviewer": ids["reviewer"], "executor": ids["executor"],
                 "reviewed": reviewed, "expiry": expiry})
        snapshot = asyncio.run(read_snapshot(disposable, ids["tenant"], ids["customer"]))
        assert snapshot["native"]["collectible"] == "100.00"
        assert snapshot["native"]["collectible_complete"] is True
        assert snapshot["native"]["reviewed_attestation_count"] == 1
        assert any(row.get("reconciliation_basis") == "reviewed_attestation" for row in snapshot["transactions"])
        assert render_statement_pdf(snapshot).startswith(b"%PDF-")
        print("PostgreSQL read-only account and PDF reviewed-head positive: pass")
        with engine.begin() as conn:
            conn.execute(text("UPDATE invoices SET due_date = due_date + interval '1 day' WHERE id=:id"), {"id": ids["invoice"]})
        drifted = asyncio.run(read_snapshot(disposable, ids["tenant"], ids["customer"]))
        assert drifted["native"]["collectible"] == "0.00"
        assert drifted["native"]["collectible_complete"] is False
        print("PostgreSQL source drift held: pass")
    finally:
        with admin.connect() as conn:
            conn.execute(text("DROP DATABASE " + name + " WITH (FORCE)"))
        admin.dispose()
        print("Disposable PostgreSQL database removed")


if __name__ == "__main__":
    main()
