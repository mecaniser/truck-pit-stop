"""Private fuel scheduling state and receipt-derived coverage; never inferred zero."""

import json
import re
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path
from uuid import UUID

from scripts.motive_sync.trip_coverage import private_read

VERSION = 1
FLOOR = date(2026, 8, 15)


def digest(value):
    import hashlib

    return hashlib.sha256(
        json.dumps(
            value, sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode()
    ).hexdigest()


def closed(day, stamp):
    parsed = date.fromisoformat(day)
    return (
        parsed.isoformat() == day
        and datetime.combine(parsed + timedelta(days=1), time(12), UTC) <= stamp
    )


def scope(tenant, actor, company, label, baseline="2026-08-15"):
    UUID(str(tenant))
    UUID(str(actor))
    if not company or not label or date.fromisoformat(baseline) < FLOOR:
        raise ValueError("Invalid fuel scope")
    return {
        "tenant_id": str(tenant),
        "actor_id": str(actor),
        "company_id": company,
        "company_label": label,
        "baseline": baseline,
        "date_policy": "unverified_zone_conservative_v1",
    }


def validate_plan(plan, expected, stamp):
    if plan.get("version") != VERSION or plan.get("scope") != expected:
        raise ValueError("Fuel plan scope mismatch")
    if not re.fullmatch(r"[0-9a-f-]{36}", plan.get("run_id", "")):
        raise ValueError("Fuel run identity required")
    UUID(plan["run_id"])
    created = datetime.fromisoformat(plan["created_at"])
    if created.tzinfo is None or created > stamp:
        raise ValueError("Fuel plan timestamp invalid")
    days = plan.get("days")
    if (
        not isinstance(days, list)
        or not 1 <= len(days) <= 7
        or len(set(days)) != len(days)
    ):
        raise ValueError("Fuel plan requires bounded unique dates")
    if any(
        date.fromisoformat(day) < date.fromisoformat(expected["baseline"])
        or not closed(day, created)
        for day in days
    ):
        raise ValueError("Fuel plan requires closed dates within baseline")
    if plan.get("mode") not in {"automatic", "explicit"} or plan.get(
        "first_lane"
    ) not in {"backlog", "recent", "explicit"}:
        raise ValueError("Fuel plan lane invalid")
    if (plan["mode"] == "explicit") != (plan["first_lane"] == "explicit"):
        raise ValueError("Fuel plan lane mismatch")
    return days


def plans(state, expected, stamp):
    result = []
    for path in Path(state).glob("*/plan.json"):
        item = private_read(path, state)
        validate_plan(item, expected, stamp)
        if path.parent.name != item["run_id"]:
            raise ValueError("Fuel plan directory mismatch")
        result.append(item)
    return sorted(result, key=lambda p: (p["created_at"], p["run_id"]))


def plan_days(expected, stamp, index, history, maximum=7, explicit=None):
    if type(maximum) is not int or not 5 <= maximum <= 7:
        raise ValueError("Fuel catchup requires 5 to 7 date slots")
    baseline = date.fromisoformat(expected["baseline"])
    latest = stamp.astimezone(UTC).date() - timedelta(
        days=1 if stamp.astimezone(UTC).hour >= 12 else 2
    )
    all_days = [
        (baseline + timedelta(days=i)).isoformat()
        for i in range(max(0, (latest - baseline).days + 1))
    ]
    if explicit is not None:
        start, end = map(date.fromisoformat, explicit)
        if not baseline <= start <= end <= latest or (end - start).days >= 7:
            raise ValueError(
                "Explicit fuel range must be closed and at most seven days"
            )
        return [
            (start + timedelta(days=i)).isoformat()
            for i in range((end - start).days + 1)
        ], "explicit"
    if not all_days:
        return [], "backlog"
    recent = all_days[-3:]
    automatic = [p for p in history if p["mode"] == "automatic"]
    lane = (
        "recent"
        if automatic and automatic[-1]["first_lane"] == "backlog"
        else "backlog"
    )
    # Only the guaranteed first slot is an attempted scheduling marker. Planned
    # later slots may never start; they must not become fictional observations.
    attempts = {p["days"][0]: p["created_at"] for p in automatic}
    recent.sort(key=lambda d: (attempts.get(d, ""), d))
    unseen = [d for d in all_days if d not in index and d not in recent]
    unseen.sort(key=lambda d: (attempts.get(d, ""), d))
    exceptions = sorted(
        (
            d
            for d in all_days
            if d in index and index[d]["status"] != "verified" and d not in recent
        ),
        key=lambda d: (index[d]["observed_at"], d),
    )
    backlog = unseen or exceptions
    selected = []

    def add(day):
        if day not in selected and len(selected) < maximum:
            selected.append(day)

    if lane == "backlog" and backlog:
        add(backlog[0])
    else:
        add(recent[0])
    # Reserve every lane before filling remaining capacity.
    if backlog:
        add(backlog[0])
    for day in recent:
        add(day)
    if exceptions:
        add(exceptions[0])
    for day in unseen + exceptions:
        add(day)
    return selected, lane


def validate_receipt(path, expected, *, plan=None, day=None):
    path = Path(path)
    root = path.parent.parent
    if root.is_symlink() or path.parent.is_symlink():
        raise ValueError("Fuel evidence directory is symlinked")
    receipt = private_read(path, root)
    source = private_read(path.with_name("source.json"))
    normalized = private_read(Path(str(path) + ".normalized.json"))
    coverage = normalized.get("coverage")
    if (
        not isinstance(coverage, dict)
        or coverage.get("version") != VERSION
        or coverage.get("scope") != expected
    ):
        raise ValueError("Fuel receipt coverage scope mismatch")
    source_plan = source.get("plan")
    finish = datetime.fromisoformat(source["finished_at"])
    validate_plan(source_plan, expected, finish)
    if plan is not None and source_plan != plan:
        raise ValueError("Fuel receipt run plan mismatch")
    actual_day = coverage["day"]
    if (
        (day is not None and actual_day != day)
        or source["report_dates"] != [actual_day]
        or actual_day not in source_plan["days"]
    ):
        raise ValueError("Fuel receipt date mismatch")
    if (
        path.parent.name != actual_day
        or path.parent.parent.name != source_plan["run_id"]
    ):
        raise ValueError("Fuel receipt path binding mismatch")
    identities = {
        key: expected[key]
        for key in ("tenant_id", "actor_id", "company_label", "company_id")
    }
    rows = normalized.get("rows")
    if (
        not isinstance(rows, list)
        or receipt.get("coverage") != coverage
        or receipt.get("mode") != "commit"
        or receipt.get("stage") != "verified"
        or receipt.get("committed") is not True
        or receipt.get("normalized_sha256") != digest(normalized)
        or any(
            record.get(key) != value
            for record in (receipt, normalized)
            for key, value in identities.items()
        )
        or any(
            record.get("source_sha256") != digest(source)
            for record in (receipt, normalized)
        )
        or any(
            receipt.get(key) != len(rows)
            for key in (
                "readback_verified",
                "replay_unchanged",
                "fleet_projection_verified",
            )
        )
        or len(receipt.get("rows", [])) != len(rows)
        or coverage.get("observed_at") != source["finished_at"]
        or coverage.get("status") not in {"verified", "examined_with_exceptions"}
    ):
        raise ValueError("Fuel receipt exact proof mismatch")
    matrix = coverage.get("matrix")
    if not isinstance(matrix, list) or len(matrix) < len(source["vehicles"]):
        raise ValueError("Fuel coverage matrix incomplete")
    providers = [
        item.get("provider_vehicle_id")
        for item in matrix
        if item.get("provider_vehicle_id") is not None
    ]
    if sorted(providers) != sorted(
        v["provider_vehicle_id"] for v in source["vehicles"]
    ):
        raise ValueError("Fuel coverage provider accounting mismatch")
    saved = [item for item in matrix if item.get("status") == "verified_saved"]
    if (
        len(saved) != len(rows)
        or any(item.get("report_date") != actual_day for item in matrix)
        or sorted(item["provider_vehicle_id"] for item in saved)
        != sorted(row["provider_vehicle_id"] for row in rows)
        or (coverage["status"] == "verified") != (len(saved) == len(matrix))
        or not re.fullmatch(r"[0-9a-f]{64}", coverage.get("mapping_sha256", ""))
    ):
        raise ValueError("Fuel coverage status accounting mismatch")
    # Use the source validator, including per-report closure and company gates,
    # without refreshing historical source age or calling any importer method.
    from scripts.motive_sync.fuel_runner import validate_source

    validate_source(
        source, expected["company_label"], expected["company_id"], finish, recovery=True
    )
    return coverage


def verified_days(state, expected):
    found = {}
    for path in Path(state).glob("*/????-??-??/receipt.json"):
        receipt = private_read(path, state)
        if receipt.get("stage") != "verified" or receipt.get("committed") is not True:
            continue
        coverage = validate_receipt(path, expected)
        day = coverage["day"]
        if day not in found or coverage["observed_at"] > found[day]["observed_at"]:
            found[day] = coverage
    if found:
        latest = max(found.values(), key=lambda c: c["observed_at"])["mapping_sha256"]
        found = {day: c for day, c in found.items() if c["mapping_sha256"] == latest}
    return found


def complete_through(expected, index):
    day = date.fromisoformat(expected["baseline"])
    last = None
    while index.get(day.isoformat(), {}).get("status") == "verified":
        last = day.isoformat()
        day += timedelta(days=1)
    return last
