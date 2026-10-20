"""Opt-in local sibling PostgreSQL186 migration, API and concurrent metadata proof."""
import asyncio
import importlib.util
import os
import json
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4
from datetime import datetime, timedelta, timezone, date
from decimal import Decimal

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from app.api.v1.endpoints import labor_cost
from app.core.dependencies import get_current_active_user
from app.db.models.tenant import Tenant
from app.db.models.user import User, UserRole
from app.db.models.customer import Customer
from app.db.models.vehicle import Vehicle
from app.db.models.repair_order import RepairOrder, RepairOrderStatus
from app.db.models.labor import Labor
from app.db.models.inventory import Inventory, PartsUsage
from app.db.models.invoice import Invoice, InvoiceStatus
from app.db.models.mechanic_time import MechanicTimeSession, MechanicAttendanceSession, MechanicSessionType, MechanicAttendanceAudit
from app.services.labor_cost.calculation import stamp
from tests.test_db136_labor_cost import valid_rate

pytestmark = pytest.mark.skipif(not os.environ.get("DB136_TEST_DATABASE_URL"), reason="isolated local PostgreSQL sibling required")


async def seed_job(db, tenant_id, owner_id, mechanic_id, *, prefix="SYNTHETIC-A1", history=False, no_time=False):
    customer = Customer(id=uuid4(), tenant_id=tenant_id, first_name="Synthetic", last_name="A1",
                        email=f"{uuid4().hex}@example.test", company_name="Synthetic A1 fixture")
    vehicle = Vehicle(id=uuid4(), tenant_id=tenant_id, customer_id=customer.id, make="Volvo", model="VNR")
    db.add_all([customer, vehicle])
    await db.flush()
    start = datetime(2026, 10, 20, 9, tzinfo=timezone.utc)
    end = start + timedelta(hours=3)
    order = RepairOrder(id=uuid4(), tenant_id=tenant_id, customer_id=customer.id, vehicle_id=vehicle.id,
                        order_number=f"{prefix}-{uuid4().hex[:6]}", status=RepairOrderStatus.INVOICED,
                        created_at=start, work_completed_at=end, total_cost=Decimal("500.00"),
                        source="easy_truck_shop_import" if history else None)
    inventory = Inventory(id=uuid4(), tenant_id=tenant_id, sku=f"SYN-A1-{uuid4().hex[:6]}", name="Synthetic part",
                          stock_quantity=10, cost=Decimal("150.00"), selling_price=Decimal("150.00"))
    db.add_all([order, inventory])
    await db.flush()
    labor = Labor(id=uuid4(), tenant_id=tenant_id, repair_order_id=order.id, description="Synthetic operation",
                  hours=Decimal("3.00"), hourly_rate=Decimal("116.67"), total_cost=Decimal("350.00"))
    part = PartsUsage(id=uuid4(), tenant_id=tenant_id, repair_order_id=order.id, inventory_id=inventory.id,
                     quantity=Decimal("1.00"), unit_cost=Decimal("150.00"), unit_price=Decimal("150.00"), total_price=Decimal("150.00"))
    snapshot = {"version": 1, "labor": [{"description": "Synthetic operation", "hours": "3.00", "hourly_rate": "116.67", "total_cost": "350.00"}],
                "parts": [{"name": "Synthetic part", "quantity": "1.00", "unit_price": "150.00", "total_price": "150.00"}]}
    invoice = Invoice(id=uuid4(), tenant_id=tenant_id, repair_order_id=order.id, billed_customer_id=customer.id,
                      invoice_number=f"SYN-A1-{uuid4().hex[:8]}", status=InvoiceStatus.SENT, subtotal=Decimal("500.00"),
                      total_amount=Decimal("500.00"), line_items_snapshot=snapshot,
                      source="easy_truck_shop_import" if history else None)
    db.add_all([labor, part, invoice])
    if not no_time and not history:
        db.add(MechanicTimeSession(id=uuid4(), tenant_id=tenant_id, mechanic_id=mechanic_id, repair_order_id=order.id,
            session_type=MechanicSessionType.REPAIR_ORDER, started_at=start, ended_at=end, stop_reason="manual",
            started_by_user_id=mechanic_id, stopped_by_user_id=mechanic_id))
        db.add(MechanicAttendanceSession(id=uuid4(), tenant_id=tenant_id, mechanic_id=mechanic_id,
            local_date=date(2026, 10, 20), started_at=start, ended_at=end, started_by_user_id=mechanic_id,
            ended_by_user_id=mechanic_id, snapshot_timezone="America/New_York", snapshot_core_target_minutes=480,
            snapshot_shift_start_local="08:00", snapshot_shift_end_local="18:00"))
    await db.flush()
    return order


@pytest.mark.asyncio
async def test_pg186_immutable_concurrent_owner_api_and_readonly_snapshot(monkeypatch):
    url = os.environ["DB136_TEST_DATABASE_URL"]
    from urllib.parse import urlsplit
    parsed = urlsplit(url)
    assert parsed.hostname in {"localhost", "127.0.0.1"} and parsed.path.startswith("/truckpitstop_db136_a1_test")
    engine = create_async_engine(url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with engine.begin() as connection:
            assert (await connection.execute(text("SELECT version_num FROM alembic_version"))).scalar_one() == "185_callrail_inquiry_main_merge"
            assert (await connection.execute(text("SELECT count(*) FROM invoices"))).scalar_one() == 0
            spec = importlib.util.spec_from_file_location("db136migration", Path(__file__).parents[1] / "alembic/versions/186_labor_cost_policy.py")
            migration = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(migration)
            def upgrade(sync):
                monkeypatch.setattr(migration, "op", Operations(MigrationContext.configure(sync)))
                migration.upgrade()
            await connection.run_sync(upgrade)
            await connection.execute(text("UPDATE alembic_version SET version_num='186_labor_cost_policy'"))
        tenant_id, owner_id, admin_id, mechanic_id, foreign_tenant, foreign_mechanic = [uuid4() for _ in range(6)]
        async with factory.begin() as db:
            db.add_all([Tenant(id=tenant_id, name="Synthetic A1 PG", slug=f"a1-pg-{uuid4().hex[:8]}", timezone="America/New_York"),
                        Tenant(id=foreign_tenant, name="Synthetic foreign", slug=f"a1-foreign-{uuid4().hex[:8]}", timezone="UTC")])
            await db.flush()
            for identity, role, tenant in ((owner_id, UserRole.GARAGE_OWNER, tenant_id), (admin_id, UserRole.GARAGE_ADMIN, tenant_id),
                                           (mechanic_id, UserRole.MECHANIC, tenant_id), (foreign_mechanic, UserRole.MECHANIC, foreign_tenant)):
                db.add(User(id=identity, tenant_id=tenant, first_name="Synthetic", last_name=role.value,
                            email=f"{uuid4().hex}@example.test", hashed_password="synthetic-unused", role=role, is_active=True))
            await db.flush()
            job = await seed_job(db, tenant_id, owner_id, mechanic_id)
            job_id = job.id
            history_job = await seed_job(db, tenant_id, owner_id, mechanic_id, history=True)
            history_job_id = history_job.id
        monkeypatch.setattr(labor_cost, "AsyncSessionLocal", factory)
        actor = SimpleNamespace(id=owner_id, tenant_id=tenant_id, role=UserRole.GARAGE_OWNER, is_active=True, deleted_at=None)
        app = FastAPI()
        app.include_router(labor_cost.router, prefix="/api/v1/reports")
        # Auth has already queried a separate transaction before GET source.
        async def auth():
            async with factory() as db:
                assert (await db.execute(select(User.id).where(User.id == actor.id))).scalar_one() == actor.id
                yield actor
        app.dependency_overrides[get_current_active_user] = auth
        async def readonly_probe(db):
            assert (await db.execute(text("SHOW transaction_isolation"))).scalar_one() == "repeatable read"
            assert (await db.execute(text("SHOW transaction_read_only"))).scalar_one() == "on"
            return True
        assert await labor_cost.read_call(actor, readonly_probe)
        source_tables = ("invoices", "payments", "labor", "parts_usage", "mechanic_time_sessions", "mechanic_attendance_sessions", "inventory", "repair_orders",
                         "invoice_settlements", "payment_overpayments", "customer_credit_entries", "payment_refunds", "invoice_charge_adjustments",
                         "mechanic_time_session_audit", "mechanic_attendance_audit", "mechanic_break_sessions")
        async def fingerprint():
            async with factory() as db:
                return {table: (await db.execute(text(f"SELECT count(*), md5(coalesce(string_agg(to_jsonb(t)::text, '' ORDER BY id),'')) FROM {table} t"))).one() for table in source_tables}
        before = await fingerprint()
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://a1.test") as client:
            base = "/api/v1/reports"
            listing = await client.get(f"{base}/technician-costs")
            assert listing.status_code == 200, listing.text
            assert listing.headers["cache-control"] == "private, no-store"
            assert listing.json()["items"][0]["version"] == 0
            assert listing.json()["items"][0]["policy"] is None
            foreign = await client.get(f"{base}/technician-costs/{foreign_mechanic}")
            assert foreign.status_code == 404
            boundary = await client.get(f"{base}/technician-costs/time-boundaries?local=2026-10-20T09:00")
            assert boundary.status_code == 200 and boundary.json()["effective_at"] == "2026-10-20T13:00:00Z"
            assert boundary.json()["activation_at"] == "2026-10-20T04:00:00Z"
            assert (await client.get(f"{base}/technician-costs/time-boundaries?local=2026-11-01T01:30")).status_code == 422
            first = await client.get(f"{base}/technician-costs/time-boundaries?local=2026-11-01T01:30&fold=0")
            second = await client.get(f"{base}/technician-costs/time-boundaries?local=2026-11-01T01:30&fold=1")
            assert first.status_code == second.status_code == 200 and first.json()["effective_at"] != second.json()["effective_at"]
            assert (await client.get(f"{base}/technician-costs/time-boundaries?local=2027-03-14T02:30")).status_code == 422
            assert (await client.get(f"{base}/technician-costs/time-boundaries?local=2026-10-20T09:00&local=2026-10-20T10:00")).status_code == 422
            key = str(uuid4())
            body = valid_rate()
            rate = await client.post(f"{base}/technician-costs/{mechanic_id}", json=body, headers={"Idempotency-Key": key})
            assert rate.status_code == 201, rate.text
            replay = await client.post(f"{base}/technician-costs/{mechanic_id}", json=body, headers={"Idempotency-Key": key})
            assert replay.status_code == 200 and replay.json() == rate.json()
            assert (await client.post(f"{base}/technician-costs/{mechanic_id}", json={**body, "reason": "Different"}, headers={"Idempotency-Key": key})).status_code == 409
            # Concurrent expected-version writers serialize on the exact tenant.
            results = await asyncio.gather(*(client.post(f"{base}/technician-costs/{mechanic_id}", json={**body, "expected_version": 1, "reason": f"Concurrent synthetic {n}"}, headers={"Idempotency-Key": str(uuid4())}) for n in range(2)))
            assert sorted(result.status_code for result in results) == [201, 409]
            detail = await client.get(f"{base}/job-contribution/{job_id}")
            assert detail.status_code == 200, detail.text
            assert detail.json()["row"]["direct_contribution"] is None
            assert detail.json()["row"]["labor"]["known_cost"] == "120.00"
            history_detail = await client.get(f"{base}/job-contribution/{history_job_id}")
            assert history_detail.status_code == 200 and history_detail.json()["row"]["source_owner"] == "ets_history"
            history_review = {"expected_version": 0, "source_fingerprint": history_detail.json()["source_fingerprint"],
                              "policy_heads_digest": history_detail.json()["policy_heads_digest"], "business_classification": "real",
                              "time_capture": "incomplete", "reviewed_exception_ids": [], "reason": "Synthetic forbidden historical review"}
            rejected = await client.post(f"{base}/job-contribution/{history_job_id}/review", json=history_review, headers={"Idempotency-Key": str(uuid4())})
            assert rejected.status_code == 422
            async with factory() as db:
                assert (await db.execute(text("SELECT count(*) FROM job_cost_reviews"))).scalar_one() == 0
            review_body = {"expected_version": 0, "source_fingerprint": detail.json()["source_fingerprint"],
                           "policy_heads_digest": detail.json()["policy_heads_digest"], "business_classification": "real",
                           "time_capture": "complete", "reviewed_exception_ids": [], "reason": "Synthetic captured direct labor"}
            review_key = str(uuid4())
            reviewed = await client.post(f"{base}/job-contribution/{job_id}/review", json=review_body, headers={"Idempotency-Key": review_key})
            assert reviewed.status_code == 201, reviewed.text
            assert reviewed.json()["row"]["direct_contribution"] == "230.00"
            assert (await client.post(f"{base}/job-contribution/{job_id}/review", json=review_body, headers={"Idempotency-Key": review_key})).json() == reviewed.json()
            final = await client.get(f"{base}/job-contribution/{job_id}")
            assert final.json()["row"]["review_status"] == "current" and final.json()["row"]["direct_contribution"] == "230.00"
            async with factory() as db:
                metadata_before_get = (await db.execute(text("SELECT (SELECT count(*) FROM technician_cost_policy_revisions),(SELECT count(*) FROM job_cost_reviews)"))).one()
            report = await client.get(f"{base}/job-contribution?from=2026-10-20&to=2026-10-20&limit=1")
            assert report.status_code == 200, report.text
            assert report.json()["summary"]["reviewed_complete_contribution"] == "230.00"
            assert report.json()["summary"]["is_complete"] is True
            assert report.json()["summary"]["history_count"] == 1
            assert len(report.json()["rows"]) == 1 and report.json()["next_cursor"]
            page2 = await client.get(f"{base}/job-contribution", params={"from": "2026-10-20", "to": "2026-10-20", "limit": 1, "cursor": report.json()["next_cursor"]})
            assert page2.status_code == 200 and page2.json()["next_cursor"] is None
            assert page2.json()["summary"] == report.json()["summary"]
            assert {row["order_id"] for page in (report, page2) for row in page.json()["rows"]} == {str(job_id), str(history_job_id)}
            async with factory() as db:
                assert (await db.execute(text("SELECT (SELECT count(*) FROM technician_cost_policy_revisions),(SELECT count(*) FROM job_cost_reviews)"))).one() == metadata_before_get
            assert await fingerprint() == before
            # A legitimate attendance correction is acknowledged using the
            # affected timer UUID, never an unrelated audit UUID. The API
            # appends metadata only; the synthetic audit itself is fixture setup.
            async with factory.begin() as db:
                attendance = (await db.execute(select(MechanicAttendanceSession).where(MechanicAttendanceSession.tenant_id == tenant_id,
                              MechanicAttendanceSession.mechanic_id == mechanic_id))).scalar_one()
                timer = (await db.execute(select(MechanicTimeSession).where(MechanicTimeSession.repair_order_id == job_id))).scalar_one()
                timer_id = str(timer.id)
                snapshot = {"mechanic_id": str(mechanic_id), "started_at": stamp(attendance.started_at), "ended_at": stamp(attendance.ended_at)}
                db.add(MechanicAttendanceAudit(id=uuid4(), tenant_id=tenant_id, mechanic_id=mechanic_id,
                    attendance_session_id=attendance.id, actor_user_id=owner_id, actor_role="garage_owner", action="edit",
                    before_snapshot=snapshot, after_snapshot=snapshot, manager_reason="Synthetic correction fixture"))
            before = await fingerprint()
            corrected = (await client.get(f"{base}/job-contribution/{job_id}")).json()
            assert "attendance_correction_review_required" in corrected["row"]["labor"]["hold_reasons"]
            ack = {**review_body, "expected_version": 1, "source_fingerprint": corrected["source_fingerprint"],
                   "policy_heads_digest": corrected["policy_heads_digest"], "reviewed_exception_ids": [timer_id]}
            acknowledged = await client.post(f"{base}/job-contribution/{job_id}/review", json=ack, headers={"Idempotency-Key": str(uuid4())})
            assert acknowledged.status_code == 201, acknowledged.text
            assert acknowledged.json()["row"]["direct_contribution"] == "230.00"
            assert await fingerprint() == before
            # Metadata restatement makes the prior review stale, without changing source.
            updated = await client.post(f"{base}/technician-costs/{mechanic_id}", json={**body, "expected_version": 2, "reason": "Synthetic restatement"}, headers={"Idempotency-Key": str(uuid4())})
            assert updated.status_code == 201
            stale = (await client.get(f"{base}/job-contribution/{job_id}")).json()["row"]
            assert stale["review_status"] == "stale" and stale["direct_contribution"] is None
            actor.id, actor.role = admin_id, UserRole.GARAGE_ADMIN
            assert (await client.get(f"{base}/job-contribution")).status_code == 403
        # Real PG raw SQL guards, not merely ORM event listeners.
        for statement in ("UPDATE technician_cost_policy_revisions SET version=version", "DELETE FROM technician_cost_policy_revisions",
                          "UPDATE job_cost_reviews SET reason=reason", "DELETE FROM job_cost_reviews"):
            async with engine.connect() as connection:
                with pytest.raises(Exception, match="A1 evidence is append-only"):
                    await connection.execute(text(statement))
                await connection.rollback()
        # Null JSON scalars must be rejected at the DB layer too, not merely
        # by the strict HTTP input model. Every probe rolls back independently.
        async with factory() as db:
            current = (await db.execute(text("SELECT id,version,policy FROM technician_cost_policy_revisions WHERE tenant_id=:tenant AND mechanic_id=:mechanic ORDER BY version DESC LIMIT 1"),
                                       {"tenant": tenant_id, "mechanic": mechanic_id})).mappings().one()
        for field in ("reason", "currency", "basis", "shop_timezone", "hourly_cost", "inclusions", "effective_from"):
            bad = deepcopy(current["policy"])
            if field in {"hourly_cost", "inclusions", "effective_from"}:
                bad["segments"][0][field] = None
            else:
                bad[field] = None
            async with engine.connect() as connection:
                with pytest.raises(Exception, match="Invalid A1 (policy|segment)"):
                    await connection.execute(text("""INSERT INTO technician_cost_policy_revisions
                        (id,tenant_id,mechanic_id,version,supersedes_id,policy,request_sha256,idempotency_key,approved_by_user_id)
                        VALUES (:id,:tenant,:mechanic,:version,:prior,CAST(:policy AS jsonb),:hash,:key,:owner)"""),
                        {"id": uuid4(), "tenant": tenant_id, "mechanic": mechanic_id, "version": current["version"]+1,
                         "prior": current["id"], "policy": json.dumps(bad), "hash": "f"*64, "key": uuid4(), "owner": owner_id})
                await connection.rollback()
        async with engine.connect() as connection:
            with pytest.raises(Exception, match="Cannot remove approved A1 evidence"):
                await connection.run_sync(lambda sync: (setattr(migration, "op", Operations(MigrationContext.configure(sync))), migration.downgrade()))
            await connection.rollback()
        assert await fingerprint() == before
    finally:
        await engine.dispose()
