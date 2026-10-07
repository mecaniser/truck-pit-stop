"""Run one bounded daily trip reconciliation; commit is explicitly opt-in."""

import fcntl
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4


def recover_pending(state):
    """Reconcile uncertain commits before reading a new provider observation."""
    for receipt in sorted(state.glob("*/receipt.json")):
        previous = json.loads(receipt.read_text())
        if previous.get("mode") != "commit" or previous.get("stage") not in {
            "validated",
            "commit_pending",
            "committed",
        }:
            continue
        if os.environ.get("MOTIVE_TRIPS_COMMIT", "false") != "true":
            raise RuntimeError(
                "Pending trip commit requires reconciliation; saving is disabled"
            )
        subprocess.run(
            [
                sys.executable,
                "-m",
                "scripts.motive_sync.trip_runner",
                "--recover",
                "--commit",
                "--input",
                str(receipt.with_name("source.json")),
                "--receipt",
                str(receipt),
            ],
            check=True,
            timeout=600,
        )
        if json.loads(receipt.read_text()).get("stage") != "verified":
            raise RuntimeError("Previous trip commit remains unverified")


def main():
    state = Path(os.environ.get("MOTIVE_TRIPS_STATE_DIR", "/data/motive-trips"))
    state.mkdir(parents=True, exist_ok=True, mode=0o700)
    with (state / "worker.lock").open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise SystemExit("Motive trip worker already running") from None
        recover_pending(state)
        run = state / (
            datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + str(uuid4())
        )
        run.mkdir(mode=0o700)
        source, receipt = run / "source.json", run / "receipt.json"
        try:
            subprocess.run(
                [
                    "node",
                    str(Path(__file__).with_name("collect_trips.cjs")),
                    str(source),
                ],
                check=True,
                timeout=1800,
            )
            command = [
                sys.executable,
                "-m",
                "scripts.motive_sync.trip_runner",
                "--input",
                str(source),
                "--receipt",
                str(receipt),
            ]
            if os.environ.get("MOTIVE_TRIPS_COMMIT", "false") == "true":
                command.append("--commit")
            subprocess.run(command, check=True, timeout=600)
            print(
                json.dumps(
                    {"stage": "trip_worker_complete", "receipt_file": str(receipt)}
                ),
                flush=True,
            )
        except (subprocess.SubprocessError, OSError):
            print(
                json.dumps(
                    {
                        "stage": "trip_worker_failed",
                        "source_file": str(source),
                        "receipt_file": str(receipt),
                    }
                ),
                flush=True,
            )
            raise SystemExit(1) from None


if __name__ == "__main__":
    main()
