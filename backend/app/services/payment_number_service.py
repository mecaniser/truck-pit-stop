from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.payment_number_counter import PaymentNumberCounter


def _payment_prefix(tenant_id: UUID) -> str:
    return f"PAY-{str(tenant_id).replace('-', '').upper()[:8]}-"


async def allocate_next_payment_number(db: AsyncSession, tenant_id: UUID) -> str:
    """
    Allocate the next tenant-scoped payment number in the caller's transaction.

    Uses SELECT ... FOR UPDATE on the tenant counter row. This assumes the
    database default isolation (READ COMMITTED in Postgres), where row locks
    serialize concurrent increments for the same tenant.
    """
    result = await db.execute(
        select(PaymentNumberCounter)
        .where(PaymentNumberCounter.tenant_id == tenant_id)
        .with_for_update()
    )
    counter = result.scalar_one_or_none()

    if not counter:
        # Handle first-write race with a savepoint so caller transaction survives.
        try:
            async with db.begin_nested():
                counter = PaymentNumberCounter(tenant_id=tenant_id, last_number=0)
                db.add(counter)
                await db.flush()
        except IntegrityError:
            pass

        result = await db.execute(
            select(PaymentNumberCounter)
            .where(PaymentNumberCounter.tenant_id == tenant_id)
            .with_for_update()
        )
        counter = result.scalar_one()

    counter.last_number += 1
    await db.flush()
    return f"{_payment_prefix(tenant_id)}{counter.last_number:06d}"
