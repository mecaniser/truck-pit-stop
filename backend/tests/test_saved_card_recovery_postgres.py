"""Real row-lock acceptance. Requires an explicit disposable PostgreSQL database."""
import asyncio
import os
from uuid import uuid4

import pytest
from sqlalchemy import MetaData, select
from sqlalchemy.schema import ForeignKeyConstraint
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db.models.customer import Customer
from app.services import stripe_customer_service as service


@pytest.mark.asyncio
@pytest.mark.parametrize('reference', [None, 'cus_missing'])
async def test_concurrent_stale_invoice_and_setup_reuse_one_recovery(monkeypatch, reference):
    url = os.environ.get('SAVED_CARDS_TEST_DATABASE_URL')
    if not url:
        pytest.skip('Explicit disposable SAVED_CARDS_TEST_DATABASE_URL required')
    engine = create_async_engine(url)
    schema = 'saved_cards_' + uuid4().hex
    table = Customer.__table__.to_metadata(MetaData(), schema=schema)
    # Standalone copy of the real customer table; related business tables are
    # irrelevant to this row-lock test and never touched.
    for constraint in list(table.constraints):
        if isinstance(constraint, ForeignKeyConstraint):
            table.constraints.remove(constraint)
    async with engine.begin() as conn:
        await conn.exec_driver_sql(f'CREATE SCHEMA {schema}')
        await conn.run_sync(table.create)
    scoped_engine = engine.execution_options(schema_translate_map={None: schema})
    sessions = async_sessionmaker(scoped_engine, expire_on_commit=False)
    cid, tid = uuid4(), uuid4()
    try:
        async with sessions() as seed:
            seed.add(Customer(id=cid, tenant_id=tid, first_name='Test', last_name='Driver', email='driver@example.com', stripe_customer_id=reference))
            await seed.commit()
        created = []
        def create(**params):
            assert params['stripe_account'] == 'acct_test_shop'
            created.append('cus_recovered')
            return {'id': 'cus_recovered'}
        def modify(customer_id, **params):
            assert params['stripe_account'] == 'acct_test_shop'
            if customer_id == 'cus_missing':
                raise service.stripe.error.InvalidRequestError('missing', 'customer', code='resource_missing')
            assert customer_id == 'cus_recovered'
        monkeypatch.setattr(service.stripe.Customer, 'create', create)
        monkeypatch.setattr(service.stripe.Customer, 'modify', modify)
        async with sessions() as setup, sessions() as invoice:
            # Both callers have already loaded the stale value before either
            # enters the helper, exactly the lost-update scenario under review.
            a = (await setup.execute(select(Customer).where(Customer.id == cid))).scalar_one()
            b = (await invoice.execute(select(Customer).where(Customer.id == cid))).scalar_one()
            result = await asyncio.wait_for(asyncio.gather(
                service.ensure_connected_stripe_customer(setup, a, 'acct_test_shop'),
                service.ensure_connected_stripe_customer(invoice, b, 'acct_test_shop'),
            ), timeout=10)
            assert result == ['cus_recovered', 'cus_recovered']
            assert created == ['cus_recovered']
            await setup.rollback()
            await invoice.rollback()
        async with sessions() as check:
            assert (await check.get(Customer, cid)).stripe_customer_id == 'cus_recovered'
    finally:
        async with engine.begin() as conn:
            await conn.exec_driver_sql(f'DROP SCHEMA {schema} CASCADE')
        await engine.dispose()
