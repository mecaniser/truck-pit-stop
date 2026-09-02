"""Canonical repair-order status sets.

These sets decide whether a repair order still accepts work edits. They were
previously defined twice — once in `app.services.price_build_service` and once in
`app.api.v1.endpoints.repair_orders` — and the two copies had drifted: the
service froze internal orders at PAID while the endpoints module did not, despite
a comment claiming the two mirrored each other. An order could therefore be
editable through one code path and frozen through another.

Both modules now import from here. Define a status set once, in this module.
"""

from __future__ import annotations

from app.db.models.repair_order import RepairOrderStatus

# Customer work stays editable across the whole active repair lifecycle.
# Finalization/invoicing is the financial lock boundary, not quote approval.
EDITABLE_RO_STATUSES: frozenset[RepairOrderStatus] = frozenset({
    RepairOrderStatus.DRAFT,
    RepairOrderStatus.QUOTED,
    RepairOrderStatus.DECLINED,
    RepairOrderStatus.APPROVED,
    RepairOrderStatus.ASSIGNED,
    RepairOrderStatus.ACKNOWLEDGED,
    RepairOrderStatus.IN_PROGRESS,
    RepairOrderStatus.PENDING_REVIEW,
})

# Internal fleet orders log labor/parts as the work happens (e.g. an in-progress
# PM), so they stay editable further into the flow than customer work and freeze
# only at these terminal states. PAID is frozen because a paid order is a
# financial record — see PRODUCT.md, "Money is a record, not a draft."
INTERNAL_FROZEN_RO_STATUSES: frozenset[RepairOrderStatus] = frozenset({
    RepairOrderStatus.COMPLETED,
    RepairOrderStatus.INVOICED,
    RepairOrderStatus.PAID,
    RepairOrderStatus.CANCELLED,
})

# Money has been published to the customer; totals must not be recomputed.
FINALIZED_STATUSES: frozenset[RepairOrderStatus] = frozenset({
    RepairOrderStatus.INVOICED,
    RepairOrderStatus.PAID,
})
