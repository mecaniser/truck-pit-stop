"""Run one bounded daily fuel reconciliation; commit is explicitly opt-in."""

import fcntl
import json
import os
import subprocess
import sys
from pathlib import Path

from scripts.motive_sync.lifecycle import FuelLifecycle
from scripts.motive_sync.recovery import collection_directory, entry, read_process


def recover_pending(state, observer=None):
    """Reconcile uncertain commits before reading a new provider observation."""
    for receipt in sorted(state.glob("*/receipt.json")):
        previous = json.loads(receipt.read_text())
        if previous.get("mode") != "commit" or previous.get("stage") not in {
            "validated",
            "commit_pending",
            "committed",
        }:
            continue
        if os.environ.get("MOTIVE_FUEL_COMMIT", "false") != "true":
            raise RuntimeError(
                "Pending fuel commit requires reconciliation; saving is disabled"
            )
        if observer is not None:
            observer.recovery_attempt()
        subprocess.run(
            [
                sys.executable,
                "-m",
                "scripts.motive_sync.fuel_runner",
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
            raise RuntimeError("Previous fuel commit remains unverified")
        if observer is not None:
            observer.recovery_verified()


def main(observer=None):
    observer = observer or FuelLifecycle(commit_enabled=os.environ.get("MOTIVE_FUEL_COMMIT") == "true")
    state = Path(os.environ.get("MOTIVE_FUEL_STATE_DIR", "/data/motive-fuel"))
    state.mkdir(parents=True, exist_ok=True, mode=0o700)
    with (state / "worker.lock").open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise SystemExit("Motive fuel worker already running") from None
        observer.enter("recovery")
        recover_pending(state, observer)
        run = collection_directory(state)
        source, receipt = run / "source.json", run / "receipt.json"
        try:
            observer.enter("collection")
            read_process(
                [
                    "node",
                    str(Path(__file__).with_name("collect_fuel.cjs")),
                    str(source),
                ],
                check=True,
                timeout=1800,
                observer=observer,
            )
            command = [
                sys.executable,
                "-m",
                "scripts.motive_sync.fuel_runner",
                "--input",
                str(source),
                "--receipt",
                str(receipt),
            ]
            if os.environ.get("MOTIVE_FUEL_COMMIT", "false") == "true":
                command.append("--commit")
            observer.enter("import")
            subprocess.run(command, check=True, timeout=600)
            observer.enter("complete")
            print(
                json.dumps(
                    {"stage": "fuel_worker_complete", "receipt_file": str(receipt)}
                ),
                flush=True,
            )
        except (subprocess.SubprocessError, OSError) as error:
            if observer.stage != "collection":
                observer.failed(error)
            print(
                json.dumps(
                    {
                        "stage": "fuel_worker_failed",
                        "source_file": str(source),
                        "receipt_file": str(receipt),
                    }
                ),
                flush=True,
            )
            raise SystemExit(1) from None


if __name__ == "__main__":
    lifecycle = FuelLifecycle(commit_enabled=os.environ.get("MOTIVE_FUEL_COMMIT") == "true")
    entry(lambda: main(lifecycle), observer=lifecycle)
