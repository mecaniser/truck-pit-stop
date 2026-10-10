"""Run explicitly configured local fleets through isolated driver journals.

One Motive account may operate trucks belonging to several local fleets. Each
child retains the normal exact-VIN/current-membership checks and its own durable
identity, recovery checkpoints, source observation, and advisory lock.
"""

import json
import os
import re
import subprocess
import sys
from pathlib import Path
from uuid import UUID

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


def main():
    children = fleet_environments(os.environ)
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
