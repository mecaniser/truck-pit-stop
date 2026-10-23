"""Multiple local fleets must keep independent, immutable worker identities."""

import json
import os
import subprocess
import sys
from pathlib import Path
from uuid import uuid4

import pytest
from scripts.motive_drivers import run_fleets


def environment():
    return {
        "MOTIVE_DRIVER_FLEET_CUSTOMER_ID": str(uuid4()),
        "MOTIVE_DRIVER_ADDITIONAL_FLEET_CUSTOMER_IDS": json.dumps([str(uuid4())]),
        "MOTIVE_DRIVER_JOURNAL": "database",
        "MOTIVE_DRIVER_JOURNAL_KEY": "existing-worker",
        "MOTIVE_DRIVER_STATE_DIR": "/tmp/motive-driver",
        "MOTIVE_DRIVER_COMMIT": "false",
        "MOTIVE_SYNC_TENANT_ID": str(uuid4()),
        "MOTIVE_SYNC_ACTOR_ID": str(uuid4()),
        "MOTIVE_COMPANY_ID": "KT123",
        "MOTIVE_COMPANY_LABEL": "Synthetic Fleet",
        "MOTIVE_PASSWORD": "PRIVATE_TEST_VALUE",
    }


def test_per_fleet_identity_isolated_and_primary_recovery_unchanged():
    source = environment()
    children = run_fleets.fleet_environments(source)
    assert len(children) == 2
    assert children[0]["MOTIVE_DRIVER_JOURNAL_KEY"] == "existing-worker"
    assert children[0]["MOTIVE_DRIVER_STATE_DIR"] == "/tmp/motive-driver"
    secondary = json.loads(source[run_fleets.EXTRA_FLEETS])[0]
    assert children[1]["MOTIVE_DRIVER_FLEET_CUSTOMER_ID"] == secondary
    assert children[1]["MOTIVE_DRIVER_JOURNAL_KEY"] == f"existing-worker.{secondary}"
    assert children[1]["MOTIVE_DRIVER_STATE_DIR"] == f"/tmp/motive-driver/{secondary}"
    for child in children:
        assert run_fleets.EXTRA_FLEETS not in child
        for key in (
            "MOTIVE_SYNC_TENANT_ID",
            "MOTIVE_SYNC_ACTOR_ID",
            "MOTIVE_COMPANY_ID",
            "MOTIVE_COMPANY_LABEL",
            "MOTIVE_PASSWORD",
            "MOTIVE_DRIVER_COMMIT",
        ):
            assert child[key] == source[key]
    assert run_fleets.EXTRA_FLEETS in source


@pytest.mark.parametrize(
    "invalid",
    [
        None,
        {},
        "not-a-list",
        [None],
        [123],
        ["../../other"],
        ["not-a-uuid"],
        [str(uuid4())] * 2,
        [str(uuid4()) for _ in range(9)],
    ],
)
def test_invalid_targets_fail_before_any_child(monkeypatch, invalid):
    source = environment()
    source[run_fleets.EXTRA_FLEETS] = json.dumps(invalid)
    monkeypatch.setattr(run_fleets.os, "environ", source)
    calls = []
    monkeypatch.setattr(run_fleets.subprocess, "run", lambda *a, **kw: calls.append(kw))
    with pytest.raises((ValueError, TypeError, AttributeError)):
        run_fleets.main()
    assert calls == []


def test_duplicate_primary_noncanonical_uuid_file_mode_and_key_overflow_rejected():
    source = environment()
    invalid = [
        {
            run_fleets.EXTRA_FLEETS: json.dumps(
                [source["MOTIVE_DRIVER_FLEET_CUSTOMER_ID"]]
            )
        },
        {run_fleets.EXTRA_FLEETS: json.dumps(["12345678-1234-4ABC-8ABC-123456789ABC"])},
        {"MOTIVE_DRIVER_JOURNAL": "file"},
        {"MOTIVE_DRIVER_JOURNAL_KEY": "a" * 120},
        {"MOTIVE_DRIVER_JOURNAL_KEY": "../unsafe"},
    ]
    for changes in invalid:
        with pytest.raises(ValueError):
            run_fleets.fleet_environments({**source, **changes})


def test_single_fleet_keeps_existing_file_or_database_mode():
    source = environment()
    del source[run_fleets.EXTRA_FLEETS]
    for mode in ("file", "database"):
        children = run_fleets.fleet_environments(
            {**source, "MOTIVE_DRIVER_JOURNAL": mode}
        )
        assert len(children) == 1
        assert (
            children[0]["MOTIVE_DRIVER_JOURNAL_KEY"]
            == source["MOTIVE_DRIVER_JOURNAL_KEY"]
        )


@pytest.fixture
def batch_harness(monkeypatch, tmp_path):
    from contextlib import asynccontextmanager
    from types import SimpleNamespace

    from scripts.motive_drivers import journal, run_worker, runner

    source = {
        **environment(),
        "MOTIVE_DRIVER_STATE_DIR": str(tmp_path),
        "MOTIVE_DRIVER_COMMIT": "true",
    }
    events = []
    stores = []
    documents = []

    @asynccontextmanager
    async def locked(engine, identity, key):
        async def pending():
            return []

        store = SimpleNamespace(identity=identity, worker_key=key, pending=pending)
        stores.append(store)
        events.append(("lock", key))
        try:
            yield store
        finally:
            events.append(("unlock", key))

    async def authorize(factory, identity):
        events.append(("authorize", identity.customer_id))

    async def prepare(journals, document, **kwargs):
        events.append(("prepare", len(journals)))
        assert kwargs["commit"] is True
        documents.append(document)
        return [object() for _ in journals]

    async def project(
        factory, document, tenant, actor, company_label, company_id, receipt, **kwargs
    ):
        events.append(("project", kwargs["expected_customer_id"]))
        assert document is documents[0]
        assert kwargs["commit"] is True
        return {"stage": "verified", "committed": True}

    async def recover(store, factory, **kwargs):
        events.append(("recover", store.identity.customer_id))
        return len(await store.pending())

    def collect(command, **kwargs):
        events.append(("collect", command[0]))
        assert (
            command[0] == "node"
            and kwargs["timeout"] == 1500
            and kwargs["check"] is True
        )
        from tests.test_motive_driver_worker import document

        Path(command[-1]).write_text(json.dumps(document()))

    @asynccontextmanager
    async def batch(engine, identities):
        from contextlib import AsyncExitStack

        async with AsyncExitStack() as stack:
            yield [
                await stack.enter_async_context(
                    journal.database_journal(engine, identity, key)
                )
                for identity, key in identities
            ]

    monkeypatch.setattr(journal, "database_journals", batch)
    monkeypatch.setattr(journal, "database_journal", locked)
    monkeypatch.setattr(journal, "authorize_configuration", authorize)
    monkeypatch.setattr(journal, "prepare_batch", prepare)
    monkeypatch.setattr(runner, "run", project)
    monkeypatch.setattr(run_worker, "recover_database", recover)
    monkeypatch.setattr(run_fleets, "read_process", collect)
    return source, events, stores, runner, journal


@pytest.mark.asyncio
async def test_one_source_prepared_for_every_fleet_before_any_projection(
    batch_harness, capsys
):
    source, events, _stores, _, _ = batch_harness
    children = run_fleets.fleet_environments(source)
    await run_fleets.database_fleets(children, engine=object(), factory=object())
    names = [event[0] for event in events]
    assert names.count("collect") == 1
    assert names.count("authorize") == 2 and names.count("project") == 2
    assert max(i for i, n in enumerate(names) if n == "authorize") < names.index(
        "collect"
    )
    assert names.index("prepare") < names.index("project")
    assert names.count("unlock") == 2
    result = json.loads(capsys.readouterr().out.splitlines()[-1])
    assert result == {
        "stage": "fleets_complete",
        "fleet_count": 2,
        "source_collections": 1,
    }


@pytest.mark.asyncio
async def test_failed_projection_stops_without_recollecting_and_releases_all_locks(
    batch_harness,
):
    source, events, _, runner, _ = batch_harness

    async def fail(*args, **kwargs):
        events.append(("failed_projection", kwargs["expected_customer_id"]))
        raise OSError("PRIVATE_TEST_VALUE")

    monkey = pytest.MonkeyPatch()
    monkey.setattr(runner, "run", fail)
    try:
        with pytest.raises(OSError):
            await run_fleets.database_fleets(
                run_fleets.fleet_environments(source), engine=object(), factory=object()
            )
    finally:
        monkey.undo()
    names = [event[0] for event in events]
    assert names.count("collect") == 1 and names.count("prepare") == 1
    assert names.count("failed_projection") == 1 and names.count("unlock") == 2


@pytest.mark.asyncio
async def test_authority_failure_prevents_browser_and_any_projection(
    batch_harness, monkeypatch
):
    source, events, _, _, journal = batch_harness

    async def denied(*args):
        raise ValueError("tenant denied")

    monkeypatch.setattr(journal, "authorize_configuration", denied)
    with pytest.raises(ValueError):
        await run_fleets.database_fleets(
            run_fleets.fleet_environments(source), engine=object(), factory=object()
        )
    assert not any(e[0] in {"collect", "prepare", "project"} for e in events)
    assert events[-1][0] == "unlock"


@pytest.mark.asyncio
async def test_pending_commit_recovery_runs_before_new_reads_and_returns_precise_status(
    batch_harness, monkeypatch, capsys
):
    source, events, _, _, journal = batch_harness
    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def locked(engine, identity, key):
        from types import SimpleNamespace

        async def pending():
            return [object()]

        yield SimpleNamespace(identity=identity, worker_key=key, pending=pending)

    monkeypatch.setattr(journal, "database_journal", locked)
    await run_fleets.database_fleets(
        run_fleets.fleet_environments(source), engine=object(), factory=object()
    )
    assert len([e for e in events if e[0] == "recover"]) == 2
    assert not any(e[0] in {"collect", "prepare", "project"} for e in events)
    assert json.loads(capsys.readouterr().out) == {
        "stage": "fleet_recovery_complete",
        "fresh_collection": False,
    }


def test_invalid_configuration_cli_never_logs_private_values():
    result = subprocess.run(
        [sys.executable, "-m", "scripts.motive_drivers.run_fleets"],
        env={
            **os.environ,
            **environment(),
            run_fleets.EXTRA_FLEETS: '["PRIVATE_TEST_VALUE"]',
        },
        cwd=Path(__file__).parents[1],
        capture_output=True,
        check=False,
        text=True,
        timeout=10,
    )
    assert result.returncode == 1
    assert "PRIVATE_TEST_VALUE" not in result.stdout + result.stderr
    assert "Traceback" not in result.stdout + result.stderr
    assert (
        json.loads(result.stdout.splitlines()[-1])["code"]
        == "invalid_fleet_configuration"
    )


@pytest.mark.asyncio
async def test_source_age_is_checked_again_before_each_fleet_projection(
    batch_harness, monkeypatch
):
    from datetime import timedelta

    from app.services import fleet_telemetry

    source, events, _, runner, _ = batch_harness
    original = runner.run

    async def slow_first(*args, **kwargs):
        result = await original(*args, **kwargs)
        stamp = fleet_telemetry.now()
        monkeypatch.setattr(
            fleet_telemetry, "now", lambda: stamp + timedelta(minutes=31)
        )
        return result

    monkeypatch.setattr(runner, "run", slow_first)
    with pytest.raises(ValueError, match="fresh projection window"):
        await run_fleets.database_fleets(
            run_fleets.fleet_environments(source), engine=object(), factory=object()
        )
    assert len([e for e in events if e[0] == "collect"]) == 1
    assert len([e for e in events if e[0] == "project"]) == 1
    assert len([e for e in events if e[0] == "unlock"]) == 2
