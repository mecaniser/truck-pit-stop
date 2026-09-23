"""Resolve road incidents when the repair order answering for them is completed.

An incident linked to a repair order — by `create-repair` or by attaching it to
an existing order — used to stay open after that order's work was done, so the
truck page kept showing a problem the shop had already fixed. Completion is the
point the work is done, so it is where the incident is resolved.

Only COMPLETED triggers this. Every later state (INVOICED, PAID) is reached
through COMPLETED, while CANCELLED and DECLINED mean the work did not happen,
so an incident linked to such an order is left open for someone to decide.
"""
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.driver_accountability import FleetIncidentEvent
from app.db.models.fleet import FleetIncident, IncidentStatus
from app.db.models.repair_order import RepairOrder

# Resolved and voided incidents are settled; completing an order must not
# rewrite either.
_UNSETTLED = (IncidentStatus.OPEN, IncidentStatus.IN_PROGRESS)


async def resolve_incidents_for_completed_order(
    db: AsyncSession,
    order: RepairOrder,
    *,
    actor_user_id: Optional[UUID],
) -> int:
    """Resolve every unsettled incident linked to `order`. Returns the count.

    Adds to the caller's session without committing, so the incident change
    lands in the same transaction as the order's completion or not at all.
    """
    incidents = (
        await db.execute(
            select(FleetIncident).where(
                FleetIncident.tenant_id == order.tenant_id,
                FleetIncident.repair_order_id == order.id,
                FleetIncident.status.in_(_UNSETTLED),
                FleetIncident.deleted_at.is_(None),
            )
        )
    ).scalars().all()

    now = datetime.now(timezone.utc)
    for incident in incidents:
        incident.status = IncidentStatus.RESOLVED
        incident.resolved_at = now
        # An outcome a person already wrote outranks the generated one.
        if not (incident.resolution_notes or "").strip():
            incident.resolution_notes = (
                f"Resolved when repair order {order.order_number} was completed."
            )
        db.add(
            FleetIncidentEvent(
                id=uuid4(),
                tenant_id=incident.tenant_id,
                incident_id=incident.id,
                actor_user_id=actor_user_id,
                event_type="resolved_by_repair_order",
                reason=None,
                data_json={
                    "repair_order_id": str(order.id),
                    "order_number": order.order_number,
                },
                occurred_at=now,
            )
        )
    return len(incidents)
