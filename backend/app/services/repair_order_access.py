from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import and_, exists, or_, select

from app.db.models.repair_order import RepairOrder
from app.db.models.user import User, UserRole
from app.db.models.user_customer_link import UserCustomerLink


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

    customer_scopes = [
        exists(
            select(UserCustomerLink.id).where(
                UserCustomerLink.user_id == current_user.id,
                UserCustomerLink.customer_id == RepairOrder.customer_id,
                UserCustomerLink.tenant_id == RepairOrder.tenant_id,
                UserCustomerLink.deleted_at.is_(None),
            )
        )
    ]
    if current_user.tenant_id is not None and current_user.customer_id is not None:
        customer_scopes.append(
            and_(
                RepairOrder.tenant_id == current_user.tenant_id,
                RepairOrder.customer_id == current_user.customer_id,
            )
        )
    return statement.where(or_(*customer_scopes))
