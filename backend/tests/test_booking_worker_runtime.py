"""Celery repeated calls reuse one loop; optional real asyncpg pool regression."""
import asyncio
import json
import os
from pathlib import Path
import subprocess
import sys
import textwrap

import pytest

from app.tasks import async_runtime
from app.tasks import booking_payments


def test_booking_worker_reuses_loop_across_repeated_celery_invocations(monkeypatch):
    loop=asyncio.new_event_loop()
    monkeypatch.setattr(async_runtime,'_worker_loop',loop)
    observed=[]
    async def fake_pass():
        observed.append(asyncio.get_running_loop())
        return {'reconciled':0,'expired':0}
    monkeypatch.setattr(booking_payments,'run_booking_expiry',fake_pass)
    try:
        assert booking_payments.expire_booking_holds.run()=={'reconciled':0,'expired':0}
        assert booking_payments.expire_booking_holds.run()=={'reconciled':0,'expired':0}
        assert observed==[loop,loop]
    finally:
        loop.close()


@pytest.mark.skipif(not os.environ.get('BOOKING_POSTGRES_TEST_URL'),reason='Isolated booking concurrency PostgreSQL is not configured')
def test_booking_worker_repeated_entrypoint_with_real_postgres_pool():
    script=textwrap.dedent('''
        import asyncio,json,os
        from uuid import uuid4
        from sqlalchemy import text
        from sqlalchemy.engine import make_url
        from sqlalchemy.ext.asyncio import create_async_engine,async_sessionmaker
        from app.db.base import Base
        import app.db.models
        from app.tasks import booking_payments as task
        from app.tasks.async_runtime import run_async
        from app.services import booking_payment_provider as provider
        url=os.environ['BOOKING_POSTGRES_TEST_URL']
        parsed=make_url(url)
        assert parsed.host in {'127.0.0.1','localhost'} and parsed.database=='booking_concurrency_tests'
        schema='booking_worker_'+uuid4().hex
        admin=create_async_engine(url)
        engine=create_async_engine(url,connect_args={'server_settings':{'search_path':schema}})
        factory=async_sessionmaker(engine,expire_on_commit=False,autoflush=False)
        async def setup():
            async with admin.begin() as db:await db.execute(text(f'CREATE SCHEMA {schema}'))
            async with engine.begin() as db:await db.run_sync(Base.metadata.create_all)
            await engine.dispose()
        async def cleanup():
            await engine.dispose()
            async with admin.begin() as db:await db.execute(text(f'DROP SCHEMA {schema} CASCADE'))
            await admin.dispose()
        async def forbidden(*a,**kw):raise AssertionError('No provider calls permitted')
        for name in ['create_booking_payment','retrieve_booking_payment','cancel_unpaid_booking_payment','recover_created_booking_payment']:setattr(provider,name,forbidden)
        task.AsyncSessionLocal=factory
        observed=[]
        core=task.run_booking_expiry
        async def probe():
            observed.append(id(asyncio.get_running_loop()))
            return await core()
        task.run_booking_expiry=probe
        run_async(setup())
        try:
            outcomes=[task.expire_booking_holds.run() for _ in range(3)]
            assert outcomes==[{'reconciled':0,'expired':0}]*3
            assert len(set(observed))==1
            print(json.dumps({'passes':3,'one_process_loop':True,'provider_calls':0,'records_seeded':0}))
        finally:run_async(cleanup())
    ''')
    env=os.environ.copy()
    backend=str(Path(__file__).resolve().parents[1])
    env['PYTHONPATH']=os.pathsep.join(filter(None,[env.get('PYTHONPATH'),backend]))
    completed=subprocess.run([sys.executable,'-c',script],env=env,text=True,capture_output=True,timeout=60)
    assert completed.returncode==0,(completed.stdout+completed.stderr)[-7000:]
    assert json.loads(completed.stdout.strip().splitlines()[-1])['passes']==3
