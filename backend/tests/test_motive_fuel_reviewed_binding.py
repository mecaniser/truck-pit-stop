"""Private reviewed fuel identity preserves immutable VIN history and SQL scope."""
import importlib.util
import io
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker
from app.db.models.fleet_fuel import FleetFuelDaily
from app.schemas.fleet_fuel import FuelDailyImport, FuelDailyPage
from app.services import fleet_fuel
from scripts import import_motive_daily_fuel as importer
from scripts.motive_sync import fuel_coverage, fuel_runner as worker
from scripts.motive_sync.trip_runner import immutable_json
from tests.test_dashboard_vehicle_bindings import setup
from tests.test_motive_fuel_catchup import daily
from tests.test_motive_fuel_worker import source


async def bound_fixture(db, monkeypatch):
    actor, vehicle, member, binding, _ = await setup(db, monkeypatch, expires=False)
    stamp = importer.now()
    vehicle.unit_number = '26'
    binding.source_company_id = 'KT8934277'
    binding.source_company_label = '77 CARGO LLC'
    binding.provider_vehicle_id = '5981300'
    binding.reviewed_at = binding.effective_from = stamp - timedelta(days=10)
    member.effective_from = stamp - timedelta(days=30)
    await db.commit()
    expected = fuel_coverage.scope(actor.tenant_id, actor.id, 'KT8934277', '77 CARGO LLC')
    document = daily(expected, worker.completed_dates(stamp)[0], stamp)
    vehicle_source = document['vehicles'][0]
    vehicle_source.update(provider_vehicle_id='5981300', unit='26', vin=None, source_vin_state='not_displayed')
    proof = document['reports'][0]
    proof.update(provider_vehicle_id='5981300', selected_unit='26', report_url=proof['report_url'].replace('vehicle_ids=123','vehicle_ids=5981300'))
    for record in vehicle_source['records']:
        for field, moment in [('identity_before',document['started_at']),('identity_after',document['finished_at'])]:
            record[field] = dict(vin=None,source_vin_state='not_displayed',provider_vehicle_id='5981300',unit='26',source_url='https://app.gomotive.com/en-US/#/fleetview/vehicles/summary/5981300',read_at=moment)
    return actor, vehicle, member, binding, document


@pytest.mark.asyncio
async def test_bound_capture_replay_recovery_and_revoked_api(_db_engine,db_session,monkeypatch,tmp_path):
    actor, _, _, binding, document = await bound_fixture(db_session,monkeypatch)
    factory=async_sessionmaker(_db_engine,expire_on_commit=False)
    folder=tmp_path/document['plan']['run_id']/document['report_dates'][0]
    folder.mkdir(parents=True)
    immutable_json(folder/'source.json',document)
    args=(factory,document,actor.tenant_id,actor.id,'77 CARGO LLC','KT8934277',folder/'receipt.json')
    receipt=await worker.run(*args,commit=True,plan=document['plan'])
    assert receipt['committed'] and receipt['readback_verified']==receipt['replay_unchanged']==1
    proof=fuel_coverage.validate_receipt(folder/'receipt.json',document['plan']['scope'])
    assert proof['status']=='verified' and len(proof['matrix'])==1
    fuel=(await db_session.execute(select(FleetFuelDaily))).scalar_one()
    assert fuel.verified_vin is None and fuel.dashboard_binding_id==binding.id
    row=worker.stored_payload(fuel).model_dump(mode='json')
    with pytest.raises(ValidationError):FuelDailyImport.model_validate(row)
    with pytest.raises(ValidationError):importer.parse_rows({'rows':[row]},importer.now())
    replay=await worker.run(*args,commit=True,recovery=True)
    assert replay['rows'][0]['action']=='unchanged' and replay['rows'][0]['fuel_id']==str(fuel.id)
    day=fuel.report_date
    parsed=FuelDailyPage.model_validate(await fleet_fuel.list_fuel_daily(db_session,actor.tenant_id,day,day))
    assert parsed.total==1 and parsed.items[0].vehicle_identity_basis=='reviewed_provider_binding'
    assert parsed.items[0].vehicle_identity_binding_id==binding.id
    assert (await fleet_fuel.list_fuel_daily(db_session,uuid4(),day,day))['total']==0
    binding.revoked_at=importer.now();await db_session.flush()
    assert (await fleet_fuel.list_fuel_daily(db_session,actor.tenant_id,day,day))['total']==0
    with pytest.raises(HTTPException):await worker.batches(db_session,[row],actor.tenant_id,actor.id,True)


@pytest.mark.asyncio
@pytest.mark.parametrize('bad',['missing_before','missing_after','changed_vin','state_changed','foreign_url','wrong_provider','wrong_unit','late_before'])
async def test_source_identity_proof_fails_closed(db_session,monkeypatch,bad):
    _,_,_,_,document=await bound_fixture(db_session,monkeypatch)
    r=document['vehicles'][0]['records'][0]
    if bad=='missing_before':r.pop('identity_before')
    if bad=='missing_after':r.pop('identity_after')
    if bad=='changed_vin':r['identity_after']['vin']='1M8GDM9AXKP042788'
    if bad=='state_changed':r['identity_after']['source_vin_state']='explicitly_empty'
    if bad=='foreign_url':r['identity_after']['source_url']='https://evil.invalid/'
    if bad=='wrong_provider':r['identity_after']['provider_vehicle_id']='other'
    if bad=='wrong_unit':r['identity_after']['unit']='other'
    if bad=='late_before':r['identity_before']['read_at']=document['finished_at']
    with pytest.raises(ValueError):worker.validate_source(document,'77 CARGO LLC','KT8934277',importer.now())


@pytest.mark.asyncio
@pytest.mark.parametrize('bad',['pre_binding','pre_membership','revoked','ended_during_day','placeholder_changed','foreign_binding','foreign_tenant','foreign_company','foreign_provider'])
async def test_private_import_revalidates_full_identity_and_interval(db_session,monkeypatch,bad):
    actor,vehicle,member,binding,document=await bound_fixture(db_session,monkeypatch)
    rows,_=await worker.prepare(db_session,document,actor.tenant_id,actor.id)
    parsed=importer.parse_rows({'rows':rows},importer.now(),allow_binding=True)
    start,end=parsed[0].membership_window();tenant=actor.tenant_id
    if bad=='pre_binding':binding.effective_from=start+timedelta(seconds=1)
    if bad=='pre_membership':member.effective_from=start+timedelta(seconds=1)
    if bad=='revoked':binding.revoked_at=importer.now()
    if bad=='ended_during_day':binding.effective_to=end-timedelta(seconds=1)
    if bad=='placeholder_changed':vehicle.vin='1M8GDM9AXKP042788'
    if bad=='foreign_binding':parsed[0].dashboard_binding_id=uuid4()
    if bad=='foreign_tenant':tenant=uuid4()
    if bad=='foreign_company':parsed[0].provider_company_id='KT999'
    if bad=='foreign_provider':parsed[0].provider_vehicle_id='999'
    await db_session.flush()
    with pytest.raises((ValueError,HTTPException,ValidationError)):
        await importer.run_import(db_session,parsed,tenant,actor.id,True,allow_binding=True)
    assert (await db_session.execute(select(FleetFuelDaily))).scalars().all()==[]


@pytest.mark.asyncio
async def test_old_missing_vin_source_not_retroactively_promoted(db_session,monkeypatch):
    actor,_,_,_,document=await bound_fixture(db_session,monkeypatch)
    v=document['vehicles'][0];v.pop('source_vin_state')
    for r in v['records']:r.pop('identity_before');r.pop('identity_after')
    worker.validate_source(document,'77 CARGO LLC','KT8934277',importer.now())
    rows,report=await worker.prepare(db_session,document,actor.tenant_id,actor.id)
    assert rows==[] and any(x['reason']=='vin_unavailable' for x in report['exclusions'])


def test_legacy_vin_schema_digest_unchanged():
    doc=source();row=worker.payload(doc,doc['vehicles'][0],doc['vehicles'][0]['records'][0])
    assert 'dashboard_binding_id' not in row.model_dump() and row.vin
    repeated=FuelDailyImport.model_validate(row.model_dump(mode='json'))
    assert importer.digest(repeated)==importer.digest(row)
    assert importer.parse_rows({'rows':[row.model_dump(mode='json')]},importer.now())[0]==row


def test_migration_sql_and_bound_history_downgrade_guard(monkeypatch):
    path=Path(__file__).parents[1]/'alembic/versions/191_fuel_reviewed_binding.py'
    spec=importlib.util.spec_from_file_location('fuel_binding_migration',path);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    output=io.StringIO();ctx=MigrationContext.configure(dialect_name='postgresql',opts={'as_sql':True,'output_buffer':output})
    monkeypatch.setattr(module,'op',Operations(ctx));module.upgrade();ddl=output.getvalue()
    assert 'DROP NOT NULL' in ddl and 'ck_fuel_identity_xor' in ddl and 'fk_fuel_dashboard_binding' in ddl
    monkeypatch.setattr(module,'op',SimpleNamespace(get_bind=lambda:SimpleNamespace(execute=lambda _:SimpleNamespace(first=lambda:(1,)))))
    with pytest.raises(RuntimeError,match='Bound fuel history exists'):module.downgrade()


@pytest.mark.asyncio
async def test_coverage_tracks_binding_and_source_state_not_read_times(db_session,monkeypatch):
    import copy
    actor,_,_,binding,document=await bound_fixture(db_session,monkeypatch)
    async def fingerprint(doc):return (await worker.prepare(db_session,doc,actor.tenant_id,actor.id))[1]['mapping_sha256']
    initial=await fingerprint(document)
    changed=copy.deepcopy(document)
    changed['vehicles'][0]['records'][0]['identity_before']['read_at']=changed['vehicles'][0]['records'][0]['source_read_at']
    assert await fingerprint(changed)==initial
    changed['vehicles'][0]['source_vin_state']='explicitly_empty'
    for key in ('identity_before','identity_after'):changed['vehicles'][0]['records'][0][key]['source_vin_state']='explicitly_empty'
    assert await fingerprint(changed)!=initial
    binding.effective_from+=timedelta(seconds=1);await db_session.flush()
    assert await fingerprint(document)!=initial


@pytest.mark.asyncio
async def test_missing_reading_never_imports_zero_and_old_date_cannot_be_backdated(db_session,monkeypatch):
    actor,_,_,binding,document=await bound_fixture(db_session,monkeypatch)
    record=document['vehicles'][0]['records'][0]
    record.update(state='source_missing',reason='explicit_no_results')
    for key in worker.MEASUREMENTS:record.pop(key,None)
    rows,report=await worker.prepare(db_session,document,actor.tenant_id,actor.id)
    assert rows==[] and len(report['exclusions'])==1 and report['exclusions'][0]['reason']=='explicit_no_results'
    record.update(state='reported',driving_fuel_gallons='30',idling_fuel_gallons='2.1',reported_total_fuel_gallons='32.1')
    binding.effective_from=importer.now()-timedelta(days=1);await db_session.flush()
    rows,report=await worker.prepare(db_session,document,actor.tenant_id,actor.id)
    assert rows==[] and any('full fuel date' in x['reason'] for x in report['exclusions'])
