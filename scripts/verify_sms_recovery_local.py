"""Exercise real Celery worker + Beat with isolated PostgreSQL and fake provider.

Usage: python scripts/communications_local.py exec python ../scripts/verify_sms_recovery_local.py
"""
import asyncio
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import time
from uuid import UUID, uuid4

sys.path.insert(0, str(Path(__file__).resolve().parent))
from communications_local_worker import celery_app
from communications_local_app import LEDGER
from app.db.session import AsyncSessionLocal
from app.db.models.automated_sms import AutomatedSMSOperation
from app.services.automated_sms_service import enqueue_automated_sms
from sqlalchemy import select

TENANT = UUID('00000000-0000-4000-8000-000000000001')
CUSTOMER = uuid4()
PHONE = '+1500' + str(1000000 + CUSTOMER.int % 9000000)

async def enqueue(event, body):
    async with AsyncSessionLocal() as db:
        operation = await enqueue_automated_sms(db, tenant_id=TENANT, domain_event_id=event, template_name='work_started_sms', to=PHONE, body=body, customer_id=CUSTOMER)
        await db.commit()
        return operation.id

async def state(operation_id):
    async with AsyncSessionLocal() as db:
        op = await db.scalar(select(AutomatedSMSOperation).where(AutomatedSMSOperation.id == operation_id))
        return op.state, op.attempt_count

def calls():
    with sqlite3.connect(LEDGER) as db:
        return db.execute('SELECT COUNT(*) FROM calls').fetchone()[0]

def next_outcome(outcome):
    with sqlite3.connect(LEDGER) as db:
        db.execute('INSERT OR REPLACE INTO control(id,outcome) VALUES (1,?)', (outcome,))

async def wait_state(operation_id, expected):
    deadline = time.monotonic() + 40
    while time.monotonic() < deadline:
        current = await state(operation_id)
        if current == (expected, 1):
            return
        if current[0] == 'rejected':
            raise AssertionError('Synthetic intent unexpectedly rejected')
        await asyncio.sleep(.3)
    raise AssertionError(f'Worker failed to reach {expected}')

async def main():
    event = 'local-worker-verification:' + uuid4().hex
    body = 'Simulated scheduled service update.'
    from app.db.models.customer import Customer
    async with AsyncSessionLocal() as db:
        db.add(Customer(id=CUSTOMER, tenant_id=TENANT, first_name='Recovery', last_name='Verification', phone=PHONE, email=f'{CUSTOMER}@communications.example.com'))
        await db.commit()
    baseline = calls()
    operation_id = await enqueue(event, body)
    assert await state(operation_id) == ('pending', 0)
    assert calls() == baseline  # enqueue never performs I/O
    env = {**os.environ, 'PYTHONPATH': str(Path(__file__).resolve().parent) + os.pathsep + os.environ.get('PYTHONPATH', '')}
    processes = []
    with tempfile.TemporaryDirectory(prefix='communications-worker-') as directory:
        def start_worker():
            log = open(Path(directory) / ('worker-' + str(len(processes)) + '.log'), 'w')
            process = subprocess.Popen([sys.executable, '-m', 'celery', '-A', 'communications_local_worker:celery_app', 'worker', '--pool=solo', '--concurrency=1', '--queues=communications-local-recovery', '--hostname=communications-local-verification@%h', '--without-gossip', '--without-mingle', '--loglevel=INFO'], env=env, stdout=log, stderr=subprocess.STDOUT)
            log.close()
            processes.append(process)
            return process
        worker = start_worker()
        log = open(Path(directory) / 'beat.log', 'w')
        beat = subprocess.Popen([sys.executable, '-m', 'celery', '-A', 'communications_local_worker:celery_app', 'beat', '--schedule', str(Path(directory)/'schedule'), '--pidfile', str(Path(directory)/'beat.pid'), '--loglevel=INFO'], env=env, stdout=log, stderr=subprocess.STDOUT)
        log.close()
        processes.append(beat)
        try:
            await wait_state(operation_id, 'accepted')
            assert calls() == baseline + 1
            assert await enqueue(event, body) == operation_id
            # Restart the actual worker with the same durable queue + database.
            worker.terminate()
            worker.wait(timeout=15)
            start_worker()
            await asyncio.sleep(5)
            assert calls() == baseline + 1
            assert await state(operation_id) == ('accepted', 1)
            next_outcome('unknown')
            uncertain = await enqueue(event + ':timeout', 'Simulated ambiguous provider response.')
            await wait_state(uncertain, 'unknown')
            assert calls() == baseline + 2
            await asyncio.sleep(5)  # multiple Beat ticks must not retry unknown
            assert calls() == baseline + 2
            assert await state(uncertain) == ('unknown', 1)
            logs = '\n'.join(p.read_text() for p in Path(directory).glob('worker-*.log'))
            assert 'Worker schema readiness passed' in logs
            assert 'sms_recovery_completed' in logs
            print('PASS actual Celery + Beat: persisted pending recovery; one provider call; same-event replay; worker restart; unknown outcome held across repeated ticks; schema readiness.')
        finally:
            for process in reversed(processes):
                if process.poll() is None:
                    process.terminate()
                    try:
                        process.wait(timeout=15)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait(timeout=5)

if __name__ == '__main__':
    asyncio.run(main())
