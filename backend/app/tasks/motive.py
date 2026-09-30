"""Default-off bounded reconciliation; no browser or provider credentials in jobs."""

from uuid import UUID

from sqlalchemy import or_, select

from app.core.config import settings
from app.db.models.customer import Customer
from app.db.models.motive_oauth import MotiveConnection
from app.db.models.tenant import Tenant
from app.db.session import AsyncSessionLocal
from app.services import motive_oauth as service
from app.tasks import celery_app
from app.tasks.async_runtime import run_async


def due_connections(approved):
    return (
        select(MotiveConnection.id)
        .join(Tenant, Tenant.id == MotiveConnection.tenant_id)
        .join(
            Customer,
            (Customer.id == MotiveConnection.fleet_customer_id)
            & (Customer.tenant_id == MotiveConnection.tenant_id),
        )
        .where(
            MotiveConnection.tenant_id.in_(approved),
            Tenant.is_active.is_(True),
            Tenant.deleted_at.is_(None),
            Customer.deleted_at.is_(None),
            or_(Customer.fleet_enabled.is_(True), Customer.is_internal_fleet.is_(True)),
            MotiveConnection.status.in_(["connected", "provider_error"]),
            MotiveConnection.deleted_at.is_(None),
            or_(
                MotiveConnection.next_sync_at.is_(None),
                MotiveConnection.next_sync_at <= service.now(),
            ),
        )
        .order_by(MotiveConnection.next_sync_at)
        .limit(20)
    )


async def reconcile():
    async with AsyncSessionLocal() as db:
        await service.purge(db)
        if not settings.MOTIVE_ENABLED:
            return {"processed": 0}
        approved = []
        for value in settings.MOTIVE_APPROVED_TENANT_IDS.split(","):
            try:
                approved.append(UUID(value.strip()))
            except ValueError:
                continue
        ids = (await db.execute(due_connections(approved))).scalars().all()
        await db.rollback()
        count = 0
        for connection_id in ids:
            row = (
                await db.execute(
                    select(MotiveConnection)
                    .where(MotiveConnection.id == connection_id)
                    .with_for_update(skip_locked=True)
                    .execution_options(populate_existing=True)
                )
            ).scalar_one_or_none()
            if row and service.configured(row.tenant_id):
                try:
                    await service.sync(db, row)
                    count += 1
                except Exception:  # noqa: BLE001 - rollback isolation for one company
                    # Never record exception text: provider/SQL exceptions can include credentials.
                    await db.rollback()
            else:
                await db.rollback()
        return {"processed": count}


@celery_app.task(name="reconcile_motive", acks_late=True)
def reconcile_motive():
    return run_async(reconcile())
