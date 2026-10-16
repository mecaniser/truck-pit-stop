"""DB134 transaction-owned program, work and evidence commands.

Callers retain transaction ownership for lifecycle/finalization hooks. Reads
never refresh targets or mutate telemetry, source work or financial history.
"""
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import hmac
import json
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from fastapi import HTTPException
from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import selectinload
from app.db.models.maintenance import MaintenanceProgram as Program, MaintenanceProgramEvent as Event, MaintenanceWorkLink as WorkLink, MaintenanceOperationLink as OperationLink, MaintenanceCompletion as Completion, MaintenanceReading as Reading
from app.db.models.customer import Customer
from app.db.models.tenant import Tenant
from app.db.models.user import UserRole
from app.db.models.vehicle import Vehicle
from app.db.models.vehicle_relationship import FleetMembership, VehicleCustomerRelationship
from app.db.models.service import Service
from app.db.models.repair_order import RepairOrder, RepairOrderStatus
from app.db.models.labor import Labor
from app.schemas import maintenance as wire
from app.services import maintenance_rules as rules, parts_pricing as pricing
from app.services.parts_operations_service import validate_idempotency_key, canonical_fingerprint, find_idempotent_response, begin_idempotency, complete_idempotency

fail=rules.fail
STAFF={UserRole.GARAGE_OWNER,UserRole.GARAGE_ADMIN,UserRole.RECEPTIONIST}
MANAGERS={UserRole.GARAGE_OWNER,UserRole.GARAGE_ADMIN,UserRole.FLEET_MANAGER}
OCCUPYING={'active','pending_evidence','review_required'}
FINALIZED={RepairOrderStatus.COMPLETED,RepairOrderStatus.INVOICED,RepairOrderStatus.PAID}


def now():
    return datetime.now(timezone.utc)


def json_value(value):
    return json.loads(json.dumps(value,default=str))


async def authorize(db,actor,channel,*,manager=False):
    allowed=STAFF if channel=='shop' else MANAGERS
    if not actor.tenant_id or actor.role not in allowed or (manager and actor.role not in MANAGERS):
        fail('maintenance_forbidden','Access denied.',403)
    tenant=await db.scalar(select(Tenant).where(Tenant.id==actor.tenant_id,Tenant.deleted_at.is_(None),Tenant.is_active.is_(True)))
    if tenant is None:
        fail('maintenance_forbidden','Access denied.',403)
    try:ZoneInfo(tenant.timezone)
    except (ZoneInfoNotFoundError,TypeError):fail('maintenance_invalid_input','The shop timezone must be corrected before maintaining service dates.',409)
    return tenant


def vehicle_scope(actor,channel):
    clauses=[Vehicle.tenant_id==actor.tenant_id,Vehicle.deleted_at.is_(None)]
    if channel=='fleet':
        clauses += [select(FleetMembership.id).where(FleetMembership.tenant_id==actor.tenant_id,FleetMembership.vehicle_id==Vehicle.id,FleetMembership.effective_to.is_(None),FleetMembership.deleted_at.is_(None)).exists(),
                    select(Customer.id).where(Customer.id==Vehicle.customer_id,Customer.tenant_id==actor.tenant_id,Customer.deleted_at.is_(None)).exists()]
    return clauses


async def load_vehicle(db,actor,channel,vehicle_id,*,lock=False):
    statement=select(Vehicle).where(Vehicle.id==vehicle_id,*vehicle_scope(actor,channel)).execution_options(populate_existing=True)
    if lock:statement=statement.with_for_update(of=Vehicle)
    row=await db.scalar(statement)
    if row is None:fail('maintenance_not_found','Maintenance vehicle or work was not found.',404)
    return row


async def load_program(db,actor,vehicle_id,program_id,*,lock=False):
    statement=select(Program).where(Program.id==program_id,Program.tenant_id==actor.tenant_id,Program.vehicle_id==vehicle_id).execution_options(populate_existing=True)
    if lock:statement=statement.with_for_update()
    row=await db.scalar(statement)
    if row is None:fail('maintenance_not_found','Maintenance program was not found.',404)
    return row


def check_version(program,expected):
    if program.version!=expected:
        fail('maintenance_version_conflict','This maintenance program changed. Refresh it before saving.',current_version=program.version)


def intervals(program):
    return {'days':program.interval_days,'miles':program.interval_miles,'engine_hours':rules.decimal_text(program.interval_hours) if program.interval_hours is not None else None}


def targets(program):
    return {'due_on':program.target_due_on.isoformat() if program.target_due_on else None,'odometer_miles':program.target_miles,'engine_hours':rules.decimal_text(program.target_hours) if program.target_hours is not None else None}


def configuration(program):
    return {'name':program.name,'mode':program.mode,'intervals':intervals(program),'service':program.service_snapshot,
            'legacy_package':program.legacy_package,'legacy_snapshot':program.legacy_snapshot,'baseline_generation':program.baseline_generation}


def snapshot(program):
    return {**configuration(program),'id':str(program.id),'version':program.version,'targets':targets(program),'current_cycle':program.current_cycle,
            'review_codes':program.review_codes,'controlling_completion_id':str(program.controlling_completion_id) if program.controlling_completion_id else None,
            'archived_at':rules.iso(program.archived_at),'baseline_snapshot':program.baseline_snapshot,'target_provenance':program.target_provenance}


def append_event(db,actor,program,action,before,*,reason=None,link=None,extra=None):
    after=snapshot(program)
    if link is not None:after['work_link']={'id':str(link.id),'version':link.version,'state':link.state}
    after.update(extra or {})
    db.add(Event(tenant_id=program.tenant_id,program_id=program.id,version=program.version,action=action,actor_id=actor.id if actor else None,
                 reason=reason,before_values=before,after_values=after,created_at=program.updated_at or now()))


def touch(program,actor):
    program.version+=1;program.updated_by=actor.id;program.updated_at=now()


async def start_command(db,actor,channel,vehicle_id,family,key,body,route,*,manager=False):
    tenant=await authorize(db,actor,channel,manager=manager)
    try:key=str(UUID(validate_idempotency_key(key)))
    except (ValueError,TypeError):fail('maintenance_invalid_input','Use a UUID Idempotency-Key.',422)
    await pricing.lock_tenant_financials(db,actor.tenant_id)
    await load_vehicle(db, actor, channel, vehicle_id)
    def referenced_orders(value):
        found = set()
        if isinstance(value, dict):
            if value.get('source_kind') == 'repair_order' and value.get('source_id'):
                try: found.add(UUID(value['source_id']))
                except (ValueError, TypeError): fail('maintenance_not_found', 'Service evidence was not found.', 404)
            if value.get('kind') == 'repair_order' and value.get('id'):
                found.add(UUID(value['id']))
            if value.get('repair_order_id'):
                found.add(UUID(value['repair_order_id']))
            for child in value.values(): found.update(referenced_orders(child))
        elif isinstance(value, list):
            for child in value: found.update(referenced_orders(child))
        return found
    order_ids = referenced_orders(body.model_dump(mode='json'))
    intent = getattr(body, 'evidence', None)
    if intent is not None and hasattr(body, 'program'):
        # Lock only the referenced source and current affected claims. Unrelated
        # deleted historical work must not prevent a later authorized service.
        if hasattr(intent, 'completion_id'):
            source = await db.scalar(select(Completion).where(Completion.tenant_id == actor.tenant_id,
                Completion.program_id == body.program.program_id, Completion.id == intent.completion_id))
            if source and source.source_kind == 'repair_order':
                order_ids.add(source.source_id)
        link_query = select(WorkLink.repair_order_id).where(WorkLink.tenant_id == actor.tenant_id,
            WorkLink.program_id == body.program.program_id)
        if hasattr(intent, 'work_link_id'):
            link_query = link_query.where(WorkLink.id == intent.work_link_id)
        else:
            link_query = link_query.where(WorkLink.state.in_(OCCUPYING))
        order_ids.update((await db.scalars(link_query)).all())
    # All involved native orders precede vehicle/program locks, including
    # corrected evidence and later work. Deleted same-scope sources can revoke.
    for order_id in sorted(order_ids, key=str):
        row = await db.scalar(select(RepairOrder).where(RepairOrder.id == order_id, RepairOrder.tenant_id == actor.tenant_id,
            RepairOrder.vehicle_id == vehicle_id).with_for_update())
        if row is None:
            fail('maintenance_not_found', 'Service evidence was not found.', 404)
        if row.deleted_at is None:
            await source_order(db, actor, channel, vehicle_id, order_id, finalized=False)
        elif intent is None or intent.action not in {'revoke', 'reaffirm', 'supersede'}:
            fail('maintenance_not_found', 'Service evidence was not found.', 404)
    vehicle=await load_vehicle(db,actor,channel,vehicle_id,lock=True)
    payload=body.model_dump(mode='json')
    def semantics(value):
        if isinstance(value,dict):return {k:semantics(v) for k,v in value.items() if k not in {'expected_target_fingerprint','expected_work_fingerprint'}}
        if isinstance(value,list):return [semantics(v) for v in value]
        return value
    digest=canonical_fingerprint(route=route,principal_id=actor.id,payload={'tenant_id':str(actor.tenant_id),'body':semantics(payload)})
    try:record=await find_idempotent_response(db,tenant_id=actor.tenant_id,family=family,key=key,fingerprint=digest)
    except HTTPException:fail('idempotency_conflict','This action key already belongs to another request.')
    if record is not None:return tenant,vehicle,record,json.loads(record.response_body)
    record=begin_idempotency(tenant_id=actor.tenant_id,family=family,key=key,fingerprint=digest);db.add(record)
    return tenant,vehicle,record,None


async def finish_command(db,record,result,*,status_code=200):
    await db.flush();complete_idempotency(record,status_code=status_code,body=result);await db.commit()


async def service_ref(db,tenant_id,service_id,*,saved=None,required=False):
    if service_id is None:return None
    row=await db.scalar(select(Service).where(Service.id==service_id,Service.tenant_id==tenant_id))
    availability='missing' if row is None or row.deleted_at is not None else 'active' if row.is_active else 'archived'
    if required and availability!='active':fail('maintenance_template_unavailable','The selected service template is unavailable.')
    return {'id':str(service_id),'name':saved['name'] if saved else row.name if row else 'Unavailable service','availability':availability}


async def telemetry_candidates(db,vehicle,as_of,zone):
    """Only stored, currently scoped observations. No provider calls or new grants."""
    from app.db.models.fleet_telemetry import FleetTelemetrySnapshot as Telemetry
    from app.db.models.motive_oauth import MotiveConnection, MotiveRemoteVehicle
    from app.services.fleet_telemetry import within
    from app.services.motive_oauth import configured
    members=list((await db.scalars(select(FleetMembership).join(Customer,Customer.id==FleetMembership.fleet_customer_id).where(
        FleetMembership.tenant_id==vehicle.tenant_id,FleetMembership.vehicle_id==vehicle.id,FleetMembership.deleted_at.is_(None),
        FleetMembership.effective_from<=as_of,or_(FleetMembership.effective_to.is_(None),FleetMembership.effective_to>as_of),
        Customer.tenant_id==vehicle.tenant_id,Customer.deleted_at.is_(None)))).all())
    by_id={m.id:m for m in members};result={meter:[] for meter in rules.METERS}
    if not members:return result
    for meter in rules.METERS:
        # Identity predicates precede ordering so an unrelated newer capture
        # cannot hide the latest valid observation for this meter.
        rows=list((await db.scalars(select(Telemetry).where(Telemetry.tenant_id==vehicle.tenant_id,Telemetry.vehicle_id==vehicle.id,
            Telemetry.deleted_at.is_(None),Telemetry.fleet_membership_id.in_(by_id),Telemetry.verified_vin==vehicle.vin,
            getattr(Telemetry,meter).is_not(None)).order_by(Telemetry.observed_at.desc().nulls_last(),Telemetry.captured_at.desc(),Telemetry.id).limit(50))).all())
        for row in rows:
            member=by_id[row.fleet_membership_id]
            valid=row.fleet_customer_id==member.fleet_customer_id and within(member,rules.utc(row.observed_at or row.captured_at))
            result[meter].append(rules.observation(getattr(row,meter),meter,source='motive_dashboard_manual',basis='dashboard_unspecified',observed_at=row.observed_at,
                precision=row.observed_precision,captured_at=row.captured_at,source_id=row.id,as_of=as_of,zone=zone,identity_matches=valid))
    if configured(vehicle.tenant_id):
        remotes=(await db.execute(select(MotiveRemoteVehicle,MotiveConnection).join(MotiveConnection,MotiveConnection.id==MotiveRemoteVehicle.connection_id).where(
            MotiveRemoteVehicle.tenant_id==vehicle.tenant_id,MotiveRemoteVehicle.vehicle_id==vehicle.id,MotiveRemoteVehicle.deleted_at.is_(None),MotiveRemoteVehicle.provider_status=='active',
            MotiveConnection.tenant_id==vehicle.tenant_id,MotiveConnection.deleted_at.is_(None),MotiveConnection.status.in_(['connected','provider_error'])))).all()
        by_customer={m.fleet_customer_id:m for m in members}
        for remote,connection in remotes:
            member=by_customer.get(connection.fleet_customer_id)
            if not member:continue
            valid=bool(remote.mapped_at and remote.metrics_observed_at and remote.vin and vehicle.vin and remote.vin.strip().upper()==vehicle.vin.strip().upper()
                       and within(member,rules.utc(remote.mapped_at)) and within(member,rules.utc(remote.metrics_observed_at)) and rules.utc(remote.metrics_observed_at)>=rules.utc(remote.mapped_at))
            for meter in rules.METERS:
                value=getattr(remote,'true_'+meter);basis='calibrated'
                if value is None:value=getattr(remote,'virtual_'+meter);basis='virtual'
                if value is not None:result[meter].append(rules.observation(value,meter,source='motive_api',basis=basis,observed_at=remote.metrics_observed_at,
                    captured_at=remote.metrics_received_at,source_id=remote.id,as_of=as_of,zone=zone,identity_matches=valid))
    return result


async def current_readings(db,program,vehicle,as_of,zone,*,candidates=None):
    candidates=candidates or await telemetry_candidates(db,vehicle,as_of,zone)
    candidates={meter:list(rows) for meter,rows in candidates.items()}
    for meter in rules.METERS:
        rows=list((await db.scalars(select(Reading).where(Reading.tenant_id==vehicle.tenant_id,Reading.vehicle_id==vehicle.id,getattr(Reading,meter).is_not(None))
            .order_by(Reading.observed_at.desc(),Reading.id).limit(1))).all())
        for row in rows:candidates[meter].append(rules.observation(getattr(row,meter),meter,source='maintenance_manual',basis=row.source,observed_at=row.observed_at,
            captured_at=row.created_at,source_id=row.id,as_of=as_of,zone=zone))
    reset_at = (program.baseline_snapshot or {}).get('comparison_reset_at')
    if reset_at:
        boundary = rules.utc(reset_at)
        # A rebaseline is an explicit new meter generation. Older observations
        # are not evidence of post-reset travel, even on the same calendar day.
        # This admission boundary does not fabricate a service observation time.
        candidates = {meter: [row for row in rows if row.get('observed_at') and row.get('captured_at')
            and rules.utc(row['observed_at']) >= boundary and rules.utc(row['captured_at']) >= boundary]
            for meter, rows in candidates.items()}
    baseline=(program.baseline_snapshot or {}).get('attestation')
    accepted_at=(program.baseline_snapshot or {}).get('confirmed_at')
    if program.controlling_completion_id:
        controlling=await db.scalar(select(Completion).where(Completion.id==program.controlling_completion_id,Completion.tenant_id==program.tenant_id,Completion.program_id==program.id))
        if controlling and controlling.performed_on:
            baseline={'performed_on':controlling.performed_on.isoformat(),'readings':controlling.readings}
            anchor=controlling
            seen=set()
            while anchor.action == 'reaffirm' and anchor.supersedes_id and anchor.id not in seen:
                seen.add(anchor.id)
                prior=await db.scalar(select(Completion).where(Completion.id==anchor.supersedes_id,
                    Completion.tenant_id==program.tenant_id,Completion.program_id==program.id))
                if prior is None:break
                anchor=prior
            accepted_at=rules.iso(anchor.created_at)
    result={}
    for meter in rules.METERS:
        baseline_reading=(baseline or {}).get('readings',{}).get(meter)
        if baseline_reading:
            captured=dict(baseline_reading);captured['freshness']=rules.freshness(captured.get('observed_at'),captured.get('observed_on'),as_of,zone)
            candidates[meter].append(captured)
            admitted=[]
            for row in candidates[meter]:
                if row['comparison_value'] is not None and Decimal(row['comparison_value'])<Decimal(baseline_reading['comparison_value']):
                    observed=rules.utc(row['observed_at']) if row.get('observed_at') else None
                    captured_at=rules.utc(row['captured_at']) if row.get('captured_at') else None
                    observed_on=observed.astimezone(ZoneInfo(zone)).date().isoformat() if observed else row.get('observed_on')
                    # A date-only actual service cannot be ranked at midnight
                    # against observations already known when it was accepted.
                    # This is an admission boundary, never an invented service time.
                    if baseline_reading.get('observed_at') is None and accepted_at and observed_on==baseline.get('performed_on'):
                        boundary=rules.utc(accepted_at)
                        if not (observed and captured_at and observed>boundary and captured_at>boundary):
                            continue
                    row={**row,'admission':'regression','comparison_value':None}
                admitted.append(row)
            candidates[meter]=admitted
        baseline_on=datetime.fromisoformat(baseline['performed_on']).date() if baseline else None
        result[meter]=rules.choose_observation(candidates[meter],baseline_on=baseline_on,zone=zone)
    return result


async def safe_work(db,actor,channel,link):
    operation_ids=list((await db.scalars(select(OperationLink.operation_id).where(OperationLink.tenant_id==actor.tenant_id,OperationLink.work_link_id==link.id,OperationLink.state=='active').order_by(OperationLink.operation_id))).all())
    order=await db.scalar(select(RepairOrder).where(RepairOrder.id==link.repair_order_id,RepairOrder.tenant_id==actor.tenant_id,RepairOrder.deleted_at.is_(None)))
    can_open=order is not None
    if can_open and actor.role == UserRole.MECHANIC:
        from app.api.v1.endpoints.repair_orders import _check_mechanic_order_assignment
        try: _check_mechanic_order_assignment(actor, order)
        except HTTPException: can_open = False
    if can_open and channel=='fleet':
        from app.api.v1.endpoints.fleet import _load_fleet_ro_or_404
        try:await _load_fleet_ro_or_404(db,actor.tenant_id,order.id)
        except HTTPException:can_open=False
    return {'work_link_id':str(link.id),'version':link.version,'cycle':link.cycle,'repair_order_id':str(order.id) if can_open else None,
            'order_number':order.order_number if can_open else None,'state':link.state,'operation_ids':[str(value) for value in operation_ids] if can_open else [],'can_open':can_open}


def safe_readings(readings, channel, role=None):
    result = json_value(readings)
    if channel == 'fleet' or role not in {UserRole.GARAGE_OWNER, UserRole.GARAGE_ADMIN}:
        for reading in result.values():
            if reading and reading.get('source') == 'service_evidence':
                # Native source links have their own currently authorized
                # projection. Meter provenance must not reveal private outside IDs.
                reading['source_id'] = None
    return result


async def program_view(db,actor,channel,program,vehicle,tenant,as_of,*,candidates=None):
    readings=safe_readings(await current_readings(db,program,vehicle,as_of,tenant.timezone,candidates=candidates), channel, actor.role)
    links=list((await db.scalars(select(WorkLink).where(WorkLink.tenant_id==program.tenant_id,WorkLink.program_id==program.id,WorkLink.state.in_(OCCUPYING)).order_by(WorkLink.cycle.desc(),WorkLink.id))).all())
    work=next((row for row in links if row.cycle==program.current_cycle),links[0] if links else None)
    service=await service_ref(db,program.tenant_id,program.service_id,saved=program.service_snapshot)
    package=None if program.mode=='independent' else [await service_ref(db,program.tenant_id,UUID(saved['id']),saved=saved) for saved in (program.legacy_package or [])]
    review_codes = list(program.review_codes or [])
    due=rules.due(intervals(program),targets(program),readings,as_of=as_of,zone=tenant.timezone,legacy=program.mode=='legacy')
    if any(due[dimension]['state'] != 'disabled' and readings[meter] and readings[meter]['admission']=='regression'
        for meter,dimension in [('odometer_miles','miles'),('engine_hours','engine_hours')]):
        review_codes.append('reading_regression')
    can_edit=program.archived_at is None
    return {'id':str(program.id),'vehicle_id':str(program.vehicle_id),'name':program.name,'version':program.version,'mode':program.mode,
            'intervals':intervals(program),'targets':targets(program),'target_provenance':program.target_provenance,'service':service,'legacy_package':package,
            'current_cycle':program.current_cycle,'archived_at':rules.iso(program.archived_at),
            'due':due,
            'work':await safe_work(db,actor,channel,work) if work else None,
            'review':{'required':bool(review_codes),'codes':review_codes,'completion_id':str(program.controlling_completion_id) if program.controlling_completion_id else None},
            'capabilities':{'can_edit':can_edit,'can_plan':can_edit and not links and not review_codes,
                'can_record_evidence':can_edit and actor.role in MANAGERS,'can_archive':program.archived_at is not None or (not links and not review_codes)}}


async def program_page(db, actor, channel, *, vehicle_id=None, customer_id=None, state=None,
                       search=None, include_archived=False, skip=0, limit=25):
    tenant = await authorize(db, actor, channel)
    as_of = now()
    if vehicle_id is not None:
        await load_vehicle(db, actor, channel, vehicle_id)
    query = select(Program, Vehicle).join(Vehicle, and_(Vehicle.id == Program.vehicle_id, Vehicle.tenant_id == Program.tenant_id)).where(
        Program.tenant_id == actor.tenant_id, *vehicle_scope(actor, channel))
    if vehicle_id is not None:
        query = query.where(Program.vehicle_id == vehicle_id)
    if not include_archived:
        query = query.where(Program.archived_at.is_(None))
    if customer_id is not None:
        # Only a currently authorized owner/operator relationship can select a
        # vehicle. Historic invoice billing is deliberately not an entitlement.
        live_customer = select(Customer.id).where(Customer.id == customer_id, Customer.tenant_id == actor.tenant_id, Customer.deleted_at.is_(None)).exists()
        relation = select(VehicleCustomerRelationship.id).where(
            VehicleCustomerRelationship.tenant_id == actor.tenant_id, VehicleCustomerRelationship.vehicle_id == Vehicle.id,
            VehicleCustomerRelationship.customer_id == customer_id, VehicleCustomerRelationship.relationship_type.in_(['owner', 'operator']),
            VehicleCustomerRelationship.deleted_at.is_(None), VehicleCustomerRelationship.effective_from <= as_of,
            or_(VehicleCustomerRelationship.effective_to.is_(None), VehicleCustomerRelationship.effective_to > as_of)).exists()
        query = query.where(live_customer, or_(Vehicle.customer_id == customer_id, relation))
    if search and search.strip():
        term = search.strip()
        query = query.where(or_(*(field.icontains(term, autoescape=True) for field in (Program.name, Vehicle.unit_number, Vehicle.vin))))
    rows = (await db.execute(query)).all()
    candidates = {}
    items = []
    for program, vehicle in rows:
        if vehicle.id not in candidates:
            candidates[vehicle.id] = await telemetry_candidates(db, vehicle, as_of, tenant.timezone)
        item = await program_view(db, actor, channel, program, vehicle, tenant, as_of, candidates=candidates[vehicle.id])
        matches = state is None or (state == 'in_work' and item['work'] is not None) or (state == 'review_required' and item['review']['required']) or item['due']['state'] == state
        if matches:
            items.append(item)
    urgency = {'overdue': 0, 'due': 1, 'unknown': 2, 'current': 3}
    items.sort(key=lambda item: (item['archived_at'] is not None, urgency[item['due']['state']], item['targets']['due_on'] or '9999-12-31', item['name'].casefold(), item['id']))
    counts = {key: 0 for key in ('active', 'overdue', 'due', 'unknown', 'in_work', 'review_required')}
    for item in items:
        counts['active'] += item['archived_at'] is None
        if item['due']['state'] in counts:
            counts[item['due']['state']] += 1
        counts['in_work'] += item['work'] is not None
        counts['review_required'] += item['review']['required']
    return {'schema_version': 1, 'as_of': rules.iso(as_of), 'timezone': tenant.timezone, 'items': items[skip:skip + limit],
            'total': len(items), 'has_more': skip + limit < len(items), 'counts': counts}


async def reading_command(db, actor, vehicle_id, body, key):
    tenant, vehicle, receipt, repeated = await start_command(db, actor, body.channel, vehicle_id, 'm1_reading', key, body, f'/vehicles/{vehicle_id}/maintenance-readings')
    as_of = now()
    if repeated:
        row = await db.scalar(select(Reading).where(Reading.id == UUID(repeated['reading_id']), Reading.tenant_id == actor.tenant_id, Reading.vehicle_id == vehicle_id))
        if row is None:
            fail('maintenance_not_found', 'The saved reading was not found.', 404)
    else:
        if rules.utc(body.observed_at) > as_of + timedelta(minutes=5):
            fail('maintenance_invalid_reading', 'Observation time cannot be in the future.', 422, field='observed_at')
        row = Reading(id=uuid4(), tenant_id=actor.tenant_id, vehicle_id=vehicle_id, observed_at=body.observed_at,
                      odometer_miles=body.odometer_miles, engine_hours=Decimal(body.engine_hours) if body.engine_hours is not None else None,
                      source=body.source, note=body.note, actor_id=actor.id, request_id=UUID(key), created_at=as_of)
        db.add(row)
        await finish_command(db, receipt, {'reading_id': str(row.id)}, status_code=201)
    return {'schema_version': 1, 'observation_id': str(row.id), 'observed_at': rules.iso(row.observed_at),
            'captured_at': rules.iso(row.created_at), 'replayed': repeated is not None}


async def source_order(db, actor, channel, vehicle_id, order_id, *, finalized=True, lock=False):
    from app.db.models.inventory import PartsUsage
    # Refreshing the source inside finalization must not expire the canonical
    # children already loaded by that transaction's financial publication path.
    query = select(RepairOrder).where(RepairOrder.id == order_id, RepairOrder.tenant_id == actor.tenant_id,
        RepairOrder.vehicle_id == vehicle_id, RepairOrder.deleted_at.is_(None)).options(
            selectinload(RepairOrder.customer), selectinload(RepairOrder.vehicle), selectinload(RepairOrder.labor_items),
            selectinload(RepairOrder.parts_usage).selectinload(PartsUsage.inventory_item)).execution_options(populate_existing=True)
    if lock:
        query = query.with_for_update(of=RepairOrder)
    order = await db.scalar(query)
    if order is None:
        fail('maintenance_not_found', 'Maintenance vehicle or work was not found.', 404)
    if channel == 'fleet':
        from app.api.v1.endpoints.fleet import _load_fleet_ro_or_404
        try:
            await _load_fleet_ro_or_404(db, actor.tenant_id, order_id)
        except HTTPException:
            fail('maintenance_not_found', 'Maintenance vehicle or work was not found.', 404)
    if finalized and order.status not in FINALIZED:
        fail('maintenance_invalid_input', 'Use completed, invoiced or paid service work.', 422)
    return order


async def source_context(db, actor, channel, vehicle, source, *, finalized=True):
    """Only source facts relevant to maintenance; no money, notes or documents."""
    if source.kind == 'repair_order':
        order = await source_order(db, actor, channel, vehicle.id, source.id, finalized=finalized)
        operations = (await db.execute(select(Labor.id, Labor.source_service_id, Labor.execution_version, Labor.execution_status, Labor.completed_at, Labor.deleted_at)
            .where(Labor.tenant_id == actor.tenant_id, Labor.repair_order_id == order.id).order_by(Labor.id))).all()
        evidence = {'kind': source.kind, 'id': str(order.id), 'vehicle_id': str(order.vehicle_id), 'status': order.status.value,
            'deleted_at': rules.iso(order.deleted_at), 'completed_at': rules.iso(order.work_completed_at),
            'mileage_in': order.mileage_in, 'mileage_in_carried': order.mileage_in_carried, 'mileage_out': order.mileage_out,
            'operations': [json_value(dict(row._mapping)) for row in operations]}
        semantic = {**evidence, 'status': 'finalized' if order.status in FINALIZED else order.status.value}
        return order, evidence, pricing.signed_digest(semantic, 'm1_source')
    if actor.role not in {UserRole.GARAGE_OWNER, UserRole.GARAGE_ADMIN}:
        fail('maintenance_forbidden', 'Outside-service acceptance requires a shop manager.', 403)
    from app.db.models.external_service import ExternalServiceRecord
    row = await db.scalar(select(ExternalServiceRecord).where(ExternalServiceRecord.id == source.id,
        ExternalServiceRecord.tenant_id == actor.tenant_id, ExternalServiceRecord.vehicle_id == vehicle.id,
        ExternalServiceRecord.deleted_at.is_(None), ExternalServiceRecord.voided_at.is_(None)).execution_options(populate_existing=True))
    if row is None:
        fail('maintenance_not_found', 'Service evidence was not found.', 404)
    evidence = {'kind': source.kind, 'id': str(row.id), 'vehicle_id': str(row.vehicle_id), 'version': row.version,
                'performed_on': row.service_date.isoformat(), 'odometer_miles': row.odometer}
    return row, evidence, pricing.signed_digest(evidence, 'm1_source')


async def resolved_attestation(db, actor, channel, vehicle, tenant, attestation, *, program=None, rebaseline=False, as_of=None):
    as_of = as_of or now()
    if attestation.performed_on > as_of.astimezone(ZoneInfo(tenant.timezone)).date():
        fail('maintenance_future_service', 'Service date cannot be in the future for this shop.', 422, field='performed_on')
    result = {'performed_on': attestation.performed_on.isoformat(), 'readings': {meter: None for meter in rules.METERS}}
    dependencies = []
    baseline = None if rebaseline or program is None else (program.baseline_snapshot or {}).get('attestation')
    if program and program.controlling_completion_id and not rebaseline:
        prior = await db.scalar(select(Completion).where(Completion.id == program.controlling_completion_id, Completion.tenant_id == actor.tenant_id, Completion.program_id == program.id))
        if prior and prior.performed_on and prior.performed_on <= attestation.performed_on:
            baseline = {'performed_on': prior.performed_on.isoformat(), 'readings': prior.readings}
    if baseline and baseline['performed_on'] > result['performed_on']:
        baseline = None  # older actual service may be recorded as history only
    for meter in rules.METERS:
        selected = getattr(attestation.readings, meter)
        if selected is None:
            continue
        if selected.kind == 'manual':
            original, _ = rules.number(selected.value, meter, manual=True)
            reading = rules.observation(original, meter, source='service_evidence', basis=selected.basis, observed_on=attestation.performed_on,
                                        as_of=as_of, zone=tenant.timezone)
        else:
            if selected.meter != meter:
                fail('maintenance_invalid_reading', 'The selected source belongs to another meter.', 422, field=meter)
            try:
                identity = UUID(selected.source_id)
            except (ValueError, TypeError):
                fail('maintenance_not_found', 'Service evidence was not found.', 404)
            if selected.source_kind == 'telemetry':
                candidates = await telemetry_candidates(db, vehicle, as_of, tenant.timezone)
                reading = next((row for row in candidates[meter] if row['source_id'] == str(identity)), None)
                if reading is None:
                    fail('maintenance_not_found', 'The selected observation is unavailable.', 404)
            elif selected.source_kind == 'maintenance_reading':
                row = await db.scalar(select(Reading).where(Reading.id == identity, Reading.tenant_id == actor.tenant_id, Reading.vehicle_id == vehicle.id))
                if row is None or getattr(row, meter) is None:
                    fail('maintenance_not_found', 'The selected observation is unavailable.', 404)
                reading = rules.observation(getattr(row, meter), meter, source='maintenance_manual', basis=row.source, observed_at=row.observed_at,
                    captured_at=row.created_at, source_id=row.id, as_of=as_of, zone=tenant.timezone)
            else:
                row, source, digest = await source_context(db, actor, channel, vehicle, wire.SourceRef(kind=selected.source_kind, id=identity))
                dependencies.append(digest)
                if selected.source_kind == 'repair_order':
                    # The old fleet finalizer may copy a current vehicle meter
                    # into mileage_out; arrival readings are not service meters.
                    # Existing columns cannot prove actual service provenance.
                    fail('maintenance_invalid_reading', 'Enter and confirm the actual service reading; saved order mileage is unverified.', 422, field=meter)
                else:
                    value, observed, observed_on = row.odometer, None, row.service_date
                if meter != 'odometer_miles' or value is None:
                    fail('maintenance_invalid_reading', 'That source has no actual reading for this meter.', 422, field=meter)
                reading = rules.observation(value, meter, source='service_evidence', basis='service_confirmed', observed_at=observed,
                    observed_on=observed_on, source_id=identity, as_of=as_of, zone=tenant.timezone)
            if reading['comparison_value'] is None or reading['admission'] not in {'accepted', 'stale'}:
                fail('maintenance_invalid_reading', 'This source is not verified actual service evidence. Enter an actual reading or choose another source.', 422, field=meter)
            observed_on = rules.utc(reading['observed_at']).astimezone(ZoneInfo(tenant.timezone)).date() if reading['observed_at'] else datetime.fromisoformat(reading['observed_on']).date() if reading['observed_on'] else None
            if observed_on != attestation.performed_on:
                fail('maintenance_invalid_reading', 'The observation date must match the actual service date.', 422, field=meter)
        prior_reading = (baseline or {}).get('readings', {}).get(meter)
        if prior_reading and prior_reading.get('comparison_value') is not None and Decimal(reading['comparison_value']) < Decimal(prior_reading['comparison_value']):
            fail('maintenance_invalid_reading', 'This reading is lower than the confirmed baseline. Review and rebaseline the program first.', 422, field=meter)
        result['readings'][meter] = reading
    return result, dependencies


def semantic_preview(value):
    """Derived freshness and request wall time never destabilize a review token."""
    if isinstance(value, dict):
        return {key: semantic_preview(item) for key, item in value.items() if key not in {'as_of', 'freshness', 'captured_at'}}
    if isinstance(value, list):
        return [semantic_preview(item) for item in value]
    return value


def target_digest(actor, vehicle_id, body, items, dependencies, programs, affected):
    return pricing.signed_digest({'tenant_id': str(actor.tenant_id), 'actor_id': str(actor.id), 'vehicle_id': str(vehicle_id),
        'request': body.model_dump(mode='json'), 'items': semantic_preview(items), 'sources': dependencies,
        'programs': [snapshot(program) for program in programs], 'affected': affected}, 'm1_targets')


async def config_preview(db, actor, vehicle, tenant, body, *, lock=False):
    as_of = now()
    program = await load_program(db, actor, vehicle.id, body.program.program_id, lock=lock) if body.program else None
    if program is not None:
        check_version(program, body.program.expected_version)
    if (program is None) != (body.action == 'create'):
        fail('maintenance_invalid_input', 'Choose a new or an existing maintenance program.', 422)
    if body.action in {'rebaseline', 'convert_legacy'}:
        await authorize(db, actor, body.channel, manager=True)
        if not body.reason or len(body.reason.strip()) < 3:
            fail('maintenance_invalid_input', 'Enter a reason for this baseline change.', 422, field='reason')
    if body.action == 'convert_legacy' and program.mode != 'legacy':
        fail('maintenance_invalid_input', 'Only a legacy program can be converted.', 422)
    mode = 'independent' if program is None or body.action == 'convert_legacy' else program.mode
    values = body.config.intervals.model_dump(mode='json')
    if mode == 'independent' and not any(value is not None for value in values.values()):
        fail('maintenance_invalid_input', 'Enable at least one maintenance interval.', 422, field='intervals')
    if mode == 'legacy' and body.config.service_id is not None:
        fail('maintenance_invalid_input', 'Convert the complete legacy package explicitly before selecting an independent service.', 422)
    if body.config.service_id is not None and (program is None or program.service_id != body.config.service_id):
        await service_ref(db, actor.tenant_id, body.config.service_id, required=True)
    if program and program.archived_at:
        fail('maintenance_invalid_input', 'Restore this program before changing it.', 409)
    if program and await db.scalar(select(WorkLink.id).where(WorkLink.tenant_id == actor.tenant_id, WorkLink.program_id == program.id, WorkLink.state.in_(OCCUPYING)).limit(1)):
        fail('maintenance_operation_linked', 'Finish or detach the current maintenance work before changing its configuration.')
    resolved = None
    dependencies = []
    if body.seed.kind == 'explicit':
        proposed = body.seed.targets.model_dump(mode='json')
        missing = []
        for interval, target in [('days', 'due_on'), ('miles', 'odometer_miles'), ('engine_hours', 'engine_hours')]:
            if values[interval] is None and proposed[target] is not None:
                fail('maintenance_invalid_input', 'Disabled intervals cannot have a due target.', 422, field=target)
            if values[interval] is not None and proposed[target] is None:
                if body.action == 'create':
                    fail('maintenance_invalid_input', 'Provide a target for every enabled interval or use an actual service baseline.', 422, field=target)
                missing.append('date' if target == 'due_on' else target)
    else:
        resolved, dependencies = await resolved_attestation(db, actor, body.channel, vehicle, tenant, body.seed.attestation,
            program=program, rebaseline=body.action in {'rebaseline', 'convert_legacy'}, as_of=as_of)
        proposed, missing = rules.next_targets(values, resolved['performed_on'], resolved['readings'], legacy=mode == 'legacy')
    item = {'program_id': str(program.id) if program else None, 'current_version': program.version if program else None,
            'outcome': 'targets_updated', 'previous_targets': targets(program) if program else dict(rules.EMPTY_TARGETS), 'proposed_targets': proposed,
            'resolved_attestation': {**resolved, 'readings': safe_readings(resolved['readings'], body.channel, actor.role)} if resolved else None, 'missing': missing, 'warnings': []}
    return {'schema_version': 1, 'as_of': rules.iso(as_of), 'timezone': tenant.timezone, 'purpose': 'configuration',
            'expected_target_fingerprint': target_digest(actor, vehicle.id, body, [item], dependencies, [program] if program else [], []),
            'items': [item], 'affected_work': [], 'warnings': []}


async def target_preview(db, actor, vehicle_id, body):
    tenant = await authorize(db, actor, body.channel, manager=body.purpose != 'configuration')
    vehicle = await load_vehicle(db, actor, body.channel, vehicle_id)
    if body.purpose == 'configuration':
        return await config_preview(db, actor, vehicle, tenant, body)
    if body.purpose == 'completion':
        return await completion_preview(db, actor, vehicle, tenant, body)
    return await evidence_preview(db, actor, vehicle, tenant, body)


def set_targets(program, proposed):
    program.target_due_on = datetime.fromisoformat(proposed['due_on']).date() if proposed['due_on'] else None
    program.target_miles = proposed['odometer_miles']
    program.target_hours = Decimal(proposed['engine_hours']) if proposed['engine_hours'] is not None else None


def config_changed(program, config):
    old = intervals(program)
    new = config.intervals.model_dump(mode='json')
    # Decimal spelling is not an interval change.
    old['engine_hours'] = Decimal(old['engine_hours']) if old['engine_hours'] is not None else None
    new['engine_hours'] = Decimal(new['engine_hours']) if new['engine_hours'] is not None else None
    return old != new or program.service_id != config.service_id


async def program_command(db, actor, vehicle_id, body, key, *, program_id=None, action='save'):
    route = f'/vehicles/{vehicle_id}/maintenance-programs/{program_id or "new"}/{action}'
    manager = getattr(getattr(body, 'targets', None), 'kind', None) in {'rebaseline', 'convert_legacy'}
    tenant, vehicle, receipt, repeated = await start_command(db, actor, body.channel, vehicle_id, 'm1_program', key, body, route, manager=manager)
    if repeated:
        program = await load_program(db, actor, vehicle_id, UUID(repeated['program_id']))
        return {'schema_version': 1, 'program': await program_view(db, actor, body.channel, program, vehicle, tenant, now()), 'replayed': True}
    program = await load_program(db, actor, vehicle_id, program_id, lock=True) if program_id else None
    if program:
        check_version(program, body.expected_version)
    if action in {'archive', 'restore'}:
        if action == 'archive' and (program.review_codes or await db.scalar(select(WorkLink.id).where(WorkLink.tenant_id == actor.tenant_id, WorkLink.program_id == program.id, WorkLink.state.in_(OCCUPYING)).limit(1))):
            fail('maintenance_operation_linked', 'Resolve maintenance work and review before archiving the program.')
        before = snapshot(program)
        touch(program, actor)
        program.archived_at = now() if action == 'archive' else None
        append_event(db, actor, program, action, before)
    else:
        if program and program.archived_at:
            fail('maintenance_invalid_input', 'Restore this program before changing it.', 409)
        if program is None and body.targets.kind != 'replace':
            fail('maintenance_invalid_input', 'Review the initial due targets before creating a program.', 422)
        if program and body.targets.kind == 'preserve':
            if program.mode == 'independent' and not any(value is not None for value in body.config.intervals.model_dump().values()):
                fail('maintenance_invalid_input', 'Enable at least one maintenance interval.', 422)
            if program.mode == 'legacy' and body.config.service_id is not None:
                fail('maintenance_invalid_input', 'Convert the legacy package explicitly before choosing a service.', 422)
            changed = config_changed(program, body.config)
            old_values, new_values = intervals(program), body.config.intervals.model_dump()
            if any((old_values[key] is None) != (new_values[key] is None) for key in old_values):
                fail('maintenance_preview_changed', 'Review targets when enabling or disabling an interval.')
            if changed and await db.scalar(select(WorkLink.id).where(WorkLink.tenant_id == actor.tenant_id, WorkLink.program_id == program.id, WorkLink.state.in_(OCCUPYING)).limit(1)):
                fail('maintenance_operation_linked', 'Finish or detach the current work before changing its configuration.')
            preview = None
        else:
            preview_body = wire.ConfigPreview.model_validate({'purpose': 'configuration', 'channel': body.channel,
                'program': {'program_id': str(program.id), 'expected_version': body.expected_version} if program else None,
                'config': body.config.model_dump(mode='json'), 'action': body.targets.kind if program else 'create',
                'seed': body.targets.seed.model_dump(mode='json'), 'reason': body.targets.reason})
            preview = await config_preview(db, actor, vehicle, tenant, preview_body, lock=True)
            if not hmac.compare_digest(preview['expected_target_fingerprint'], body.targets.expected_target_fingerprint):
                fail('maintenance_preview_changed', 'The maintenance targets changed. Review the current calculation.', preview=preview)
        before = snapshot(program) if program else {}
        if program is None:
            program = Program(id=uuid4(), tenant_id=actor.tenant_id, vehicle_id=vehicle_id, mode='independent', version=1,
                current_cycle=1, baseline_generation=1, created_by=actor.id, updated_by=actor.id, created_at=now(), updated_at=now(), review_codes=[])
            db.add(program)
        else:
            touch(program, actor)
        if body.targets.kind == 'convert_legacy':
            program.mode = 'independent'
            program.legacy_package = None
        program.name = body.config.name
        program.interval_days = body.config.intervals.days
        program.interval_miles = body.config.intervals.miles
        program.interval_hours = Decimal(body.config.intervals.engine_hours) if body.config.intervals.engine_hours is not None else None
        if body.config.service_id != program.service_id or not before:
            program.service_snapshot = await service_ref(db, actor.tenant_id, body.config.service_id, required=True)
        program.service_id = body.config.service_id
        if preview:
            item = preview['items'][0]
            set_targets(program, item['proposed_targets'])
            kind = 'baseline' if item['resolved_attestation'] else 'explicit'
            program.target_provenance = {'kind': kind, 'confirmed_at': rules.iso(program.updated_at), 'evidence_id': None}
            previous_reset = (program.baseline_snapshot or {}).get('comparison_reset_at')
            stored_attestation = None
            if body.targets.seed.kind == 'baseline':
                stored_attestation, _ = await resolved_attestation(db, actor, body.channel, vehicle, tenant, body.targets.seed.attestation,
                    program=program if before else None, rebaseline=body.targets.kind in {'rebaseline', 'convert_legacy'})
            program.baseline_snapshot = {'targets': item['proposed_targets'], 'attestation': stored_attestation,
                'generation': program.baseline_generation, 'comparison_reset_at': previous_reset,
                'confirmed_at': rules.iso(program.updated_at) if stored_attestation else None}
            program.controlling_completion_id = None
            if body.targets.kind in {'rebaseline', 'convert_legacy'}:
                program.baseline_generation += 1
                program.baseline_snapshot['generation'] = program.baseline_generation
                program.baseline_snapshot['comparison_reset_at'] = rules.iso(program.updated_at)
                program.review_codes = []
                program.controlling_completion_id = None
        append_event(db, actor, program, 'create' if not before else body.targets.kind if preview else 'update', before,
                     reason=getattr(body.targets, 'reason', None))
    await finish_command(db, receipt, {'program_id': str(program.id)}, status_code=201 if program_id is None else 200)
    return {'schema_version': 1, 'program': await program_view(db, actor, body.channel, program, vehicle, tenant, now()), 'replayed': False}


async def completion_view(db, actor, channel, row):
    can_open = False
    source_id = None
    label = 'Manual service evidence'
    if row.source_kind == 'repair_order' and row.source_id:
        order = await db.scalar(select(RepairOrder).where(RepairOrder.id == row.source_id, RepairOrder.tenant_id == actor.tenant_id, RepairOrder.deleted_at.is_(None)))
        if order:
            can_open = True
            if channel == 'fleet':
                from app.api.v1.endpoints.fleet import _load_fleet_ro_or_404
                try:
                    await _load_fleet_ro_or_404(db, actor.tenant_id, order.id)
                except HTTPException:
                    can_open = False
            if can_open:
                source_id, label = str(order.id), order.order_number
    elif row.source_kind == 'external_service':
        label = 'Outside service'
        if actor.role in {UserRole.GARAGE_OWNER, UserRole.GARAGE_ADMIN}:
            from app.db.models.external_service import ExternalServiceRecord
            source = await db.scalar(select(ExternalServiceRecord).where(ExternalServiceRecord.id == row.source_id,
                ExternalServiceRecord.tenant_id == actor.tenant_id, ExternalServiceRecord.deleted_at.is_(None)))
            if source:
                can_open, source_id = True, str(source.id)
    return {'id': str(row.id), 'program_id': str(row.program_id), 'cycle': row.cycle, 'work_link_id': str(row.work_link_id) if row.work_link_id else None,
        'action': row.action, 'result': row.result, 'performed_on': row.performed_on.isoformat() if row.performed_on else None,
        'readings': safe_readings(row.readings, channel, actor.role), 'source': {'kind': row.source_kind, 'id': source_id, 'can_open': can_open, 'label': label},
        'previous_targets': row.previous_targets, 'next_targets': row.next_targets,
        'supersedes_id': str(row.supersedes_id) if row.supersedes_id else None, 'recorded_at': rules.iso(row.created_at)}


async def program_history(db, actor, channel, vehicle_id, program_id, *, skip=0, limit=25):
    await authorize(db, actor, channel)
    await load_vehicle(db, actor, channel, vehicle_id)
    await load_program(db, actor, vehicle_id, program_id)
    query = select(Event).where(Event.tenant_id == actor.tenant_id, Event.program_id == program_id)
    total = await db.scalar(select(func.count()).select_from(query.subquery()))
    events = list((await db.scalars(query.order_by(Event.version.desc()).offset(skip).limit(limit))).all())
    items = []
    for event in events:
        completion = None
        completion_id = event.after_values.get('completion_id')
        if completion_id:
            row = await db.scalar(select(Completion).where(Completion.id == UUID(completion_id), Completion.tenant_id == actor.tenant_id, Completion.program_id == program_id))
            if row:
                completion = await completion_view(db, actor, channel, row)
        items.append({'id': str(event.id), 'version': event.version, 'action': event.action, 'occurred_at': rules.iso(event.created_at),
            'reason': event.reason if actor.role in MANAGERS else None, 'summary': event.action.replace('_', ' ').capitalize(), 'completion': completion})
    return {'schema_version': 1, 'items': items, 'total': total, 'has_more': skip + len(items) < total}


async def guard_vehicle_merge(db, canonical, duplicate):
    """Called under existing sorted vehicle locks; never acquire tenant here."""
    losing_program = await db.scalar(select(Program.id).where(Program.tenant_id == duplicate.tenant_id, Program.vehicle_id == duplicate.id).limit(1))
    losing_reading = await db.scalar(select(Reading.id).where(Reading.tenant_id == duplicate.tenant_id, Reading.vehicle_id == duplicate.id).limit(1))
    if losing_program or losing_reading:
        fail('maintenance_vehicle_merge_requires_review', 'This truck has maintenance identity or history. Keep its identity until the maintenance records are reviewed.')
    winning = await db.scalar(select(Program.id).where(Program.tenant_id == canonical.tenant_id, Program.vehicle_id == canonical.id).limit(1))
    if not winning:
        return
    from app.db.models.fleet import VehiclePMService
    incoming_package = await db.scalar(select(VehiclePMService.id).where(VehiclePMService.tenant_id == duplicate.tenant_id,
        VehiclePMService.vehicle_id == duplicate.id, VehiclePMService.deleted_at.is_(None)).limit(1))
    incoming_work = await db.scalar(select(RepairOrder.id).where(RepairOrder.tenant_id == duplicate.tenant_id,
        RepairOrder.vehicle_id == duplicate.id, RepairOrder.deleted_at.is_(None), RepairOrder.is_pm.is_(True)).limit(1))
    if duplicate.next_pm_miles is not None or duplicate.pm_due_date is not None or incoming_package or incoming_work:
        fail('maintenance_vehicle_merge_requires_review', 'The other truck has a separate legacy maintenance schedule. Review it before merging identities.')


async def guard_legacy_configuration(db, actor, vehicle, *, changes=True):
    """Legacy scalar controls cannot redefine an independent/occupied program."""
    if not changes:
        return None
    programs = list((await db.scalars(select(Program).where(Program.tenant_id == actor.tenant_id, Program.vehicle_id == vehicle.id)
        .order_by(Program.id).with_for_update())).all())
    if any(row.mode == 'independent' for row in programs):
        fail('maintenance_review_required', 'Use this truck’s maintenance programs to edit its service schedule.')
    legacy = next((row for row in programs if row.mode == 'legacy'), None)
    if legacy:
        claim = await db.scalar(select(WorkLink.id).where(WorkLink.tenant_id == actor.tenant_id, WorkLink.program_id == legacy.id,
            WorkLink.state.in_(OCCUPYING)).limit(1))
        if claim or legacy.review_codes:
            fail('maintenance_operation_linked' if claim else 'maintenance_review_required', 'Review the existing maintenance program before changing its legacy schedule.')
    return legacy


async def sync_legacy_configuration(db, actor, vehicle, legacy=None, *, force=False):
    """Mirror only explicitly saved legacy scalar/package intent, never telemetry."""
    from uuid import uuid5
    from app.db.models.fleet import VehiclePMService
    await db.flush()
    ids = list((await db.scalars(select(VehiclePMService.service_id).where(VehiclePMService.tenant_id == actor.tenant_id,
        VehiclePMService.vehicle_id == vehicle.id, VehiclePMService.deleted_at.is_(None)).order_by(VehiclePMService.sort_order, VehiclePMService.id))).all())
    if not force and legacy is None and not ids and vehicle.next_pm_miles is None and vehicle.pm_due_date is None:
        return None
    package = [await service_ref(db, actor.tenant_id, sid) for sid in ids]
    days, miles = vehicle.pm_interval_days, vehicle.pm_interval_miles
    valid_days = days if days is not None and 1 <= days <= 36500 else None
    valid_miles = miles if miles is not None and 1 <= miles <= 99999999 else None
    valid_target = vehicle.next_pm_miles if vehicle.next_pm_miles is not None and 0 <= vehicle.next_pm_miles <= 99999999 else None
    value = {'pm_interval_days': days, 'pm_interval_miles': miles, 'next_pm_miles': vehicle.next_pm_miles,
        'pm_due_date': vehicle.pm_due_date.isoformat() if vehicle.pm_due_date else None,
        'date_rule': '600_miles_per_day_saturday', 'package': package}
    if legacy and all((legacy.legacy_snapshot or {}).get(key) == item for key, item in value.items()):
        return legacy
    before = snapshot(legacy) if legacy else {}
    if legacy is None:
        legacy = Program(id=uuid5(UUID('6e2386ac-9ba3-49f2-875f-3c410bfb8783'), f'legacy:{actor.tenant_id}:{vehicle.id}'),
            tenant_id=actor.tenant_id, vehicle_id=vehicle.id, name='Preventive maintenance', mode='legacy', version=1,
            current_cycle=1, baseline_generation=1, created_by=actor.id, updated_by=actor.id, created_at=now(), updated_at=now(), review_codes=[])
        db.add(legacy)
    else:
        touch(legacy, actor)
    legacy.interval_days, legacy.interval_miles, legacy.interval_hours = valid_days, valid_miles, None
    legacy.target_due_on, legacy.target_miles, legacy.target_hours = vehicle.pm_due_date, valid_target, None
    legacy.legacy_package, legacy.legacy_snapshot = package, value
    legacy.target_provenance = {'kind': 'legacy', 'evidence_id': None, 'confirmed_at': rules.iso(now())}
    if (days is not None and valid_days is None) or (miles is not None and valid_miles is None) or (vehicle.next_pm_miles is not None and valid_target is None):
        legacy.review_codes = list(set(legacy.review_codes or []) | {'legacy_invalid_interval'})
    append_event(db, actor, legacy, 'legacy_configuration', before)
    await db.flush()
    return legacy


async def prepare_legacy_recognition(db, actor, vehicle, order, body):
    """The old explicit reclassification command is confined to one legacy adapter."""
    tenant = await authorize(db, actor, 'fleet', manager=True)
    try:
        legacy = await guard_legacy_configuration(db, actor, vehicle)
    except HTTPException as error:
        if error.status_code == 409:
            fail('maintenance_review_required', 'Review this truck’s maintenance programs before recognizing legacy PM.')
        raise
    if legacy is None:
        legacy = await sync_legacy_configuration(db, actor, vehicle, force=True)
    if legacy.review_codes:
        fail('maintenance_review_required', 'Review the legacy maintenance baseline before recognizing this service.')
    if await db.scalar(select(Completion.id).where(Completion.tenant_id == actor.tenant_id, Completion.program_id == legacy.id,
        Completion.source_kind == 'repair_order', Completion.source_id == order.id).limit(1)):
        fail('maintenance_review_required', 'This source already has maintenance evidence. Review its existing evidence chain.')
    attestation = wire.Attestation.model_validate({'performed_on': body.performed_on.isoformat(), 'confirm_actual_service_readings': True,
        'readings': {'odometer_miles': {'kind': 'manual', 'value': str(body.odometer), 'basis': 'staff_reported', 'note': None}, 'engine_hours': None}})
    resolved, _ = await resolved_attestation(db, actor, 'fleet', vehicle, tenant, attestation, program=legacy)
    if legacy.controlling_completion_id:
        previous = await db.scalar(select(Completion).where(Completion.id == legacy.controlling_completion_id, Completion.tenant_id == actor.tenant_id))
        if previous and previous.performed_on == body.performed_on and previous.source_id != order.id:
            fail('maintenance_review_required', 'Another service controls this date. Review that evidence explicitly.')
    return legacy, resolved


async def record_legacy_recognition(db, actor, vehicle, order, body, program, attestation, *, advance):
    """No commit. The old route owns its explicitly requested source edits."""
    await db.flush()
    _, source, digest = await source_context(db, actor, 'fleet', vehicle, wire.SourceRef(kind='repair_order', id=order.id))
    before = snapshot(program)
    if program.controlling_completion_id:
        controlling = await db.scalar(select(Completion).where(Completion.id == program.controlling_completion_id, Completion.tenant_id == actor.tenant_id))
        if controlling and controlling.performed_on and controlling.performed_on > body.performed_on:
            advance = False
    proposed, missing = rules.next_targets(intervals(program), attestation['performed_on'], attestation['readings'], legacy=True)
    if missing:
        fail('maintenance_review_required', 'This legacy program needs its actual service readings before recognition.')
    row = Completion(id=uuid4(), tenant_id=actor.tenant_id, program_id=program.id, cycle=program.current_cycle,
        action='recognize', result='advanced' if advance else 'history_only', performed_on=body.performed_on, readings=attestation['readings'],
        source_kind='repair_order', source_id=order.id, source_fingerprint=digest, source_snapshot=source, configuration=configuration(program),
        previous_targets=targets(program), next_targets=proposed if advance else targets(program),
        recognition_key='repair_order:' + str(order.id), actor_id=actor.id, request_id=uuid4(),
        request_fingerprint=pricing.signed_digest({'source': str(order.id), 'attestation': attestation}, 'm1_legacy_recognition'))
    db.add(row)
    await db.flush()
    touch(program, actor)
    if advance:
        set_targets(program, proposed)
        program.current_cycle += 1
        program.controlling_completion_id = row.id
        program.target_provenance = {'kind': 'completion', 'evidence_id': str(row.id), 'confirmed_at': rules.iso(now())}
        vehicle.next_pm_miles = program.target_miles
        vehicle.pm_due_date = program.target_due_on
    append_event(db, actor, program, 'recognize', before, extra={'completion_id': str(row.id)})
    await db.flush()
    return row


async def work_scope(db, actor, vehicle_id, body, *, lock=False):
    """C1 customer precedes order/vehicle locks; preview has no writes."""
    from types import SimpleNamespace
    from app.services import customer_pricing as account
    from app.services.internal_fleet import uses_internal_fleet_pricing
    from app.services.price_build_service import PriceBuildService
    tenant = await authorize(db, actor, body.channel)
    if lock:
        await pricing.lock_tenant_financials(db, actor.tenant_id)
    vehicle = await load_vehicle(db, actor, body.channel, vehicle_id)
    if body.target.kind == 'existing':
        order = await source_order(db, actor, body.channel, vehicle_id, body.target.repair_order_id, finalized=False)
        await account.live_customer(db, actor.tenant_id, order.customer_id, lock=lock)
        order = await PriceBuildService().load_order(db, order.id, tenant_id=actor.tenant_id, for_update=lock)
        from app.services.operation_execution import editable
        if order.status != RepairOrderStatus.DRAFT or not editable(order) or order.hold_reason:
            fail('maintenance_operation_linked', 'Choose an editable draft order for maintenance work.')
    else:
        payer = await account.live_customer(db, actor.tenant_id, body.target.bill_to_customer_id, lock=lock)
        if payer is None:
            fail('maintenance_not_found', 'The work customer was not found.', 404)
        captured = await account.candidate(db, tenant, payer, lock=lock)
        internal = uses_internal_fleet_pricing(payer, tenant)
        order = SimpleNamespace(id=None, tenant_id=actor.tenant_id, customer_id=payer.id, vehicle_id=vehicle.id,
            pricing_policy_snapshot=captured, pricing_matrix_revision_id=account.revision_id(captured), is_internal=internal,
            bill_labor_at_customer_rate=bool(vehicle.bill_labor_at_customer_rate) if internal else False,
            parts_usage=[], labor_items=[], labor_discount_amount=Decimal(0), order_discount_amount=Decimal(0),
            status=RepairOrderStatus.DRAFT, pricing_locked_at=None, pricing_lock_reason=None, deleted_at=None, hold_reason=None,
            is_fleet_work=body.channel == 'fleet', is_pm=body.channel == 'fleet', tenant=tenant)
    vehicle = await load_vehicle(db, actor, body.channel, vehicle_id, lock=lock)
    return tenant, vehicle, order


async def work_plan(db, actor, vehicle_id, body, *, lock=False):
    from app.services.parts_pricing_planner import build_maintenance_plan
    from app.db.models.service_checklist import RepairOrderChecklistItem as Task
    from app.services import customer_pricing as account
    tenant, vehicle, order = await work_scope(db, actor, vehicle_id, body, lock=lock)
    programs = []
    required = set()
    for reference in sorted(body.programs, key=lambda item: str(item.program_id)):
        program = await load_program(db, actor, vehicle_id, reference.program_id, lock=lock)
        check_version(program, reference.expected_version)
        if order.id and await db.scalar(select(Completion.id).where(Completion.tenant_id == actor.tenant_id, Completion.program_id == program.id, Completion.source_kind == 'repair_order', Completion.source_id == order.id).limit(1)):
            fail('maintenance_review_required', 'This order already has evidence for this program. Review the existing evidence chain.')
        if program.archived_at:
            fail('maintenance_review_required', 'Restore this maintenance program before creating work.')
        view = await program_view(db, actor, body.channel, program, vehicle, tenant, now())
        if view['review']['required']:
            fail('maintenance_review_required', 'Review the maintenance baseline before creating work.')
        claims = list((await db.scalars(select(WorkLink).where(WorkLink.tenant_id == actor.tenant_id,
            WorkLink.program_id == program.id, WorkLink.state.in_(OCCUPYING)).order_by(WorkLink.id))).all())
        if claims:
            fail('maintenance_cycle_claimed', 'This program already has work in progress.',
                 existing_work=[await safe_work(db, actor, body.channel, link) for link in claims])
        ids = [UUID(item['id']) for item in program.legacy_package or []] if program.mode == 'legacy' else [program.service_id] if program.service_id else []
        if len(set(ids)) > 30:
            fail('maintenance_scope_too_large', 'This saved package is too large for one maintenance action.')
        if not ids:
            fail('maintenance_template_unavailable', 'Choose a service for this maintenance program before creating work.')
        required.update((program.id, identity) for identity in ids)
        programs.append(program)
    actual = {(identity, group.service_id) for group in body.coverage for identity in group.program_ids}
    if actual != required or sum(len(group.program_ids) for group in body.coverage) != len(required):
        fail('maintenance_invalid_coverage', 'Each program must cover its exact configured service package once.', 422)
    coverage, operation_binding, operations = [], [], {}
    for group in body.coverage:
        if group.operation.kind == 'existing':
            labor = next((line for line in order.labor_items if line.id == group.operation.labor_id and line.deleted_at is None), None)
            if labor is None or labor.source_service_id != group.service_id:
                fail('maintenance_not_found', 'The selected service operation was not found.', 404)
            if labor.execution_status == 'completed' or labor.completed_at:
                fail('maintenance_operation_linked', 'Completed work requires historical maintenance evidence.')
            if labor.execution_version != group.operation.expected_operation_version:
                fail('maintenance_version_conflict', 'This service operation changed. Refresh it before adding coverage.')
            tasks = list((await db.scalars(select(Task).where(Task.tenant_id == actor.tenant_id, Task.labor_id == labor.id, Task.removed_at.is_(None)))).all())
            reference = await service_ref(db, actor.tenant_id, group.service_id, saved={'name': labor.description})
            coverage.append({'key': group.key, 'program_ids': [str(i) for i in group.program_ids], 'service_id': str(group.service_id),
                'service_name': reference['name'], 'operation_kind': 'existing', 'labor_id': str(labor.id), 'hours': rules.decimal_text(labor.hours),
                'checklist_items': len(tasks), 'preserves_saved_operation': True})
            operations[group.key] = labor
            operation_binding.append({'id': str(labor.id), 'version': labor.execution_version, 'state': labor.execution_status,
                'hours': str(labor.hours), 'rate': str(labor.hourly_rate), 'total': str(labor.total_cost),
                'checklist': sorted((str(task.id), task.version, task.is_completed) for task in tasks)})
        else:
            await service_ref(db, actor.tenant_id, group.service_id, required=True)
    new_ids = [group.service_id for group in body.coverage if group.operation.kind == 'new']
    reserves = not (body.target.kind == 'new' and body.channel == 'fleet' or body.target.kind == 'existing' and order.is_pm and (order.is_fleet_work or order.is_internal))
    try:
        plan = await build_maintenance_plan(db, actor, tenant, order, new_ids, reserves=reserves, channel=body.channel, lock=lock)
    except ValueError:
        fail('maintenance_invalid_input', 'A service has invalid hours or part quantities. Correct its template before creating work.', 422)
    except HTTPException as error:
        if isinstance(error.detail, dict) and error.detail.get('code') == 'plan_too_large':
            fail('maintenance_scope_too_large', 'Use no more than 100 resulting part lines in one maintenance action.')
        raise
    for group in body.coverage:
        if group.operation.kind == 'existing':
            continue
        template = next(item for item in plan.services if item.id == group.service_id)
        coverage.append({'key': group.key, 'program_ids': [str(i) for i in group.program_ids], 'service_id': str(group.service_id),
            'service_name': template.name, 'operation_kind': 'new', 'labor_id': None,
            'hours': rules.decimal_text(Decimal(template.duration_minutes or 0) / 60),
            'checklist_items': len(template.checklist_template or []), 'preserves_saved_operation': False})
        operation_binding.append({'service': str(template.id), 'checklist_version': template.checklist_version,
            'checklist': template.checklist_template, 'duration': template.duration_minutes, 'base_price': str(template.base_price)})
    by_key = {row['key']: row for row in coverage}
    coverage = [by_key[group.key] for group in body.coverage]
    payload = body.model_dump(mode='json', exclude={'expected_work_fingerprint'})
    fingerprint = pricing.signed_digest({'request': payload, 'tenant': str(actor.tenant_id), 'actor': str(actor.id), 'vehicle': str(vehicle_id),
        'programs': [snapshot(p) for p in programs], 'pricing': plan.response['pricing_preview_fingerprint'], 'operations': operation_binding,
        'reservation_adapter': reserves, 'account': account.stable_policy(plan.account_snapshot) if new_ids or order.id is None else None}, 'm1_work')
    response = {'schema_version': 1, 'as_of': rules.iso(now()), 'vehicle_id': str(vehicle_id), 'expected_work_fingerprint': fingerprint,
        'confirmation_required': True, 'target': payload['target'], 'coverage': coverage, 'availability': plan.response['availability'],
        'warnings': plan.response['warnings'], 'existing_work': [], 'projection': body.channel, 'currency': 'USD',
        'lines': [{k: v for k, v in line.items() if k != 'sale_line_id'} for line in plan.response['lines']], 'totals': plan.response['totals']}
    if body.channel == 'fleet':
        response['agreement_applies'] = bool(plan.account_snapshot and (plan.account_snapshot['labor']['source'] == 'customer' or plan.account_snapshot['parts']['source'] == 'customer'))
    else:
        saved = plan.account_snapshot
        rate, labor_source = account.labor_default(order, tenant, legacy_fleet=not reserves)
        response['account_policy'] = {'snapshot_id': saved['snapshot_id'] if saved and order.id else None,
            'labor': {'source': labor_source if saved or order.id is None or order.is_internal else 'legacy', 'rate': pricing.cents(rate)},
            'parts': {'source': 'internal' if order.is_internal else saved['parts']['source'] if saved else 'legacy',
                'mode': 'internal' if order.is_internal else saved['parts']['mode'] if saved else 'legacy'}}
    return response, (tenant, vehicle, order, programs, operations, plan, reserves)


async def work_preview(db, actor, vehicle_id, body):
    return (await work_plan(db, actor, vehicle_id, body))[0]


async def command_receipt(db, actor, family, key, body, route):
    try:
        key = str(UUID(validate_idempotency_key(key)))
    except (ValueError, TypeError):
        fail('maintenance_invalid_input', 'Use a UUID Idempotency-Key.', 422)
    payload = body.model_dump(mode='json', exclude={'expected_work_fingerprint', 'expected_target_fingerprint'})
    digest = canonical_fingerprint(route=route, principal_id=actor.id, payload={'tenant_id': str(actor.tenant_id), 'body': payload})
    try:
        record = await find_idempotent_response(db, tenant_id=actor.tenant_id, family=family, key=key, fingerprint=digest)
    except HTTPException:
        fail('idempotency_conflict', 'This action key already belongs to another request.')
    if record is not None:
        return record, json.loads(record.response_body)
    record = begin_idempotency(tenant_id=actor.tenant_id, family=family, key=key, fingerprint=digest)
    db.add(record)
    return record, None


async def attach_program_links(db, actor, order, programs, coverage, operations, *, captured_configs=None):
    """One program claim, any explicitly shared operation mappings; no money edits."""
    links = []
    for program in programs:
        before = snapshot(program)
        link = WorkLink(id=uuid4(), tenant_id=actor.tenant_id, program_id=program.id, cycle=program.current_cycle,
            repair_order_id=order.id, program_version=program.version, captured_config=(captured_configs or {}).get(program.id, configuration(program)), captured_targets=targets(program),
            state='active', version=1, created_at=now(), updated_at=now())
        db.add(link)
        await db.flush()
        versions = {}
        for group in coverage:
            if program.id not in group.program_ids:
                continue
            labor = operations[group.key]
            mapping = OperationLink(id=uuid4(), tenant_id=actor.tenant_id, work_link_id=link.id, operation_id=labor.id,
                identity_snapshot={'operation_id': str(labor.id), 'service_id': str(labor.source_service_id), 'service_name': labor.description,
                    'execution_version': labor.execution_version}, version=1, state='active', created_at=now(), updated_at=now())
            db.add(mapping)
            versions[str(mapping.id)] = 1
        touch(program, actor)
        append_event(db, actor, program, 'work_attached', before, link=link, extra={'operation_versions': versions})
        links.append(link)
    await db.flush()
    return links


async def work_result(db, actor, channel, vehicle, tenant, order_id, link_ids, *, created, replayed):
    await source_order(db, actor, channel, vehicle.id, order_id, finalized=False)
    links, programs = [], []
    for identity in link_ids:
        link = await db.scalar(select(WorkLink).where(WorkLink.id == UUID(str(identity)), WorkLink.tenant_id == actor.tenant_id,
            WorkLink.repair_order_id == order_id))
        if link is None:
            fail('maintenance_not_found', 'Saved maintenance work was not found.', 404)
        program = await load_program(db, actor, vehicle.id, link.program_id)
        links.append(await safe_work(db, actor, channel, link))
        programs.append(await program_view(db, actor, channel, program, vehicle, tenant, now()))
    return {'schema_version': 1, 'repair_order_id': str(order_id), 'created': created, 'links': links, 'programs': programs, 'replayed': replayed}


async def work_command(db, actor, vehicle_id, body, key):
    from app.services import customer_pricing as account, operation_execution
    from app.services.parts_pricing_planner import apply_plan_parts
    from app.services.service_checklist import snapshot_service
    from app.db.models.labor import LaborLineType
    from app.core.unique_id import create_with_retry
    from app.api.v1.endpoints.repair_orders import generate_order_number, _refresh_repair_order_totals
    tenant = await authorize(db, actor, body.channel)
    vehicle = await load_vehicle(db, actor, body.channel, vehicle_id)
    if body.target.kind == 'existing':
        await source_order(db, actor, body.channel, vehicle_id, body.target.repair_order_id, finalized=False)
    await pricing.lock_tenant_financials(db, actor.tenant_id)
    receipt, repeated = await command_receipt(db, actor, 'm1_work', key, body, f'/vehicles/{vehicle_id}/maintenance-work')
    if repeated:
        return await work_result(db, actor, body.channel, vehicle, tenant, UUID(repeated['order_id']), repeated['links'], created=repeated['created'], replayed=True)
    preview, context = await work_plan(db, actor, vehicle_id, body, lock=True)
    if not hmac.compare_digest(body.expected_work_fingerprint, preview['expected_work_fingerprint']):
        fail('maintenance_preview_changed', 'Maintenance work changed. Review the current work before applying.', preview=preview)
    tenant, vehicle, order, programs, operations, plan, reserves = context
    created = order.id is None
    if created:
        from app.services.vehicle_identity import ensure_vehicle_relationship
        await ensure_vehicle_relationship(db, tenant_id=actor.tenant_id, vehicle_id=vehicle.id,
            customer_id=order.customer_id, relationship_type='default_payer')
        candidate = order
        async def create_order(number):
            row = RepairOrder(id=uuid4(), tenant_id=actor.tenant_id, customer_id=candidate.customer_id, vehicle_id=vehicle.id,
                order_number=number, status=RepairOrderStatus.DRAFT, description=body.target.description or 'Maintenance service',
                is_internal=candidate.is_internal, is_fleet_work=candidate.is_fleet_work, is_pm=candidate.is_pm,
                bill_labor_at_customer_rate=candidate.bill_labor_at_customer_rate, pricing_policy_snapshot=candidate.pricing_policy_snapshot,
                pricing_matrix_revision_id=candidate.pricing_matrix_revision_id, labor_discount_amount=0, order_discount_amount=0,
                mileage_in=vehicle.mileage)
            db.add(row)
            return row
        order = await create_with_retry(db, create_order, lambda: generate_order_number(db, actor.tenant_id), entity_name='repair_order', commit=False)
    if plan.services:
        operation_execution.enroll_new_scope(order)
    for group in body.coverage:
        if group.operation.kind == 'existing':
            continue
        template = next(item for item in plan.services if item.id == group.service_id)
        hours = Decimal(template.duration_minutes or 0) / 60
        rate, origin, price_source = account.new_labor(order, tenant, actor, legacy_fleet=not reserves)
        labor = Labor(id=uuid4(), tenant_id=actor.tenant_id, repair_order_id=order.id, description=template.name,
            hours=hours, hourly_rate=rate, total_cost=(hours * rate).quantize(Decimal('.01')), line_type=LaborLineType.FLAT_SERVICE,
            source_service_id=template.id, auto_recalc_enabled=True, execution_status='pending', execution_version=1,
            pricing_snapshot=origin, pricing_source=price_source)
        db.add(labor)
        await db.flush()
        account.audit_labor(db, actor, order, labor)
        await snapshot_service(db, order, labor, template, actor)
        operations[group.key] = labor
    if order.is_pm:
        from app.db.models.fleet import RepairOrderPMService
        memberships = list((await db.scalars(select(RepairOrderPMService).where(
            RepairOrderPMService.tenant_id == actor.tenant_id, RepairOrderPMService.repair_order_id == order.id,
            RepairOrderPMService.deleted_at.is_(None)).order_by(RepairOrderPMService.sort_order, RepairOrderPMService.id))).all())
        present = {row.service_id for row in memberships}
        position = max((row.sort_order for row in memberships), default=-1) + 1
        for group in body.coverage:
            if group.operation.kind == 'new' and group.service_id not in present:
                db.add(RepairOrderPMService(tenant_id=actor.tenant_id, repair_order_id=order.id,
                    service_id=group.service_id, sort_order=position))
                present.add(group.service_id)
                position += 1
    await apply_plan_parts(db, actor, order, plan, parent_ids={group.service_id: operations[group.key].id for group in body.coverage})
    await _refresh_repair_order_totals(db, order.id)
    links = await attach_program_links(db, actor, order, programs, body.coverage, operations)
    result = {'order_id': str(order.id), 'created': created, 'links': [str(link.id) for link in links]}
    await finish_command(db, receipt, result, status_code=201 if created else 200)
    return await work_result(db, actor, body.channel, vehicle, tenant, order.id, result['links'], created=created, replayed=False)


async def order_bundle(db, actor, channel, order_id, *, lock=False):
    """Caller takes the financial lock before requesting a locked bundle."""
    if actor.role == UserRole.MECHANIC and channel == 'shop':
        tenant = await db.scalar(select(Tenant).where(Tenant.id == actor.tenant_id, Tenant.deleted_at.is_(None), Tenant.is_active.is_(True)))
        if tenant is None:
            fail('maintenance_forbidden', 'Access denied.', 403)
    else:
        tenant = await authorize(db, actor, channel)
    order = await db.scalar(select(RepairOrder).where(RepairOrder.id == order_id, RepairOrder.tenant_id == actor.tenant_id, RepairOrder.deleted_at.is_(None)))
    if order is None:
        fail('maintenance_not_found', 'Maintenance work was not found.', 404)
    order = await source_order(db, actor, channel, order.vehicle_id, order_id, finalized=False, lock=lock)
    if actor.role == UserRole.MECHANIC:
        from app.api.v1.endpoints.repair_orders import _check_mechanic_order_assignment
        _check_mechanic_order_assignment(actor, order)
    vehicle = await load_vehicle(db, actor, channel, order.vehicle_id, lock=lock)
    links = list((await db.scalars(select(WorkLink).where(WorkLink.tenant_id == actor.tenant_id, WorkLink.repair_order_id == order_id).order_by(WorkLink.program_id, WorkLink.id))).all())
    programs = {}
    for identity in sorted({link.program_id for link in links}, key=str):
        programs[identity] = await load_program(db, actor, vehicle.id, identity, lock=lock)
    if lock and links:
        links = list((await db.scalars(select(WorkLink).where(WorkLink.tenant_id == actor.tenant_id, WorkLink.id.in_([link.id for link in links]))
            .order_by(WorkLink.program_id, WorkLink.id).with_for_update().execution_options(populate_existing=True))).all())
    query = select(OperationLink).where(OperationLink.tenant_id == actor.tenant_id, OperationLink.work_link_id.in_([link.id for link in links])).order_by(OperationLink.id)
    if lock:
        query = query.with_for_update()
    mappings = list((await db.scalars(query)).all())
    _, source, source_digest = await source_context(db, actor, channel, vehicle, wire.SourceRef(kind='repair_order', id=order.id), finalized=False)
    digest = pricing.signed_digest({'actor': str(actor.id), 'tenant': str(actor.tenant_id), 'channel': channel, 'source': source_digest,
        'order_hold': order.hold_reason, 'programs': [snapshot(programs[i]) for i in sorted(programs, key=str)],
        'links': [{'id': str(row.id), 'version': row.version, 'state': row.state, 'cycle': row.cycle, 'config': row.captured_config} for row in links],
        'mappings': [{'id': str(row.id), 'version': row.version, 'state': row.state, 'operation': str(row.operation_id)} for row in mappings]}, 'm1_review')
    return tenant, vehicle, order, links, programs, mappings, source, digest


async def order_maintenance(db, actor, channel, order_id):
    tenant, vehicle, order, links, programs, mappings, source, digest = await order_bundle(db, actor, channel, order_id)
    rendered = [await program_view(db, actor, channel, program, vehicle, tenant, now()) for program in programs.values()]
    if actor.role == UserRole.MECHANIC:
        rendered = []  # linked operation summary only; no independent config
    required = set()
    for link in links:
        if link.state in OCCUPYING:
            values = link.captured_config['intervals']
            if values['miles'] is not None:
                required.add('odometer_miles')
            if values['engine_hours'] is not None:
                required.add('engine_hours')
    return {'schema_version': 1, 'repair_order_id': str(order.id), 'expected_review_fingerprint': digest,
        'links': [await safe_work(db, actor, channel, link) for link in links], 'programs': rendered,
        'required_readings': [meter for meter in rules.METERS if meter in required], 'can_record_evidence': actor.role in MANAGERS}


def captured_intervals(link):
    return link.captured_config['intervals']


async def completion_preview(db, actor, vehicle, tenant, body, *, lock=False):
    await authorize(db, actor, body.channel, manager=True)
    bundle = await order_bundle(db, actor, body.channel, body.repair_order_id, lock=lock)
    if bundle[1].id != vehicle.id:
        fail('maintenance_not_found', 'Maintenance work was not found.', 404)
    tenant, vehicle, order, all_links, programs, mappings, source, review = bundle
    from app.services import service_checklist
    await service_checklist.guard_completion(db, order)
    if not hmac.compare_digest(body.expected_review_fingerprint, review):
        fail('maintenance_preview_changed', 'Maintenance work changed. Refresh its linked programs before reviewing completion.')
    links = [link for link in all_links if link.state == 'active']
    entries = {entry.work_link_id: entry for entry in body.entries}
    if len(entries) != len(body.entries) or set(entries) != {link.id for link in links}:
        fail('maintenance_invalid_input', 'Review every active linked program exactly once.', 422)
    items, dependencies = [], []
    for link in links:
        program, entry = programs[link.program_id], entries[link.id]
        if entry.program.program_id != program.id:
            fail('maintenance_invalid_input', 'The completion program does not match this work link.', 422)
        check_version(program, entry.program.expected_version)
        if entry.expected_link_version != link.version:
            fail('maintenance_version_conflict', 'This maintenance work link changed. Refresh the completion review.')
        attestation = None
        if entry.attestation is not None:
            attestation, fetched = await resolved_attestation(db, actor, body.channel, vehicle, tenant, entry.attestation, program=program)
            dependencies.extend(fetched)
            controlling = await db.scalar(select(Completion).where(Completion.tenant_id == actor.tenant_id,
                Completion.program_id == program.id, Completion.id == program.controlling_completion_id)) if program.controlling_completion_id else None
            if controlling and controlling.performed_on and (attestation['performed_on'] < controlling.performed_on.isoformat()
                or (attestation['performed_on'] == controlling.performed_on.isoformat() and controlling.source_id != order.id)):
                fail('maintenance_review_required', 'This service date is older than or ambiguous with the controlling completion. Review its historical evidence separately.')
            proposed, missing = rules.next_targets(captured_intervals(link), attestation['performed_on'], attestation['readings'], legacy=link.captured_config['mode'] == 'legacy')
        else:
            proposed, missing = targets(program), ['attestation']
        active_maps = [mapping for mapping in mappings if mapping.work_link_id == link.id and mapping.state == 'active']
        present = {row['id'] for row in source['operations'] if row['deleted_at'] is None}
        expected_services = {str(row['id']) for row in link.captured_config.get('legacy_package') or []} if link.captured_config['mode'] == 'legacy' else {str((link.captured_config.get('service') or {}).get('id'))}
        mapped_services = [mapping.identity_snapshot.get('service_id') for mapping in active_maps]
        complete_scope = bool(active_maps) and set(mapped_services) == expected_services and len(mapped_services) == len(expected_services) and all(str(mapping.operation_id) in present for mapping in active_maps)
        if not complete_scope:
            missing = list(dict.fromkeys([*missing, 'attestation']))
        outcome = 'pending_evidence' if missing else 'advanced'
        if program.review_codes:
            outcome = 'review_required'
        items.append({'program_id': str(program.id), 'current_version': program.version, 'outcome': outcome,
            'previous_targets': targets(program), 'proposed_targets': targets(program) if missing or program.review_codes else proposed,
            'resolved_attestation': {**attestation, 'readings': safe_readings(attestation['readings'], body.channel, actor.role)} if attestation else None,
            'missing': missing, 'warnings': []})
    affected = [await safe_work(db, actor, body.channel, link) for link in links]
    fingerprint = target_digest(actor, vehicle.id, body, items, [review, *dependencies], list(programs.values()), affected)
    return {'schema_version': 1, 'as_of': rules.iso(now()), 'timezone': tenant.timezone, 'purpose': 'completion',
        'expected_target_fingerprint': fingerprint, 'items': items, 'affected_work': affected, 'warnings': []}


async def prepare_finalization(db, actor, order, review, *, channel):
    """Validate pre-transition tokens before operation/status/invoice mutation."""
    # No new role or state requirement is imposed on unrelated old orders.
    if not await db.scalar(select(WorkLink.id).where(WorkLink.tenant_id == actor.tenant_id, WorkLink.repair_order_id == order.id).limit(1)):
        if review is not None:
            fail('maintenance_invalid_input', 'This order has no linked maintenance work to review.', 422)
        return None
    bundle = await order_bundle(db, actor, channel, order.id, lock=True)
    tenant, vehicle, _, links, programs, mappings, source, fingerprint = bundle
    active = [link for link in links if link.state == 'active']
    if review is not None:
        if not active:
            fail('maintenance_review_required', 'Review existing maintenance evidence; repeating finalization cannot advance it again.')
        body = wire.CompletionPreview(purpose='completion', channel=channel, repair_order_id=order.id,
            expected_review_fingerprint=review.expected_review_fingerprint, entries=review.entries)
        preview = await completion_preview(db, actor, vehicle, tenant, body, lock=True)
        if not hmac.compare_digest(review.expected_target_fingerprint, preview['expected_target_fingerprint']):
            fail('maintenance_preview_changed', 'Maintenance evidence changed. Review the current targets before completing.', preview=preview)
        request_id = review.request_id
    else:
        body = wire.CompletionPreview(purpose='completion', channel=channel, repair_order_id=order.id, expected_review_fingerprint=fingerprint,
            entries=[wire.CompletionEntry(work_link_id=link.id, expected_link_version=link.version,
                program=wire.ProgramRef(program_id=link.program_id, expected_version=programs[link.program_id].version), attestation=None) for link in active]) if active else None
        preview = await completion_preview(db, actor, vehicle, tenant, body, lock=True) if body else {'items': []}
        request_id = uuid4()
    return {'bundle': bundle, 'preview': preview, 'body': body, 'request_id': request_id, 'channel': channel}


async def finish_finalization(db, actor, order, prepared):
    """Append evidence after final source status settles, before caller's commit."""
    if prepared is None:
        return None
    await db.flush()
    tenant, vehicle, _, links, programs, mappings, _, _ = prepared['bundle']
    _, source, source_digest = await source_context(db, actor, prepared['channel'], vehicle, wire.SourceRef(kind='repair_order', id=order.id))
    items = {UUID(item['program_id']): item for item in prepared['preview']['items']}
    entries = {entry.work_link_id: entry for entry in prepared['body'].entries} if prepared['body'] else {}
    results = []
    for link in links:
        if link.state != 'active':
            continue
        program, item = programs[link.program_id], items[link.program_id]
        # Resolve original evidence again for storage; downward projection never
        # removes private provenance from the immutable internal snapshot.
        attestation = None
        if entries[link.id].attestation:
            attestation, _ = await resolved_attestation(db, actor, prepared['channel'], vehicle, tenant, entries[link.id].attestation, program=program)
        before = snapshot(program)
        advance = item['outcome'] == 'advanced'
        evidence = Completion(id=uuid4(), tenant_id=actor.tenant_id, program_id=program.id, cycle=link.cycle, work_link_id=link.id,
            action='finalize' if advance else 'pending', result=item['outcome'], performed_on=datetime.fromisoformat(attestation['performed_on']).date() if attestation else None,
            readings=attestation['readings'] if attestation else {meter: None for meter in rules.METERS}, source_kind='repair_order', source_id=order.id,
            source_fingerprint=source_digest, source_snapshot=source, configuration=link.captured_config, previous_targets=targets(program),
            next_targets=item['proposed_targets'], recognition_key='repair_order:' + str(order.id), actor_id=actor.id,
            request_id=prepared['request_id'], request_fingerprint=pricing.signed_digest(prepared['body'].model_dump(mode='json'), 'm1_finalize'))
        db.add(evidence)
        await db.flush()
        touch(program, actor)
        link.version += 1
        link.updated_at = now()
        link.state = 'completed' if advance else 'review_required' if program.review_codes else 'pending_evidence'
        if advance:
            set_targets(program, item['proposed_targets'])
            program.current_cycle += 1
            program.controlling_completion_id = evidence.id
            program.target_provenance = {'kind': 'completion', 'evidence_id': str(evidence.id), 'confirmed_at': rules.iso(now())}
            if program.mode == 'legacy':
                vehicle.next_pm_miles, vehicle.pm_due_date = program.target_miles, program.target_due_on
        append_event(db, actor, program, evidence.action, before, link=link, extra={'completion_id': str(evidence.id)})
        results.append({'program_id': str(program.id), 'work_link_id': str(link.id), 'result': evidence.result, 'missing': item['missing']})
    await db.flush()
    return {'schema_version': 1, 'items': results}


async def evidence_context(db, actor, channel, vehicle, program, intent, *, lock=False, replay=False):
    """Resolve identities; stored references never grant lookup permission."""
    original = link = None
    if intent.action == 'resolve_pending':
        query = select(WorkLink).where(WorkLink.id == intent.work_link_id, WorkLink.tenant_id == actor.tenant_id, WorkLink.program_id == program.id)
        link = await db.scalar(query.with_for_update() if lock else query)
        if link is None:
            fail('maintenance_not_found', 'Maintenance work was not found.', 404)
        if link.version != intent.expected_link_version:
            fail('maintenance_version_conflict', 'This maintenance link changed. Refresh the evidence review.')
        if link.state not in {'pending_evidence', 'review_required'}:
            fail('maintenance_review_required', 'This work has no pending maintenance reading.')
        original = await db.scalar(select(Completion).where(Completion.tenant_id == actor.tenant_id, Completion.work_link_id == link.id,
            Completion.action == 'pending'))
        if original is None or await db.scalar(select(Completion.id).where(Completion.tenant_id == actor.tenant_id, Completion.work_link_id == link.id, Completion.action == 'resolve_pending')):
            fail('maintenance_review_required', 'Review the existing completion evidence for this work.')
        while True:
            successors = list((await db.scalars(select(Completion).where(Completion.tenant_id == actor.tenant_id,
                Completion.program_id == program.id, Completion.supersedes_id == original.id))).all())
            if len(successors) > 1:
                fail('maintenance_review_required', 'Review the conflicting evidence chain before resolving this work.')
            if not successors:
                break
            original = successors[0]
        source_ref = wire.SourceRef(kind='repair_order', id=link.repair_order_id)
    elif intent.action == 'recognize':
        source_ref = intent.source
        if await db.scalar(select(Completion.id).where(Completion.tenant_id == actor.tenant_id, Completion.program_id == program.id,
            Completion.source_kind == source_ref.kind, Completion.source_id == source_ref.id).limit(1)):
            fail('maintenance_review_required', 'This service already has maintenance evidence. Review its existing record.')
    else:
        original = await db.scalar(select(Completion).where(Completion.id == intent.completion_id, Completion.tenant_id == actor.tenant_id, Completion.program_id == program.id))
        if original is None:
            fail('maintenance_not_found', 'Maintenance evidence was not found.', 404)
        if not replay and await db.scalar(select(Completion.id).where(Completion.tenant_id == actor.tenant_id, Completion.supersedes_id == original.id).limit(1)):
            fail('maintenance_review_required', 'This evidence already has a later correction. Review the latest record.')
        source_ref = wire.SourceRef(kind=original.source_kind, id=original.source_id)
        if original.work_link_id:
            query = select(WorkLink).where(WorkLink.id == original.work_link_id, WorkLink.tenant_id == actor.tenant_id, WorkLink.program_id == program.id)
            link = await db.scalar(query.with_for_update() if lock else query)
    try:
        source_row, source, source_digest = await source_context(db, actor, channel, vehicle, source_ref)
    except HTTPException as error:
        if intent.action != 'revoke' or error.status_code not in {404, 422}:
            raise
        # Revoking inaccessible private source data is not allowed. A deleted
        # same-scope source may be revoked without fetching any private details.
        if source_ref.kind == 'external_service':
            if actor.role not in {UserRole.GARAGE_OWNER, UserRole.GARAGE_ADMIN}:
                fail('maintenance_forbidden', 'Outside-service acceptance requires a shop manager.', 403)
            from app.db.models.external_service import ExternalServiceRecord
            source_row = await db.scalar(select(ExternalServiceRecord).where(ExternalServiceRecord.id == source_ref.id, ExternalServiceRecord.tenant_id == actor.tenant_id, ExternalServiceRecord.vehicle_id == vehicle.id))
        else:
            source_row = await db.scalar(select(RepairOrder).where(RepairOrder.id == source_ref.id, RepairOrder.tenant_id == actor.tenant_id, RepairOrder.vehicle_id == vehicle.id))
        if source_row is None:
            fail('maintenance_not_found', 'Service evidence was not found.', 404)
        source = {'kind': source_ref.kind, 'id': str(source_ref.id), 'unavailable': True, 'deleted_at': rules.iso(source_row.deleted_at),
            'version': getattr(source_row, 'version', None), 'status': str(getattr(source_row, 'status', None))}
        source_digest = pricing.signed_digest(source, 'm1_source')
    return original, link, source_row, source, source_digest


async def correction_work(db, actor, channel, program, original):
    links = list((await db.scalars(select(WorkLink).where(WorkLink.tenant_id == actor.tenant_id, WorkLink.program_id == program.id,
        WorkLink.state.in_(OCCUPYING)).order_by(WorkLink.id))).all())
    safe = []
    for link in links:
        view = await safe_work(db, actor, channel, link)
        if not view['can_open']:
            fail('maintenance_not_found', 'Affected maintenance work is unavailable.', 404)
        safe.append(view)
    return links, safe


async def source_evidence_current(db, actor, channel, vehicle, program, evidence, *, accepted_id=None):
    try:
        _, _, digest = await source_context(db, actor, channel, vehicle,
            wire.SourceRef(kind=evidence.source_kind, id=evidence.source_id))
    except HTTPException:
        return False
    if digest != evidence.source_fingerprint:
        return False
    if evidence.id == accepted_id:
        return True  # This exact source was explicitly reviewed in this locked command.
    events = list((await db.scalars(select(Event).where(Event.tenant_id == actor.tenant_id,
        Event.program_id == program.id).order_by(Event.version.desc()))).all())
    accepted_version = next((event.version for event in events
        if (event.after_values or {}).get('completion_id') == str(evidence.id)), None)
    if accepted_version is None:
        return False
    # Restoring the same source bytes does not acknowledge an intervening
    # reopen/delete/edit. Only a later explicit evidence acceptance does that.
    return not any(event.version > accepted_version and event.action == 'source_changed'
        and (event.after_values or {}).get('source_kind') == evidence.source_kind
        and (event.after_values or {}).get('source_id') == str(evidence.source_id) for event in events)


async def prior_valid_targets(db, actor, channel, vehicle, program, original):
    candidates = list((await db.scalars(select(Completion).where(Completion.tenant_id == actor.tenant_id, Completion.program_id == program.id,
        Completion.id != original.id, Completion.result.in_({'advanced', 'reaffirmed'}), Completion.performed_on < original.performed_on)
        .order_by(Completion.performed_on.desc(), Completion.created_at.desc()))).all()) if original.performed_on else []
    for row in candidates:
        if row.configuration.get('baseline_generation') != program.baseline_generation:
            continue
        if await db.scalar(select(Completion.id).where(Completion.tenant_id == actor.tenant_id, Completion.supersedes_id == row.id).limit(1)):
            continue
        anchor, seen = row, set()
        while anchor and anchor.action == 'reaffirm' and anchor.id not in seen:
            seen.add(anchor.id)
            anchor = await db.scalar(select(Completion).where(Completion.tenant_id == actor.tenant_id,
                Completion.program_id == program.id, Completion.id == anchor.supersedes_id)) if anchor.supersedes_id else None
        if anchor is None or anchor.result != 'advanced':
            continue  # Reaffirming pending/history-only evidence cannot create a baseline.
        if await source_evidence_current(db, actor, channel, vehicle, program, row):
            return row.next_targets, row.id
    return (program.baseline_snapshot or {}).get('targets') or {key: None for key in ('due_on', 'odometer_miles', 'engine_hours')}, None


async def evidence_preview(db, actor, vehicle, tenant, body, *, lock=False):
    await authorize(db, actor, body.channel, manager=True)
    program = await load_program(db, actor, vehicle.id, body.program.program_id, lock=lock)
    check_version(program, body.program.expected_version)
    intent = body.evidence
    original, link, source_row, source, source_digest = await evidence_context(db, actor, body.channel, vehicle, program, intent, lock=lock)
    attestation, dependencies, missing, affected = None, [], [], []
    proposed = targets(program)
    corrections = intent.action in {'reaffirm', 'supersede', 'revoke'}
    if corrections:
        affected_links, affected = await correction_work(db, actor, body.channel, program, original)
        acknowledgements = intent.acknowledged_work_link_ids
        if acknowledgements and (len(acknowledgements) != len(set(acknowledgements)) or set(acknowledgements) != {row.id for row in affected_links}):
            fail('maintenance_preview_changed', 'Review every currently affected maintenance link before correcting this evidence.')
    elif program.review_codes:
        fail('maintenance_review_required', 'Review the controlling maintenance evidence before advancing this program.')
    if intent.action in {'recognize', 'resolve_pending', 'supersede'}:
        attestation, dependencies = await resolved_attestation(db, actor, body.channel, vehicle, tenant, intent.attestation,
            program=program, rebaseline=corrections)
        captured = link.captured_config if link else original.configuration if original else configuration(program)
        proposed, missing = rules.next_targets(captured['intervals'], attestation['performed_on'], attestation['readings'], legacy=captured['mode'] == 'legacy')
        outcome = 'pending_evidence' if missing else 'advanced'
        controlling = await db.scalar(select(Completion).where(Completion.tenant_id == actor.tenant_id, Completion.id == program.controlling_completion_id)) if program.controlling_completion_id else None
        if not corrections and controlling and controlling.performed_on:
            if controlling.performed_on.isoformat() > attestation['performed_on']:
                outcome, proposed = 'history_only', targets(program)
            elif controlling.performed_on.isoformat() == attestation['performed_on'] and controlling.source_id != source_row.id:
                fail('maintenance_review_required', 'Another service controls this date. Review that evidence explicitly.')
        if missing:
            proposed = targets(program)
        if intent.action == 'recognize':
            claims = list((await db.scalars(select(WorkLink).where(WorkLink.tenant_id == actor.tenant_id, WorkLink.program_id == program.id, WorkLink.state.in_(OCCUPYING)))).all())
            if claims and outcome != 'history_only':
                fail('maintenance_cycle_claimed', 'Resolve the linked maintenance work before recognizing another service.', existing_work=[await safe_work(db, actor, body.channel, row) for row in claims])
        if corrections and program.controlling_completion_id != original.id and not (program.controlling_completion_id is None and (original.result == 'pending_evidence' or (link and link.state in {'pending_evidence', 'review_required'} and link.cycle == program.current_cycle))):
            outcome, proposed = 'history_only', targets(program)
    elif intent.action == 'reaffirm':
        outcome = 'reaffirmed'
        attestation = {'performed_on': original.performed_on.isoformat(), 'readings': original.readings} if original.performed_on else None
    else:
        outcome = 'revoked'
        if program.controlling_completion_id == original.id:
            proposed, _ = await prior_valid_targets(db, actor, body.channel, vehicle, program, original)
    item = {'program_id': str(program.id), 'current_version': program.version, 'outcome': outcome,
        'previous_targets': targets(program), 'proposed_targets': proposed,
        'resolved_attestation': {**attestation, 'readings': safe_readings(attestation['readings'], body.channel, actor.role)} if attestation else None,
        'missing': missing, 'warnings': []}
    fingerprint = target_digest(actor, vehicle.id, body, [item], [source_digest, *dependencies], [program], affected)
    return {'schema_version': 1, 'as_of': rules.iso(now()), 'timezone': tenant.timezone, 'purpose': 'evidence',
        'expected_target_fingerprint': fingerprint, 'items': [item], 'affected_work': affected, 'warnings': []}


async def unresolved_pending(db, program):
    return list((await db.scalars(select(Completion).join(WorkLink, and_(WorkLink.id == Completion.work_link_id,
        WorkLink.tenant_id == Completion.tenant_id)).where(Completion.tenant_id == program.tenant_id,
        Completion.program_id == program.id, Completion.action == 'pending',
        WorkLink.state.in_({'pending_evidence', 'review_required'})).order_by(Completion.id))).all())


async def source_review_resolved(db, actor, channel, vehicle, program, *, accepted_id=None):
    required = []
    if program.controlling_completion_id:
        controlling = await db.scalar(select(Completion).where(Completion.tenant_id == actor.tenant_id,
            Completion.program_id == program.id, Completion.id == program.controlling_completion_id))
        if controlling is None:
            return False
        required.append(controlling)
    for initial in await unresolved_pending(db, program):
        leaf, seen = initial, set()
        while leaf.id not in seen:
            seen.add(leaf.id)
            successors = list((await db.scalars(select(Completion).where(Completion.tenant_id == actor.tenant_id,
                Completion.program_id == program.id, Completion.supersedes_id == leaf.id))).all())
            if len(successors) > 1:
                return False
            if not successors:
                break
            leaf = successors[0]
        else:
            return False
        if leaf.action != 'revoke':
            required.append(leaf)
    for evidence in required:
        if not await source_evidence_current(db, actor, channel, vehicle, program, evidence, accepted_id=accepted_id):
            return False
    return True


async def evidence_command(db, actor, vehicle_id, body, key):
    tenant, vehicle, receipt, repeated = await start_command(db, actor, body.channel, vehicle_id, 'm1_evidence', key, body,
        f'/vehicles/{vehicle_id}/maintenance-programs/{body.program.program_id}/evidence', manager=True)
    program = await load_program(db, actor, vehicle_id, body.program.program_id, lock=True)
    if repeated:
        row = await db.scalar(select(Completion).where(Completion.id == UUID(repeated['completion_id']), Completion.tenant_id == actor.tenant_id, Completion.program_id == program.id))
        if row is None:
            fail('maintenance_not_found', 'Saved maintenance evidence was not found.', 404)
        # Validate current source scope even when immutable evidence is replayed.
        await evidence_context(db, actor, body.channel, vehicle, program, body.evidence, replay=True) if body.evidence.action == 'revoke' else await source_context(db, actor, body.channel, vehicle, wire.SourceRef(kind=row.source_kind, id=row.source_id))
        return {'schema_version': 1, 'program': await program_view(db, actor, body.channel, program, vehicle, tenant, now()),
            'completion': await completion_view(db, actor, body.channel, row), 'replayed': True}
    preview_body = wire.EvidencePreview(purpose='evidence', channel=body.channel, program=body.program, evidence=body.evidence)
    preview = await evidence_preview(db, actor, vehicle, tenant, preview_body, lock=True)
    if not hmac.compare_digest(body.expected_target_fingerprint, preview['expected_target_fingerprint']):
        fail('maintenance_preview_changed', 'Maintenance evidence changed. Review the current targets.', preview=preview)
    intent = body.evidence
    original, link, source_row, source, source_digest = await evidence_context(db, actor, body.channel, vehicle, program, intent, lock=True)
    affected_links = []
    if intent.action in {'reaffirm', 'supersede', 'revoke'}:
        affected_links, affected = await correction_work(db, actor, body.channel, program, original)
        if set(intent.acknowledged_work_link_ids) != {row.id for row in affected_links}:
            fail('maintenance_preview_changed', 'Explicitly acknowledge every affected work link.', preview=preview)
    item = preview['items'][0]
    if intent.action == 'resolve_pending' and item['missing']:
        fail('maintenance_review_required', 'Provide the remaining actual service readings before resolving this pending evidence.', preview=preview)
    attestation = None
    if hasattr(intent, 'attestation'):
        attestation, _ = await resolved_attestation(db, actor, body.channel, vehicle, tenant, intent.attestation, program=program,
            rebaseline=intent.action == 'supersede')
    elif item['resolved_attestation']:
        attestation = {'performed_on': original.performed_on.isoformat(), 'readings': original.readings}
    before = snapshot(program)
    row = Completion(id=uuid4(), tenant_id=actor.tenant_id, program_id=program.id, cycle=link.cycle if link else original.cycle if original else program.current_cycle,
        work_link_id=link.id if link else original.work_link_id if original else None, action=intent.action, result=item['outcome'],
        performed_on=datetime.fromisoformat(attestation['performed_on']).date() if attestation else None,
        readings=attestation['readings'] if attestation else {meter: None for meter in rules.METERS}, source_kind=source['kind'], source_id=source_row.id,
        source_fingerprint=source_digest, source_snapshot=source, configuration=link.captured_config if link else original.configuration if original else configuration(program),
        previous_targets=targets(program), next_targets=item['proposed_targets'], supersedes_id=original.id if original else None,
        recognition_key=(source['kind'] + ':' + str(source_row.id)) if intent.action == 'recognize' else None,
        actor_id=actor.id, request_id=UUID(key), request_fingerprint=pricing.signed_digest(body.model_dump(mode='json', exclude={'expected_target_fingerprint'}), 'm1_evidence'))
    db.add(row)
    await db.flush()
    touch(program, actor)
    if row.result == 'advanced':
        set_targets(program, row.next_targets)
        if intent.action in {'recognize', 'resolve_pending'} or (link and link.cycle == program.current_cycle) or (original and original.result == 'pending_evidence'):
            program.current_cycle += 1
        program.controlling_completion_id = row.id
        program.target_provenance = {'kind': 'completion', 'evidence_id': str(row.id), 'confirmed_at': rules.iso(now())}
        if program.mode == 'legacy':
            vehicle.next_pm_miles, vehicle.pm_due_date = program.target_miles, program.target_due_on
    if link and intent.action in {'resolve_pending', 'supersede'}:
        link.version += 1
        link.updated_at = now()
        link.state = 'completed' if row.result in {'advanced', 'history_only'} else 'pending_evidence'
    if intent.action in {'reaffirm', 'supersede', 'revoke'}:
        if program.controlling_completion_id == original.id:
            if intent.action == 'revoke':
                proposed, prior = await prior_valid_targets(db, actor, body.channel, vehicle, program, original)
                set_targets(program, proposed)
                program.controlling_completion_id = prior
                program.target_provenance = {'kind': 'completion' if prior else 'baseline', 'evidence_id': str(prior) if prior else None, 'confirmed_at': rules.iso(now())}
            else:
                program.controlling_completion_id = row.id
        if await source_review_resolved(db, actor, body.channel, vehicle, program, accepted_id=row.id):
            program.review_codes = [code for code in program.review_codes or [] if not code.startswith('source_')]
    append_event(db, actor, program, row.action, before, reason=getattr(intent, 'reason', None), link=link, extra={'completion_id': str(row.id)})
    await db.flush()
    for affected in affected_links:
        if affected.state != 'review_required' or program.review_codes:
            continue
        prior = (affected.restore_state or {}).get('review_previous_state', 'active')
        before = snapshot(program)
        touch(program, actor)
        affected.version += 1
        affected.updated_at = now()
        affected.state = prior if prior in {'active', 'pending_evidence', 'completed'} else 'active'
        append_event(db, actor, program, 'work_review_acknowledged', before, link=affected)
        await db.flush()
    await finish_command(db, receipt, {'completion_id': str(row.id)}, status_code=201)
    return {'schema_version': 1, 'program': await program_view(db, actor, body.channel, program, vehicle, tenant, now()),
        'completion': await completion_view(db, actor, body.channel, row), 'replayed': False}


async def source_programs_locked(db, actor, vehicle_id, kind, source_id):
    identities = set((await db.scalars(select(Completion.program_id).where(Completion.tenant_id == actor.tenant_id,
        Completion.source_kind == kind, Completion.source_id == source_id))).all())
    if kind == 'repair_order':
        identities.update((await db.scalars(select(WorkLink.program_id).where(WorkLink.tenant_id == actor.tenant_id,
            WorkLink.repair_order_id == source_id))).all())
    return [await load_program(db, actor, vehicle_id, identity, lock=True) for identity in sorted(identities, key=str)]


async def invalidate_source(db, actor, vehicle_id, kind, source_id, *, programs=None):
    """Called beneath an existing vehicle lock, never takes tenant/order locks."""
    programs = programs if programs is not None else await source_programs_locked(db, actor, vehicle_id, kind, source_id)
    for program in programs:
        matches = list((await db.scalars(select(Completion).where(Completion.tenant_id == actor.tenant_id, Completion.program_id == program.id,
            Completion.source_kind == kind, Completion.source_id == source_id))).all())
        controlling = next((row for row in matches if row.id == program.controlling_completion_id), None)
        pending = [row for row in await unresolved_pending(db, program) if row.source_kind == kind and row.source_id == source_id]
        before = snapshot(program)
        touch(program, actor)
        if controlling or pending:
            program.review_codes = sorted(set([*(program.review_codes or []), 'source_changed']))
        append_event(db, actor, program, 'source_changed', before, extra={'source_kind': kind, 'source_id': str(source_id)})
        await db.flush()
        if controlling or pending:
            links = list((await db.scalars(select(WorkLink).where(WorkLink.tenant_id == actor.tenant_id, WorkLink.program_id == program.id,
                WorkLink.state.in_({'active', 'pending_evidence'})).order_by(WorkLink.id).with_for_update())).all())
            for link in links:
                before = snapshot(program)
                touch(program, actor)
                link.restore_state = {**(link.restore_state or {}), 'review_previous_state': link.state}
                link.state, link.version, link.updated_at = 'review_required', link.version + 1, now()
                append_event(db, actor, program, 'source_review_required', before, link=link)
                await db.flush()


async def detach_links(db, actor, links, programs, mappings, *, action, restorable=False):
    for link in links:
        program = programs[link.program_id]
        before = snapshot(program)
        touch(program, actor)
        if restorable:
            link.restore_state = {'reason': action, 'state': link.state, 'configuration': configuration(program), 'targets': targets(program),
                'mapping_ids': [str(row.id) for row in mappings if row.work_link_id == link.id and row.state == 'active']}
        link.state, link.version, link.updated_at = 'detached', link.version + 1, now()
        changed = {}
        for mapping in mappings:
            if mapping.work_link_id == link.id and mapping.state == 'active':
                mapping.state, mapping.version, mapping.updated_at = 'detached', mapping.version + 1, now()
                changed[str(mapping.id)] = mapping.version
        append_event(db, actor, program, action, before, link=link, extra={'operation_versions': changed})
        await db.flush()


async def operation_removal_metadata(db, actor, order, operation_ids, *, channel=None, lock=False):
    affected_ids = set((await db.scalars(select(OperationLink.work_link_id).where(OperationLink.tenant_id == order.tenant_id,
        OperationLink.operation_id.in_(operation_ids), OperationLink.state == 'active'))).all())
    if not affected_ids:
        return None, None
    if actor is None:
        fail('maintenance_operation_linked', 'Review linked maintenance before removing this operation.')
    channel = channel or ('fleet' if actor.role == UserRole.FLEET_MANAGER else 'shop')
    bundle = await order_bundle(db, actor, channel, order.id, lock=lock)
    _, _, _, links, programs, mappings, _, digest = bundle
    affected = [row for row in links if row.id in affected_ids and row.state != 'detached']
    views = [{**await safe_work(db, actor, channel, row), 'program_id': str(row.program_id), 'program_name': programs[row.program_id].name} for row in affected]
    binding = {'review': digest, 'removed_operations': sorted(str(i) for i in operation_ids),
        'mappings': [{'id': str(row.id), 'version': row.version, 'state': row.state} for row in mappings if row.work_link_id in affected_ids]}
    return {'affected_work': views}, (bundle, affected, binding)


async def guard_operation_removal(db, actor, order, operation_ids, *, expected=None, channel=None, confirmed=False):
    metadata, context = await operation_removal_metadata(db, actor, order, operation_ids, channel=channel, lock=True)
    if not metadata:
        return
    bundle, affected, _ = context
    _, _, _, _, programs, mappings, _, digest = bundle
    if not confirmed and (not isinstance(expected, str) or not hmac.compare_digest(expected, digest)):
        fail('maintenance_preview_changed', 'Review all linked maintenance programs before removing this operation.')
    for link in affected:
        if link.state != 'active' or programs[link.program_id].review_codes or await db.scalar(select(Completion.id).where(Completion.tenant_id == order.tenant_id, Completion.work_link_id == link.id).limit(1)):
            fail('maintenance_operation_linked', 'Completed or disputed maintenance evidence cannot be detached by removing an operation.')
        ids = [mapping.operation_id for mapping in mappings if mapping.work_link_id == link.id and mapping.state == 'active']
        if await db.scalar(select(Labor.id).where(Labor.tenant_id == order.tenant_id, Labor.id.in_(ids),
            or_(Labor.execution_status == 'completed', Labor.completed_at.is_not(None))).limit(1)):
            fail('maintenance_operation_linked', 'Completed maintenance work requires evidence review before removal.')
    await detach_links(db, actor, affected, programs, mappings, action='operation_detached')


async def detach_command(db, actor, vehicle_id, program_id, body, key):
    # Resolve the actual order before taking vehicle/program locks.
    await authorize(db, actor, body.channel)
    await load_vehicle(db, actor, body.channel, vehicle_id)
    link = await db.scalar(select(WorkLink).join(Program, Program.id == WorkLink.program_id).where(WorkLink.tenant_id == actor.tenant_id,
        WorkLink.id == body.work_link_id, WorkLink.program_id == program_id, Program.vehicle_id == vehicle_id))
    if link is None:
        fail('maintenance_not_found', 'Maintenance work was not found.', 404)
    await pricing.lock_tenant_financials(db, actor.tenant_id)
    await source_order(db, actor, body.channel, vehicle_id, link.repair_order_id, finalized=False, lock=True)
    vehicle = await load_vehicle(db, actor, body.channel, vehicle_id, lock=True)
    tenant = await db.get(Tenant, actor.tenant_id)
    receipt, repeated = await command_receipt(db, actor, 'm1_detach', key, body, f'/vehicles/{vehicle_id}/maintenance-programs/{program_id}/detach-work')
    program = await load_program(db, actor, vehicle_id, program_id, lock=True)
    if not repeated:
        check_version(program, body.expected_version)
        if link.version != body.expected_link_version:
            fail('maintenance_version_conflict', 'This maintenance work changed. Refresh it before detaching.')
        mappings = list((await db.scalars(select(OperationLink).where(OperationLink.tenant_id == actor.tenant_id, OperationLink.work_link_id == link.id))).all())
        if link.state != 'active' or program.review_codes or await db.scalar(select(Completion.id).where(Completion.tenant_id == actor.tenant_id, Completion.work_link_id == link.id).limit(1)):
            fail('maintenance_operation_linked', 'Accepted or pending evidence cannot be detached.')
        if await db.scalar(select(Labor.id).where(Labor.tenant_id == actor.tenant_id, Labor.id.in_([row.operation_id for row in mappings]),
            or_(Labor.execution_status == 'completed', Labor.completed_at.is_not(None))).limit(1)):
            fail('maintenance_operation_linked', 'Completed operations require maintenance evidence review.')
        await detach_links(db, actor, [link], {program.id: program}, mappings, action='work_detached')
        await finish_command(db, receipt, {'link_id': str(link.id)})
    return {'schema_version': 1, 'program': await program_view(db, actor, body.channel, program, vehicle, tenant, now()),
        'link': await safe_work(db, actor, body.channel, link), 'replayed': repeated is not None}


async def restore_mapping_facts(db, order, mappings):
    facts = []
    for mapping in sorted(mappings, key=lambda row: str(row.id)):
        labor = await db.scalar(select(Labor).where(Labor.id == mapping.operation_id, Labor.tenant_id == order.tenant_id,
            Labor.repair_order_id == order.id, Labor.deleted_at.is_(None)))
        if labor is None:
            fail('maintenance_restore_conflict', 'An original maintenance operation is unavailable.')
        facts.append({'id': str(mapping.id), 'version': mapping.version, 'state': mapping.state,
            'operation_id': str(labor.id), 'service_id': str(labor.source_service_id),
            'execution_version': labor.execution_version, 'execution_status': labor.execution_status,
            'completed_at': rules.iso(labor.completed_at)})
    return facts


def restoration_config(value):
    return {key: item for key, item in value.items() if key != 'name'}


async def partial_restore_valid(db, order, program, link, mappings, saved):
    if saved.get('state') != 'active' or not saved.get('mapping_facts'):
        return False
    if await db.scalar(select(Completion.id).where(Completion.tenant_id == order.tenant_id,
        Completion.program_id == program.id, or_(Completion.work_link_id == link.id,
            and_(Completion.source_kind == 'repair_order', Completion.source_id == order.id))).limit(1)):
        return False
    # Compare relevant event history as well as current values: changing a
    # target/configuration away and back cannot erase a disputed generation.
    events = list((await db.scalars(select(Event).where(Event.tenant_id == order.tenant_id, Event.program_id == program.id,
        Event.version > saved.get('program_version', -1)).order_by(Event.version))).all())
    relevant = ('mode', 'intervals', 'service', 'legacy_package', 'legacy_snapshot', 'baseline_generation',
        'targets', 'current_cycle', 'review_codes', 'controlling_completion_id', 'archived_at')
    for event in events:
        before, after = event.before_values or {}, event.after_values or {}
        if event.action in {'source_changed', 'source_review_required'} or any(before.get(key) != after.get(key) for key in relevant):
            return False
    current = await restore_mapping_facts(db, order, [row for row in mappings if row.work_link_id == link.id])
    return current == saved['mapping_facts']


async def order_lifecycle(db, actor, order, action, *, intended_status=None):
    """Before stock/status mutations; caller owns tenant/order lock and commit."""
    if not await db.scalar(select(WorkLink.id).where(WorkLink.tenant_id == order.tenant_id, WorkLink.repair_order_id == order.id).limit(1)) and not await db.scalar(select(Completion.id).where(Completion.tenant_id == order.tenant_id, Completion.source_kind == 'repair_order', Completion.source_id == order.id).limit(1)):
        return
    vehicle = await db.scalar(select(Vehicle).where(Vehicle.id == order.vehicle_id, Vehicle.tenant_id == order.tenant_id).with_for_update())
    if vehicle is None:
        fail('maintenance_not_found', 'Maintenance vehicle was not found.', 404)
    rows = await source_programs_locked(db, actor, vehicle.id, 'repair_order', order.id)
    programs = {row.id: row for row in rows}
    links = list((await db.scalars(select(WorkLink).where(WorkLink.tenant_id == order.tenant_id, WorkLink.repair_order_id == order.id).order_by(WorkLink.id).with_for_update())).all())
    mappings = list((await db.scalars(select(OperationLink).where(OperationLink.tenant_id == order.tenant_id,
        OperationLink.work_link_id.in_([row.id for row in links])).order_by(OperationLink.id).with_for_update())).all())
    if action == 'restore':
        operational = {RepairOrderStatus.DRAFT, RepairOrderStatus.QUOTED, RepairOrderStatus.APPROVED,
            RepairOrderStatus.IN_PROGRESS, RepairOrderStatus.PENDING_REVIEW}
        if (intended_status or order.status) not in operational:
            return  # Restoring a still-cancelled/finalized row does not resume work.
        for link in links:
            saved = link.restore_state or {}
            partial = link.state == 'review_required' and saved.get('partial_performed') is True
            if (link.state != 'detached' and not partial) or saved.get('reason') not in {'order_deleted', 'order_cancelled'}:
                continue
            program = programs[link.program_id]
            invalid = program.archived_at or program.review_codes or program.current_cycle != link.cycle
            invalid = invalid or restoration_config(configuration(program)) != restoration_config(saved.get('configuration', {})) or targets(program) != saved.get('targets', link.captured_targets)
            invalid = invalid or await db.scalar(select(WorkLink.id).where(WorkLink.tenant_id == order.tenant_id,
                WorkLink.program_id == program.id, WorkLink.cycle == link.cycle, WorkLink.state.in_(OCCUPYING), WorkLink.id != link.id).limit(1))
            if invalid or (partial and not await partial_restore_valid(db, order, program, link, mappings, saved)):
                fail('maintenance_restore_conflict', 'This maintenance cycle changed or is already claimed. Review it before restoring this order.')
            before = snapshot(program)
            touch(program, actor)
            link.state, link.version, link.updated_at = 'active', link.version + 1, now()
            changed = {}
            for mapping in mappings:
                if str(mapping.id) in saved.get('mapping_ids', []):
                    if not await db.scalar(select(Labor.id).where(Labor.id == mapping.operation_id, Labor.tenant_id == order.tenant_id,
                        Labor.repair_order_id == order.id, Labor.deleted_at.is_(None))):
                        fail('maintenance_restore_conflict', 'An original maintenance operation is unavailable.')
                    if not partial:
                        mapping.state, mapping.version, mapping.updated_at = 'active', mapping.version + 1, now()
                        changed[str(mapping.id)] = mapping.version
            append_event(db, actor, program, 'partial_work_resumed' if partial else 'order_restored', before, link=link, extra={'operation_versions': changed})
            await db.flush()
        return
    detachable, disputed = [], []
    for link in links:
        evidence = await db.scalar(select(Completion.id).where(Completion.tenant_id == order.tenant_id, Completion.work_link_id == link.id).limit(1))
        completed = await db.scalar(select(Labor.id).where(Labor.tenant_id == order.tenant_id, Labor.id.in_([row.operation_id for row in mappings if row.work_link_id == link.id]),
            or_(Labor.execution_status == 'completed', Labor.completed_at.is_not(None))).limit(1))
        if action in {'delete', 'cancel'} and link.state == 'active' and not evidence and not completed:
            detachable.append(link)
        elif action in {'delete', 'cancel', 'reopen', 'void'} and link.state == 'active' and completed and not evidence:
            disputed.append(link)
    await invalidate_source(db, actor, vehicle.id, 'repair_order', order.id, programs=rows)
    for link in disputed:
        program = programs[link.program_id]
        before = snapshot(program)
        touch(program, actor)
        saved = {'review_previous_state': link.state}
        if action in {'delete', 'cancel'}:
            selected = [row for row in mappings if row.work_link_id == link.id]
            saved.update(reason='order_deleted' if action == 'delete' else 'order_cancelled', state=link.state,
                partial_performed=True, configuration=configuration(program), targets=targets(program),
                program_version=program.version, baseline_generation=program.baseline_generation, cycle=program.current_cycle,
                mapping_ids=[str(row.id) for row in selected], mapping_facts=await restore_mapping_facts(db, order, selected))
        link.restore_state = saved
        link.state, link.version, link.updated_at = 'review_required', link.version + 1, now()
        append_event(db, actor, program, 'performed_work_review_required', before, link=link)
        await db.flush()
    if detachable:
        await detach_links(db, actor, detachable, programs, mappings, action='order_deleted' if action == 'delete' else 'order_cancelled', restorable=True)


async def has_vehicle_program(db, order):
    return bool(await db.scalar(select(Program.id).where(Program.tenant_id == order.tenant_id, Program.vehicle_id == order.vehicle_id).limit(1)))


async def enroll_scheduled_legacy_work(db, actor, vehicle, program, order, services):
    """The existing one-off legacy package never overwrites the truck default."""
    from types import SimpleNamespace
    program = program or await sync_legacy_configuration(db, actor, vehicle, force=True)
    captured = configuration(program)
    captured['legacy_package'] = [await service_ref(db, actor.tenant_id, template.id, saved={'name': template.name}) for template in services]
    operations, groups, ambiguous = {}, [], False
    for template in services:
        matches = list((await db.scalars(select(Labor).where(Labor.tenant_id == actor.tenant_id, Labor.repair_order_id == order.id,
            Labor.source_service_id == template.id, Labor.deleted_at.is_(None)))).all())
        if len(matches) != 1:
            ambiguous = True
            continue
        key = str(template.id)
        operations[key] = matches[0]
        groups.append(SimpleNamespace(key=key, service_id=template.id, program_ids=[program.id]))
    links = await attach_program_links(db, actor, order, [program], groups, operations, captured_configs={program.id: captured})
    if ambiguous or not groups:
        link = links[0]
        before = snapshot(program)
        touch(program, actor)
        program.review_codes = sorted(set([*(program.review_codes or []), 'legacy_operation_mapping_review']))
        link.state, link.version, link.updated_at = 'review_required', link.version + 1, now()
        append_event(db, actor, program, 'legacy_mapping_review', before, link=link)
        await db.flush()
    return links[0]
