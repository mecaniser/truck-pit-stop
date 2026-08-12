from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import and_, select

from app.db.models.repair_order import RepairOrder
from app.db.models.user import User, UserRole


def selected_customer_repair_order_scope(current_user: User):
    """Require the exact customer context selected for this request.

    A provider-neutral customer may have links to several shops. Authentication
    projects exactly one selected ``tenant_id``/``customer_id`` pair onto the
    immutable request principal; no other active link may widen that request.
    Direct customer users carry the same exact pair on their persisted identity.
    """
    return and_(
        RepairOrder.tenant_id == current_user.tenant_id,
        RepairOrder.customer_id == current_user.customer_id,
    )


def tenant_repair_order_statement(
    order_id: UUID,
    current_user: User,
    *additional_filters: Any,
):
    """Build a non-enumerating initial repair-order lookup for tenant routes."""
    statement = select(RepairOrder).where(
        RepairOrder.id == order_id,
        RepairOrder.deleted_at.is_(None),
        *additional_filters,
    )
    if current_user.role != UserRole.CUSTOMER:
        return statement.where(RepairOrder.tenant_id == current_user.tenant_id)

    return statement.where(selected_customer_repair_order_scope(current_user))
