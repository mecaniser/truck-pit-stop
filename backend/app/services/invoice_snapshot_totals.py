"""Read-only totals from issued invoice snapshots, never live repair orders."""
from decimal import Decimal, DecimalException


def invoice_snapshot_totals(snapshot):
    if not isinstance(snapshot, dict):
        return {}
    totals = {}
    for collection, amount, field in (
        ("labor", "total_cost", "labor_total"),
        ("parts", "total_price", "parts_total"),
    ):
        rows = snapshot.get(collection)
        if not isinstance(rows, list):
            return {}
        try:
            values = [Decimal(str(row[amount])) for row in rows]
            if any(not value.is_finite() or value < 0 for value in values):
                return {}
            totals[field] = sum(values, Decimal("0.00")).quantize(Decimal("0.01"))
        except (KeyError, TypeError, ValueError, DecimalException):
            return {}
    return totals
