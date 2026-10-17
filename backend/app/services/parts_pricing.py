"""DB132 policy storage, private configuration, and retained-line evidence."""
from __future__ import annotations
import base64
import hashlib
import hmac
import json
from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
from uuid import UUID, uuid4
from fastapi import HTTPException
from sqlalchemy import func, select, tuple_, or_
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.config import settings
from app.db.models.parts_pricing import PartsPriceMatrix as Matrix, PartsPriceMatrixRevision as Revision, PartsPricingPolicy as Policy, PartsPricingEvent as Event
from app.db.models.inventory import Inventory, PartsUsage
from app.db.models.user import User, UserRole
from app.db.models.tenant import Tenant
from app.services.operation_execution import lock_tenant_financials
from app.services.parts_operations_service import validate_idempotency_key, canonical_fingerprint, find_idempotent_response, begin_idempotency, complete_idempotency
from app.services.parts_pricing_rules import PricePolicy, amount, cents, fail, resolve_price, validate_bands, safe_price, saved_floor, line_total

MANAGERS = {UserRole.GARAGE_OWNER, UserRole.GARAGE_ADMIN}
EDITORS = MANAGERS | {UserRole.RECEPTIONIST, UserRole.FLEET_MANAGER}
STAFF = EDITORS | {UserRole.MECHANIC}


def signed_digest(payload, purpose='preview'):
    raw = json.dumps(payload, sort_keys=True, separators=(',', ':'), default=str).encode()
    return hmac.new(settings.SECRET_KEY.encode(), b'db132:' + purpose.encode() + b':' + raw, hashlib.sha256).hexdigest()


def cursor_encode(scope, key):
    data = {'scope': scope, 'key': key}
    raw = json.dumps(data, sort_keys=True, separators=(',', ':'), default=str).encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip('=') + '.' + signed_digest(data,'cursor')


def cursor_decode(raw, scope):
    if not raw: return None
    try:
        encoded, signature = raw.split('.')
        data = json.loads(base64.urlsafe_b64decode(encoded + '=' * (-len(encoded) % 4)))
        if data['scope'] != scope or not hmac.compare_digest(signature, signed_digest(data, 'cursor')): raise ValueError()
        return data['key']
    except (ValueError, KeyError, TypeError):
        fail('invalid_cursor', 'This page cursor is invalid for the current view.', 400)


async def authorize(db, actor, *, manager=False):
    if actor.role not in (MANAGERS if manager else STAFF) or not actor.tenant_id:
        fail('pricing_access_denied', 'Access denied.',403)
    tenant = await db.scalar(select(Tenant).where(Tenant.id==actor.tenant_id,Tenant.deleted_at.is_(None),Tenant.is_active.is_(True)))
    if not tenant: fail('pricing_access_denied','Access denied.',403)
    return tenant


def presentation(actor, requested=None, management=False, counter=False):
    if management and actor.role not in MANAGERS: fail('pricing_access_denied','Access denied.',403)
    result = 'fleet' if actor.role == UserRole.FLEET_MANAGER else (requested or 'shop')
    if counter and result == 'fleet': fail('presentation_not_supported','Counter sales use the shop workspace.')
    if management and result == 'fleet': fail('management_details_not_available_in_fleet','Open price details in the shop workspace.')
    return result


async def selected_policy(db, tenant_id, *, lock=False):
    stmt=select(Policy).where(Policy.tenant_id==tenant_id).execution_options(populate_existing=True)
    if lock: stmt=stmt.with_for_update()
    policy=await db.scalar(stmt)
    if not policy or not policy.default_matrix_id: return PricePolicy(generation=policy.generation if policy else 0)
    stmt=select(Matrix).where(Matrix.tenant_id==tenant_id,Matrix.id==policy.default_matrix_id).execution_options(populate_existing=True)
    if lock: stmt=stmt.with_for_update()
    matrix=await db.scalar(stmt)
    if matrix is None or matrix.archived_at: fail('matrix_archived','The selected pricing matrix is unavailable.',409)
    revision=await db.scalar(select(Revision).where(Revision.tenant_id==tenant_id,Revision.matrix_id==matrix.id,Revision.revision==matrix.current_revision))
    if revision is None: fail('matrix_revision_missing','The selected pricing rules are unavailable.',409)
    return PricePolicy(policy.generation,matrix.id,revision.id,revision.revision,revision.name_snapshot,revision.bands)


async def inventory(db, tenant_id, ids, *, lock=False, retained_ids=()):
    ids=set(ids)
    if len(ids)>100: fail('plan_too_large','Use no more than 100 parts per command.')
    if not ids: return {}
    stmt=select(Inventory).where(Inventory.tenant_id==tenant_id,Inventory.id.in_(ids),or_(Inventory.deleted_at.is_(None), Inventory.id.in_(set(retained_ids)))).order_by(Inventory.id).execution_options(populate_existing=True)
    if lock: stmt=stmt.with_for_update()
    rows={r.id:r for r in (await db.scalars(stmt)).all()}
    if set(rows)!=ids: fail('part_not_found','One or more parts were not found.',404)
    return rows


def policy_view(item):
    known=not (item.is_placeholder and not item.cost)
    return {'schema_version':1,'policy':{'inventory_id':str(item.id),'pricing_version':item.pricing_version,
        'actual_unit_cost':cents(item.cost) if known else None,'actual_cost_known':known,'selling_price':cents(item.selling_price),
        'pricing_cost_floor':cents(item.pricing_cost_floor) if item.pricing_cost_floor is not None else None,
        'minimum_sale_price':cents(item.minimum_sale_price) if item.minimum_sale_price is not None else None,'fixed_sales_price':item.fixed_sales_price}}


def json_values(values):
    return json.loads(json.dumps(values,default=str))


def add_event(db, actor, entity_type, entity_id, event_type, *, before=None, after=None, old_version=None,new_version=None,reason=None,identity=None,correlation_id=None,**refs):
    event=Event(tenant_id=actor.tenant_id,entity_type=entity_type,entity_id=entity_id,event_type=event_type,actor_id=actor.id,
        correlation_id=correlation_id or uuid4(),old_version=old_version,new_version=new_version,reason=reason,
        before_values=json_values(before or {}),after_values=json_values(after or {}),identity_snapshot=json_values(identity or {}),**refs)
    db.add(event)
    return event


async def audit_usage(db, actor, order, usage, event_type, *, before=None, reason=None, old_version=None, correlation_id=None):
    # Do not accept an arbitrary historical UUID as authorization. Validate all
    # live identities at append, then preserve a non-FK evidence snapshot.
    if actor is None: fail('pricing_actor_required','An authenticated staff member is required.',403)
    if actor.tenant_id != order.tenant_id or usage.tenant_id != order.tenant_id or usage.repair_order_id != order.id:
        fail('pricing_access_denied','Access denied.',403)
    inv = usage.__dict__.get('inventory_item')
    if inv is None or inv.id != usage.inventory_id or inv.tenant_id != actor.tenant_id:
        inv=await db.scalar(select(Inventory).where(Inventory.id==usage.inventory_id,Inventory.tenant_id==actor.tenant_id))
    if inv is None: fail('part_not_found','Part not found.',404)
    if usage.pricing_matrix_revision_id and not await db.scalar(select(Revision.id).where(Revision.id==usage.pricing_matrix_revision_id,Revision.tenant_id==actor.tenant_id)):
        fail('matrix_revision_missing','Pricing revision not found.',404)
    snapshot=usage.pricing_snapshot or {}
    add_event(db,actor,'parts_usage',usage.id,event_type,before=before,after=usage_values(usage),old_version=old_version,new_version=usage.pricing_version or 0,reason=reason,
        inventory_id=inv.id,revision_id=usage.pricing_matrix_revision_id,correlation_id=correlation_id,
        identity={'parts_usage_id':usage.id,'repair_order_id':order.id,'order_number':order.order_number,'inventory_id':inv.id,'name':inv.name,
          'source_service_id':usage.source_service_id,'source_line_id':usage.source_line_id,'source_component_id':usage.source_component_id,
          'snapshot_id':snapshot.get('snapshot_id'),'schema_version':snapshot.get('schema_version'),'actual_unit_cost':snapshot.get('actual_unit_cost')})


def usage_values(row):
    return {'quantity':str(row.quantity),'unit_cost':str(row.unit_cost) if row.unit_cost is not None else None,'unit_price':str(row.unit_price),'list_price':str(row.list_price) if row.list_price is not None else None,'total_price':str(row.total_price)}


def parts_fingerprint(order):
    return signed_digest({'tenant':str(order.tenant_id),'order':str(order.id),'parts':[
        {'id':str(p.id),'version':p.pricing_version or 0,'quantity':str(p.quantity),'cost':str(p.unit_cost),'default':str(p.list_price),'charged':str(p.unit_price)}
        for p in sorted(order.parts_usage,key=lambda r:str(r.id)) if p.deleted_at is None]},'parts')


def check_line_version(row, expected, *, required=False):
    if expected is None:
        if required: fail('pricing_version_required','Refresh this part before changing its price.',409)
    elif expected != (row.pricing_version or 0): fail('pricing_version_conflict','This part changed. Refresh it while keeping your draft.',409)


def retained_price(row, *, action, requested=None, reason=None, actor, internal=False):
    if actor.role not in EDITORS: fail('price_override_forbidden','You cannot override a part price.',403)
    if action=='list':
        value=row.list_price
        if value is None: fail('original_price_unknown','The original default price is unknown.',409)
        reason='restore_original_default'
    elif action=='stock':
        value=row.unit_cost
        if value is None: fail('part_cost_required','The original actual cost is unknown.')
        reason='use_original_cost'
    elif action=='manual':
        value=requested
        reason=(reason or '').strip()
        if not 3<=len(reason)<=500: fail('price_reason_required','Enter a reason between 3 and 500 characters.')
    else: fail('price_intent_required','Choose an explicit price action.',409)
    value=amount(value)
    if internal and row.unit_cost is not None and value != row.unit_cost:
        fail('internal_price_fixed','Internal parts must use original actual cost.')
    floor=saved_floor(row)
    if floor is None:
        # Keep the legacy actual-cost guard for null snapshots only. New unknown
        # origins never acquire invented expense from a changing catalog.
        if row.pricing_snapshot is None:
            from app.services.discount_limits import part_cost
            floor=part_cost(row)
        if floor is None and value < row.unit_price: fail('part_cost_required','Record a known original cost before discounting this part.')
    if floor is not None and value < floor: fail('price_below_minimum','This part price is below its allowed minimum.')
    line_total(value,row.quantity)
    return value,reason


async def config_command(db,actor,key,route,payload,operation):
    await authorize(db,actor,manager=True)
    key=validate_idempotency_key(key)
    await lock_tenant_financials(db,actor.tenant_id)
    fingerprint=canonical_fingerprint(route=route,principal_id=actor.id,payload={'tenant':str(actor.tenant_id),'body':payload})
    try:
        record=await find_idempotent_response(db,tenant_id=actor.tenant_id,family='p1_config',key=key,fingerprint=fingerprint)
    except HTTPException as exc:
        if exc.status_code==409: fail('idempotency_conflict','This action key already belongs to a different request.',409)
        raise
    if record: return json.loads(record.response_body)
    record=begin_idempotency(tenant_id=actor.tenant_id,family='p1_config',key=key,fingerprint=fingerprint);db.add(record)
    result=await operation()
    await db.flush()
    complete_idempotency(record,status_code=201 if route=='matrix:create' else 200,body=result)
    await db.commit()
    return result


async def get_matrix(db,tenant_id,matrix_id,*,lock=False):
    stmt=select(Matrix).where(Matrix.tenant_id==tenant_id,Matrix.id==matrix_id).execution_options(populate_existing=True)
    if lock: stmt=stmt.with_for_update()
    matrix=await db.scalar(stmt)
    if matrix is None: fail('matrix_not_found','Matrix not found.',404)
    return matrix


async def matrix_view(db,matrix,*,detail=True):
    revision=await db.scalar(select(Revision).where(Revision.tenant_id==matrix.tenant_id,Revision.matrix_id==matrix.id,Revision.revision==matrix.current_revision))
    default=await db.scalar(select(Policy.default_matrix_id).where(Policy.tenant_id==matrix.tenant_id))
    def iso(v): return v.replace(tzinfo=timezone.utc).isoformat() if v and not v.tzinfo else (v.isoformat() if v else None)
    view={'id':str(matrix.id),'name':matrix.name,'version':matrix.version,'current_revision':matrix.current_revision,'current_revision_id':str(revision.id),
          'is_default':matrix.id==default,'archived_at':iso(matrix.archived_at),'created_at':iso(matrix.created_at),'updated_at':iso(matrix.updated_at)}
    if detail: view['bands']=revision.bands
    return view


async def write_matrix(db,actor,body,matrix_id=None,action=None):
    matrix=await get_matrix(db,actor.tenant_id,matrix_id,lock=True) if matrix_id else None
    if matrix and matrix.version != body.expected_version: fail('matrix_version_conflict','This matrix changed. Refresh it while keeping your draft.',409)
    if action:
        archived=action=='archive'
        if archived and await db.scalar(select(Policy.tenant_id).where(Policy.tenant_id==actor.tenant_id,Policy.default_matrix_id==matrix.id)):
            fail('matrix_is_default','Clear or replace the shop default before archiving this matrix.',409)
        if archived:
            from app.db.models.customer import Customer
            if await db.scalar(select(Customer.id).where(Customer.tenant_id==actor.tenant_id,Customer.parts_price_matrix_id==matrix.id,Customer.deleted_at.is_(None)).limit(1)):
                fail('matrix_assigned_to_customer','Clear or replace customer pricing defaults before archiving this matrix.',409)
        if bool(matrix.archived_at)==archived: return {'schema_version':1,'matrix':await matrix_view(db,matrix)}
        if not archived: await check_name(db,actor.tenant_id,matrix.name,matrix.id)
        before={'archived_at':matrix.archived_at};old=matrix.version
        matrix.archived_at=datetime.now(timezone.utc) if archived else None;matrix.archived_by=actor.id if archived else None
        matrix.version+=1;matrix.updated_by=actor.id;matrix.updated_at=datetime.now(timezone.utc)
        add_event(db,actor,'matrix',matrix.id,'matrix.'+action,before=before,after={'archived_at':matrix.archived_at},old_version=old,new_version=matrix.version,matrix_id=matrix.id)
    else:
        if matrix and matrix.archived_at: fail('matrix_archived','Restore this matrix before editing its rules.',409)
        name=body.name;bands=validate_bands([b.model_dump() for b in body.bands])
        await check_name(db,actor.tenant_id,name,matrix.id if matrix else None)
        before={};old=None
        if matrix:
            revision=await db.scalar(select(Revision).where(Revision.tenant_id==actor.tenant_id,Revision.matrix_id==matrix.id,Revision.revision==matrix.current_revision))
            if matrix.name==name and revision.bands==bands: return {'schema_version':1,'matrix':await matrix_view(db,matrix)}
            before={'name':matrix.name,'bands':revision.bands};old=matrix.version
            matrix.name=name;matrix.version+=1;matrix.current_revision+=1;matrix.updated_by=actor.id;matrix.updated_at=datetime.now(timezone.utc)
        else:
            matrix=Matrix(id=uuid4(),tenant_id=actor.tenant_id,name=name,version=1,current_revision=1,created_by=actor.id,updated_by=actor.id);db.add(matrix);await db.flush()
        revision=Revision(id=uuid4(),tenant_id=actor.tenant_id,matrix_id=matrix.id,revision=matrix.current_revision,name_snapshot=name,bands=bands,created_by=actor.id);db.add(revision);await db.flush()
        add_event(db,actor,'matrix',matrix.id,'matrix.updated' if old else 'matrix.created',before=before,after={'name':name,'bands':bands},old_version=old,new_version=matrix.version,matrix_id=matrix.id,revision_id=revision.id)
    await db.flush()
    return {'schema_version':1,'matrix':await matrix_view(db,matrix)}


async def check_name(db,tenant_id,name,exclude=None):
    stmt=select(Matrix.id).where(Matrix.tenant_id==tenant_id,Matrix.archived_at.is_(None),func.lower(Matrix.name)==name.lower())
    if exclude: stmt=stmt.where(Matrix.id!=exclude)
    if await db.scalar(stmt): fail('matrix_name_conflict','An active matrix already uses this name.',409)


async def default_view(db,tenant_id):
    row=await db.get(Policy,tenant_id)
    return {'matrix_id':str(row.default_matrix_id) if row and row.default_matrix_id else None,'generation':row.generation if row else 0}


async def set_default(db,actor,body):
    row=await db.scalar(select(Policy).where(Policy.tenant_id==actor.tenant_id).with_for_update().execution_options(populate_existing=True))
    generation=row.generation if row else 0
    if generation != body.expected_generation: fail('default_generation_conflict','The shop default changed. Refresh it while keeping your selection.',409)
    if body.matrix_id:
        matrix=await get_matrix(db,actor.tenant_id,body.matrix_id,lock=True)
        if matrix.archived_at: fail('matrix_archived','Restore this matrix before choosing it.',409)
    old=row.default_matrix_id if row else None
    if old==body.matrix_id: return await default_view(db,actor.tenant_id)
    if row is None: row=Policy(tenant_id=actor.tenant_id,generation=0);db.add(row)
    row.default_matrix_id=body.matrix_id;row.generation+=1;row.updated_by=actor.id
    add_event(db,actor,'default_policy',actor.tenant_id,'default.changed',before={'matrix_id':old},after={'matrix_id':body.matrix_id},old_version=generation,new_version=row.generation,matrix_id=body.matrix_id)
    await db.flush()
    return await default_view(db,actor.tenant_id)


async def patch_inventory(db,actor,item,changes,expected):
    if expected is None: fail('pricing_version_required','Refresh this part before changing its pricing.',409)
    if expected != item.pricing_version: fail('pricing_version_conflict','This part pricing changed. Refresh it while keeping your draft.',409)
    values={k:(bool(v) if k=='fixed_sales_price' else amount(v,optional=k in {'pricing_cost_floor','minimum_sale_price'})) for k,v in changes.items()}
    before={k:getattr(item,k) for k in values}
    if all(before[k]==v for k,v in values.items()): return
    old=item.pricing_version
    for k,v in values.items(): setattr(item,k,v)
    item.pricing_version+=1
    add_event(db,actor,'inventory',item.id,'inventory.pricing_changed',before=before,after=values,old_version=old,new_version=item.pricing_version,inventory_id=item.id)


async def load_overlays(db,tenant_id,rows,entity_type='parts_usage'):
    ids=[r.id for r in rows if r.id]
    if not ids: return
    ranked=select(Event.entity_id,Event.event_type,Event.reason,Event.actor_id,Event.created_at,
        func.row_number().over(partition_by=Event.entity_id,order_by=(Event.new_version.desc(),Event.created_at.desc(),Event.id.desc())).label('rank')).where(
        Event.tenant_id==tenant_id,Event.entity_type==entity_type,Event.entity_id.in_(ids),
        Event.event_type.in_(['price.manual','price.stock','price.list'])).subquery()
    events={r.entity_id:r for r in (await db.execute(select(ranked).where(ranked.c.rank==1))).all()}
    for row in rows:
        event=events.get(row.id)
        if event:
            row._pricing_current_source=(row.pricing_snapshot or {}).get('source','legacy_unknown') if event.event_type=='price.list' else 'manual'
            row._pricing_override=None if event.event_type=='price.list' else {'reason':event.reason,'actor_id':str(event.actor_id),'occurred_at':event.created_at.isoformat()}


async def begin_write(db,actor,key,route,payload):
    await authorize(db,actor)
    await lock_tenant_financials(db,actor.tenant_id)
    if not isinstance(key,str): return None,None
    key=validate_idempotency_key(key)
    digest=canonical_fingerprint(route=route,principal_id=actor.id,payload={'tenant':str(actor.tenant_id),'body':payload})
    record=await find_idempotent_response(db,tenant_id=actor.tenant_id,family='p1_work',key=key,fingerprint=digest)
    if record: return record,json.loads(record.response_body)
    record=begin_idempotency(tenant_id=actor.tenant_id,family='p1_work',key=key,fingerprint=digest);db.add(record)
    return record,None


def finish_write(record,body,status_code=200):
    if record: complete_idempotency(record,status_code=status_code,body=body)



def part_receipt(response, usage):
    # Durable private storage is audience-neutral. Never replay an earlier
    # audience-shaped API payload after current authority/presentation changes.
    body=response.model_dump(mode='json')
    body.pop('pricing',None)
    body.update(unit_price=str(usage.unit_price),unit_cost=str(usage.unit_cost) if usage.unit_cost is not None else None,
        list_price=str(usage.list_price) if usage.list_price is not None else None,total_price=str(usage.total_price),
        pricing_version=usage.pricing_version or 0)
    return {'part':body,'origin':usage.pricing_snapshot,'current_source':getattr(usage,'_pricing_current_source',None)}


def replay_part(receipt,actor,requested=None,can_edit=False):
    from app.schemas.repair_order import PartsUsageResponse
    payload=dict(receipt['part']);audience=presentation(actor,requested)
    row=SimpleNamespace(unit_price=Decimal(payload['unit_price']),unit_cost=Decimal(payload['unit_cost']) if payload.get('unit_cost') is not None else None,
        list_price=Decimal(payload['list_price']) if payload.get('list_price') is not None else None,quantity=Decimal(payload['quantity']),
        pricing_version=payload.get('pricing_version',0),pricing_snapshot=receipt.get('origin'),_pricing_current_source=receipt.get('current_source'))
    payload['savings'] = max(Decimal(0), (row.list_price or row.unit_price) - row.unit_price) * row.quantity
    payload['pricing']=safe_price(row,can_override=can_edit and actor.role in EDITORS) if audience=='shop' else None
    return PartsUsageResponse.model_validate({**payload,'pricing_audience':audience})
