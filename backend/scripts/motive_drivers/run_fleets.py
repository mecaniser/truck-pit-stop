"""Run explicitly configured local fleets through isolated driver journals.

One Motive account may operate trucks belonging to several local fleets. Each
child retains the normal exact-VIN/current-membership checks and its own durable
identity, recovery checkpoints, source observation, and advisory lock.
"""

import asyncio
import json
import os
import re
import subprocess
import sys
from contextlib import AsyncExitStack
from pathlib import Path
from uuid import UUID

from scripts.motive_sync.recovery import (
    collection_directory,
    install_signals,
    read_process,
)

EXTRA_FLEETS = "MOTIVE_DRIVER_ADDITIONAL_FLEET_CUSTOMER_IDS"


def fleet_environments(environment):
    """Validate every target before any child can collect or write data."""
    extras = json.loads(environment.get(EXTRA_FLEETS, "[]"))
    if not isinstance(extras, list) or len(extras) > 8:
        raise ValueError("Expected at most eight additional fleets")
    primary = environment["MOTIVE_DRIVER_FLEET_CUSTOMER_ID"]
    customer_ids = [primary, *extras]
    if any(
        not isinstance(value, str) or str(UUID(value)) != value
        for value in customer_ids
    ) or len(set(customer_ids)) != len(customer_ids):
        raise ValueError("Fleet IDs must be distinct canonical UUIDs")
    mode = environment.get("MOTIVE_DRIVER_JOURNAL", "file")
    if mode not in {"file", "database"} or (extras and mode != "database"):
        raise ValueError("Additional fleets require database journaling")
    key = environment.get("MOTIVE_DRIVER_JOURNAL_KEY", "motive-driver")
    state = Path(
        environment.get(
            "MOTIVE_DRIVER_STATE_DIR",
            "/tmp/motive-driver" if mode == "database" else "/data/motive-driver",
        )
    )
    children = []
    for ordinal, customer_id in enumerate(customer_ids):
        child_key = key if ordinal == 0 else f"{key}.{customer_id}"
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,119}", child_key):
            raise ValueError("Invalid stable per-fleet journal key")
        child = dict(environment)
        child.pop(EXTRA_FLEETS, None)
        child["MOTIVE_DRIVER_FLEET_CUSTOMER_ID"] = customer_id
        child["MOTIVE_DRIVER_JOURNAL_KEY"] = child_key
        child["MOTIVE_DRIVER_STATE_DIR"] = str(
            state if ordinal == 0 else state / customer_id
        )
        children.append(child)
    return children


async def database_fleets(children, *, engine=None, factory=None):
    """Collect once; keep every fleet's lock, authorization and journal separate."""
    from scripts.motive_drivers.journal import (
        Identity,
        authorize_configuration,
        database_journal,
        prepare_batch,
    )
    from scripts.motive_drivers.run_worker import (
        recover_database,
        validate_fresh_source,
    )
    from scripts.motive_drivers.runner import run

    if engine is None or factory is None:
        from app.db.session import AsyncSessionLocal
        from app.db.session import engine as application_engine

        engine, factory = application_engine, AsyncSessionLocal
    commit = children[0].get("MOTIVE_DRIVER_COMMIT", "false") == "true"
    async with AsyncExitStack() as stack:
        journals = {}
        # Stable ordering avoids deadlocks against another overlapping fleet batch.
        for child in sorted(children, key=lambda c: c["MOTIVE_DRIVER_JOURNAL_KEY"]):
            identity = Identity.from_environment(child)
            journal = await stack.enter_async_context(
                database_journal(
                    engine,
                    identity,
                    child["MOTIVE_DRIVER_JOURNAL_KEY"],
                )
            )
            await authorize_configuration(factory, identity)
            journals[child["MOTIVE_DRIVER_JOURNAL_KEY"]] = journal
        ordered = [journals[child["MOTIVE_DRIVER_JOURNAL_KEY"]] for child in children]
        recovered = []
        # Reconcile uncertain commits first. Old source-only rows remain immutable
        # evidence and are skipped without blocking a legitimate fresh collection.
        for journal in ordered:
            recovered.append(await recover_database(journal, factory, commit=commit))
        if any(recovered):
            print(
                json.dumps(
                    {"stage": "fleet_recovery_complete", "fresh_collection": False}
                ),
                flush=True,
            )
            return
        state = Path(children[0]["MOTIVE_DRIVER_STATE_DIR"])
        state.mkdir(parents=True, exist_ok=True, mode=0o700)
        directory = collection_directory(state)
        source = directory / "source.json"
        print(
            json.dumps({"stage": "driver_source_start", "fleet_count": len(children)}),
            flush=True,
        )
        await asyncio.to_thread(
            read_process,
            ["node", str(Path(__file__).with_name("collect.cjs")), str(source)],
            env={
                **children[0],
                "MOTIVE_DRIVER_COLLECTION_FLEETS": json.dumps(
                    sorted(
                        child["MOTIVE_DRIVER_FLEET_CUSTOMER_ID"] for child in children
                    )
                ),
            },
            check=True,
            timeout=1500,
        )
        document = json.loads(source.read_text())
        validate_fresh_source(
            document, ordered[0].identity.company_label, ordered[0].identity.company_id
        )
        durable = await prepare_batch(ordered, document, commit=commit)
        for ordinal, (journal, saved) in enumerate(
            zip(ordered, durable, strict=True), start=1
        ):
            identity = journal.identity
            validate_fresh_source(document, identity.company_label, identity.company_id)
            # The existing runner rechecks current membership, assignment and
            # per-fleet authority; a shared provider read grants no local access.
            receipt = await run(
                factory,
                document,
                identity.tenant_id,
                identity.actor_id,
                identity.company_label,
                identity.company_id,
                None,
                commit=commit,
                expected_customer_id=identity.customer_id,
                durable=saved,
            )
            if receipt["stage"] != ("verified" if commit else "validated"):
                raise RuntimeError("Fleet projection remains unverified")
            print(
                json.dumps(
                    {
                        "stage": "fleet_projection_complete",
                        "fleet_ordinal": ordinal,
                        "receipt_stage": receipt["stage"],
                        "committed": receipt["committed"],
                    }
                ),
                flush=True,
            )
        print(
            json.dumps(
                {
                    "stage": "fleets_complete",
                    "fleet_count": len(children),
                    "source_collections": 1,
                }
            ),
            flush=True,
        )


def main():
    children = fleet_environments(os.environ)
    if children[0].get("MOTIVE_DRIVER_JOURNAL", "file") == "database":
        asyncio.run(database_fleets(children))
        return
    for ordinal, environment in enumerate(children, start=1):
        try:
            subprocess.run(
                [sys.executable, "-m", "scripts.motive_drivers.run_worker"],
                env=environment,
                check=True,
                timeout=2400,
            )
        except (subprocess.SubprocessError, OSError):
            print(
                json.dumps(
                    {
                        "stage": "fleet_worker_failed",
                        "fleet_ordinal": ordinal,
                        "fleet_count": len(children),
                    }
                ),
                flush=True,
            )
            raise SystemExit(1) from None
    print(
        json.dumps(
            {
                "stage": "fleets_complete",
                "fleet_count": len(children),
            }
        ),
        flush=True,
    )


if __name__ == "__main__":
    install_signals()
    print(json.dumps({"stage": "worker_start"}), flush=True)
    try:
        main()
    except Exception:  # noqa: BLE001 - keep private configuration out of process logs
        print(
            json.dumps(
                {
                    "stage": "fleet_worker_failed",
                    "code": "invalid_fleet_configuration",
                }
            ),
            flush=True,
        )
        raise SystemExit(1) from None
