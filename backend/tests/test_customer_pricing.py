"""C1 configuration, pinning and writer regression tests under production session semantics."""
from decimal import Decimal as D
from types import SimpleNamespace as NS
from uuid import uuid4, UUID
import pytest
from fastapi import HTTPException
from sqlalchemy import select, func
from app.db.models.customer import Customer
from app.db.models.customer_pricing import AccountPricingEvent
from app.db.models.user import UserRole
from app.services import customer_pricing as account
from app.api.v1.endpoints import customer_pricing as api, parts_pricing as parts_api
from app.schemas.customer_pricing import CustomerPricingWrite
from app.schemas.parts_pricing import MatrixCreate
from test_parts_pricing import BANDS
from test_repair_order_ad_hoc_parts import _seed

@pytest.fixture
def db_session(db_session):
    db_session.autoflush=False
    return db_session

async def setup(db):
    tenant,actor,order=await _seed(db,role=UserRole.GARAGE_OWNER)
    tenant.labor_rate=D('145');await db.commit()
    customer=await db.get(Customer,order.customer_id)
    return NS(tenant=tenant,actor=actor,order=order,customer=customer)

@pytest.mark.asyncio
async def test_customer_policy_foundation(db_session):
    a=await setup(db_session)
    view=await api.get_policy(a.customer.id,db_session,a.actor)
    assert view['version']==0 and view['effective']['labor']=={'source':'shop','rate':'145.00'}
    matrix=(await parts_api.create_matrix(MatrixCreate(name='Account matrix',bands=BANDS),str(uuid4()),db_session,a.actor))['matrix']
    body=CustomerPricingWrite(expected_version=0,labor_rate='125',parts_matrix_id=matrix['id'],reason='Agreed account terms')
    key=str(uuid4());first=await api.put_policy(a.customer.id,body,key,db_session,a.actor)
    assert first==await api.put_policy(a.customer.id,body,key,db_session,a.actor)
    assert first['version']==1 and first['effective']['labor']['rate']=='125.00'
    assert await db_session.scalar(select(func.count(AccountPricingEvent.id)))==1
    snapshot,preview=await account.capture(db_session,a.actor,a.customer.id,a.order.vehicle_id)
    assert snapshot['labor']=={'source':'customer','rate':'125.00'} and snapshot['parts']['matrix']['revision_id']==matrix['current_revision_id']
    assert 'matrix' not in preview['parts']
    a.actor.role=UserRole.RECEPTIONIST
    with pytest.raises(HTTPException) as exc:await api.put_policy(a.customer.id,body,key,db_session,a.actor)
    assert exc.value.status_code==403

async def configure(db,a,rate='125',matrix_id=None,version=0):
    return await api.put_policy(a.customer.id,CustomerPricingWrite(expected_version=version,labor_rate=rate,parts_matrix_id=matrix_id,reason='Synthetic agreed terms'),str(uuid4()),db,a.actor)

async def create_order(db,a,**changes):
    from app.api.v1.endpoints import repair_orders as ro
    from app.schemas.repair_order import RepairOrderCreate
    return await ro.create_repair_order(RepairOrderCreate(**{'customer_id':a.customer.id,'vehicle_id':a.order.vehicle_id,**changes}),db,a.actor)

@pytest.mark.parametrize('rate',['0','-1','NaN','Infinity','1.001','100000000'])
def test_account_default_requires_positive_finite_cents(rate):
    from pydantic import ValidationError
    with pytest.raises(ValidationError):CustomerPricingWrite(expected_version=0,labor_rate=rate,parts_matrix_id=None,reason='Agreement')

@pytest.mark.asyncio
async def test_config_noop_aba_history_cursor_and_missing_evidence(db_session):
    a=await setup(db_session)
    await configure(db_session,a)
    assert (await configure(db_session,a,version=1))['version']==1
    await configure(db_session,a,rate=None,version=1)
    await configure(db_session,a,version=2)
    with pytest.raises(HTTPException) as exc:await configure(db_session,a,rate='135',version=1)
    assert exc.value.detail['code']=='customer_pricing_conflict'
    history=await api.history(a.customer.id,1,None,db_session,a.actor)
    assert history['items'][0]['version']==3 and history['next_cursor']
    second=await api.history(a.customer.id,1,history['next_cursor'],db_session,a.actor)
    assert second['items'][0]['version']==2
    b=await setup(db_session)
    with pytest.raises(HTTPException) as exc:await api.history(b.customer.id,1,history['next_cursor'],db_session,b.actor)
    assert exc.value.detail['code']=='invalid_cursor'
    a.customer.pricing_version=9;await db_session.flush()
    with pytest.raises(HTTPException) as exc:await account.candidate(db_session,a.tenant,a.customer)
    assert exc.value.detail['code']=='account_pricing_unverified'

@pytest.mark.asyncio
async def test_intake_pins_exact_policy_and_does_not_adopt_changed_agreement_or_shop(db_session):
    from app.db.models.repair_order import RepairOrder
    from app.api.v1.endpoints import repair_orders as ro
    from app.schemas.repair_order import LaborCreate,QuickRepairOrderCreate
    a=await setup(db_session);await configure(db_session,a)
    preview=await api.intake_preview(a.customer.id,a.order.vehicle_id,None,db_session,a.actor)
    first=await create_order(db_session,a,expected_pricing_policy=preview['expected_pricing_policy'])
    firstrow=await db_session.get(RepairOrder,first.id)
    assert first.pricing_policy['labor']['rate']=='125.00'
    await configure(db_session,a,rate='135',version=1);a.tenant.labor_rate=D('155');await db_session.commit()
    saved=await ro.add_labor_to_repair_order(first.id,LaborCreate(description='Later attachment',hours=1),db_session,a.actor)
    assert saved.hourly_rate==125 and saved.pricing['source']=='customer'
    with pytest.raises(HTTPException) as exc:await create_order(db_session,a,expected_pricing_policy=preview['expected_pricing_policy'])
    assert exc.value.detail['code']=='account_pricing_changed'
    second=await create_order(db_session,a)
    assert second.pricing_policy['labor']['rate']=='135.00'
    legacy=await ro.add_labor_to_repair_order(a.order.id,LaborCreate(description='Legacy new line',hours=1),db_session,a.actor)
    assert legacy.hourly_rate==155 and (await db_session.get(RepairOrder,a.order.id)).pricing_policy_snapshot is None
    a.customer.phone='5550001111';await db_session.commit()
    quick=await ro.quick_create_repair_order(QuickRepairOrderCreate(phone='5550001111',complaint='Synthetic quick'),db_session,a.actor)
    assert quick.customer_id==a.customer.id and quick.pricing_policy['labor']['rate']=='135.00'
    assert firstrow.pricing_policy_snapshot['labor']['rate']=='125.00'

@pytest.mark.asyncio
async def test_saved_service_override_survives_reapply_and_recalculate_even_enabled(db_session):
    from app.api.v1.endpoints import repair_orders as ro
    from app.db.models.service import Service
    from app.services.price_build_service import PriceBuildService
    from app.schemas.repair_order import LaborCreate
    a=await setup(db_session);await configure(db_session,a);created=await create_order(db_session,a)
    service=Service(tenant_id=a.tenant.id,name='C1 synthetic service',duration_minutes=60,is_active=True);db_session.add(service);await db_session.commit()
    svc=PriceBuildService();order=await svc.load_order(db_session,created.id)
    first=await svc.add_flat_service_line(db_session,order,service.id,actor=a.actor)
    line=first.order.labor_items[0];origin=line.pricing_snapshot.copy();assert line.hourly_rate==125
    changed=await svc.update_line(db_session,first.order,line_id=line.id,hourly_rate=D('111'),auto_recalc_enabled=True,actor=a.actor)
    assert changed.order.labor_items[0].pricing_source=='manual'
    await configure(db_session,a,rate='160',version=1)
    reapplied=await svc.add_flat_service_line(db_session,changed.order,service.id,quantity=2,actor=a.actor)
    retained=reapplied.order.labor_items[0]
    assert retained.id==line.id and retained.hourly_rate==111 and retained.hours==2 and retained.total_cost==222
    assert retained.pricing_source=='manual' and retained.pricing_snapshot==origin and retained.auto_recalc_enabled
    manual=await ro.add_labor_to_repair_order(created.id,LaborCreate(description='Explicit zero',hours=1,hourly_rate=0,pricing_intent='manual'),db_session,a.actor)
    assert manual.hourly_rate==0 and manual.pricing['current_source']=='manual'
    default=await ro.add_labor_to_repair_order(created.id,LaborCreate(description='Echoed stale shop',hours=1,hourly_rate=145,pricing_intent='default'),db_session,a.actor)
    assert default.hourly_rate==125 and default.pricing['current_source']=='default'

@pytest.mark.asyncio
async def test_pinned_part_revision_survives_archive_and_new_orders_use_new_policy(db_session):
    from app.api.v1.endpoints import repair_orders as ro
    from app.db.models.inventory import Inventory
    from app.schemas import parts_pricing as ps
    from app.schemas.repair_order import PartsUsageCreate
    from app.services.parts_pricing_planner import build_plan
    a=await setup(db_session)
    matrix=(await parts_api.create_matrix(MatrixCreate(name='Account matrix',bands=BANDS),str(uuid4()),db_session,a.actor))['matrix']
    await configure(db_session,a,matrix_id=matrix['id']);created=await create_order(db_session,a)
    with pytest.raises(HTTPException) as exc:await parts_api.archive_matrix(UUID(matrix['id']),ps.MatrixArchive(expected_version=1),str(uuid4()),db_session,a.actor)
    assert exc.value.detail['code']=='matrix_assigned_to_customer'
    await configure(db_session,a,rate=None,matrix_id=None,version=1)
    await parts_api.archive_matrix(UUID(matrix['id']),ps.MatrixArchive(expected_version=1),str(uuid4()),db_session,a.actor)
    part=Inventory(tenant_id=a.tenant.id,sku='C1-'+uuid4().hex,name='Pinned rules',cost=20,selling_price=45,stock_quantity=10);db_session.add(part);await db_session.commit()
    request=ps.ResolveRequest.model_validate({'context':{'kind':'repair_order','repair_order_id':created.id},'plan':{'kind':'parts_add','lines':[{'client_key':'part','inventory_id':part.id,'quantity':1}]}})
    preview=await build_plan(db_session,a.actor,request)
    saved=await ro.add_parts_to_repair_order(created.id,PartsUsageCreate(inventory_id=part.id,quantity=1,pricing_preview_fingerprint=preview.response['pricing_preview_fingerprint']),str(uuid4()),db_session,a.actor)
    assert saved.unit_price==40 and saved.pricing.policy_source=='customer'
    fresh=await create_order(db_session,a)
    assert fresh.pricing_policy['parts']=={'source':'shop','mode':'catalog'}
    savednew=await ro.add_parts_to_repair_order(fresh.id,PartsUsageCreate(inventory_id=part.id,quantity=1),str(uuid4()),db_session,a.actor)
    assert savednew.unit_price==45

@pytest.mark.asyncio
async def test_merge_guard_preserves_policy_and_deleted_work_identity(db_session):
    from app.services.customer_merge_guard import require_removable_pricing_identity
    from app.db.models.repair_order import RepairOrder
    from datetime import datetime,timezone
    a=await setup(db_session)
    await require_removable_pricing_identity(db_session,a.customer)
    created=await create_order(db_session,a)
    row=await db_session.get(RepairOrder,created.id);row.deleted_at=datetime.now(timezone.utc);await db_session.commit()
    with pytest.raises(HTTPException) as exc:await require_removable_pricing_identity(db_session,a.customer)
    assert exc.value.detail['code']=='customer_pricing_merge_locked'
    b=await setup(db_session);await configure(db_session,b);await configure(db_session,b,rate=None,version=1)
    with pytest.raises(HTTPException) as exc:await require_removable_pricing_identity(db_session,b.customer)
    assert exc.value.detail['code']=='customer_pricing_merge_locked'

@pytest.fixture
def client(client,_db_engine):
    from sqlalchemy.ext.asyncio import async_sessionmaker
    from app.main import app
    from app.core.dependencies import get_db
    previous=app.dependency_overrides[get_db]
    factory=async_sessionmaker(_db_engine,expire_on_commit=False,autoflush=False)
    async def sessions():
        async with factory() as session:yield session
    app.dependency_overrides[get_db]=sessions
    yield client
    app.dependency_overrides[get_db]=previous

@pytest.mark.asyncio
async def test_http_configuration_and_intake_replays_reauthorize_and_project(client,db_session):
    from app.core.security import create_access_token
    from app.db.models.repair_order import RepairOrder
    a=await setup(db_session)
    headers={'Authorization':'Bearer '+create_access_token({'sub':str(a.actor.id)},tenant_id=str(a.tenant.id))}
    key=str(uuid4());body={'expected_version':0,'labor_rate':'125.00','parts_matrix_id':None,'reason':'Synthetic agreement'}
    first=await client.put(f'/api/v1/customers/{a.customer.id}/pricing-policy',json=body,headers={**headers,'Idempotency-Key':key})
    assert first.status_code==200,first.text
    assert {part.strip() for part in first.headers['cache-control'].split(',')}=={'private','no-store'}
    orderkey=str(uuid4());orderbody={'customer_id':str(a.customer.id),'vehicle_id':str(a.order.vehicle_id)}
    created=await client.post('/api/v1/repair-orders',json=orderbody,headers={**headers,'Idempotency-Key':orderkey})
    assert created.status_code==201,created.text
    assert created.json()['pricing_policy']['labor']['rate']=='125.00'
    a.actor.role=UserRole.RECEPTIONIST;await db_session.commit()
    denied=await client.put(f'/api/v1/customers/{a.customer.id}/pricing-policy',json=body,headers={**headers,'Idempotency-Key':key})
    assert denied.status_code==403
    retry=await client.post('/api/v1/repair-orders',json=orderbody,headers={**headers,'Idempotency-Key':orderkey})
    assert retry.status_code==201 and retry.json()['id']==created.json()['id']
    detail=await client.get(f"/api/v1/repair-orders/{created.json()['id']}/detail?pricing_presentation=fleet",headers=headers)
    assert detail.status_code==200 and 'pricing_policy' not in detail.json()
    fleet_summary=await client.get(f"/api/v1/repair-orders/{created.json()['id']}/price-build?pricing_presentation=fleet",headers=headers)
    assert fleet_summary.status_code==200 and fleet_summary.json()['recommendation_hourly_rate'] is None
    assert 'pricing_policy' not in fleet_summary.json()
    a.actor.role=UserRole.MECHANIC;await db_session.commit()
    denied=await client.post('/api/v1/repair-orders',json=orderbody,headers={**headers,'Idempotency-Key':orderkey})
    assert denied.status_code==403
    assert await db_session.scalar(select(func.count(RepairOrder.id)).where(RepairOrder.tenant_id==a.tenant.id))==2

@pytest.mark.parametrize('role',[UserRole.RECEPTIONIST,UserRole.MECHANIC,UserRole.FLEET_MANAGER,UserRole.CUSTOMER])
@pytest.mark.asyncio
async def test_config_roles_cannot_read_private_terms(db_session,role):
    a=await setup(db_session);a.actor.role=role
    with pytest.raises(HTTPException) as exc:await api.get_policy(a.customer.id,db_session,a.actor)
    assert exc.value.status_code==403

@pytest.mark.asyncio
async def test_foreign_deleted_internal_and_fleet_downward_scope(db_session):
    from datetime import datetime,timezone
    a=await setup(db_session);b=await setup(db_session)
    with pytest.raises(HTTPException) as exc:await api.get_policy(b.customer.id,db_session,a.actor)
    assert exc.value.status_code==404
    view=await api.intake_preview(a.customer.id,a.order.vehicle_id,'fleet',db_session,a.actor)
    assert view['projection']=='fleet' and 'labor' not in view and 'parts' not in view
    a.customer.is_internal_fleet=True;await db_session.commit()
    view=await api.get_policy(a.customer.id,db_session,a.actor)
    assert not view['can_edit'] and view['effective']['labor']['rate'] is None
    with pytest.raises(HTTPException) as exc:await configure(db_session,a)
    assert exc.value.detail['code']=='internal_account_pricing'
    a.customer.deleted_at=datetime.now(timezone.utc);await db_session.commit()
    with pytest.raises(HTTPException) as exc:await api.get_policy(a.customer.id,db_session,a.actor)
    assert exc.value.status_code==404

@pytest.mark.asyncio
async def test_all_fleet_new_external_routes_use_agreement_then_shop_and_internal_unchanged(db_session):
    from app.api.v1.endpoints import fleet
    from app.db.models.vehicle import Vehicle
    from app.db.models.service import Service
    from app.db.models.labor import Labor
    from app.services.price_build_service import PriceBuildService
    a=await setup(db_session);await configure(db_session,a)
    vehicle=await db_session.get(Vehicle,a.order.vehicle_id)
    service=Service(tenant_id=a.tenant.id,name='PM synthetic',duration_minutes=60,is_active=True);db_session.add(service);await db_session.commit()
    order=await fleet._spawn_internal_ro(db_session,a.tenant.id,vehicle,is_pm=True,description='Synthetic PM',actor=a.actor)
    await fleet._apply_pm_services_to_ro(db_session,a.tenant.id,order,[service],actor=a.actor)
    await db_session.commit()
    line=await db_session.scalar(select(Labor).where(Labor.repair_order_id==order.id))
    assert line.hourly_rate==125 and line.pricing_snapshot['source']=='customer'
    line.hourly_rate=111;line.pricing_source='manual';line.auto_recalc_enabled=True;await db_session.commit()
    await fleet._apply_pm_services_to_ro(db_session,a.tenant.id,order,[service],actor=a.actor);await db_session.commit();await db_session.refresh(line)
    assert line.hourly_rate==111 and line.auto_recalc_enabled
    await configure(db_session,a,rate=None,version=1)
    fresh=await fleet._spawn_internal_ro(db_session,a.tenant.id,vehicle,is_pm=False,description='External fallback',actor=a.actor)
    assert fresh.pricing_policy_snapshot['labor']['rate']=='145.00'
    a.customer.is_internal_fleet=True;vehicle.bill_labor_at_customer_rate=False;a.tenant.internal_labor_rate=D('65');await db_session.commit()
    internal=await fleet._spawn_internal_ro(db_session,a.tenant.id,vehicle,is_pm=False,description='Internal',actor=a.actor)
    assert internal.pricing_policy_snapshot is None and account.labor_default(internal,a.tenant)[0]==65
    vehicle.bill_labor_at_customer_rate=True;await db_session.commit()
    internal2=await fleet._spawn_internal_ro(db_session,a.tenant.id,vehicle,is_pm=False,description='Internal billing preference',actor=a.actor)
    assert internal2.pricing_policy_snapshot is None and account.labor_default(internal2,a.tenant)[0]==145

@pytest.mark.asyncio
async def test_call_known_reservation_survives_pricing_conflict_and_original_order_replay(db_session,monkeypatch):
    from app.services import repair_intake_reference as intake
    from app.api.v1.endpoints import repair_orders as ro
    from app.schemas.repair_order import RepairOrderCreate
    from app.db.models.repair_order import RepairOrder
    from app.db.models.parts_operations import PartsOperationIdempotency
    a=await setup(db_session);await configure(db_session,a)
    original=await api.intake_preview(a.customer.id,a.order.vehicle_id,None,db_session,a.actor)
    reserved=NS(repair_order_uuid=uuid4(),elis_opportunity_id=uuid4(),callrail_call_id='synthetic-call')
    calls=[]
    async def reserve(*args):
        calls.append(True)
        await configure(db_session,a,rate='135',version=1)
        return intake.IntakeReservation(**reserved.__dict__)
    monkeypatch.setattr(intake,'reserve_originating_call',reserve)
    body=RepairOrderCreate(customer_id=a.customer.id,vehicle_id=a.order.vehicle_id,originating_call_reference='opaque-test-token',expected_pricing_policy=original['expected_pricing_policy'])
    with pytest.raises(HTTPException) as exc:await ro.create_repair_order(body,db_session,a.actor)
    assert exc.value.detail['code']=='account_pricing_changed'
    await db_session.rollback();await db_session.refresh(a.actor);await db_session.refresh(a.customer);await db_session.refresh(a.order)
    assert await db_session.scalar(select(func.count(PartsOperationIdempotency.id)).where(PartsOperationIdempotency.operation_family=='c1_call_reservation'))==1
    fresh=await api.intake_preview(a.customer.id,a.order.vehicle_id,None,db_session,a.actor)
    retry=body.model_copy(update={'expected_pricing_policy':fresh['expected_pricing_policy']})
    saved=await ro.create_repair_order(retry,db_session,a.actor)
    assert saved.id==reserved.repair_order_uuid and saved.pricing_policy['labor']['rate']=='135.00'
    await configure(db_session,a,rate='150',version=2)
    again=await ro.create_repair_order(retry,db_session,a.actor)
    assert again.id==saved.id and again.pricing_policy['labor']['rate']=='135.00' and len(calls)==1
    assert await db_session.scalar(select(func.count(RepairOrder.id)).where(RepairOrder.id==saved.id))==1

@pytest.mark.asyncio
async def test_unknown_call_reservation_failure_does_not_record_success(db_session,monkeypatch):
    from app.services import repair_intake_reference as intake
    from app.db.models.parts_operations import PartsOperationIdempotency
    a=await setup(db_session)
    async def unavailable(*args):raise HTTPException(502,'Call intake service is unavailable; please retry')
    monkeypatch.setattr(intake,'reserve_originating_call',unavailable)
    with pytest.raises(HTTPException) as exc:await account.reserve_call(db_session,a.actor,a.customer.id,a.order.vehicle_id,'ambiguous-token')
    assert exc.value.status_code==502
    assert await db_session.scalar(select(func.count(PartsOperationIdempotency.id)).where(PartsOperationIdempotency.operation_family=='c1_call_reservation'))==0

@pytest.mark.asyncio
async def test_malformed_saved_provenance_fails_closed_without_live_fallback(db_session):
    from copy import deepcopy
    a=await setup(db_session);await configure(db_session,a)
    snapshot,_=await account.capture(db_session,a.actor,a.customer.id,a.order.vehicle_id)
    corrupt=[{'schema_version':1,'parts':{'mode':'catalog','matrix':None}}]
    for path,value in [('labor.rate','broken'),('labor.rate','100000000.00'),('labor.rate','NaN'),('labor.rate','125.001'),('parts.source','alien'),('snapshot_id','not-a-uuid'),('customer_policy_event_id',None),('captured_at','2026-01-01'),('customer_pricing_version',True)]:
        saved=deepcopy(snapshot);keys=path.split('.');target=saved
        for key in keys[:-1]:target=target[key]
        target[keys[-1]]=value;corrupt.append(saved)
    for saved in corrupt:
        row=NS(tenant_id=a.tenant.id,pricing_policy_snapshot=saved,pricing_matrix_revision_id=None,is_internal=False)
        with pytest.raises(HTTPException) as exc:await account.policy_for_saved(db_session,a.tenant.id,row)
        assert exc.value.status_code==409 and exc.value.detail['code']=='account_pricing_unverified'
        with pytest.raises(HTTPException) as exc:account.labor_default(row,a.tenant)
        assert exc.value.detail['code']=='account_pricing_unverified'
    walkin=await account.candidate(db_session,a.tenant,None,counter=True)
    assert account.validated_snapshot(walkin,counter=True)==walkin
    for field,value in [('customer_pricing_version',1),('customer_name','Fabricated'),('customer_id',str(uuid4()))]:
        saved=deepcopy(walkin);saved[field]=value
        with pytest.raises(HTTPException):account.validated_snapshot(saved,counter=True)

@pytest.mark.asyncio
async def test_customer_only_token_checks_real_vehicle_and_preserves_quick_atomicity(db_session):
    from app.api.v1.endpoints import repair_orders as ro
    from app.schemas.repair_order import QuickRepairOrderCreate
    from app.db.models.vehicle import Vehicle
    from app.db.models.repair_order import RepairOrder
    a=await setup(db_session);await configure(db_session,a)
    preview=await api.intake_preview(a.customer.id,None,None,db_session,a.actor)
    saved=await create_order(db_session,a,expected_pricing_policy=preview['expected_pricing_policy'])
    assert saved.pricing_policy['labor']['rate']=='125.00'
    bound=await api.intake_preview(a.customer.id,a.order.vehicle_id,None,db_session,a.actor)
    other=Vehicle(tenant_id=a.tenant.id,customer_id=a.customer.id,make='Other',model='Truck');db_session.add(other);await db_session.commit()
    with pytest.raises(HTTPException) as exc:await create_order(db_session,a,vehicle_id=other.id,expected_pricing_policy=bound['expected_pricing_policy'])
    assert exc.value.detail['code']=='account_pricing_changed' and exc.value.detail['preview']['vehicle_id']==str(other.id)
    counts=[await db_session.scalar(select(func.count(model.id))) for model in (Customer,Vehicle,RepairOrder)]
    with pytest.raises(HTTPException) as exc:await ro.quick_create_repair_order(QuickRepairOrderCreate(phone='5559876543',expected_pricing_policy='stale'),db_session,a.actor)
    assert exc.value.detail['code']=='account_pricing_changed'
    assert counts==[await db_session.scalar(select(func.count(model.id))) for model in (Customer,Vehicle,RepairOrder)]

@pytest.mark.asyncio
async def test_counter_buyer_repins_future_lines_without_repricing_saved_lines(db_session,monkeypatch):
    from app.core.config import settings
    from test_db045_inventory_lifecycle import seed_context
    from app.services.counter_sale_service import create_or_replace_draft
    from app.services.parts_pricing_planner import build_plan
    from app.schemas.parts_pricing import ResolveRequest
    monkeypatch.setattr(settings,'PARTS_OPERATIONS_V1_ENABLED',True);monkeypatch.setattr(settings,'COUNTER_SALES_ENABLED',True)
    tenant,actor,part=await seed_context(db_session)
    customer=Customer(tenant_id=tenant.id,first_name='Account',last_name='Buyer',email=f'{uuid4()}@example.invalid');db_session.add(customer);await db_session.commit()
    a=NS(tenant=tenant,actor=actor,customer=customer)
    matrix=(await parts_api.create_matrix(MatrixCreate(name='Counter account terms',bands=BANDS),str(uuid4()),db_session,actor))['matrix']
    await configure(db_session,a,matrix_id=matrix['id'])
    async def save(sale,cid,lines,name='Buyer'):
        request=ResolveRequest.model_validate({'context':{'kind':'counter_sale','sale_id':sale.id if sale else None,'customer_id':cid,'expected_sale_version':sale.version if sale else None},'plan':{'kind':'counter_draft','lines':lines}})
        plan=await build_plan(db_session,actor,request)
        result=await create_or_replace_draft(db_session,tenant=tenant,actor=actor,sale=sale,customer_id=cid,buyer_name=name,buyer_email=None,buyer_phone=None,line_inputs=lines,pricing_preview_fingerprint=plan.response['pricing_preview_fingerprint'])
        await db_session.commit();await db_session.refresh(result[0]);return result
    sale,lines=await save(None,customer.id,[{'inventory_id':part.id,'quantity':1}])
    original=sale.pricing_policy_snapshot;line=lines[0];identity=line.id;price=line.charged_unit_price;origin=line.pricing_snapshot
    assert original['parts']['source']=='customer' and price==45
    from app.services.counter_sale_service import serialize_sale
    projected=(await serialize_sale(db_session,sale,actor))['pricing_policy']
    assert projected=={'schema_version':1,'snapshot_id':original['snapshot_id'],'mode':'captured','parts':{'source':'customer','mode':'matrix'}}
    await configure(db_session,a,matrix_id=None,version=1)
    sale,lines=await save(sale,customer.id,[{'inventory_id':part.id,'sale_line_id':identity,'quantity':2}],name='Contact-only edit')
    assert sale.pricing_policy_snapshot==original and lines[0].id==identity and lines[0].charged_unit_price==price
    sale,lines=await save(sale,None,[{'inventory_id':part.id,'sale_line_id':identity,'quantity':2}])
    assert sale.pricing_policy_snapshot['customer_id'] is None and sale.pricing_policy_snapshot['parts']['mode']=='catalog'
    assert lines[0].pricing_snapshot==origin and lines[0].charged_unit_price==price
    assert (await serialize_sale(db_session,sale,actor))['pricing_policy']['parts']=={'source':'shop','mode':'catalog'}
    assert await db_session.scalar(select(func.count(AccountPricingEvent.id)).where(AccountPricingEvent.entity_type=='counter_policy'))==2

@pytest.mark.asyncio
async def test_new_external_fleet_staged_preview_matches_saved_rate_and_part_policy(db_session):
    from app.api.v1.endpoints import fleet
    from app.schemas.fleet import WorkOrderCreate,WorkOrderLaborLineCreate,WorkOrderPartLineCreate
    from app.schemas.parts_pricing import ResolveRequest
    from app.services.parts_pricing_planner import build_plan
    from app.services.vehicle_identity import ensure_fleet_membership
    from app.db.models.inventory import Inventory,PartsUsage
    from app.db.models.labor import Labor
    from app.db.models.repair_order import RepairOrder
    a=await setup(db_session);await configure(db_session,a)
    await ensure_fleet_membership(db_session,tenant_id=a.tenant.id,vehicle_id=a.order.vehicle_id,fleet_customer_id=a.customer.id)
    part=Inventory(tenant_id=a.tenant.id,sku='C1-STAGED',name='Staged part',stock_quantity=10,cost=D('20'),selling_price=D('30'));db_session.add(part);await db_session.commit()
    body=WorkOrderCreate(description='Staged customer work',labor_lines=[WorkOrderLaborLineCreate(description='Agreed labor',hours='1.5')],part_lines=[WorkOrderPartLineCreate(inventory_id=part.id,quantity=2,client_key='part:0')])
    request=ResolveRequest.model_validate({'context':{'kind':'fleet_draft','vehicle_id':a.order.vehicle_id},'plan':{'kind':'fleet_create','service_ids':[],'labor_lines':[x.model_dump() for x in body.labor_lines],'part_lines':[x.model_dump() for x in body.part_lines]},'pricing_presentation':'fleet'})
    preview=await build_plan(db_session,a.actor,request)
    assert preview.response['totals']['repair_total']=='247.50'
    body.pricing_preview_fingerprint=preview.response['pricing_preview_fingerprint'];body.pricing_presentation='fleet'
    response=await fleet.new_work_order(a.order.vehicle_id,body,None,db_session,a.actor)
    row=await db_session.get(RepairOrder,response.created_work_order.repair_order_id)
    line=await db_session.scalar(select(Labor).where(Labor.repair_order_id==row.id))
    usage=await db_session.scalar(select(PartsUsage).where(PartsUsage.repair_order_id==row.id))
    assert row.total_cost==D('247.50') and line.hourly_rate==125 and usage.unit_price==30 and part.stock_quantity==8
    assert row.pricing_policy_snapshot['labor']['source']=='customer' and line.pricing_snapshot['source']=='customer'

@pytest.mark.asyncio
async def test_recommendation_uses_pinned_default_and_explicit_manual_without_reason(db_session):
    from app.services import recommendation_conversion
    from app.schemas.recommendation_conversion import RecommendationConvertRequest
    from app.db.models.recommended_service import RecommendedService
    from app.db.models.repair_order import RepairOrder
    from app.db.models.labor import Labor
    a=await setup(db_session);await configure(db_session,a)
    target=await create_order(db_session,a)
    recs=[RecommendedService(tenant_id=a.tenant.id,repair_order_id=a.order.id,description='Synthetic recommendation '+str(i)) for i in range(2)]
    db_session.add_all(recs);await db_session.commit()
    await configure(db_session,a,rate='135',version=1)
    body=RecommendationConvertRequest(request_id=uuid4(),hours='2')
    first,replay=await recommendation_conversion.convert(db_session,target_id=target.id,recommendation_id=recs[0].id,body=body,user=a.actor)
    await db_session.commit()
    again,replay=await recommendation_conversion.convert(db_session,target_id=target.id,recommendation_id=recs[0].id,body=body,user=a.actor)
    assert replay and again.id==first.id
    manual=RecommendationConvertRequest(request_id=uuid4(),hours='1',hourly_rate='110',pricing_intent='manual')
    await recommendation_conversion.convert(db_session,target_id=target.id,recommendation_id=recs[1].id,body=manual,user=a.actor);await db_session.commit()
    lines=list((await db_session.scalars(select(Labor).where(Labor.repair_order_id==target.id).order_by(Labor.hourly_rate))).all())
    assert [line.hourly_rate for line in lines]==[110,125] and [line.total_cost for line in lines]==[110,250]
    assert lines[0].pricing_source=='manual' and lines[1].pricing_source=='default'
    assert all(line.pricing_snapshot['default_hourly_rate']=='125.00' for line in lines)

@pytest.mark.asyncio
async def test_existing_zero_shop_rate_intake_line_and_replay_stay_valid(client,db_session):
    from app.core.security import create_access_token
    a=await setup(db_session);a.tenant.labor_rate=D('0');await db_session.commit()
    headers={'Authorization':'Bearer '+create_access_token({'sub':str(a.actor.id)},tenant_id=str(a.tenant.id)),'Idempotency-Key':str(uuid4())}
    preview=await client.get(f'/api/v1/customers/{a.customer.id}/pricing-preview',headers=headers,params={'vehicle_id':str(a.order.vehicle_id)})
    body={'customer_id':str(a.customer.id),'vehicle_id':str(a.order.vehicle_id),'expected_pricing_policy':preview.json()['expected_pricing_policy']}
    first=await client.post('/api/v1/repair-orders',json=body,headers=headers)
    assert first.status_code==201,first.text
    assert first.json()['pricing_policy']['labor']=={'source':'shop','rate':'0.00'}
    replay=await client.post('/api/v1/repair-orders',json=body,headers=headers)
    assert replay.status_code==201 and replay.json()['id']==first.json()['id']
    line=await client.post(f"/api/v1/repair-orders/{first.json()['id']}/labor",json={'description':'Zero shop default','hours':'1'},headers={k:v for k,v in headers.items() if k!='Idempotency-Key'})
    assert line.status_code==201 and D(line.json()['hourly_rate'])==0 and line.json()['pricing']['source']=='shop'

@pytest.mark.asyncio
async def test_owner_fleet_mutation_responses_omit_customer_provenance(client,db_session):
    from app.core.security import create_access_token
    a=await setup(db_session);await configure(db_session,a)
    target=await create_order(db_session,a)
    headers={'Authorization':'Bearer '+create_access_token({'sub':str(a.actor.id)},tenant_id=str(a.tenant.id))}
    base=f'/api/v1/repair-orders/{target.id}'
    line=await client.post(base+'/labor?pricing_presentation=fleet',json={'description':'Fleet add','hours':1},headers=headers)
    assert line.status_code==201 and 'pricing' not in line.json()
    line_id=line.json()['id']
    updated=await client.patch(base+f'/price-build/lines/{line_id}?pricing_presentation=fleet',json={'hours':2},headers=headers)
    assert updated.status_code==200,updated.text
    for payload in (updated.json(),(await client.post(base+'/price-build/recalculate?pricing_presentation=fleet',headers=headers)).json()):
        assert 'pricing_policy' not in payload and payload['recommendation_hourly_rate'] is None
        assert all('pricing' not in item for item in payload['lines'])
    removed=await client.delete(base+f'/price-build/lines/{line_id}?pricing_presentation=fleet',headers=headers)
    assert removed.status_code==200 and 'pricing_policy' not in removed.json()

@pytest.mark.asyncio
@pytest.mark.parametrize('mechanic',[False,True])
async def test_sublet_does_not_adopt_customer_defaults_or_expand_existing_rate_authority(db_session,mechanic):
    from app.api.v1.endpoints import repair_orders as ro
    from app.schemas.repair_order import LaborCreate
    from app.db.models.labor import LaborLineType
    a=await setup(db_session);await configure(db_session,a)
    a.order.is_internal=True;a.order.bill_labor_at_customer_rate=False;a.tenant.internal_labor_rate=D('65')
    if mechanic:a.actor.role=UserRole.MECHANIC;a.order.assigned_mechanic_id=a.actor.id
    await db_session.commit()
    response=await ro.add_labor_to_repair_order(a.order.id,LaborCreate(description='Legacy sublet semantics',hours=1,hourly_rate=999,line_type=LaborLineType.SUBLET),db_session,a.actor)
    assert response.hourly_rate==(145 if mechanic else 65) and 'pricing' not in response.model_dump()

@pytest.mark.asyncio
async def test_book_operation_and_deprecated_fleet_service_use_saved_customer_rate(db_session):
    from app.api.v1.endpoints import repair_orders as ro,fleet
    from app.schemas.repair_order import PriceBuildRepairOpsApplyRequest
    from app.schemas.fleet import AddServiceRequest
    from app.db.models.repair_order import RepairOrder
    from app.db.models.service import Service
    from app.db.models.labor import Labor
    from app.services.vehicle_identity import ensure_fleet_membership
    a=await setup(db_session);await configure(db_session,a)
    await ensure_fleet_membership(db_session,tenant_id=a.tenant.id,vehicle_id=a.order.vehicle_id,fleet_customer_id=a.customer.id);await db_session.commit()
    target=await create_order(db_session,a)
    service=Service(tenant_id=a.tenant.id,name='Legacy adapter customer terms',duration_minutes=60,is_active=True);db_session.add(service);await db_session.commit()
    await configure(db_session,a,rate='135',version=1)
    summary=await ro.apply_price_build_repair_operation(target.id,PriceBuildRepairOpsApplyRequest(operation_id='custom:c1-book',name='Pinned operation',estimated_hours=2,auto_recalc_enabled=False),db_session,a.actor)
    assert summary.labor_total==250 and summary.lines[0].pricing['source']=='customer'
    await fleet.add_service_to_work_order(target.id,AddServiceRequest(service_id=service.id),None,db_session,a.actor)
    lines=list((await db_session.scalars(select(Labor).where(Labor.repair_order_id==target.id))).all())
    assert len(lines)==2 and all(line.hourly_rate==125 and line.pricing_snapshot['source']=='customer' for line in lines)
    assert (await db_session.get(RepairOrder,target.id)).total_cost==375


def test_counter_legacy_projection_never_infers_current_terms():
    assert account.counter_view(NS(pricing_policy_snapshot=None))=={'schema_version':1,'snapshot_id':None,'mode':'legacy','parts':{'source':'legacy','mode':'legacy'}}
