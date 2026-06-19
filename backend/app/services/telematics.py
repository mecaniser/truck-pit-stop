"""Provider-agnostic telematics (fleet GPS/ELD) layer.

The fleet board reads each vehicle's last-known location from its ``last_*`` columns.
Those are populated either manually or by syncing from a telematics provider here.

v1 ships the ``manual`` provider (no external feed — positions are whatever has been
entered/last-known). Samsara/Motive adapters are stubbed with the right shape so that,
once an API key + truck→device mapping exist, ``sync_locations`` lights up live GPS
with no changes to the board, API, or UI.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.logging import get_logger
from app.db.models.vehicle import Vehicle

logger = get_logger(__name__)


@dataclass
class LocationSample:
    """A normalized location reading for one device, provider-independent."""
    device_id: str
    lat: float
    lng: float
    speed_mph: Optional[int] = None
    heading: Optional[str] = None
    label: Optional[str] = None
    city: Optional[str] = None
    odometer_miles: Optional[int] = None
    recorded_at: Optional[datetime] = None


class TelematicsProvider(ABC):
    """A telematics source. Implementations map external device ids -> LocationSample."""

    name: str = "base"

    @abstractmethod
    async def fetch_locations(self, device_ids: list[str]) -> dict[str, LocationSample]:
        """Return {device_id: LocationSample} for the given device ids."""
        raise NotImplementedError


class ManualTelematicsProvider(TelematicsProvider):
    """No external feed. Locations are whatever is stored on the vehicle (manual entry)."""

    name = "manual"

    async def fetch_locations(self, device_ids: list[str]) -> dict[str, LocationSample]:
        return {}


class SamsaraTelematicsProvider(TelematicsProvider):
    """Samsara adapter (stub).

    When enabled: GET https://api.samsara.com/fleet/vehicles/locations with a bearer
    token (settings.TELEMATICS_API_KEY), then map each vehicle's gps {latitude,
    longitude, speedMilesPerHour, headingDegrees, reverseGeo} to LocationSample keyed
    by the Samsara vehicle id stored in Vehicle.telematics_device_id.
    """

    name = "samsara"

    async def fetch_locations(self, device_ids: list[str]) -> dict[str, LocationSample]:
        raise NotImplementedError(
            "Samsara telematics not wired yet — provide TELEMATICS_API_KEY and implement fetch_locations()."
        )


class MotiveTelematicsProvider(TelematicsProvider):
    """Motive (KeepTruckin) adapter (stub).

    When enabled: GET https://api.gomotive.com/v1/vehicle_locations with the API key,
    map current_location {lat, lon, bearing, speed, located_at, description} to
    LocationSample keyed by Vehicle.telematics_device_id.
    """

    name = "motive"

    async def fetch_locations(self, device_ids: list[str]) -> dict[str, LocationSample]:
        raise NotImplementedError(
            "Motive telematics not wired yet — provide TELEMATICS_API_KEY and implement fetch_locations()."
        )


_PROVIDERS: dict[str, type[TelematicsProvider]] = {
    "manual": ManualTelematicsProvider,
    "samsara": SamsaraTelematicsProvider,
    "motive": MotiveTelematicsProvider,
}


def get_provider() -> TelematicsProvider:
    """Resolve the active provider from settings (default: manual)."""
    cls = _PROVIDERS.get((settings.TELEMATICS_PROVIDER or "manual").lower(), ManualTelematicsProvider)
    return cls()


def heading_from_degrees(degrees: Optional[float]) -> Optional[str]:
    """Convert a compass bearing to an 8-point label (N, NE, E, …)."""
    if degrees is None:
        return None
    dirs = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]
    return dirs[int((degrees % 360) / 45 + 0.5) % 8]


async def sync_locations(db: AsyncSession, tenant_id) -> int:
    """Pull fresh positions from the active provider and write them onto vehicles.

    No-op for the manual provider. Returns the number of vehicles updated. Safe to call
    on a schedule once a real provider + device mapping are configured.
    """
    provider = get_provider()
    if provider.name == "manual":
        return 0

    result = await db.execute(
        select(Vehicle).where(
            Vehicle.tenant_id == tenant_id,
            Vehicle.telematics_device_id.isnot(None),
            Vehicle.deleted_at.is_(None),
        )
    )
    vehicles = list(result.scalars().all())
    device_ids = [v.telematics_device_id for v in vehicles if v.telematics_device_id]
    if not device_ids:
        return 0

    samples = await provider.fetch_locations(device_ids)
    updated = 0
    for v in vehicles:
        s = samples.get(v.telematics_device_id)
        if not s:
            continue
        v.last_lat = s.lat
        v.last_lng = s.lng
        v.last_speed_mph = s.speed_mph
        v.last_heading = s.heading
        if s.label:
            v.last_location_label = s.label
        if s.city:
            v.last_location_city = s.city
        if s.odometer_miles is not None:
            v.mileage = s.odometer_miles
        v.last_location_at = s.recorded_at or datetime.utcnow()
        updated += 1

    if updated:
        await db.commit()
    logger.info("telematics_sync", provider=provider.name, tenant_id=str(tenant_id), updated=updated)
    return updated
