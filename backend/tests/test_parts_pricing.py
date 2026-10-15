"""DB132 monetary rules, config isolation/CAS, and safe contextual confirmation."""
from decimal import Decimal as D
from types import SimpleNamespace as NS
from uuid import uuid4, UUID
import pytest
from fastapi import HTTPException
from sqlalchemy import select,func
from app.db.models.inventory import Inventory,PartsUsage
from app.db.models.parts_pricing import PartsPriceMatrix,PartsPriceMatrixRevision,PartsPricingPolicy,PartsPricingEvent
from app.db.models.user import UserRole
from app.services import parts_pricing as p
from app.services.parts_pricing_rules import resolve_price,PricePolicy,validate_bands,safe_price
from app.schemas import parts_pricing as s
from app.api.v1.endpoints import parts_pricing as api,repair_orders as ro
from app.schemas.repair_order import PartsUsageCreate,PartsUsageUpdate,AdHocPartCreate
from app.services.parts_pricing_planner import build_plan
from test_repair_order_ad_hoc_parts import _seed

# Match app.db.session.AsyncSessionLocal for this feature's direct and HTTP
# writers without changing the fixture contract of unrelated test modules.
@pytest.fixture
def db_session(db_session):
    db_session.autoflush = False
    return db_session


@pytest.fixture
def client(client, _db_engine):
    from sqlalchemy.ext.asyncio import async_sessionmaker
    from app.main import app
    from app.core.dependencies import get_db
    previous = app.dependency_overrides[get_db]
    factory = async_sessionmaker(_db_engine, expire_on_commit=False, autoflush=False)
    async def sessions():
        async with factory() as session:
            yield session
    app.dependency_overrides[get_db] = sessions
    try:
        yield client
    finally:
        app.dependency_overrides[get_db] = previous


BANDS=[{'min_cost':'0.00','max_cost':'25.00','markup_percent':'100.00'}, {'min_cost':'25.00','max_cost':'100.00','markup_percent':'50.00'}, {'min_cost':'100.00','max_cost':None,'markup_percent':'30.00'}]
POLICY=PricePolicy(1,uuid4(),uuid4(),1,'Test',BANDS)


def item(cost='20',catalog='45',**values):
    return NS(cost=D(cost) if cost is not None else None,selling_price=D(catalog),pricing_cost_floor=None,minimum_sale_price=None,fixed_sales_price=False,is_placeholder=False,**values) if not values else NS(**{**item(cost,catalog).__dict__,**values})


def failure(code,call,status=422):
    with pytest.raises(HTTPException) as e: call()
    assert e.value.status_code==status
    assert e.value.detail['code']==code


@pytest.mark.parametrize('cost,expected',[('20','40'),('25','37.50'),('100','130'),('24.99','49.98'),('99.99','149.99')])
def test_matrix_boundaries(cost,expected):
    got=resolve_price(item(cost),POLICY)
    assert got.charged==D(expected) and got.actual_cost==D(cost)


def test_distinct_floor_minimum_fixed_internal_and_zero():
    got=resolve_price(item('50',pricing_cost_floor=D('75')),POLICY)
    assert got.charged==D('112.50') and got.actual_cost==D('50')
    assert resolve_price(item(minimum_sale_price=D('50')),POLICY).charged==50
    assert resolve_price(item(fixed_sales_price=True,pricing_cost_floor=D('100')),POLICY).charged==45
    failure('price_below_minimum',lambda:resolve_price(item(fixed_sales_price=True,minimum_sale_price=D('50')),POLICY))
    assert resolve_price(item(minimum_sale_price=D('50'),fixed_sales_price=True),POLICY,internal=True).charged==20
    failure('internal_price_fixed',lambda:resolve_price(item(),POLICY,internal=True,requested='30'))
    assert resolve_price(item('0',pricing_cost_floor=D('10')),POLICY).charged==20
    zero=resolve_price(item('0','12'),POLICY)
    assert zero.charged==12 and zero.snapshot['source']=='catalog' and zero.warning=='catalog_zero_cost'


def test_unset_catalog_minimum_only_floor_only_and_explicit_manual():
    assert resolve_price(item('50','20'),PricePolicy()).charged==20
    assert not resolve_price(item(pricing_cost_floor=D('100')),PricePolicy()).snapshot['managed']
    assert resolve_price(item(minimum_sale_price=D('30')),PricePolicy()).snapshot['managed']
    failure('price_intent_required',lambda:resolve_price(item(),POLICY,requested='35',can_override=True),409)
    failure('price_intent_required',lambda:resolve_price(item(),POLICY,requested='35'),403)
    got=resolve_price(item(minimum_sale_price=D('30')),POLICY,intent='manual',requested='35',reason='Contract price',can_override=True,actor_id=uuid4())
    assert got.default==40 and got.charged==35 and got.snapshot['initial_override']['reason']=='Contract price'
    failure('price_below_minimum',lambda:resolve_price(item(minimum_sale_price=D('30')),POLICY,intent='manual',requested='29.99',reason='Contract price',can_override=True))


@pytest.mark.parametrize('value',['NaN','Infinity','-1','1.001','100000000'])
def test_invalid_money_never_zero(value):
    failure('invalid_price',lambda:resolve_price(item(),POLICY,requested=value))


def test_rules_order_gaps_bounds_and_overflow():
    for bands in [[],[{'min_cost':'1','max_cost':None,'markup_percent':'10'}],BANDS[::-1],BANDS+[BANDS[-1]], [{**BANDS[0],'max_cost':'26'},*BANDS[1:]]]:
        failure('invalid_bands',lambda:validate_bands(bands))
    failure('price_overflow',lambda:resolve_price(item('99999999.99'),POLICY))
    failure('price_overflow',lambda:resolve_price(item('1','99999999.99'),PricePolicy(),quantity=D('2')))


def test_unknown_ad_hoc_is_not_known_zero_or_matrix():
    got=resolve_price(item('0','12'),POLICY,ad_hoc=True,actual_cost_known=False,requested='12',actor_id=uuid4())
    assert got.actual_cost is None and got.snapshot['source']=='ad_hoc' and not got.snapshot['actual_cost_known']
    failure('ad_hoc_cost_required',lambda:resolve_price(item('0','12'),POLICY,ad_hoc=True,internal=True,actual_cost_known=False,requested='12'))
    failure('part_cost_required',lambda:resolve_price(item('0','12',is_placeholder=True),POLICY,actual_cost_known=False))


async def setup(db):
    tenant,actor,order=await _seed(db,role=UserRole.GARAGE_OWNER)
    part=Inventory(id=uuid4(),tenant_id=tenant.id,sku='P1-'+uuid4().hex[:8],name='Filter',cost=D('20'),selling_price=D('45'),stock_quantity=10)
    db.add(part);await db.commit()
    return NS(tenant=tenant,actor=actor,order=order,part=part)


async def matrix(db,a):
    result=await api.create_matrix(s.MatrixCreate(name='Shop matrix',bands=BANDS),str(uuid4()),db,a.actor)
    return result['matrix']


@pytest.mark.asyncio
async def test_config_inactive_version_revision_default_aba_archive_idempotency(db_session):
    a=await setup(db_session);key=str(uuid4());body=s.MatrixCreate(name='Shop matrix',bands=BANDS)
    first=await api.create_matrix(body,key,db_session,a.actor)
    assert first==await api.create_matrix(body,key,db_session,a.actor)
    m=first['matrix'];mid=UUID(m['id'])
    assert m['version']==m['current_revision']==1 and not m['is_default']
    assert await api.get_default(db_session,a.actor)=={'matrix_id':None,'generation':0}
    unchanged=await api.update_matrix(mid,s.MatrixUpdate(name='Shop matrix',bands=BANDS,expected_version=1),str(uuid4()),db_session,a.actor)
    assert unchanged==first
    await api.set_default(s.DefaultUpdate(matrix_id=mid,expected_generation=0),str(uuid4()),db_session,a.actor)
    with pytest.raises(HTTPException) as e: await api.archive_matrix(mid,s.MatrixArchive(expected_version=1),str(uuid4()),db_session,a.actor)
    assert e.value.detail['code']=='matrix_is_default';await db_session.rollback();await db_session.refresh(a.actor)
    await api.set_default(s.DefaultUpdate(matrix_id=None,expected_generation=1),str(uuid4()),db_session,a.actor)
    assert (await api.set_default(s.DefaultUpdate(matrix_id=mid,expected_generation=2),str(uuid4()),db_session,a.actor))['generation']==3
    with pytest.raises(HTTPException) as e: await api.set_default(s.DefaultUpdate(matrix_id=None,expected_generation=1),str(uuid4()),db_session,a.actor)
    assert e.value.detail['code']=='default_generation_conflict'


@pytest.mark.asyncio
async def test_config_role_tenant_policy_cas_and_cost_only_version(db_session):
    a=await setup(db_session);b=await setup(db_session);m=await matrix(db_session,a)
    with pytest.raises(HTTPException) as e: await api.get_matrix(UUID(m['id']),db_session,b.actor)
    assert e.value.status_code==404
    a.actor.role=UserRole.RECEPTIONIST
    with pytest.raises(HTTPException) as e: await api.get_default(db_session,a.actor)
    assert e.value.status_code==403
    a.actor.role=UserRole.GARAGE_OWNER
    original=await api.get_policy(a.part.id,db_session,a.actor)
    saved=await api.patch_policy(a.part.id,s.InventoryPolicyPatch(expected_pricing_version=original['policy']['pricing_version'],minimum_sale_price='30'),str(uuid4()),db_session,a.actor)
    assert saved['policy']['pricing_version']==original['policy']['pricing_version']+1
    with pytest.raises(HTTPException) as e: await api.patch_policy(a.part.id,s.InventoryPolicyPatch(expected_pricing_version=original['policy']['pricing_version'],selling_price='45'),str(uuid4()),db_session,a.actor)
    assert e.value.detail['code']=='pricing_version_conflict'


def request(a,**changes):
    return s.ResolveRequest.model_validate({'context':{'kind':'repair_order','repair_order_id':a.order.id},'plan':{'kind':'parts_add','lines':[{'client_key':'part','inventory_id':a.part.id,'quantity':'1','pricing_intent':'default'}]},**changes})


@pytest.mark.asyncio
async def test_managed_confirmation_stable_fingerprint_stale_then_attach(db_session):
    a=await setup(db_session);m=await matrix(db_session,a)
    await api.set_default(s.DefaultUpdate(matrix_id=m['id'],expected_generation=0),str(uuid4()),db_session,a.actor)
    plan=await build_plan(db_session,a.actor,request(a));again=await build_plan(db_session,a.actor,request(a))
    assert plan.response['pricing_preview_fingerprint']==again.response['pricing_preview_fingerprint']
    assert plan.response['confirmation_required'] and plan.response['totals']['repair_total']=='40.00'
    with pytest.raises(HTTPException) as e: plan.confirm(None)
    assert e.value.detail['code']=='pricing_preview_required' and e.value.detail['preview']['management'] is None
    saved=await ro.add_parts_to_repair_order(a.order.id,PartsUsageCreate(inventory_id=a.part.id,quantity='1',pricing_preview_fingerprint=plan.response['pricing_preview_fingerprint']),str(uuid4()),db_session,a.actor)
    assert saved.unit_price==40 and saved.unit_cost==20 and saved.pricing.origin_source=='matrix'
    usage=await db_session.get(PartsUsage,saved.id)
    assert usage.pricing_matrix_revision_id and usage.pricing_snapshot['actual_unit_cost']=='20.00'
    assert await db_session.scalar(select(func.count()).select_from(PartsPricingEvent).where(PartsPricingEvent.entity_id==usage.id))==1


@pytest.mark.asyncio
async def test_safe_fleet_downward_management_and_foreign_order(db_session):
    a=await setup(db_session);b=await setup(db_session)
    fleet=await build_plan(db_session,a.actor,request(a,pricing_presentation='fleet'))
    assert fleet.response['projection']=='fleet' and set(fleet.response['totals'])=={'kind','repair_total'}
    assert 'management' not in fleet.response and 'pricing' not in fleet.response['lines'][0]
    with pytest.raises(HTTPException) as e: await build_plan(db_session,a.actor,request(a,pricing_presentation='fleet',include_management_details=True))
    assert e.value.detail['code']=='management_details_not_available_in_fleet'
    with pytest.raises(HTTPException) as e: await build_plan(db_session,b.actor,request(a))
    assert e.value.status_code==404
    a.actor.role=UserRole.MECHANIC
    with pytest.raises(HTTPException) as e: await build_plan(db_session,a.actor,request(a,include_management_details=True))
    assert e.value.status_code==403


def test_safe_projection_uses_canonical_fractional_total_and_explicit_origin():
    legacy = NS(unit_price=D('0.10'), list_price=D('1.00'), quantity=D('0.25'), pricing_version=0, pricing_snapshot=None)
    safe = safe_price(legacy)
    assert safe['line_total'] == '0.02'
    assert safe['current_source'] == 'legacy_unknown'
    legacy._pricing_current_source = 'manual'
    assert safe_price(legacy)['current_source'] == 'manual'
    legacy._pricing_current_source = 'catalog'
    assert safe_price(legacy)['current_source'] == 'catalog'


@pytest.mark.asyncio
async def test_http_saved_part_retry_reauthorizes_role_and_preserves_single_reservation(client, db_session):
    from app.core.security import create_access_token
    a = await setup(db_session)
    a.order.is_fleet_work = True
    await db_session.commit()
    auth = {'Authorization': 'Bearer ' + create_access_token({'sub': str(a.actor.id)}, tenant_id=str(a.tenant.id)), 'Idempotency-Key': str(uuid4())}
    path = f'/api/v1/repair-orders/{a.order.id}/parts'
    body = {'inventory_id': str(a.part.id), 'quantity': '1'}
    first = await client.post(path, json=body, headers=auth)
    assert first.status_code == 201, first.text
    assert first.json()['pricing']['origin_source'] == 'catalog'
    a.actor.role = UserRole.FLEET_MANAGER
    await db_session.commit()
    replay = await client.post(path, json=body, headers=auth)
    assert replay.status_code == 201, replay.text
    assert replay.json()['id'] == first.json()['id']
    for key in ('pricing', 'unit_cost', 'unit_price', 'list_price', 'total_price', 'savings'):
        assert key not in replay.json()
    assert replay.json()['pricing_version'] == 0
    await db_session.refresh(a.part)
    assert a.part.stock_quantity == 9
    assert await db_session.scalar(select(func.count(PartsUsage.id)).where(PartsUsage.repair_order_id == a.order.id)) == 1
    assert await db_session.scalar(select(func.count(PartsPricingEvent.id)).where(PartsPricingEvent.entity_id == UUID(first.json()['id']))) == 1
    # A receipt is not authority after the exact fleet scope disappears.
    a.order.is_fleet_work = False
    await db_session.commit()
    denied = await client.post(path, json=body, headers=auth)
    assert denied.status_code == 403


@pytest.mark.asyncio
async def test_http_fleet_first_receipt_round_trip_and_configuration_cache(client, db_session):
    from app.core.security import create_access_token
    a = await setup(db_session)
    a.order.is_fleet_work = True
    a.actor.role = UserRole.FLEET_MANAGER
    await db_session.commit()
    headers = {'Authorization': 'Bearer ' + create_access_token({'sub': str(a.actor.id)}, tenant_id=str(a.tenant.id)), 'Idempotency-Key': str(uuid4())}
    path = f'/api/v1/repair-orders/{a.order.id}/parts'
    body = {'inventory_id': str(a.part.id), 'quantity': '0.25'}
    first = await client.post(path, json=body, headers=headers)
    replay = await client.post(path, json=body, headers=headers)
    assert first.status_code == replay.status_code == 201, (first.text, replay.text)
    assert first.json() == replay.json()
    assert 'pricing' not in first.json()
    a.actor.role = UserRole.GARAGE_OWNER
    await db_session.commit()
    config = await client.get('/api/v1/parts-pricing/matrices', headers=headers)
    assert config.status_code == 200, config.text
    assert set(config.headers['cache-control'].split(', ')) == {'private', 'no-store'}
    assert config.json() == {'schema_version': 1, 'items': [], 'next_cursor': None}


@pytest.mark.asyncio
async def test_managed_service_reapply_keeps_saved_money_and_identity_after_policy_change(db_session):
    from app.db.models.service import Service, ServicePart
    from app.services.price_build_service import PriceBuildService
    a = await setup(db_session)
    m = await matrix(db_session, a)
    await api.set_default(s.DefaultUpdate(matrix_id=UUID(m['id']), expected_generation=0), str(uuid4()), db_session, a.actor)
    service = Service(tenant_id=a.tenant.id, name='Filter service', duration_minutes=30, base_price=0, is_active=True)
    db_session.add(service); await db_session.flush()
    component = ServicePart(tenant_id=a.tenant.id, service_id=service.id, inventory_id=a.part.id, quantity=D(1))
    db_session.add(component); await db_session.commit()
    def request(quantity=1):
        return s.ResolveRequest.model_validate({'context': {'kind':'repair_order','repair_order_id':a.order.id}, 'plan': {'kind':'service_apply','service_id':service.id,'quantity':quantity}})
    preview = await build_plan(db_session, a.actor, request())
    svc = PriceBuildService()
    result = await svc.add_flat_service_line(db_session, a.order, service.id, actor=a.actor, pricing_preview_fingerprint=preview.response['pricing_preview_fingerprint'])
    row = result.order.parts_usage[0]
    identity, snapshot, parent_id = row.id, row.pricing_snapshot.copy(), row.source_line_id
    assert row.unit_cost == 20 and row.unit_price == row.list_price == 40
    retained = await build_plan(db_session, a.actor, request())
    old_token = retained.response['pricing_preview_fingerprint']
    a.part.cost = D(100); a.part.selling_price = D(300); a.part.pricing_version += 1
    await db_session.commit()
    await api.update_matrix(UUID(m['id']), s.MatrixUpdate(expected_version=1, name='Changed current policy', bands=[{'min_cost':'0','max_cost':None,'markup_percent':'200'}]), str(uuid4()), db_session, a.actor)
    unchanged = await build_plan(db_session, a.actor, request())
    assert unchanged.response['pricing_preview_fingerprint'] == old_token
    result = await svc.add_flat_service_line(db_session, a.order, service.id, actor=a.actor, pricing_preview_fingerprint=old_token)
    same = result.order.parts_usage[0]
    assert (same.id, same.source_line_id, same.pricing_snapshot) == (identity, parent_id, snapshot)
    assert same.unit_price == 40 and same.unit_cost == 20
    doubled = await build_plan(db_session, a.actor, request(2))
    result = await svc.add_flat_service_line(db_session, a.order, service.id, actor=a.actor, quantity=2, pricing_preview_fingerprint=doubled.response['pricing_preview_fingerprint'])
    same = result.order.parts_usage[0]
    assert (same.id, same.source_line_id, same.pricing_snapshot) == (identity, parent_id, snapshot)
    assert same.quantity == 2 and same.total_price == 80 and same.stock_reserved_packages == 2
    await db_session.refresh(a.part)
    assert a.part.stock_quantity == 8


@pytest.mark.asyncio
async def test_http_owner_fleet_projection_and_counter_replay_current_permissions(client, db_session, monkeypatch):
    from app.core.security import create_access_token
    from app.core.config import settings
    from test_db045_inventory_lifecycle import seed_context
    a = await setup(db_session)
    a.order.is_fleet_work = True
    await db_session.commit()
    headers = {'Authorization':'Bearer '+create_access_token({'sub':str(a.actor.id)},tenant_id=str(a.tenant.id))}
    created = await client.post(f'/api/v1/repair-orders/{a.order.id}/parts',json={'inventory_id':str(a.part.id),'quantity':'1'},headers=headers)
    assert created.status_code == 201, created.text
    fleet = await client.get(f'/api/v1/repair-orders/{a.order.id}/price-build?pricing_presentation=fleet',headers=headers)
    assert fleet.status_code == 200, fleet.text
    assert 'parts_pricing_fingerprint' not in fleet.json()
    assert 'pricing' not in fleet.json()['parts'][0]
    assert 'unit_cost' not in fleet.json()['parts'][0]
    assert fleet.json()['parts'][0]['pricing_version'] == 0
    detail = await client.get(f'/api/v1/repair-orders/{a.order.id}/detail?pricing_presentation=fleet',headers=headers)
    assert detail.status_code == 200, detail.text
    assert 'pricing' not in detail.json()['parts_usage'][0]
    assert 'unit_cost' not in detail.json()['parts_usage'][0]
    assert detail.json()['parts_usage'][0]['pricing_version'] == 0
    monkeypatch.setattr(settings,'PARTS_OPERATIONS_V1_ENABLED',True)
    monkeypatch.setattr(settings,'COUNTER_SALES_ENABLED',True)
    tenant, actor, part = await seed_context(db_session)
    auth = {'Authorization':'Bearer '+create_access_token({'sub':str(actor.id)},tenant_id=str(tenant.id)),'Idempotency-Key':str(uuid4())}
    body={'buyer_name':'Synthetic walk-in','lines':[{'inventory_id':str(part.id),'quantity':1}]}
    first=await client.post('/api/v1/parts-operations/counter-sales',json=body,headers=auth)
    assert first.status_code==201, first.text
    assert first.json()['lines'][0]['pricing']['can_override']
    actor.role=UserRole.RECEPTIONIST
    await db_session.commit()
    replay=await client.post('/api/v1/parts-operations/counter-sales',json=body,headers=auth)
    assert replay.status_code==201, replay.text
    assert replay.json()['id']==first.json()['id']
    assert not replay.json()['lines'][0]['pricing']['can_override']
    assert 'cancel' not in replay.json()['allowed_actions']


@pytest.mark.asyncio
async def test_saved_unknown_cost_and_nonreserved_bundle_never_invent_current_cost_or_stock(db_session):
    from app.db.models.service import Service
    from app.services.discount_limits import part_cost
    a=await setup(db_session)
    ad_hoc=await ro.add_ad_hoc_part_to_repair_order(a.order.id,AdHocPartCreate(name='Unknown expense',quantity=D(1),unit_price=D(12)),None,db_session,a.actor)
    row=await db_session.get(PartsUsage,ad_hoc.id)
    row.inventory_item=await db_session.get(Inventory,row.inventory_id)
    row.inventory_item.cost=D(50)
    assert row.unit_cost is None and part_cost(row) is None
    service=Service(tenant_id=a.tenant.id,name='Legacy fleet service',duration_minutes=30,is_active=True)
    db_session.add(service);await db_session.flush()
    row.source_service_id=service.id;row.stock_reserved_packages=0;row.stock_shortage_override=False
    await db_session.commit()
    updated=await ro.update_parts_quantity(a.order.id,row.id,PartsUsageUpdate(quantity=D(2),expected_pricing_version=0),db_session,a.actor)
    assert updated.quantity==2 and updated.unit_price==12 and updated.unit_cost is None
    await db_session.refresh(row.inventory_item)
    assert row.inventory_item.stock_quantity==0


@pytest.mark.asyncio
async def test_managed_counter_retains_identity_cost_price_on_buyer_quantity_and_policy_changes(db_session, monkeypatch):
    from app.core.config import settings
    from test_db045_inventory_lifecycle import seed_context
    from app.services.counter_sale_service import create_or_replace_draft, serialize_sale
    monkeypatch.setattr(settings,'PARTS_OPERATIONS_V1_ENABLED',True)
    monkeypatch.setattr(settings,'COUNTER_SALES_ENABLED',True)
    tenant,actor,part=await seed_context(db_session)
    a=NS(tenant=tenant,actor=actor,part=part)
    m=await matrix(db_session,a)
    await api.set_default(s.DefaultUpdate(matrix_id=UUID(m['id']),expected_generation=0),str(uuid4()),db_session,actor)
    lines=[{'inventory_id':part.id,'quantity':1}]
    request=s.ResolveRequest.model_validate({'context':{'kind':'counter_sale'},'plan':{'kind':'counter_draft','lines':lines}})
    plan=await build_plan(db_session,actor,request)
    sale,saved=await create_or_replace_draft(db_session,tenant=tenant,actor=actor,sale=None,customer_id=None,buyer_name='First buyer',buyer_email=None,buyer_phone=None,line_inputs=lines,pricing_preview_fingerprint=plan.response['pricing_preview_fingerprint'])
    await db_session.commit()
    identity=saved[0].id;snapshot=saved[0].pricing_snapshot.copy()
    assert saved[0].unit_cost==30 and saved[0].list_unit_price==45
    lines=[{'inventory_id':part.id,'sale_line_id':identity,'quantity':2,'charged_unit_price':'45.00'}]
    request=s.ResolveRequest.model_validate({'context':{'kind':'counter_sale','sale_id':sale.id,'expected_sale_version':sale.version},'plan':{'kind':'counter_draft','lines':lines}})
    retained=await build_plan(db_session,actor,request)
    part.cost=D(500);part.selling_price=D(900);part.pricing_version+=1
    await db_session.commit()
    changed=await build_plan(db_session,actor,request)
    assert changed.response['pricing_preview_fingerprint']==retained.response['pricing_preview_fingerprint']
    sale,saved=await create_or_replace_draft(db_session,tenant=tenant,actor=actor,sale=sale,customer_id=None,buyer_name='Second buyer',buyer_email=None,buyer_phone=None,line_inputs=lines,pricing_preview_fingerprint=retained.response['pricing_preview_fingerprint'])
    await db_session.commit()
    assert saved[0].id==identity and saved[0].pricing_snapshot==snapshot
    assert saved[0].unit_cost==30 and saved[0].list_unit_price==saved[0].charged_unit_price==45
    assert saved[0].quantity==2 and part.stock_quantity==10
    await db_session.refresh(sale)
    assert (await serialize_sale(db_session,sale,actor))['buyer_name']=='Second buyer'


@pytest.mark.asyncio
async def test_manual_then_quantity_then_list_saved_sources_are_explicit(db_session):
    a=await setup(db_session)
    row=await ro.add_parts_to_repair_order(a.order.id,PartsUsageCreate(inventory_id=a.part.id,quantity=D(1)),None,db_session,a.actor)
    manual=await ro.update_parts_quantity(a.order.id,row.id,PartsUsageUpdate(unit_price=D(40),price_action='manual',price_override_reason='Approved price',expected_pricing_version=0),db_session,a.actor)
    assert manual.pricing.current_source=='manual' and manual.pricing.pricing_version==1
    quantity=await ro.update_parts_quantity(a.order.id,row.id,PartsUsageUpdate(quantity=D(2),expected_pricing_version=1),db_session,a.actor)
    assert quantity.pricing.current_source=='manual' and quantity.unit_price==40
    restored=await ro.update_parts_quantity(a.order.id,row.id,PartsUsageUpdate(price_action='list',expected_pricing_version=2),db_session,a.actor)
    assert restored.unit_price==45 and restored.pricing.current_source=='catalog'
    before=restored.pricing.pricing_version
    no_op=await ro.update_parts_quantity(a.order.id,row.id,PartsUsageUpdate(unit_price=D(45),expected_pricing_version=before),db_session,a.actor)
    assert no_op.pricing.pricing_version==before and no_op.pricing.current_source=='catalog'


@pytest.mark.asyncio
async def test_http_ad_hoc_downward_projection_and_retry(client, db_session):
    from app.core.security import create_access_token
    a = await setup(db_session)
    headers = {'Authorization': 'Bearer '+create_access_token({'sub':str(a.actor.id)}, tenant_id=str(a.tenant.id)), 'Idempotency-Key':str(uuid4())}
    path = f'/api/v1/repair-orders/{a.order.id}/parts/ad-hoc'
    body = {'name':'Fleet-only new item', 'quantity':'1', 'unit_price':'30', 'unit_cost':'20', 'pricing_presentation':'fleet'}
    first = await client.post(path, json=body, headers=headers)
    retry = await client.post(path, json=body, headers=headers)
    assert first.status_code == retry.status_code == 201, (first.text, retry.text)
    assert first.json() == retry.json()
    assert first.json()['pricing_version'] == 0
    assert not {'pricing','unit_cost','unit_price','list_price','total_price','savings'} & first.json().keys()
    assert await db_session.scalar(select(func.count(PartsUsage.id)).where(PartsUsage.repair_order_id==a.order.id)) == 1


@pytest.mark.asyncio
async def test_http_search_service_alias_confirms_and_shares_canonical_receipt(client, db_session):
    from app.core.security import create_access_token
    from app.db.models.service import Service, ServicePart
    from app.db.models.labor import Labor
    a = await setup(db_session)
    a.order.is_fleet_work = True
    matrix_row = await matrix(db_session, a)
    await api.set_default(s.DefaultUpdate(matrix_id=matrix_row['id'], expected_generation=0), str(uuid4()), db_session, a.actor)
    service = Service(tenant_id=a.tenant.id, name='Search package', duration_minutes=30, base_price=0, is_active=True)
    db_session.add(service); await db_session.flush()
    db_session.add(ServicePart(tenant_id=a.tenant.id, service_id=service.id, inventory_id=a.part.id, quantity=D(1)))
    await db_session.commit()
    headers = {'Authorization':'Bearer '+create_access_token({'sub':str(a.actor.id)},tenant_id=str(a.tenant.id)), 'Idempotency-Key':str(uuid4())}
    path = f'/api/v1/repair-orders/{a.order.id}/price-build/repair-ops/apply'
    body = {'operation_id':f'service:{service.id}', 'provider':'service_catalog'}
    required = await client.post(path, json=body, headers=headers)
    assert required.status_code == 409, required.text
    preview = required.json()['detail']['preview']
    assert preview['plan_kind'] == 'service_apply'
    assert preview['confirmation_required']
    assert await db_session.scalar(select(func.count(Labor.id)).where(Labor.repair_order_id==a.order.id)) == 0
    body['pricing_preview_fingerprint'] = preview['pricing_preview_fingerprint']
    first = await client.post(path, json=body, headers=headers)
    assert first.status_code == 200, first.text
    identity = first.json()['parts'][0]['id']
    a.actor.role = UserRole.FLEET_MANAGER
    await db_session.commit()
    retry = await client.post(path, json=body, headers=headers)
    assert retry.status_code == 200, retry.text
    assert retry.json()['parts'][0]['id'] == identity
    assert 'pricing' not in retry.json()['parts'][0]
    assert 'unit_cost' not in retry.json()['parts'][0]
    # The canonical endpoint recognizes the same logical service command.
    canonical = await client.post(f'/api/v1/repair-orders/{a.order.id}/price-build/flat-service', json={'service_id':str(service.id),'quantity':1,'pricing_preview_fingerprint':body['pricing_preview_fingerprint']}, headers=headers)
    assert canonical.status_code == 200, canonical.text
    assert canonical.json()['parts'][0]['id'] == identity
    await db_session.refresh(a.part)
    assert a.part.stock_quantity == 9
    assert await db_session.scalar(select(func.count(Labor.id)).where(Labor.repair_order_id==a.order.id)) == 1
    a.order.is_fleet_work = False
    await db_session.commit()
    denied = await client.post(path, json=body, headers=headers)
    assert denied.status_code == 403


@pytest.mark.asyncio
async def test_http_plain_operation_keeps_durable_retry_when_alias_bypasses_redis(client, db_session):
    from app.core.security import create_access_token
    from app.db.models.labor import Labor
    a = await setup(db_session)
    headers = {'Authorization':'Bearer '+create_access_token({'sub':str(a.actor.id)},tenant_id=str(a.tenant.id)), 'Idempotency-Key':str(uuid4())}
    path = f'/api/v1/repair-orders/{a.order.id}/price-build/repair-ops/apply'
    body = {'operation_id':'custom:inspect-filter','name':'Inspect filter','estimated_hours':'0.5'}
    first = await client.post(path, json=body, headers=headers)
    retry = await client.post(path, json=body, headers=headers)
    assert first.status_code == retry.status_code == 200, (first.text, retry.text)
    assert await db_session.scalar(select(func.count(Labor.id)).where(Labor.repair_order_id==a.order.id)) == 1


@pytest.mark.asyncio
async def test_legacy_fleet_bundle_reapply_preserves_explicit_zero_reservation(db_session):
    from test_fleet_manager_price_build_access import _seed as seed_fleet
    from app.api.v1.endpoints import fleet
    from app.schemas.fleet import AddServiceRequest
    from app.services.vehicle_identity import ensure_fleet_membership
    from app.services.price_build_service import PriceBuildService
    tenant, actor, order, inv, service = await seed_fleet(db_session, is_internal=False, is_fleet_work=True)
    actor.role = UserRole.GARAGE_OWNER
    await ensure_fleet_membership(db_session,tenant_id=tenant.id,vehicle_id=order.vehicle_id,fleet_customer_id=order.customer_id)
    await db_session.commit()
    await fleet.add_service_to_work_order(order.id, AddServiceRequest(service_id=service.id), None, db_session, actor)
    row = await db_session.scalar(select(PartsUsage).where(PartsUsage.repair_order_id==order.id))
    identity, snapshot, stock = row.id, row.pricing_snapshot.copy(), inv.stock_quantity
    plan = await build_plan(db_session, actor, s.ResolveRequest.model_validate({'context':{'kind':'repair_order','repair_order_id':order.id},'plan':{'kind':'service_apply','service_id':service.id,'quantity':2}}))
    await PriceBuildService().add_flat_service_line(db_session,order,service.id,quantity=2,actor=actor,pricing_preview_fingerprint=plan.response['pricing_preview_fingerprint'])
    await db_session.refresh(row); await db_session.refresh(inv)
    assert (row.id,row.pricing_snapshot,row.quantity,row.stock_reserved_packages,inv.stock_quantity) == (identity,snapshot,D(2),0,stock)


@pytest.mark.asyncio
async def test_bundle_core_quantity_sync_and_recovered_core_fail_atomically(db_session):
    from test_fleet_manager_price_build_access import _seed as seed_fleet
    from app.services.price_build_service import PriceBuildService
    from app.db.models.parts_operations import CoreObligation
    tenant, actor, order, inv, service = await seed_fleet(db_session,is_internal=False,is_fleet_work=True)
    actor.role = UserRole.GARAGE_OWNER; inv.core_charge=D(15)
    await db_session.commit()
    svc=PriceBuildService()
    await svc.add_flat_service_line(db_session,order,service.id,actor=actor)
    row=await db_session.scalar(select(PartsUsage).where(PartsUsage.repair_order_id==order.id))
    core=await db_session.scalar(select(CoreObligation).where(CoreObligation.parts_usage_id==row.id))
    async def reapply(quantity):
        plan=await build_plan(db_session,actor,s.ResolveRequest.model_validate({'context':{'kind':'repair_order','repair_order_id':order.id},'plan':{'kind':'service_apply','service_id':service.id,'quantity':quantity}}))
        return await svc.add_flat_service_line(db_session,order,service.id,quantity=quantity,actor=actor,pricing_preview_fingerprint=plan.response['pricing_preview_fingerprint'])
    await reapply(2)
    await db_session.refresh(row); await db_session.refresh(core)
    assert row.stock_reserved_packages==core.quantity==2
    assert core.version==2 and core.unit_core_value_snapshot==15
    await ro.update_parts_quantity(order.id,row.id,PartsUsageUpdate(quantity=D(3),expected_pricing_version=row.pricing_version),db_session,actor)
    await db_session.refresh(core)
    assert core.quantity==3 and core.version==3
    core.status='on_hand'; await db_session.commit()
    ids = (row.id, core.id, inv.id, order.id)
    await db_session.refresh(inv); stock=inv.stock_quantity
    with pytest.raises(HTTPException) as rejected: await reapply(4)
    assert rejected.value.detail['code']=='core_requires_review'
    await db_session.rollback()
    persisted=await db_session.get(PartsUsage,ids[0]); saved_core=await db_session.get(CoreObligation,ids[1]); saved_inv=await db_session.get(Inventory,ids[2])
    assert persisted.quantity==saved_core.quantity==3
    assert saved_inv.stock_quantity==stock
