from __future__ import annotations

from datetime import datetime, timezone

from app.core.logging import get_logger
from app.db.models.vehicle import Vehicle
from app.services.vin_decoder_service import decode_vin

logger = get_logger(__name__)

_NHTSA_CLEAR_FIELDS = (
    "nhtsa_make",
    "nhtsa_model",
    "nhtsa_model_year",
    "nhtsa_vehicle_type",
    "nhtsa_body_class",
    "nhtsa_drive_type",
    "nhtsa_fuel_type",
    "nhtsa_engine_cylinders",
    "nhtsa_engine_displacement_l",
    "nhtsa_engine_hp",
    "nhtsa_transmission",
    "nhtsa_gvwr",
    "nhtsa_decoded_at",
)


def clear_vehicle_nhtsa_snapshot(vehicle: Vehicle) -> None:
    for field_name in _NHTSA_CLEAR_FIELDS:
        setattr(vehicle, field_name, None)


async def sync_vehicle_nhtsa_snapshot(vehicle: Vehicle) -> None:
    clear_vehicle_nhtsa_snapshot(vehicle)

    vin = (vehicle.vin or "").strip()
    if len(vin) < 11:
        return

    try:
        result = await decode_vin(vin, model_year=vehicle.year)
    except Exception as exc:
        logger.warning(
            "vehicle_nhtsa_decode_failed",
            error_type=type(exc).__name__,
            error_message=str(exc),
            vin=vin,
        )
        return

    if result.error_code and result.error_code != "0":
        logger.info(
            "vehicle_nhtsa_decode_unresolved",
            vin=vin,
            error_code=result.error_code,
            error_text=result.error_text,
        )
        return

    vehicle.nhtsa_make = result.make
    vehicle.nhtsa_model = result.model
    vehicle.nhtsa_model_year = result.year
    vehicle.nhtsa_vehicle_type = result.vehicle_type
    vehicle.nhtsa_body_class = result.body_class
    vehicle.nhtsa_drive_type = result.drive_type
    vehicle.nhtsa_fuel_type = result.fuel_type
    vehicle.nhtsa_engine_cylinders = result.engine_cylinders
    vehicle.nhtsa_engine_displacement_l = result.engine_displacement_l
    vehicle.nhtsa_engine_hp = result.engine_hp
    vehicle.nhtsa_transmission = result.transmission
    vehicle.nhtsa_gvwr = result.gvwr
    vehicle.nhtsa_decoded_at = datetime.now(timezone.utc)
