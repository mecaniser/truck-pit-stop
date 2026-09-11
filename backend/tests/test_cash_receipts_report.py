from datetime import date, datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from sqlalchemy.dialects import postgresql

from app.api.v1.endpoints.reports import cash_receipts_for_range


def receipt(amount, company="Cash customer"):
    return (
        SimpleNamespace(id=uuid4(), payment_number="PAY-1", amount=Decimal(amount),
                        created_at=datetime(2026, 9, 11, tzinfo=timezone.utc)),
        SimpleNamespace(invoice_number="INV-1"),
        SimpleNamespace(company_name=company, first_name="Jane", last_name="Doe"),
    )


@pytest.mark.asyncio
async def test_cash_query_has_all_tenant_and_receipt_boundaries():
    tenant = uuid4()
    rng = SimpleNamespace(start=date(2026, 9, 1), end=date(2026, 9, 11))
    db = SimpleNamespace(execute=AsyncMock(return_value=SimpleNamespace(all=lambda: [])))
    total, rows = await cash_receipts_for_range(db, tenant, rng)
    query = str(db.execute.call_args.args[0].compile(
        dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}))
    for table in ("payments", "invoices", "repair_orders", "customers"):
        assert f"{table}.tenant_id = '{tenant}'" in query
    assert "payments.method = 'cash'" in query
    assert "payments.status = 'completed'" in query
    assert "invoices.is_internal IS false" in query
    assert "date(payments.created_at) >= '2026-09-01'" in query
    assert "date(payments.created_at) <= '2026-09-11'" in query
    assert "ORDER BY payments.created_at DESC, payments.id" in query
    assert total == "0.00"
    assert rows == []
    db.execute.assert_awaited_once()


@pytest.mark.asyncio
async def test_cash_sum_uses_receipt_amounts_and_fallback_customer_name():
    records = [receipt("0.10"), receipt("0.20", company=None)]
    db = SimpleNamespace(execute=AsyncMock(return_value=SimpleNamespace(all=lambda: records)))
    total, rows = await cash_receipts_for_range(db, uuid4(),
        SimpleNamespace(start=date(2026, 9, 1), end=date(2026, 9, 11)))
    assert total == "0.30"
    assert [row.amount for row in rows] == ["0.10", "0.20"]
    assert rows[1].customer_name == "Jane Doe"
    assert rows[0].payment_id == records[0][0].id
    assert rows[0].received_at == records[0][0].created_at
    assert rows[0].invoice_number == "INV-1"
