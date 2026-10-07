"""Server trip worker gates, immutable replay, and tenant-scoped imports."""

import copy
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

import pytest
from app.db.models.fleet_trip import FleetTrip
from scripts.motive_sync import trip_runner as worker
from scripts.prepare_motive_trip_history import ZONE
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker
from tests.test_db036_fleet_telemetry import VIN, prepared


def source(stamp=None):
    stamp = stamp or datetime.now(timezone.utc)
    today = stamp.astimezone(ZONE).date()
    yesterday = today - timedelta(days=1)
    row = {
        "cells": [
            "",
            f"{yesterday:%m/%d/%Y} 01:00 PM\nCity A",
            f"{yesterday:%m/%d/%Y} 02:00 PM\nCity B",
            "40 mi\n1h 0m 0s",
            "77",
        ],
        "links": ["#/fleetview/vehicles/summary/123"],
    }
    return {
        "company_label": "77 CARGO LLC",
        "company_id": "KT8934277",
        "company_verified_before": True,
        "company_verified_after": True,
        "complete": True,
        "timezone_evidence": "Eastern Time - New York",
        "started_at": (stamp - timedelta(minutes=2)).isoformat(),
        "finished_at": stamp.isoformat(),
        "directory_count": 1,
        "vehicles": [{"provider_vehicle_id": "123", "unit": "77", "vin": VIN}],
        "windows": [
            {
                "start": (today - timedelta(days=2)).isoformat(),
                "end": today.isoformat(),
                "source_read_at": (stamp - timedelta(minutes=1)).isoformat(),
                "status": "captured",
                "rows": [row],
                "expected_total": 1,
                "footerShown": 1,
                "terminal_evidence": "Showing 1 results",
            }
        ],
    }


def test_source_valid_and_terminal_evidence_required():
    stamp = datetime.now(timezone.utc)
    document = source(stamp)
    worker.validate_source(document, "77 CARGO LLC", "KT8934277", stamp)
    document["windows"][0]["footerShown"] = 2
    with pytest.raises(ValueError, match="terminal count"):
        worker.validate_source(document, "77 CARGO LLC", "KT8934277", stamp)


@pytest.mark.parametrize(
    "change",
    [
        {"company_id": "other"},
        {"company_verified_after": False},
        {"complete": False},
        {"timezone_evidence": "UTC"},
        {"directory_count": 2},
        {"started_at": "2026-01-01T00:00:00Z"},
    ],
)
def test_bad_identity_or_incomplete_source(change):
    stamp = datetime.now(timezone.utc)
    document = source(stamp)
    document.update(change)
    with pytest.raises(ValueError):
        worker.validate_source(document, "77 CARGO LLC", "KT8934277", stamp)


def test_duplicate_vin_or_provider_rejected():
    stamp = datetime.now(timezone.utc)
    for changed in ({"provider_vehicle_id": "124"}, {"vin": None}):
        document = source(stamp)
        document["vehicles"].append({**document["vehicles"][0], **changed})
        document["directory_count"] = 2
        with pytest.raises(ValueError, match="duplicate"):
            worker.validate_source(document, "77 CARGO LLC", "KT8934277", stamp)


def test_partial_recent_window_rejected():
    stamp = datetime.now(timezone.utc)
    document = source(stamp)
    document["windows"][0]["start"] = document["windows"][0]["end"]
    with pytest.raises(ValueError, match="preceding two"):
        worker.validate_source(document, "77 CARGO LLC", "KT8934277", stamp)


def test_immutable_retry_material(tmp_path):
    path = tmp_path / "normalized.json"
    worker.immutable_json(path, {"rows": [1]})
    worker.immutable_json(path, {"rows": [1]})
    assert path.stat().st_mode & 0o777 == 0o600
    with pytest.raises(ValueError, match="differs"):
        worker.immutable_json(path, {"rows": [2]})
    assert json.loads(path.read_text()) == {"rows": [1]}


@pytest.mark.asyncio
async def test_commit_receipt_replay_and_foreign_tenant(
    _db_engine, db_session, monkeypatch, tmp_path
):
    actor, vehicle, member = await prepared(db_session, monkeypatch)
    member.effective_from = datetime.now(timezone.utc) - timedelta(days=7)
    await db_session.commit()
    tenant_id, actor_id = actor.tenant_id, actor.id
    factory = async_sessionmaker(_db_engine, expire_on_commit=False)
    document = source()
    args = (factory, document, tenant_id, actor_id, "77 CARGO LLC", "KT8934277")
    dry = await worker.run(*args, tmp_path / "dry.json")
    assert not dry["committed"] and dry["rows"][0]["action"] == "would_create"
    async with factory() as session:
        assert (
            await session.execute(select(func.count()).select_from(FleetTrip))
        ).scalar_one() == 0
    saved = await worker.run(*args, tmp_path / "apply.json", True)
    assert saved["committed"] and saved["stage"] == "verified"
    assert saved["replay_unchanged"] == saved["readback_verified"] == 1
    retried = await worker.run(*args, tmp_path / "apply.json", True)
    assert retried["rows"][0]["action"] == "unchanged"
    assert retried["rows"][0]["trip_id"] == saved["rows"][0]["trip_id"]
    with pytest.raises(ValueError, match="tenant owner/admin"):
        await worker.run(
            factory,
            document,
            uuid4(),
            actor_id,
            "77 CARGO LLC",
            "KT8934277",
            tmp_path / "foreign.json",
            True,
        )
    assert not (tmp_path / "foreign.json").exists()
    async with factory() as session:
        assert (
            await session.execute(select(func.count()).select_from(FleetTrip))
        ).scalar_one() == 1
    assert vehicle.mileage == 100


@pytest.mark.asyncio
async def test_unknown_vin_recent_membership_and_changed_source_quarantined(
    _db_engine, db_session, monkeypatch, tmp_path
):
    actor, _, member = await prepared(db_session, monkeypatch)
    tenant_id, actor_id = actor.tenant_id, actor.id
    factory = async_sessionmaker(_db_engine, expire_on_commit=False)
    document = source()
    args = (tenant_id, actor_id, "77 CARGO LLC", "KT8934277")
    # Current membership cannot manufacture historical eligibility.
    receipt = await worker.run(factory, document, *args, tmp_path / "recent.json", True)
    assert receipt["rows"] == []
    assert receipt["report"]["exclusions"][0]["reason"] == "outside_membership"
    member.effective_from = datetime.now(timezone.utc) - timedelta(days=7)
    await db_session.commit()
    await worker.run(factory, document, *args, tmp_path / "first.json", True)
    changed = copy.deepcopy(document)
    changed["windows"][0]["rows"][0]["cells"][3] = "41 mi\n1h 0m 0s"
    receipt = await worker.run(
        factory, changed, *args, tmp_path / "revision.json", True
    )
    assert not receipt["rows"]
    assert receipt["report"]["exclusions"][0]["reason"] == "conflicting_source_identity"
    missing = copy.deepcopy(document)
    missing["vehicles"][0]["vin"] = None
    receipt = await worker.run(factory, missing, *args, tmp_path / "unknown.json", True)
    assert not receipt["rows"]
    assert receipt["report"]["vehicle_exclusions"][0]["reason"] == "unknown_vin"
    async with factory() as session:
        trip = (await session.execute(select(FleetTrip))).scalar_one()
        assert trip.distance_miles == 40


@pytest.mark.asyncio
async def test_replay_failure_rolls_back_whole_import(
    _db_engine, db_session, monkeypatch, tmp_path
):
    actor, _, member = await prepared(db_session, monkeypatch)
    member.effective_from = datetime.now(timezone.utc) - timedelta(days=7)
    await db_session.commit()
    tenant_id, actor_id = actor.tenant_id, actor.id
    factory = async_sessionmaker(_db_engine, expire_on_commit=False)
    original = worker.importer.run_import
    calls = 0

    async def fail_replay(*args, **kwargs):
        nonlocal calls
        calls += 1
        result = await original(*args, **kwargs)
        if calls == 3:
            raise ValueError("Injected replay failure after staged insert")
        return result

    monkeypatch.setattr(worker.importer, "run_import", fail_replay)
    receipt_path = tmp_path / "failed.json"
    with pytest.raises(ValueError, match="Injected replay"):
        await worker.run(
            factory,
            source(),
            tenant_id,
            actor_id,
            "77 CARGO LLC",
            "KT8934277",
            receipt_path,
            True,
        )
    assert json.loads(receipt_path.read_text())["committed"] is False
    assert Path(str(receipt_path) + ".normalized.json").exists()
    async with factory() as session:
        assert (
            await session.execute(select(func.count()).select_from(FleetTrip))
        ).scalar_one() == 0


@pytest.mark.asyncio
async def test_frozen_metrics_survive_source_only_refresh(
    _db_engine, db_session, monkeypatch, tmp_path
):
    actor, _, member = await prepared(db_session, monkeypatch)
    member.effective_from = datetime.now(timezone.utc) - timedelta(days=7)
    await db_session.commit()
    tenant_id, actor_id = actor.tenant_id, actor.id
    factory = async_sessionmaker(_db_engine, expire_on_commit=False)
    document = source()
    async with factory() as session:
        rows, _ = await worker.prepare(
            session, document, tenant_id, actor_id, datetime.now(timezone.utc)
        )
        rows[0]["metrics"] = {"fuel_used_gallons": 5}
        await worker.import_batches(session, rows, tenant_id, actor_id, True)
        await session.commit()
    receipt = await worker.run(
        factory,
        document,
        tenant_id,
        actor_id,
        "77 CARGO LLC",
        "KT8934277",
        tmp_path / "metrics.json",
        True,
    )
    assert receipt["rows"][0]["action"] == "unchanged"
    normalized = json.loads((tmp_path / "metrics.json.normalized.json").read_text())
    assert normalized["rows"][0]["metrics"]["fuel_used_gallons"] == 5


@pytest.mark.asyncio
async def test_stale_attempt_recovery_preserves_source_time_and_identity(
    _db_engine, db_session, monkeypatch, tmp_path
):
    actor, _, member = await prepared(db_session, monkeypatch)
    member.effective_from = datetime.now(timezone.utc) - timedelta(days=7)
    await db_session.commit()
    tenant_id, actor_id = actor.tenant_id, actor.id
    factory = async_sessionmaker(_db_engine, expire_on_commit=False)
    document = source()
    path = tmp_path / "recover.json"
    args = (factory, document, tenant_id, actor_id, "77 CARGO LLC", "KT8934277", path)
    first = await worker.run(*args, True)
    original_material = Path(str(path) + ".normalized.json").read_bytes()

    class Later(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime.now(tz) + timedelta(hours=3)

    monkeypatch.setattr(worker, "datetime", Later)
    with pytest.raises(ValueError, match="Stale"):
        await worker.run(*args, True)
    # A server commit may have succeeded despite a missing client response.
    receipt = json.loads(path.read_text())
    receipt.update(stage="commit_pending", committed=False)
    worker.private_json(path, receipt)
    recovered = await worker.recover(*args)
    assert recovered["recovery"] and recovered["stage"] == "verified"
    assert recovered["rows"][0]["action"] == "unchanged"
    assert recovered["rows"][0]["trip_id"] == first["rows"][0]["trip_id"]
    assert Path(str(path) + ".normalized.json").read_bytes() == original_material
    bad_source = copy.deepcopy(document)
    bad_source["finished_at"] = datetime.now(timezone.utc).isoformat()
    with pytest.raises(ValueError, match="immutable evidence"):
        await worker.recover(
            factory, bad_source, tenant_id, actor_id, "77 CARGO LLC", "KT8934277", path
        )
    with pytest.raises(ValueError, match="identity"):
        await worker.recover(
            factory, document, uuid4(), actor_id, "77 CARGO LLC", "KT8934277", path
        )
