"""One immutable planned fuel day; successful exit requires exact saved proof."""

import argparse
import fcntl
import asyncio
import json
import os
from pathlib import Path
from datetime import timedelta
from uuid import UUID

from scripts.motive_sync.fuel_coverage import (
    private_read,
    scope,
    validate_plan,
    validate_receipt,
)
from scripts.motive_sync import fuel_runner
from scripts.motive_sync.fuel_runner import run, timestamp
from scripts.motive_sync.trip_runner import immutable_json


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


def bound_source(source_path, plan_path, day):
    source, plan, expected = (
        private_read(source_path),
        private_read(plan_path),
        expected_scope(),
    )
    if source.get("plan") != plan or source.get("report_dates") != [day]:
        raise ValueError("Fuel day source plan mismatch")
    validate_plan(plan, expected, timestamp(source["started_at"]))
    if (
        Path(source_path).parent.name != day
        or Path(source_path).parent.parent.name != plan["run_id"]
        or Path(plan_path).parent != Path(source_path).parent.parent
    ):
        raise ValueError("Fuel day path binding mismatch")
    return source, plan, expected


def verify_preview(source_path, plan_path, day):
    source, plan, expected = bound_source(source_path, plan_path, day)
    if plan["mode"] != "explicit" or len(plan["days"]) > 2:
        raise ValueError("Fuel preview requires an explicit maximum-two-date plan")
    fuel_runner.validate_source(
        source,
        expected["company_label"],
        expected["company_id"],
        timestamp(source["finished_at"]),
        recovery=True,
    )
    path = Path(source_path).with_name("preview.json")
    preview, normalized = (
        private_read(path),
        private_read(str(path) + ".normalized.json"),
    )
    identity = {
        key: expected[key]
        for key in ("tenant_id", "actor_id", "company_label", "company_id")
    }
    if (
        preview.get("mode") != "dry_run"
        or preview.get("stage") != "validated"
        or preview.get("committed") is not False
        or any(
            any(record.get(key) != value for key, value in identity.items())
            for record in (preview, normalized)
        )
        or preview.get("source_sha256") != fuel_runner.checksum(source)
        or normalized.get("source_sha256") != fuel_runner.checksum(source)
        or preview.get("normalized_sha256") != fuel_runner.checksum(normalized)
        or preview.get("coverage") != normalized.get("coverage")
        or normalized.get("coverage", {}).get("scope") != expected
        or normalized.get("coverage", {}).get("day") != day
        or len(preview.get("rows", [])) != len(normalized.get("rows", []))
        or any(
            row.get("action") not in {"would_create", "unchanged"}
            for row in preview.get("rows", [])
        )
    ):
        raise ValueError("Fuel preview immutable proof mismatch")
    return source, plan, expected, preview, normalized


def assert_preview_fresh(plan):
    created = timestamp(plan["created_at"])
    if (
        not timedelta(0)
        <= fuel_runner.importer.now() - created
        <= timedelta(minutes=30)
    ):
        raise ValueError("Fuel preview plan expired")


async def apply_preview(
    factory, source_path, plan_path, day, normalized_sha256, preview_sha256
):
    source, plan, expected, preview, normalized = verify_preview(
        source_path, plan_path, day
    )
    if (
        fuel_runner.checksum(preview) != preview_sha256
        or fuel_runner.checksum(normalized) != normalized_sha256
    ):
        raise ValueError("Fuel preview approval hash mismatch")
    receipt_path = Path(source_path).with_name("receipt.json")
    identity = (UUID(expected["tenant_id"]), UUID(expected["actor_id"]))
    if receipt_path.exists():
        saved = private_read(receipt_path)
        if (
            saved.get("approved_preview_sha256") != preview_sha256
            or fuel_runner.checksum(
                private_read(str(receipt_path) + ".normalized.json")
            )
            != normalized_sha256
        ):
            raise ValueError("Fuel saved preview approval mismatch")
        await run(
            factory,
            source,
            *identity,
            expected["company_label"],
            expected["company_id"],
            receipt_path,
            commit=True,
            recovery=True,
        )
        return verify(source_path, plan_path, day)
    validate_plan(plan, expected, fuel_runner.importer.now())
    assert_preview_fresh(plan)
    async with factory() as db:
        rows, report = await fuel_runner.prepare(db, source, *identity)
        dry = await fuel_runner.batches(db, rows, *identity)
        if (
            rows != normalized["rows"]
            or report != preview["report"]
            or dry != preview["rows"]
        ):
            raise ValueError("Fuel approved dry plan changed; reconcile before import")
        await db.rollback()
    validate_plan(plan, expected, fuel_runner.importer.now())
    assert_preview_fresh(plan)
    normal = str(receipt_path) + ".normalized.json"
    if Path(normal).exists():
        raise ValueError("Fuel orphan normal intent requires reconciliation")
    receipt = {**preview, "mode": "commit", "approved_preview_sha256": preview_sha256}

    def stage_intent():
        if receipt_path.exists() or Path(normal).exists():
            raise ValueError(
                "Fuel normal intent already exists; reconcile before import"
            )
        immutable_json(normal, normalized)
        fuel_runner.private_json(receipt_path, receipt)

    await fuel_runner.apply_verify(
        factory,
        normalized["rows"],
        *identity,
        receipt_path,
        receipt,
        approval={
            "source": source,
            "report": preview["report"],
            "rows": preview["rows"],
        },
        stage_intent=stage_intent,
    )
    return verify(source_path, plan_path, day)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True)
    parser.add_argument("--plan", required=True)
    parser.add_argument("--day", required=True)
    parser.add_argument("--verify-only", action="store_true")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--prepare-only", action="store_true")
    mode.add_argument("--apply-preview", action="store_true")
    parser.add_argument("--expected-normalized-sha256")
    parser.add_argument("--expected-preview-sha256")
    args = parser.parse_args()
    if not args.apply_preview and (
        args.expected_normalized_sha256 or args.expected_preview_sha256
    ):
        raise ValueError("Fuel approval hashes require explicit apply-preview mode")
    if args.apply_preview:
        if args.verify_only or os.environ.get("MOTIVE_FUEL_COMMIT") != "true":
            raise ValueError("Fuel preview application requires explicit commit")
        source, plan, expected, preview, normalized = verify_preview(
            args.input, args.plan, args.day
        )
        if (
            fuel_runner.checksum(preview) != args.expected_preview_sha256
            or fuel_runner.checksum(normalized) != args.expected_normalized_sha256
        ):
            raise ValueError("Fuel preview approval hash mismatch")
        from app.db.session import AsyncSessionLocal
        from scripts.motive_sync.run_fuel_worker import recover_pending

        state = Path(args.plan).parent.parent
        with (state / "worker.lock").open("a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            recover_pending(state)
            asyncio.run(
                apply_preview(
                    AsyncSessionLocal,
                    args.input,
                    args.plan,
                    args.day,
                    args.expected_normalized_sha256,
                    args.expected_preview_sha256,
                )
            )
        print(json.dumps({"stage": "fuel_day_verified", "day": args.day}), flush=True)
        return
    if args.prepare_only:
        source, plan, expected = bound_source(args.input, args.plan, args.day)
        if (
            os.environ.get("MOTIVE_FUEL_PREPARE_ONLY") != "true"
            or os.environ.get("MOTIVE_FUEL_COMMIT") != "true"
            or plan["mode"] != "explicit"
            or len(plan["days"]) > 2
        ):
            raise ValueError(
                "Fuel preview requires explicit private prepare-only scope"
            )
        if not args.verify_only:
            from app.db.session import AsyncSessionLocal

            asyncio.run(
                run(
                    AsyncSessionLocal,
                    source,
                    UUID(expected["tenant_id"]),
                    UUID(expected["actor_id"]),
                    expected["company_label"],
                    expected["company_id"],
                    Path(args.input).with_name("preview.json"),
                    commit=False,
                    plan=plan,
                )
            )
        verify_preview(args.input, args.plan, args.day)
        print(json.dumps({"stage": "fuel_day_prepared", "day": args.day}), flush=True)
        return
    if not args.verify_only and os.environ.get("MOTIVE_FUEL_PREPARE_ONLY") == "true":
        raise ValueError("Fuel prepare-only mode forbids implicit commit")
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
