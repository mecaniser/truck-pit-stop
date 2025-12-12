from typing import List, Optional
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel
from decimal import Decimal

from app.core.dependencies import get_db, get_current_active_user
from app.db.models.user import User
from app.db.models.inventory import Inventory

router = APIRouter()


class InventoryResponse(BaseModel):
    id: UUID
    tenant_id: UUID
    sku: str
    name: str
    description: Optional[str]
    category: Optional[str]
    stock_quantity: int
    reorder_level: int
    cost: Decimal
    selling_price: Decimal
    supplier_name: Optional[str]
    supplier_contact: Optional[str]
    created_at: str
    updated_at: str

    class Config:
        from_attributes = True


class InventoryCreate(BaseModel):
    sku: str
    name: str
    description: Optional[str] = None
    category: Optional[str] = None
    stock_quantity: int = 0
    reorder_level: int = 0
    cost: Decimal
    selling_price: Decimal
    supplier_name: Optional[str] = None
    supplier_contact: Optional[str] = None


@router.get("", response_model=List[InventoryResponse])
async def list_inventory(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    category: Optional[str] = None,
    low_stock: Optional[bool] = None,
):
    query = select(Inventory).where(Inventory.deleted_at.is_(None))
    
    if current_user.tenant_id:
        query = query.where(Inventory.tenant_id == current_user.tenant_id)
    
    if category:
        query = query.where(Inventory.category == category)
    
    result = await db.execute(query.order_by(Inventory.name))
    items = result.scalars().all()
    
    # Filter low stock items if requested
    if low_stock:
        items = [item for item in items if item.stock_quantity <= item.reorder_level]
    
    return [
        InventoryResponse(
            id=item.id,
            tenant_id=item.tenant_id,
            sku=item.sku,
            name=item.name,
            description=item.description,
            category=item.category,
            stock_quantity=item.stock_quantity,
            reorder_level=item.reorder_level,
            cost=item.cost,
            selling_price=item.selling_price,
            supplier_name=item.supplier_name,
            supplier_contact=item.supplier_contact,
            created_at=item.created_at.isoformat(),
            updated_at=item.updated_at.isoformat(),
        )
        for item in items
    ]


@router.get("/{item_id}", response_model=InventoryResponse)
async def get_inventory_item(
    item_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    query = select(Inventory).where(
        Inventory.id == item_id,
        Inventory.deleted_at.is_(None)
    )
    
    if current_user.tenant_id:
        query = query.where(Inventory.tenant_id == current_user.tenant_id)
    
    result = await db.execute(query)
    item = result.scalar_one_or_none()
    
    if not item:
        raise HTTPException(status_code=404, detail="Inventory item not found")
    
    return InventoryResponse(
        id=item.id,
        tenant_id=item.tenant_id,
        sku=item.sku,
        name=item.name,
        description=item.description,
        category=item.category,
        stock_quantity=item.stock_quantity,
        reorder_level=item.reorder_level,
        cost=item.cost,
        selling_price=item.selling_price,
        supplier_name=item.supplier_name,
        supplier_contact=item.supplier_contact,
        created_at=item.created_at.isoformat(),
        updated_at=item.updated_at.isoformat(),
    )

