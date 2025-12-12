from typing import List
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from app.core.dependencies import get_db, get_current_active_user
from app.db.models.user import User, UserRole
from app.db.models.customer import Customer
from app.schemas.customer import CustomerCreate, CustomerUpdate, CustomerResponse

router = APIRouter()


def require_role(*allowed_roles: UserRole):
    async def role_checker(current_user: User = Depends(get_current_active_user)):
        if current_user.role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions",
            )
        return current_user
    return role_checker


@router.post("", response_model=CustomerResponse, status_code=status.HTTP_201_CREATED)
async def create_customer(
    customer_data: CustomerCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(
        UserRole.SUPER_ADMIN,
        UserRole.GARAGE_ADMIN,
        UserRole.RECEPTIONIST,
    )),
):
    if not current_user.tenant_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User must be associated with a tenant",
        )
    
    # Check if customer email already exists for this tenant
    result = await db.execute(
        select(Customer).where(
            and_(
                Customer.email == customer_data.email,
                Customer.tenant_id == current_user.tenant_id,
            )
        )
    )
    existing = result.scalar_one_or_none()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Customer with this email already exists",
        )
    
    customer = Customer(
        tenant_id=current_user.tenant_id,
        **customer_data.model_dump(),
    )
    
    db.add(customer)
    await db.commit()
    await db.refresh(customer)
    
    return CustomerResponse.model_validate(customer)


@router.get("", response_model=List[CustomerResponse])
async def list_customers(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    if current_user.role == UserRole.CUSTOMER:
        # Customers can only see their own profile
        if not current_user.customer_id:
            return []
        result = await db.execute(
            select(Customer).where(Customer.id == current_user.customer_id)
        )
        customer = result.scalar_one_or_none()
        return [CustomerResponse.model_validate(customer)] if customer else []
    
    # Staff can see all customers in their tenant
    if not current_user.tenant_id:
        return []
    
    result = await db.execute(
        select(Customer)
        .where(Customer.tenant_id == current_user.tenant_id)
        .offset(skip)
        .limit(limit)
    )
    customers = result.scalars().all()
    
    return [CustomerResponse.model_validate(c) for c in customers]


@router.get("/{customer_id}", response_model=CustomerResponse)
async def get_customer(
    customer_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    result = await db.execute(select(Customer).where(Customer.id == customer_id))
    customer = result.scalar_one_or_none()
    
    if not customer:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Customer not found",
        )
    
    # Check access: customers can only see their own profile
    if current_user.role == UserRole.CUSTOMER:
        if current_user.customer_id != customer_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied",
            )
    # Staff can only see customers in their tenant
    elif current_user.tenant_id != customer.tenant_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied",
        )
    
    return CustomerResponse.model_validate(customer)


@router.put("/{customer_id}", response_model=CustomerResponse)
async def update_customer(
    customer_id: UUID,
    customer_data: CustomerUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    result = await db.execute(select(Customer).where(Customer.id == customer_id))
    customer = result.scalar_one_or_none()
    
    if not customer:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Customer not found",
        )
    
    # Check access
    if current_user.role == UserRole.CUSTOMER:
        if current_user.customer_id != customer_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied",
            )
    elif current_user.tenant_id != customer.tenant_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied",
        )
    
    # Update fields
    update_data = customer_data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(customer, field, value)
    
    await db.commit()
    await db.refresh(customer)
    
    return CustomerResponse.model_validate(customer)


