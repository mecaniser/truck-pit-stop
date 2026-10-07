from copy import deepcopy
from datetime import timedelta
from types import SimpleNamespace
from uuid import uuid4

import pytest
from app.db.models.fleet_telemetry import FleetTelemetrySnapshot as Snapshot
from app.db.models.user import UserRole
from app.services import fleet_telemetry as telemetry
from scripts.motive_sync import import_locations as worker
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker
from tests.test_db036_fleet_telemetry import VIN, prepared


def source(stamp=None):
    stamp = stamp or telemetry.now()
    return {
        "company_label": "77 CARGO LLC",
        "company_id": "KT8934277",
        "company_verified_before": True,
        "company_verified_after": True,
        "complete": True,
        "vehicles": [
            {
                "provider_vehicle_id": "123",
                "unit": "609",
                "vin": VIN,
                "lat": 35.1,
                "lng": -80.2,
                "address": "Matthews, NC",
                "sourceAge": "1m",
                "sourceReadTime": stamp.isoformat(),
                "rawTimestamp": "verified fixture",
                "timezone": "America/New_York",
                "precision": "second",
                "observed_at": (stamp - timedelta(minutes=1)).isoformat(),
                "status": "located",
            }
        ],
    }


def old(observed=None, **kwargs):
    return SimpleNamespace(
        observed_at=observed, lat=35.1, lng=-80.2, evidence_note=None, **kwargs
    )


@pytest.mark.parametrize(
    "change",
    [
        {"company_id": "other"},
        {"company_verified_after": False},
        {"complete": False},
        {"company_verified_before": "true"},
        {"vehicles": []},
    ],
)
def test_document_identity(change):
    doc = source()
    doc.update(change)
    with pytest.raises(ValueError):
        worker.parse_document(doc, "77 CARGO LLC", "KT8934277", telemetry.now())


def test_duplicate_vin_and_tenant_request_ids():
    doc = source()
    row = doc["vehicles"][0]
    body = worker.make_body(
        row, uuid4(), uuid4(), doc["company_label"], doc["company_id"]
    )
    assert body.observed_at is not None
    a, b = uuid4(), uuid4()
    args = (row, a, b, doc["company_label"], doc["company_id"])
    assert (
        worker.make_body(*args).client_request_id
        == worker.make_body(*args).client_request_id
    )
    assert (
        worker.make_body(
            row, uuid4(), b, doc["company_label"], doc["company_id"]
        ).client_request_id
        != worker.make_body(*args).client_request_id
    )
    doc["vehicles"].append(deepcopy(row))
    with pytest.raises(ValueError, match="Duplicate"):
        worker.parse_document(doc, "77 CARGO LLC", "KT8934277", telemetry.now())


def test_ordering_does_not_refresh_unknown_or_old():
    row = source()["vehicles"][0]
    t = worker.time_value(row["observed_at"])
    assert worker.disposition(row, [old()]) == "prior_time_unknown"
    assert worker.disposition(row, [old(t + timedelta(seconds=1))]) == "older"
    assert worker.disposition(row, [old(t)]) == "unchanged"
    row["lat"] = 30
    assert worker.disposition(row, [old(t)]) == "conflicting_observation"


def test_minute_precision_cannot_replace_known():
    row = source()["vehicles"][0]
    t = worker.time_value(row["observed_at"]).replace(second=0, microsecond=0)
    row.update(
        precision="minute",
        observed_at=None,
        observed_minute_start=t.isoformat(),
        observed_minute_end=(t + timedelta(minutes=1)).isoformat(),
    )
    assert (
        worker.disposition(row, [old(t - timedelta(hours=1))])
        == "precision_insufficient_for_projection"
    )
    body = worker.make_body(row, uuid4(), uuid4(), "77 CARGO LLC", "KT8934277")
    assert body.observed_at is None and "observed_minute_start" in body.evidence_note


@pytest.mark.asyncio
async def test_capture_dryrun_commit_replay_and_tenant_guard(
    db_session, monkeypatch, _db_engine
):
    actor, truck, _ = await prepared(db_session, monkeypatch)
    truck.last_lat = None
    truck.last_lng = None
    await db_session.commit()
    tenant_id, actor_id = actor.tenant_id, actor.id
    factory = async_sessionmaker(_db_engine, expire_on_commit=False)
    doc = source()
    args = (factory, doc, tenant_id, actor_id, "77 CARGO LLC", "KT8934277")
    dry = await worker.run_import(*args)
    assert not dry["committed"] and dry["rows"][0]["board_verified"]
    assert not (await db_session.execute(select(Snapshot))).scalars().all()
    await db_session.rollback()
    result = await worker.run_import(*args, commit=True)
    assert result["committed"] and result["rows"][0]["created"]
    replay = await worker.run_import(*args, commit=True)
    assert replay["rows"][0]["status"] == "replay"
    assert replay["rows"][0]["snapshot_id"] == result["rows"][0]["snapshot_id"]
    future = telemetry.now() + timedelta(hours=1)
    monkeypatch.setattr(telemetry, "now", lambda: future)
    recovered = await worker.run_import(*args, commit=True)
    assert recovered["rows"][0]["snapshot_id"] == result["rows"][0]["snapshot_id"]
    assert recovered["rows"][0]["saved_receipt_verified"]
    with pytest.raises(ValueError, match="Active tenant"):
        await worker.run_import(
            factory, doc, uuid4(), actor_id, "77 CARGO LLC", "KT8934277", commit=True
        )
    assert len((await db_session.execute(select(Snapshot))).scalars().all()) == 1


@pytest.mark.asyncio
async def test_wrong_role_and_unknown_prior_keep_data(db_session, monkeypatch):
    actor, _truck, _ = await prepared(db_session, monkeypatch)
    doc = source()
    rows = worker.parse_document(doc, "77 CARGO LLC", "KT8934277", telemetry.now())
    _, plans, report = await worker.prepare(
        db_session,
        rows,
        actor.tenant_id,
        actor.id,
        doc["company_label"],
        doc["company_id"],
    )
    assert not plans and report[0]["status"] == "prior_time_unknown"
    actor.role = UserRole.CUSTOMER
    await db_session.commit()
    with pytest.raises(ValueError, match="owner/admin"):
        await worker.prepare(
            db_session,
            rows,
            actor.tenant_id,
            actor.id,
            doc["company_label"],
            doc["company_id"],
        )


def test_verified_new_time_can_supersede_unknown_capture():
    row = source()["vehicles"][0]
    stamp = worker.time_value(row["observed_at"])
    assert (
        worker.disposition(row, [old(captured_at=stamp - timedelta(seconds=1))])
        == "update"
    )
    assert worker.disposition(row, [old(captured_at=stamp)]) == "prior_time_unknown"


def test_unavailable_without_vin_and_expired_file():
    doc = source()
    doc["vehicles"][0].update(status="unavailable", vin=None, reason="vin_unavailable")
    doc["vehicles"][0].pop("sourceReadTime")
    assert (
        worker.parse_document(doc, "77 CARGO LLC", "KT8934277", telemetry.now())[0][
            "vin"
        ]
        == ""
    )
    with pytest.raises(ValueError, match="Stale"):
        worker.parse_document(
            source(telemetry.now() - timedelta(hours=1)),
            "77 CARGO LLC",
            "KT8934277",
            telemetry.now(),
        )


@pytest.mark.asyncio
async def test_ambiguous_membership_rejected_before_capture(db_session, monkeypatch):
    from app.db.models.vehicle_relationship import FleetMembership

    actor, truck, membership = await prepared(db_session, monkeypatch)
    db_session.add(
        FleetMembership(
            tenant_id=actor.tenant_id,
            vehicle_id=truck.id,
            fleet_customer_id=membership.fleet_customer_id,
            effective_from=telemetry.now() - timedelta(hours=1),
        )
    )
    await db_session.commit()
    doc = source()
    with pytest.raises(ValueError, match="unique current"):
        await worker.prepare(
            db_session,
            doc["vehicles"],
            actor.tenant_id,
            actor.id,
            doc["company_label"],
            doc["company_id"],
        )
    assert not (await db_session.execute(select(Snapshot))).scalars().all()


@pytest.mark.asyncio
async def test_cross_replica_lock_and_release(monkeypatch):
    calls = []

    class Connection:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_):
            return False

        async def execute(self, query, params):
            calls.append(str(query))
            return SimpleNamespace(scalar_one=lambda: True)

    connection = Connection()
    factory = SimpleNamespace(
        kw={
            "bind": SimpleNamespace(
                dialect=SimpleNamespace(name="postgresql"), connect=lambda: connection
            )
        }
    )

    async def fail(*args):
        raise ValueError("synthetic_failure")

    monkeypatch.setattr(worker, "_run_import", fail)
    with pytest.raises(ValueError, match="synthetic_failure"):
        await worker.run_import(factory, {}, uuid4(), uuid4(), "company", "id")
    assert calls == [
        "SELECT pg_try_advisory_lock(:key)",
        "SELECT pg_advisory_unlock(:key)",
    ]
