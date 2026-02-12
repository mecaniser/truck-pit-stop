"""
NHTSA VIN Decoder Service
Uses the free NHTSA vPIC API: https://vpic.nhtsa.dot.gov/api/
"""
import httpx
from typing import Optional
from pydantic import BaseModel


NHTSA_BASE_URL = "https://vpic.nhtsa.dot.gov/api/vehicles"


class VINDecodeResult(BaseModel):
    vin: str
    make: Optional[str] = None
    model: Optional[str] = None
    year: Optional[int] = None
    vehicle_type: Optional[str] = None
    body_class: Optional[str] = None
    drive_type: Optional[str] = None
    fuel_type: Optional[str] = None
    engine_cylinders: Optional[int] = None
    engine_displacement_l: Optional[float] = None
    engine_hp: Optional[int] = None
    transmission: Optional[str] = None
    gvwr: Optional[str] = None  # Gross Vehicle Weight Rating
    error_code: Optional[str] = None
    error_text: Optional[str] = None


def _safe_int(value: Optional[str]) -> Optional[int]:
    if not value:
        return None
    try:
        return int(value)
    except (ValueError, TypeError):
        return None


def _safe_float(value: Optional[str]) -> Optional[float]:
    if not value:
        return None
    try:
        return float(value)
    except (ValueError, TypeError):
        return None


async def decode_vin(vin: str, model_year: Optional[int] = None) -> VINDecodeResult:
    """
    Decode a VIN using the NHTSA vPIC API.
    
    Args:
        vin: The VIN to decode (17 characters for full decode, partial supported)
        model_year: Optional model year to improve accuracy
    
    Returns:
        VINDecodeResult with decoded vehicle information
    """
    url = f"{NHTSA_BASE_URL}/DecodeVinValues/{vin}"
    params = {"format": "json"}
    if model_year:
        params["modelyear"] = str(model_year)
    
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.get(url, params=params)
        response.raise_for_status()
        data = response.json()
    
    results = data.get("Results", [])
    if not results:
        return VINDecodeResult(vin=vin, error_code="0", error_text="No results returned")
    
    r = results[0]
    
    # NHTSA returns error codes in the response
    error_code = r.get("ErrorCode", "")
    error_text = r.get("ErrorText", "")
    
    return VINDecodeResult(
        vin=vin,
        make=r.get("Make") or None,
        model=r.get("Model") or None,
        year=_safe_int(r.get("ModelYear")),
        vehicle_type=r.get("VehicleType") or None,
        body_class=r.get("BodyClass") or None,
        drive_type=r.get("DriveType") or None,
        fuel_type=r.get("FuelTypePrimary") or None,
        engine_cylinders=_safe_int(r.get("EngineCylinders")),
        engine_displacement_l=_safe_float(r.get("DisplacementL")),
        engine_hp=_safe_int(r.get("EngineHP")),
        transmission=r.get("TransmissionStyle") or None,
        gvwr=r.get("GVWR") or None,
        error_code=error_code if error_code else None,
        error_text=error_text if error_text else None,
    )
