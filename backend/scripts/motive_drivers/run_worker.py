"""Collect once, preserve source evidence, then validate/import through runner.

No scheduler is enabled here. Default is a rollback-only dry run.
"""

import asyncio
import fcntl
import json
import os
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4


async def recover_database(journal, factory, *, commit):
    from scripts.motive_drivers.runner import run

    pending = await journal.pending()
    if pending and not commit:
        raise RuntimeError(
            "Pending driver commit requires reconciliation; saving is disabled"
        )
    identity = journal.identity
    for durable in pending:
        saved = await durable.load()
        receipt = await run(
            factory,
            saved["source"],
            identity.tenant_id,
            identity.actor_id,
            identity.company_label,
            identity.company_id,
            None,
            commit=True,
            recovery=True,
            expected_customer_id=identity.customer_id,
            durable=durable,
        )
        if receipt["stage"] != "verified":
            raise RuntimeError("Previous driver commit remains unverified")


async def database_worker(state, *, engine=None, factory=None):
    from scripts.motive_drivers.journal import (
        Identity,
        authorize_configuration,
        database_journal,
    )
    from scripts.motive_drivers.runner import run

    if engine is None or factory is None:
        from app.db.session import AsyncSessionLocal
        from app.db.session import engine as application_engine

        engine, factory = application_engine, AsyncSessionLocal
    identity = Identity.from_environment()
    commit = os.environ.get("MOTIVE_DRIVER_COMMIT", "false") == "true"
    async with database_journal(
        engine, identity, os.environ.get("MOTIVE_DRIVER_JOURNAL_KEY", "motive-driver")
    ) as journal:
        await authorize_configuration(factory, identity)
        await recover_database(journal, factory, commit=commit)
        directory = state / (
            datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ") + "-" + str(uuid4())
        )
        directory.mkdir(mode=0o700)
        source, receipt_file = directory / "source.json", directory / "receipt.json"
        # No shell, provider credentials or source values are emitted here.
        await asyncio.to_thread(
            subprocess.run,
            ["node", str(Path(__file__).with_name("collect.cjs")), str(source)],
            check=True,
            timeout=1500,
        )
        document = json.loads(source.read_text())
        durable = await journal.create(document, commit=commit)
        receipt = await run(
            factory,
            document,
            identity.tenant_id,
            identity.actor_id,
            identity.company_label,
            identity.company_id,
            receipt_file,
            commit=commit,
            expected_customer_id=identity.customer_id,
            durable=durable,
        )
        print(
            json.dumps(
                {
                    "stage": "worker_complete",
                    "journal_run_id": str(durable.id),
                    "receipt_stage": receipt["stage"],
                    "committed": receipt["committed"],
                }
            ),
            flush=True,
        )


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
        if os.environ.get("MOTIVE_DRIVER_COMMIT", "false") != "true":
            raise RuntimeError(
                "Pending driver commit requires reconciliation; saving is disabled"
            )
        subprocess.run(
            [
                sys.executable,
                "-m",
                "scripts.motive_drivers.runner",
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
            raise RuntimeError("Previous driver commit remains unverified")


def main():
    mode = os.environ.get("MOTIVE_DRIVER_JOURNAL", "file")
    if mode not in {"file", "database"}:
        raise ValueError("Unsupported driver journal mode")
    state = Path(
        os.environ.get(
            "MOTIVE_DRIVER_STATE_DIR",
            "/tmp/motive-driver" if mode == "database" else "/data/motive-driver",
        )
    )
    state.mkdir(parents=True, exist_ok=True, mode=0o700)
    if mode == "database":
        asyncio.run(database_worker(state))
        return
    with (state / "worker.lock").open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise SystemExit("Motive driver worker already running") from None
        recover_pending(state)
        run = state / (
            datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ") + "-" + str(uuid4())
        )
        run.mkdir(mode=0o700)
        source, receipt = run / "source.json", run / "receipt.json"
        try:
            subprocess.run(
                ["node", str(Path(__file__).with_name("collect.cjs")), str(source)],
                check=True,
                timeout=1500,
            )
            command = [
                sys.executable,
                "-m",
                "scripts.motive_drivers.runner",
                "--input",
                str(source),
                "--receipt",
                str(receipt),
            ]
            if os.environ.get("MOTIVE_DRIVER_COMMIT", "false") == "true":
                command.append("--commit")
            subprocess.run(command, check=True, timeout=600)
            print(
                json.dumps({"stage": "worker_complete", "receipt_file": str(receipt)}),
                flush=True,
            )
        except (subprocess.SubprocessError, OSError):
            print(
                json.dumps(
                    {
                        "stage": "worker_failed",
                        "source_file": str(source),
                        "receipt_file": str(receipt),
                    }
                ),
                flush=True,
            )
            raise SystemExit(1) from None


if __name__ == "__main__":
    try:
        main()
    except Exception:  # noqa: BLE001 - process boundary must not leak provider values
        # Includes pre-collection recovery/receipt parsing errors. Do not render
        # provider data, subprocess argv, or exception values in service logs.
        print(
            json.dumps(
                {"stage": "worker_failed", "code": "driver_record_worker_failed"}
            ),
            flush=True,
        )
        raise SystemExit(1) from None
