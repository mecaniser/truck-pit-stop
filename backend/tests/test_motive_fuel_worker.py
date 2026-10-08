"""Daily source-fuel evidence, immutable identity and recovery acceptance."""

import copy
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

import pytest
from app.db.models.fleet_fuel import FleetFuelDaily
from app.db.models.fleet_trip import FleetTrip
from app.services.fleet_telemetry import now
from scripts.motive_sync import fuel_runner as worker
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker
from tests.test_db036_fleet_telemetry import VIN, prepared


def source(stamp=None):
    stamp = stamp or now()
    start = stamp - timedelta(minutes=2)
    days = worker.completed_dates(start)
    return {
        "version": 1,
        "company_label": "77 CARGO LLC",
        "company_id": "KT8934277",
        "company_verified_before": True,
        "company_verified_after": True,
        "timezone_evidence": "Eastern Time - New York",
        "started_at": start.isoformat(),
        "finished_at": stamp.isoformat(),
        "complete": True,
        "directory_count": 1,
        "terminal_evidence": "Showing 1 of 1",
        "report_dates": days,
        "reports": [
            {
                "report_date": day,
                "filter_start": day,
                "filter_end": day,
                "report_url": f"https://app.gomotive.com/en-US/#/reports/vehicle-fuel-performance;start_date={day};end_date={day};report_id=48;report_type=normal;vehicle_ids=123",
                "visible_date_text": datetime.fromisoformat(day).strftime("%b")
                + " "
                + str(datetime.fromisoformat(day).day),
                "complete": True,
                "terminal_evidence": "Showing 1 result",
                "row_count": 1,
                "provider_vehicle_id": "123",
                "selected_unit": "77",
                "explicit_empty": False,
                "source_read_at": (stamp - timedelta(minutes=1)).isoformat(),
            }
            for day in days
        ],
        "vehicles": [
            {
                "provider_vehicle_id": "123",
                "unit": "77",
                "vin": VIN,
                "records": [
                    {
                        "report_date": day,
                        "state": "reported",
                        "source_read_at": (stamp - timedelta(minutes=1)).isoformat(),
                        "driving_fuel_gallons": "30",
                        "idling_fuel_gallons": "2.1",
                        "reported_total_fuel_gallons": "32.1",
                        "source_distance_miles": "180",
                        "source_driving_seconds": 12000,
                        "source_idling_seconds": 3600,
                    }
                    for day in days
                ],
            }
        ],
    }


def test_completed_dates_use_conservative_noon_cutoff():
    assert worker.completed_dates(
        datetime(2026, 10, 8, 11, 59, tzinfo=timezone.utc)
    ) == ["2026-10-04", "2026-10-05", "2026-10-06"]
    assert worker.completed_dates(
        datetime(2026, 10, 8, 12, 0, tzinfo=timezone.utc)
    ) == ["2026-10-05", "2026-10-06", "2026-10-07"]
    with pytest.raises(ValueError):
        worker.completed_dates(now(), 8)


@pytest.mark.parametrize(
    "change",
    [
        {"company_id": "other"},
        {"company_verified_after": False},
        {"complete": False},
        {"directory_count": 2},
        {"terminal_evidence": None},
        {"version": True},
    ],
)
def test_global_source_gates_cannot_be_quarantined(change):
    document = source()
    document.update(change)
    with pytest.raises(ValueError):
        worker.validate_source(document, "77 CARGO LLC", "KT8934277", now())


def test_report_date_binding_count_and_full_grid_gates():
    original = source()
    worker.validate_source(original, "77 CARGO LLC", "KT8934277", now())
    for change in (
        {"complete": False},
        {"filter_start": "2020-01-01"},
        {"visible_date_text": "Jan 1"},
        {"row_count": 2},
        {"provider_vehicle_id": "999"},
        {"report_url": original["reports"][0]["report_url"] + ";vehicle=777"},
    ):
        broken = copy.deepcopy(original)
        broken["reports"][0].update(change)
        with pytest.raises(ValueError):
            worker.validate_source(broken, "77 CARGO LLC", "KT8934277", now())
    broken = copy.deepcopy(original)
    broken["vehicles"][0]["records"].pop()
    with pytest.raises(ValueError, match="every report date"):
        worker.validate_source(broken, "77 CARGO LLC", "KT8934277", now())


@pytest.mark.asyncio
async def test_dry_commit_replay_preserves_dates_values_and_fleet_projection(
    _db_engine, db_session, monkeypatch, tmp_path
):
    actor, vehicle, member = await prepared(db_session, monkeypatch)
    member.effective_from = now() - timedelta(days=14)
    await db_session.commit()
    tenant, actor_id = actor.tenant_id, actor.id
    factory = async_sessionmaker(_db_engine, expire_on_commit=False)
    document = source()
    args = (
        factory,
        document,
        tenant,
        actor_id,
        "77 CARGO LLC",
        "KT8934277",
        tmp_path / "receipt.json",
    )
    dry = await worker.run(*args)
    assert not dry["committed"] and len(dry["rows"]) == 3
    async with factory() as db:
        assert (
            await db.execute(select(func.count()).select_from(FleetFuelDaily))
        ).scalar_one() == 0
    saved = await worker.run(*args, commit=True)
    assert saved["stage"] == "verified" and saved["fleet_projection_verified"] == 3
    repeated = await worker.run(*args, commit=True, recovery=True)
    assert [r["fuel_id"] for r in saved["rows"]] == [
        r["fuel_id"] for r in repeated["rows"]
    ]
    assert all(r["action"] == "unchanged" for r in repeated["rows"])
    # Normal execution also accepts exact retry despite database Decimal scale.
    again = await worker.run(*args, commit=True)
    assert all(r["action"] == "unchanged" for r in again["rows"])
    async with factory() as db:
        fuels = (await db.execute(select(FleetFuelDaily))).scalars().all()
        assert len(fuels) == 3 and all(
            f.timezone_status == "unverified" and f.source_timezone is None
            for f in fuels
        )
        assert all(
            float(f.driving_fuel_gallons) == 30 and float(f.idling_fuel_gallons) == 2.1
            for f in fuels
        )
        assert (
            await db.execute(select(func.count()).select_from(FleetTrip))
        ).scalar_one() == 0
    assert vehicle.mileage == 100
    with pytest.raises(ValueError, match="owner/admin"):
        await worker.run(
            factory,
            document,
            uuid4(),
            actor_id,
            "77 CARGO LLC",
            "KT8934277",
            tmp_path / "foreign.json",
            commit=True,
        )


@pytest.mark.asyncio
async def test_changed_immutable_reading_quarantines_without_blocking_valid_day(
    _db_engine, db_session, monkeypatch, tmp_path
):
    actor, _, member = await prepared(db_session, monkeypatch)
    member.effective_from = now() - timedelta(days=14)
    await db_session.commit()
    factory = async_sessionmaker(_db_engine, expire_on_commit=False)
    args = (actor.tenant_id, actor.id, "77 CARGO LLC", "KT8934277")
    document = source()
    missing = copy.deepcopy(document)
    for record in missing["vehicles"][0]["records"][1:]:
        record.update(
            state="source_missing",
            reason="no_source_fuel",
            **{key: None for key in worker.MEASUREMENTS},
        )
    await worker.run(factory, missing, *args, tmp_path / "first.json", commit=True)
    document["vehicles"][0]["records"][0].update(
        driving_fuel_gallons="31", reported_total_fuel_gallons="33.1"
    )
    result = await worker.run(
        factory, document, *args, tmp_path / "second.json", commit=True
    )
    assert result["report"]["exclusions"][0]["reason"] == "conflicting_immutable_fuel"
    assert len(result["rows"]) == 2 and all(
        row["action"] == "created" for row in result["rows"]
    )
    async with factory() as db:
        fuels = (await db.execute(select(FleetFuelDaily))).scalars().all()
        assert len(fuels) == 3 and all(
            float(f.driving_fuel_gallons) == 30 for f in fuels
        )


@pytest.mark.asyncio
async def test_zero_missing_vin_and_membership_are_explicit(
    _db_engine, db_session, monkeypatch, tmp_path
):
    actor, _, member = await prepared(db_session, monkeypatch)
    member.effective_from = now() - timedelta(days=14)
    await db_session.commit()
    factory = async_sessionmaker(_db_engine, expire_on_commit=False)
    args = (actor.tenant_id, actor.id, "77 CARGO LLC", "KT8934277")
    document = source()
    records = document["vehicles"][0]["records"]
    records[0].update(
        driving_fuel_gallons="0",
        idling_fuel_gallons=None,
        reported_total_fuel_gallons=None,
    )
    records[1].update(
        state="source_missing",
        reason="no_source_fuel",
        **{key: None for key in worker.MEASUREMENTS},
    )
    records[2].update(
        driving_fuel_gallons=None,
        idling_fuel_gallons=None,
        reported_total_fuel_gallons=None,
    )
    result = await worker.run(
        factory, document, *args, tmp_path / "partial.json", commit=True
    )
    assert len(result["rows"]) == 1
    assert {r["reason"] for r in result["report"]["exclusions"]} == {
        "no_source_fuel",
        "invalid_source_reading",
    }
    async with factory() as db:
        fuel = (await db.execute(select(FleetFuelDaily))).scalars().one()
        assert fuel.driving_fuel_gallons == 0 and fuel.idling_fuel_gallons is None
    unknown = source()
    unknown["vehicles"][0]["vin"] = None
    result = await worker.run(
        factory, unknown, *args, tmp_path / "unknown.json", commit=True
    )
    assert (
        not result["rows"]
        and sum(
            x["reason"] == "vin_unavailable" for x in result["report"]["exclusions"]
        )
        == 3
    )
    member.effective_from = now() - timedelta(minutes=5)
    await db_session.commit()
    result = await worker.run(
        factory, source(), *args, tmp_path / "member.json", commit=True
    )
    assert not result["rows"] and all(
        "membership" in row["reason"] for row in result["report"]["exclusions"]
    )


@pytest.mark.asyncio
async def test_atomic_failure_and_exact_source_recovery(
    _db_engine, db_session, monkeypatch, tmp_path
):
    actor, _, member = await prepared(db_session, monkeypatch)
    member.effective_from = now() - timedelta(days=14)
    await db_session.commit()
    factory = async_sessionmaker(_db_engine, expire_on_commit=False)
    document = source()
    args = (
        factory,
        document,
        actor.tenant_id,
        actor.id,
        "77 CARGO LLC",
        "KT8934277",
        tmp_path / "recover.json",
    )
    original = worker.batches
    calls = 0

    async def broken(*args, **kwargs):
        nonlocal calls
        calls += 1
        result = await original(*args, **kwargs)
        if calls == 3:
            raise ValueError("Injected replay failure")
        return result

    monkeypatch.setattr(worker, "batches", broken)
    with pytest.raises(ValueError, match="Injected"):
        await worker.run(*args, commit=True)
    async with factory() as db:
        assert (
            await db.execute(select(func.count()).select_from(FleetFuelDaily))
        ).scalar_one() == 0
    material = Path(str(tmp_path / "recover.json") + ".normalized.json").read_bytes()
    monkeypatch.setattr(worker, "batches", original)
    saved = await worker.run(*args, commit=True, recovery=True)
    assert (
        saved["committed"]
        and Path(str(tmp_path / "recover.json") + ".normalized.json").read_bytes()
        == material
    )
    bad = copy.deepcopy(document)
    bad["vehicles"][0]["records"][0]["driving_fuel_gallons"] = "50"
    with pytest.raises(ValueError, match="immutable identity"):
        await worker.run(
            factory,
            bad,
            actor.tenant_id,
            actor.id,
            "77 CARGO LLC",
            "KT8934277",
            tmp_path / "recover.json",
            commit=True,
            recovery=True,
        )
    assert json.loads((tmp_path / "recover.json").read_text())["stage"] == "verified"


@pytest.mark.asyncio
async def test_fuel_read_projection_rechecks_current_vin(db_session, monkeypatch):
    from app.services.fleet_fuel import list_fuel_daily
    from scripts.import_motive_daily_fuel import parse_rows, run_import
    from tests.test_db036_daily_fuel import document

    actor, vehicle, member = await prepared(db_session, monkeypatch)
    member.effective_from = now() - timedelta(days=14)
    await db_session.commit()
    rows = parse_rows(document(), now())
    await run_import(db_session, rows, actor.tenant_id, actor.id, True)
    await db_session.commit()
    day = rows[0].report_date
    vehicle.vin = " " + VIN.lower() + " "
    await db_session.commit()
    same = await list_fuel_daily(db_session, actor.tenant_id, day, day)
    assert same["total"] == 1 and same["imported_start"] == day
    vehicle.vin = "2" + VIN[1:]
    await db_session.commit()
    changed = await list_fuel_daily(db_session, actor.tenant_id, day, day)
    assert changed["total"] == 0 and changed["items"] == []
    assert changed["imported_start"] is None and changed["imported_end"] is None


@pytest.mark.parametrize("enabled", [None, "false", "TRUE", "true"])
def test_orchestrator_saves_only_exact_true(tmp_path, monkeypatch, enabled):
    from scripts.motive_sync import run_fuel_worker as orchestrator

    monkeypatch.setenv("MOTIVE_FUEL_STATE_DIR", str(tmp_path))
    monkeypatch.delenv("MOTIVE_FUEL_COMMIT", raising=False)
    if enabled is not None:
        monkeypatch.setenv("MOTIVE_FUEL_COMMIT", enabled)
    calls = []
    monkeypatch.setattr(
        orchestrator.subprocess, "run", lambda command, **kwargs: calls.append(command)
    )
    orchestrator.main()
    assert len(calls) == 2 and calls[0][0] == "node"
    assert ("--commit" in calls[1]) is (enabled == "true")


def test_pending_recovery_precedes_new_collection_and_blocks_if_disabled(
    tmp_path, monkeypatch
):
    from scripts.motive_sync import run_fuel_worker as orchestrator

    previous = tmp_path / "previous"
    previous.mkdir()
    receipt = previous / "receipt.json"
    receipt.write_text(json.dumps({"mode": "commit", "stage": "commit_pending"}))
    monkeypatch.setenv("MOTIVE_FUEL_STATE_DIR", str(tmp_path))
    monkeypatch.setenv("MOTIVE_FUEL_COMMIT", "false")
    calls = []
    monkeypatch.setattr(
        orchestrator.subprocess, "run", lambda command, **kwargs: calls.append(command)
    )
    with pytest.raises(RuntimeError, match="saving is disabled"):
        orchestrator.main()
    assert not calls
    monkeypatch.setenv("MOTIVE_FUEL_COMMIT", "true")
    with pytest.raises(RuntimeError, match="remains unverified"):
        orchestrator.main()
    assert len(calls) == 1 and "--recover" in calls[0]
    calls.clear()

    def completed(command, **kwargs):
        calls.append(command)
        if "--recover" in command:
            receipt.write_text(json.dumps({"mode": "commit", "stage": "verified"}))

    monkeypatch.setattr(orchestrator.subprocess, "run", completed)
    orchestrator.main()
    assert len(calls) == 3 and "--recover" in calls[0] and calls[1][0] == "node"
    assert str(previous / "source.json") in calls[0]
