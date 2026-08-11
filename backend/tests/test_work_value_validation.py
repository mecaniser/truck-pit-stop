from __future__ import annotations

from decimal import Decimal
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.api.v1.endpoints.services import ServicePartCreate, ServicePartUpdate
from app.schemas.fleet import WorkOrderLaborLineCreate, WorkOrderPartLineCreate
from app.schemas.repair_order import (
    LaborCreate,
    LaborUpdate,
    PartsUsageCreate,
    PartsUsageUpdate,
    PriceBuildLineUpdateRequest,
    PriceBuildRepairOpsApplyRequest,
)
from app.services.price_build_service import (
    PriceBuildInputError,
    validate_mechanic_labor_hours,
)


INVALID_VALUES = (
    "NaN",
    "Infinity",
    "-Infinity",
    Decimal("0"),
    Decimal("-0.01"),
    Decimal("1.001"),
    Decimal("1000.00"),
    Decimal("9999.99"),
)


@pytest.mark.parametrize("value", INVALID_VALUES)
def test_every_direct_part_quantity_schema_rejects_invalid_exact_values(value):
    inventory_id = uuid4()
    constructors = (
        lambda: PartsUsageCreate(inventory_id=inventory_id, quantity=value),
        lambda: PartsUsageUpdate(quantity=value),
        lambda: ServicePartCreate(inventory_id=inventory_id, quantity=value),
        lambda: ServicePartUpdate(quantity=value),
        lambda: WorkOrderPartLineCreate(inventory_id=inventory_id, quantity=value),
    )

    for construct in constructors:
        with pytest.raises(ValidationError):
            construct()


@pytest.mark.parametrize("value", INVALID_VALUES)
def test_every_direct_labor_hours_schema_rejects_invalid_exact_values(value):
    constructors = (
        lambda: LaborCreate(
            description="Labor",
            hours=value,
            hourly_rate=Decimal("100.00"),
        ),
        lambda: LaborUpdate(hours=value),
        lambda: PriceBuildLineUpdateRequest(hours=value),
        lambda: PriceBuildRepairOpsApplyRequest(
            operation_id="custom:invalid",
            estimated_hours=value,
        ),
        lambda: WorkOrderLaborLineCreate(description="Labor", hours=value),
    )

    for construct in constructors:
        with pytest.raises(ValidationError):
            construct()


@pytest.mark.parametrize("value", [Decimal("0.01"), Decimal("1.23"), Decimal("999.99")])
def test_boundary_values_are_preserved_without_rounding(value):
    inventory_id = uuid4()

    assert PartsUsageCreate(inventory_id=inventory_id, quantity=value).quantity == value
    assert LaborCreate(
        description="Labor", hours=value, hourly_rate=Decimal("100.00")
    ).hours == value
    assert validate_mechanic_labor_hours(value) == value


def test_runtime_labor_validation_rejects_precision_instead_of_rounding():
    with pytest.raises(PriceBuildInputError):
        validate_mechanic_labor_hours(Decimal("0.015"))
