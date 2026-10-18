"""Recovery rollout, overlap, failure visibility and execution bounds."""
import asyncio
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from app.tasks import sms_recovery as task
from app.services import automated_sms_service as automated


@pytest.fixture
def recovery(monkeypatch):
    config = SimpleNamespace(SMS_RECOVERY_ENABLED=True, SMS_RECOVERY_TENANT_IDS='', ENVIRONMENT='development', SMS_RECOVERY_BATCH_SIZE=10, SMS_RECOVERY_BUDGET_SECONDS=50)
    redis = SimpleNamespace(set=AsyncMock(return_value=True), eval=AsyncMock())
    monkeypatch.setattr(task, 'settings', config)
    monkeypatch.setattr(task, 'get_redis', AsyncMock(return_value=redis))
    monkeypatch.setattr(task, 'get_sms_sender', lambda: SimpleNamespace(mode='simulated', ready=True))
    @asynccontextmanager
    async def session():
        yield object()
    monkeypatch.setattr(task, 'AsyncSessionLocal', session)
    manual = AsyncMock(return_value={'examined': 1, 'accepted': 1})
    auto = AsyncMock(return_value={'examined': 2, 'accepted': 2})
    monkeypatch.setattr(task, 'process_pending_operations', manual)
    monkeypatch.setattr(automated, 'process_pending_automated_operations', auto)
    return config, redis, manual, auto


@pytest.mark.asyncio
async def test_disabled_does_not_touch_provider_database_or_redis(recovery):
    config, redis, manual, auto = recovery
    config.SMS_RECOVERY_ENABLED = False
    assert await task.recover_sms() == {'status': 'disabled', 'batches': 0}
    task.get_redis.assert_not_called()
    manual.assert_not_called()
    auto.assert_not_called()


@pytest.mark.asyncio
async def test_overlapping_tick_is_noop(recovery):
    _, redis, manual, auto = recovery
    redis.set.return_value = False
    assert (await task.recover_sms())['status'] == 'busy'
    manual.assert_not_called()
    auto.assert_not_called()
    redis.eval.assert_not_called()  # must not release somebody else's lease


@pytest.mark.asyncio
async def test_both_queues_scoped_bounded_and_lock_released(recovery):
    config, redis, manual, auto = recovery
    tenant = '00000000-0000-4000-8000-000000000001'
    config.SMS_RECOVERY_TENANT_IDS = tenant + ',' + tenant
    result = await task.recover_sms()
    assert result == {'status': 'completed', 'batches': 2, 'examined': 3, 'accepted': 3}
    for processor in (manual, auto):
        processor.assert_awaited_once()
        assert processor.call_args.kwargs == {'limit': 10, 'tenant_id': task.UUID(tenant)}
    assert redis.set.call_args.kwargs == {'nx': True, 'ex': 110}
    redis.eval.assert_awaited_once_with(task.RELEASE_LOCK, 1, task.LOCK_KEY, redis.set.call_args.args[1])


@pytest.mark.asyncio
async def test_database_failure_is_failed_task_and_releases_lease(recovery):
    _, redis, manual, auto = recovery
    manual.side_effect = RuntimeError('database unavailable')
    auto.side_effect = RuntimeError('database unavailable')
    with pytest.raises(RuntimeError, match='database unavailable'):
        await task.recover_sms()
    redis.eval.assert_awaited_once()


@pytest.mark.asyncio
async def test_slow_provider_budget_is_bounded_and_lease_released(recovery):
    config, redis, manual, auto = recovery
    config.SMS_RECOVERY_BUDGET_SECONDS = .01
    async def slow(*args, **kwargs):
        await asyncio.sleep(1)
    manual.side_effect = slow
    auto.side_effect = slow
    assert (await task.recover_sms())['status'] == 'budget_exhausted'
    redis.eval.assert_awaited_once()


@pytest.mark.parametrize('allowlist', ['', 'not-a-uuid'])
def test_production_requires_valid_explicit_tenants(recovery, allowlist):
    config, *_ = recovery
    config.ENVIRONMENT = 'production'
    config.SMS_RECOVERY_TENANT_IDS = allowlist
    with pytest.raises(RuntimeError):
        task.configured_tenants()


@pytest.mark.asyncio
async def test_production_rejects_simulation(recovery):
    config, *_ = recovery
    config.ENVIRONMENT = 'production'
    config.SMS_RECOVERY_TENANT_IDS = '00000000-0000-4000-8000-000000000001'
    with pytest.raises(RuntimeError, match='live provider'):
        await task.recover_sms()
    task.get_redis.assert_not_called()


@pytest.mark.asyncio
async def test_missing_credentials_fail_before_claim(recovery, monkeypatch):
    monkeypatch.setattr(task, 'get_sms_sender', lambda: SimpleNamespace(mode='live', ready=False))
    with pytest.raises(RuntimeError, match='credentials'):
        await task.recover_sms()
    task.get_redis.assert_not_called()


def test_task_is_sync_with_hard_stop():
    import inspect
    assert not inspect.iscoroutinefunction(task.process_sms_recovery.run)
    assert task.process_sms_recovery.soft_time_limit == 70
    assert task.process_sms_recovery.time_limit == 90
    assert task.process_sms_recovery.acks_late


@pytest.mark.parametrize('enabled', [False, True])
def test_beat_schedule_is_opt_in_and_expires(enabled):
    import json
    import os
    import subprocess
    import sys
    code = """
import json
from app.tasks import celery_app
entry = celery_app.conf.beat_schedule.get('process-sms-recovery')
print(json.dumps(None if entry is None else {'task':entry['task'], 'seconds':entry['schedule'].total_seconds(), 'expires':entry['options']['expires']}))
"""
    env = {**os.environ, 'SMS_RECOVERY_ENABLED': str(enabled).lower()}
    result = subprocess.run([sys.executable, '-c', code], env=env, capture_output=True, text=True, check=True)
    assert json.loads(result.stdout.strip().splitlines()[-1]) == ({'task':'process_sms_recovery', 'seconds':60, 'expires':60} if enabled else None)


@pytest.mark.parametrize('table', ['sms_send_operations', 'automated_sms_operations'])
def test_worker_schema_gate_rejects_missing_outbox_columns(monkeypatch, table):
    import sqlalchemy
    from unittest.mock import MagicMock
    from app.commands import worker_schema_readiness as gate, schema_preflight
    engine = MagicMock()
    monkeypatch.setattr(sqlalchemy, 'create_engine', lambda *a, **k: engine)
    monkeypatch.setattr(schema_preflight, 'verify_database', lambda *a: None)
    def columns(name):
        return [{'name': c} for c in gate.REQUIRED_COLUMNS[name] if not (name == table and c == 'attempt_count')]
    monkeypatch.setattr(sqlalchemy, 'inspect', lambda *a: SimpleNamespace(get_columns=columns))
    assert gate._probe_database('postgresql://localhost/test', {'178'}) == 'schema_not_ready'


@pytest.mark.asyncio
async def test_small_budget_rotates_every_tenant_queue_pair(recovery, monkeypatch):
    config, _, manual, auto = recovery
    tenants = ['00000000-0000-4000-8000-000000000001', '00000000-0000-4000-8000-000000000002']
    config.SMS_RECOVERY_TENANT_IDS = ','.join(tenants)
    seen = set()
    clock = SimpleNamespace(now=0, tick=0)
    monkeypatch.setattr(task, 'time', SimpleNamespace(time=lambda: clock.tick * 60, monotonic=lambda: clock.now))
    async def consume_budget(queue, *args, **kwargs):
        seen.add((queue, str(kwargs['tenant_id'])))
        clock.now += 51
        return {}
    async def manual_run(*args, **kwargs):
        return await consume_budget('manual', *args, **kwargs)
    async def automated_run(*args, **kwargs):
        return await consume_budget('automated', *args, **kwargs)
    manual.side_effect = manual_run
    auto.side_effect = automated_run
    for tick in range(4):
        clock.tick, clock.now = tick, 0
        assert (await task.recover_sms())['status'] == 'budget_exhausted'
    assert seen == {(queue, tenant) for queue in ('manual', 'automated') for tenant in tenants}
