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
            await conn.run_sync(upgrade)
            await conn.run_sync(downgrade)
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
                    await conn.exec_driver_sql(f"UPDATE customer_payment_profiles SET environment='test' WHERE id='{pid}'")
            with pytest.raises(IntegrityError):
                async with conn.begin_nested():
                    await conn.exec_driver_sql(f"UPDATE saved_card_operations SET state='confirmed' WHERE id='{oid}'")
    finally:
        async with engine.begin() as conn:
            await conn.exec_driver_sql(f'DROP SCHEMA {schema} CASCADE')
        await engine.dispose()
