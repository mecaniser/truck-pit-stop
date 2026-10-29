"""PostgreSQL CRM association acceptance; fixtures roll back, providers never called."""
import os
from uuid import uuid4
from datetime import datetime, timezone
import pytest
import pytest_asyncio
from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from app.api.v1.endpoints import communications_context as api
from app.db.models.tenant import Tenant
from app.db.models.user import User, UserRole
from app.db.models.customer import Customer
from app.db.models.contact import Contact
from app.db.models.message_thread import MessageThread
from app.db.models.vehicle import Vehicle
from app.db.models.repair_order import RepairOrder, RepairOrderStatus
from app.db.models.conversation_contact import ConversationContactLink, ContactRepairLink, ConversationContextMutation

isolated_postgres = pytest.mark.skipif(os.getenv('COMMUNICATIONS_ISOLATED_LOCAL') != '1',reason='dedicated synthetic PostgreSQL required')


@pytest_asyncio.fixture
async def data():
    if os.getenv('COMMUNICATIONS_ISOLATED_LOCAL') != '1':
        pytest.skip('dedicated synthetic PostgreSQL required')
    from app.db.session import engine
    async with engine.connect() as conn:
        outer = await conn.begin()
        async with AsyncSession(bind=conn,expire_on_commit=False,join_transaction_mode='create_savepoint') as db:
            tenant=Tenant(name='Context fixture',slug='context-'+uuid4().hex,messaging_enabled=True)
            other=Tenant(name='Foreign fixture',slug='foreign-'+uuid4().hex,messaging_enabled=True)
            db.add_all([tenant,other]); await db.flush()
            user=User(tenant_id=tenant.id,email=uuid4().hex+'@example.test',first_name='Alex',last_name='Staff',hashed_password='disabled',role=UserRole.GARAGE_OWNER,is_active=True)
            customer=Customer(tenant_id=tenant.id,company_name='Fleet A',first_name='Fleet',last_name='Owner',email=uuid4().hex+'@example.test')
            foreign=Customer(tenant_id=other.id,company_name='Foreign',first_name='Other',last_name='Owner',email=uuid4().hex+'@example.test')
            db.add_all([user,customer,foreign]);await db.flush()
            person=Contact(tenant_id=tenant.id,customer_id=customer.id,first_name='Driver',is_primary=False)
            thread=MessageThread(tenant_id=tenant.id,customer_id=customer.id)
            v1=Vehicle(tenant_id=tenant.id,customer_id=customer.id,make='Example',model='Truck',unit_number='A1')
            v2=Vehicle(tenant_id=tenant.id,customer_id=customer.id,make='Example',model='Truck',unit_number='A2')
            db.add_all([person,thread,v1,v2]);await db.flush()
            orders=[RepairOrder(tenant_id=tenant.id,customer_id=customer.id,vehicle_id=v.id,order_number=uuid4().hex,status=status,description='Public repair',shop_notes='Private secret') for v,status in [(v1,RepairOrderStatus.IN_PROGRESS),(v1,RepairOrderStatus.COMPLETED),(v2,RepairOrderStatus.CANCELLED)]]
            db.add_all(orders);await db.commit()
            yield db,user,thread,customer,person,orders,foreign
        await outer.rollback()
    await engine.dispose()


async def link(data,key=None):
    db,user,thread,customer,person,*_=data
    body=api.LinkRequest(action='link',expected_version=0,customer_id=customer.id,contact_id=person.id)
    return await api.put_context(thread.id,body,key or uuid4(),db,user)


@pytest.mark.asyncio
async def test_read_is_pure_and_explicit_link_preserves_transport(data):
    db,user,thread,customer,person,*_=data
    state=await api.get_context(thread.id,db,user)
    assert state['link_state']=='unlinked' and state['customer']['id']==str(customer.id)
    assert await db.scalar(select(func.count()).select_from(ConversationContactLink).where(ConversationContactLink.tenant_id==user.tenant_id))==0
    before=(thread.customer_id,thread.thread_kind,thread.customer_phone,thread.inquiry_binding_id)
    key=uuid4();result=await link(data,key)
    assert result['contact']['id']==str(person.id) and result['version']==1
    assert await link(data,key)==result
    assert await db.scalar(select(func.count()).select_from(ConversationContactLink).where(ConversationContactLink.tenant_id==user.tenant_id))==1
    assert (thread.customer_id,thread.thread_kind,thread.customer_phone,thread.inquiry_binding_id)==before
    assert person.is_primary is False
    with pytest.raises(HTTPException) as error:
        await link(data)
    assert error.value.detail['code']=='version_conflict'


@pytest.mark.asyncio
async def test_contact_fleet_separation_and_pagination(data):
    db,user,thread,customer,person,orders,_=data
    await link(data)
    empty=await api.repairs(thread.id,'contact','all',None,20,'',db,user)
    assert empty['items']==[]
    for order in orders[:2]:
        await api.link_repair(thread.id,order.id,api.RepairRequest(expected_version=1),uuid4(),db,user)
    active=await api.repairs(thread.id,'contact','active',None,20,'',db,user)
    history=await api.repairs(thread.id,'contact','history',None,20,'',db,user)
    assert [r['id'] for r in active['items']]==[str(orders[0].id)]
    assert [r['id'] for r in history['items']]==[str(orders[1].id)]
    fleet=await api.repairs(thread.id,'fleet','all',None,1,'',db,user)
    assert fleet['has_more']
    page2=await api.repairs(thread.id,'fleet','all',fleet['next_cursor'],20,'',db,user)
    assert len(page2['items'])==2
    assert len({r['id'] for r in fleet['items']+page2['items']})==3
    assert 'Private secret' not in str(fleet)+str(page2)
    with pytest.raises(HTTPException) as err:
        await api.repairs(thread.id,'contact','all',fleet['next_cursor'],20,'',db,user)
    assert err.value.status_code==422
    vehicles=await api.vehicles(thread.id,'contact',None,20,db,user)
    assert len(vehicles['items'])==1
    first=await api.vehicles(thread.id,'fleet',None,1,db,user)
    second=await api.vehicles(thread.id,'fleet',first['next_cursor'],1,db,user)
    assert len(first['items'])==len(second['items'])==1 and not second['has_more']


@pytest.mark.asyncio
async def test_foreign_mismatch_and_deleted_records(data):
    db,user,thread,customer,person,orders,foreign=data
    with pytest.raises(HTTPException) as err:
        await api.contacts(thread.id,foreign.id,db,user)
    assert err.value.status_code==404
    await link(data)
    person.deleted_at=datetime.now(timezone.utc);await db.flush()
    assert (await api.get_context(thread.id,db,user))['link_state']=='unavailable'
    assert (await api.repairs(thread.id,'fleet','all',None,20,'',db,user))['items']==[]


@pytest.mark.asyncio
async def test_disallowed_role(data):
    db,user,thread,*_=data
    user.role=UserRole.MECHANIC
    with pytest.raises(HTTPException) as err:
        await api.get_context(thread.id,db,user)
    assert err.value.status_code==403


@pytest.mark.asyncio
async def test_idempotency_payload_conflict_and_repair_no_duplicate(data):
    db,user,thread,customer,person,orders,_=data
    key=uuid4();await link(data,key)
    body=api.LinkRequest(action='link',expected_version=1,customer_id=customer.id,contact_id=person.id)
    with pytest.raises(HTTPException) as err:
        await api.put_context(thread.id,body,key,db,user)
    assert err.value.detail['code']=='idempotency_conflict'
    rkey=uuid4();request=api.RepairRequest(expected_version=1)
    result=await api.link_repair(thread.id,orders[0].id,request,rkey,db,user)
    assert await api.link_repair(thread.id,orders[0].id,request,rkey,db,user)==result
    await api.link_repair(thread.id,orders[0].id,request,uuid4(),db,user)
    assert await db.scalar(select(func.count()).select_from(ContactRepairLink).where(ContactRepairLink.tenant_id==user.tenant_id))==1


@pytest.mark.parametrize('payload',[
    dict(first_name='',last_name=''),dict(first_name='A',phone='garbage'),
    dict(first_name='A',email='invalid'),dict(first_name='A',is_primary=True),dict(first_name='A'*101)])
def test_contact_validation(payload):
    with pytest.raises(ValidationError):
        api.Person(**payload)


@pytest.mark.asyncio
async def test_create_contact_is_atomic_replay_nonprimary(data):
    db,user,thread,customer,*_=data
    before=await db.scalar(select(func.count()).select_from(Contact).where(Contact.tenant_id==user.tenant_id))
    body=api.ContactRequest(action='create_contact',expected_version=0,customer_id=customer.id,contact=api.Person(first_name='New',last_name='Driver',phone='(500) 555-1234'))
    key=uuid4()
    result=await api.put_context(thread.id,body,key,db,user)
    assert await api.put_context(thread.id,body,key,db,user)==result
    created=await db.get(Contact,result['contact']['id'])
    assert created.is_primary is False and created.phone=='5005551234'
    assert await db.scalar(select(func.count()).select_from(Contact).where(Contact.tenant_id==user.tenant_id))==before+1
    with pytest.raises(HTTPException):
        await api.put_context(thread.id,body,uuid4(),db,user)
    assert await db.scalar(select(func.count()).select_from(Contact).where(Contact.tenant_id==user.tenant_id))==before+1


@pytest.mark.asyncio
async def test_mismatched_contact_and_repair(data):
    db,user,thread,customer,person,orders,_=data
    second=Customer(tenant_id=user.tenant_id,company_name='B',first_name='B',last_name='Owner',email=uuid4().hex+'@example.test')
    db.add(second);await db.flush()
    stranger=Contact(tenant_id=user.tenant_id,customer_id=second.id,first_name='Other')
    db.add(stranger);await db.flush()
    with pytest.raises(HTTPException) as err:
        await api.put_context(thread.id,api.LinkRequest(action='link',expected_version=0,customer_id=customer.id,contact_id=stranger.id),uuid4(),db,user)
    assert err.value.status_code==404
    await link(data)
    orders[0].customer_id=second.id;await db.flush()
    with pytest.raises(HTTPException) as err:
        await api.link_repair(thread.id,orders[0].id,api.RepairRequest(expected_version=1),uuid4(),db,user)
    assert err.value.status_code==404


async def inquiry(db, tenant_id):
    from app.db.models.callrail import CallRailNumberBinding, CallRailConversation
    binding=CallRailNumberBinding(tenant_id=tenant_id,account_id=uuid4().hex,company_id='synthetic',tracker_id='synthetic',sender_phone='+15005550001',credential_ref='disabled',signing_secret_ref='disabled')
    db.add(binding);await db.flush()
    thread=MessageThread(tenant_id=tenant_id,thread_kind='inquiry',customer_id=None,customer_phone='+15005550002',inquiry_binding_id=binding.id)
    db.add(thread);await db.flush()
    mapping=CallRailConversation(tenant_id=tenant_id,thread_id=thread.id,binding_id=binding.id,customer_id=None,customer_phone=thread.customer_phone)
    db.add(mapping);await db.flush()
    return thread


def create_request(email=None):
    return api.CustomerRequest(action='create_customer',expected_version=0,customer=api.NewCustomer(company_name='Synthetic new fleet',first_name='New',last_name='Owner',email=email or uuid4().hex+'@example.com',phone='+15005550002'),contact=api.Person(first_name='New',last_name='Owner',phone='+15005550002'))


@pytest.mark.asyncio
async def test_inquiry_customer_creation_replay_and_transport(data):
    db,user,*_=data
    thread=await inquiry(db,user.tenant_id)
    await db.commit()
    key=uuid4();request=create_request()
    result=await api.put_context(thread.id,request,key,db,user)
    assert await api.put_context(thread.id,request,key,db,user)==result
    assert thread.customer_id is None and thread.thread_kind=='inquiry'
    from app.db.models.callrail import CallRailConversation
    mapping=await db.scalar(select(CallRailConversation).where(CallRailConversation.thread_id==thread.id))
    assert mapping.customer_id is None and mapping.customer_phone==thread.customer_phone
    created=await db.get(Customer,result['customer']['id'])
    assert created.company_name=='Synthetic new fleet' and created.phone=='15005550002'
    assert await db.scalar(select(func.count()).select_from(Customer).where(Customer.email==request.customer.email))==1


@pytest.mark.asyncio
async def test_creation_failure_rolls_back_customer_and_contact(data,monkeypatch):
    db,user,*_=data
    thread=await inquiry(db,user.tenant_id);await db.commit()
    request=create_request()
    original=db.flush
    async def failing(*args,**kwargs):
        if any(isinstance(row,ConversationContactLink) for row in db.new):
            raise RuntimeError('Injected failure after customer/contact creation')
        return await original(*args,**kwargs)
    monkeypatch.setattr(db,'flush',failing)
    with pytest.raises(RuntimeError):
        await api.put_context(thread.id,request,uuid4(),db,user)
    await db.rollback()
    monkeypatch.setattr(db,'flush',original)
    assert await db.scalar(select(func.count()).select_from(Customer).where(Customer.email==request.customer.email))==0


@isolated_postgres
@pytest.mark.asyncio
async def test_concurrent_creates_same_key_and_cross_thread_email():
    import asyncio
    from sqlalchemy import delete
    from app.db.session import AsyncSessionLocal,engine
    from app.db.models.callrail import CallRailConversation,CallRailNumberBinding
    tenant_id,user_id,second_actor_id=uuid4(),uuid4(),uuid4()
    async with AsyncSessionLocal() as db:
        db.add(Tenant(id=tenant_id,name='Concurrent context fixture',slug='concurrent-'+uuid4().hex,messaging_enabled=True));await db.flush()
        for identity in (user_id,second_actor_id):
            db.add(User(id=identity,tenant_id=tenant_id,email=uuid4().hex+'@example.test',first_name='Test',last_name='Staff',hashed_password='disabled',role=UserRole.GARAGE_OWNER,is_active=True))
        first=await inquiry(db,tenant_id);second=await inquiry(db,tenant_id)
        first_id,second_id=first.id,second.id
        await db.commit()
    try:
        request=create_request();key=uuid4()
        async def run(thread_id,actor_id,key,body):
            async with AsyncSessionLocal() as db:
                actor=await db.get(User,actor_id)
                try:
                    return await api.put_context(thread_id,body,key,db,actor)
                except HTTPException as exc:
                    await db.rollback()
                    return exc.detail['code']
        results=await asyncio.gather(*(run(first_id,user_id,key,request) for _ in range(3)))
        assert all(isinstance(r,dict) for r in results)
        assert len({r['customer']['id'] for r in results})==1
        # Different actor/key/thread cannot create the same email again.
        assert await run(second_id,second_actor_id,uuid4(),request)=='duplicate_customer'
        # Truly competing different threads and actors, same new email.
        async with AsyncSessionLocal() as db:
            third=await inquiry(db,tenant_id);third_id=third.id;await db.commit()
        next_request=create_request()
        raced=await asyncio.gather(run(second_id,user_id,uuid4(),next_request),run(third_id,second_actor_id,uuid4(),next_request))
        assert sum(isinstance(r,dict) for r in raced)==1
        assert 'duplicate_customer' in raced
        async with AsyncSessionLocal() as db:
            assert await db.scalar(select(func.count()).select_from(Customer).where(Customer.tenant_id==tenant_id))==2
            assert await db.scalar(select(func.count()).select_from(Contact).where(Contact.tenant_id==tenant_id))==2
    finally:
        async with AsyncSessionLocal() as db:
            for model in (ConversationContextMutation,ContactRepairLink,ConversationContactLink,CallRailConversation,MessageThread,CallRailNumberBinding,Contact,Customer,User):
                await db.execute(delete(model).where(model.tenant_id==tenant_id))
            await db.execute(delete(Tenant).where(Tenant.id==tenant_id));await db.commit()
        await engine.dispose()


@pytest.mark.asyncio
async def test_linked_display_names_preserve_transport_and_fail_closed(data):
    from app.services.communications_service import conversation_display
    db,user,thread,customer,person,orders,foreign=data
    # Inquiries retain null transport customer even after CRM association.
    thread=await inquiry(db,user.tenant_id)
    data=(db,user,thread,customer,person,orders,foreign)
    before=(thread.customer_id,thread.thread_kind,thread.customer_phone,thread.inquiry_binding_id)
    assert await conversation_display(db,user,thread,None)==('New inquiry',None)
    await link(data)
    assert await conversation_display(db,user,thread,None)==('Driver','Fleet A')
    assert (thread.customer_id,thread.thread_kind,thread.customer_phone,thread.inquiry_binding_id)==before
    user.role=UserRole.MECHANIC
    assert await conversation_display(db,user,thread,None)==('New inquiry',None)
    user.role=UserRole.GARAGE_OWNER
    person.first_name=''; person.last_name=''
    assert await conversation_display(db,user,thread,None)==('Fleet A','Fleet A')
    person.deleted_at=datetime.now(timezone.utc);await db.flush()
    assert await conversation_display(db,user,thread,None)==('New inquiry',None)
    person.deleted_at=None;person.tenant_id=foreign.tenant_id;await db.flush()
    assert await conversation_display(db,user,thread,None)==('New inquiry',None)
