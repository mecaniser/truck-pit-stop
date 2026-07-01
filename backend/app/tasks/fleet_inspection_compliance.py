"""
Fleet weekly inspection compliance task.

Every truck in the garage's internal fleet must have a completed weekly
inspection. When the 7-day cadence lapses with no inspection performed, this
task records a MISSED inspection (a failed-compliance marker in the truck's
history) and notifies the fleet managers / garage owners.

Schedule: weekly.
"""
import asyncio
from datetime import date, datetime, timedelta, timezone
from uuid import uuid4

from sqlalchemy import select, and_
from sqlalchemy.orm import selectinload

from app.tasks import celery_app
from app.db.session import AsyncSessionLocal
from app.db.models.customer import Customer
from app.db.models.vehicle import Vehicle
from app.db.models.tenant import Tenant
from app.db.models.user import User, UserRole
from app.db.models.fleet import (
    FleetInspection,
    InspectionStatus,
    InspectionResult,
    INSPECTION_INTERVAL_DAYS,
)
from app.services.email_service import send_email

# Fleet managers own the fleet; owners/admins can act on their behalf.
NOTIFY_ROLES = (UserRole.FLEET_MANAGER, UserRole.GARAGE_OWNER, UserRole.GARAGE_ADMIN)


def _unit_label(v: Vehicle) -> str:
    return v.unit_number or f"{v.make} {v.model}".strip() or "Unit"


async def record_missed_inspections(db) -> dict:
    """Scan internal-fleet trucks and record a MISSED inspection for any that
    lapsed the 7-day window. Returns {tenant_id: [vehicles]} for notification.
    Idempotent within a weekly window. Commits its own writes.
    """
    today = date.today()
    now = datetime.now(timezone.utc)
    window_start = now - timedelta(days=INSPECTION_INTERVAL_DAYS)

    # All internal-fleet vehicles across tenants (soft-deleted excluded).
    vehicles = (await db.execute(
        select(Vehicle)
        .join(Customer, Vehicle.customer_id == Customer.id)
        .where(and_(
            Customer.is_internal_fleet.is_(True),
            Vehicle.deleted_at.is_(None),
        ))
    )).scalars().all()

    missed_by_tenant: dict = {}
    for v in vehicles:
        # Out-of-service trucks aren't in rotation — don't penalize them.
        if v.status_override == "out_of_service":
            continue

        last_completed = (await db.execute(
            select(FleetInspection)
            .where(and_(
                FleetInspection.vehicle_id == v.id,
                FleetInspection.status == InspectionStatus.COMPLETED,
            ))
            .order_by(FleetInspection.performed_at.desc())
            .limit(1)
        )).scalar_one_or_none()

        performed_at = last_completed.performed_at if last_completed else None
        if performed_at is not None and performed_at.tzinfo is None:
            performed_at = performed_at.replace(tzinfo=timezone.utc)
        if performed_at is not None and performed_at >= window_start:
            continue  # inspected within the window

        # Idempotency: don't record a second miss for the same weekly window.
        already_missed = (await db.execute(
            select(FleetInspection.id).where(and_(
                FleetInspection.vehicle_id == v.id,
                FleetInspection.status == InspectionStatus.MISSED,
                FleetInspection.scheduled_for > today - timedelta(days=INSPECTION_INTERVAL_DAYS),
            )).limit(1)
        )).scalar_one_or_none()
        if already_missed:
            continue

        db.add(FleetInspection(
            id=uuid4(),
            tenant_id=v.tenant_id,
            vehicle_id=v.id,
            status=InspectionStatus.MISSED,
            result=InspectionResult.FAIL,
            scheduled_for=today,
            notes="No weekly inspection was performed within the required 7-day window.",
        ))
        missed_by_tenant.setdefault(v.tenant_id, []).append(v)

    await db.commit()
    return missed_by_tenant


async def _process_fleet_inspection_compliance():
    async with AsyncSessionLocal() as db:
        missed_by_tenant = await record_missed_inspections(db)
        recorded = sum(len(v) for v in missed_by_tenant.values())

        # Notify the people who own the fleet, one email per tenant.
        for tenant_id, trucks in missed_by_tenant.items():
            tenant = (await db.execute(
                select(Tenant).where(Tenant.id == tenant_id)
            )).scalar_one_or_none()
            recipients = (await db.execute(
                select(User).where(and_(
                    User.tenant_id == tenant_id,
                    User.role.in_(NOTIFY_ROLES),
                    User.is_active.is_(True),
                ))
            )).scalars().all()

            garage = tenant.name if tenant else "Your fleet"
            rows = "".join(f"<li>{_unit_label(t)}</li>" for t in trucks)
            subject = f"Missed weekly inspection — {len(trucks)} truck(s)"
            html = f"""
            <html><body style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px;">
              <h2 style="color: #dc2626;">Weekly inspection missed</h2>
              <p>The following {len(trucks)} truck(s) in <strong>{garage}</strong> went past the
                 7-day inspection window with no inspection performed. Each is marked
                 as a failed weekly inspection in its record.</p>
              <ul>{rows}</ul>
              <p>Complete an inspection to bring them back into compliance.</p>
            </body></html>
            """
            for u in recipients:
                if not u.email:
                    continue
                try:
                    await send_email(
                        db, str(tenant_id), u.email, subject, html,
                        template_name="fleet_inspection_missed",
                    )
                except Exception:
                    pass

        return recorded


@celery_app.task(name="process_fleet_inspection_compliance")
def process_fleet_inspection_compliance():
    """Celery task wrapper — runs the async compliance logic."""
    loop = asyncio.get_event_loop()
    if loop.is_closed():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    try:
        count = loop.run_until_complete(_process_fleet_inspection_compliance())
        return {"status": "success", "missed_recorded": count}
    except Exception as e:
        return {"status": "error", "message": str(e)}
