"""Run one bounded daily trip reconciliation; commit is explicitly opt-in."""

from datetime import datetime, timezone
from uuid import uuid4
import fcntl
import json
import os
import subprocess
import sys
from pathlib import Path

from scripts.motive_sync import trip_coverage, trip_rejection
from scripts.motive_sync.runner import private_json
from scripts.motive_sync.recovery import entry, read_process


def recover_pending(state):
    """Reconcile uncertain commits before reading a new provider observation."""
    for receipt in sorted(state.rglob("receipt.json")):
        previous = trip_coverage.private_read(receipt, state)
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
        trip_coverage.private_read(receipt.with_name("source.json"), state)
        trip_coverage.private_read(Path(str(receipt) + ".normalized.json"), state)
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
        if trip_coverage.private_read(receipt, state).get("stage") != "verified":
            raise RuntimeError("Previous trip commit remains unverified")


def main():
    state = Path(os.environ.get("MOTIVE_TRIPS_STATE_DIR", "/data/motive-trips"))
    if state.is_symlink():
        raise ValueError("Trip state directory is symlinked")
    state.mkdir(parents=True, exist_ok=True, mode=0o700)
    with (state / "worker.lock").open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise SystemExit("Motive trip worker already running") from None
        recover_pending(state)
        expected = trip_coverage.scope(
            os.environ["MOTIVE_SYNC_TENANT_ID"], os.environ["MOTIVE_SYNC_ACTOR_ID"],
            os.environ["MOTIVE_COMPANY_ID"], os.environ["MOTIVE_COMPANY_LABEL"],
            os.environ.get("MOTIVE_TRIPS_BASELINE", "2026-04-01"))
        binding_file = state / "coverage-scope.json"
        if binding_file.exists():
            if trip_coverage.private_read(binding_file) != expected:
                raise ValueError("Persisted trip coverage scope changed; explicit reconciliation required")
        else:
            from scripts.motive_sync.trip_runner import immutable_json
            immutable_json(binding_file, expected)
        today = datetime.now(trip_coverage.ZONE).date()
        examined = trip_coverage.verified_days(state, expected)
        plan = trip_coverage.plan_days(expected, today, examined,
            limit=int(os.environ.get("MOTIVE_TRIPS_MAX_DAYS", "14")),
            start=os.environ.get("MOTIVE_TRIPS_FROM"), end=os.environ.get("MOTIVE_TRIPS_TO"))
        run = state / (datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + str(uuid4()))
        run.mkdir(mode=0o700)
        source, receipt = run / "source.json", run / "receipt.json"
        plan_file = run / "plan.json"
        private_json(plan_file, plan)
        try:
            read_process(
                ["node", str(Path(__file__).with_name("collect_trips.cjs")), str(source)],
                check=True, timeout=1800,
                env={**os.environ, "MOTIVE_TRIPS_PLAN_FILE": str(plan_file),
                     "MOTIVE_TRIPS_PYTHON": sys.executable},
            )
            collection = trip_coverage.private_read(source, state)
            rejection_rows = collection.get('rejected_days', [])
            if not isinstance(rejection_rows, list):
                raise RuntimeError('Invalid partial collection evidence')
            rejected = {row['day']: row for row in rejection_rows}
            if len(rejected) != len(rejection_rows) or not set(rejected) <= set(plan['days']):
                raise RuntimeError('Invalid rejected days')
            for day in plan["days"]:
                if day in rejected:
                    checked = trip_rejection.validate_rejection(run / day / 'source.json',
                        expected, rejected[day]['nonce'], collection['started_at'])
                    if checked != rejected[day]:
                        raise RuntimeError('Rejected day evidence mismatch')
                    continue
                saved = trip_coverage.private_read(run / day / "receipt.json", state)
                required_stage = "verified" if os.environ.get("MOTIVE_TRIPS_COMMIT", "false") == "true" else "validated"
                if saved.get("stage") != required_stage:
                    raise RuntimeError("Planned daily receipt incomplete")
            print(json.dumps({"stage": "trip_worker_partial" if rejected else "trip_worker_complete",
                "acceptance": "PARTIAL" if rejected else "complete", "rejected_days": sorted(rejected),
                "rejections": rejection_rows, "planned_days": len(plan["days"]),
                "coverage": trip_coverage.summarize(expected, trip_coverage.verified_days(state, expected), today)}), flush=True)
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
    entry(main)
