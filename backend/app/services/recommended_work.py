"""Read-only, tenant-scoped recommendation continuity across truck visits."""
from datetime import datetime, timezone
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import and_, case, exists, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.customer import Customer
from app.db.models.recommended_service import RecommendedService, RecommendedServicePriority
from app.db.models.repair_order import RepairOrder, RepairOrderStatus
from app.db.models.vehicle import Vehicle
from app.db.models.vehicle_relationship import VehicleCustomerRelationship
from app.schemas.recommended_work import (
    RecommendedWorkItem,
    RecommendedWorkPage,
    RecommendedWorkSourceOrder,
    RecommendedWorkVehicle,
)

CONTEXT_NOT_FOUND = "Recommended work context not found"


def _customer_link(tenant_id: UUID, customer_id: UUID, now: datetime):
    # EXISTS keeps duplicated owner/operator links from multiplying rows/counts.
    return or_(
        Vehicle.customer_id == customer_id,
        exists(select(VehicleCustomerRelationship.id).where(
            VehicleCustomerRelationship.tenant_id == tenant_id,
            VehicleCustomerRelationship.vehicle_id == Vehicle.id,
            VehicleCustomerRelationship.customer_id == customer_id,
            VehicleCustomerRelationship.deleted_at.is_(None),
            VehicleCustomerRelationship.relationship_type.in_(("owner", "operator")),
            VehicleCustomerRelationship.effective_from <= now,
            VehicleCustomerRelationship.effective_to.is_(None),
        )),
    )


async def list_recommended_work(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    vehicle_id: UUID | None,
    customer_id: UUID | None,
    context_order_id: UUID | None,
    skip: int,
    limit: int,
) -> RecommendedWorkPage:
    if context_order_id is not None and vehicle_id is None:
        raise HTTPException(status_code=422, detail="context_order_id requires vehicle_id")

    now = datetime.now(timezone.utc)
    if customer_id is not None:
        customer = await db.scalar(select(Customer.id).where(
            Customer.id == customer_id,
            Customer.tenant_id == tenant_id,
            Customer.deleted_at.is_(None),
        ))
        if customer is None:
            raise HTTPException(status_code=404, detail=CONTEXT_NOT_FOUND)
    if vehicle_id is not None:
        vehicle_query = select(Vehicle.id).where(
            Vehicle.id == vehicle_id,
            Vehicle.tenant_id == tenant_id,
            Vehicle.deleted_at.is_(None),
        )
        if customer_id is not None:
            vehicle_query = vehicle_query.where(_customer_link(tenant_id, customer_id, now))
        if await db.scalar(vehicle_query) is None:
            raise HTTPException(status_code=404, detail=CONTEXT_NOT_FOUND)
    if context_order_id is not None:
        context = await db.scalar(select(RepairOrder.id).where(
            RepairOrder.id == context_order_id,
            RepairOrder.tenant_id == tenant_id,
            RepairOrder.vehicle_id == vehicle_id,
            RepairOrder.deleted_at.is_(None),
            RepairOrder.status != RepairOrderStatus.CANCELLED,
        ))
        if context is None:
            raise HTTPException(status_code=404, detail=CONTEXT_NOT_FOUND)

    # Project only the fields this endpoint may disclose, never payer or pricing.
    query = select(
        RecommendedService.id,
        RecommendedService.description,
        RecommendedService.priority,
        RecommendedService.created_at,
        Vehicle.id.label("vehicle_id"),
        Vehicle.unit_number,
        Vehicle.year,
        Vehicle.make,
        Vehicle.model,
        RepairOrder.id.label("source_order_id"),
        RepairOrder.order_number,
        RepairOrder.status,
        RepairOrder.created_at.label("source_created_at"),
    ).select_from(RecommendedService).join(RepairOrder, and_(
        RepairOrder.id == RecommendedService.repair_order_id,
        RepairOrder.tenant_id == RecommendedService.tenant_id,
    )).join(Vehicle, and_(
        Vehicle.id == RepairOrder.vehicle_id,
        Vehicle.tenant_id == RepairOrder.tenant_id,
    )).join(Customer, and_(
        Customer.id == RepairOrder.customer_id,
        Customer.tenant_id == RepairOrder.tenant_id,
    )).where(
        RecommendedService.tenant_id == tenant_id,
        RecommendedService.deleted_at.is_(None),
        RecommendedService.is_resolved.is_(False),
        RecommendedService.resolved_by_repair_order_id.is_(None),
        RepairOrder.deleted_at.is_(None),
        RepairOrder.status != RepairOrderStatus.CANCELLED,
        Vehicle.deleted_at.is_(None),
        Customer.deleted_at.is_(None),
    )
    if vehicle_id is not None:
        query = query.where(Vehicle.id == vehicle_id)
    if customer_id is not None:
        query = query.where(_customer_link(tenant_id, customer_id, now))
    if context_order_id is not None:
        query = query.where(RepairOrder.id != context_order_id)

    # Same complete predicate set for total and page; joins are all to unique IDs.
    total = await db.scalar(select(func.count()).select_from(query.subquery()))
    priority_order = case(
        (RecommendedService.priority == RecommendedServicePriority.URGENT, 0),
        (RecommendedService.priority == RecommendedServicePriority.SOON, 1),
        else_=2,
    )
    rows = (await db.execute(query.order_by(
        priority_order, RecommendedService.created_at.asc(), RecommendedService.id.asc(),
    ).offset(skip).limit(limit))).mappings().all()
    return RecommendedWorkPage(
        items=[RecommendedWorkItem(
            id=row["id"], description=row["description"], priority=row["priority"],
            created_at=row["created_at"],
            vehicle=RecommendedWorkVehicle(
                id=row["vehicle_id"], unit_number=row["unit_number"], year=row["year"],
                make=row["make"], model=row["model"],
            ),
            source_order=RecommendedWorkSourceOrder(
                id=row["source_order_id"], order_number=row["order_number"],
                status=row["status"], created_at=row["source_created_at"],
            ),
        ) for row in rows],
        total=total or 0, skip=skip, limit=limit,
    )
