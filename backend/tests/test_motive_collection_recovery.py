"""Read recovery cannot replace import receipts or reuse expired private work."""

import json
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from scripts.motive_sync.recovery import collection_directory


def pending(tmp_path, stamp):
    directory = tmp_path / (stamp.strftime("%Y%m%dT%H%M%SZ") + "-" + str(uuid4()))
    directory.mkdir(mode=0o700)
    for name, value in [
        ("source.json", {"complete": False}),
        ("source.json.tasks.json", {"created_at": stamp.isoformat()}),
    ]:
        path = directory / name
        path.write_text(json.dumps(value))
        path.chmod(0o600)
    return directory


def test_process_replacement_resumes_same_private_read_work(tmp_path):
    stamp = datetime.now(UTC)
    prior = pending(tmp_path, stamp)
    assert collection_directory(tmp_path, now=stamp + timedelta(seconds=5)) == prior


@pytest.mark.parametrize(
    "reason", ["expired", "future", "receipt", "fatal", "complete"]
)
def test_no_stale_identity_failure_or_uncertain_write_replay(tmp_path, reason):
    stamp = datetime.now(UTC)
    prior = pending(tmp_path, stamp)
    if reason == "receipt":
        (prior / "receipt.json").write_text('{"stage":"commit_pending"}')
    if reason == "fatal":
        path = prior / "source.json.failure.json"
        path.write_text('{"retryable":false}')
        path.chmod(0o600)
    if reason == "complete":
        (prior / "source.json").write_text('{"complete":true}')
    offset = {"expired": 1900, "future": -1}.get(reason, 1)
    assert (
        collection_directory(tmp_path, now=stamp + timedelta(seconds=offset)) != prior
    )


def test_public_or_symlink_checkpoint_rejected(tmp_path):
    stamp = datetime.now(UTC)
    prior = pending(tmp_path, stamp)
    (prior / "source.json").chmod(0o644)
    with pytest.raises(ValueError, match="private"):
        collection_directory(tmp_path, now=stamp)
    (prior / "source.json").unlink()
    (prior / "source.json").symlink_to(prior / "source.json.tasks.json")
    with pytest.raises(ValueError, match="private"):
        collection_directory(tmp_path, now=stamp)


def test_timeout_and_normal_exit_reap_the_entire_browser_process_group(tmp_path):
    import subprocess
    import sys

    from scripts.motive_sync.recovery import read_process

    for behavior in ["hang", "exit"]:
        pidfile = tmp_path / (behavior + ".pid")
        code = (
            "import subprocess,sys,time; "
            "child=subprocess.Popen([sys.executable,'-c','import time; time.sleep(60)']); "
            f"open({str(pidfile)!r},'w').write(str(child.pid)); "
            + ("time.sleep(60)" if behavior == "hang" else "sys.exit(0)")
        )
        if behavior == "hang":
            with pytest.raises(subprocess.TimeoutExpired):
                read_process([sys.executable, "-c", code], timeout=0.5)
        else:
            read_process([sys.executable, "-c", code], timeout=5)
        pid = int(pidfile.read_text())
        # A terminated child may remain a zombie until the OS reaps it; it must
        # no longer run or hold browser sockets after the supervisor returns.
        status = subprocess.run(
            ["ps", "-p", str(pid), "-o", "stat="],
            capture_output=True,
            text=True,
            check=False,
        ).stdout.strip()
        assert not status or status.startswith("Z")
