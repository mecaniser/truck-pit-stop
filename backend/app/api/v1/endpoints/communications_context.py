"""Explicit staff CRM associations; never changes a conversation's transport identity."""
from __future__ import annotations
import hashlib
import json
from typing import Annotated, Literal
from uuid import UUID
from fastapi import APIRouter, Depends, Header, Query, HTTPException, Body
from pydantic import BaseModel, ConfigDict, Field, EmailStr, field_validator, model_validator
from sqlalchemy import select, or_, and_, func
from app.core.dependencies import get_db, get_current_active_user
from app.core.phone import normalize_phone
from app.db.models.user import User, UserRole
from app.db.models.customer import Customer
from app.db.models.contact import Contact
from app.db.models.vehicle import Vehicle
from app.db.models.repair_order import RepairOrder, RepairOrderStatus
from app.db.models.conversation_contact import ConversationContactLink as Link, ContactRepairLink as RepairLink, ConversationContextMutation as Mutation
from app.schemas.customer import CustomerCreate
from app.services import communications_service as svc

router = APIRouter()
PREFIX = '/conversations/{conversation_id}'
ROLES = {UserRole.GARAGE_OWNER, UserRole.GARAGE_ADMIN, UserRole.RECEPTIONIST}
HISTORY = [RepairOrderStatus.COMPLETED, RepairOrderStatus.INVOICED, RepairOrderStatus.PAID, RepairOrderStatus.CANCELLED]


class Strict(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)


class Person(Strict):
    first_name: str = Field('', max_length=100)
    last_name: str = Field('', max_length=100)
    role: str | None = Field(None, max_length=100)
    email: EmailStr | None = Field(None, max_length=255)
    phone: str | None = Field(None, max_length=20)

    @field_validator('phone')
    @classmethod
    def phone_valid(cls, value):
        if not value:
            return None
        if any(c not in '+0123456789 ().-' for c in value) or not 7 <= len(normalize_phone(value) or '') <= 15:
            raise ValueError('Enter a valid phone number')
        return normalize_phone(value)

    @model_validator(mode='after')
    def named(self):
        if not (self.first_name or self.last_name):
            raise ValueError('A person name is required')
        return self


class NewCustomer(Strict):
    company_name: str = Field(min_length=1, max_length=255)
    first_name: str = Field(max_length=100)
    last_name: str = Field(max_length=100)
    email: EmailStr = Field(max_length=255)
    phone: str | None = Field(None, max_length=20)
    _phone = field_validator('phone')(Person.phone_valid.__func__)
    _named = model_validator(mode='after')(Person.named)


class LinkRequest(Strict):
    action: Literal['link']
    expected_version: int = Field(ge=0)
    customer_id: UUID
    contact_id: UUID


class ContactRequest(Strict):
    action: Literal['create_contact']
    expected_version: int = Field(ge=0)
    customer_id: UUID
    contact: Person


class CustomerRequest(Strict):
    action: Literal['create_customer']
    expected_version: int = Field(ge=0)
    customer: NewCustomer
    contact: Person


class RepairRequest(Strict):
    expected_version: int = Field(ge=1)


async def access(db, user, conversation_id, lock=False):
    await svc.authorize(db, user)
    if user.role not in ROLES:
        svc.fail('forbidden', 'Customer access is required.', 403)
    return await svc.thread_for(db, user.tenant_id, conversation_id, lock=lock)


async def visible(db, model, tenant, identity):
    row = await db.scalar(select(model).where(model.id == identity, model.tenant_id == tenant, model.deleted_at.is_(None)))
    if not row:
        svc.fail('not_found', 'Record not found.', 404)
    return row


def customer_json(c):
    return dict(id=str(c.id), company_name=c.company_name, display_name=f'{c.first_name} {c.last_name}'.strip())


def contact_json(c):
    return dict(id=str(c.id), **{k: getattr(c, k) for k in ('first_name','last_name','role','phone','email')})


def vehicle_json(v):
    return dict(id=str(v.id), **{k: getattr(v, k) for k in ('unit_number','make','model','year')})


async def context(db, thread):
    link = await db.scalar(select(Link).where(Link.tenant_id == thread.tenant_id, Link.thread_id == thread.id))
    cid = link.customer_id if link else thread.customer_id
    c = await db.scalar(select(Customer).where(Customer.id == cid, Customer.tenant_id == thread.tenant_id, Customer.deleted_at.is_(None))) if cid else None
    p = await db.scalar(select(Contact).where(Contact.id == link.contact_id, Contact.customer_id == cid, Contact.tenant_id == thread.tenant_id, Contact.deleted_at.is_(None))) if link and c else None
    unavailable = bool(link and (link.deleted_at is not None or not c or not p or (thread.customer_id and thread.customer_id != cid)))
    if unavailable:
        c = p = None
    result = dict(version=link.version if link else 0, link_state='unavailable' if unavailable else ('linked' if p else 'unlinked'), can_manage=True, customer=customer_json(c) if c else None, contact=contact_json(p) if p else None, default_scope='contact', fleet_available=bool(c))
    return result, link, c, p


@router.get(PREFIX + '/customer-context')
async def get_context(conversation_id: UUID, db=Depends(get_db), user=Depends(get_current_active_user)):
    return (await context(db, await access(db, user, conversation_id)))[0]


@router.get(PREFIX + '/customer-options')
async def customers(conversation_id: UUID, q: str = Query('', max_length=200), limit: int = Query(20, ge=1, le=50), db=Depends(get_db), user=Depends(get_current_active_user)):
    thread = await access(db, user, conversation_id)
    query = select(Customer).where(Customer.tenant_id == user.tenant_id, Customer.deleted_at.is_(None))
    if thread.customer_id:
        query = query.where(Customer.id == thread.customer_id)
    if q.strip():
        term = '%' + q.replace('\\','\\\\').replace('%','\\%').replace('_','\\_').strip() + '%'
        query = query.where(or_(*(getattr(Customer, field).ilike(term, escape='\\') for field in ('company_name','first_name','last_name'))))
    return dict(items=[customer_json(c) for c in (await db.scalars(query.order_by(Customer.company_name, Customer.id).limit(limit))).all()])


@router.get(PREFIX + '/customer-options/{customer_id}/contacts')
async def contacts(conversation_id: UUID, customer_id: UUID, db=Depends(get_db), user=Depends(get_current_active_user)):
    thread = await access(db, user, conversation_id)
    await customer_for(db, thread, customer_id)
    rows = (await db.scalars(select(Contact).where(Contact.tenant_id == user.tenant_id, Contact.customer_id == customer_id, Contact.deleted_at.is_(None)).order_by(Contact.first_name, Contact.id).limit(101))).all()
    return dict(items=[contact_json(c) for c in rows[:100]], has_more=len(rows)>100)


async def customer_for(db, thread, customer_id):
    if thread.customer_id and thread.customer_id != customer_id:
        svc.fail('not_found', 'Customer not found.', 404)
    return await visible(db, Customer, thread.tenant_id, customer_id)


async def mutation(db, user, thread, key, operation, payload):
    # Actor lock serializes idempotency across different conversations, thread lock
    # serializes identity version changes. All callers acquire these in this order.
    await db.scalar(select(User).where(User.id == user.id, User.tenant_id == user.tenant_id).with_for_update())
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    old = await db.scalar(select(Mutation).where(Mutation.tenant_id == user.tenant_id, Mutation.actor_id == user.id, Mutation.idempotency_key == key))
    if old and (old.operation != operation or old.payload_hash != digest or old.thread_id != thread.id):
        svc.fail('idempotency_conflict', 'This request key was already used.', 409)
    return old, digest


@router.put(PREFIX + '/customer-context')
async def put_context(conversation_id: UUID, body: Annotated[LinkRequest | ContactRequest | CustomerRequest, Body(discriminator='action')], idempotency_key: UUID = Header(), db=Depends(get_db), user=Depends(get_current_active_user)):
    thread = await access(db, user, conversation_id)
    old, digest = await mutation(db, user, thread, idempotency_key, 'customer-context', body.model_dump(mode='json'))
    thread = await access(db, user, conversation_id, lock=True)
    state, link, _, _ = await context(db, thread)
    c = await customer_for(db, thread, body.customer_id) if body.action != 'create_customer' else None
    p = await visible(db, Contact, user.tenant_id, body.contact_id) if body.action == 'link' else None
    if p and p.customer_id != c.id:
        svc.fail('not_found', 'Contact not found.', 404)
    if old:
        # Replay requires the committed targets still be visible, not merely the key.
        await customer_for(db, thread, UUID(old.result['customer']['id']))
        previous_person = await visible(db, Contact, user.tenant_id, UUID(old.result['contact']['id']))
        if str(previous_person.customer_id) != old.result['customer']['id']:
            svc.fail('not_found', 'Contact not found.', 404)
        return old.result
    if state['version'] != body.expected_version:
        svc.fail('version_conflict', 'Customer link changed. Refresh and try again.', 409)
    if body.action == 'create_customer':
        if thread.thread_kind != 'inquiry':
            svc.fail('invalid_action', 'This conversation already has a customer.', 409)
        from app.db.models.tenant import Tenant
        # Serialize duplicate detection across different actors, keys and threads.
        await db.scalar(select(Tenant).where(Tenant.id == user.tenant_id).with_for_update())
        data = CustomerCreate(**body.customer.model_dump(), no_vehicle=True)
        # Same invariant as ordinary customer creation, including deleted addresses.
        if await db.scalar(select(Customer.id).where(Customer.tenant_id == user.tenant_id, Customer.email == data.email)):
            svc.fail('duplicate_customer', 'A customer with this email already exists. Link it instead.', 409)
        c = Customer(tenant_id=user.tenant_id, **data.model_dump(exclude={'no_vehicle','initial_vehicle'}))
        db.add(c)
        await db.flush()
    if body.action != 'link':
        p = Contact(tenant_id=user.tenant_id, customer_id=c.id, is_primary=False, **body.contact.model_dump())
        db.add(p)
        await db.flush()
    previous = dict(customer_id=str(link.customer_id), contact_id=str(link.contact_id)) if link else None
    if not link:
        link = Link(tenant_id=user.tenant_id, thread_id=thread.id, customer_id=c.id, contact_id=p.id, actor_id=user.id, version=1)
        db.add(link)
    else:
        link.customer_id, link.contact_id, link.actor_id = c.id, p.id, user.id
        link.version += 1
    await db.flush()
    result = (await context(db, thread))[0]
    db.add(Mutation(tenant_id=user.tenant_id, actor_id=user.id, thread_id=thread.id, idempotency_key=idempotency_key, operation='customer-context', payload_hash=digest, result=result, previous_target=previous))
    await db.commit()
    return result


def repairs_query(tenant, customer):
    return select(RepairOrder, Vehicle).join(Vehicle, Vehicle.id == RepairOrder.vehicle_id).where(RepairOrder.tenant_id == tenant, RepairOrder.customer_id == customer, RepairOrder.deleted_at.is_(None), Vehicle.tenant_id == tenant, Vehicle.customer_id == customer, Vehicle.deleted_at.is_(None))


@router.get(PREFIX + '/repairs')
async def repairs(conversation_id: UUID, scope: Literal['contact','fleet']='contact', status: Literal['active','history','all']='active', cursor: str | None=Query(None, max_length=4096), limit: int=Query(20, ge=1, le=50), q: str=Query('', max_length=200), db=Depends(get_db), user=Depends(get_current_active_user)):
    thread = await access(db, user, conversation_id)
    state, _, c, p = await context(db, thread)
    binding = json.dumps([str(user.tenant_id),str(thread.id),state['version'],scope,status,q,'repairs'])
    try:
        decoded = svc.cursor_decode(cursor, binding)
    except HTTPException:
        svc.fail('invalid_cursor', 'Invalid pagination cursor.', 422)
    if not c or (scope == 'contact' and not p):
        return dict(items=[],has_more=False,next_cursor=None)
    query = repairs_query(user.tenant_id, c.id)
    linked = select(RepairLink.id).where(RepairLink.tenant_id == user.tenant_id, RepairLink.contact_id == (p.id if p else None), RepairLink.repair_order_id == RepairOrder.id, RepairLink.deleted_at.is_(None)).exists()
    query = query.add_columns(linked.label('linked'))
    if scope == 'contact':
        query = query.where(linked)
    if status != 'all':
        query = query.where(RepairOrder.status.in_(HISTORY) if status == 'history' else RepairOrder.status.not_in(HISTORY))
    if q:
        term = '%' + q.replace('\\','\\\\').replace('%','\\%').replace('_','\\_') + '%'
        query = query.where(or_(RepairOrder.order_number.ilike(term,escape='\\'), Vehicle.unit_number.ilike(term,escape='\\')))
    if decoded:
        dt, identity = decoded
        query = query.where(or_(RepairOrder.created_at < dt, and_(RepairOrder.created_at == dt, RepairOrder.id < identity)))
    rows = (await db.execute(query.order_by(RepairOrder.created_at.desc(), RepairOrder.id.desc()).limit(limit+1))).all()
    more = len(rows)>limit
    rows = rows[:limit]
    return dict(items=[dict(id=str(r.id),order_number=r.order_number,status=r.status.value,created_at=r.created_at.isoformat(),description=(r.description or '')[:500],vehicle=vehicle_json(v),linked_to_contact=bool(linked)) for r,v,linked in rows],has_more=more,next_cursor=svc.cursor_encode(binding, rows[-1][0].created_at, rows[-1][0].id) if rows and more else None)


@router.put(PREFIX + '/repairs/{repair_order_id}/contact-link')
async def link_repair(conversation_id: UUID, repair_order_id: UUID, body: RepairRequest, idempotency_key: UUID=Header(), db=Depends(get_db), user=Depends(get_current_active_user)):
    thread = await access(db, user, conversation_id)
    operation = 'repair:' + str(repair_order_id)
    old, digest = await mutation(db,user,thread,idempotency_key,operation,body.model_dump())
    thread = await access(db,user,conversation_id,lock=True)
    state, _, c, p = await context(db,thread)
    if not c or not p:
        svc.fail('contact_required','Link a contact first.',409)
    if not (await db.execute(repairs_query(user.tenant_id,c.id).where(RepairOrder.id == repair_order_id))).first():
        svc.fail('not_found','Repair not found.',404)
    if old:
        if old.previous_target != dict(contact_id=str(p.id)):
            svc.fail('version_conflict','Customer link changed. Refresh and try again.',409)
        return old.result
    if state['version'] != body.expected_version:
        svc.fail('version_conflict','Customer link changed. Refresh and try again.',409)
    # Different conversations can share a contact; serialize their association writes.
    await db.scalar(select(Contact).where(Contact.id == p.id, Contact.tenant_id == user.tenant_id).with_for_update())
    exists = await db.scalar(select(RepairLink).where(RepairLink.tenant_id == user.tenant_id, RepairLink.contact_id == p.id, RepairLink.repair_order_id == repair_order_id))
    result = dict(repair_order_id=str(repair_order_id),linked=True)
    if not exists:
        db.add(RepairLink(tenant_id=user.tenant_id,contact_id=p.id,repair_order_id=repair_order_id,actor_id=user.id))
    db.add(Mutation(tenant_id=user.tenant_id,actor_id=user.id,thread_id=thread.id,idempotency_key=idempotency_key,operation=operation,payload_hash=digest,result=result,previous_target=dict(contact_id=str(p.id))))
    await db.commit()
    return result


@router.get(PREFIX + '/vehicles')
async def vehicles(conversation_id: UUID, scope: Literal['contact','fleet']='contact', cursor: str | None=Query(None, max_length=4096), limit: int=Query(20,ge=1,le=50), db=Depends(get_db), user=Depends(get_current_active_user)):
    import base64
    thread = await access(db,user,conversation_id)
    state, _, c, p = await context(db,thread)
    binding = [str(user.tenant_id),str(thread.id),state['version'],scope,'vehicles']
    after = None
    if cursor:
        try:
            actual, unit, identity = json.loads(base64.urlsafe_b64decode(cursor))
            if actual != binding or not isinstance(unit,str) or len(unit)>255:
                raise ValueError()
            after = (unit, UUID(identity))
        except Exception:
            svc.fail('invalid_cursor','Invalid pagination cursor.',422)
    if not c or (scope == 'contact' and not p):
        return dict(items=[],has_more=False,next_cursor=None)
    query = select(Vehicle).where(Vehicle.tenant_id == user.tenant_id,Vehicle.customer_id == c.id,Vehicle.deleted_at.is_(None))
    if scope == 'contact':
        query = query.where(select(RepairOrder.id).join(RepairLink,RepairLink.repair_order_id == RepairOrder.id).where(RepairOrder.tenant_id == user.tenant_id,RepairOrder.customer_id == c.id,RepairOrder.vehicle_id == Vehicle.id,RepairOrder.deleted_at.is_(None),RepairLink.tenant_id == user.tenant_id,RepairLink.contact_id == p.id,RepairLink.deleted_at.is_(None)).exists())
    ordering = func.coalesce(Vehicle.unit_number,'')
    if after:
        query = query.where(or_(ordering>after[0],and_(ordering==after[0],Vehicle.id>after[1])))
    rows = (await db.scalars(query.order_by(ordering,Vehicle.id).limit(limit+1))).all()
    more = len(rows)>limit
    rows = rows[:limit]
    next_cursor = base64.urlsafe_b64encode(json.dumps([binding,rows[-1].unit_number or '',str(rows[-1].id)]).encode()).decode() if more and rows else None
    return dict(items=[vehicle_json(v) for v in rows],has_more=more,next_cursor=next_cursor)
