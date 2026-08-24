from decimal import Decimal
from typing import List, Optional
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from pydantic import BaseModel, Field

from app.core.dependencies import get_db, get_current_active_user
from app.core.pagination import paginated_or_list
from app.core.search import build_search
from app.db.models.user import User, UserRole
from app.db.models.supplier import Supplier
from app.services.parts_operations_service import normalize_name

router = APIRouter()


class SupplierBase(BaseModel):
    name: str
    address: Optional[str] = None
    phone: Optional[str] = None
    contact_name: Optional[str] = None
    notes: Optional[str] = None
    account_reference: Optional[str] = None
    email: Optional[str] = None


class SupplierCreate(SupplierBase):
    payment_terms: Optional[str] = Field(default=None, max_length=100)
    default_lead_time_days: Optional[int] = Field(default=None, ge=0, le=365)
    minimum_order_amount: Optional[Decimal] = Field(
        default=None,
        ge=Decimal("0"),
        le=Decimal("9999999999.99"),
    )
    purchasing_notes: Optional[str] = None


class SupplierUpdate(BaseModel):
    name: Optional[str] = None
    address: Optional[str] = None
    phone: Optional[str] = None
    contact_name: Optional[str] = None
    notes: Optional[str] = None
    account_reference: Optional[str] = None
    email: Optional[str] = None
    payment_terms: Optional[str] = Field(default=None, max_length=100)
    default_lead_time_days: Optional[int] = Field(default=None, ge=0, le=365)
    minimum_order_amount: Optional[Decimal] = Field(
        default=None,
        ge=Decimal("0"),
        le=Decimal("9999999999.99"),
    )
    purchasing_notes: Optional[str] = None
    is_active: Optional[bool] = None


class SupplierResponse(SupplierBase):
    id: UUID
    tenant_id: UUID
    normalized_name: Optional[str] = None
    is_active: bool = True
    account_reference: Optional[str] = None
    email: Optional[str] = None

    class Config:
        from_attributes = True


class SupplierAdminResponse(SupplierResponse):
    payment_terms: Optional[str] = None
    default_lead_time_days: Optional[int] = None
    minimum_order_amount: Optional[Decimal] = None
    purchasing_notes: Optional[str] = None


def _tenant_id(current_user: User) -> UUID:
    """Require a server-derived shop boundary for every legacy supplier path."""
    if not current_user.tenant_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")
    return current_user.tenant_id


def _not_found() -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")


def _admin_tenant_id(current_user: User) -> UUID:
    if current_user.role not in [UserRole.GARAGE_OWNER, UserRole.GARAGE_ADMIN]:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")
    return _tenant_id(current_user)


def require_admin():
    async def role_checker(current_user: User = Depends(get_current_active_user)):
        _admin_tenant_id(current_user)
        return current_user
    return role_checker


@router.get("", response_model=List[SupplierResponse])
async def list_suppliers(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=100),
    paginated: bool = Query(False),
    search: Optional[str] = Query(None, description="Filter by name, contact, phone, or address"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    tenant_id = _tenant_id(current_user)
    query = select(Supplier).where(
        Supplier.tenant_id == tenant_id,
        Supplier.deleted_at.is_(None),
    )

    count_query = select(func.count(Supplier.id)).where(
        Supplier.tenant_id == tenant_id,
        Supplier.deleted_at.is_(None),
    )

    order_by = [Supplier.name]
    if search and search.strip():
        # Shared search semantics (app/core/search.py): ILIKE + squashed
        # phone/name matching + pg_trgm typo tolerance, ranked by relevance.
        search_filter, relevance = build_search(
            search,
            primary=[Supplier.name, Supplier.contact_name],
            squashed=[Supplier.name, Supplier.phone],
            secondary=[Supplier.address, Supplier.notes],
            similarity=[Supplier.name],
        )
        query = query.where(search_filter)
        count_query = count_query.where(search_filter)
        order_by = [relevance.desc(), Supplier.name, Supplier.id]

    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    paged_query = query.order_by(*order_by)
    if paginated:
        paged_query = paged_query.offset(skip).limit(limit)
    result = await db.execute(paged_query)
    suppliers = result.scalars().all()
    items = [SupplierResponse.model_validate(s) for s in suppliers]
    return paginated_or_list(items, total, skip, limit, paginated)


@router.post("", response_model=SupplierAdminResponse, status_code=status.HTTP_201_CREATED)
async def create_supplier(
    data: SupplierCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin()),
):
    tenant_id = _admin_tenant_id(current_user)

    normalized_name = normalize_name(data.name)
    existing = (await db.execute(select(Supplier).where(
        Supplier.tenant_id == tenant_id,
        Supplier.normalized_name == normalized_name,
        Supplier.deleted_at.is_(None),
    ))).scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=409, detail="Supplier already exists")
    supplier = Supplier(
        tenant_id=tenant_id,
        normalized_name=normalized_name,
        **data.model_dump(exclude_unset=True),
    )
    db.add(supplier)
    await db.commit()
    await db.refresh(supplier)
    return SupplierAdminResponse.model_validate(supplier)


@router.put("/{supplier_id}", response_model=SupplierAdminResponse)
async def update_supplier(
    supplier_id: str,
    data: SupplierUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin()),
):
    tenant_id = _admin_tenant_id(current_user)
    query = select(Supplier).where(
        Supplier.id == supplier_id,
        Supplier.tenant_id == tenant_id,
        Supplier.deleted_at.is_(None),
    )

    result = await db.execute(query)
    supplier = result.scalar_one_or_none()
    if not supplier:
        raise _not_found()

    updates = data.model_dump(exclude_unset=True)
    if "name" in updates:
        normalized_name = normalize_name(updates["name"])
        existing = (await db.execute(select(Supplier).where(
            Supplier.tenant_id == tenant_id,
            Supplier.normalized_name == normalized_name,
            Supplier.id != supplier.id,
            Supplier.deleted_at.is_(None),
        ))).scalar_one_or_none()
        if existing:
            raise HTTPException(status_code=409, detail="Supplier already exists")
        supplier.normalized_name = normalized_name
    for field, value in updates.items():
        setattr(supplier, field, value)

    await db.commit()
    await db.refresh(supplier)
    return SupplierAdminResponse.model_validate(supplier)


@router.delete("/{supplier_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_supplier(
    supplier_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin()),
):
    tenant_id = _admin_tenant_id(current_user)
    query = select(Supplier).where(
        Supplier.id == supplier_id,
        Supplier.tenant_id == tenant_id,
        Supplier.deleted_at.is_(None),
    )

    result = await db.execute(query)
    supplier = result.scalar_one_or_none()
    if not supplier:
        raise _not_found()

    supplier.deleted_at = supplier.deleted_at or supplier.updated_at
    await db.commit()
    return None
