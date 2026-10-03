"""Offline, fail-closed normalization of visibly captured Motive trip tables."""
import argparse
import json
import os
import re
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

ZONE = ZoneInfo("America/New_York")
CORE = ("vin", "unit", "provider_vehicle_id", "started_at", "ended_at", "origin_label", "destination_label", "distance_miles", "driving_seconds", "timestamp_precision")


def timestamp(value):
    if not isinstance(value, str):
        raise ValueError("Explicit timestamp required")
    result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if result.tzinfo is None:
        raise ValueError("Explicit timezone required")
    return result.astimezone(timezone.utc)


def endpoint(value):
    clock, label = value.split("\n", 1)
    naive = datetime.strptime(clock.strip(), "%m/%d/%Y %I:%M %p")
    candidates = {naive.replace(tzinfo=ZONE, fold=fold).astimezone(timezone.utc) for fold in (0, 1)
                  if naive.replace(tzinfo=ZONE, fold=fold).astimezone(timezone.utc).astimezone(ZONE).replace(tzinfo=None) == naive}
    if len(candidates) != 1:
        raise ValueError("Ambiguous or nonexistent local time")
    label = label.strip()
    if not label or len(label) > 500:
        raise ValueError("Invalid location")
    return candidates.pop(), label


def identity(row):
    return row["provider_vehicle_id"], timestamp(row["started_at"])


def core(row):
    value = {key: row[key] for key in CORE}
    for key in ("started_at", "ended_at"):
        value[key] = timestamp(value[key]).isoformat()
    return value


def normalize(document, mapping, prior=None, now=None):
    now = now or datetime.now(timezone.utc)
    if not isinstance(document, dict) or set(document) != {"tenant_id", "company_label", "windows"}:
        raise ValueError("Invalid capture document")
    if not isinstance(mapping, dict) or set(mapping) != {"tenant_id", "company_label", "vehicles"}:
        raise ValueError("Invalid mapping document")
    for key in ("tenant_id", "company_label"):
        if not isinstance(mapping[key], str) or not mapping[key].strip() or document[key] != mapping[key]:
            raise ValueError("Tenant/company mismatch")
    if not isinstance(document["windows"], list) or not isinstance(mapping["vehicles"], list):
        raise ValueError("Invalid windows or mappings")
    vehicles = {}
    vins = set()
    for row in mapping["vehicles"]:
        if not isinstance(row, dict) or set(row) != {"provider_vehicle_id", "vin", "unit", "effective_from"}:
            raise ValueError("Invalid mapping")
        pid = row["provider_vehicle_id"]
        if not isinstance(pid, str) or not pid or pid in vehicles or row["vin"] in vins:
            raise ValueError("Duplicate or invalid mapping")
        if not re.fullmatch(r"[A-HJ-NPR-Z0-9]{17}", row["vin"]) or not isinstance(row["unit"], str) or not row["unit"].strip():
            raise ValueError("Invalid VIN/unit")
        timestamp(row["effective_from"])
        vehicles[pid] = row
        vins.add(row["vin"])
    previous = {}
    if prior is not None:
        if not isinstance(prior, dict) or set(prior) != {"rows"} or not isinstance(prior["rows"], list):
            raise ValueError("Invalid prior document")
        for row in prior["rows"]:
            key = identity(row)
            core(row)
            if key in previous:
                raise ValueError("Duplicate prior identity")
            previous[key] = row
    accepted, blocked = {}, set()
    report = {"tenant_id": document["tenant_id"], "company_label": document["company_label"], "windows": [], "exclusions": [], "replayed": 0}
    for window_index, window in enumerate(document["windows"]):
        if not isinstance(window, dict) or set(window) != {"start", "end", "source_read_at", "status", "rows"}:
            raise ValueError("Invalid window")
        start, end = date.fromisoformat(window["start"]), date.fromisoformat(window["end"])
        read = timestamp(window["source_read_at"])
        if start < date(2026, 4, 1) or end < start or end > now.astimezone(ZONE).date() or read > now or not isinstance(window["rows"], list) or window["status"] not in ("captured", "empty", "partial"):
            raise ValueError("Invalid window bounds/status")
        if window["status"] == "empty" and window["rows"]:
            raise ValueError("Empty window contains rows")
        report["windows"].append({key: window[key] for key in ("start", "end", "status", "source_read_at")})
        for index, raw in enumerate(window["rows"]):
            reason = None
            try:
                if window["status"] == "partial":
                    raise ValueError("partial_window")
                if not isinstance(raw, dict) or set(raw) != {"cells", "links"} or not isinstance(raw["cells"], list) or not isinstance(raw["links"], list):
                    raise ValueError("invalid_row")
                cells, links = raw["cells"], raw["links"]
                if len(cells) < 4 or not all(isinstance(c, str) for c in cells) or len(links) != 1 or not isinstance(links[0], str):
                    raise ValueError("invalid_row")
                provider = re.fullmatch(r"(?:https://app\.gomotive\.com/en-US/)?#/fleetview/vehicles/summary/([0-9]+)", links[0])
                if not provider:
                    raise ValueError("invalid_provider_link")
                pid = provider.group(1)
                if pid not in vehicles:
                    raise ValueError("unverified_vehicle")
                match = vehicles[pid]
                departure, origin = endpoint(cells[1])
                if not start <= departure.astimezone(ZONE).date() <= end:
                    raise ValueError("outside_window")
                if "PROGRESS" in cells[2].upper():
                    raise ValueError("ongoing")
                arrival, destination = endpoint(cells[2])
                measurement = re.fullmatch(r"((?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?)\s*(?:mi)?\n(\d+)h (\d+)m (\d+)s", cells[3].strip())
                if not measurement:
                    raise ValueError("invalid_measurement")
                distance, hours, minutes, seconds = measurement.groups()
                if int(minutes) >= 60 or int(seconds) >= 60:
                    raise ValueError("invalid_duration")
                duration = int(hours) * 3600 + int(minutes) * 60 + int(seconds)
                elapsed = (arrival - departure).total_seconds()
                miles = float(distance.replace(",", ""))
                if not 0 <= miles <= 100000 or elapsed < 0 or (elapsed == 0 and duration <= 0) or not 0 <= duration <= min(elapsed + 59, 2678400) or arrival + timedelta(minutes=1) > read:
                    raise ValueError("incomplete_or_invalid_trip")
                if departure < timestamp(match["effective_from"]):
                    raise ValueError("outside_membership")
                row = dict(vin=match["vin"], unit=match["unit"], provider_vehicle_id=pid, source_read_at=read.isoformat(), started_at=departure.isoformat(), ended_at=arrival.isoformat(), origin_label=origin, destination_label=destination, distance_miles=miles, driving_seconds=duration, stops=None, metrics=None, timestamp_precision="minute")
                key = identity(row)
                if key in blocked:
                    raise ValueError("conflicting_source_identity")
                existing = previous.get(key) or accepted.get(key)
                if existing and core(existing) != core(row):
                    accepted.pop(key, None)
                    blocked.add(key)
                    raise ValueError("conflicting_source_identity")
                if key in previous:
                    # Full frozen normalized payload retained; import will revalidate it.
                    row = dict(previous[key])
                accepted[key] = row
            except (ValueError, KeyError, TypeError, OverflowError) as error:
                reason = str(error) or "invalid_row"
            if reason:
                report["exclusions"].append({"window": window_index, "row": index, "reason": reason})
    rows = [accepted[key] for key in sorted(accepted, key=lambda key: (key[1], key[0]))]
    report["replayed"] = sum(identity(row) in previous for row in rows)
    report["accepted"] = len(rows)
    report["coverage"] = "partial"
    return rows, report


def write_outputs(directory, rows, report):
    directory = Path(directory)
    directory.mkdir(mode=0o700, parents=True, exist_ok=False)
    directory.chmod(0o700)
    paths = []
    for offset in range(0, len(rows), 1000):
        path = directory / f"batch-{offset // 1000 + 1:04d}.json"
        paths.append(path.name)
        _write(path, {"rows": rows[offset:offset + 1000]})
    _write(directory / "report.json", {**report, "batches": paths})


def _write(path, data):
    with os.fdopen(os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "w") as handle:
        json.dump(data, handle, indent=2, allow_nan=False)
        handle.write("\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True)
    parser.add_argument("--mapping", required=True)
    parser.add_argument("--prior")
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args()
    try:
        def read(path):
            return json.loads(Path(path).read_text())
        rows, report = normalize(read(args.input), read(args.mapping), read(args.prior) if args.prior else None)
        write_outputs(args.output_dir, rows, report)
    except (ValueError, TypeError, KeyError, OSError):
        raise SystemExit("Preparation failed; no database changes. Check private input and output path.") from None
    print(json.dumps({"accepted": len(rows), "excluded": len(report["exclusions"]), "coverage": "partial", "database_written": False}))


if __name__ == "__main__":
    main()
