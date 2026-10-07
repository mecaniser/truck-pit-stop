"""The dedicated worker defaults to no writes and preserves its private run evidence."""

import fcntl
import json
import subprocess
from pathlib import Path

import pytest
from scripts.motive_health import run_worker


def test_dry_run_and_explicit_commit_are_separate(tmp_path, monkeypatch):
    monkeypatch.setenv("MOTIVE_HEALTH_STATE_DIR", str(tmp_path))
    monkeypatch.delenv("MOTIVE_HEALTH_COMMIT", raising=False)
    calls = []
    monkeypatch.setattr(
        run_worker.subprocess, "run", lambda command, **kwargs: calls.append(command)
    )
    run_worker.main()
    assert len(calls) == 2
    assert calls[1][2] == "scripts.motive_health.runner"
    assert "--commit" not in calls[1]
    assert Path(calls[0][-1]).parent.stat().st_mode & 0o777 == 0o700
    monkeypatch.setenv("MOTIVE_HEALTH_COMMIT", "true")
    run_worker.main()
    assert "--commit" in calls[-1]
    monkeypatch.setenv("MOTIVE_HEALTH_COMMIT", "TRUE")
    run_worker.main()
    assert "--commit" not in calls[-1]


def test_failed_capture_never_invokes_import(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("MOTIVE_HEALTH_STATE_DIR", str(tmp_path))
    calls = []

    def fail(command, **kwargs):
        calls.append(command)
        raise subprocess.CalledProcessError(1, command)

    monkeypatch.setattr(run_worker.subprocess, "run", fail)
    with pytest.raises(SystemExit):
        run_worker.main()
    assert len(calls) == 1
    result = json.loads(capsys.readouterr().out)
    assert result["stage"] == "worker_failed"
    assert Path(result["source_file"]).name == "source.json"


def test_exclusive_lock_prevents_second_collector(tmp_path, monkeypatch):
    monkeypatch.setenv("MOTIVE_HEALTH_STATE_DIR", str(tmp_path))
    with (tmp_path / "worker.lock").open("a") as held:
        fcntl.flock(held, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with pytest.raises(SystemExit, match="already running"):
            run_worker.main()


@pytest.mark.parametrize("stage", ["validated", "commit_pending", "committed"])
def test_pending_commit_blocks_new_capture_when_saving_disabled(
    tmp_path, monkeypatch, stage
):
    monkeypatch.setenv("MOTIVE_HEALTH_STATE_DIR", str(tmp_path))
    monkeypatch.delenv("MOTIVE_HEALTH_COMMIT", raising=False)
    previous = tmp_path / "previous"
    previous.mkdir()
    (previous / "receipt.json").write_text(
        json.dumps({"mode": "commit", "stage": stage})
    )
    calls = []
    monkeypatch.setattr(
        run_worker.subprocess, "run", lambda *args, **kwargs: calls.append(args)
    )
    with pytest.raises(RuntimeError, match="saving is disabled"):
        run_worker.main()
    assert calls == []
    assert [p.name for p in tmp_path.iterdir() if p.is_dir()] == ["previous"]


def test_recovery_reuses_saved_source_and_receipt_before_new_capture(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("MOTIVE_HEALTH_STATE_DIR", str(tmp_path))
    monkeypatch.setenv("MOTIVE_HEALTH_COMMIT", "true")
    previous = tmp_path / "previous"
    previous.mkdir()
    receipt = previous / "receipt.json"
    receipt.write_text(json.dumps({"mode": "commit", "stage": "commit_pending"}))
    calls = []

    def run(command, **kwargs):
        calls.append(command)
        if "--recover" in command:
            assert command[command.index("--input") + 1] == str(
                previous / "source.json"
            )
            assert command[command.index("--receipt") + 1] == str(receipt)
            receipt.write_text(json.dumps({"mode": "commit", "stage": "verified"}))

    monkeypatch.setattr(run_worker.subprocess, "run", run)
    run_worker.main()
    assert "--recover" in calls[0]
    assert calls[1][0] == "node"
    assert len(calls) == 3


def test_recovery_must_verify_before_new_capture(tmp_path, monkeypatch):
    monkeypatch.setenv("MOTIVE_HEALTH_STATE_DIR", str(tmp_path))
    monkeypatch.setenv("MOTIVE_HEALTH_COMMIT", "true")
    previous = tmp_path / "previous"
    previous.mkdir()
    (previous / "receipt.json").write_text(
        json.dumps({"mode": "commit", "stage": "committed"})
    )
    calls = []
    monkeypatch.setattr(
        run_worker.subprocess, "run", lambda command, **kwargs: calls.append(command)
    )
    with pytest.raises(RuntimeError, match="remains unverified"):
        run_worker.main()
    assert len(calls) == 1
    assert "--recover" in calls[0]
    assert [p.name for p in tmp_path.iterdir() if p.is_dir()] == ["previous"]
