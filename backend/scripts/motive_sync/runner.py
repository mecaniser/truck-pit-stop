"""One-shot worker; explicit --commit, no scheduling or provider activation."""

import argparse
import asyncio
import fcntl
import json
import os
from pathlib import Path
from uuid import UUID

from scripts.motive_sync.import_locations import run_import


def private_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    temporary = path.with_suffix(path.suffix + ".tmp")
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w") as stream:
        json.dump(value, stream, indent=2, default=str)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True)
    parser.add_argument("--receipt", required=True)
    parser.add_argument("--lock", default="/tmp/dieselbridge-motive-sync.lock")
    parser.add_argument("--commit", action="store_true")
    args = parser.parse_args()
    required = [
        "MOTIVE_SYNC_TENANT_ID",
        "MOTIVE_SYNC_ACTOR_ID",
        "MOTIVE_COMPANY_LABEL",
        "MOTIVE_COMPANY_ID",
    ]
    if any(not os.environ.get(key) for key in required):
        parser.error("Explicit tenant, actor and company configuration required")
    # Process-level lock complements capture() tenant DB serialization.
    with open(args.lock, "a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise SystemExit("Another Motive worker is running") from None
        from app.db.session import AsyncSessionLocal

        document = json.loads(Path(args.input).read_text())
        result = asyncio.run(
            run_import(
                AsyncSessionLocal,
                document,
                UUID(os.environ["MOTIVE_SYNC_TENANT_ID"]),
                UUID(os.environ["MOTIVE_SYNC_ACTOR_ID"]),
                os.environ["MOTIVE_COMPANY_LABEL"],
                os.environ["MOTIVE_COMPANY_ID"],
                args.commit,
            )
        )
        private_json(args.receipt, result)
        counts = {}
        for row in result["rows"]:
            counts[row["status"]] = counts.get(row["status"], 0) + 1
        print(
            json.dumps(
                {
                    "mode": result["mode"],
                    "committed": result["committed"],
                    "counts": counts,
                }
            )
        )


if __name__ == "__main__":
    main()
