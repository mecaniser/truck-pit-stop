"""Private reviewed placeholder trips preserve immutable and SQL tenant gates."""
import copy
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from pydantic import ValidationError
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker
from app.db.models.fleet_trip import FleetTrip
from app.schemas.fleet_trip import TripImport
from app.services import fleet_trips
from scripts import import_motive_trips as importer
from scripts.motive_sync import trip_runner as worker
from tests.test_dashboard_vehicle_bindings import setup
from tests.test_motive_trip_worker import source
from tests.motive_populated_fixture import prove


async def bound_fixture(db, monkeypatch):
    actor, vehicle, member, binding, _ = await setup(db, monkeypatch, expires=False)
    binding.source_company_id = 'KT8934277'
    binding.source_company_label = '77 CARGO LLC'
    binding.provider_vehicle_id = '5981300'
    binding.reviewed_at = binding.effective_from = datetime.now(timezone.utc) - timedelta(days=5)
    member.effective_from = datetime.now(timezone.utc) - timedelta(days=7)
    await db.commit()
    document = source()
    document['vehicles'][0].update(provider_vehicle_id='5981300', vin=None,
        source_vin_state='not_displayed',
        identity_before={'vin': None, 'source_vin_state': 'not_displayed', 'read_at': document['started_at']},
        identity_after={'vin': None, 'source_vin_state': 'not_displayed', 'read_at': document['finished_at']})
    document['windows'][0]['rows'][0]['links'] = ['#/fleetview/vehicles/summary/5981300']
    prove(document['windows'][0])
    return actor, vehicle, member, binding, document


@pytest.mark.asyncio
async def test_bound_worker_replay_private_only_and_sql_visibility(_db_engine, db_session, monkeypatch, tmp_path):
    actor, vehicle, member, binding, document = await bound_fixture(db_session, monkeypatch)
    factory = async_sessionmaker(_db_engine, expire_on_commit=False)
    args = (factory, document, actor.tenant_id, actor.id, '77 CARGO LLC', 'KT8934277')
    receipt = await worker.run(*args, tmp_path/'receipt.json', True)
    assert receipt['committed'] and receipt['readback_verified'] == 1
    replay = await worker.run(*args, tmp_path/'receipt.json', True)
    assert replay['rows'][0]['action'] == 'unchanged'
    assert replay['rows'][0]['trip_id'] == receipt['rows'][0]['trip_id']
    trip = (await db_session.execute(select(FleetTrip))).scalar_one()
    assert trip.verified_vin is None and trip.dashboard_binding_id == binding.id
    payload = worker.prior_payload(trip)
    with pytest.raises(ValidationError):
        TripImport.model_validate(payload)
    with pytest.raises(ValidationError):
        importer.parse_rows({'rows':[payload]}, datetime.now(timezone.utc))
    day = trip.started_at.date()
    view = await fleet_trips.list_trips(db_session, actor.tenant_id, day, day, 'UTC', limit=1)
    assert view['total'] == view['summary']['trip_count'] == 1
    assert view['items'][0]['vehicle_identity_basis'] == 'reviewed_provider_binding'
    foreign = await fleet_trips.list_trips(db_session, uuid4(), day, day, 'UTC')
    assert foreign['total'] == 0
    binding.revoked_at = datetime.now(timezone.utc)
    await db_session.flush()
    view = await fleet_trips.list_trips(db_session, actor.tenant_id, day, day, 'UTC', limit=1)
    assert view['total'] == view['summary']['trip_count'] == 0
    assert view['items'] == [] and view['imported_start'] is None and view['imported_end'] is None


@pytest.mark.asyncio
@pytest.mark.parametrize('bad', ['missing_proof', 'changed_vin', 'unbracketed', 'wrong_company'])
async def test_placeholder_source_fails_closed(db_session, monkeypatch, bad):
    actor, _, _, _, document = await bound_fixture(db_session, monkeypatch)
    item = document['vehicles'][0]
    if bad == 'missing_proof': item.pop('identity_before')
    if bad == 'changed_vin': item['identity_after']['vin'] = '1M8GDM9AXKP042788'
    if bad == 'unbracketed': item['identity_before']['read_at'] = document['finished_at']
    if bad == 'wrong_company': document['company_id'] = 'other'
    with pytest.raises(ValueError):
        await worker.prepare(db_session, document, actor.tenant_id, actor.id, datetime.now(timezone.utc))


@pytest.mark.asyncio
@pytest.mark.parametrize('bad', ['pre_binding', 'pre_membership', 'revoked', 'expired', 'placeholder_changed', 'foreign_binding'])
async def test_bound_import_revalidates_interval_and_identity(db_session, monkeypatch, bad):
    actor, vehicle, member, binding, document = await bound_fixture(db_session, monkeypatch)
    prepared = await worker.prepare(db_session, document, actor.tenant_id, actor.id, datetime.now(timezone.utc))
    # Preparation never grants future import authority: importer resolves again.
    rows = importer.parse_rows({'rows': prepared[0]}, datetime.now(timezone.utc), allow_binding=True)
    if bad == 'pre_binding': binding.effective_from = rows[0].started_at + timedelta(seconds=1)
    if bad == 'pre_membership': member.effective_from = rows[0].started_at + timedelta(seconds=1)
    if bad == 'revoked': binding.revoked_at = datetime.now(timezone.utc)
    if bad == 'expired': binding.effective_to = rows[0].ended_at
    if bad == 'placeholder_changed': vehicle.vin = '1M8GDM9AXKP042788'
    if bad == 'foreign_binding': rows[0].dashboard_binding_id = uuid4()
    await db_session.flush()
    with pytest.raises((ValueError, HTTPException)):
        await importer.run_import(db_session, rows, actor.tenant_id, actor.id, True, allow_binding=True)
    assert (await db_session.execute(select(FleetTrip))).scalars().all() == []


@pytest.mark.asyncio
async def test_coverage_scope_ignores_observation_times_but_tracks_binding(db_session, monkeypatch):
    actor, _, _, binding, document = await bound_fixture(db_session, monkeypatch)
    document['plan'] = {'scope': {'tenant_id': str(actor.tenant_id)}}
    document['windows'][0]['end'] = document['windows'][0]['start']
    async def checksum(doc):
        return (await worker.prepare(db_session, doc, actor.tenant_id, actor.id, datetime.now(timezone.utc)))[1]['coverage']['mapping_sha256']
    first = await checksum(document)
    updated = copy.deepcopy(document)
    updated['vehicles'][0]['identity_before']['read_at'] = (datetime.fromisoformat(document['started_at']) + timedelta(seconds=1)).isoformat()
    updated['vehicles'][0]['identity_after']['read_at'] = (datetime.fromisoformat(document['finished_at']) - timedelta(seconds=1)).isoformat()
    assert await checksum(updated) == first
    binding.effective_from += timedelta(seconds=1)
    await db_session.flush()
    assert await checksum(updated) != first
    changed = copy.deepcopy(document)
    changed['vehicles'][0]['source_vin_state'] = 'explicitly_empty'
    for key in ('identity_before', 'identity_after'):
        changed['vehicles'][0][key]['source_vin_state'] = 'explicitly_empty'
    assert await checksum(changed) != await checksum(updated)


def test_migration_upgrade_sql_and_postwrite_downgrade_guard(monkeypatch):
    import importlib.util
    import io
    from pathlib import Path
    from types import SimpleNamespace
    from alembic.migration import MigrationContext
    from alembic.operations import Operations
    path = Path(__file__).parents[1] / 'alembic/versions/189_trip_reviewed_binding.py'
    spec = importlib.util.spec_from_file_location('trip_binding_migration', path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    sql = io.StringIO()
    context = MigrationContext.configure(dialect_name='postgresql', opts={'as_sql': True, 'output_buffer': sql})
    monkeypatch.setattr(migration, 'op', Operations(context))
    migration.upgrade()
    ddl = sql.getvalue()
    assert 'DROP NOT NULL' in ddl and 'ck_trip_identity_xor' in ddl and 'fk_trip_dashboard_binding' in ddl
    monkeypatch.setattr(migration, 'op', SimpleNamespace(get_bind=lambda: SimpleNamespace(execute=lambda _: SimpleNamespace(first=lambda: (1,)))))
    with pytest.raises(RuntimeError, match='Bound trip history exists'):
        migration.downgrade()
