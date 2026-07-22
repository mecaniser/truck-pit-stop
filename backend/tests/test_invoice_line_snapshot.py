from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.api.v1.endpoints.invoices import _line_items_snapshot, _load_line_items


def test_invoice_line_snapshot_is_json_safe():
    snapshot = _line_items_snapshot(
        [{"description": "Diagnosis", "hours": Decimal("1.50"), "total_cost": Decimal("225.00")}],
        [{"name": "Sensor", "quantity": Decimal("1.00"), "total_price": Decimal("89.99")}],
    )

    assert snapshot == {
        "version": 1,
        "labor": [{"description": "Diagnosis", "hours": "1.50", "total_cost": "225.00"}],
        "parts": [{"name": "Sensor", "quantity": "1.00", "total_price": "89.99"}],
    }


@pytest.mark.asyncio
async def test_invoice_line_loader_prefers_finalized_snapshot():
    snapshot = {
        "version": 1,
        "labor": [{"description": "Final labor", "total_cost": "100.00"}],
        "parts": [{"name": "Final part", "total_price": "50.00"}],
    }
    invoice = SimpleNamespace(line_items_snapshot=snapshot)

    labor, parts = await _load_line_items(None, "unused-order-id", invoice)

    assert labor == snapshot["labor"]
    assert parts == snapshot["parts"]
