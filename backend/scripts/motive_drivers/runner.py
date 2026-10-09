"""Receipt-backed driver record import; explicit commit and exact-source recovery."""

import argparse
import asyncio
import json
import os
from pathlib import Path
from uuid import UUID

from app.services import fleet_driver_records as service
from scripts.motive_drivers.import_records import batch, source_hash, validate
from scripts.motive_sync.runner import private_json


def immutable(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if path.exists():
        if json.loads(path.read_text()) != value:
            raise ValueError("Immutable driver record attempt changed")
        return
    with os.fdopen(
        os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "w"
    ) as stream:
        json.dump(value, stream, indent=2, allow_nan=False)
        stream.flush()
        os.fsync(stream.fileno())


async def run(
    factory,
    document,
    tenant_id,
    actor_id,
    company_label,
    company_id,
    receipt_path,
    *,
    commit=False,
    recovery=False,
    expected_customer_id=None,
):
    if not expected_customer_id:
        raise ValueError("Explicit fleet customer configuration required")
    validate(document, company_label, company_id, recovery=recovery)
    identity = {
        "tenant_id": str(tenant_id),
        "actor_id": str(actor_id),
        "company_id": company_id,
        "company_label": company_label,
        "expected_customer_id": str(expected_customer_id)
        if expected_customer_id
        else None,
        "source_sha256": source_hash(document),
    }
    attempt_path = str(receipt_path) + ".attempt.json"
    if recovery:
        if not commit:
            raise ValueError("Recovery requires explicit commit")
        receipt = json.loads(Path(receipt_path).read_text())
        attempt = json.loads(Path(attempt_path).read_text())
        if (
            receipt.get("mode") != "commit"
            or receipt.get("stage")
            not in {"validated", "commit_pending", "committed", "verified"}
            or receipt.get("attempt_sha256") != source_hash(attempt)
            or any(attempt.get(key) != value for key, value in identity.items())
        ):
            raise ValueError("Recovery intent or immutable identity mismatch")
        if (
            source_hash(
                json.loads(Path(str(receipt_path) + ".source.json").read_text())
            )
            != identity["source_sha256"]
        ):
            raise ValueError("Saved source evidence changed")
        eligible = set(attempt["eligible_requests"])
    else:
        eligible = None
    async with factory() as db:
        dry = await batch(
            db,
            document,
            tenant_id,
            actor_id,
            company_label,
            company_id,
            apply=False,
            expected_customer_id=expected_customer_id,
            eligible=eligible,
        )
        await db.rollback()
    eligible = {
        row["client_request_id"]
        for row in dry
        if row["status"] in {"would_create", "unchanged"}
    }
    if recovery and eligible != set(attempt["eligible_requests"]):
        raise ValueError("Recovery eligible captures changed")
    attempt = {**identity, "eligible_requests": sorted(eligible)}
    immutable(attempt_path, attempt)
    immutable(str(receipt_path) + ".source.json", document)
    receipt = {
        **identity,
        "attempt_sha256": source_hash(attempt),
        "mode": "commit" if commit else "dry_run",
        "stage": "validated",
        "committed": False,
        "rows": dry,
        "recovery": recovery,
    }
    private_json(receipt_path, receipt)
    if not commit:
        return receipt
    async with factory() as db:
        applied = await batch(
            db,
            document,
            tenant_id,
            actor_id,
            company_label,
            company_id,
            apply=True,
            expected_customer_id=expected_customer_id,
            eligible=eligible,
        )
        replay = await batch(
            db,
            document,
            tenant_id,
            actor_id,
            company_label,
            company_id,
            apply=True,
            expected_customer_id=expected_customer_id,
            eligible=eligible,
        )
        if any(
            row["status"] != "unchanged"
            for row in replay
            if row.get("client_request_id") in eligible
        ):
            raise ValueError("Driver record unchanged replay failed")
        receipt.update(stage="commit_pending", rows=applied)
        private_json(receipt_path, receipt)
        await db.commit()
    receipt.update(stage="committed", committed=True)
    private_json(receipt_path, receipt)
    async with factory() as db:
        verified = await batch(
            db,
            document,
            tenant_id,
            actor_id,
            company_label,
            company_id,
            apply=False,
            expected_customer_id=expected_customer_id,
            eligible=eligible,
        )
        saved_ids = {
            row["client_request_id"]: row["capture_id"]
            for row in applied
            if row.get("client_request_id") in eligible
        }
        for row in verified:
            if row.get("client_request_id") in eligible:
                if (
                    row["status"] != "unchanged"
                    or row["capture_id"] != saved_ids[row["client_request_id"]]
                ):
                    raise ValueError("Committed driver record readback mismatch")
                # Auth-independent current-member projection, same path as fleet API.
                projection = await service.read(db, tenant_id, UUID(row["vehicle_id"]))
                if projection.availability not in {
                    "available",
                    "assignment_unverified",
                }:
                    raise ValueError("Fleet driver record projection unavailable")
                # A verified provider observation can be retained even when the
                # local free-text label cannot safely be linked to that driver.
                row["projection"] = projection.availability
        await db.rollback()
    receipt.update(
        stage="verified",
        replay_unchanged=len(eligible),
        readback_verified=len(eligible),
        projection_available=sum(
            row.get("projection") == "available" for row in verified
        ),
        assignment_unverified=sum(
            row.get("projection") == "assignment_unverified" for row in verified
        ),
    )
    private_json(receipt_path, receipt)
    return receipt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True)
    parser.add_argument("--receipt", required=True)
    parser.add_argument("--commit", action="store_true")
    parser.add_argument("--recover", action="store_true")
    args = parser.parse_args()
    required = [
        "MOTIVE_SYNC_TENANT_ID",
        "MOTIVE_SYNC_ACTOR_ID",
        "MOTIVE_COMPANY_LABEL",
        "MOTIVE_COMPANY_ID",
    ]
    if any(not os.environ.get(key) for key in required):
        parser.error("Explicit tenant, actor and company configuration required")
    from app.db.session import AsyncSessionLocal

    expected = os.environ.get("MOTIVE_DRIVER_FLEET_CUSTOMER_ID")
    if not expected:
        parser.error("Explicit fleet customer configuration required")
    receipt = asyncio.run(
        run(
            AsyncSessionLocal,
            json.loads(Path(args.input).read_text()),
            UUID(os.environ[required[0]]),
            UUID(os.environ[required[1]]),
            os.environ[required[2]],
            os.environ[required[3]],
            args.receipt,
            commit=args.commit,
            recovery=args.recover,
            expected_customer_id=UUID(expected) if expected else None,
        )
    )
    counts = {}
    for row in receipt["rows"]:
        counts[row["status"]] = counts.get(row["status"], 0) + 1
    print(
        json.dumps(
            {
                "mode": receipt["mode"],
                "stage": receipt["stage"],
                "committed": receipt["committed"],
                "counts": counts,
            }
        )
    )


if __name__ == "__main__":
    try:
        main()
    except Exception:  # noqa: BLE001 - process boundary must not leak provider values
        # Pydantic includes rejected input values in its exception text. Provider
        # data belongs only in private source evidence, never process logs.
        print(
            json.dumps(
                {"stage": "runner_failed", "code": "driver_record_import_failed"}
            ),
            flush=True,
        )
        raise SystemExit(1) from None
