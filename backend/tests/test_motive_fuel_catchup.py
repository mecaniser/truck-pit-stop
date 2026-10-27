"""Fuel-specific receipt planning, interval closure and interruption fairness."""

import copy
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import pytest
from scripts.motive_sync import fuel_coverage as coverage
from scripts.motive_sync import fuel_runner
from scripts.motive_sync.trip_runner import immutable_json
from sqlalchemy.ext.asyncio import async_sessionmaker
from tests.test_db036_fleet_telemetry import prepared
from tests.test_motive_fuel_worker import source

STAMP = datetime(2026, 10, 26, 14, tzinfo=UTC)


def scope():
    return coverage.scope(uuid4(), uuid4(), "KT8934277", "77 CARGO LLC")


def plan(expected, days, stamp=STAMP, lane="backlog", explicit=False):
    return {
        "version": 1,
        "scope": expected,
        "run_id": str(uuid4()),
        "created_at": stamp.isoformat(),
        "mode": "explicit" if explicit else "automatic",
        "first_lane": "explicit" if explicit else lane,
        "days": days,
    }


def daily(expected, day, stamp=STAMP):
    document = source(stamp)
    old = document["report_dates"][0]
    document["report_dates"] = [day]
    document["reports"] = document["reports"][:1]
    for proof in document["reports"]:
        proof.update(
            report_date=day,
            filter_start=day,
            filter_end=day,
            report_url=proof["report_url"].replace(old, day),
            visible_date_text=datetime.fromisoformat(day).strftime("%b")
            + " "
            + str(datetime.fromisoformat(day).day),
        )
    document["vehicles"][0]["records"] = document["vehicles"][0]["records"][:1]
    document["vehicles"][0]["records"][0]["report_date"] = day
    document["plan"] = plan(expected, [day], stamp - timedelta(minutes=3))
    return document


@pytest.mark.parametrize(
    "day,stamp,want",
    [
        ("2026-10-25", "2026-10-26T11:59:59+00:00", False),
        ("2026-10-25", "2026-10-26T12:00:00+00:00", True),
        ("2026-11-01", "2026-11-02T11:59:59+00:00", False),
        ("2026-11-01", "2026-11-02T12:00:00+00:00", True),
        ("2028-02-29", "2028-03-01T12:00:00+00:00", True),
    ],
)
def test_conservative_report_interval(day, stamp, want):
    assert coverage.closed(day, datetime.fromisoformat(stamp)) is want


def test_long_outage_and_repeated_single_day_budget_progress():
    expected = scope()
    index, history, completed = {}, [], []
    for i in range(12):
        stamp = STAMP + timedelta(minutes=i)
        days, lane = coverage.plan_days(expected, stamp, index, history)
        assert len(days) == 7 and all(coverage.closed(d, stamp) for d in days)
        item = plan(expected, days, stamp, lane)
        coverage.validate_plan(item, expected, stamp)
        history.append(item)
        # Hard interruption after first exact receipt: later planned dates do
        # not count as attempted or examined. Alternate first-slot lanes.
        first = days[0]
        index[first] = {"status": "verified", "observed_at": stamp.isoformat()}
        completed.append(first)
    assert completed[::2] == [f"2026-08-{d:02}" for d in range(15, 21)]
    assert set(completed[1::2]) == {"2026-10-23", "2026-10-24", "2026-10-25"}
    assert coverage.complete_through(expected, index) == "2026-08-20"


def test_failed_first_day_not_lost_or_permanent_head_blocker():
    expected = scope()
    history = []
    for i in range(6):
        days, lane = coverage.plan_days(
            expected, STAMP + timedelta(minutes=i), {}, history
        )
        history.append(plan(expected, days, STAMP + timedelta(minutes=i), lane))
    assert [p["days"][0] for p in history[::2]] == [
        "2026-08-15",
        "2026-08-16",
        "2026-08-17",
    ]
    assert coverage.complete_through(expected, {}) is None


def test_exception_rotation_and_manual_does_not_consume_lane():
    expected = scope()
    index = {
        (datetime(2026, 8, 15) + timedelta(days=i)).date().isoformat(): {
            "status": "examined_with_exceptions",
            "observed_at": (
                STAMP - timedelta(days=20) + timedelta(minutes=i)
            ).isoformat(),
        }
        for i in range(72)
    }
    days, lane = coverage.plan_days(expected, STAMP, index, [])
    assert days[0] == "2026-08-15"
    auto = plan(expected, days, lane=lane)
    explicit = plan(
        expected, ["2026-09-01"], STAMP + timedelta(seconds=1), explicit=True
    )
    _next_days, next_lane = coverage.plan_days(
        expected, STAMP + timedelta(seconds=2), index, [auto, explicit]
    )
    assert next_lane == "recent"
    index["2026-08-15"]["observed_at"] = STAMP.isoformat()
    retry, _ = coverage.plan_days(expected, STAMP, index, [])
    assert retry[0] == "2026-08-16"
    forced, _ = coverage.plan_days(
        expected, STAMP, index, [auto], explicit=("2026-09-01", "2026-09-07")
    )
    assert len(forced) == 7 and forced[0] == "2026-09-01"


def test_scope_plan_and_closure_fail_closed(tmp_path):
    expected = scope()
    item = plan(expected, ["2026-08-15"])
    folder = tmp_path / item["run_id"]
    folder.mkdir()
    immutable_json(folder / "plan.json", item)
    assert coverage.plans(tmp_path, expected, STAMP) == [item]
    with pytest.raises(ValueError, match="scope"):
        coverage.plans(tmp_path, scope(), STAMP)
    for mutate in [
        lambda p: p.update(days=["2026-10-26"]),
        lambda p: p.update(days=["2026-02-30"]),
        lambda p: p.update(days=["2026-08-15"] * 2),
        lambda p: p.update(days=["2026-08-14"]),
    ]:
        changed = copy.deepcopy(item)
        mutate(changed)
        with pytest.raises(ValueError):
            coverage.validate_plan(changed, expected, STAMP)
    with pytest.raises(ValueError):
        coverage.plan_days(
            expected, STAMP, {}, [], explicit=("2026-10-25", "2026-10-26")
        )


def test_legacy_recent_contract_not_bypassed():
    document = daily(scope(), "2026-08-15")
    fuel_runner.validate_source(document, "77 CARGO LLC", "KT8934277", STAMP)
    document.pop("plan")
    with pytest.raises(ValueError, match="Contiguous"):
        fuel_runner.validate_source(document, "77 CARGO LLC", "KT8934277", STAMP)


@pytest.mark.asyncio
async def test_actual_daily_commit_index_replay_conflict_and_source_absence(
    _db_engine, db_session, monkeypatch, tmp_path
):
    actor, _vehicle, member = await prepared(db_session, monkeypatch)
    stamp = fuel_runner.importer.now()
    member.effective_from = stamp - timedelta(days=120)
    await db_session.commit()
    expected = coverage.scope(actor.tenant_id, actor.id, "KT8934277", "77 CARGO LLC")
    day = (stamp - timedelta(days=10)).date().isoformat()
    document = daily(expected, day, stamp)
    factory = async_sessionmaker(_db_engine, expire_on_commit=False)

    async def save(doc):
        folder = tmp_path / doc["plan"]["run_id"] / day
        folder.mkdir(parents=True)
        immutable_json(folder / "source.json", doc)
        result = await fuel_runner.run(
            factory,
            doc,
            actor.tenant_id,
            actor.id,
            "77 CARGO LLC",
            "KT8934277",
            folder / "receipt.json",
            commit=True,
            plan=doc["plan"],
        )
        return folder, result

    folder, result = await save(document)
    assert result["coverage"]["status"] == "verified"
    exact = coverage.validate_receipt(
        folder / "receipt.json", expected, plan=document["plan"], day=day
    )
    assert coverage.verified_days(tmp_path, expected)[day] == exact
    # Real Node wrapper -> real Python verifier using saved fixture evidence.
    import asyncio
    import os
    import subprocess
    import sys

    plan_path = folder.parent / "plan.json"
    immutable_json(plan_path, document["plan"])
    environment = {
        **os.environ,
        "PYTHONPATH": str(Path(__file__).resolve().parents[1]),
        "MOTIVE_FUEL_PYTHON": sys.executable,
        "MOTIVE_SYNC_TENANT_ID": str(actor.tenant_id),
        "MOTIVE_SYNC_ACTOR_ID": str(actor.id),
        "MOTIVE_COMPANY_ID": "KT8934277",
        "MOTIVE_COMPANY_LABEL": "77 CARGO LLC",
    }
    wrapper = Path(__file__).resolve().parents[1] / "scripts/motive_sync/fuel_day.cjs"
    js = "const {finalizeDay}=require(process.argv[1]);const {spawnSync}=require('node:child_process');finalizeDay(process.argv[2],process.argv[3],process.argv[4],()=>{},(exe,args,opts)=>args.includes('--verify-only')?spawnSync(exe,args,opts):({status:0}));"
    command = [
        "node",
        "-e",
        js,
        str(wrapper),
        str(folder / "source.json"),
        str(plan_path),
        day,
    ]
    checked = await asyncio.to_thread(
        subprocess.run,
        command,
        check=False,
        env=environment,
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert checked.returncode == 0, "Actual receipt verifier rejected valid fixture"
    wrong = await asyncio.to_thread(
        subprocess.run,
        command,
        check=False,
        env={**environment, "MOTIVE_SYNC_ACTOR_ID": str(uuid4())},
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert wrong.returncode != 0

    replay = await fuel_runner.run(
        factory,
        document,
        actor.tenant_id,
        actor.id,
        "77 CARGO LLC",
        "KT8934277",
        folder / "receipt.json",
        commit=True,
        recovery=True,
    )
    assert replay["rows"][0]["action"] == "unchanged"
    changed = copy.deepcopy(document)
    changed["plan"]["run_id"] = str(uuid4())
    changed["finished_at"] = (stamp + timedelta(microseconds=1)).isoformat()
    monkeypatch.setattr(
        fuel_runner.importer, "now", lambda: stamp + timedelta(seconds=1)
    )
    changed["vehicles"][0]["records"][0].update(
        driving_fuel_gallons="31", reported_total_fuel_gallons="33.1"
    )
    _, result = await save(changed)
    assert result["coverage"]["status"] == "examined_with_exceptions"
    assert result["coverage"]["matrix"][0]["status"] == "immutable_source_conflict"
    missing = copy.deepcopy(changed)
    missing["plan"]["run_id"] = str(uuid4())
    missing["finished_at"] = (stamp + timedelta(microseconds=2)).isoformat()
    record = missing["vehicles"][0]["records"][0]
    record.update(
        state="source_missing",
        reason="fuel_readings_missing",
        **{key: None for key in fuel_runner.MEASUREMENTS},
    )
    _, result = await save(missing)
    assert result["coverage"]["matrix"][0]["status"] == "observed_source_absence"
    assert result["coverage"]["matrix"][0]["prior_retained"] is True
    assert (
        coverage.verified_days(tmp_path, expected)[day]["status"]
        == "examined_with_exceptions"
    )
    with pytest.raises(ValueError, match="private worker"):
        await fuel_runner.run(
            factory,
            document,
            actor.tenant_id,
            actor.id,
            "77 CARGO LLC",
            "KT8934277",
            tmp_path / "manual.json",
            commit=True,
        )
    # An arbitrary scope substitution cannot consume the valid receipt.
    with pytest.raises(ValueError, match="scope"):
        coverage.validate_receipt(folder / "receipt.json", scope())
    document["reports"][0]["row_count"] = 2
    with pytest.raises(ValueError, match="zero or one"):
        fuel_runner.validate_source(document, "77 CARGO LLC", "KT8934277", stamp)


def fixture_receipt(root, expected, day, observed, mapping="a" * 64, status="verified"):
    document = daily(expected, day, observed)
    folder = root / document["plan"]["run_id"] / day
    folder.mkdir(parents=True)
    row = {"provider_vehicle_id": "123"}
    matrix = [
        {
            "provider_vehicle_id": "123",
            "report_date": day,
            "status": "verified_saved"
            if status == "verified"
            else "observed_source_absence",
        }
    ]
    c = {
        "version": 1,
        "scope": expected,
        "day": day,
        "observed_at": document["finished_at"],
        "mapping_sha256": mapping,
        "status": status,
        "matrix": matrix,
    }
    identity = {
        key: expected[key]
        for key in ("tenant_id", "actor_id", "company_id", "company_label")
    }
    normalized = {
        **identity,
        "source_sha256": coverage.digest(document),
        "rows": [row] if status == "verified" else [],
        "coverage": c,
    }
    size = len(normalized["rows"])
    receipt = {
        **identity,
        "source_sha256": coverage.digest(document),
        "normalized_sha256": coverage.digest(normalized),
        "coverage": c,
        "mode": "commit",
        "stage": "verified",
        "committed": True,
        "rows": [{"fuel_id": str(uuid4())}] if size else [],
        "readback_verified": size,
        "replay_unchanged": size,
        "fleet_projection_verified": size,
    }
    for name, value in [
        ("source.json", document),
        ("receipt.json", receipt),
        ("receipt.json.normalized.json", normalized),
    ]:
        immutable_json(folder / name, value)
    return folder


def test_latest_exception_mapping_invalidates_old_certification_and_hashes(tmp_path):
    expected = scope()
    old = fixture_receipt(tmp_path, expected, "2026-08-15", STAMP)
    fixture_receipt(
        tmp_path,
        expected,
        "2026-08-16",
        STAMP + timedelta(seconds=1),
        mapping="b" * 64,
        status="examined_with_exceptions",
    )
    found = coverage.verified_days(tmp_path, expected)
    assert (
        set(found) == {"2026-08-16"}
        and coverage.complete_through(expected, found) is None
    )
    proof = json.loads((old / "source.json").read_text())
    proof["company_verified_after"] = False
    (old / "source.json").write_text(json.dumps(proof))
    with pytest.raises(ValueError, match="proof mismatch"):
        coverage.verified_days(tmp_path, expected)


def test_daily_recovery_orphan_and_symlink_fail_closed(tmp_path, monkeypatch):
    from scripts.motive_sync import run_fuel_worker as worker

    day = tmp_path / str(uuid4()) / "2026-08-15"
    day.mkdir(parents=True)
    intent = day / "receipt.json.normalized.json"
    immutable_json(intent, {"rows": []})
    calls = []
    monkeypatch.setattr(worker.subprocess, "run", lambda *a, **k: calls.append(a))
    with pytest.raises(RuntimeError, match="without receipt"):
        worker.recover_pending(tmp_path)
    assert calls == []
    immutable_json(day / "receipt.json", {"mode": "commit", "stage": "commit_pending"})
    monkeypatch.setenv("MOTIVE_FUEL_COMMIT", "true")
    with pytest.raises(RuntimeError, match="unverified"):
        worker.recover_pending(tmp_path)
    assert len(calls) == 1 and "--recover" in calls[0][0]
    (day / "receipt.json").unlink()
    (day / "receipt.json").symlink_to(intent)
    with pytest.raises(ValueError, match="private"):
        worker.recover_pending(tmp_path)


def test_automatic_worker_pins_scope_before_browser_and_has_no_plan_no_browser(
    tmp_path, monkeypatch
):
    from scripts.motive_sync import run_fuel_worker as worker
    from scripts.motive_sync.lifecycle import FuelLifecycle

    expected = scope()
    monkeypatch.setattr(worker, "expected_scope", lambda: expected)
    calls = []
    monkeypatch.setattr(worker, "read_process", lambda *a, **k: calls.append(a))
    monkeypatch.setattr(
        worker.fuel_coverage, "plan_days", lambda *a, **k: ([], "backlog")
    )
    worker.run_catchup(tmp_path, FuelLifecycle(commit_enabled=True))
    assert calls == [] and coverage.private_read(tmp_path / "scope.json") == expected
    monkeypatch.setattr(worker, "expected_scope", scope)
    with pytest.raises(ValueError, match="pinned scope"):
        worker.run_catchup(tmp_path, FuelLifecycle(commit_enabled=True))
    assert calls == []


@pytest.mark.asyncio
async def test_private_historical_import_rejects_expired_plan_before_db(tmp_path):
    expected = scope()
    stamp = fuel_runner.importer.now()
    document = daily(expected, (stamp - timedelta(days=10)).date().isoformat(), stamp)
    document["plan"]["created_at"] = (stamp - timedelta(minutes=31)).isoformat()

    def forbidden():
        raise AssertionError("Database must not open for expired plan")

    with pytest.raises(ValueError, match="plan expired"):
        await fuel_runner.run(
            forbidden,
            document,
            expected["tenant_id"],
            expected["actor_id"],
            expected["company_label"],
            expected["company_id"],
            tmp_path / "receipt.json",
            commit=True,
            plan=document["plan"],
        )
    assert not (tmp_path / "receipt.json").exists()
