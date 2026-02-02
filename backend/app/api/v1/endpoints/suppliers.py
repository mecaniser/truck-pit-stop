from typing import List, Optional
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel

from app.core.dependencies import get_db, get_current_active_user
from app.db.models.user import User, UserRole
from app.db.models.supplier import Supplier

router = APIRouter()


class SupplierBase(BaseModel):
    name: str
    address: Optional[str] = None
    phone: Optional[str] = None
    contact_name: Optional[str] = None
    notes: Optional[str] = None


class SupplierCreate(SupplierBase):
    pass


class SupplierUpdate(BaseModel):
    name: Optional[str] = None
    address: Optional[str] = None
    phone: Optional[str] = None
    contact_name: Optional[str] = None
    notes: Optional[str] = None


class SupplierResponse(SupplierBase):
    id: UUID
    tenant_id: UUID

    class Config:
        from_attributes = True


def require_admin():
    async def role_checker(current_user: User = Depends(get_current_active_user)):
        if current_user.role not in [UserRole.GARAGE_OWNER, UserRole.GARAGE_ADMIN]:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Admin access required",
            )
        return current_user
    return role_checker


@router.get("", response_model=List[SupplierResponse])
async def list_suppliers(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    query = select(Supplier).where(Supplier.deleted_at.is_(None))
    if current_user.tenant_id:
        query = query.where(Supplier.tenant_id == current_user.tenant_id)

    result = await db.execute(query.order_by(Supplier.name))
    suppliers = result.scalars().all()
    return [SupplierResponse.model_validate(s) for s in suppliers]


@router.post("", response_model=SupplierResponse, status_code=status.HTTP_201_CREATED)
async def create_supplier(
    data: SupplierCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin()),
):
    if not current_user.tenant_id:
        raise HTTPException(status_code=400, detail="User must be associated with a tenant")

    supplier = Supplier(
        tenant_id=current_user.tenant_id,
        **data.model_dump(exclude_unset=True),
    )
    db.add(supplier)
    await db.commit()
    await db.refresh(supplier)
    return SupplierResponse.model_validate(supplier)


@router.put("/{supplier_id}", response_model=SupplierResponse)
async def update_supplier(
    supplier_id: str,
    data: SupplierUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin()),
):
    query = select(Supplier).where(
        Supplier.id == supplier_id,
        Supplier.deleted_at.is_(None),
    )
    if current_user.tenant_id:
        query = query.where(Supplier.tenant_id == current_user.tenant_id)

    result = await db.execute(query)
    supplier = result.scalar_one_or_none()
    if not supplier:
        raise HTTPException(status_code=404, detail="Supplier not found")

    updates = data.model_dump(exclude_unset=True)
    for field, value in updates.items():
        setattr(supplier, field, value)

    await db.commit()
    await db.refresh(supplier)
    return SupplierResponse.model_validate(supplier)


@router.delete("/{supplier_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_supplier(
    supplier_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin()),
):
    query = select(Supplier).where(
        Supplier.id == supplier_id,
        Supplier.deleted_at.is_(None),
    )
    if current_user.tenant_id:
        query = query.where(Supplier.tenant_id == current_user.tenant_id)

    result = await db.execute(query)
    supplier = result.scalar_one_or_none()
    if not supplier:
        raise HTTPException(status_code=404, detail="Supplier not found")

    supplier.deleted_at = supplier.deleted_at or supplier.updated_at
    await db.commit()
    return None
