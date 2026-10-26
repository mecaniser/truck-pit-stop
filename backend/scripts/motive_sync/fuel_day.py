"""One immutable planned fuel day; successful exit requires exact saved proof."""

import argparse
import asyncio
import json
import os
from pathlib import Path
from uuid import UUID

from scripts.motive_sync.fuel_coverage import (
    private_read,
    scope,
    validate_plan,
    validate_receipt,
)
from scripts.motive_sync.fuel_runner import run, timestamp


def expected_scope():
    return scope(
        *(
            os.environ[k]
            for k in (
                "MOTIVE_SYNC_TENANT_ID",
                "MOTIVE_SYNC_ACTOR_ID",
                "MOTIVE_COMPANY_ID",
                "MOTIVE_COMPANY_LABEL",
            )
        ),
        os.environ.get("MOTIVE_FUEL_BASELINE", "2026-08-15"),
    )


def verify(source_path, plan_path, day):
    plan = private_read(plan_path)
    expected = expected_scope()
    source = private_read(source_path)
    validate_plan(plan, expected, timestamp(source["started_at"]))
    if source.get("plan") != plan or source.get("report_dates") != [day]:
        raise ValueError("Fuel day source plan mismatch")
    return validate_receipt(
        Path(source_path).with_name("receipt.json"), expected, plan=plan, day=day
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True)
    parser.add_argument("--plan", required=True)
    parser.add_argument("--day", required=True)
    parser.add_argument("--verify-only", action="store_true")
    args = parser.parse_args()
    if not args.verify_only:
        from app.db.session import AsyncSessionLocal

        expected = expected_scope()
        source = private_read(args.input)
        plan = private_read(args.plan)
        if source.get("plan") != plan or source.get("report_dates") != [args.day]:
            raise ValueError("Fuel day source plan mismatch")
        validate_plan(plan, expected, timestamp(source["started_at"]))
        if (
            Path(args.input).parent.name != args.day
            or Path(args.input).parent.parent.name != plan["run_id"]
            or Path(args.plan).parent != Path(args.input).parent.parent
        ):
            raise ValueError("Fuel day path binding mismatch")
        if os.environ.get("MOTIVE_FUEL_COMMIT") != "true":
            raise ValueError("Durable fuel catchup requires explicit commit")
        asyncio.run(
            run(
                AsyncSessionLocal,
                source,
                UUID(expected["tenant_id"]),
                UUID(expected["actor_id"]),
                expected["company_label"],
                expected["company_id"],
                Path(args.input).with_name("receipt.json"),
                commit=True,
                plan=plan,
            )
        )
    verify(args.input, args.plan, args.day)
    print(json.dumps({"stage": "fuel_day_verified", "day": args.day}), flush=True)


if __name__ == "__main__":
    main()
