from __future__ import annotations

import math
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from time import perf_counter
from typing import Optional
from uuid import UUID

from sqlalchemy import and_, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import settings
from app.db.models.inventory import Inventory, PartsUsage
from app.db.models.labor import Labor, LaborLineType
from app.db.models.labor_operation_memory import LaborOperationMemory
from app.db.models.repair_order import RepairOrder, RepairOrderStatus
from app.db.models.service import Service, ServicePart
from app.db.models.tenant import Tenant
from app.core.logging import get_logger
from app.services.repair_operation_library import (
    OperationEstimate,
    OperationWarning,
    RepairOperationCandidate,
    build_custom_candidate,
    build_custom_estimate,
    get_library_estimate,
    search_operation_library,
)
from app.services.internal_fleet import fleet_labor_uses_customer_rate
from app.services.pricing import compute_canonical_order_totals
from app.core.work_value_validation import validate_labor_hours, validate_part_quantity


class PriceBuildError(Exception):
    pass


class PriceBuildNotFoundError(PriceBuildError):
    pass


class PriceBuildLockedError(PriceBuildError):
    pass


class PriceBuildConflictError(PriceBuildError):
    pass


class PriceBuildInputError(PriceBuildError):
    pass


class PriceBuildValidationError(PriceBuildError):
    pass


EDITABLE_RO_STATUSES = {
    RepairOrderStatus.DRAFT,
    RepairOrderStatus.QUOTED,
    RepairOrderStatus.DECLINED,
    RepairOrderStatus.APPROVED,
    RepairOrderStatus.ASSIGNED,
    RepairOrderStatus.ACKNOWLEDGED,
    RepairOrderStatus.IN_PROGRESS,
    RepairOrderStatus.PENDING_REVIEW,
}
# Internal fleet work orders log labor/parts throughout their active flow (e.g.
# an in-progress PM) and only freeze once completed/invoiced/paid/cancelled —
# mirrors INTERNAL_FROZEN_RO_STATUSES in the repair_orders endpoints module.
INTERNAL_FROZEN_STATUSES = {
    RepairOrderStatus.COMPLETED,
    RepairOrderStatus.INVOICED,
    RepairOrderStatus.PAID,
    RepairOrderStatus.CANCELLED,
}
FINALIZED_STATUSES = {RepairOrderStatus.INVOICED, RepairOrderStatus.PAID}
logger = get_logger(__name__)
def validate_mechanic_labor_hours(value: Decimal) -> Decimal:
    """Return exact database-safe hours or reject the additive operation."""
    try:
        return validate_labor_hours(value)
    except ValueError as exc:
        raise PriceBuildInputError(str(exc)) from exc


def _validate_price_build_part_quantity(value: Decimal) -> Decimal:
    try:
        return validate_part_quantity(value)
    except ValueError as exc:
        raise PriceBuildInputError(str(exc)) from exc


@dataclass
class PriceBuildResult:
    order: RepairOrder
    warnings: list[OperationWarning]


def _money(value: Decimal) -> Decimal:
    return Decimal(value).quantize(Decimal("0.01"))


def _packages_consumed(quantity: Decimal) -> int:
    """Whole packages/jugs a (possibly fractional) part quantity draws from stock.

    stock_quantity tracks whole packages on hand, not fractional volume, so any
    quantity > 0 rounds up to at least 1 package. See the identical helper in
    app/api/v1/endpoints/repair_orders.py for the same rationale.
    """
    if quantity <= 0:
        return 0
    return max(1, math.ceil(quantity))


def _labor_rate_for(order: RepairOrder, tenant: Tenant) -> Decimal:
    """Internal fleet repairs cost labor at the tenant's internal rate (no markup);
    customer repairs use the billable labor rate."""
    if getattr(order, "is_internal", False) and not fleet_labor_uses_customer_rate(order):
        return Decimal(str(tenant.internal_labor_rate))
    return Decimal(str(tenant.labor_rate))


def _part_unit_price_for(order: RepairOrder, inventory_item: Inventory) -> Decimal:
    """Internal fleet repairs price parts at cost; customer repairs at selling price."""
    if getattr(order, "is_internal", False):
        return Decimal(str(inventory_item.cost))
    return Decimal(str(inventory_item.selling_price))


def _has_reusable_hours(value: Decimal) -> bool:
    return Decimal(str(value)) > Decimal("0.00")


def _is_locked(order: RepairOrder) -> bool:
    if order.pricing_locked_at is None:
        return False
    if order.pricing_lock_reason == "quote_sent":
        return False
    return True


def _vehicle_signature(order: RepairOrder) -> str:
    v = order.vehicle
    if not v:
        return "unknown"
    parts: list[str] = []

    def add(label: str, value: Optional[object]) -> None:
        normalized = _normalize_lookup(None if value is None else str(value))
        if normalized:
            parts.append(f"{label}:{normalized}")

    add("year", getattr(v, "nhtsa_model_year", None) or v.year)
    add("make", getattr(v, "nhtsa_make", None) or v.make)
    add("model", getattr(v, "nhtsa_model", None) or v.model)
    add("vehicle_type", getattr(v, "nhtsa_vehicle_type", None))
    add("body_class", getattr(v, "nhtsa_body_class", None))
    add("drive_type", getattr(v, "nhtsa_drive_type", None))
    add("fuel_type", getattr(v, "nhtsa_fuel_type", None))
    add("engine_cylinders", getattr(v, "nhtsa_engine_cylinders", None))
    add("engine_displacement_l", getattr(v, "nhtsa_engine_displacement_l", None))
    add("gvwr", getattr(v, "nhtsa_gvwr", None))

    return "|".join(parts) if parts else "unknown"


def _legacy_vehicle_signature(order: RepairOrder) -> str:
    v = order.vehicle
    if not v:
        return "unknown"
    return f"{v.year or 'na'}:{(v.make or '').lower()}:{(v.model or '').lower()}"


def _application_vehicle_signature(order: RepairOrder) -> str:
    v = order.vehicle
    if not v:
        return "unknown"
    parts: list[str] = []

    def add(label: str, value: Optional[object]) -> None:
        normalized = _normalize_lookup(None if value is None else str(value))
        if normalized:
            parts.append(f"{label}:{normalized}")

    add("year", getattr(v, "nhtsa_model_year", None) or v.year)
    add("make", getattr(v, "nhtsa_make", None) or v.make)
    add("model", getattr(v, "nhtsa_model", None) or v.model)
    return "|".join(parts) if parts else "unknown"


def _vehicle_signatures(order: RepairOrder) -> list[str]:
    signatures: list[str] = []
    for candidate in (_vehicle_signature(order), _application_vehicle_signature(order), _legacy_vehicle_signature(order)):
        if candidate and candidate not in signatures:
            signatures.append(candidate)
    return signatures or ["unknown"]


def _component_signature(order: RepairOrder) -> Optional[str]:
    """Build a normalized engine-component fingerprint for cross-model matching.

    Uses fuel type, cylinder count, and displacement — enough to uniquely identify
    most heavy-truck engine families (e.g. Cummins ISX15, Detroit DD15).
    Requires at least two populated fields to avoid over-broad matches.
    """
    v = order.vehicle
    if not v:
        return None
    parts: list[str] = []

    def add(label: str, value: Optional[object]) -> None:
        normalized = _normalize_lookup(None if value is None else str(value))
        if normalized:
            parts.append(f"{label}:{normalized}")

    add("fuel_type", getattr(v, "nhtsa_fuel_type", None))
    add("cylinders", getattr(v, "nhtsa_engine_cylinders", None))
    add("displacement_l", getattr(v, "nhtsa_engine_displacement_l", None))

    return "|".join(parts) if len(parts) >= 2 else None


def _normalize_lookup(value: Optional[str]) -> str:
    clean = re.sub(r"\s+", " ", (value or "").strip().lower())
    return clean


def _memory_operation_key(
    *,
    operation_id: Optional[str] = None,
    name: Optional[str] = None,
    description: Optional[str] = None,
) -> Optional[str]:
    if _normalize_lookup(operation_id):
        return f"operation:{_normalize_lookup(operation_id)}"
    if _normalize_lookup(name):
        return f"name:{_normalize_lookup(name)}"
    if _normalize_lookup(description):
        return f"description:{_normalize_lookup(description)}"
    return None


class PriceBuildService:
    async def load_order(
        self,
        db: AsyncSession,
        order_id: UUID,
        *,
        for_update: bool = False,
        tenant_id: Optional[UUID] = None,
    ) -> RepairOrder:
        statement = (
            select(RepairOrder)
            .where(RepairOrder.id == order_id, RepairOrder.deleted_at.is_(None))
            .options(
                selectinload(RepairOrder.vehicle),
                selectinload(RepairOrder.parts_usage).selectinload(PartsUsage.inventory_item),
                selectinload(RepairOrder.labor_items),
            )
            .execution_options(populate_existing=True)
        )
        if tenant_id is not None:
            statement = statement.where(RepairOrder.tenant_id == tenant_id)
        if for_update:
            statement = statement.with_for_update()
        result = await db.execute(statement)
        order = result.scalar_one_or_none()
        if not order:
            raise PriceBuildNotFoundError("Repair order not found")
        return order

    async def add_flat_service_line(
        self,
        db: AsyncSession,
        order: RepairOrder,
        service_id: UUID,
        *,
        quantity: int = 1,
        mechanic_additive_only: bool = False,
    ) -> PriceBuildResult:
        if quantity < 1:
            raise PriceBuildInputError("quantity must be >= 1")

        svc_result = await db.execute(
            select(Service)
            .where(
                and_(
                    Service.id == service_id,
                    Service.tenant_id == order.tenant_id,
                    Service.is_active.is_(True),
                    Service.deleted_at.is_(None),
                )
            )
            .options(
                selectinload(Service.service_parts).selectinload(ServicePart.inventory_item),
            )
        )
        service = svc_result.scalar_one_or_none()
        if not service:
            raise PriceBuildNotFoundError("Source reference not found")

        # Validate every generated numeric value before the repair order or
        # inventory rows are locked and before any existing bundle is reset.
        hours_per_unit = Decimal(service.duration_minutes) / Decimal(60)
        total_hours = validate_mechanic_labor_hours(
            hours_per_unit * Decimal(quantity)
        )
        required_quantities = {
            sp.id: _validate_price_build_part_quantity(
                Decimal(str(sp.quantity)) * Decimal(quantity)
            )
            for sp in service.service_parts
        }

        order = await self.load_order(
            db, order.id, for_update=True, tenant_id=order.tenant_id
        )
        self._assert_editable(order)

        existing_line = next(
            (
                li
                for li in order.labor_items
                if li.source_service_id == service.id
            ),
            None,
        )
        if existing_line and mechanic_additive_only:
            raise PriceBuildConflictError(
                "Mechanics may only add new service lines; an existing service requires staff review"
            )

        tenant = await self._get_tenant(db, order.tenant_id)
        hourly_rate = _labor_rate_for(order, tenant)
        # Labor hours come from the service's duration, scaled by quantity (how many
        # times this service is being performed). A 60-minute service × quantity 2 = 2 hours.
        if existing_line:
            line = existing_line
            line.description = service.name
            line.hours = total_hours
            line.hourly_rate = hourly_rate
            line.total_cost = _money(total_hours * hourly_rate)
            line.line_type = LaborLineType.MANUAL
            line.auto_recalc_enabled = True
            # Reset previously-attached parts so we can re-snapshot at current prices/stock.
            await self._restore_service_parts(db, order, service.id)
        else:
            line = Labor(
                tenant_id=order.tenant_id,
                repair_order_id=order.id,
                service_code=None,
                description=service.name,
                hours=total_hours,
                hourly_rate=hourly_rate,
                total_cost=_money(total_hours * hourly_rate),
                line_type=LaborLineType.MANUAL,
                provider=None,
                provider_operation_id=None,
                auto_recalc_enabled=True,
                source_service_id=service.id,
            )
            db.add(line)
            await db.flush()

        inventory_ids = sorted(
            {
                sp.inventory_item.id
                for sp in service.service_parts
                if sp.inventory_item and sp.inventory_item.deleted_at is None
            },
            key=str,
        )
        locked_inventory: dict[UUID, Inventory] = {}
        if inventory_ids:
            inventory_result = await db.execute(
                select(Inventory)
                .where(
                    Inventory.tenant_id == order.tenant_id,
                    Inventory.id.in_(inventory_ids),
                )
                .order_by(Inventory.id)
                .with_for_update()
            )
            locked_inventory = {
                inventory.id: inventory for inventory in inventory_result.scalars().all()
            }

        # Auto-attach parts bundled with this service. Skip inventory items whose
        # stock would go negative and return an inline warning on the service labor
        # line. Operators can add/override that part explicitly from the operation.
        warnings: list[OperationWarning] = []
        for sp in service.service_parts:
            inv = locked_inventory.get(sp.inventory_item.id) if sp.inventory_item else None
            if not inv or inv.deleted_at is not None:
                continue
            required_qty = required_quantities[sp.id]
            packages_needed = _packages_consumed(required_qty)
            if (inv.stock_quantity or 0) < packages_needed:
                warnings.append(
                    OperationWarning(
                        code="service_part_stock_shortage",
                        line_id=line.id,
                        message=(
                            f"Inventory shortage for bundled part '{inv.name}': "
                            f"have {inv.stock_quantity or 0}, need {required_qty} ({packages_needed} package(s)). "
                            "The service was added without this part."
                        ),
                    )
                )
                continue
            unit_price = _part_unit_price_for(order, inv)
            line_total = _money(unit_price * Decimal(required_qty))
            db.add(
                PartsUsage(
                    tenant_id=order.tenant_id,
                    repair_order_id=order.id,
                    inventory_id=inv.id,
                    quantity=required_qty,
                    unit_cost=inv.cost,
                    unit_price=unit_price,
                    list_price=unit_price,
                    total_price=line_total,
                    source_service_id=service.id,
                )
            )
            inv.stock_quantity = (inv.stock_quantity or 0) - packages_needed

        result = await self.recalculate_order(db, order)
        result.warnings.extend(warnings)
        return result

    async def _search_service_catalog(
        self,
        db: AsyncSession,
        order: RepairOrder,
        query: str,
    ) -> list[RepairOperationCandidate]:
        """Tenant's own Service catalog (My Garage), surfaced as operation candidates
        so package services (PM Level A, kingpin replacement, etc.) are reachable from
        the same search box. Applying one still bundles its parts (see add_flat_service_line) —
        only the search/discovery step is unified, not the underlying pricing model."""
        result = await db.execute(
            select(Service).where(
                and_(
                    Service.tenant_id == order.tenant_id,
                    Service.is_active.is_(True),
                    Service.deleted_at.is_(None),
                    Service.name.ilike(f"%{query}%"),
                )
            ).limit(8)
        )
        services = result.scalars().all()
        return [
            RepairOperationCandidate(
                operation_id=f"service:{svc.id}",
                name=svc.name,
                description=svc.description,
                estimated_hours=(Decimal(svc.duration_minutes) / Decimal(60)),
                provider="service_catalog",
            )
            for svc in services
        ]

    async def search_repair_operations(
        self,
        db: AsyncSession,
        order: RepairOrder,
        query: str,
    ) -> tuple[list[RepairOperationCandidate], list[OperationWarning]]:
        clean_query = (query or "").strip()
        if not clean_query:
            return [], [OperationWarning(code="invalid_query", message="Search query is required.")]

        learned_candidates, match_tier = await self._search_internal_memory(db, order, clean_query)
        service_candidates = await self._search_service_catalog(db, order, clean_query)
        library_candidates = search_operation_library(clean_query)
        candidates = self._merge_candidates(learned_candidates, self._merge_candidates(service_candidates, library_candidates))
        warnings: list[OperationWarning] = []
        if learned_candidates:
            if match_tier == "component":
                warnings.append(
                    OperationWarning(
                        code="component_memory_hit",
                        message="Using saved labor hours from a truck with the same engine configuration.",
                    )
                )
            else:
                warnings.append(
                    OperationWarning(
                        code="internal_memory_hit",
                        message="Using saved labor hours from previous matching jobs.",
                    )
                )
        if candidates:
            return candidates, warnings

        return [build_custom_candidate(clean_query)], [
            OperationWarning(
                code="no_saved_match",
                message="No saved labor match yet. Add hours once and future matching jobs will reuse them.",
            )
        ]

    async def add_repair_operation_line(
        self,
        db: AsyncSession,
        order: RepairOrder,
        *,
        operation_id: str,
        name: Optional[str] = None,
        description: Optional[str] = None,
        estimated_hours: Optional[Decimal] = None,
        provider: Optional[str] = None,
        auto_recalc_enabled: bool = True,
        mechanic_additive_only: bool = False,
    ) -> PriceBuildResult:
        # Service-catalog candidates (operation_id="service:<uuid>") carry their own
        # parts bundle and pricing — route to the existing flat-service path instead
        # of creating a bare labor line, so PM/kingpin-style packages still attach
        # their parts automatically when picked from the unified operation search.
        if operation_id.startswith("service:"):
            service_id = UUID(operation_id[len("service:"):])
            return await self.add_flat_service_line(
                db,
                order,
                service_id,
                quantity=1,
                mechanic_additive_only=mechanic_additive_only,
            )

        warnings: list[OperationWarning] = []

        est_hours = estimated_hours
        est_name = name or operation_id
        est_description = description
        resolved_provider = provider or "internal_library"
        if est_hours is None:
            estimate = await self._get_operation_estimate(db, order, operation_id, name=name)
            est_hours = estimate.estimated_hours
            est_name = name or estimate.name
            est_description = description or estimate.description
            warnings.extend(estimate.warnings)
            resolved_provider = provider or estimate.provider
        est_hours = validate_mechanic_labor_hours(est_hours)

        order = await self.load_order(
            db, order.id, for_update=True, tenant_id=order.tenant_id
        )
        self._assert_editable(order)
        tenant = await self._get_tenant(db, order.tenant_id)

        hourly_rate = _labor_rate_for(order, tenant)
        line = Labor(
            tenant_id=order.tenant_id,
            repair_order_id=order.id,
            description=est_name,
            hours=Decimal(str(est_hours)),
            hourly_rate=hourly_rate,
            total_cost=_money(Decimal(str(est_hours)) * hourly_rate),
            line_type=LaborLineType.REPAIR_OPERATION,
            provider=resolved_provider,
            provider_operation_id=operation_id,
            auto_recalc_enabled=auto_recalc_enabled,
            source_service_id=None,
        )

        db.add(line)
        await self._upsert_internal_memory(
            db=db,
            order=order,
            operation_id=operation_id,
            name=est_name,
            description=est_description,
            hours=Decimal(str(est_hours)),
            source_provider=resolved_provider,
        )
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
        if hours is not None:
            hours = validate_mechanic_labor_hours(hours)

        order = await self.load_order(
            db, order.id, for_update=True, tenant_id=order.tenant_id
        )
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
            # A manual rate edit is the user overriding the shop default —
            # stop auto-recalc from reapplying that default on the very next
            # recalculate_order() call below (and on every later edit to this
            # line), unless the caller explicitly says otherwise.
            if auto_recalc_enabled is None:
                line.auto_recalc_enabled = False
        if auto_recalc_enabled is not None:
            line.auto_recalc_enabled = auto_recalc_enabled
        if hours is not None or hourly_rate is not None:
            line.total_cost = _money(Decimal(str(line.hours)) * Decimal(str(line.hourly_rate)))

        if line.line_type == LaborLineType.REPAIR_OPERATION:
            await self._upsert_internal_memory(
                db=db,
                order=order,
                operation_id=line.provider_operation_id,
                name=line.description,
                description=line.description,
                hours=Decimal(str(line.hours)),
                source_provider=line.provider or "internal_memory",
            )

        return await self.recalculate_order(db, order)

    async def remove_line(
        self,
        db: AsyncSession,
        order: RepairOrder,
        *,
        line_id: UUID,
    ) -> PriceBuildResult:
        order = await self.load_order(db, order.id, for_update=True)
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
        # If this labor line came from a Service, also release its bundled parts.
        if line.source_service_id:
            await self._restore_service_parts(db, order, line.source_service_id)
        # Parts attached directly to this line (free-form operations) are kept as
        # standalone parts — clear the link so they survive the line deletion.
        # The FK is ON DELETE SET NULL in Postgres; do it explicitly here too so
        # the behavior holds regardless of DB-level FK enforcement.
        await db.execute(
            update(PartsUsage)
            .where(PartsUsage.source_line_id == line.id)
            .values(source_line_id=None)
        )
        await db.delete(line)
        return await self.recalculate_order(db, order)

    async def _restore_service_parts(
        self,
        db: AsyncSession,
        order: RepairOrder,
        service_id: UUID,
    ) -> None:
        """Delete PartsUsage rows auto-added for this service and restore stock."""
        pu_result = await db.execute(
            select(PartsUsage).where(
                and_(
                    PartsUsage.repair_order_id == order.id,
                    PartsUsage.source_service_id == service_id,
                )
            )
        )
        parts = pu_result.scalars().all()
        inventory_ids = sorted({pu.inventory_id for pu in parts}, key=str)
        locked_inventory: dict[UUID, Inventory] = {}
        if inventory_ids:
            inv_result = await db.execute(
                select(Inventory)
                .where(
                    Inventory.tenant_id == order.tenant_id,
                    Inventory.id.in_(inventory_ids),
                )
                .order_by(Inventory.id)
                .with_for_update()
            )
            locked_inventory = {
                inventory.id: inventory for inventory in inv_result.scalars().all()
            }
        for pu in parts:
            inv = locked_inventory.get(pu.inventory_id)
            if inv:
                inv.stock_quantity = (inv.stock_quantity or 0) + _packages_consumed(pu.quantity)
            await db.delete(pu)

    async def recalculate_order(self, db: AsyncSession, order: RepairOrder) -> PriceBuildResult:
        started = perf_counter()
        # Flush pending child mutations, then refresh canonical children while
        # retaining the same repair-order row lock. The eventual commit owns the
        # child/stock changes and their derived totals together.
        await db.flush()
        order = await self.load_order(db, order.id, for_update=True)
        self._assert_editable(order)
        warnings: list[OperationWarning] = []

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

            if line.source_service_id:
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
                # Service-sourced lines are billed as labor-hour units.
                if line.line_type == LaborLineType.FLAT_SERVICE:
                    line.line_type = LaborLineType.MANUAL
                line.hourly_rate = _labor_rate_for(order, tenant)
                line.total_cost = _money(Decimal(str(line.hours)) * Decimal(str(line.hourly_rate)))
            elif line.line_type == LaborLineType.REPAIR_OPERATION and line.provider_operation_id:
                estimate = await self._get_operation_estimate(
                    db,
                    order,
                    line.provider_operation_id,
                    name=line.description,
                )
                line.hours = estimate.estimated_hours
                line.hourly_rate = _labor_rate_for(order, tenant)
                line.total_cost = _money(Decimal(str(line.hours)) * Decimal(str(line.hourly_rate)))
                warnings.extend(estimate.warnings)

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
        order = await self.load_order(db, order_id, for_update=True)
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
        # Both internal and customer repair orders are live work records. They
        # stay editable until the work is finalized/invoiced.
        if getattr(order, "is_internal", False):
            if order.status in INTERNAL_FROZEN_STATUSES:
                raise PriceBuildValidationError(
                    "Price build lines can't be modified after the work order is completed"
                )
            return
        if order.status not in EDITABLE_RO_STATUSES:
            raise PriceBuildValidationError(
                "Price build lines can't be modified after the repair order is finalized"
            )

    def _compute_totals(self, order: RepairOrder) -> dict[str, Decimal]:
        return compute_canonical_order_totals(order)

    async def _get_tenant(self, db: AsyncSession, tenant_id: UUID) -> Tenant:
        result = await db.execute(select(Tenant).where(Tenant.id == tenant_id))
        tenant = result.scalar_one_or_none()
        if not tenant:
            raise PriceBuildNotFoundError("Tenant not found")
        return tenant

    async def _get_operation_estimate(
        self,
        db: AsyncSession,
        order: RepairOrder,
        operation_id: str,
        *,
        name: Optional[str] = None,
    ) -> OperationEstimate:
        learned_estimate = await self._read_internal_memory_estimate(
            db,
            order,
            operation_id=operation_id,
        )
        if learned_estimate:
            return learned_estimate

        library_estimate = get_library_estimate(operation_id)
        if library_estimate:
            return library_estimate

        return build_custom_estimate(operation_id, name=name)

    async def _search_internal_memory(
        self,
        db: AsyncSession,
        order: RepairOrder,
        query: str,
    ) -> tuple[list[RepairOperationCandidate], str]:
        """Two-pass memory search.

        Pass 1 — exact vehicle signature match (same make/model/year/engine).
        Pass 2 — component signature fallback (same engine family, different model).

        Returns (candidates, match_tier) where match_tier is "vehicle", "component", or "".
        """
        pattern = f"%{_normalize_lookup(query)}%"
        keyword_filter = or_(
            LaborOperationMemory.operation_key.ilike(pattern),
            LaborOperationMemory.operation_name.ilike(pattern),
            LaborOperationMemory.operation_description.ilike(pattern),
            LaborOperationMemory.provider_operation_id.ilike(pattern),
        )

        result = await db.execute(
            select(LaborOperationMemory)
            .where(
                and_(
                    LaborOperationMemory.tenant_id == order.tenant_id,
                    LaborOperationMemory.normalized_hours > 0,
                    LaborOperationMemory.vehicle_signature.in_(_vehicle_signatures(order)),
                    keyword_filter,
                )
            )
            .order_by(
                LaborOperationMemory.usage_count.desc(),
                LaborOperationMemory.last_used_at.desc(),
            )
            .limit(8)
        )
        rows = result.scalars().all()
        if rows:
            return self._dedupe_candidates(rows), "vehicle"

        comp_sig = _component_signature(order)
        if not comp_sig:
            return [], ""

        comp_result = await db.execute(
            select(LaborOperationMemory)
            .where(
                and_(
                    LaborOperationMemory.tenant_id == order.tenant_id,
                    LaborOperationMemory.normalized_hours > 0,
                    LaborOperationMemory.component_signature == comp_sig,
                    keyword_filter,
                )
            )
            .order_by(
                LaborOperationMemory.usage_count.desc(),
                LaborOperationMemory.last_used_at.desc(),
            )
            .limit(8)
        )
        comp_rows = comp_result.scalars().all()
        return self._dedupe_candidates(comp_rows), ("component" if comp_rows else "")

    def _dedupe_candidates(self, rows: list[LaborOperationMemory]) -> list[RepairOperationCandidate]:
        seen: set[str] = set()
        out: list[RepairOperationCandidate] = []
        for row in rows:
            candidate = self._memory_candidate(row)
            dedupe_key = _normalize_lookup(candidate.operation_id or row.operation_key)
            if dedupe_key in seen:
                continue
            seen.add(dedupe_key)
            out.append(candidate)
        return out

    async def _read_internal_memory_estimate(
        self,
        db: AsyncSession,
        order: RepairOrder,
        *,
        operation_id: Optional[str] = None,
        name: Optional[str] = None,
        description: Optional[str] = None,
    ) -> Optional[OperationEstimate]:
        operation_key = _memory_operation_key(
            operation_id=operation_id,
            name=name,
            description=description,
        )
        if not operation_key:
            return None

        # Pass 1: exact vehicle signature match
        result = await db.execute(
            select(LaborOperationMemory).where(
                and_(
                    LaborOperationMemory.tenant_id == order.tenant_id,
                    LaborOperationMemory.normalized_hours > 0,
                    LaborOperationMemory.vehicle_signature.in_(_vehicle_signatures(order)),
                    LaborOperationMemory.operation_key == operation_key,
                )
            )
        )
        rows = result.scalars().all()
        if rows:
            row = next((item for item in rows if item.vehicle_signature == _vehicle_signature(order)), rows[0])
            return OperationEstimate(
                operation_id=row.provider_operation_id or operation_id or row.operation_key,
                name=row.operation_name,
                description=row.operation_description,
                estimated_hours=Decimal(str(row.normalized_hours)),
                warnings=[],
                provider="internal_memory",
            )

        # Pass 2: component signature fallback
        comp_sig = _component_signature(order)
        if not comp_sig:
            return None

        comp_result = await db.execute(
            select(LaborOperationMemory)
            .where(
                and_(
                    LaborOperationMemory.tenant_id == order.tenant_id,
                    LaborOperationMemory.normalized_hours > 0,
                    LaborOperationMemory.component_signature == comp_sig,
                    LaborOperationMemory.operation_key == operation_key,
                )
            )
            .order_by(
                LaborOperationMemory.usage_count.desc(),
                LaborOperationMemory.last_used_at.desc(),
            )
            .limit(1)
        )
        comp_rows = comp_result.scalars().all()
        if not comp_rows:
            return None
        row = comp_rows[0]
        return OperationEstimate(
            operation_id=row.provider_operation_id or operation_id or row.operation_key,
            name=row.operation_name,
            description=row.operation_description,
            estimated_hours=Decimal(str(row.normalized_hours)),
            warnings=[],
            provider="internal_memory",
        )

    async def _upsert_internal_memory(
        self,
        db: AsyncSession,
        order: RepairOrder,
        *,
        operation_id: Optional[str],
        name: Optional[str],
        description: Optional[str],
        hours: Decimal,
        source_provider: Optional[str],
    ) -> None:
        operation_key = _memory_operation_key(
            operation_id=operation_id,
            name=name,
            description=description,
        )
        if not operation_key or not _has_reusable_hours(hours):
            return

        now = datetime.now(timezone.utc)
        preferred_signature = _vehicle_signature(order)
        comp_sig = _component_signature(order)
        result = await db.execute(
            select(LaborOperationMemory).where(
                and_(
                    LaborOperationMemory.tenant_id == order.tenant_id,
                    LaborOperationMemory.vehicle_signature.in_(_vehicle_signatures(order)),
                    LaborOperationMemory.operation_key == operation_key,
                )
            )
        )
        rows = result.scalars().all()
        row = next((item for item in rows if item.vehicle_signature == preferred_signature), rows[0] if rows else None)
        operation_name = (name or description or operation_id or "Operation").strip()
        operation_description = description.strip() if description else None
        vehicle = order.vehicle
        if row:
            row.vehicle_signature = preferred_signature
            row.component_signature = comp_sig
            row.operation_name = operation_name
            row.operation_description = operation_description
            if vehicle:
                row.vehicle_year = getattr(vehicle, "nhtsa_model_year", None) or vehicle.year
                row.vehicle_make = getattr(vehicle, "nhtsa_make", None) or vehicle.make
                row.vehicle_model = getattr(vehicle, "nhtsa_model", None) or vehicle.model
                row.vehicle_type = getattr(vehicle, "nhtsa_vehicle_type", None)
                row.body_class = getattr(vehicle, "nhtsa_body_class", None)
                row.fuel_type = getattr(vehicle, "nhtsa_fuel_type", None)
                row.engine_cylinders = getattr(vehicle, "nhtsa_engine_cylinders", None)
                row.engine_displacement_l = getattr(vehicle, "nhtsa_engine_displacement_l", None)
                row.gvwr = getattr(vehicle, "nhtsa_gvwr", None)
                row.vin_sample = vehicle.vin
            row.provider_operation_id = operation_id
            row.source_provider = source_provider or row.source_provider or "internal_memory"
            row.normalized_hours = Decimal(str(hours))
            row.usage_count = int(row.usage_count or 0) + 1
            row.last_used_at = now
            return

        db.add(
            LaborOperationMemory(
                tenant_id=order.tenant_id,
                vehicle_signature=preferred_signature,
                component_signature=comp_sig,
                operation_key=operation_key,
                operation_name=operation_name,
                operation_description=operation_description,
                vehicle_year=(getattr(vehicle, "nhtsa_model_year", None) or vehicle.year) if vehicle else None,
                vehicle_make=(getattr(vehicle, "nhtsa_make", None) or vehicle.make) if vehicle else None,
                vehicle_model=(getattr(vehicle, "nhtsa_model", None) or vehicle.model) if vehicle else None,
                vehicle_type=getattr(vehicle, "nhtsa_vehicle_type", None) if vehicle else None,
                body_class=getattr(vehicle, "nhtsa_body_class", None) if vehicle else None,
                fuel_type=getattr(vehicle, "nhtsa_fuel_type", None) if vehicle else None,
                engine_cylinders=getattr(vehicle, "nhtsa_engine_cylinders", None) if vehicle else None,
                engine_displacement_l=getattr(vehicle, "nhtsa_engine_displacement_l", None) if vehicle else None,
                gvwr=getattr(vehicle, "nhtsa_gvwr", None) if vehicle else None,
                vin_sample=vehicle.vin if vehicle else None,
                provider_operation_id=operation_id,
                source_provider=source_provider or "internal_memory",
                normalized_hours=Decimal(str(hours)),
                usage_count=1,
                last_used_at=now,
            )
        )

    def _memory_candidate(self, row: LaborOperationMemory) -> RepairOperationCandidate:
        return RepairOperationCandidate(
            operation_id=row.provider_operation_id or row.operation_key,
            name=row.operation_name,
            description=row.operation_description,
            estimated_hours=Decimal(str(row.normalized_hours)),
            provider="internal_memory",
        )

    def _merge_candidates(
        self,
        preferred: list[RepairOperationCandidate],
        secondary: list[RepairOperationCandidate],
    ) -> list[RepairOperationCandidate]:
        merged: list[RepairOperationCandidate] = []
        seen: set[str] = set()
        for candidate in [*preferred, *secondary]:
            key = _normalize_lookup(candidate.operation_id)
            if key in seen:
                continue
            seen.add(key)
            merged.append(candidate)
        return merged[:8]
