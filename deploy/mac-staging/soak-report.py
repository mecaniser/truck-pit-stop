"""Report a previously approved 24-hour observation window; never start/reset it."""
import datetime as dt
import json
import pathlib

WORKERS = {"sync", "health", "trips", "fuel", "drivers"}
CONTAINERS = {
    "dieselbridge-staging-" + name + "-1"
    for name in ("web", "postgres", "redis", "gateway")
}


def aware_timestamp(value):
    if not isinstance(value, str):
        raise ValueError("timestamp_must_be_string")
    stamp = dt.datetime.fromisoformat(value)
    if stamp.tzinfo is None or stamp.utcoffset() is None:
        raise ValueError("timestamp_must_be_aware")
    return stamp


def report(root, now=None):
    now = now or dt.datetime.now(dt.timezone.utc)
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("report_clock_must_be_aware")
    baseline = root / "soak-baseline.json"
    if not baseline.exists():
        return {"status": "waiting_for_reboot_and_worker_gates", "complete": False}
    try:
        record = json.loads(baseline.read_text())
        if not isinstance(record, dict):
            raise ValueError("baseline_must_be_object")
        verified = record.get("workers_verified")
        if (
            record.get("reboot_verified") is not True
            or record.get("independent_qa") != "GO"
            or not isinstance(verified, list)
            or len(verified) != len(WORKERS)
            or any(not isinstance(worker, str) for worker in verified)
            or set(verified) != WORKERS
        ):
            raise ValueError("approval_gates_missing")
        if not isinstance(record.get("source"), str) or not record["source"]:
            raise ValueError("approved_source_missing")
        start = aware_timestamp(record["started_at"])
        if start > now:
            raise ValueError("future_baseline")
        approved_starts = record.get("container_started")
        if not isinstance(approved_starts, dict) or set(approved_starts) != CONTAINERS:
            raise ValueError("approved_container_starts_missing")
        for value in approved_starts.values():
            if aware_timestamp(value) > start:
                raise ValueError("container_started_after_baseline")
    except (ValueError, TypeError, KeyError, OSError) as error:
        return {"status": "failed", "complete": False,
                "issues": ["invalid_baseline", str(error)]}

    end = start + dt.timedelta(hours=24)
    samples = []
    issues = []
    for name in ("monitor.previous.jsonl", "monitor.jsonl"):
        path = root / name
        if not path.exists():
            continue
        try:
            lines = path.read_text().splitlines()
        except OSError:
            issues.append("unreadable_samples")
            continue
        for line in lines:
            try:
                sample = json.loads(line)
                if not isinstance(sample, dict):
                    raise ValueError("sample_must_be_object")
                stamp = aware_timestamp(sample["at"])
            except (ValueError, TypeError, KeyError):
                issues.append("invalid_sample_timestamp_or_record")
                continue
            if stamp > now:
                issues.append("future_sample")
                continue
            if start <= stamp <= end + dt.timedelta(seconds=90):
                samples.append((stamp, sample))
    samples.sort(key=lambda pair: pair[0])
    last = start
    for stamp, sample in samples:
        if (stamp - last).total_seconds() > 90:
            issues.append("sample_gap")
        if sample.get("ok") is not True or sample.get("source") != record["source"]:
            issues.append("unhealthy_or_source_changed")
        containers = sample.get("containers")
        if not isinstance(containers, dict) or any(
            not isinstance(value, dict) for value in containers.values()
        ):
            issues.append("invalid_container_sample")
        else:
            starts = {key: value.get("started") for key, value in containers.items()}
            # The approved baseline owns the identity, including the first sample.
            if starts != approved_starts:
                issues.append("container_restarted_or_missing")
        last = stamp
    if (min(now, end) - last).total_seconds() > 90:
        issues.append("missing_recent_sample")
    complete = bool(samples) and now >= end and last >= end and not issues
    return {
        "status": "passed" if complete else ("failed" if issues else "observing"),
        "complete": complete, "started_at": start.isoformat(), "ends_at": end.isoformat(),
        "samples": len(samples), "last_sample": last.isoformat(),
        "issues": sorted(set(issues)),
    }


if __name__ == "__main__":
    print(json.dumps(report(pathlib.Path.home() / "dieselbridge-staging/private")))
