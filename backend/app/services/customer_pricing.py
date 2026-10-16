"""DB133 account defaults, immutable intake policy, and factual labor provenance.

Routes own policy/work transactions. reserve_call commits only its known-success
reservation receipt before work begins; no other helper commits.
Saved work never consults a customer's current agreement.
"""
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from uuid import UUID, uuid4
from fastapi import HTTPException
from sqlalchemy import select
from app.db.models.customer import Customer
from app.db.models.customer_pricing import AccountPricingEvent as Event
from app.db.models.parts_pricing import PartsPriceMatrix as Matrix, PartsPriceMatrixRevision as Revision
from app.db.models.tenant import Tenant
from app.db.models.user import UserRole
from app.services import parts_pricing as pricing
from app.services.parts_pricing_rules import PricePolicy, cents, fail
from app.services.internal_fleet import uses_internal_fleet_pricing, fleet_labor_uses_customer_rate

CREATE_ROLES = pricing.EDITORS


def name(customer):
    return (customer.company_name or f'{customer.first_name} {customer.last_name}').strip()


async def lock_customers(db, tenant_id, ids, *, lock=True):
    ids=set(ids)
    query=select(Customer).where(Customer.tenant_id==tenant_id,Customer.id.in_(ids),Customer.deleted_at.is_(None)).order_by(Customer.id).execution_options(populate_existing=True)
    if lock: query=query.with_for_update()
    rows={c.id:c for c in (await db.scalars(query)).all()}
    if set(rows)!=ids: raise HTTPException(404,'Customer not found')
    return rows


async def live_customer(db, tenant_id, customer_id, *, lock=False):
    return (await lock_customers(db,tenant_id,[customer_id],lock=lock))[customer_id]


async def evidence(db, customer):
    version=customer.pricing_version or 0
    if not version:
        if customer.pricing_labor_rate is not None or customer.parts_price_matrix_id is not None:
            fail('account_pricing_unverified','The saved account pricing could not be verified.',409)
        return None
    event=await db.scalar(select(Event).where(Event.tenant_id==customer.tenant_id,Event.entity_type=='customer_policy',Event.entity_id==customer.id,Event.new_version==version))
    if event is None or event.after_values!=values(customer):
        fail('account_pricing_unverified','The saved account pricing could not be verified.',409)
    return event


def values(customer):
    return {'labor_rate':cents(customer.pricing_labor_rate) if customer.pricing_labor_rate is not None else None,
            'parts_matrix_id':str(customer.parts_price_matrix_id) if customer.parts_price_matrix_id else None}


async def matrix_policy(db,tenant_id,matrix_id,*,lock=False):
    query=select(Matrix).where(Matrix.tenant_id==tenant_id,Matrix.id==matrix_id).execution_options(populate_existing=True)
    if lock: query=query.with_for_update()
    matrix=await db.scalar(query)
    if matrix is None: raise HTTPException(404,'Pricing matrix not found')
    if matrix.archived_at: fail('matrix_archived','The selected pricing matrix is unavailable.',409)
    revision=await db.scalar(select(Revision).where(Revision.tenant_id==tenant_id,Revision.matrix_id==matrix.id,Revision.revision==matrix.current_revision))
    if revision is None: fail('account_pricing_unverified','The saved account pricing could not be verified.',409)
    return PricePolicy(0,matrix.id,revision.id,revision.revision,revision.name_snapshot,revision.bands)


def matrix_ref(policy):
    return {'id':str(policy.matrix_id),'revision_id':str(policy.revision_id),'revision':policy.revision,'name':policy.name} if policy.revision_id else None


async def candidate(db,tenant,customer,*,lock=False,counter=False):
    internal=customer is not None and uses_internal_fleet_pricing(customer,tenant)
    if internal and not counter: return None
    event=await evidence(db,customer) if customer else None
    customer_matrix=customer.parts_price_matrix_id if customer and not internal else None
    policy=await matrix_policy(db,tenant.id,customer_matrix,lock=lock) if customer_matrix else await pricing.selected_policy(db,tenant.id,lock=lock)
    snapshot={'schema_version':1,'snapshot_id':str(uuid4()),'captured_at':datetime.now(timezone.utc).isoformat(),
        'customer_id':str(customer.id) if customer else None,'customer_name':name(customer) if customer else None,
        'customer_pricing_version':customer.pricing_version or 0 if customer else 0,'customer_policy_event_id':str(event.id) if event else None,
        'parts':{'source':'customer' if customer_matrix else 'shop','mode':'matrix' if policy.revision_id else 'catalog',
            'matrix':matrix_ref(policy),'shop_default_generation':None if customer_matrix else policy.generation}}
    if counter: snapshot['captured_for']='counter_sale'
    else: snapshot['labor']={'source':'customer' if customer.pricing_labor_rate is not None else 'shop','rate':cents(customer.pricing_labor_rate if customer.pricing_labor_rate is not None else tenant.labor_rate)}
    return snapshot


def stable_policy(snapshot):
    return {k:v for k,v in snapshot.items() if k not in {'snapshot_id','captured_at','customer_name'}} if snapshot else None


def revision_id(snapshot):
    value=((snapshot or {}).get('parts',{}).get('matrix') or {}).get('revision_id')
    return UUID(value) if value else None


def validated_snapshot(snapshot, *, counter=False):
    """Fail closed on incomplete or corrupt saved provenance, never use live terms."""
    def integer(value, minimum=0):
        if type(value) is not int or value < minimum: raise ValueError()
    def uuid(value):
        if not isinstance(value, str): raise ValueError()
        UUID(value)
    try:
        required={'schema_version','snapshot_id','captured_at','customer_id','customer_name','customer_pricing_version','customer_policy_event_id','parts'} | ({'captured_for'} if counter else {'labor'})
        if not isinstance(snapshot,dict) or set(snapshot)!=required or type(snapshot['schema_version']) is not int or snapshot['schema_version']!=1: raise ValueError()
        uuid(snapshot['snapshot_id'])
        captured=datetime.fromisoformat(snapshot['captured_at'].replace('Z','+00:00'))
        if captured.utcoffset() is None or captured.utcoffset().total_seconds()!=0: raise ValueError()
        version=snapshot['customer_pricing_version'];integer(version)
        if snapshot['customer_id'] is None:
            if not counter or snapshot['customer_name'] is not None or version!=0 or snapshot['customer_policy_event_id'] is not None: raise ValueError()
        else:
            uuid(snapshot['customer_id'])
            if not isinstance(snapshot['customer_name'],str): raise ValueError()
            if version: uuid(snapshot['customer_policy_event_id'])
            elif snapshot['customer_policy_event_id'] is not None: raise ValueError()
        part=snapshot['parts']
        if not isinstance(part,dict) or set(part)!={'source','mode','matrix','shop_default_generation'} or part['source'] not in {'shop','customer'}: raise ValueError()
        if part['source']=='customer':
            if not version or snapshot['customer_id'] is None or part['shop_default_generation'] is not None or part['mode']!='matrix': raise ValueError()
        else: integer(part['shop_default_generation'])
        if part['mode']=='matrix':
            matrix=part['matrix']
            if not isinstance(matrix,dict) or set(matrix)!={'id','revision_id','revision','name'}: raise ValueError()
            uuid(matrix['id']);uuid(matrix['revision_id']);integer(matrix['revision'],1)
            if not isinstance(matrix['name'],str) or not 1<=len(matrix['name'])<=100: raise ValueError()
        elif part['mode']!='catalog' or part['matrix'] is not None: raise ValueError()
        if counter:
            if snapshot['captured_for']!='counter_sale': raise ValueError()
        else:
            import re
            labor=snapshot['labor']
            if not isinstance(labor,dict) or set(labor)!={'source','rate'} or labor['source'] not in {'shop','customer'}: raise ValueError()
            if labor['source']=='customer' and not version: raise ValueError()
            if not isinstance(labor['rate'],str) or not re.fullmatch(r'[0-9]+\.[0-9]{2}',labor['rate']): raise ValueError()
            rate=Decimal(labor['rate'])
            if not rate.is_finite() or not 0<=rate<=Decimal('99999999.99') or (labor['source']=='customer' and rate==0): raise ValueError()
        return snapshot
    except (KeyError,TypeError,ValueError,InvalidOperation,AttributeError):
        fail('account_pricing_unverified','The saved work pricing could not be verified.',409)


async def policy_for_saved(db, tenant_id, row, *, lock=False):
    snapshot=getattr(row,'pricing_policy_snapshot',None)
    if snapshot is None:
        if getattr(row,'pricing_matrix_revision_id',None): fail('account_pricing_unverified','The saved work pricing could not be verified.',409)
        return await pricing.selected_policy(db,tenant_id,lock=lock)
    try:
        if row.tenant_id!=tenant_id: raise ValueError()
        snapshot=validated_snapshot(snapshot,counter=hasattr(row,'buyer_name_snapshot') or bool(getattr(row,'_pricing_counter',False)))
        part=snapshot['parts']; rid=revision_id(snapshot)
        if rid!=row.pricing_matrix_revision_id: raise ValueError()
        if part['mode']=='catalog' and rid is None and part['matrix'] is None:
            return PricePolicy(generation=part.get('shop_default_generation') or 0)
        if part['mode']!='matrix' or not rid: raise ValueError()
        revision=await db.scalar(select(Revision).where(Revision.tenant_id==tenant_id,Revision.id==rid))
        if revision is None or str(revision.matrix_id)!=part['matrix']['id'] or revision.revision!=part['matrix']['revision']: raise ValueError()
        return PricePolicy(part.get('shop_default_generation') or 0,revision.matrix_id,revision.id,revision.revision,revision.name_snapshot,revision.bands)
    except (KeyError,TypeError,ValueError):
        fail('account_pricing_unverified','The saved work pricing could not be verified.',409)


async def preview_scope(db,actor,customer_id,vehicle_id=None,*,lock=False):
    if actor.role not in CREATE_ROLES: raise HTTPException(403,'Access denied')
    tenant=await pricing.authorize(db,actor)
    if lock:
        await pricing.lock_tenant_financials(db,actor.tenant_id)
        tenant=await db.scalar(select(Tenant).where(Tenant.id==actor.tenant_id).execution_options(populate_existing=True))
    customer=await live_customer(db,actor.tenant_id,customer_id,lock=lock)
    if vehicle_id:
        from app.db.models.vehicle import Vehicle
        vehicle=await db.scalar(select(Vehicle).where(Vehicle.tenant_id==actor.tenant_id,Vehicle.id==vehicle_id,Vehicle.deleted_at.is_(None)))
        if not vehicle: raise HTTPException(404,'Vehicle not found')
        if actor.role==UserRole.FLEET_MANAGER:
            from app.db.models.vehicle_relationship import FleetMembership
            member=await db.scalar(select(FleetMembership.id).where(FleetMembership.tenant_id==actor.tenant_id,FleetMembership.vehicle_id==vehicle.id,FleetMembership.deleted_at.is_(None),FleetMembership.effective_to.is_(None)).limit(1))
            if not member and not customer.is_internal_fleet: raise HTTPException(403,'Fleet managers can only create work orders for active fleet vehicles')
    elif actor.role==UserRole.FLEET_MANAGER: raise HTTPException(403,'Select an accessible fleet vehicle')
    return tenant,customer


def intake_view(actor,customer_id,vehicle_id,snapshot,presentation=None):
    mode=pricing.presentation(actor,presentation)
    data={'tenant':str(actor.tenant_id),'actor':str(actor.id),'customer':str(customer_id),'vehicle':str(vehicle_id) if vehicle_id else None,'presentation':mode,'policy':stable_policy(snapshot)}
    view={'schema_version':1,'customer_id':str(customer_id),'vehicle_id':str(vehicle_id) if vehicle_id else None,
          'expected_pricing_policy':pricing.signed_digest(data,'c1-intake'),'policy_kind':'external' if snapshot else 'internal','projection':mode}
    if mode=='fleet': view['agreement_applies']=bool(snapshot and (snapshot['labor']['source']=='customer' or snapshot['parts']['source']=='customer'))
    else:
        view['labor']=snapshot['labor'] if snapshot else {'source':'internal','rate':None}
        view['parts']={k:snapshot['parts'][k] for k in ('source','mode')} if snapshot else {'source':'internal','mode':'internal'}
    return view


async def capture(db,actor,customer_id,vehicle_id=None,*,expected=None,presentation=None,lock=True):
    tenant,customer=await preview_scope(db,actor,customer_id,vehicle_id,lock=lock)
    snapshot=await candidate(db,tenant,customer,lock=lock)
    view=intake_view(actor,customer_id,vehicle_id,snapshot,presentation)
    if expected:
        # A customer-only preview may precede truck selection; its authoritative
        # scope is still checked independently above.
        unbound=intake_view(actor,customer_id,None,snapshot,presentation)['expected_pricing_policy']
        if expected not in (view['expected_pricing_policy'],unbound):
            fail('account_pricing_changed','The account pricing changed. Review the current defaults before creating the order.',409,preview=view)
    return snapshot,view


def assign(row,snapshot):
    row.pricing_policy_snapshot=snapshot
    row.pricing_matrix_revision_id=revision_id(snapshot)


def order_view(order):
    snapshot=getattr(order,'pricing_policy_snapshot',None)
    if snapshot is not None:
        snapshot=validated_snapshot(snapshot)
        return {'schema_version':1,'snapshot_id':snapshot['snapshot_id'],'mode':'captured','labor':snapshot['labor'],
                'parts':{k:snapshot['parts'][k] for k in ('source','mode')}}
    mode='internal' if order.is_internal else 'legacy'
    return {'schema_version':1,'snapshot_id':None,'mode':mode,'labor':{'source':mode,'rate':None},'parts':{'source':mode,'mode':mode}}


def counter_view(sale):
    snapshot=getattr(sale,'pricing_policy_snapshot',None)
    if snapshot is None:
        return {'schema_version':1,'snapshot_id':None,'mode':'legacy','parts':{'source':'legacy','mode':'legacy'}}
    snapshot=validated_snapshot(snapshot,counter=True)
    return {'schema_version':1,'snapshot_id':snapshot['snapshot_id'],'mode':'captured','parts':{key:snapshot['parts'][key] for key in ('source','mode')}}


def labor_default(order,tenant,*,legacy_fleet=False):
    snapshot=getattr(order,'pricing_policy_snapshot',None)
    if snapshot is not None and not order.is_internal:
        snapshot=validated_snapshot(snapshot)
        try:
            if snapshot['schema_version']!=1 or snapshot['labor']['source'] not in {'customer','shop'}:raise ValueError()
            rate=Decimal(snapshot['labor']['rate'])
            if not rate.is_finite() or not 0<=rate<=Decimal('99999999.99'):raise ValueError()
            return rate,snapshot['labor']['source']
        except (KeyError,TypeError,ValueError,InvalidOperation): fail('account_pricing_unverified','The saved work pricing could not be verified.',409)
    if order.is_internal or legacy_fleet:
        return (Decimal(tenant.labor_rate),'shop') if fleet_labor_uses_customer_rate(order) else (Decimal(tenant.internal_labor_rate),'internal')
    return Decimal(tenant.labor_rate),'shop'


def new_labor(order,tenant,actor,*,requested=None,intent=None,legacy_fleet=False):
    default,source=labor_default(order,tenant,legacy_fleet=legacy_fleet)
    can_override=getattr(actor,'role',None) in pricing.EDITORS and not order.is_internal
    if intent=='manual' and (requested is None or not can_override):
        fail('labor_price_override_forbidden','You cannot override this labor rate.',403 if not can_override else 422)
    rate=default if requested is None or intent=='default' or not can_override else Decimal(requested)
    current='manual' if intent=='manual' or rate!=default else 'default'
    return rate,{'schema_version':1,'snapshot_id':str(uuid4()),'order_policy_snapshot_id':(getattr(order,'pricing_policy_snapshot',None) or {}).get('snapshot_id'),
                 'default_hourly_rate':cents(default),'source':source,'initial_intent':current},current


def labor_view(line,actor,*,editable=True):
    snapshot=getattr(line,'pricing_snapshot',None) or {}
    return {'source':snapshot.get('source','legacy_unknown'),'current_source':getattr(line,'pricing_source',None) or 'legacy_unknown',
        'default_hourly_rate':snapshot.get('default_hourly_rate'),'charged_hourly_rate':cents(line.hourly_rate),
        'can_override':bool(editable and actor.role in pricing.EDITORS)}


def add_event(db,actor,entity_type,entity_id,*,customer=None,customer_id=None,customer_name=None,order_id=None,sale_id=None,before=None,after=None,old_version=None,new_version=None,reason=None,matrix_id=None,revision_id=None):
    if customer is not None:
        if customer.tenant_id!=actor.tenant_id: raise HTTPException(403,'Access denied')
        customer_id=customer.id;customer_name=name(customer)
    event=Event(id=uuid4(),tenant_id=actor.tenant_id,entity_type=entity_type,entity_id=entity_id,customer_id=customer_id,customer_name=customer_name,
        repair_order_id=order_id,counter_sale_id=sale_id,actor_id=actor.id,actor_name=f'{getattr(actor,"first_name","")} {getattr(actor,"last_name","")}'.strip(),actor_role=actor.role.value,
        correlation_id=uuid4(),before_values=pricing.json_values(before or {}),after_values=pricing.json_values(after or {}),old_version=old_version,new_version=new_version,reason=reason,matrix_id=matrix_id,revision_id=revision_id)
    db.add(event);return event


def audit_labor(db,actor,order,line,*,before=None):
    if actor.tenant_id!=order.tenant_id or line.tenant_id!=order.tenant_id or line.repair_order_id!=order.id:raise HTTPException(403,'Access denied')
    after={'hourly_rate':cents(line.hourly_rate),'source':line.pricing_source}
    if before==after:return
    snapshot=getattr(order,'pricing_policy_snapshot',None) or {}
    add_event(db,actor,'labor',line.id,customer_id=order.customer_id,customer_name=snapshot.get('customer_name'),order_id=order.id,before=before,after=after)


def observe_rate_change(db,actor,order,line,previous_rate,previous_source):
    if Decimal(previous_rate)!=Decimal(line.hourly_rate):
        line.pricing_source='manual'
        audit_labor(db,actor,order,line,before={'hourly_rate':cents(previous_rate),'source':previous_source})


async def config_view(db,tenant,customer):
    if uses_internal_fleet_pricing(customer,tenant):
        effective={'labor':{'source':'internal','rate':None},'parts':{'source':'internal','mode':'internal','matrix':None}}
        eligible=False
    else:
        snapshot=await candidate(db,tenant,customer)
        effective={'labor':snapshot['labor'],'parts':{k:snapshot['parts'][k] for k in ('source','mode','matrix')}};eligible=True
    return {'schema_version':1,'customer_id':str(customer.id),'version':customer.pricing_version or 0,'configured':values(customer),
        'effective':effective,'can_edit':eligible,'ineligible_reason':None if eligible else 'internal_account','updated_at':customer.pricing_updated_at.isoformat() if customer.pricing_updated_at else None}


async def write_config(db,actor,body,customer_id):
    tenant=await db.scalar(select(Tenant).where(Tenant.id==actor.tenant_id).execution_options(populate_existing=True))
    customer=await live_customer(db,actor.tenant_id,customer_id,lock=True)
    if uses_internal_fleet_pricing(customer,tenant):fail('internal_account_pricing','Internal accounts use the existing internal pricing settings.',409)
    if (customer.pricing_version or 0)!=body.expected_version:fail('customer_pricing_conflict','These pricing settings changed. Refresh them while keeping your draft.',409,field='expected_version')
    await evidence(db,customer)
    if body.parts_matrix_id:await matrix_policy(db,actor.tenant_id,body.parts_matrix_id,lock=True)
    before=values(customer);after={'labor_rate':cents(body.labor_rate) if body.labor_rate is not None else None,'parts_matrix_id':str(body.parts_matrix_id) if body.parts_matrix_id else None}
    if before!=after:
        old=customer.pricing_version or 0
        customer.pricing_labor_rate=body.labor_rate;customer.parts_price_matrix_id=body.parts_matrix_id;customer.pricing_version=old+1
        customer.pricing_updated_at=datetime.now(timezone.utc);customer.pricing_updated_by=actor.id
        add_event(db,actor,'customer_policy',customer.id,customer=customer,before=before,after=after,old_version=old,new_version=old+1,reason=body.reason,matrix_id=body.parts_matrix_id)
        await db.flush()
    return await config_view(db,tenant,customer)


async def begin_intake(db,actor,key,route,payload):
    """Canonical identity receipt; responses are projected after current authorization."""
    from app.services.parts_operations_service import validate_idempotency_key, canonical_fingerprint, find_idempotent_response, begin_idempotency
    await pricing.lock_tenant_financials(db,actor.tenant_id)
    if not isinstance(key,str):return None,None
    key=validate_idempotency_key(key)
    digest=canonical_fingerprint(route=route,principal_id=actor.id,payload=payload)
    try:receipt=await find_idempotent_response(db,tenant_id=actor.tenant_id,family='c1_intake',key=key,fingerprint=digest)
    except HTTPException as exc:
        if exc.status_code==409:fail('idempotency_conflict','This action key already belongs to a different request.',409)
        raise
    if receipt:
        import json
        from app.db.models.repair_order import RepairOrder
        saved=await db.scalar(select(RepairOrder).where(RepairOrder.id==UUID(json.loads(receipt.response_body)['order_id']),RepairOrder.tenant_id==actor.tenant_id,RepairOrder.deleted_at.is_(None)))
        if saved is None:raise HTTPException(404,'Repair order not found')
        await preview_scope(db,actor,saved.customer_id,saved.vehicle_id)
        return receipt,saved
    receipt=begin_idempotency(tenant_id=actor.tenant_id,family='c1_intake',key=key,fingerprint=digest);db.add(receipt)
    return receipt,None


async def reserve_call(db,actor,customer_id,vehicle_id,reference_token,*,expected=None,presentation=None):
    """Retain known-success provider identity across later local pricing conflicts.

    Only this key's advisory/receipt lock spans the bounded provider request;
    no tenant/customer financial lock does. An ambiguous provider response is
    still ambiguous: this receipt cannot guarantee recovery before it commits.
    """
    import json
    from sqlalchemy.exc import DBAPIError
    from app.services import repair_intake_reference as intake
    from app.services.parts_operations_service import canonical_fingerprint, find_idempotent_response, begin_idempotency, complete_idempotency
    if actor.role not in pricing.MANAGERS | {UserRole.RECEPTIONIST}:raise HTTPException(403,'Only shop staff can select an originating call')
    tenant,_=await preview_scope(db,actor,customer_id,vehicle_id)
    key=pricing.signed_digest({'tenant':str(actor.tenant_id),'actor':str(actor.id),'reference':reference_token},'c1-call-key')
    digest=canonical_fingerprint(route='c1-call-reservation',principal_id=actor.id,payload={'customer_id':str(customer_id),'vehicle_id':str(vehicle_id)})
    try:
        receipt=await find_idempotent_response(db,tenant_id=actor.tenant_id,family='c1_call_reservation',key=key,fingerprint=digest)
    except DBAPIError as exc:
        if getattr(exc.orig,'sqlstate',getattr(exc.orig,'pgcode',None))=='55P03':
            await db.rollback();fail('call_intake_in_progress','This call intake is still being reserved. Retry the same selection.',409)
        raise
    except HTTPException as exc:
        if exc.status_code==409:fail('idempotency_conflict','This call selection already belongs to a different intake.',409)
        raise
    if receipt:
        try:
            stored=json.loads(receipt.response_body)
            bound={'schema_version':1,'tenant_id':str(actor.tenant_id),'actor_id':str(actor.id),'customer_id':str(customer_id),'vehicle_id':str(vehicle_id)}
            if set(stored)!=set(bound)|{'repair_order_uuid','elis_opportunity_id','callrail_call_id','recorded_at'} or any(stored.get(k)!=v for k,v in bound.items()): raise ValueError()
            recorded=datetime.fromisoformat(stored['recorded_at'].replace('Z','+00:00'))
            if recorded.utcoffset() is None or recorded.utcoffset().total_seconds()!=0: raise ValueError()
            reservation=intake.IntakeReservation.model_validate(stored)
        except (KeyError,TypeError,ValueError,AttributeError):
            fail('account_pricing_unverified','The saved call reservation could not be verified.',409)
        await preview_scope(db,actor,customer_id,vehicle_id)
        return reservation
    if expected:await capture(db,actor,customer_id,vehicle_id,expected=expected,presentation=presentation,lock=False)
    reservation=await intake.reserve_originating_call(tenant,actor.id,reference_token)
    receipt=begin_idempotency(tenant_id=actor.tenant_id,family='c1_call_reservation',key=key,fingerprint=digest)
    db.add(receipt);complete_idempotency(receipt,status_code=200,body={**reservation.model_dump(mode='json'),'schema_version':1,'tenant_id':str(actor.tenant_id),'actor_id':str(actor.id),'customer_id':str(customer_id),'vehicle_id':str(vehicle_id),'recorded_at':datetime.now(timezone.utc).isoformat()})
    await db.commit()  # reservation evidence only; no work/customer/stock mutation yet
    return reservation
