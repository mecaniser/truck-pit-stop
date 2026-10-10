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


def test_runs_sequential_children_and_stops_on_failure(monkeypatch, capsys):
    source = environment()
    source[run_fleets.EXTRA_FLEETS] = json.dumps([str(uuid4()), str(uuid4())])
    monkeypatch.setattr(run_fleets.os, "environ", source)
    calls = []

    def child(command, **kwargs):
        calls.append(kwargs["env"])
        assert command == [sys.executable, "-m", "scripts.motive_drivers.run_worker"]
        assert kwargs["check"] is True
        assert kwargs["timeout"] == 2400
        if len(calls) == 2:
            raise subprocess.CalledProcessError(1, command, stderr="PRIVATE_TEST_VALUE")

    monkeypatch.setattr(run_fleets.subprocess, "run", child)
    with pytest.raises(SystemExit) as result:
        run_fleets.main()
    assert result.value.code == 1
    assert len(calls) == 2
    assert json.loads(capsys.readouterr().out) == {
        "stage": "fleet_worker_failed",
        "fleet_ordinal": 2,
        "fleet_count": 3,
    }


def test_success_preserves_explicit_commit_and_reports_complete(monkeypatch, capsys):
    source = {**environment(), "MOTIVE_DRIVER_COMMIT": "true"}
    monkeypatch.setattr(run_fleets.os, "environ", source)
    calls = []
    monkeypatch.setattr(
        run_fleets.subprocess, "run", lambda *a, **kw: calls.append(kw["env"])
    )
    run_fleets.main()
    assert len(calls) == 2
    assert all(child["MOTIVE_DRIVER_COMMIT"] == "true" for child in calls)
    assert json.loads(capsys.readouterr().out) == {
        "stage": "fleets_complete",
        "fleet_count": 2,
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
    assert json.loads(result.stdout)["code"] == "invalid_fleet_configuration"
