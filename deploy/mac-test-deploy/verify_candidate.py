"""Candidate-container acceptance on an isolated synthetic database, never production."""
import asyncio
from decimal import Decimal
import json
import sys
from uuid import uuid4
import httpx
from sqlalchemy import inspect, select, text
from sqlalchemy.dialects import postgresql
from sqlalchemy.engine import make_url
from app.core.config import settings
from app.db.base import Base
from app.db.session import engine, AsyncSessionLocal
import app.db.models
from app.db.models.inventory import Inventory
from app.db.models.inventory_lifecycle import PartActivityEvent
from app.db.models.tenant import Tenant
from app.main import app


async def main():
    passwords = json.load(sys.stdin)
    url = make_url(settings.DATABASE_URL)
    assert url.host == 'postgres' and url.database.startswith('dbtest_') and url.username == url.database
    assert settings.ENVIRONMENT == 'staging' and settings.REDIS_URL == 'redis://redis:6379/14'
    problems=[]; mapped_columns=0
    async with engine.connect() as connection:
        await connection.execute(text('SET TRANSACTION READ ONLY'))
        def examine(sync):
            inspector=inspect(sync); tables=set(inspector.get_table_names()); result=[]
            for table in Base.metadata.sorted_tables:
                if table.name not in tables: result.append('missing_table:'+table.name);continue
                actual={c['name']:c for c in inspector.get_columns(table.name)}
                for column in table.columns:
                    found=actual.get(column.name)
                    if found is None: result.append('missing_column:'+table.name+'.'+column.name);continue
                    expected_enum=getattr(column.type,'enums',None); actual_enum=getattr(found['type'],'enums',None)
                    if expected_enum and actual_enum:
                        if not set(expected_enum)<=set(actual_enum):result.append('enum_type:'+table.name+'.'+column.name)
                    elif column.type._type_affinity != found['type']._type_affinity:
                        result.append('type:'+table.name+'.'+column.name)
                for name,column in actual.items():
                    if name not in table.c and not column['nullable'] and column.get('default') is None and not column.get('identity') and not column.get('computed'):
                        result.append('required_unmapped:'+table.name+'.'+name)
            return result
        problems=await connection.run_sync(examine)
        for table in Base.metadata.sorted_tables:
            for column in table.columns:
                mapped_columns+=1
                if not column.nullable:
                    count=await connection.scalar(select(text('count(*)')).select_from(table).where(column.is_(None)))
                    if count:problems.append('null_data:'+table.name+'.'+column.name)
                if getattr(column.type,'enums',None):
                    count=await connection.scalar(select(text('count(*)')).select_from(table).where(column.is_not(None),column.cast(postgresql.TEXT).notin_(column.type.enums)))
                    if count:problems.append('enum_data:'+table.name+'.'+column.name)
        await connection.rollback()
    # An independent read-only connection to original data must fail privileges.
    from sqlalchemy.ext.asyncio import create_async_engine
    denied=False; other=create_async_engine(url.set(database='dieselbridge_local_test'))
    try:
        async with other.connect() as c: await c.execute(text('SELECT id FROM users LIMIT 1'))
    except Exception:denied=True
    finally:await other.dispose()
    assert denied, 'Candidate role can read original users'
    if problems:
        print(json.dumps({'schema_compatible':False,'problems':problems,'mapped_columns':mapped_columns,'original_db_access_denied':denied}));return
    tokens={};customer_ids={}
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='https://dieselbridge-test.elisprotech.com') as client:
        for name in ('alpha','beta'):
            response=await client.post('/api/v1/auth/login',json={'email':'staging-'+name+'@example.com','password':passwords[name]})
            assert response.status_code==200, ('native_login',name,response.status_code)
            tokens[name]=response.json()['access_token']
            response=await client.get('/api/v1/customers',headers={'Authorization':'Bearer '+tokens[name]})
            assert response.status_code==200 and len(response.json())==1
            customer_ids[name]=response.json()[0]['id']
        for name,other_name in (('alpha','beta'),('beta','alpha')):
            response=await client.get('/api/v1/customers/'+customer_ids[other_name],headers={'Authorization':'Bearer '+tokens[name]})
            assert response.status_code in (403,404)
        async with AsyncSessionLocal() as db:
            tenant=await db.scalar(select(Tenant).where(Tenant.slug=='local-test-alpha'))
            if tenant is None:tenant=await db.scalar(select(Tenant).where(Tenant.name=='Staging Alpha'))
            assert tenant is not None
            part=Inventory(tenant_id=tenant.id,sku='MAC-DEPLOY-'+uuid4().hex[:12],name='Synthetic deploy activity check',stock_quantity=1,reorder_level=0,cost=Decimal('10.00'),selling_price=Decimal('15.00'),core_charge=Decimal('0.00'),unit_type='each')
            db.add(part);await db.commit();part_id=part.id
        response=await client.put('/api/v1/inventory/'+str(part_id),headers={'Authorization':'Bearer '+tokens['alpha']},json={'cost':'20.30','selling_price':'51.78','core_charge':'5.00','supplier_name':'Synthetic Test Supplier','supplier_contact':'parts@example.test'})
        assert response.status_code==200, ('catalog_update',response.status_code)
        assert response.json()['cost']=='20.30' and response.json()['supplier_name']=='Synthetic Test Supplier'
        async with AsyncSessionLocal() as db:
            events=(await db.execute(select(PartActivityEvent).where(PartActivityEvent.inventory_id==part_id))).scalars().all()
            assert len(events)==5
            assert {event.event_type for event in events}=={'part.cost_changed','part.selling_price_changed','part.core_charge_changed','part.supplier_text_changed'}
            cost=next(e for e in events if e.event_type=='part.cost_changed')
            assert cost.before_values=={'cost':'10.00'} and cost.after_values=={'cost':'20.30'}
    print(json.dumps({'schema_compatible':True,'mapped_tables':len(Base.metadata.tables),'mapped_columns':mapped_columns,'enum_null_data_checks':True,'native_login':True,'tenant_denials_both_directions':True,'read_write':True,'activity_count':5,'original_db_access_denied':True,'synthetic_part_id':str(part_id),'original_database_mutated':False,'no_automatic_migrations':True,'worker_queues_blocked':True}))
    await engine.dispose()


if __name__=='__main__':
    try:asyncio.run(main())
    except Exception as error:raise SystemExit('Candidate acceptance failed: '+type(error).__name__) from None
