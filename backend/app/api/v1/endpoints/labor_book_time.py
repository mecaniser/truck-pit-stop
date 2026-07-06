from __future__ import annotations

import re
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_active_user, get_db
from app.db.models.labor_operation_memory import LaborOperationMemory
from app.db.models.user import User, UserRole


router = APIRouter()


class LaborBookTimeEntryResponse(BaseModel):
    id: str
    operation_name: str
    operation_description: Optional[str] = None
    normalized_hours: str
    vehicle_year: Optional[int] = None
    vehicle_make: Optional[str] = None
    vehicle_model: Optional[str] = None
    vehicle_type: Optional[str] = None
    body_class: Optional[str] = None
    engine: Optional[str] = None
    fuel_type: Optional[str] = None
    engine_cylinders: Optional[int] = None
    engine_displacement_l: Optional[float] = None
    gvwr: Optional[str] = None
    vin_sample: Optional[str] = None
    vehicle_signature: str
    component_signature: Optional[str] = None
    operation_key: str
    provider_operation_id: Optional[str] = None
    source_provider: str
    usage_count: int
    last_used_at: datetime
    created_at: datetime
    updated_at: datetime


class LaborBookTimeScopePayload(BaseModel):
    vehicle_year: Optional[int] = Field(default=None, ge=1900, le=2100)
    vehicle_make: Optional[str] = Field(default=None, max_length=100)
    vehicle_model: Optional[str] = Field(default=None, max_length=100)
    vehicle_type: Optional[str] = Field(default=None, max_length=100)
    body_class: Optional[str] = Field(default=None, max_length=150)
    engine: Optional[str] = Field(default=None, max_length=150)
    fuel_type: Optional[str] = Field(default=None, max_length=100)
    engine_cylinders: Optional[int] = Field(default=None, ge=1, le=24)
    engine_displacement_l: Optional[float] = Field(default=None, gt=0, le=30)
    gvwr: Optional[str] = Field(default=None, max_length=100)
    vin_sample: Optional[str] = Field(default=None, max_length=17)


class LaborBookTimeEntryCreate(LaborBookTimeScopePayload):
    operation_name: str = Field(..., min_length=1, max_length=255)
    operation_description: Optional[str] = Field(default=None, max_length=1000)
    normalized_hours: Decimal = Field(..., gt=Decimal("0"), le=Decimal("99.99"))


class LaborBookTimeEntryUpdate(LaborBookTimeScopePayload):
    operation_name: Optional[str] = Field(default=None, min_length=1, max_length=255)
    operation_description: Optional[str] = Field(default=None, max_length=1000)
    normalized_hours: Optional[Decimal] = Field(default=None, gt=Decimal("0"), le=Decimal("99.99"))


def _require_garage_admin(current_user: User) -> User:
    if current_user.role not in (UserRole.GARAGE_OWNER, UserRole.GARAGE_ADMIN):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Garage owner/admin access required",
        )
    if not current_user.tenant_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User must be associated with a tenant",
        )
    return current_user


def _clean_text(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    clean = re.sub(r"\s+", " ", value.strip())
    return clean or None


def _normalize_lookup(value: Optional[object]) -> str:
    return re.sub(r"\s+", " ", "" if value is None else str(value).strip().lower())


def _slug(value: Optional[object]) -> str:
    clean = _normalize_lookup(value)
    return re.sub(r"[^a-z0-9]+", "-", clean).strip("-")


def _build_vehicle_signature(payload: LaborBookTimeScopePayload) -> str:
    parts: list[str] = []

    def add(label: str, value: Optional[object]) -> None:
        normalized = _normalize_lookup(value)
        if normalized:
            parts.append(f"{label}:{normalized}")

    add("year", payload.vehicle_year)
    add("make", payload.vehicle_make)
    add("model", payload.vehicle_model)
    return "|".join(parts) if parts else "unknown"


def _build_component_signature(payload: LaborBookTimeScopePayload) -> Optional[str]:
    parts: list[str] = []

    def add(label: str, value: Optional[object]) -> None:
        normalized = _normalize_lookup(value)
        if normalized:
            parts.append(f"{label}:{normalized}")

    add("engine", payload.engine)
    add("fuel_type", payload.fuel_type)
    add("cylinders", payload.engine_cylinders)
    add("displacement_l", payload.engine_displacement_l)
    return "|".join(parts) if parts else None


def _build_operation_key_from_values(
    *,
    name: str,
    engine: Optional[str],
    vehicle_make: Optional[str],
    vehicle_model: Optional[str],
    vehicle_year: Optional[int],
) -> str:
    base = _slug(name) or "operation"
    qualifiers = [
        _slug(engine),
        _slug(vehicle_make),
        _slug(vehicle_model),
        _slug(vehicle_year),
    ]
    suffix = "-".join(part for part in qualifiers if part)
    return f"custom:{base}:{suffix}" if suffix else f"custom:{base}"


def _apply_scope(entry: LaborOperationMemory, payload: LaborBookTimeScopePayload) -> None:
    entry.vehicle_year = payload.vehicle_year
    entry.vehicle_make = _clean_text(payload.vehicle_make)
    entry.vehicle_model = _clean_text(payload.vehicle_model)
    entry.vehicle_type = _clean_text(payload.vehicle_type)
    entry.body_class = _clean_text(payload.body_class)
    entry.engine = _clean_text(payload.engine)
    entry.fuel_type = _clean_text(payload.fuel_type)
    entry.engine_cylinders = payload.engine_cylinders
    entry.engine_displacement_l = payload.engine_displacement_l
    entry.gvwr = _clean_text(payload.gvwr)
    entry.vin_sample = _clean_text(payload.vin_sample.upper() if payload.vin_sample else None)
    entry.vehicle_signature = _build_vehicle_signature(payload)
    entry.component_signature = _build_component_signature(payload)


def _serialize_entry(entry: LaborOperationMemory) -> LaborBookTimeEntryResponse:
    return LaborBookTimeEntryResponse(
        id=str(entry.id),
        operation_name=entry.operation_name,
        operation_description=entry.operation_description,
        normalized_hours=str(Decimal(str(entry.normalized_hours)).quantize(Decimal("0.01"))),
        vehicle_year=entry.vehicle_year,
        vehicle_make=entry.vehicle_make,
        vehicle_model=entry.vehicle_model,
        vehicle_type=entry.vehicle_type,
        body_class=entry.body_class,
        engine=entry.engine,
        fuel_type=entry.fuel_type,
        engine_cylinders=entry.engine_cylinders,
        engine_displacement_l=entry.engine_displacement_l,
        gvwr=entry.gvwr,
        vin_sample=entry.vin_sample,
        vehicle_signature=entry.vehicle_signature,
        component_signature=entry.component_signature,
        operation_key=entry.operation_key,
        provider_operation_id=entry.provider_operation_id,
        source_provider=entry.source_provider,
        usage_count=int(entry.usage_count or 0),
        last_used_at=entry.last_used_at,
        created_at=entry.created_at,
        updated_at=entry.updated_at,
    )


async def _load_tenant_entry(
    db: AsyncSession,
    current_user: User,
    entry_id: UUID,
) -> LaborOperationMemory:
    result = await db.execute(
        select(LaborOperationMemory).where(
            and_(
                LaborOperationMemory.id == entry_id,
                LaborOperationMemory.tenant_id == current_user.tenant_id,
                LaborOperationMemory.deleted_at.is_(None),
            )
        )
    )
    entry = result.scalar_one_or_none()
    if not entry:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Labor book time entry not found")
    return entry


@router.get("", response_model=list[LaborBookTimeEntryResponse])
async def list_labor_book_time_entries(
    q: str = Query("", max_length=120),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    current_user = _require_garage_admin(current_user)

    filters = [
        LaborOperationMemory.tenant_id == current_user.tenant_id,
        LaborOperationMemory.deleted_at.is_(None),
        LaborOperationMemory.normalized_hours > 0,
    ]
    search = q.strip()
    if search:
        pattern = f"%{search}%"
        filters.append(
            or_(
                LaborOperationMemory.operation_name.ilike(pattern),
                LaborOperationMemory.operation_description.ilike(pattern),
                LaborOperationMemory.operation_key.ilike(pattern),
                LaborOperationMemory.vehicle_signature.ilike(pattern),
                LaborOperationMemory.vehicle_make.ilike(pattern),
                LaborOperationMemory.vehicle_model.ilike(pattern),
                LaborOperationMemory.engine.ilike(pattern),
                LaborOperationMemory.vin_sample.ilike(pattern),
            )
        )

    result = await db.execute(
        select(LaborOperationMemory)
        .where(and_(*filters))
        .order_by(LaborOperationMemory.last_used_at.desc(), LaborOperationMemory.operation_name.asc())
        .limit(250)
    )
    return [_serialize_entry(entry) for entry in result.scalars().all()]


@router.post("", response_model=LaborBookTimeEntryResponse, status_code=status.HTTP_201_CREATED)
async def create_labor_book_time_entry(
    body: LaborBookTimeEntryCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    current_user = _require_garage_admin(current_user)
    name = body.operation_name.strip()
    if not body.vehicle_year or not _clean_text(body.vehicle_make) or not _clean_text(body.vehicle_model):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Year, make, and model are required for Labor Book Time entries",
        )

    operation_key = _build_operation_key_from_values(
        name=name,
        engine=body.engine,
        vehicle_make=body.vehicle_make,
        vehicle_model=body.vehicle_model,
        vehicle_year=body.vehicle_year,
    )
    vehicle_signature = _build_vehicle_signature(body)
    existing = await db.execute(
        select(LaborOperationMemory).where(
            and_(
                LaborOperationMemory.tenant_id == current_user.tenant_id,
                LaborOperationMemory.vehicle_signature == vehicle_signature,
                LaborOperationMemory.operation_key == operation_key,
                LaborOperationMemory.deleted_at.is_(None),
            )
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A matching labor book time entry already exists for this truck application",
        )

    now = datetime.now(timezone.utc)
    entry = LaborOperationMemory(
        tenant_id=current_user.tenant_id,
        operation_key=operation_key,
        operation_name=name,
        operation_description=_clean_text(body.operation_description),
        provider_operation_id=operation_key,
        source_provider="manual_book_time",
        normalized_hours=Decimal(str(body.normalized_hours)).quantize(Decimal("0.01")),
        usage_count=1,
        last_used_at=now,
        vehicle_signature=vehicle_signature,
    )
    _apply_scope(entry, body)
    db.add(entry)
    await db.commit()
    await db.refresh(entry)
    return _serialize_entry(entry)


@router.patch("/{entry_id}", response_model=LaborBookTimeEntryResponse)
async def update_labor_book_time_entry(
    entry_id: UUID,
    body: LaborBookTimeEntryUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    current_user = _require_garage_admin(current_user)
    entry = await _load_tenant_entry(db, current_user, entry_id)

    if body.operation_name is not None:
        name = body.operation_name.strip()
        if not name:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Operation name is required")
        entry.operation_name = name
    if body.operation_description is not None:
        entry.operation_description = body.operation_description.strip() or None
    if body.normalized_hours is not None:
        entry.normalized_hours = Decimal(str(body.normalized_hours)).quantize(Decimal("0.01"))
    scope_fields = {
        "vehicle_year",
        "vehicle_make",
        "vehicle_model",
        "vehicle_type",
        "body_class",
        "engine",
        "fuel_type",
        "engine_cylinders",
        "engine_displacement_l",
        "gvwr",
        "vin_sample",
    }
    if scope_fields & body.model_fields_set:
        merged = LaborBookTimeScopePayload(
            vehicle_year=body.vehicle_year if "vehicle_year" in body.model_fields_set else entry.vehicle_year,
            vehicle_make=body.vehicle_make if "vehicle_make" in body.model_fields_set else entry.vehicle_make,
            vehicle_model=body.vehicle_model if "vehicle_model" in body.model_fields_set else entry.vehicle_model,
            vehicle_type=body.vehicle_type if "vehicle_type" in body.model_fields_set else entry.vehicle_type,
            body_class=body.body_class if "body_class" in body.model_fields_set else entry.body_class,
            engine=body.engine if "engine" in body.model_fields_set else entry.engine,
            fuel_type=body.fuel_type if "fuel_type" in body.model_fields_set else entry.fuel_type,
            engine_cylinders=body.engine_cylinders if "engine_cylinders" in body.model_fields_set else entry.engine_cylinders,
            engine_displacement_l=body.engine_displacement_l if "engine_displacement_l" in body.model_fields_set else entry.engine_displacement_l,
            gvwr=body.gvwr if "gvwr" in body.model_fields_set else entry.gvwr,
            vin_sample=body.vin_sample if "vin_sample" in body.model_fields_set else entry.vin_sample,
        )
        _apply_scope(entry, merged)
    if (body.operation_name is not None) or (scope_fields & body.model_fields_set):
        entry.operation_key = _build_operation_key_from_values(
            name=entry.operation_name,
            engine=entry.engine,
            vehicle_make=entry.vehicle_make,
            vehicle_model=entry.vehicle_model,
            vehicle_year=entry.vehicle_year,
        )
        entry.provider_operation_id = entry.operation_key

    await db.commit()
    await db.refresh(entry)
    return _serialize_entry(entry)


@router.delete("/{entry_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_labor_book_time_entry(
    entry_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    current_user = _require_garage_admin(current_user)
    entry = await _load_tenant_entry(db, current_user, entry_id)

    await db.delete(entry)
    await db.commit()
    return None
