"""Read-only cron execution audit. A platform exit is not an import receipt."""

import json
import subprocess
from datetime import UTC, datetime, timedelta

PROJECT = "78a30cb6-c422-458a-ad8f-daa02073b579"
ENVIRONMENT = "b5c9fdf5-4430-4cb3-97b9-cd739d7d5ece"
SCHEDULES = {
    "DBN-motive-sync": (None, 5),
    "DBN-motive-health": (None, 30),
    "DBN-motive-trips": (9, 15),
    "DBN-motive-fuel": (13, 30),
    "DBN-motive-drivers-safety": (13, 45),
}


def expected_slot(service, now):
    """Allow five minutes of scheduler start delay, then require a real run."""
    target = now - timedelta(minutes=5)
    hour, minute = SCHEDULES[service]
    if service == "DBN-motive-sync":
        return target.replace(minute=(target.minute // 5) * 5, second=0, microsecond=0)
    slot = target.replace(minute=minute, second=0, microsecond=0)
    if hour is not None:
        slot = slot.replace(hour=hour)
    if slot > target:
        slot -= timedelta(days=1) if hour is not None else timedelta(hours=1)
    return slot


def summarize(service, runs, now):
    expected = expected_slot(service, now)
    latest = max(runs, key=lambda run: run["createdAt"], default=None)
    alerts = []
    if latest is None or datetime.fromisoformat(latest["createdAt"]) < expected:
        alerts.append("scheduled_execution_missing")
    if latest and latest["status"] == "CRASHED":
        alerts.append("latest_execution_crashed")
        if latest.get("durationSeconds") == 150:
            alerts.append("150_second_exit_needs_startup_evidence")
    return {
        "service": service,
        "expected_slot_utc": expected.isoformat(),
        "latest_run": {
            key: latest.get(key)
            for key in ("id", "deploymentId", "createdAt", "status", "durationSeconds")
        }
        if latest
        else None,
        "alerts": alerts,
        "import_verified": None,
    }


def main():
    now = datetime.now(UTC)
    results = []
    for service in SCHEDULES:
        # Explicit project and environment prevent an unrelated linked service
        # from silently changing the audit's target. This command never triggers runs.
        response = subprocess.run(
            [
                "railway",
                "cron",
                "list",
                "--project",
                PROJECT,
                "--environment",
                ENVIRONMENT,
                "--service",
                service,
                "--limit",
                "20",
                "--json",
            ],
            capture_output=True,
            text=True,
            check=True,
            timeout=30,
        )
        results.append(summarize(service, json.loads(response.stdout), now))
    print(json.dumps({"observed_at": now.isoformat(), "services": results}, indent=2))
    return 2 if any(result["alerts"] for result in results) else 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception:  # noqa: BLE001 - never print CLI environment or raw error output
        print(json.dumps({"stage": "audit_unavailable", "healthy": None}))
        raise SystemExit(1) from None
