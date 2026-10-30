"""Exercise the bounded location-history query with real synthetic DB rows."""

import json
from copy import deepcopy
from datetime import datetime
from datetime import timedelta
from uuid import uuid4

import pytest
from app.db.models.fleet_telemetry import FleetTelemetrySnapshot as Snapshot
from app.db.models.vehicle_relationship import FleetMembership
from app.services import fleet_telemetry as telemetry
from scripts.motive_sync import import_locations as worker
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker
from tests.test_db036_fleet_telemetry import VIN, prepared
from tests.test_motive_sync_import import minute_source, source, unknown_source


def history_row(
    actor,
    truck,
    member,
    start,
    *,
    observed,
    precision=None,
    note=None,
    captured=None,
    lat=35.1,
):
    return Snapshot(
        tenant_id=actor.tenant_id,
        vehicle_id=truck.id,
        fleet_customer_id=member.fleet_customer_id,
        fleet_membership_id=member.id,
        verified_vin=VIN,
        client_request_id=uuid4(),
        request_digest="0" * 64,
        source="motive_dashboard_manual",
        captured_at=captured or start - timedelta(minutes=2),
        captured_by_user_id=actor.id,
        observed_at=observed,
        observed_precision=precision,
        lat=lat,
        lng=-80.2,
        evidence_note=note,
    )


async def fixture(db, monkeypatch, engine, doc=None):
    actor, truck, member = await prepared(db, monkeypatch)
    truck.last_lat = truck.last_lng = None
    await db.commit()
    doc = doc or minute_source()
    args = (
        async_sessionmaker(engine, expire_on_commit=False),
        doc,
        actor.tenant_id,
        actor.id,
        "77 CARGO LLC",
        "KT8934277",
    )
    return actor, truck, member, doc, args


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "case",
    [
        "earlier_exact",
        "earlier_second",
        "earlier_minute",
        "same_exact",
        "same_second",
        "overlapping_minute",
        "later_exact",
        "unknown",
        "legacy_future_note",
    ],
)
async def test_location_bound_counts_only_relevant_known_intervals(
    db_session, monkeypatch, _db_engine, case
):
    actor, truck, member, doc, args = await fixture(db_session, monkeypatch, _db_engine)
    start, _ = worker.interval(doc["vehicles"][0])
    earlier = case.startswith("earlier")
    observed = start - timedelta(minutes=1) if earlier else start
    if case == "later_exact":
        observed += timedelta(minutes=1)
    note = None
    if case in {"unknown", "legacy_future_note"}:
        observed = None
    if case == "legacy_future_note":
        note = json.dumps({"observed_at": (start + timedelta(minutes=1)).isoformat()})
    rows = [
        history_row(
            actor,
            truck,
            member,
            start,
            observed=observed,
            precision=(
                "minute"
                if case.endswith("minute")
                else "second"
                if case.endswith("second")
                else None
            ),
            note=note,
        )
        for _ in range(1001)
    ]
    db_session.add_all(rows)
    await db_session.commit()

    # Preserve immutable historical fields, including evidence notes.
    def immutable(row):
        values = {
            column.name: getattr(row, column.name) for column in row.__table__.columns
        }
        for key, value in values.items():
            if isinstance(value, datetime):
                values[key] = telemetry.utc(value).isoformat()
        return json.dumps(values, sort_keys=True, default=str)

    frozen = {r.id: immutable(r) for r in rows}
    result = (await worker.run_import(*args, commit=True))["rows"][0]
    assert result["status"] == ("update" if earlier else "history_review_required")
    assert truck.last_lat is None and truck.last_lng is None
    all_rows = (
        (
            await db_session.execute(
                select(Snapshot).execution_options(populate_existing=True)
            )
        )
        .scalars()
        .all()
    )
    assert len(all_rows) == (1002 if earlier else 1001)
    assert {r.id: immutable(r) for r in all_rows if r.id in frozen} == frozen
    if earlier:
        assert result["created"] and result["saved_receipt_verified"]
        assert result["board_verified_after_commit"]
        replay = (await worker.run_import(*args, commit=True))["rows"][0]
        assert replay["status"] == "replay" and replay["created"] is False
        assert replay["snapshot_id"] == result["snapshot_id"]
        later_doc = deepcopy(doc)
        later_doc["vehicles"][0]["sourceReadTime"] = (
            worker.time_value(doc["vehicles"][0]["sourceReadTime"])
            + timedelta(seconds=1)
        ).isoformat()
        later_args = (args[0], later_doc, *args[2:])
        later = (await worker.run_import(*later_args, commit=True))["rows"][0]
        assert later["status"] == "unchanged" and "snapshot_id" not in later
        assert len((await db_session.execute(select(Snapshot))).scalars().all()) == 1002


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "case,status",
    [
        ("same_exact", "unchanged"),
        ("same_conflict", "conflicting_observation"),
        ("later_exact", "older"),
        ("overlapping_minute", "overlapping_observation_interval"),
        ("legacy_future", "older"),
        ("unknown_later_capture", "prior_time_unknown"),
    ],
)
async def test_single_relevant_location_keeps_original_disposition(
    db_session, monkeypatch, _db_engine, case, status
):
    actor, truck, member, doc, args = await fixture(
        db_session, monkeypatch, _db_engine, source()
    )
    start, _ = worker.interval(doc["vehicles"][0])
    observed, precision, note, captured = start, None, None, None
    if case == "later_exact":
        observed += timedelta(seconds=1)
    if case == "overlapping_minute":
        observed -= timedelta(seconds=30)
        precision = "minute"
    if case in {"legacy_future", "unknown_later_capture"}:
        observed = None
    if case == "legacy_future":
        note = json.dumps({"observed_at": (start + timedelta(seconds=1)).isoformat()})
    if case == "unknown_later_capture":
        captured = start + timedelta(seconds=1)
    db_session.add(
        history_row(
            actor,
            truck,
            member,
            start,
            observed=observed,
            precision=precision,
            note=note,
            captured=captured,
            lat=36 if case == "same_conflict" else 35.1,
        )
    )
    await db_session.commit()
    result = (await worker.run_import(*args, commit=True))["rows"][0]
    assert result["status"] == status
    assert len((await db_session.execute(select(Snapshot))).scalars().all()) == 1


@pytest.mark.asyncio
async def test_unknown_incoming_time_keeps_full_history_guard(
    db_session, monkeypatch, _db_engine
):
    actor, truck, member, doc, args = await fixture(
        db_session, monkeypatch, _db_engine, unknown_source()
    )
    start = telemetry.now()
    db_session.add_all(
        [
            history_row(
                actor,
                truck,
                member,
                start,
                observed=start - timedelta(days=40),
                captured=start - timedelta(days=40),
            )
            for _ in range(1001)
        ]
    )
    await db_session.commit()
    result = (await worker.run_import(*args, commit=True))["rows"][0]
    assert result["status"] == "history_review_required"
    assert len((await db_session.execute(select(Snapshot))).scalars().all()) == 1001


@pytest.mark.asyncio
@pytest.mark.parametrize("scope", ["other_tenant", "old_membership"])
async def test_history_query_still_scopes_tenant_and_membership(
    db_session, monkeypatch, _db_engine, scope
):
    actor, truck, member, doc, args = await fixture(db_session, monkeypatch, _db_engine)
    start, _ = worker.interval(doc["vehicles"][0])
    if scope == "other_tenant":
        other_actor, other_truck, other_member = await prepared(db_session, monkeypatch)
    else:
        other_actor, other_truck = actor, truck
        other_member = FleetMembership(
            tenant_id=actor.tenant_id,
            vehicle_id=truck.id,
            fleet_customer_id=member.fleet_customer_id,
            effective_from=start - timedelta(days=10),
            effective_to=start - timedelta(days=2),
        )
        db_session.add(other_member)
        await db_session.commit()
    db_session.add_all(
        [
            history_row(
                other_actor,
                other_truck,
                other_member,
                start,
                observed=start + timedelta(minutes=1),
            )
            for _ in range(1001)
        ]
    )
    await db_session.commit()
    result = (await worker.run_import(*args, commit=True))["rows"][0]
    assert result["status"] == "update"
    assert result["saved_receipt_verified"]
    assert len((await db_session.execute(select(Snapshot))).scalars().all()) == 1002


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "history,status",
    [
        ("none", "prior_time_unknown"),
        ("within_window", "update"),
        ("outside_window", "prior_time_unknown"),
    ],
)
async def test_canonical_fallback_uses_original_scope_emptiness(
    db_session, monkeypatch, _db_engine, history, status
):
    actor, truck, member, doc, args = await fixture(db_session, monkeypatch, _db_engine)
    start, _ = worker.interval(doc["vehicles"][0])
    truck.last_lat, truck.last_lng, truck.last_location_at = 1, 2, None
    if history != "none":
        captured = start - (
            timedelta(days=40) if history == "outside_window" else timedelta(minutes=2)
        )
        db_session.add(
            history_row(
                actor,
                truck,
                member,
                start,
                observed=start - timedelta(minutes=1),
                captured=captured,
            )
        )
    await db_session.commit()
    result = (await worker.run_import(*args, commit=True))["rows"][0]
    assert result["status"] == status
    await db_session.refresh(truck)
    assert (truck.last_lat, truck.last_lng, truck.last_location_at) == (1, 2, None)


@pytest.mark.asyncio
async def test_old_speed_only_snapshot_gets_location_supplement_then_replays(
    db_session, monkeypatch, _db_engine
):
    actor, truck, member, doc, args = await fixture(db_session, monkeypatch, _db_engine)
    start, _ = worker.interval(doc["vehicles"][0])
    db_session.add_all(
        [
            history_row(
                actor, truck, member, start, observed=start - timedelta(minutes=1)
            )
            for _ in range(1001)
        ]
    )
    await db_session.commit()
    doc["vehicles"][0].update(speed_mph=0, speedText="0 MPH")
    # Reproduce the previous all-history query without changing production code.
    with monkeypatch.context() as old_query:
        old_query.setattr(worker, "relevant_location_history", lambda _: True)
        old_receipt = (await worker.run_import(*args, commit=True))["rows"][0]
    assert old_receipt["location_status"] == "history_review_required"
    assert old_receipt["speed_status"] == "update"
    old_id = old_receipt["snapshot_id"]
    fixed_receipt = (await worker.run_import(*args, commit=True))["rows"][0]
    assert fixed_receipt["location_status"] == "update"
    assert fixed_receipt["speed_status"] == "replay"
    assert fixed_receipt["snapshot_id"] != old_id
    assert fixed_receipt["created"] and fixed_receipt["saved_receipt_verified"]
    saved = (
        (
            await db_session.execute(
                select(Snapshot).where(
                    Snapshot.id.in_([old_id, fixed_receipt["snapshot_id"]])
                )
            )
        )
        .scalars()
        .all()
    )
    assert len(saved) == 2
    assert sum(row.lat is not None for row in saved) == 1
    assert sum(row.speed_mph is not None for row in saved) == 1
    replay = (await worker.run_import(*args, commit=True))["rows"][0]
    assert replay["status"] == "replay" and not replay["created"]
    assert len((await db_session.execute(select(Snapshot))).scalars().all()) == 1003
