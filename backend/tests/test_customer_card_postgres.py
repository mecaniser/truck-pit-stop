"""Migration and concurrent receipt constraints against disposable PostgreSQL."""
import importlib.util
import os
from pathlib import Path
from uuid import uuid4
import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.exc import IntegrityError


@pytest.mark.asyncio
async def test_migration_roundtrip_and_open_receipt_serialization():
    url=os.environ.get('SAVED_CARDS_TEST_DATABASE_URL')
    if not url:
        pytest.skip('Explicit disposable SAVED_CARDS_TEST_DATABASE_URL required')
    engine=create_async_engine(url)
    schema='wallet_'+uuid4().hex
    path=Path(__file__).parents[1]/'alembic/versions/201_customer_payment_profiles.py'
    spec=importlib.util.spec_from_file_location('wallet_migration',path)
    migration=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    async with engine.begin() as conn:
        await conn.exec_driver_sql(f'CREATE SCHEMA {schema}')
    try:
        async with engine.begin() as conn:
            await conn.exec_driver_sql(f'SET search_path TO {schema}')
            await conn.exec_driver_sql('CREATE TABLE tenants (id UUID PRIMARY KEY)')
            await conn.exec_driver_sql('CREATE TABLE customers (id UUID PRIMARY KEY, tenant_id UUID NOT NULL, UNIQUE(tenant_id,id))')
            def upgrade(sync):
                with Operations.context(MigrationContext.configure(sync)):
                    migration.upgrade()
            def downgrade(sync):
                with Operations.context(MigrationContext.configure(sync)):
                    migration.downgrade()
            await conn.exec_driver_sql("INSERT INTO tenants VALUES ('00000000-0000-0000-0000-000000000001')")
            await conn.run_sync(upgrade)
            await conn.run_sync(downgrade)
            assert (await conn.exec_driver_sql('SELECT count(*) FROM tenants')).scalar_one()==1
            await conn.run_sync(upgrade)
            tid,cid,pid,oid=map(str,[uuid4(),uuid4(),uuid4(),uuid4()])
            await conn.exec_driver_sql(f"INSERT INTO tenants VALUES ('{tid}')")
            await conn.exec_driver_sql(f"INSERT INTO customers VALUES ('{cid}','{tid}')")
            await conn.exec_driver_sql(f"INSERT INTO customer_payment_profiles (id,tenant_id,customer_id,provider,provider_account_id,environment,provider_customer_id) VALUES ('{pid}','{tid}','{cid}','quickbooks_payments','realm','sandbox','identity')")
            await conn.exec_driver_sql(f"INSERT INTO saved_card_operations (id,tenant_id,customer_id,profile_id,context_key,idempotency_key,token_hash,state) VALUES ('{oid}','{tid}','{cid}','{pid}','context','first','hash_first','pending')")
        # Independent committed transaction cannot create another open receipt.
        async with engine.begin() as conn:
            await conn.exec_driver_sql(f'SET search_path TO {schema}')
            with pytest.raises(IntegrityError):
                async with conn.begin_nested():
                    await conn.exec_driver_sql(f"INSERT INTO saved_card_operations (id,tenant_id,customer_id,profile_id,context_key,idempotency_key,token_hash,state) VALUES ('{uuid4()}','{tid}','{cid}','{pid}','context','second','hash_second','pending')")
            with pytest.raises(IntegrityError):
                async with conn.begin_nested():
                    await conn.exec_driver_sql(f"UPDATE customer_payment_profiles SET tenant_id='00000000-0000-0000-0000-000000000001' WHERE id='{pid}'")
            with pytest.raises(IntegrityError):
                async with conn.begin_nested():
                    await conn.exec_driver_sql(f"UPDATE customer_payment_profiles SET environment='test' WHERE id='{pid}'")
            with pytest.raises(IntegrityError):
                async with conn.begin_nested():
                    await conn.exec_driver_sql(f"UPDATE saved_card_operations SET state='confirmed' WHERE id='{oid}'")
    finally:
        async with engine.begin() as conn:
            await conn.exec_driver_sql(f'DROP SCHEMA {schema} CASCADE')
        await engine.dispose()


@pytest.mark.asyncio
async def test_full_revision_200_to_201_roundtrip_preserves_previous_schema():
    import asyncio
    import subprocess
    import sys
    url=os.environ.get('SAVED_CARDS_TEST_DATABASE_URL')
    if not url:
        pytest.skip('Explicit disposable SAVED_CARDS_TEST_DATABASE_URL required')
    env=dict(os.environ,DATABASE_URL=url,SECRET_KEY='disposable_migration_test_only_0123456789')
    async def migrate(*args):
        result=await asyncio.to_thread(subprocess.run,[sys.executable,'-m','alembic',*args],cwd=Path(__file__).parents[1],env=env,capture_output=True,text=True)
        assert result.returncode==0,result.stderr[-3000:]
    engine=create_async_engine(url)
    async def previous_schema():
        async with engine.connect() as conn:
            return list((await conn.exec_driver_sql("SELECT table_name,column_name,data_type,is_nullable,column_default FROM information_schema.columns WHERE table_schema='public' AND table_name NOT IN ('customer_payment_profiles','saved_card_operations') ORDER BY table_name,ordinal_position")).all())
    try:
        await migrate('upgrade','200')
        before=await previous_schema()
        assert any(row[0]=='booking_receipt_applications' for row in before)
        await migrate('upgrade','201_customer_payment_profiles')
        assert await previous_schema()==before
        await migrate('downgrade','200')
        assert await previous_schema()==before
        await migrate('upgrade','201_customer_payment_profiles')
        assert await previous_schema()==before
        async with engine.connect() as conn:
            assert (await conn.exec_driver_sql('SELECT version_num FROM alembic_version')).scalar_one()=='201_customer_payment_profiles'
    finally:
        await engine.dispose()
