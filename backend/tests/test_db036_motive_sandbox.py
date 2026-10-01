"""DB-036 service acceptance using synthetic records and no provider calls."""

import hashlib
import hmac
import json
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, select

from app.db.models.customer import Customer
from app.db.models.motive import (
    MotiveBinding,
    MotiveIngestionReceipt,
    MotiveLocationSample,
)
from app.db.models.tenant import Tenant
from app.db.models.user import User, UserRole
from app.db.models.vehicle import Vehicle
from app.services import motive_sandbox as motive

pytestmark = pytest.mark.asyncio
NOW = datetime(2026, 9, 28, 16, tzinfo=timezone.utc)
SECRET = "db036-synthetic-fixture-signing-secret"


async def seed(db, *, enabled=True, binding=True):
    tenant = Tenant(id=uuid4(), name="Fixture Fleet", slug=uuid4().hex)
    db.add(tenant)
    await db.flush()
    owner = User(
        id=uuid4(),
        tenant_id=tenant.id,
        email=f"{uuid4()}@example.test",
        hashed_password="fixture",
        first_name="Fixture",
        last_name="Owner",
        role=UserRole.GARAGE_OWNER,
        is_active=True,
        is_verified=True,
    )
    customer = Customer(
        id=uuid4(),
        tenant_id=tenant.id,
        company_name="Fixture fleet",
        first_name="Fixture",
        last_name="Customer",
        email="fixture@example.test",
    )
    db.add_all([owner, customer])
    await db.flush()
    truck = Vehicle(
        id=uuid4(),
        tenant_id=tenant.id,
        customer_id=customer.id,
        make="Fixture",
        model="Truck",
        mileage=100,
        last_lat=1,
        last_lng=2,
        driver_name="Manual Driver",
    )
    db.add(truck)
    await db.flush()
    account = await motive.create_fixture_account(
        db, actor=owner, external_company_id="fixture:company"
    )
    if enabled:
        await motive.set_fixture_enabled(
            db, actor=owner, account_id=account.id, enabled=True
        )
    if binding:
        await motive.create_binding(
            db,
            actor=owner,
            account_id=account.id,
            vehicle_id=truck.id,
            provider_vehicle_id="123",
            gateway_id="fixture:gateway",
            valid_from=NOW - timedelta(days=40),
            now=NOW,
        )
    await db.commit()
    return owner, account, truck


def signed(**changes):
    payload = {
        "action": "vehicle_location_updated",
        "id": "fixture:event",
        "vehicle_id": 123,
        "located_at": NOW.isoformat(),
        "lat": 35.1,
        "lon": -80.7,
        "speed": 50,
        "odometer": 541190,
    }
    payload.update(changes)
    body = json.dumps(payload).encode()
    return body, hmac.new(SECRET.encode(), body, hashlib.sha1).hexdigest()


async def ingest(db, account, *, received_at=NOW, **changes):
    body, signature = signed(**changes)
    return await motive.ingest_fixture_location(
        db,
        tenant_id=account.tenant_id,
        account_id=account.id,
        raw_body=body,
        signature=signature,
        fixture_secret=SECRET,
        received_at=received_at,
    )


async def test_default_off_and_manual_fields_preserved(db_session):
    owner, account, truck = await seed(db_session, enabled=False)
    assert not account.enabled
    assert (await ingest(db_session, account)).outcome == "disabled"
    assert (
        await motive.latest_locations(
            db_session, actor=owner, vehicle_ids=[truck.id], now=NOW
        )
        == {}
    )
    await motive.set_fixture_enabled(
        db_session, actor=owner, account_id=account.id, enabled=True
    )
    result = await ingest(db_session, account)
    assert result.outcome == "stored"
    latest = await motive.latest_locations(
        db_session, actor=owner, vehicle_ids=[truck.id], now=NOW
    )
    assert latest[truck.id].id == result.sample_id
    await db_session.refresh(truck)
    assert (truck.mileage, truck.last_lat, truck.last_lng, truck.driver_name) == (
        100,
        1,
        2,
        "Manual Driver",
    )
    await motive.set_fixture_enabled(
        db_session, actor=owner, account_id=account.id, enabled=False
    )
    assert (
        await motive.latest_locations(
            db_session, actor=owner, vehicle_ids=[truck.id], now=NOW
        )
        == {}
    )


async def test_duplicate_other_action_and_conflicting_measurement(db_session):
    _, account, _ = await seed(db_session)
    first = await ingest(db_session, account)
    duplicate = await ingest(
        db_session, account, action="vehicle_location_received", speed=50.0
    )
    conflict = await ingest(db_session, account, lat=36)
    assert (first.outcome, duplicate.outcome, conflict.outcome) == (
        "stored",
        "duplicate",
        "conflict",
    )
    assert duplicate.sample_id == first.sample_id and conflict.sample_id is None
    assert (
        await db_session.scalar(select(func.count()).select_from(MotiveLocationSample))
        == 1
    )
    assert (
        await db_session.scalar(
            select(func.count()).select_from(MotiveIngestionReceipt)
        )
        == 3
    )
    sample = await db_session.get(MotiveLocationSample, first.sample_id)
    assert sample.lat == 35.1


async def test_provider_time_wins_and_equal_time_keeps_first_received(db_session):
    owner, account, truck = await seed(db_session)
    first = await ingest(db_session, account)
    await ingest(
        db_session,
        account,
        id="older",
        located_at=(NOW - timedelta(minutes=1)).isoformat(),
        received_at=NOW + timedelta(seconds=1),
    )
    await ingest(
        db_session,
        account,
        id="same-time",
        lat=40,
        received_at=NOW + timedelta(seconds=2),
    )
    latest = await motive.latest_locations(
        db_session, actor=owner, vehicle_ids=[truck.id], now=NOW
    )
    assert latest[truck.id].id == first.sample_id
    newest = await ingest(
        db_session,
        account,
        id="newer",
        located_at=(NOW + timedelta(seconds=3)).isoformat(),
        received_at=NOW + timedelta(seconds=4),
    )
    latest = await motive.latest_locations(
        db_session, actor=owner, vehicle_ids=[truck.id], now=NOW + timedelta(seconds=4)
    )
    assert latest[truck.id].id == newest.sample_id


async def test_reassignment_uses_historical_interval_and_exact_boundary(db_session):
    owner, account, truck = await seed(db_session)
    second = Vehicle(
        id=uuid4(),
        tenant_id=truck.tenant_id,
        customer_id=truck.customer_id,
        make="Fixture",
        model="Second",
    )
    db_session.add(second)
    await db_session.flush()
    old = await db_session.scalar(
        select(MotiveBinding).where(MotiveBinding.account_id == account.id)
    )
    cutover = NOW - timedelta(hours=1)
    await motive.close_binding(
        db_session,
        actor=owner,
        account_id=account.id,
        binding_id=old.id,
        valid_to=cutover,
        now=NOW,
    )
    new = await motive.create_binding(
        db_session,
        actor=owner,
        account_id=account.id,
        vehicle_id=second.id,
        provider_vehicle_id="123",
        gateway_id="fixture:gateway",
        valid_from=cutover,
        now=NOW,
    )
    late = await ingest(
        db_session,
        account,
        id="late",
        located_at=(cutover - timedelta(seconds=1)).isoformat(),
    )
    current = await ingest(
        db_session, account, id="cutover", located_at=cutover.isoformat()
    )
    assert (
        await db_session.get(MotiveLocationSample, late.sample_id)
    ).binding_id == old.id
    assert (
        await db_session.get(MotiveLocationSample, current.sample_id)
    ).binding_id == new.id


@pytest.mark.parametrize("collision", ["external", "gateway", "truck"])
async def test_overlapping_bindings_fail_closed(db_session, collision):
    owner, account, truck = await seed(db_session)
    other = Vehicle(
        id=uuid4(),
        tenant_id=truck.tenant_id,
        customer_id=truck.customer_id,
        make="Fixture",
        model="Other",
    )
    db_session.add(other)
    await db_session.flush()
    with pytest.raises(motive.MotiveConflict):
        await motive.create_binding(
            db_session,
            actor=owner,
            account_id=account.id,
            vehicle_id=truck.id if collision == "truck" else other.id,
            provider_vehicle_id="123" if collision == "external" else "456",
            gateway_id="fixture:gateway" if collision == "gateway" else None,
            valid_from=NOW,
            now=NOW,
        )


async def test_closed_history_cannot_overlap_or_truncate_accepted_points(db_session):
    owner, account, truck = await seed(db_session)
    await ingest(db_session, account)
    binding = await db_session.scalar(
        select(MotiveBinding).where(MotiveBinding.account_id == account.id)
    )
    with pytest.raises(motive.MotiveConflict):
        await motive.close_binding(
            db_session,
            actor=owner,
            account_id=account.id,
            binding_id=binding.id,
            valid_to=NOW - timedelta(seconds=1),
            now=NOW,
        )
    await motive.close_binding(
        db_session,
        actor=owner,
        account_id=account.id,
        binding_id=binding.id,
        valid_to=NOW + timedelta(seconds=1),
        now=NOW + timedelta(seconds=1),
    )
    with pytest.raises(motive.MotiveConflict):
        await motive.create_binding(
            db_session,
            actor=owner,
            account_id=account.id,
            vehicle_id=truck.id,
            provider_vehicle_id="123",
            gateway_id=None,
            valid_from=NOW,
            now=NOW,
        )


async def test_missing_binding_and_bad_signature_store_receipts_only(db_session):
    _, account, _ = await seed(db_session, binding=False)
    assert (await ingest(db_session, account)).outcome == "unbound"
    body, _ = signed()
    result = await motive.ingest_fixture_location(
        db_session,
        tenant_id=account.tenant_id,
        account_id=account.id,
        raw_body=body,
        signature="0" * 40,
        fixture_secret=SECRET,
        received_at=NOW,
    )
    assert result.outcome == "invalid"
    receipt = await db_session.get(MotiveIngestionReceipt, result.receipt_id)
    assert receipt.signature_state == "rejected"
    assert receipt.event_id is None and receipt.sample_id is None
    assert (
        await db_session.scalar(select(func.count()).select_from(MotiveLocationSample))
        == 0
    )


@pytest.mark.parametrize("offset", [timedelta(days=-31), timedelta(minutes=6)])
async def test_expired_and_future_points_are_rejected(db_session, offset):
    _, account, _ = await seed(db_session)
    result = await ingest(db_session, account, located_at=(NOW + offset).isoformat())
    assert result.outcome == "invalid" and result.sample_id is None


async def test_retention_removes_points_but_replay_does_not_extend_first_receipt(
    db_session,
):
    owner, account, truck = await seed(db_session)
    located_at = (NOW - timedelta(days=29)).isoformat()
    await ingest(db_session, account, located_at=located_at)
    later = NOW + timedelta(days=2)
    assert (
        await motive.latest_locations(
            db_session, actor=owner, vehicle_ids=[truck.id], now=later
        )
        == {}
    )
    assert (
        await motive.purge_expired_fixture_data(
            db_session, tenant_id=account.tenant_id, account_id=account.id, now=later
        )
    )["samples"] == 1
    replay = await ingest(db_session, account, located_at=located_at, received_at=later)
    assert replay.outcome == "duplicate" and replay.sample_id is None
    much_later = NOW + timedelta(days=31)
    await motive.purge_expired_fixture_data(
        db_session, tenant_id=account.tenant_id, account_id=account.id, now=much_later
    )
    assert (
        await ingest(db_session, account, located_at=located_at, received_at=much_later)
    ).outcome == "invalid"


async def test_tenant_collisions_are_isolated_and_foreign_resources_are_not_found(
    db_session,
):
    owner, account, truck = await seed(db_session)
    other_owner, other_account, other_truck = await seed(db_session)
    assert (await ingest(db_session, account)).outcome == "stored"
    assert (await ingest(db_session, other_account)).outcome == "stored"
    visible = await motive.latest_locations(
        db_session, actor=owner, vehicle_ids=[truck.id, other_truck.id], now=NOW
    )
    assert list(visible) == [truck.id]
    for inaccessible in [other_account.id, uuid4()]:
        with pytest.raises(motive.MotiveNotFound, match="Motive resource not found"):
            await motive.set_fixture_enabled(
                db_session, actor=owner, account_id=inaccessible, enabled=True
            )
    with pytest.raises(motive.MotiveNotFound):
        await motive.create_binding(
            db_session,
            actor=owner,
            account_id=account.id,
            vehicle_id=other_truck.id,
            provider_vehicle_id="789",
            gateway_id=None,
            valid_from=NOW,
            now=NOW,
        )
    other_owner.is_active = False
    await db_session.flush()
    with pytest.raises(motive.MotiveNotFound):
        await motive.latest_locations(
            db_session, actor=other_owner, vehicle_ids=[other_truck.id], now=NOW
        )


@pytest.mark.parametrize(
    "role", [UserRole.CUSTOMER, UserRole.FLEET_MANAGER, UserRole.MECHANIC]
)
async def test_non_admin_cannot_manage_connection(db_session, role):
    owner, account, _ = await seed(db_session)
    owner.role = role
    await db_session.flush()
    with pytest.raises(motive.MotiveNotFound):
        await motive.set_fixture_enabled(
            db_session, actor=owner, account_id=account.id, enabled=True
        )


async def test_deleted_account_or_vehicle_is_inaccessible(db_session):
    owner, account, truck = await seed(db_session)
    truck.deleted_at = NOW
    await db_session.flush()
    assert (await ingest(db_session, account)).outcome == "unbound"
    account.deleted_at = NOW
    await db_session.flush()
    with pytest.raises(motive.MotiveNotFound):
        await ingest(db_session, account)
    assert (
        await motive.latest_locations(
            db_session, actor=owner, vehicle_ids=[truck.id], now=NOW
        )
        == {}
    )


async def test_retention_still_purges_a_deleted_account_and_inactive_tenant(db_session):
    owner, account, _ = await seed(db_session)
    await ingest(db_session, account)
    tenant = await db_session.get(Tenant, owner.tenant_id)
    tenant.is_active = False
    account.deleted_at = NOW
    await db_session.flush()
    with pytest.raises(motive.MotiveNotFound):
        await ingest(db_session, account)
    result = await motive.purge_expired_fixture_data(
        db_session,
        tenant_id=account.tenant_id,
        account_id=account.id,
        now=NOW + timedelta(days=31),
    )
    assert result == {"samples": 1, "receipts": 1}


async def test_signed_malformed_event_is_recorded_without_aborting_ingestion(
    db_session,
):
    _, account, _ = await seed(db_session)
    body = b'{"id":' + b"1" * 5000 + b"}"
    signature = hmac.new(SECRET.encode(), body, hashlib.sha1).hexdigest()
    result = await motive.ingest_fixture_location(
        db_session,
        tenant_id=account.tenant_id,
        account_id=account.id,
        raw_body=body,
        signature=signature,
        fixture_secret=SECRET,
        received_at=NOW,
    )
    receipt = await db_session.get(MotiveIngestionReceipt, result.receipt_id)
    assert result.outcome == "invalid" and receipt.signature_state == "verified"
    assert receipt.reason == "invalid_event" and receipt.event_id is None


async def test_identical_timestamps_use_acceptance_order_not_random_uuid(
    db_session, monkeypatch
):
    owner, account, truck = await seed(db_session)
    ids = iter(UUID(int=n) for n in (100, 200, 300, 1))
    monkeypatch.setattr(motive, "uuid4", lambda: next(ids))
    first = await ingest(db_session, account, id="first", lat=35)
    second = await ingest(db_session, account, id="second", lat=40)
    assert second.sample_id.int < first.sample_id.int
    latest = await motive.latest_locations(
        db_session, actor=owner, vehicle_ids=[truck.id], now=NOW
    )
    assert latest[truck.id].id == first.sample_id


@pytest.mark.parametrize("identifier", ["fixture:\x00bad", "fixture:\ud800bad"])
async def test_unrepresentable_binding_identifier_fails_before_database(
    db_session, identifier
):
    owner, account, truck = await seed(db_session, binding=False)
    with pytest.raises(ValueError, match="invalid provider identifier"):
        await motive.create_binding(
            db_session,
            actor=owner,
            account_id=account.id,
            vehicle_id=truck.id,
            provider_vehicle_id=identifier,
            gateway_id=None,
            valid_from=NOW,
            now=NOW,
        )
