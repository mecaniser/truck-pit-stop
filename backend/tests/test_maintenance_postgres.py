"""Real DB134 constraints/transactions on an explicitly allowlisted disposable DB."""
import asyncio
import os
from uuid import UUID, uuid4
import pytest
import pytest_asyncio
from fastapi import HTTPException
from sqlalchemy import select, text, func
from sqlalchemy.engine import make_url
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from app.db.models.maintenance import MaintenanceProgram as Program, MaintenanceProgramEvent as Event
from app.schemas import maintenance as wire
from app.services import maintenance as service
from test_service_checklists import seed
from test_maintenance_programs import config, create

pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture
async def pg():
    raw = os.environ.get('DB134_POSTGRES_TEST_URL')
    if not raw:
        pytest.skip('DB134 isolated PostgreSQL not configured')
    url = make_url(raw)
    if url.host not in {'localhost', '127.0.0.1'} or not (url.database or '').startswith('db134_test_m1_'):
        raise RuntimeError('Only a disposable local db134_test_m1 database is permitted')
    engine = create_async_engine(raw)
    factory = async_sessionmaker(engine, expire_on_commit=False, autoflush=False)
    async with factory() as db:
        data = await seed(db)
    yield factory, data
    await engine.dispose()


async def test_program_event_transaction_and_immutable_evidence(pg):
    factory,a=pg
    async with factory() as db:
        first,_=await create(db,a)
        identity=UUID(first['program']['id'])
        assert await db.scalar(select(func.count(Event.id)).where(Event.program_id==identity))==1
        for sql in [
            'UPDATE maintenance_programs SET name=\'forged\' WHERE id=:id',
            'UPDATE maintenance_programs SET name=\'forged\', version=version+1 WHERE id=:id',
            'DELETE FROM maintenance_programs WHERE id=:id',
            'UPDATE maintenance_program_events SET action=\'forged\' WHERE program_id=:id',
            'DELETE FROM maintenance_program_events WHERE program_id=:id',
        ]:
            with pytest.raises(DBAPIError):
                async with db.begin_nested():
                    await db.execute(text(sql),{'id':identity})
                    await db.execute(text('SET CONSTRAINTS ALL IMMEDIATE'))
        row=await db.get(Program,identity)
        assert row.version==1


async def test_same_key_concurrency_returns_one_identity(pg):
    factory,a=pg
    async with factory() as db:
        from test_maintenance_programs import explicit
        preview=await service.target_preview(db,a.owner,a.vehicle.id,wire.ConfigPreview.model_validate({'purpose':'configuration','channel':'shop','program':None,'config':config(a),'action':'create','seed':explicit(),'reason':None}))
    body=wire.ProgramCreate.model_validate({'channel':'shop','config':config(a),'targets':{'kind':'replace','seed':explicit(),'expected_target_fingerprint':preview['expected_target_fingerprint'],'reason':None}})
    key=str(uuid4())
    async def write():
        async with factory() as db:
            return await service.program_command(db,a.owner,a.vehicle.id,body,key)
    results=await asyncio.wait_for(asyncio.gather(write(),write(),return_exceptions=True),timeout=10)
    successes=[item for item in results if isinstance(item,dict)]
    failures=[item for item in results if isinstance(item,Exception)]
    assert successes
    for failure in failures:
        assert isinstance(failure,HTTPException) and failure.status_code==409
        assert failure.detail=='This shop has another workflow update in progress. Refresh and retry.'
    # The shared financial lock deliberately returns a bounded busy response;
    # an identical retry after the winning commit reconstructs that identity.
    replay=await write()
    assert replay['replayed']
    assert {item['program']['id'] for item in successes}=={replay['program']['id']}
    async with factory() as db:
        assert await db.scalar(select(func.count(Program.id)).where(Program.tenant_id==a.tenant.id))==1


async def test_config_compare_and_swap_serializes(pg):
    factory,a=pg
    async with factory() as db:
        first,_=await create(db,a)
    identity=UUID(first['program']['id'])
    async def write(name):
        async with factory() as db:
            body=wire.ProgramUpdate.model_validate({'channel':'shop','expected_version':1,'config':config(a,name=name),'targets':{'kind':'preserve'}})
            try:
                return await service.program_command(db,a.owner,a.vehicle.id,body,str(uuid4()),program_id=identity)
            except HTTPException as error:
                await db.rollback()
                if isinstance(error.detail,str):
                    assert error.detail=='This shop has another workflow update in progress. Refresh and retry.'
                    return 'busy:' + name
                return error.detail['code']
    results=await asyncio.wait_for(asyncio.gather(write('First'),write('Second')),timeout=10)
    for index,item in enumerate(results):
        if isinstance(item,str) and item.startswith('busy:'):
            results[index]=await write(item.split(':',1)[1])
    assert sum(isinstance(item,dict) for item in results)==1
    assert 'maintenance_version_conflict' in results
    async with factory() as db:
        assert await db.scalar(select(func.count(Event.id)).where(Event.program_id==identity))==2


async def test_atomic_shared_work_claim_race_and_replay(pg):
    from test_maintenance_work import setup
    from app.db.models.maintenance import MaintenanceWorkLink as Link, MaintenanceOperationLink as Mapping
    from app.db.models.labor import Labor
    from app.db.models.inventory import Inventory, PartsUsage
    from app.db.models.repair_order import RepairOrder
    factory, _ = pg
    async with factory() as db:
        a, item, body = await setup(db)
        preview = await service.work_preview(db, a.owner, a.vehicle.id, body)
    command = wire.WorkCommit.model_validate({**body.model_dump(mode='json'), 'expected_work_fingerprint':preview['expected_work_fingerprint']})
    key = str(uuid4())
    async def create_work():
        async with factory() as db:
            return await service.work_command(db,a.owner,a.vehicle.id,command,key)
    raced = await asyncio.wait_for(asyncio.gather(create_work(),create_work(),return_exceptions=True),10)
    assert any(isinstance(value,dict) for value in raced)
    for value in raced:
        if isinstance(value,Exception):
            assert isinstance(value,HTTPException) and value.status_code==409
            assert value.detail=='This shop has another workflow update in progress. Refresh and retry.'
    replay = await create_work()
    assert replay['replayed']
    identity = UUID(replay['repair_order_id'])
    async with factory() as db:
        assert await db.scalar(select(func.count(Link.id)).where(Link.tenant_id==a.tenant.id))==2
        assert await db.scalar(select(func.count(Mapping.id)).where(Mapping.tenant_id==a.tenant.id))==2
        assert await db.scalar(select(func.count(Labor.id)).where(Labor.repair_order_id==identity))==1
        assert await db.scalar(select(func.count(PartsUsage.id)).where(PartsUsage.repair_order_id==identity))==1
        assert (await db.get(Inventory,item.id)).stock_quantity==8
        assert (await db.get(RepairOrder,identity)).total_cost==120


async def test_completion_pending_resolution_and_lifecycle_constraints(pg):
    from test_maintenance_evidence import work, reviewed, actual
    from app.db.models.maintenance import MaintenanceWorkLink as Link, MaintenanceCompletion as Completion
    from app.db.models.repair_order import RepairOrderStatus
    from app.db.models.labor import Labor
    factory,_=pg
    async with factory() as db:
        a,_,order,_=await work(db)
        for operation in (await db.scalars(select(Labor).where(Labor.repair_order_id==order.id))).all():
            operation.execution_status='completed'
            operation.execution_version+=1
        await db.commit()
        review,_=await reviewed(db,a,order,[actual(),actual(None)])
        prepared=await service.prepare_finalization(db,a.owner,order,review,channel='shop')
        order.status=RepairOrderStatus.COMPLETED
        result=await service.finish_finalization(db,a.owner,order,prepared)
        await db.commit()
        assert {item['result'] for item in result['items']}=={'advanced','pending_evidence'}
        link=await db.scalar(select(Link).where(Link.repair_order_id==order.id,Link.state=='pending_evidence'))
        program=await db.get(Program,link.program_id)
        raw={'purpose':'evidence','channel':'shop','program':{'program_id':str(program.id),'expected_version':program.version},
            'evidence':{'action':'resolve_pending','work_link_id':str(link.id),'expected_link_version':link.version,'attestation':actual()}}
        preview=await service.target_preview(db,a.owner,a.vehicle.id,wire.EvidencePreview.model_validate(raw))
        command=wire.EvidenceCommit.model_validate({k:v for k,v in {**raw,'expected_target_fingerprint':preview['expected_target_fingerprint']}.items() if k!='purpose'})
        saved=await service.evidence_command(db,a.owner,a.vehicle.id,command,str(uuid4()))
        assert saved['program']['current_cycle']==2 and saved['completion']['result']=='advanced'
        await service.order_lifecycle(db,a.owner,order,'reopen')
        order.status=RepairOrderStatus.IN_PROGRESS
        await db.commit()
        assert all('source_changed' in row.review_codes for row in (await db.scalars(select(Program).where(Program.tenant_id==a.tenant.id))).all())
        assert await db.scalar(select(func.count(Completion.id)).where(Completion.tenant_id==a.tenant.id))==3
        before=await db.get(Program,program.id)
        assert before.current_cycle==2 and before.target_miles==111000


async def test_late_bundle_failure_rolls_back_entire_order_and_receipt(pg,monkeypatch):
    from test_maintenance_work import setup
    from app.db.models.maintenance import MaintenanceWorkLink as Link
    from app.db.models.repair_order import RepairOrder
    from app.db.models.inventory import Inventory,PartsUsage
    from app.db.models.labor import Labor
    from app.db.models.parts_operations import PartsOperationIdempotency
    from app.services import parts_pricing_planner
    factory,_=pg
    async with factory() as db:
        a,item,body=await setup(db)
        preview=await service.work_preview(db,a.owner,a.vehicle.id,body)
    original=parts_pricing_planner.apply_plan_parts
    async def fail_after_parts(*args,**kwargs):
        await original(*args,**kwargs)
        raise HTTPException(409,{'code':'bundle_availability_changed','message':'Review stock again.'})
    monkeypatch.setattr(parts_pricing_planner,'apply_plan_parts',fail_after_parts)
    async with factory() as db:
        with pytest.raises(HTTPException):
            await service.work_command(db,a.owner,a.vehicle.id,wire.WorkCommit.model_validate({**body.model_dump(mode='json'),'expected_work_fingerprint':preview['expected_work_fingerprint']}),str(uuid4()))
        await db.rollback()
    async with factory() as db:
        assert await db.scalar(select(func.count(RepairOrder.id)).where(RepairOrder.tenant_id==a.tenant.id))==1
        assert await db.scalar(select(func.count(Link.id)).where(Link.tenant_id==a.tenant.id))==0
        assert await db.scalar(select(func.count(PartsUsage.id)).where(PartsUsage.tenant_id==a.tenant.id))==0
        assert await db.scalar(select(func.count(Labor.id)).where(Labor.tenant_id==a.tenant.id))==0
        assert (await db.get(Inventory,item.id)).stock_quantity==10
        assert await db.scalar(select(func.count(PartsOperationIdempotency.id)).where(PartsOperationIdempotency.tenant_id==a.tenant.id,PartsOperationIdempotency.operation_family=='m1_work'))==0


async def test_source_edit_before_recognition_revalidates_after_vehicle_lock(pg):
    from test_external_service import create as external_create, update as external_update
    from test_external_service_postgres import blocked_call
    from app.services import external_service
    from app.db.models.maintenance import MaintenanceCompletion as Completion
    from test_maintenance_evidence import actual
    factory, a = pg
    async with factory() as db:
        record = (await external_service.mutate(db, a.vehicle.id, a.owner, external_create())).record
        await db.commit()
        saved, _ = await create(db, a)
        raw = {'purpose': 'evidence', 'channel': 'shop', 'program': {'program_id': saved['program']['id'], 'expected_version': 1},
            'evidence': {'action': 'recognize', 'source': {'kind': 'external_service', 'id': str(record.id)}, 'attestation': actual()}}
        preview = await service.target_preview(db, a.owner, a.vehicle.id, wire.EvidencePreview.model_validate(raw))
    command = wire.EvidenceCommit.model_validate({k:v for k,v in {**raw,'expected_target_fingerprint':preview['expected_target_fingerprint']}.items() if k!='purpose'})
    async with factory() as writer, factory() as recognition:
        await external_service.mutate(writer, a.vehicle.id, a.owner, external_update(record, odometer=425001), action='update', record_id=record.id)
        with pytest.raises(HTTPException) as error:
            await blocked_call(recognition, service.evidence_command(recognition,a.owner,a.vehicle.id,command,str(uuid4())), writer.commit)
        assert error.value.detail['code'] == 'maintenance_preview_changed'
        await recognition.rollback()
        assert await recognition.scalar(select(func.count(Completion.id)).where(Completion.tenant_id==a.tenant.id)) == 0
        program = await recognition.get(Program, UUID(saved['program']['id']))
        assert program.current_cycle == 1 and program.target_miles == 100000
        fresh = await service.target_preview(recognition,a.owner,a.vehicle.id,wire.EvidencePreview.model_validate(raw))
        command.expected_target_fingerprint = fresh['expected_target_fingerprint']
        accepted = await service.evidence_command(recognition,a.owner,a.vehicle.id,command,str(uuid4()))
        assert accepted['program']['current_cycle'] == 2
    async with factory() as db:
        current = (await external_service.page(db,a.vehicle.id,a.owner)).items[0]
        await external_service.mutate(db,a.vehicle.id,a.owner,external_update(current,description='Corrected after acceptance'),action='update',record_id=current.id)
        await db.commit()
        program = await db.get(Program,UUID(saved['program']['id']))
        assert program.current_cycle == 2 and program.target_miles == 111000 and 'source_changed' in program.review_codes


async def test_config_vs_completion_is_bounded_and_stale_review_cannot_finalize(pg):
    from test_maintenance_evidence import work, reviewed, actual
    from app.db.models.maintenance import MaintenanceCompletion as Completion
    from app.db.models.repair_order import RepairOrder, RepairOrderStatus
    factory, _ = pg
    async with factory() as db:
        a, _, order, _ = await work(db)
        review, _ = await reviewed(db,a,order,[actual(),actual()])
        program = await db.scalar(select(Program).where(Program.tenant_id==a.tenant.id).order_by(Program.id))
        identity, version = program.id, program.version
    body = wire.ProgramUpdate.model_validate({'channel':'shop','expected_version':version,'config':config(a,name='Concurrent display name'),'targets':{'kind':'preserve'}})
    async with factory() as finalizer, factory() as editor:
        await service.pricing.lock_tenant_financials(finalizer,a.tenant.id)
        with pytest.raises(HTTPException) as busy:
            await asyncio.wait_for(service.program_command(editor,a.owner,a.vehicle.id,body,str(uuid4()),program_id=identity),5)
        assert busy.value.status_code == 409 and isinstance(busy.value.detail,str)
        await editor.rollback()
        await finalizer.rollback()
        await service.program_command(editor,a.owner,a.vehicle.id,body,str(uuid4()),program_id=identity)
    async with factory() as db:
        current = await db.get(RepairOrder,order.id)
        with pytest.raises(HTTPException) as stale:
            await service.prepare_finalization(db,a.owner,current,review,channel='shop')
        assert stale.value.detail['code']=='maintenance_preview_changed'
        await db.rollback()
        current = await db.get(RepairOrder,order.id)
        assert current.status == RepairOrderStatus.PENDING_REVIEW
        assert await db.scalar(select(func.count(Completion.id)).where(Completion.tenant_id==a.tenant.id))==0


async def test_merge_and_first_program_serialize_without_identity_transfer(pg):
    from test_external_service import add_vehicle
    from test_external_service_postgres import blocked_call
    from app.services.vehicle_merge import merge_vehicles
    from app.db.models.vehicle import Vehicle
    from sqlalchemy import update
    from test_maintenance_programs import explicit
    factory,a=pg
    async with factory() as db:
        canonical=await add_vehicle(db,a)
        await db.execute(update(Vehicle).where(Vehicle.id==a.vehicle.id).values(vin=canonical.vin))
        await db.commit()
        preview=await service.target_preview(db,a.owner,a.vehicle.id,wire.ConfigPreview.model_validate({'purpose':'configuration','channel':'shop','program':None,'config':config(a),'action':'create','seed':explicit(),'reason':None}))
    body=wire.ProgramCreate.model_validate({'channel':'shop','config':config(a),'targets':{'kind':'replace','seed':explicit(),'expected_target_fingerprint':preview['expected_target_fingerprint'],'reason':None}})
    async with factory() as merge, factory() as creator:
        await merge_vehicles(merge,tenant_id=a.tenant.id,canonical_id=canonical.id,duplicate_id=a.vehicle.id,merged_by_user_id=a.owner.id,confirm_vin=canonical.vin)
        with pytest.raises(HTTPException) as missing:
            await blocked_call(creator,service.program_command(creator,a.owner,a.vehicle.id,body,str(uuid4())),merge.commit)
        assert missing.value.status_code == 404
        await creator.rollback()
        assert await creator.scalar(select(func.count(Program.id)).where(Program.tenant_id==a.tenant.id))==0
    # The inverse ordering preserves the first maintenance identity and refuses
    # the merge before moving existing work or customer relationships.
    async with factory() as db:
        b=await seed(db)
        other=await add_vehicle(db,b)
        await db.execute(update(Vehicle).where(Vehicle.id==b.vehicle.id).values(vin=other.vin))
        await db.commit()
        saved,_=await create(db,b)
        vehicle_id = b.vehicle.id
        with pytest.raises(HTTPException) as blocked:
            await merge_vehicles(db,tenant_id=b.tenant.id,canonical_id=other.id,duplicate_id=b.vehicle.id,merged_by_user_id=b.owner.id,confirm_vin=other.vin)
        assert blocked.value.detail['code']=='maintenance_vehicle_merge_requires_review'
        await db.rollback()
        assert (await db.get(Program,UUID(saved['program']['id']))).vehicle_id==vehicle_id


async def test_price_edit_vs_additive_work_retains_edit_and_requires_fresh_preview(pg,monkeypatch):
    from decimal import Decimal
    from test_maintenance_work import setup
    from app.db.models.labor import Labor
    from app.db.models.repair_order import RepairOrder
    from app.db.models.maintenance import MaintenanceWorkLink as Link
    from app.services.price_build_service import PriceBuildService
    factory,_=pg
    builder=PriceBuildService()
    async with factory() as db:
        a,_,body=await setup(db,existing=True)
        line=Labor(id=uuid4(),tenant_id=a.tenant.id,repair_order_id=a.order.id,description='Saved unrelated labor',
            hours=1,hourly_rate=100,total_cost=100,auto_recalc_enabled=False,execution_status='pending',execution_version=1)
        db.add(line)
        await db.commit()
        await builder.recalculate_order(db,a.order)
        preview=await service.work_preview(db,a.owner,a.vehicle.id,body)
        line_id=line.id
    command=wire.WorkCommit.model_validate({**body.model_dump(mode='json'),'expected_work_fingerprint':preview['expected_work_fingerprint']})
    original=builder.recalculate_order
    async def keep_transaction(db,order,**kwargs):
        return await original(db,order,commit=False)
    monkeypatch.setattr(builder,'recalculate_order',keep_transaction)
    async with factory() as editor,factory() as attaching:
        order=await editor.get(RepairOrder,a.order.id)
        await builder.update_line(editor,order,line_id=line_id,hourly_rate=Decimal(150),actor=a.owner)
        with pytest.raises(HTTPException) as busy:
            await asyncio.wait_for(service.work_command(attaching,a.owner,a.vehicle.id,command,str(uuid4())),5)
        assert busy.value.status_code==409 and isinstance(busy.value.detail,str)
        await attaching.rollback()
        await editor.commit()
        with pytest.raises(HTTPException) as stale:
            await service.work_command(attaching,a.owner,a.vehicle.id,command,str(uuid4()))
        assert stale.value.detail['code']=='maintenance_preview_changed'
        assert stale.value.detail['preview']['totals']['repair_total']=='270.00'
        await attaching.rollback()
        assert (await attaching.get(Labor,line_id)).hourly_rate==150
        assert await attaching.scalar(select(func.count(Link.id)).where(Link.tenant_id==a.tenant.id))==0
        assert (await attaching.get(RepairOrder,a.order.id)).total_cost==150
