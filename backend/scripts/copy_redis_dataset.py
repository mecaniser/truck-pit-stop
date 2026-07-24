#!/usr/bin/env python3
"""Copy Redis keys between endpoints while preserving their remaining TTLs.

This is a cutover utility, not an application migration. It is deliberately
guarded because it may copy Celery queues, authentication revocations, and
one-time portal links. Run it only after application writers have stopped.
"""

from __future__ import annotations

import argparse
import os
import sys
from collections import Counter

import redis


CONFIRMATION_VALUE = "copy-redis-cutover-state"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source-url",
        default=os.getenv("SOURCE_REDIS_URL"),
        help="Source Redis URL; defaults to SOURCE_REDIS_URL.",
    )
    parser.add_argument(
        "--target-url",
        default=os.getenv("TARGET_REDIS_URL"),
        help="Target Redis URL; defaults to TARGET_REDIS_URL.",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Perform the copy. Without this flag the command only validates inputs.",
    )
    parser.add_argument(
        "--flush-target",
        action="store_true",
        help="Delete target keys before copying. Only use for an unused cutover target.",
    )
    parser.add_argument(
        "--scan-count",
        type=int,
        default=500,
        help="Redis SCAN batch hint. Default: 500.",
    )
    parser.add_argument(
        "--progress-every",
        type=int,
        default=500,
        help="Print a progress line after this many copied keys. Default: 500.",
    )
    return parser.parse_args()


def require_confirmation(args: argparse.Namespace) -> None:
    if not args.apply:
        raise SystemExit("Refusing to copy without --apply.")
    if os.getenv("REDIS_COPY_CONFIRM") != CONFIRMATION_VALUE:
        raise SystemExit(
            "Set REDIS_COPY_CONFIRM=copy-redis-cutover-state before running this utility."
        )
    if not args.source_url or not args.target_url:
        raise SystemExit("Both source and target Redis URLs are required.")
    if args.source_url == args.target_url:
        raise SystemExit("Source and target Redis URLs must be different.")
    if args.scan_count < 1 or args.progress_every < 1:
        raise SystemExit("--scan-count and --progress-every must be at least 1.")


def copy_dataset(
    source: redis.Redis,
    target: redis.Redis,
    *,
    flush_target: bool,
    scan_count: int,
    progress_every: int,
) -> None:
    source.ping()
    target.ping()

    if flush_target:
        target.flushdb(asynchronous=False)

    copied = 0
    skipped = 0
    kinds: Counter[str] = Counter()
    cursor = 0
    next_progress = progress_every
    while True:
        cursor, keys = source.scan(cursor=cursor, count=scan_count)
        if keys:
            source_batch = source.pipeline(transaction=False)
            for key in keys:
                source_batch.dump(key)
                source_batch.pttl(key)
                source_batch.type(key)
            snapshots = source_batch.execute()

            target_batch = target.pipeline(transaction=False)
            for offset, key in enumerate(keys):
                payload, ttl, kind = snapshots[offset * 3 : offset * 3 + 3]
                if payload is None or ttl == -2:
                    skipped += 1
                    continue

                # Redis RESTORE treats zero as no expiry; preserve persistent keys.
                target_batch.restore(key, max(ttl, 0), payload, replace=True)
                copied += 1
                kind_name = kind.decode("utf-8") if isinstance(kind, bytes) else str(kind)
                kinds[kind_name] += 1

            target_batch.execute()
            if copied >= next_progress:
                print(f"redis_copy_progress copied={copied}", flush=True)
                next_progress += progress_every

        if cursor == 0:
            break

    print(
        "redis_copy_complete "
        f"copied={copied} skipped_expired={skipped} "
        f"types={','.join(f'{kind}:{count}' for kind, count in sorted(kinds.items())) or 'none'}"
    )


def main() -> None:
    args = parse_args()
    require_confirmation(args)
    source = redis.from_url(args.source_url, decode_responses=False)
    target = redis.from_url(args.target_url, decode_responses=False)
    try:
        copy_dataset(
            source,
            target,
            flush_target=args.flush_target,
            scan_count=args.scan_count,
            progress_every=args.progress_every,
        )
    finally:
        source.close()
        target.close()


if __name__ == "__main__":
    main()
