"""The repair-order status sets are defined once and shared.

These sets were previously duplicated between the price-build service and the
repair-orders endpoints, and the copies drifted: the service froze internal
orders at PAID while the endpoints module did not. An internal order could
therefore be editable through one code path and frozen through another. These
tests lock the sets to one definition so the drift cannot come back.
"""

from app.api.v1.endpoints import repair_orders as ro_endpoints
from app.db.models.repair_order import RepairOrderStatus
from app.services import price_build_service as pbs
from app.services.repair_order_status_sets import (
    EDITABLE_RO_STATUSES,
    FINALIZED_STATUSES,
    INTERNAL_FROZEN_RO_STATUSES,
)


def test_both_modules_share_one_definition():
    assert ro_endpoints.EDITABLE_RO_STATUSES is EDITABLE_RO_STATUSES
    assert ro_endpoints.INTERNAL_FROZEN_RO_STATUSES is INTERNAL_FROZEN_RO_STATUSES
    assert pbs.EDITABLE_RO_STATUSES is EDITABLE_RO_STATUSES
    assert pbs.INTERNAL_FROZEN_STATUSES is INTERNAL_FROZEN_RO_STATUSES
    assert pbs.FINALIZED_STATUSES is FINALIZED_STATUSES


def test_paid_internal_orders_are_frozen():
    """A paid order is a financial record — PRODUCT.md, "Money is a record"."""
    assert RepairOrderStatus.PAID in INTERNAL_FROZEN_RO_STATUSES
    assert RepairOrderStatus.INVOICED in INTERNAL_FROZEN_RO_STATUSES


def test_editable_and_frozen_do_not_overlap():
    assert not (EDITABLE_RO_STATUSES & INTERNAL_FROZEN_RO_STATUSES)


def test_finalized_statuses_are_frozen_for_internal_work_too():
    assert FINALIZED_STATUSES <= INTERNAL_FROZEN_RO_STATUSES


def test_every_status_is_classified():
    """No status may be silently absent from both sets."""
    unclassified = set(RepairOrderStatus) - EDITABLE_RO_STATUSES - INTERNAL_FROZEN_RO_STATUSES
    assert unclassified == set()
