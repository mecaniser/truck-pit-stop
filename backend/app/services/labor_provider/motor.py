from __future__ import annotations

from decimal import Decimal
from time import perf_counter
from typing import Any, Optional

import httpx

from app.core.config import settings
from app.core.logging import get_logger
from app.services.labor_provider.base import (
    LaborProvider,
    LaborProviderError,
    ProviderEstimate,
    ProviderPartSuggestion,
    ProviderWarning,
    RepairOperationCandidate,
    VehicleContext,
)

logger = get_logger(__name__)


def _to_decimal(value: Any, default: Decimal = Decimal("0.00")) -> Decimal:
    if value is None:
        return default
    try:
        return Decimal(str(value))
    except Exception:
        return default


def _fallback_operations(query: str) -> list[RepairOperationCandidate]:
    q = (query or "").lower()
    catalog = [
        ("brake-change", "Brake Change", "Replace pads/shoes and inspect brake hardware", Decimal("2.50")),
        ("egr-replacement", "EGR Replacement", "Replace EGR valve and verify operation", Decimal("6.00")),
        ("dpf-service", "DPF Service", "DPF inspection and service cycle", Decimal("3.00")),
        ("coolant-leak-repair", "Coolant Leak Repair", "Pressure test and repair leak source", Decimal("4.50")),
    ]
    out: list[RepairOperationCandidate] = []
    for op_id, name, desc, hrs in catalog:
        if not q or q in name.lower() or q in desc.lower() or q in op_id:
            out.append(
                RepairOperationCandidate(
                    operation_id=op_id,
                    name=name,
                    description=desc,
                    estimated_hours=hrs,
                    provider="motor",
                )
            )
    return out[:8]


class MotorLaborProvider(LaborProvider):
    provider_name = "motor"

    async def search_operations(
        self,
        vehicle: VehicleContext,
        query: str,
    ) -> tuple[list[RepairOperationCandidate], list[ProviderWarning]]:
        if not settings.MOTOR_ENABLED:
            return _fallback_operations(query), [
                ProviderWarning(
                    code="provider_disabled",
                    message="MOTOR is disabled; showing fallback operation suggestions.",
                )
            ]

        payload = {
            "query": query,
            "vin": vehicle.vin,
            "year": vehicle.year,
            "make": vehicle.make,
            "model": vehicle.model,
        }
        try:
            data = await self._post_json("/operations/search", payload)
            items = data.get("operations") or data.get("results") or []
            candidates = [self._candidate_from_item(item) for item in items]
            if candidates:
                return candidates, []
            return _fallback_operations(query), [
                ProviderWarning(
                    code="no_results",
                    message="No provider operations found; using fallback suggestions.",
                )
            ]
        except Exception as exc:
            logger.warning(
                "motor_search_failed",
                error_type=type(exc).__name__,
                error_message=str(exc),
            )
            return _fallback_operations(query), [
                ProviderWarning(
                    code="provider_unavailable",
                    message="MOTOR search is unavailable; showing fallback suggestions.",
                )
            ]

    async def get_operation_estimate(
        self,
        vehicle: VehicleContext,
        operation_id: str,
    ) -> ProviderEstimate:
        if not settings.MOTOR_ENABLED:
            fallback = _fallback_operations(operation_id)
            choice = fallback[0] if fallback else RepairOperationCandidate(
                operation_id=operation_id,
                name=operation_id.replace("-", " ").title(),
                description="Manual fallback estimate",
                estimated_hours=Decimal("0.00"),
            )
            return ProviderEstimate(
                operation_id=choice.operation_id,
                name=choice.name,
                description=choice.description,
                estimated_hours=choice.estimated_hours,
                warnings=[
                    ProviderWarning(
                        code="provider_disabled",
                        message="MOTOR is disabled; using fallback estimated hours.",
                    )
                ],
            )

        payload = {
            "operation_id": operation_id,
            "vin": vehicle.vin,
            "year": vehicle.year,
            "make": vehicle.make,
            "model": vehicle.model,
        }
        try:
            data = await self._post_json("/operations/estimate", payload)
            hours = _to_decimal(data.get("estimated_hours") or data.get("hours"))
            name = data.get("name") or operation_id.replace("-", " ").title()
            description = data.get("description")
            return ProviderEstimate(
                operation_id=operation_id,
                name=name,
                description=description,
                estimated_hours=hours,
                warnings=[],
            )
        except Exception as exc:
            logger.warning(
                "motor_estimate_failed",
                error_type=type(exc).__name__,
                error_message=str(exc),
                operation_id=operation_id,
            )
            raise LaborProviderError("Unable to retrieve operation estimate from MOTOR") from exc

    async def get_operation_parts(
        self,
        vehicle: VehicleContext,
        operation_id: str,
    ) -> tuple[list[ProviderPartSuggestion], list[ProviderWarning]]:
        if not settings.MOTOR_ENABLED:
            return [], [
                ProviderWarning(
                    code="provider_disabled",
                    message="MOTOR is disabled; part suggestions unavailable.",
                )
            ]

        payload = {
            "operation_id": operation_id,
            "vin": vehicle.vin,
            "year": vehicle.year,
            "make": vehicle.make,
            "model": vehicle.model,
        }
        try:
            data = await self._post_json("/operations/parts", payload)
            raw_parts = data.get("parts") or data.get("results") or []
            out: list[ProviderPartSuggestion] = []
            for part in raw_parts:
                out.append(
                    ProviderPartSuggestion(
                        part_number=str(part.get("part_number") or part.get("sku") or ""),
                        name=str(part.get("name") or "Part"),
                        quantity=int(part.get("quantity") or 1),
                    )
                )
            return out, []
        except Exception:
            return [], [
                ProviderWarning(
                    code="provider_unavailable",
                    message="Unable to fetch part suggestions from MOTOR.",
                )
            ]

    async def _post_json(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        base_url = settings.MOTOR_BASE_URL.rstrip("/")
        url = f"{base_url}{path}"
        headers = {
            "Accept": "application/json",
        }
        if settings.MOTOR_PUBLIC_KEY:
            headers["X-MOTOR-PUBLIC-KEY"] = settings.MOTOR_PUBLIC_KEY
        if settings.MOTOR_PRIVATE_KEY:
            headers["X-MOTOR-PRIVATE-KEY"] = settings.MOTOR_PRIVATE_KEY

        auth: Optional[tuple[str, str]] = None
        if settings.MOTOR_PUBLIC_KEY and settings.MOTOR_PRIVATE_KEY:
            auth = (settings.MOTOR_PUBLIC_KEY, settings.MOTOR_PRIVATE_KEY)

        started = perf_counter()
        try:
            async with httpx.AsyncClient(timeout=float(settings.MOTOR_TIMEOUT_SECONDS)) as client:
                response = await client.post(url, json=payload, headers=headers, auth=auth)
                response.raise_for_status()
                data = response.json()
                if not isinstance(data, dict):
                    raise LaborProviderError("Unexpected response format from MOTOR")
                logger.info(
                    "motor_request_completed",
                    path=path,
                    status_code=response.status_code,
                    duration_ms=round((perf_counter() - started) * 1000, 2),
                )
                return data
        except Exception as exc:
            logger.warning(
                "motor_request_failed",
                path=path,
                error_type=type(exc).__name__,
                error_message=str(exc),
                duration_ms=round((perf_counter() - started) * 1000, 2),
            )
            raise

    def _candidate_from_item(self, item: dict[str, Any]) -> RepairOperationCandidate:
        return RepairOperationCandidate(
            operation_id=str(item.get("operation_id") or item.get("id") or item.get("code") or ""),
            name=str(item.get("name") or "Operation"),
            description=item.get("description"),
            estimated_hours=_to_decimal(item.get("estimated_hours") or item.get("hours")),
            provider="motor",
        )
