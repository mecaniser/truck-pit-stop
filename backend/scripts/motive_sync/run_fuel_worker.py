"""Run one bounded daily fuel reconciliation; commit is explicitly opt-in."""

import fcntl
import json
import os
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from scripts.motive_sync import fuel_coverage
from scripts.motive_sync.fuel_day import expected_scope
from scripts.motive_sync.lifecycle import FuelLifecycle
from scripts.motive_sync.recovery import collection_directory, entry, read_process
from scripts.motive_sync.trip_runner import immutable_json


def recover_pending(state, observer=None):
    """Reconcile uncertain commits before reading a new provider observation."""
    for intent in state.glob("*/????-??-??/receipt.json.normalized.json"):
        fuel_coverage.private_read(intent, state)
        if not intent.with_name("receipt.json").exists():
            raise RuntimeError(
                "Fuel normalized intent without receipt requires reconciliation"
            )
    for receipt in sorted(
        [*state.glob("*/receipt.json"), *state.glob("*/????-??-??/receipt.json")]
    ):
        previous = fuel_coverage.private_read(receipt, state)
        daily = receipt.parent.parent != state
        if daily and (
            previous.get("mode") != "commit"
            or previous.get("stage")
            not in {"validated", "commit_pending", "committed", "verified"}
        ):
            raise RuntimeError("Unknown daily fuel receipt requires reconciliation")
        if daily and previous.get("stage") == "verified":
            fuel_coverage.validate_receipt(receipt, expected_scope())
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
        if fuel_coverage.private_read(receipt, state).get("stage") != "verified":
            raise RuntimeError("Previous fuel commit remains unverified")
        if daily:
            fuel_coverage.validate_receipt(receipt, expected_scope())
        if observer is not None:
            observer.recovery_verified()


def run_catchup(state, observer):
    stamp = datetime.now(UTC)
    expected = expected_scope()
    pin = state / "scope.json"
    if pin.exists() and fuel_coverage.private_read(pin, state) != expected:
        raise ValueError("Fuel pinned scope changed")
    immutable_json(pin, expected)
    index = fuel_coverage.verified_days(state, expected)
    history = fuel_coverage.plans(state, expected, stamp)
    start, end = os.environ.get("MOTIVE_FUEL_FROM"), os.environ.get("MOTIVE_FUEL_TO")
    if bool(start) != bool(end):
        raise ValueError("Both explicit fuel range bounds required")
    days, lane = fuel_coverage.plan_days(
        expected,
        stamp,
        index,
        history,
        maximum=int(os.environ.get("MOTIVE_FUEL_MAX_DAYS", "7")),
        explicit=(start, end) if start else None,
    )
    if not days:
        observer.enter("complete")
        return
    run_id = str(uuid4())
    run = state / run_id
    run.mkdir(mode=0o700)
    plan = {
        "version": 1,
        "scope": expected,
        "run_id": run_id,
        "created_at": stamp.isoformat(),
        "mode": "explicit" if start else "automatic",
        "first_lane": lane,
        "days": days,
    }
    immutable_json(run / "plan.json", plan)
    observer.batch_import_possible = True
    observer.enter("collection")
    read_process(
        [
            "node",
            str(Path(__file__).with_name("collect_fuel.cjs")),
            str(run / "source.json"),
            "--plan",
            str(run / "plan.json"),
        ],
        check=True,
        timeout=1800,
        observer=observer,
    )
    # Child success alone is insufficient. Validate every exact receipt again
    # against this immutable run plan before reporting completion.
    for day in days:
        fuel_coverage.validate_receipt(
            run / day / "receipt.json", expected, plan=plan, day=day
        )
    observer.enter("complete")
    print(
        json.dumps(
            {
                "stage": "fuel_worker_complete",
                "dates": len(days),
                "complete_through": fuel_coverage.complete_through(
                    expected, fuel_coverage.verified_days(state, expected)
                ),
            }
        ),
        flush=True,
    )


def main(observer=None):
    observer = observer or FuelLifecycle(
        commit_enabled=os.environ.get("MOTIVE_FUEL_COMMIT") == "true"
    )
    state = Path(os.environ.get("MOTIVE_FUEL_STATE_DIR", "/data/motive-fuel"))
    if state.is_symlink():
        raise ValueError("Fuel state directory is symlinked")
    state.mkdir(parents=True, exist_ok=True, mode=0o700)
    with (state / "worker.lock").open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise SystemExit("Motive fuel worker already running") from None
        observer.enter("recovery")
        recover_pending(state, observer)
        # Dry-run/manual legacy use keeps its original recent-window behavior.
        # Committing scheduled runs always use the durable automatic planner.
        if os.environ.get("MOTIVE_FUEL_COMMIT") == "true":
            run_catchup(state, observer)
            return
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
    lifecycle = FuelLifecycle(
        commit_enabled=os.environ.get("MOTIVE_FUEL_COMMIT") == "true"
    )
    entry(lambda: main(lifecycle), observer=lifecycle)
