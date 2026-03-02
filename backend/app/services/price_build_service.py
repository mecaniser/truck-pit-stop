from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from time import perf_counter
from typing import Optional
from uuid import UUID

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import settings
from app.db.models.labor import Labor, LaborLineType
from app.db.models.motor_operation_cache import MotorOperationCache
from app.db.models.repair_order import RepairOrder, RepairOrderStatus
from app.db.models.service import Service
from app.db.models.tenant import Tenant
from app.core.logging import get_logger
from app.services.labor_provider.base import (
    LaborProviderError,
    ProviderWarning,
    RepairOperationCandidate,
    VehicleContext,
)
from app.services.labor_provider.motor import MotorLaborProvider
from app.services.pricing import get_selected_services_total


class PriceBuildError(Exception):
    pass


class PriceBuildNotFoundError(PriceBuildError):
    pass


class PriceBuildLockedError(PriceBuildError):
    pass


class PriceBuildValidationError(PriceBuildError):
    pass


EDITABLE_RO_STATUSES = {RepairOrderStatus.DRAFT, RepairOrderStatus.QUOTED}
FINALIZED_STATUSES = {RepairOrderStatus.INVOICED, RepairOrderStatus.PAID}
logger = get_logger(__name__)


@dataclass
class PriceBuildResult:
    order: RepairOrder
    warnings: list[ProviderWarning]


def _money(value: Decimal) -> Decimal:
    return Decimal(value).quantize(Decimal("0.01"))


def _is_locked(order: RepairOrder) -> bool:
    return order.pricing_locked_at is not None


def _vehicle_ctx(order: RepairOrder) -> VehicleContext:
    vehicle = order.vehicle
    if vehicle is None:
        return VehicleContext()
    return VehicleContext(
        vin=vehicle.vin,
        year=vehicle.year,
        make=vehicle.make,
        model=vehicle.model,
    )


def _vehicle_fingerprint(order: RepairOrder) -> str:
    v = order.vehicle
    if not v:
        return "unknown"
    return f"{v.year or 'na'}:{(v.make or '').lower()}:{(v.model or '').lower()}:{v.vin or 'na'}"


class PriceBuildService:
    def __init__(self) -> None:
        self.provider = MotorLaborProvider()

    async def load_order(self, db: AsyncSession, order_id: UUID) -> RepairOrder:
        result = await db.execute(
            select(RepairOrder)
            .where(RepairOrder.id == order_id)
            .options(
                selectinload(RepairOrder.vehicle),
                selectinload(RepairOrder.parts_usage),
                selectinload(RepairOrder.labor_items),
            )
            .execution_options(populate_existing=True)
        )
        order = result.scalar_one_or_none()
        if not order:
            raise PriceBuildNotFoundError("Repair order not found")
        # Keep relationship collections fresh across write->read cycles in the same session.
        await db.refresh(order, attribute_names=["vehicle", "parts_usage", "labor_items"])
        return order

    async def add_flat_service_line(
        self,
        db: AsyncSession,
        order: RepairOrder,
        service_id: UUID,
        *,
        quantity: int = 1,
    ) -> PriceBuildResult:
        self._assert_editable(order)
        if quantity < 1:
            raise PriceBuildValidationError("quantity must be >= 1")

        svc_result = await db.execute(
            select(Service).where(
                and_(
                    Service.id == service_id,
                    Service.tenant_id == order.tenant_id,
                )
            )
        )
        service = svc_result.scalar_one_or_none()
        if not service:
            raise PriceBuildNotFoundError("Service not found")

        qty = Decimal(quantity)
        base_price = Decimal(str(service.base_price))

        existing_line = next(
            (
                li
                for li in order.labor_items
                if li.line_type == LaborLineType.FLAT_SERVICE and li.source_service_id == service.id
            ),
            None,
        )
        if existing_line:
            existing_line.description = service.name
            existing_line.hours = qty
            existing_line.hourly_rate = base_price
            existing_line.total_cost = _money(qty * base_price)
            existing_line.auto_recalc_enabled = True
        else:
            db.add(
                Labor(
                    tenant_id=order.tenant_id,
                    repair_order_id=order.id,
                    service_code=None,
                    description=service.name,
                    hours=qty,
                    hourly_rate=base_price,
                    total_cost=_money(qty * base_price),
                    line_type=LaborLineType.FLAT_SERVICE,
                    provider=None,
                    provider_operation_id=None,
                    auto_recalc_enabled=True,
                    source_service_id=service.id,
                )
            )
        await db.commit()
        order = await self.load_order(db, order.id)
        return await self.recalculate_order(db, order)

    async def search_repair_operations(
        self,
        db: AsyncSession,
        order: RepairOrder,
        query: str,
    ) -> tuple[list[RepairOperationCandidate], list[ProviderWarning]]:
        clean_query = (query or "").strip()
        if not clean_query:
            return [], [ProviderWarning(code="invalid_query", message="Search query is required.")]

        cache_key = f"search:{clean_query.lower()}"
        cached = await self._read_cached_candidates(db, order, cache_key)
        if cached:
            return cached, []

        candidates, warnings = await self.provider.search_operations(_vehicle_ctx(order), clean_query)
        if candidates:
            await self._write_cache(
                db=db,
                order=order,
                operation_key=cache_key,
                normalized_hours=candidates[0].estimated_hours,
                payload=candidates,
            )
        return candidates, warnings

    async def add_repair_operation_line(
        self,
        db: AsyncSession,
        order: RepairOrder,
        *,
        operation_id: str,
        name: Optional[str] = None,
        description: Optional[str] = None,
        estimated_hours: Optional[Decimal] = None,
        auto_recalc_enabled: bool = True,
    ) -> PriceBuildResult:
        self._assert_editable(order)

        tenant = await self._get_tenant(db, order.tenant_id)
        warnings: list[ProviderWarning] = []

        est_hours = estimated_hours
        est_name = name or operation_id
        est_description = description
        if est_hours is None:
            try:
                estimate = await self._get_operation_estimate_cached(db, order, operation_id)
                est_hours = estimate.estimated_hours
                est_name = name or estimate.name
                est_description = description or estimate.description
                warnings.extend(estimate.warnings)
            except LaborProviderError:
                est_hours = Decimal("0.00")
                warnings.append(
                    ProviderWarning(
                        code="provider_unavailable",
                        message="MOTOR estimate unavailable. Enter labor hours manually.",
                    )
                )

        hourly_rate = Decimal(str(tenant.labor_rate))
        line = Labor(
            tenant_id=order.tenant_id,
            repair_order_id=order.id,
            description=est_name,
            hours=Decimal(str(est_hours)),
            hourly_rate=hourly_rate,
            total_cost=_money(Decimal(str(est_hours)) * hourly_rate),
            line_type=LaborLineType.REPAIR_OPERATION,
            provider="motor",
            provider_operation_id=operation_id,
            auto_recalc_enabled=auto_recalc_enabled,
            source_service_id=None,
        )
        if est_description and est_description.strip():
            line.description = est_description.strip()

        db.add(line)
        await db.commit()
        order = await self.load_order(db, order.id)
        result = await self.recalculate_order(db, order)
        result.warnings.extend(warnings)
        return result

    async def update_line(
        self,
        db: AsyncSession,
        order: RepairOrder,
        *,
        line_id: UUID,
        description: Optional[str] = None,
        hours: Optional[Decimal] = None,
        hourly_rate: Optional[Decimal] = None,
        auto_recalc_enabled: Optional[bool] = None,
    ) -> PriceBuildResult:
        self._assert_editable(order)

        line_result = await db.execute(
            select(Labor).where(
                and_(
                    Labor.id == line_id,
                    Labor.repair_order_id == order.id,
                    Labor.tenant_id == order.tenant_id,
                )
            )
        )
        line = line_result.scalar_one_or_none()
        if not line:
            raise PriceBuildNotFoundError("Price build line not found")

        if description is not None:
            line.description = description
        if hours is not None:
            line.hours = hours
        if hourly_rate is not None:
            line.hourly_rate = hourly_rate
        if auto_recalc_enabled is not None:
            line.auto_recalc_enabled = auto_recalc_enabled
        if hours is not None or hourly_rate is not None:
            line.total_cost = _money(Decimal(str(line.hours)) * Decimal(str(line.hourly_rate)))

        await db.commit()
        order = await self.load_order(db, order.id)
        return await self.recalculate_order(db, order)

    async def remove_line(
        self,
        db: AsyncSession,
        order: RepairOrder,
        *,
        line_id: UUID,
    ) -> PriceBuildResult:
        self._assert_editable(order)
        line_result = await db.execute(
            select(Labor).where(
                and_(
                    Labor.id == line_id,
                    Labor.repair_order_id == order.id,
                    Labor.tenant_id == order.tenant_id,
                )
            )
        )
        line = line_result.scalar_one_or_none()
        if not line:
            raise PriceBuildNotFoundError("Price build line not found")
        await db.delete(line)
        await db.commit()
        order = await self.load_order(db, order.id)
        return await self.recalculate_order(db, order)

    async def recalculate_order(self, db: AsyncSession, order: RepairOrder) -> PriceBuildResult:
        started = perf_counter()
        self._assert_editable(order)
        warnings: list[ProviderWarning] = []

        if settings.ENVIRONMENT != "development" and order.status in FINALIZED_STATUSES:
            totals = self._compute_totals(order)
            order.total_parts_cost = totals["parts_total"]
            order.total_labor_cost = totals["labor_total"]
            order.total_cost = totals["total_cost"]
            await db.commit()
            logger.info(
                "price_build_recalculate_skipped_finalized",
                tenant_id=str(order.tenant_id),
                order_id=str(order.id),
                status=order.status.value,
                duration_ms=round((perf_counter() - started) * 1000, 2),
            )
            return PriceBuildResult(order=order, warnings=warnings)

        tenant = await self._get_tenant(db, order.tenant_id)
        for line in order.labor_items:
            if not line.auto_recalc_enabled:
                continue

            if line.line_type == LaborLineType.FLAT_SERVICE and line.source_service_id:
                svc_result = await db.execute(
                    select(Service).where(
                        and_(
                            Service.id == line.source_service_id,
                            Service.tenant_id == order.tenant_id,
                        )
                    )
                )
                service = svc_result.scalar_one_or_none()
                if service:
                    line.description = service.name
                    line.hourly_rate = Decimal(str(service.base_price))
                    line.total_cost = _money(Decimal(str(line.hours)) * Decimal(str(line.hourly_rate)))
            elif (
                line.line_type == LaborLineType.REPAIR_OPERATION
                and line.provider == "motor"
                and line.provider_operation_id
            ):
                try:
                    estimate = await self._get_operation_estimate_cached(db, order, line.provider_operation_id)
                    line.hours = estimate.estimated_hours
                    line.hourly_rate = Decimal(str(tenant.labor_rate))
                    line.total_cost = _money(Decimal(str(line.hours)) * Decimal(str(line.hourly_rate)))
                except LaborProviderError:
                    warnings.append(
                        ProviderWarning(
                            code="provider_unavailable",
                            message=f"Unable to refresh hours for operation {line.provider_operation_id}.",
                        )
                    )

        totals = self._compute_totals(order)
        order.total_parts_cost = totals["parts_total"]
        order.total_labor_cost = totals["labor_total"]
        order.total_cost = totals["total_cost"]
        await db.commit()
        order = await self.load_order(db, order.id)
        logger.info(
            "price_build_recalculated",
            tenant_id=str(order.tenant_id),
            order_id=str(order.id),
            status=order.status.value,
            warnings=len(warnings),
            duration_ms=round((perf_counter() - started) * 1000, 2),
        )
        return PriceBuildResult(order=order, warnings=warnings)

    async def lock_order_pricing(
        self,
        db: AsyncSession,
        order_id: UUID,
        *,
        reason: str = "quote_sent",
    ) -> RepairOrder:
        order = await self.load_order(db, order_id)
        if order.pricing_locked_at is None:
            order.pricing_locked_at = datetime.now(timezone.utc)
        order.pricing_lock_reason = reason
        await db.commit()
        logger.info(
            "price_build_locked",
            tenant_id=str(order.tenant_id),
            order_id=str(order.id),
            reason=reason,
        )
        return await self.load_order(db, order.id)

    def compute_totals(self, order: RepairOrder) -> dict[str, Decimal]:
        return self._compute_totals(order)

    def _assert_editable(self, order: RepairOrder) -> None:
        if _is_locked(order):
            raise PriceBuildLockedError("Pricing is locked for this repair order")
        if order.status not in EDITABLE_RO_STATUSES:
            raise PriceBuildValidationError(
                "Price build lines can only be modified when repair order is draft or quoted"
            )

    def _compute_totals(self, order: RepairOrder) -> dict[str, Decimal]:
        parts_total = _money(sum(Decimal(str(p.total_price)) for p in order.parts_usage))
        labor_total = _money(sum(Decimal(str(l.total_cost)) for l in order.labor_items))
        if labor_total <= Decimal("0.00"):
            legacy_total = _money(get_selected_services_total(order.internal_notes))
            if legacy_total > Decimal("0.00"):
                labor_total = legacy_total
        total_cost = _money(parts_total + labor_total)
        return {
            "parts_total": parts_total,
            "labor_total": labor_total,
            "total_cost": total_cost,
        }

    async def _get_tenant(self, db: AsyncSession, tenant_id: UUID) -> Tenant:
        result = await db.execute(select(Tenant).where(Tenant.id == tenant_id))
        tenant = result.scalar_one_or_none()
        if not tenant:
            raise PriceBuildNotFoundError("Tenant not found")
        return tenant

    async def _get_operation_estimate_cached(
        self,
        db: AsyncSession,
        order: RepairOrder,
        operation_id: str,
    ):
        cache_key = f"operation:{operation_id}"
        cached_candidates = await self._read_cached_candidates(db, order, cache_key)
        if cached_candidates:
            first = cached_candidates[0]
            from app.services.labor_provider.base import ProviderEstimate

            return ProviderEstimate(
                operation_id=first.operation_id,
                name=first.name,
                description=first.description,
                estimated_hours=first.estimated_hours,
                warnings=[],
            )

        estimate = await self.provider.get_operation_estimate(_vehicle_ctx(order), operation_id)
        await self._write_cache(
            db=db,
            order=order,
            operation_key=cache_key,
            normalized_hours=estimate.estimated_hours,
            payload=[
                RepairOperationCandidate(
                    operation_id=estimate.operation_id,
                    name=estimate.name,
                    description=estimate.description,
                    estimated_hours=estimate.estimated_hours,
                    provider="motor",
                )
            ],
        )
        return estimate

    async def _read_cached_candidates(
        self,
        db: AsyncSession,
        order: RepairOrder,
        operation_key: str,
    ) -> list[RepairOperationCandidate]:
        expires_at = datetime.now(timezone.utc) - timedelta(seconds=settings.MOTOR_CACHE_TTL_SECONDS)
        result = await db.execute(
            select(MotorOperationCache).where(
                and_(
                    MotorOperationCache.tenant_id == order.tenant_id,
                    MotorOperationCache.vehicle_fingerprint == _vehicle_fingerprint(order),
                    MotorOperationCache.operation_key == operation_key,
                    MotorOperationCache.last_synced_at >= expires_at,
                )
            )
        )
        row = result.scalar_one_or_none()
        if not row:
            return []
        try:
            parsed = json.loads(row.payload_json)
            out: list[RepairOperationCandidate] = []
            for item in parsed:
                out.append(
                    RepairOperationCandidate(
                        operation_id=str(item.get("operation_id") or ""),
                        name=str(item.get("name") or "Operation"),
                        description=item.get("description"),
                        estimated_hours=Decimal(str(item.get("estimated_hours") or "0")),
                        provider=str(item.get("provider") or "motor"),
                    )
                )
            return out
        except Exception:
            return []

    async def _write_cache(
        self,
        db: AsyncSession,
        order: RepairOrder,
        operation_key: str,
        normalized_hours: Decimal,
        payload: list[RepairOperationCandidate],
    ) -> None:
        now = datetime.now(timezone.utc)
        payload_json = json.dumps(
            [
                {
                    "operation_id": p.operation_id,
                    "name": p.name,
                    "description": p.description,
                    "estimated_hours": str(p.estimated_hours),
                    "provider": p.provider,
                }
                for p in payload
            ]
        )
        result = await db.execute(
            select(MotorOperationCache).where(
                and_(
                    MotorOperationCache.tenant_id == order.tenant_id,
                    MotorOperationCache.vehicle_fingerprint == _vehicle_fingerprint(order),
                    MotorOperationCache.operation_key == operation_key,
                )
            )
        )
        row = result.scalar_one_or_none()
        if row:
            row.normalized_hours = normalized_hours
            row.payload_json = payload_json
            row.last_synced_at = now
        else:
            db.add(
                MotorOperationCache(
                    tenant_id=order.tenant_id,
                    vehicle_fingerprint=_vehicle_fingerprint(order),
                    operation_key=operation_key,
                    normalized_hours=normalized_hours,
                    payload_json=payload_json,
                    last_synced_at=now,
                )
            )
        await db.commit()
