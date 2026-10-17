"""One read-only typed plan shared by preview and locked attachment adapters."""
from __future__ import annotations
import copy
import math
from dataclasses import dataclass, field
from decimal import Decimal
from types import SimpleNamespace
from uuid import UUID, uuid5, NAMESPACE_URL
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from app.db.models.inventory import Inventory, PartsUsage
from app.db.models.labor import Labor
from app.db.models.service import Service, ServicePart
from app.db.models.repair_order import RepairOrder
from app.db.models.fleet import RepairOrderPMService
from app.db.models.customer import Customer
from app.db.models.inventory_lifecycle import CounterSale, CounterSaleLine
from app.db.models.user import UserRole
from app.schemas.parts_pricing import ResolveRequest
from app.services import parts_pricing as pricing, customer_pricing as account
from app.services.parts_pricing_rules import PricePolicy, ResolvedPrice, resolve_price, safe_price, cents, fail, line_total, amount
from app.services.pricing import compute_canonical_order_totals
from app.services.internal_fleet import uses_internal_fleet_pricing, fleet_labor_uses_customer_rate
from app.core.work_value_validation import validate_part_quantity, validate_labor_hours


@dataclass
class PlannedPart:
    key: str
    inventory: Inventory
    quantity: Decimal
    disposition: str = 'added'
    existing: object | None = None
    price: ResolvedPrice | None = None
    source_service_id: UUID | None = None
    source_line_id: UUID | None = None
    source_component_id: UUID | None = None
    reserves: bool = True
    included: bool = True
    availability: dict = field(default_factory=dict)
    intent: str = 'default'
    reason: str | None = None
    charged: Decimal | None = None

    @property
    def unit_price(self):
        if self.charged is not None: return self.charged
        if self.existing is not None: return getattr(self.existing,'unit_price',getattr(self.existing,'charged_unit_price',None))
        return self.price.charged

    @property
    def default(self):
        if self.existing is not None: return getattr(self.existing,'list_price',getattr(self.existing,'list_unit_price',None))
        return self.price.default

    @property
    def cost(self):
        return self.existing.unit_cost if self.existing is not None else self.price.actual_cost

    @property
    def snapshot(self):
        return (self.existing.pricing_snapshot or {}) if self.existing is not None else self.price.snapshot


@dataclass
class PricingPlan:
    request: ResolveRequest
    order: object | None
    sale: object | None
    services: list
    lines: list[PlannedPart]
    response: dict
    policy: PricePolicy
    account_snapshot: dict | None = None

    def confirm(self, supplied, *, stock_acknowledged=False):
        actual=self.response['pricing_preview_fingerprint']
        if not supplied:
            # An unmanaged direct add already carries explicit shortage consent
            # in allow_stock_shortage. Keep that existing stock contract without
            # weakening managed/manual prices or a supplied quote's comparison.
            stock_only_ack = (
                stock_acknowledged and self.request.plan.kind == 'parts_add'
                and not self.response['availability']['omitted_line_keys']
                and all(p.existing or (not p.snapshot.get('managed') and p.intent == 'default') for p in self.lines)
            )
            if self.response['confirmation_required'] and not stock_only_ack:
                fail('pricing_preview_required','Review the proposed parts and total before applying.',409,preview=self.safe_response())
            return
        if supplied==actual: return
        # Both components are opaque keyed digests. Availability is intentionally
        # separate so stock scope changes are not presented as price changes.
        old=supplied.split('.') if isinstance(supplied,str) else []
        fresh=actual.split('.')
        code='bundle_availability_changed' if len(old)==3 and old[:2]==fresh[:2] else 'pricing_preview_changed'
        fail(code,'The proposed work changed. Review the updated parts and total.',409,preview=self.safe_response())

    def safe_response(self):
        result=copy.deepcopy(self.response)
        if result['projection']=='shop': result['management']=None
        return result

    def new(self,key):
        return next(p for p in self.lines if p.key==key)


def retained_part(row, item, *, counter=False):
    return PlannedPart(('sale:' if counter else 'usage:')+str(row.id),item,Decimal(str(row.quantity)),disposition='retained',existing=row,
        source_service_id=getattr(row,'source_service_id',None),source_line_id=getattr(row,'source_line_id',None),source_component_id=getattr(row,'source_component_id',None),reserves=not counter)


def reservation(row):
    if row.stock_reserved_packages is not None: return row.stock_reserved_packages
    if row.source_service_id:
        fail('bundle_reservation_unknown','Review the original stock reservation before changing this bundled part.',409)
    return math.ceil(row.quantity)


async def load_services(db,tenant_id,ids,*,lock=False):
    if len(ids)>30 or len(set(ids))!=len(ids): fail('invalid_services','Choose up to 30 distinct services.')
    if not ids: return []
    stmt=select(Service).where(Service.tenant_id==tenant_id,Service.id.in_(ids),Service.deleted_at.is_(None),Service.is_active.is_(True)).order_by(Service.id).options(selectinload(Service.service_parts).selectinload(ServicePart.inventory_item)).execution_options(populate_existing=True)
    if lock: stmt=stmt.with_for_update(of=Service)
    rows={s.id:s for s in (await db.scalars(stmt)).all()}
    if set(rows)!=set(ids): fail('service_not_found','One or more services were not found.',404)
    return [rows[i] for i in ids]


async def context(db,actor,request,tenant,lock):
    c=request.context
    if c.kind=='repair_order':
        from app.services.price_build_service import PriceBuildService, PriceBuildNotFoundError
        from app.api.v1.endpoints.repair_orders import _check_mechanic_order_assignment, _require_editable_ro
        try: order=await PriceBuildService().load_order(db,c.repair_order_id,tenant_id=actor.tenant_id,for_update=lock)
        except PriceBuildNotFoundError: fail('order_not_found','Repair order not found.',404)
        _check_mechanic_order_assignment(actor,order)
        inspect_only=request.plan.kind=='parts_add' and not request.plan.lines
        if not inspect_only or lock: _require_editable_ro(order)
        return order,None
    if c.kind=='fleet_draft':
        if actor.role not in pricing.EDITORS: fail('pricing_access_denied','Access denied.',403)
        from app.api.v1.endpoints.fleet import _load_fleet_vehicle_or_404
        vehicle=await _load_fleet_vehicle_or_404(db,actor.tenant_id,c.vehicle_id)
        payer=await account.live_customer(db,actor.tenant_id,c.bill_to_customer_id or vehicle.customer_id,lock=lock)
        if payer is None: fail('customer_not_found','Bill-to company not found.',404)
        internal=uses_internal_fleet_pricing(payer,tenant)
        snapshot=await account.candidate(db,tenant,payer,lock=lock)
        return SimpleNamespace(id=None,tenant_id=actor.tenant_id,pricing_policy_snapshot=snapshot,pricing_matrix_revision_id=account.revision_id(snapshot),customer_id=payer.id,vehicle_id=vehicle.id,is_internal=internal,
            bill_labor_at_customer_rate=bool(vehicle.bill_labor_at_customer_rate) if internal else False,parts_usage=[],labor_items=[],labor_discount_amount=Decimal(0),order_discount_amount=Decimal(0),status='draft',pricing_locked_at=None,pricing_lock_reason=None,tenant=tenant),None
    from app.services.counter_sale_service import require_counter_sales_enabled, _tenant_customer, require_counter_sale_role
    await require_counter_sales_enabled(db,actor);require_counter_sale_role(actor)
    if c.customer_id: await account.live_customer(db,tenant.id,c.customer_id,lock=lock)
    await _tenant_customer(db,tenant.id,c.customer_id)
    sale=None
    if c.sale_id:
        stmt=select(CounterSale).where(CounterSale.tenant_id==tenant.id,CounterSale.id==c.sale_id,CounterSale.deleted_at.is_(None)).execution_options(populate_existing=True)
        if lock: stmt=stmt.with_for_update()
        sale=await db.scalar(stmt)
        if sale is None: fail('sale_not_found','Counter sale not found.',404)
        if sale.status!='draft': fail('sale_not_editable','Only draft sales can be edited.',409)
        if c.expected_sale_version!=sale.version: fail('pricing_version_conflict','This sale changed. Refresh it while keeping your draft.',409)
    elif c.expected_sale_version is not None: fail('invalid_sale_version','A new sale has no saved version.')
    return None,sale


async def build_plan(db, actor, request: ResolveRequest, *, lock=False):
    try:
        return await _build_plan(db, actor, request, lock=lock)
    except HTTPException as exc:
        if request.context.kind == 'counter_sale' and exc.status_code == 404:
            raise HTTPException(404, 'Not found') from exc
        raise
    except ValueError as exc:
        fail('invalid_work_value', str(exc))


async def _build_plan(db,actor,request:ResolveRequest,*,lock=False):
    tenant=await pricing.authorize(db,actor)
    mode=pricing.presentation(actor,request.pricing_presentation,request.include_management_details,request.context.kind=='counter_sale')
    kind=request.plan.kind
    if (request.context.kind=='counter_sale') != (kind=='counter_draft') or (request.context.kind=='fleet_draft') != (kind=='fleet_create'):
        fail('invalid_pricing_context','This plan does not belong to the selected workspace.')
    if lock: await pricing.lock_tenant_financials(db,actor.tenant_id)
    order,sale=await context(db,actor,request,tenant,lock)
    account_snapshot=getattr(order,'pricing_policy_snapshot',None) if order else getattr(sale,'pricing_policy_snapshot',None)
    if kind=='counter_draft' and (sale is None or sale.customer_id!=request.context.customer_id):
        payer=await account.live_customer(db,actor.tenant_id,request.context.customer_id,lock=lock) if request.context.customer_id else None
        account_snapshot=await account.candidate(db,tenant,payer,lock=lock,counter=True)
    legacy = kind == 'service_apply' and request.plan.attachment_path == 'fleet_legacy_service'
    if legacy and order.is_pm:
        fail('invalid_pricing_context', 'Use PM services to change this work order.', 400)
    if legacy and (actor.role not in pricing.EDITORS or not (order.is_internal or order.is_fleet_work) or order.is_pm or request.plan.quantity != 1):
        fail('invalid_pricing_context','This service adapter is only available for non-PM fleet work.',409)
    if kind == 'pm_replace' and str(getattr(order.status, 'value', order.status)) != 'draft':
        fail('order_not_editable','PM services can only be changed on a draft work order.',409)
    lines=[];services=[];policy=PricePolicy();new_inputs={};labor_inputs=[]
    if order is not None:
        lines=[retained_part(p,p.inventory_item) for p in order.parts_usage if p.deleted_at is None]
    else:
        old=list((await db.scalars(select(CounterSaleLine).where(CounterSaleLine.tenant_id==actor.tenant_id,CounterSaleLine.sale_id==sale.id,CounterSaleLine.deleted_at.is_(None)).order_by(CounterSaleLine.id))).all()) if sale else []
        invs=await pricing.inventory(db,actor.tenant_id,[p.inventory_id for p in old], retained_ids=[p.inventory_id for p in old])
        lines=[retained_part(p,invs[p.inventory_id],counter=True) for p in old]
    if kind=='parts_add':
        from app.api.v1.endpoints.repair_orders import _validate_source_references
        for entry in request.plan.lines:
            await _validate_source_references(db,tenant_id=actor.tenant_id,order_id=order.id,source_service_id=entry.source_service_id,source_line_id=entry.source_line_id)
            new_inputs[entry.client_key]=entry
            lines.append(PlannedPart(entry.client_key,None,entry.quantity,source_service_id=entry.source_service_id,source_line_id=entry.source_line_id,intent=entry.pricing_intent,reason=entry.price_override_reason))
    elif kind in {'service_apply','pm_replace','fleet_create'}:
        ids=[request.plan.service_id] if kind=='service_apply' else request.plan.service_ids
        services=await load_services(db,actor.tenant_id,ids,lock=False)
        old_by_service={}
        for li in order.labor_items:
            if li.source_service_id and li.deleted_at is None:
                old_by_service.setdefault(li.source_service_id,[]).append(li)
        if not legacy and any(len(old_by_service.get(sid,[]))>1 for sid in ids): fail('bundle_identity_ambiguous','Review duplicate service operations before applying this package.',409)
        if actor.role==UserRole.MECHANIC and any(old_by_service.get(sid) for sid in ids): fail('bundle_staff_review_required','Mechanics may add new operations; changing an existing service requires staff review.',409)
        prior=set()
        if kind=='pm_replace':
            prior=set((await db.scalars(select(RepairOrderPMService.service_id).where(RepairOrderPMService.tenant_id==actor.tenant_id,RepairOrderPMService.repair_order_id==order.id))).all())
        affected=set() if legacy else prior|set(ids)
        remaining=[p for p in lines if p.source_service_id in affected]
        for p in remaining: p.disposition='removed';p.included=False
        for svc in services:
            parent=None if legacy else (old_by_service.get(svc.id) or [None])[0]
            qty=Decimal(request.plan.quantity) if kind=='service_apply' else Decimal(1)
            seen=set()
            for component in svc.service_parts:
                if component.inventory_item is None or component.inventory_item.deleted_at is not None: continue
                if component.inventory_id in seen: fail('bundle_identity_ambiguous','Review duplicate part components before applying this package.',409)
                seen.add(component.inventory_id)
                quantity=validate_part_quantity(Decimal(str(component.quantity))*qty)
                candidates=[p for p in remaining if p.source_service_id==svc.id and p.inventory.id==component.inventory_id and (p.source_line_id is None or (parent and p.source_line_id==parent.id))]
                exact=[p for p in candidates if p.source_component_id==component.id]
                matches=exact or candidates
                if len(matches)>1: fail('bundle_identity_ambiguous','Review duplicate historical part lines before applying this package.',409)
                if matches:
                    p=matches[0];remaining.remove(p);p.quantity=quantity;p.disposition='retained';p.included=True
                    p.reserves=bool(p.existing.stock_reserved_packages) or bool(p.existing.stock_shortage_override)
                    # Origin/component references stay immutable on retained rows;
                    # key follows saved identity, even after a template recreation.
                    if p.existing.quantity!=quantity: reservation(p.existing)
                else:
                    key='component:'+str(component.id)
                    lines.append(PlannedPart(key,component.inventory_item,quantity,source_service_id=svc.id,source_line_id=parent.id if parent else None,source_component_id=component.id,reserves=kind=='service_apply' and not legacy))
                    new_inputs[key]=SimpleNamespace(inventory_id=component.inventory_id,pricing_intent='default',unit_price=None,price_override_reason=None)
            labor_inputs.append({'service_id':str(svc.id),'hours':str(validate_labor_hours(Decimal(svc.duration_minutes or 0)/60*qty)), 'parent_id':str(parent.id) if parent else None})
        for p in lines:
            if p.disposition=='removed': reservation(p.existing)
        if kind=='fleet_create':
            for entry in request.plan.part_lines:
                if entry.client_key in new_inputs: fail('invalid_line_key','Part line keys must be unique.')
                new_inputs[entry.client_key]=entry
                lines.append(PlannedPart(entry.client_key,None,entry.quantity,intent=entry.pricing_intent,reason=entry.price_override_reason))
            labor_inputs.extend({'hours':str(li.hours),'description':li.description} for li in request.plan.labor_lines)
    else:
        existing={p.existing.id:p for p in lines}
        by_inventory = {}
        for saved in lines:
            by_inventory.setdefault(saved.inventory.id, []).append(saved)
        for p in lines: p.disposition='removed';p.included=False
        for entry in request.plan.lines:
            if entry.sale_line_id:
                p=existing.get(entry.sale_line_id)
                if p is None or p.inventory.id!=entry.inventory_id: fail('sale_line_not_found','The retained sale line was not found.',404)
            else:
                matches = by_inventory.get(entry.inventory_id, [])
                if len(matches) > 1:
                    fail('sale_line_ambiguous', 'Choose the exact saved sale line before changing this part.', 409)
                p = matches[0] if matches else None
            if p:
                p.disposition='retained';p.included=True;p.quantity=Decimal(entry.quantity);p.intent=entry.pricing_intent;p.reason=entry.price_override_reason
                supplied=entry.charged_unit_price
                if (supplied is not None and supplied != p.unit_price) or entry.pricing_intent in {'stock', 'list'}:
                    if actor.role not in pricing.MANAGERS: fail('price_override_forbidden','Only a manager can override counter-sale prices.',403)
                    proxy=SimpleNamespace(**p.existing.__dict__,unit_price=p.existing.charged_unit_price,list_price=p.existing.list_unit_price,inventory_item=p.inventory)
                    p.charged,p.reason=pricing.retained_price(proxy,action=entry.pricing_intent,requested=supplied,reason=entry.price_override_reason,actor=actor)
                    if p.charged<=0: fail('part_price_required','Counter-sale prices must be greater than zero.')
            else:
                key='counter:'+str(entry.inventory_id)
                new_inputs[key]=SimpleNamespace(inventory_id=entry.inventory_id,pricing_intent=entry.pricing_intent,unit_price=entry.charged_unit_price,price_override_reason=entry.price_override_reason)
                lines.append(PlannedPart(key,None,Decimal(entry.quantity),reserves=False,intent=entry.pricing_intent,reason=entry.price_override_reason))
    if len([p for p in lines if p.included])>100: fail('plan_too_large','Use no more than 100 resulting parts per command.')
    # Retained-only plans intentionally do not select or fingerprint live policy.
    if new_inputs:
        subject=order if order is not None else SimpleNamespace(tenant_id=actor.tenant_id,pricing_policy_snapshot=account_snapshot,pricing_matrix_revision_id=account.revision_id(account_snapshot),_pricing_counter=request.context.kind=='counter_sale')
        policy=await account.policy_for_saved(db,actor.tenant_id,subject,lock=lock)
    if lock and services:
        # All template mutations take the same tenant lock. Select policy before
        # locking these stable service rows, then lock inventory in sorted order.
        services = await load_services(db, actor.tenant_id, [s.id for s in services], lock=True)
    wanted={e.inventory_id for e in new_inputs.values()}
    wanted|={p.inventory.id for p in lines if p.inventory is not None}
    items=await pricing.inventory(db,actor.tenant_id,wanted,lock=lock,retained_ids=[p.inventory.id for p in lines if p.existing])
    for p in lines:
        if p.key in new_inputs:
            entry=new_inputs[p.key];p.inventory=items[entry.inventory_id]
            if p.inventory.deleted_at is not None: fail('part_not_found', 'One or more parts were not found.', 404)
            if kind=='counter_draft' and (p.inventory.is_placeholder or p.inventory.ets_retired_at): fail('part_not_found','This part is unavailable for counter sales.',404)
            p.price=resolve_price(p.inventory,policy,internal=bool(order and order.is_internal),actual_cost_known=not(p.inventory.is_placeholder and not p.inventory.cost),intent=entry.pricing_intent,
                requested=entry.unit_price,reason=entry.price_override_reason,actor_id=actor.id,can_override=actor.role in (pricing.MANAGERS if kind=='counter_draft' else pricing.EDITORS),quantity=p.quantity,counter=kind=='counter_draft')
            if order and order.is_internal: p.price.snapshot['policy_source']='internal'
            elif account_snapshot: p.price.snapshot['policy_source']=account_snapshot['parts']['source']
            else: p.price.snapshot['policy_source']='legacy'
        else: p.inventory=items[p.inventory.id]
    available={i:max(0,v.stock_quantity or 0) for i,v in items.items()}
    for p in lines:
        if p.existing is not None and kind!='counter_draft' and (p.disposition=='removed' or p.quantity!=p.existing.quantity):
            old_reserved=reservation(p.existing)
            if p.disposition=='removed': available[p.inventory.id]+=old_reserved
            elif math.ceil(p.quantity)<old_reserved: available[p.inventory.id]+=old_reserved-math.ceil(p.quantity)
    for p in lines:
        inv=p.inventory;reserved=getattr(p.existing,'stock_reserved_packages',None) if p.existing else 0
        need=max(0,math.ceil(p.quantity)-(reserved or 0)) if p.reserves else 0
        state='available'
        if p.existing is not None and p.disposition=='retained' and p.quantity==Decimal(str(p.existing.quantity)): need=0
        if not p.included: state='not_stocked'
        elif inv.is_placeholder: state='not_stocked'
        elif p.reserves and need>available[inv.id]:
            state='shortage'
            if p.disposition=='added' and p.source_component_id and kind=='service_apply': p.disposition='omitted';p.included=False
        if p.included and p.reserves: available[inv.id]=max(0,available[inv.id]-need)
        p.availability={'state':state,'requested_packages':math.ceil(p.quantity),'available_packages':max(0,inv.stock_quantity or 0),'reserved_packages':reserved,'included':p.included}
    await pricing.load_overlays(db, actor.tenant_id, [p.existing for p in lines if p.existing], 'parts_usage' if order is not None else 'counter_sale_line')
    response=await response_for(db,actor,request,order,sale,tenant,lines,services,policy,labor_inputs,mode,account_snapshot)
    return PricingPlan(request,order,sale,services,lines,response,policy,account_snapshot)


def _editable(order):
    from app.services import operation_execution
    return operation_execution.editable(order)


async def response_for(db,actor,request,order,sale,tenant,lines,services,policy,labor_inputs,mode,account_snapshot=None):
    kind=request.plan.kind
    legacy = kind == 'service_apply' and request.plan.attachment_path == 'fleet_legacy_service'
    if order is not None:
        labor=[SimpleNamespace(total_cost=li.total_cost) for li in order.labor_items if li.deleted_at is None]
        if kind in {'service_apply','pm_replace','fleet_create'}:
            source_ids=set() if legacy else {UUID(i['service_id']) for i in labor_inputs if i.get('service_id')}
            if kind=='pm_replace':
                source_ids|=set((await db.scalars(select(RepairOrderPMService.service_id).where(RepairOrderPMService.tenant_id==actor.tenant_id,RepairOrderPMService.repair_order_id==order.id))).all())
            labor=[SimpleNamespace(total_cost=li.total_cost) for li in order.labor_items if li.deleted_at is None and li.source_service_id not in source_ids]
            rate,_=account.labor_default(order,tenant,legacy_fleet=kind in {'pm_replace','fleet_create'} or legacy)
            if kind == 'service_apply' and not legacy:
                # The existing shop adapter recalculates other opted-in labor.
                # Include those exact generated hours/rates in preview and token.
                from app.services.price_build_service import PriceBuildService
                from app.db.models.labor import LaborLineType
                svc = PriceBuildService()
                labor = []
                for li in order.labor_items:
                    if li.deleted_at is not None or li.source_service_id in source_ids:
                        continue
                    total = li.total_cost
                    hours = li.hours
                    recalculated = False
                    if li.auto_recalc_enabled:
                        if li.source_service_id:
                            recalculated = True
                        elif li.line_type == LaborLineType.REPAIR_OPERATION and li.provider_operation_id:
                            estimate = await svc._get_operation_estimate(db, order, li.provider_operation_id, name=li.description)
                            generated = validate_labor_hours(estimate.estimated_hours)
                            hours = li.hours if li.execution_status == 'completed' else generated
                            recalculated = True
                    if recalculated:
                        total = (Decimal(str(hours)) * Decimal(str(li.hourly_rate))).quantize(Decimal('.01'))
                    labor.append(SimpleNamespace(total_cost=total))
                    labor_inputs.append({'retained_labor_id': str(li.id), 'hours': str(hours),
                                         'total_cost': str(total), 'recalculated': recalculated})
            for entry in labor_inputs:
                if not entry.get('retained_labor_id'):
                    parent=next((li for li in order.labor_items if str(li.id)==entry.get('parent_id')),None)
                    actual_rate=Decimal(str(parent.hourly_rate)) if parent else rate
                    entry['hourly_rate']=str(actual_rate)
                    labor.append(SimpleNamespace(total_cost=(Decimal(entry['hours'])*actual_rate).quantize(Decimal('.01'))))
        view=SimpleNamespace(parts_usage=[SimpleNamespace(total_price=line_total(p.unit_price,p.quantity)) for p in lines if p.included],labor_items=labor,labor_discount_amount=order.labor_discount_amount,order_discount_amount=order.order_discount_amount)
        totals=compute_canonical_order_totals(view)
        totals={'kind':'repair_order','parts_subtotal':cents(totals['parts_total']),'labor_subtotal':cents(totals['labor_total']),'labor_discount_amount':cents(order.labor_discount_amount or 0),'order_discount_amount':cents(order.order_discount_amount or 0),'repair_total':cents(totals['total_cost'])}
    else:
        from app.services.counter_sale_service import price_sale
        proxy=SimpleNamespace(tax_rate_snapshot=sale.tax_rate_snapshot if sale else Decimal(tenant.sales_tax_rate or 0))
        price_sale(proxy,[SimpleNamespace(id=p.existing.id if p.existing else uuid5(NAMESPACE_URL,p.key),quantity=int(p.quantity),unit_cost=p.cost,list_unit_price=p.default,charged_unit_price=p.unit_price) for p in lines if p.included])
        totals={'kind':'counter_sale',**{k:cents(getattr(proxy,k)) for k in ('list_subtotal','charged_subtotal','discount_total','tax_total','total')}}
    semantic=[];scope=[];output=[];private=[];warnings=[]
    for p in lines:
        inv=p.inventory;snap=p.snapshot
        identity={'line_key':p.key,'inventory_id':str(inv.id),'parts_usage_id':str(p.existing.id) if p.existing and order else None,'sale_line_id':str(p.existing.id) if p.existing and order is None else None,
          'source_service_id':str(p.source_service_id) if p.source_service_id else None,'source_line_id':str(p.source_line_id) if p.source_line_id else None,'source_component_id':str(p.source_component_id) if p.source_component_id else None,
          'disposition':p.disposition,'name':inv.name,'unit_type':inv.unit_type or 'each','quantity':format(p.quantity.normalize(), 'f')}
        entry={**identity,'availability':p.availability}
        if mode=='fleet': entry['pricing_version']=getattr(p.existing,'pricing_version',None) if p.existing else None
        if mode=='shop': entry['pricing']=safe_price(p.existing or p,can_override=actor.role in (pricing.MANAGERS if order is None else pricing.EDITORS) and (order is None or _editable(order)),snapshot=snap,price=p.unit_price,default=p.default,quantity=p.quantity,persisted=p.existing is not None)
        output.append(entry)
        bound={k:v for k,v in identity.items() if k not in {'name','unit_type','disposition'}}
        bound.update(disposition='added' if p.disposition=='omitted' else p.disposition,cost=str(p.cost),default=str(p.default),charged=str(p.unit_price),intent=p.intent,reason=p.reason,
                     original_quantity=str(p.existing.quantity) if p.existing else None,version=getattr(p.existing,'pricing_version',sale.version if sale else None),snapshot_id=snap.get('snapshot_id') if p.existing else None,
                     revision=str(getattr(p.existing,'pricing_matrix_revision_id',None)) if p.existing else str(p.price.revision_id))
        if not p.existing:
            bound['policy']={'generation':policy.generation,'revision':str(policy.revision_id),'inventory_version':inv.pricing_version,'cost':str(inv.cost),'catalog':str(inv.selling_price),'floor':str(inv.pricing_cost_floor),'minimum':str(inv.minimum_sale_price),'fixed':inv.fixed_sales_price}
        semantic.append(bound);scope.append([p.key,p.included])
        if p.price and p.price.warning: warnings.append({'code':p.price.warning,'message':'Catalog price is used for this part.','line_key':p.key,'inventory_id':str(inv.id)})
        if p.disposition=='omitted': warnings.append({'code':'service_part_stock_shortage','message':f'{inv.name} is excluded because recorded stock is insufficient.','line_key':p.key,'inventory_id':str(inv.id)})
        private.append({'line_key':p.key,'snapshot_id':snap.get('snapshot_id'),**{k:snap.get(k) for k in ('actual_unit_cost','actual_cost_known','pricing_cost_floor','pricing_basis','minimum_sale_price','effective_minimum','fixed_catalog_price','catalog_unit_price','matrix')}, **({'actual_unit_cost': str(p.cost) if p.cost is not None else None, 'actual_cost_known': p.cost is not None} if not snap else {}),'override':getattr(p.existing, '_pricing_override', snap.get('initial_override')) if p.existing else snap.get('initial_override')})
    normalized=request.model_dump();normalized.pop('include_management_details',None);normalized['pricing_presentation']=mode
    def canonical(v):
        if isinstance(v, Decimal): return format(v.normalize(),'f')
        if isinstance(v, UUID): return str(v)
        if isinstance(v, list): return [canonical(x) for x in v]
        if isinstance(v, dict): return {k:canonical(x) for k,x in v.items()}
        return v
    normalized=canonical(normalized)
    binding={'tenant':str(actor.tenant_id),'actor':str(actor.id),'request':normalized,'lines':semantic,'labor':labor_inputs,'totals':totals,
             'order':{'id':str(order.id),'customer':str(order.customer_id),'internal':bool(order.is_internal),'status':str(order.status),'lock':str(order.pricing_locked_at),'discounts':[str(order.labor_discount_amount),str(order.order_discount_amount)]} if order else None,
             'sale_version':sale.version if sale else None,
             'labor_total': totals.get('labor_subtotal'),
             'tax_rate': str(sale.tax_rate_snapshot if sale else tenant.sales_tax_rate) if order is None else None}
    if any(not p.existing for p in lines) or kind in {'fleet_create','counter_draft'}:
        binding['account_policy']=account.stable_policy(account_snapshot)
        if order and order.id and account_snapshot: binding['order_policy_snapshot_id']=account_snapshot['snapshot_id']
    # Totals vary with omitted bundle scope; separate that effect from price
    # dependencies, while keeping canonical labor/discount inputs bound above.
    binding.pop('totals')
    omitted=[p.key for p in lines if p.disposition=='omitted'];shortage=any(p.included and p.availability['state']=='shortage' for p in lines)
    required=bool(omitted or shortage or any(not p.existing and (p.snapshot.get('managed') or p.intent!='default') for p in lines))
    response={'schema_version':1,'plan_kind':kind,'pricing_preview_fingerprint':'v1.'+pricing.signed_digest(binding)+'.'+pricing.signed_digest(scope,'scope'),
      'confirmation_required':required,'currency':'USD','expected_sale_version':sale.version if sale else None,'availability':{'state':'partial_bundle' if omitted else ('requires_stock_acknowledgement' if shortage else 'ready'),'omitted_line_keys':omitted},'warnings':warnings,'projection':mode,'lines':output,
      'totals':{'kind':'repair_order','repair_total':totals['repair_total']} if mode=='fleet' else totals}
    if mode=='shop':
        response['parts_pricing_fingerprint']=pricing.parts_fingerprint(order) if order and order.id else None
        response['management']={'default_generation':policy.generation if any(not p.existing for p in lines) else None,'lines':private} if request.include_management_details else None
    return response


async def remove_usage(db,actor,order,row,item):
    """Existing physical deletion, with actual reservation and durable evidence."""
    from app.db.models.parts_operations import CoreObligation,VendorReturnLine
    from app.services.parts_operations_service import apply_inventory_movement
    cores=list((await db.scalars(select(CoreObligation).where(CoreObligation.tenant_id==order.tenant_id,CoreObligation.parts_usage_id==row.id).with_for_update())).all())
    if any(c.status=='on_hand' and c.deleted_at is None for c in cores): fail('core_requires_review','Return or waive the recovered core before removing this part.',409)
    if cores and await db.scalar(select(VendorReturnLine.id).where(VendorReturnLine.tenant_id==order.tenant_id,VendorReturnLine.core_obligation_id.in_([c.id for c in cores])).limit(1)):
        fail('core_requires_review','Void the vendor return before removing this part.',409)
    reserved=reservation(row)
    if actor: await pricing.audit_usage(db,actor,order,row,'part.removed',before=pricing.usage_values(row),old_version=row.pricing_version or 0)
    for core in cores: await db.delete(core)
    if reserved:
        await apply_inventory_movement(db,item=item,quantity_delta=reserved,movement_type='repair_release',actor=actor,
            source_type='repair_order',source_id=order.id,destination_type='parts_usage',destination_id=row.id,reason_code='bundled_service_part_release')
    await db.delete(row)


async def sync_expected_core_quantity(db, order, row, quantity):
    """Keep unrecovered custody quantity aligned without rewriting settled cores."""
    from app.db.models.parts_operations import CoreObligation, VendorReturnLine
    cores = list((await db.scalars(select(CoreObligation).where(
        CoreObligation.tenant_id == order.tenant_id,
        CoreObligation.parts_usage_id == row.id,
        CoreObligation.deleted_at.is_(None),
    ).with_for_update())).all())
    needed = math.ceil(quantity)
    changed = [core for core in cores if core.quantity != needed]
    if not changed:
        return
    if len(cores) != 1 or any(core.status != 'expected' for core in changed):
        fail('core_requires_review', 'Review the recovered or settled core before changing this part quantity.', 409)
    if await db.scalar(select(VendorReturnLine.id).where(
        VendorReturnLine.tenant_id == order.tenant_id,
        VendorReturnLine.core_obligation_id.in_([core.id for core in changed]),
    ).limit(1)):
        fail('core_requires_review', 'Review the vendor return before changing this part quantity.', 409)
    for core in changed:
        core.quantity = needed
        core.version += 1


async def apply_plan_parts(db,actor,order,plan,parent_ids=None,*,components_only=False,include_keys=None):
    """Apply only planned deltas. Caller owns the single transaction/commit."""
    from app.db.models.parts_operations import CoreObligation
    from app.services.parts_operations_service import apply_inventory_movement
    parent_ids=parent_ids or {}
    selected=[p for p in plan.lines if (not components_only or p.source_service_id is not None) and (include_keys is None or p.key in include_keys)]
    for p in selected:
        if p.disposition=='removed': await remove_usage(db,actor,order,p.existing,p.inventory)
    for p in selected:
        if not p.included: continue
        inv=p.inventory
        if p.existing:
            row=p.existing
            if row.quantity==p.quantity: continue
            before=pricing.usage_values(row);old=row.pricing_version or 0
            previous=reservation(row)
            await sync_expected_core_quantity(db, order, row, p.quantity)
            needed=math.ceil(p.quantity) if p.reserves else 0
            delta=needed-previous
            if delta>max(0,inv.stock_quantity or 0): fail('insufficient_stock','There is not enough recorded stock for this bundle change.',409)
            if delta:
                await apply_inventory_movement(db,item=inv,quantity_delta=-delta,movement_type='repair_reservation' if delta>0 else 'repair_release',actor=actor,
                    source_type='repair_order',source_id=order.id,destination_type='parts_usage',destination_id=row.id,reason_code='bundled_service_quantity_changed')
            row.quantity=p.quantity;row.stock_reserved_packages=needed;row.total_price=line_total(row.unit_price,row.quantity);row.pricing_version=old+1
            if actor: await pricing.audit_usage(db,actor,order,row,'part.quantity_changed',before=before,old_version=old)
        else:
            from uuid import uuid4
            needed=math.ceil(p.quantity) if p.reserves else 0
            if needed>max(0,inv.stock_quantity or 0): fail('bundle_availability_changed','Bundle stock changed. Review the updated work.',409,preview=plan.safe_response())
            row=PartsUsage(id=uuid4(),tenant_id=order.tenant_id,repair_order_id=order.id,inventory_id=inv.id,
                quantity=p.quantity,unit_cost=p.price.actual_cost,unit_price=p.price.charged,list_price=p.price.default,total_price=line_total(p.price.charged,p.quantity),
                pricing_snapshot=p.price.snapshot,pricing_matrix_revision_id=p.price.revision_id,source_service_id=p.source_service_id,
                source_line_id=parent_ids.get(p.source_service_id,p.source_line_id),source_component_id=p.source_component_id,
                stock_reserved_packages=needed,stock_shortage_override=False)
            db.add(row);await db.flush()
            if p.reserves and Decimal(inv.core_charge or 0)>0:
                db.add(CoreObligation(tenant_id=order.tenant_id,parts_usage_id=row.id,inventory_id=inv.id,supplier_id=inv.preferred_supplier_id,quantity=needed,unit_core_value_snapshot=inv.core_charge,status='expected'))
            if needed:
                await apply_inventory_movement(db,item=inv,quantity_delta=-needed,movement_type='repair_reservation',actor=actor,source_type='repair_order',source_id=order.id,destination_type='parts_usage',destination_id=row.id,reason_code='bundled_service_part_reservation')
            if actor: await pricing.audit_usage(db,actor,order,row,'part.attached')
    await db.flush()
