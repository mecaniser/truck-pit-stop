"""Whole-source validation, immutable recovery and latest assignment projection."""

import copy
import json
from datetime import timedelta

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.db.models.fleet_driver_record import (
    FleetDriverDirectoryCapture,
    FleetDriverRecordCapture,
)
from app.schemas.fleet_driver_record import DriverRecordContent
from app.services import fleet_driver_records as service
from app.services.fleet_telemetry import now
from scripts.motive_drivers import runner
from scripts.motive_drivers.import_records import body_for, validate
from tests.test_fleet_driver_records import body, fixture


def document():
    capture = body()
    stamp = now()
    row = {
        key: value
        for key, value in capture.model_dump(mode="json").items()
        if key in DriverRecordContent.model_fields
        or key
        in {
            "vin",
            "provider_vehicle_id",
            "provider_driver_id",
            "driver_name",
            "source_read_at",
            "assignment_verified_before",
            "assignment_verified_after",
        }
    }
    row.update(
        state="captured", unit="Synthetic 77", source_timezone="America/New_York"
    )
    return {
        "version": 1,
        "company_label": "Synthetic Fleet",
        "company_id": "KT123",
        "company_verified_before": True,
        "company_verified_after": True,
        "complete": True,
        "timezone_evidence": "Eastern Time - New York",
        "started_at": (stamp - timedelta(minutes=1)).isoformat(),
        "finished_at": stamp.isoformat(),
        "driver_directory_count": 1,
        "terminal_evidence": "Showing 1 of 1",
        "drivers": [row],
        "performance_ranges": [
            {"label": "Fair", "min": 50, "max": 84, "band": "red"},
            {"label": "Good", "min": 85, "max": 95, "band": "yellow"},
            {"label": "Excellent", "min": 96, "max": 100, "band": "green"},
        ],
    }


@pytest.mark.parametrize(
    "change",
    [
        {"company_id": "foreign"},
        {"company_verified_after": False},
        {"complete": False},
        {"driver_directory_count": 2},
        {"terminal_evidence": None},
        {"version": True},
        {"performance_ranges": []},
        {"timezone_evidence": "browser local"},
    ],
)
def test_incomplete_or_foreign_document_rejected(change):
    with pytest.raises(ValueError):
        validate({**document(), **change}, "Synthetic Fleet", "KT123")


@pytest.mark.parametrize(
    "change",
    [
        {"state": "unavailable", "reason": "missing"},
        {"assignment_verified_after": False},
        {"vin": None},
        {"provider_vehicle_id": None},
        {"source_timezone": None},
        {"safety": {"score": 101}},
        {"safety": {"score": 82, "band": "green", "band_label": "Excellent (96–100)"}},
        {"safety": {"score": 82, "band": "red", "band_label": "Fair"}},
    ],
)
def test_entire_reading_validated_before_writing(change):
    source = document()
    source["drivers"][0].update(change)
    with pytest.raises(ValueError):
        validate(source, "Synthetic Fleet", "KT123")


def test_verified_range_mapping_and_request_identity():
    source = document()
    source["drivers"][0]["safety"].update(band="red", band_label="Fair (50–84)")
    assert validate(source, "Synthetic Fleet", "KT123") is source
    from uuid import uuid4

    tenant = uuid4()
    first = body_for(source, source["drivers"][0], tenant)
    assert (
        body_for(copy.deepcopy(source), source["drivers"][0], tenant).client_request_id
        == first.client_request_id
    )
    assert (
        body_for(source, source["drivers"][0], uuid4()).client_request_id
        != first.client_request_id
    )


@pytest.mark.asyncio
async def test_runner_commit_recovery_and_malformed_tail_atomicity(
    _db_engine, db_session, monkeypatch, tmp_path
):
    actor, _vehicle, member = await fixture(db_session, monkeypatch)
    factory = async_sessionmaker(_db_engine, expire_on_commit=False)
    source = document()
    args = (
        factory,
        source,
        actor.tenant_id,
        actor.id,
        "Synthetic Fleet",
        "KT123",
        tmp_path / "receipt.json",
    )
    receipt = await runner.run(
        *args, commit=True, expected_customer_id=member.fleet_customer_id
    )
    assert (
        receipt["stage"] == "verified"
        and receipt["readback_verified"] == 1
        and receipt["projection_available"] == 1
    )
    repeated = await runner.run(
        *args, commit=True, recovery=True, expected_customer_id=member.fleet_customer_id
    )
    assert repeated["rows"][0]["capture_id"] == receipt["rows"][0]["capture_id"]
    assert repeated["rows"][0]["status"] == "unchanged"
    assert (tmp_path / "receipt.json.attempt.json").stat().st_mode & 0o777 == 0o600
    assert (tmp_path / "receipt.json.source.json").stat().st_mode & 0o777 == 0o600
    bad = copy.deepcopy(source)
    bad["drivers"][0]["safety"]["score"] = 81
    with pytest.raises(ValueError, match="immutable identity"):
        await runner.run(
            factory,
            bad,
            actor.tenant_id,
            actor.id,
            "Synthetic Fleet",
            "KT123",
            tmp_path / "receipt.json",
            commit=True,
            recovery=True,
            expected_customer_id=member.fleet_customer_id,
        )
    bad = document()
    bad["drivers"].append({"provider_driver_id": "second", "state": "captured"})
    bad["driver_directory_count"] = 2
    with pytest.raises(ValueError):
        await runner.run(
            factory,
            bad,
            actor.tenant_id,
            actor.id,
            "Synthetic Fleet",
            "KT123",
            tmp_path / "bad.json",
            commit=True,
            expected_customer_id=member.fleet_customer_id,
        )
    async with factory() as db:
        assert (
            await db.scalar(select(func.count()).select_from(FleetDriverRecordCapture))
            == 1
        )
        assert (
            await db.scalar(
                select(func.count()).select_from(FleetDriverDirectoryCapture)
            )
            == 1
        )


@pytest.mark.asyncio
async def test_missing_new_assignment_and_empty_directory_suppress_prior_score(
    _db_engine, db_session, monkeypatch, tmp_path
):
    actor, vehicle, member = await fixture(db_session, monkeypatch)
    factory = async_sessionmaker(_db_engine, expire_on_commit=False)

    async def run(source, name):
        return await runner.run(
            factory,
            source,
            actor.tenant_id,
            actor.id,
            "Synthetic Fleet",
            "KT123",
            tmp_path / name,
            commit=True,
            expected_customer_id=member.fleet_customer_id,
        )

    await run(document(), "first.json")
    later = document()
    later["drivers"] = [
        {
            "provider_driver_id": "new-driver",
            "driver_name": "Different Driver",
            "provider_vehicle_id": "vehicle-123",
            "unit": "77",
            "vin": None,
            "state": "unavailable",
            "source_read_at": later["finished_at"],
            "reason": "vin_unavailable",
        }
    ]
    receipt = await run(later, "second.json")
    assert receipt["readback_verified"] == 0
    async with factory() as db:
        assert (await service.read(db, actor.tenant_id, vehicle.id)).record is None
    # Even a complete zero-row directory must invalidate older assignments.
    again = document()
    await run(again, "third.json")
    empty = document()
    empty.update(
        drivers=[], driver_directory_count=0, terminal_evidence="Showing 0 of 0"
    )
    await run(empty, "empty.json")
    async with factory() as db:
        assert (await service.read(db, actor.tenant_id, vehicle.id)).record is None
        assert (
            await db.scalar(select(func.count()).select_from(FleetDriverRecordCapture))
            == 2
        )


@pytest.mark.asyncio
async def test_local_name_mismatch_projects_only_explicit_provider_identity(
    _db_engine, db_session, monkeypatch, tmp_path
):
    actor, vehicle, member = await fixture(db_session, monkeypatch)
    source = document()
    source["drivers"][0]["driver_name"] = "Different Driver"
    receipt = await runner.run(
        async_sessionmaker(_db_engine, expire_on_commit=False),
        source,
        actor.tenant_id,
        actor.id,
        "Synthetic Fleet",
        "KT123",
        tmp_path / "mismatch.json",
        commit=True,
        expected_customer_id=member.fleet_customer_id,
    )
    assert receipt["readback_verified"] == 1 and receipt["assignment_unverified"] == 0
    assert receipt["projection_available"] == 1
    result = await service.read(db_session, actor.tenant_id, vehicle.id)
    assert result.record.driver_name == "Different Driver"
    assert result.record.local_driver_name == vehicle.driver_name == "Synthetic Driver"
    assert result.record.identity_basis == "motive_current_assignment"


@pytest.mark.asyncio
async def test_replay_failure_rolls_back_records_and_directory_then_recovers(
    _db_engine, db_session, monkeypatch, tmp_path
):
    actor, _vehicle, member = await fixture(db_session, monkeypatch)
    factory = async_sessionmaker(_db_engine, expire_on_commit=False)
    source = document()
    args = (
        factory,
        source,
        actor.tenant_id,
        actor.id,
        "Synthetic Fleet",
        "KT123",
        tmp_path / "rollback.json",
    )
    original = runner.batch
    calls = 0

    async def fail_replay(*args, **kwargs):
        nonlocal calls
        calls += 1
        value = await original(*args, **kwargs)
        if calls == 3:
            raise ValueError("Injected replay failure")
        return value

    monkeypatch.setattr(runner, "batch", fail_replay)
    with pytest.raises(ValueError, match="Injected replay"):
        await runner.run(
            *args, commit=True, expected_customer_id=member.fleet_customer_id
        )
    receipt = json.loads((tmp_path / "rollback.json").read_text())
    identity = receipt["rows"][0]["client_request_id"]
    assert receipt["committed"] is False
    async with factory() as db:
        assert (
            await db.scalar(select(func.count()).select_from(FleetDriverRecordCapture))
            == 0
        )
        assert (
            await db.scalar(
                select(func.count()).select_from(FleetDriverDirectoryCapture)
            )
            == 0
        )
    monkeypatch.setattr(runner, "batch", original)
    recovered = await runner.run(
        *args, commit=True, recovery=True, expected_customer_id=member.fleet_customer_id
    )
    assert (
        recovered["committed"] and recovered["rows"][0]["client_request_id"] == identity
    )


@pytest.mark.parametrize(
    "footer",
    [
        "Showing 1 of 22",
        "Showing 0 of 0",
        "Showing 2 of 2",
        "Showing 1-1 of 1",
        "Showing 1 of 1 next",
        "Showing 1 of 1\n",
        " Showing 1 of 1",
        "Showing 01 of 01",
        "No more drivers",
        "Showing 1 of 1Showing 1 of 1",
    ],
)
def test_terminal_footer_must_prove_exact_complete_directory(footer):
    source = document()
    source["terminal_evidence"] = footer
    with pytest.raises(ValueError, match="terminal count"):
        validate(source, "Synthetic Fleet", "KT123")


def test_explicit_empty_directory_footer_is_valid():
    source = document()
    source.update(
        drivers=[], driver_directory_count=0, terminal_evidence="Showing 0 of 0"
    )
    assert validate(source, "Synthetic Fleet", "KT123") is source


@pytest.mark.parametrize(
    "change",
    [
        {"index": 0, "min": 49},
        {"index": 0, "min": 51},
        {"index": 1, "min": 86},
        {"index": 2, "max": 99},
        {"index": 0, "label": "Good", "band": "yellow"},
        {"index": 1, "label": "Fair", "band": "red"},
    ],
)
def test_performance_ranges_agree_with_supported_collector_contract(change):
    source = document()
    source["performance_ranges"][change["index"]].update(
        {key: value for key, value in change.items() if key != "index"}
    )
    with pytest.raises(ValueError, match="performance ranges"):
        validate(source, "Synthetic Fleet", "KT123")
