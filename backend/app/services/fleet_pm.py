"""Read-only PM mileage projection from already tenant-scoped telemetry."""
import math
from datetime import datetime, timedelta, timezone


def apply_pm_mileage(truck, now=None):
    """Keep service mileage/PM target immutable; derive remaining miles as of reading.

    Manual dashboard snapshots are accepted for the interim workflow. API mileage
    must be calibrated, never virtual. The existing 30-day retention window is
    also the maximum PM snapshot age; old readings are not extrapolated.
    """
    now = now or datetime.now(timezone.utc)
    service = truck.odometer
    mileage = service
    reading = truck.telemetry.odometer if truck.telemetry else None
    if reading:
        stamp = reading.observed_at or reading.captured_at
        if stamp and stamp.tzinfo is None:
            stamp = stamp.replace(tzinfo=timezone.utc)
        comparable = (
            reading.source == "motive_dashboard_manual"
            and reading.basis == "dashboard_unspecified"
        ) or (reading.source == "motive_api" and reading.basis == "calibrated")
        if (
            comparable
            and reading.unit == "mi"
            and math.isfinite(reading.value)
            and reading.value >= 0
            and (service is None or reading.value >= service)
            and stamp is not None
            and now - timedelta(days=30) <= stamp <= now + timedelta(minutes=5)
        ):
            mileage = math.floor(reading.value)
    truck.pm_remaining = (
        truck.next_pm_miles - mileage
        if truck.next_pm_miles is not None and mileage is not None
        else None
    )
    # Keep operational overrides and open-work-order status authoritative.
    if truck.work_order is None and not truck.status_override:
        due = (truck.pm_remaining is not None and truck.pm_remaining < 2500) or (
            truck.pm_days_remaining is not None and truck.pm_days_remaining <= 14
        )
        truck.status = "pm" if due else "active"
