"""Work & Labor lines must keep their place when one of them is edited.

Neither relationship declared an order, so rows came back in heap order.
Postgres writes a new tuple version on UPDATE, which usually lands at the end
of the heap, so editing a labor duration or a part quantity silently moved that
line to the bottom of the work list. Demonstrated against Postgres: two lines
inserted 1, 2 come back 2, 1 after `UPDATE ... WHERE id = 1`.

These assert the ordering is declared, because SQLite (used by the suite) does
not reproduce the heap behaviour that caused the bug.
"""
from app.db.models.repair_order import RepairOrder


def _order_by_columns(relationship_name: str) -> list[str]:
    prop = getattr(RepairOrder, relationship_name).property
    return [str(clause) for clause in (prop.order_by or [])]


def test_labor_items_are_ordered_by_insertion():
    columns = _order_by_columns("labor_items")
    assert columns, "labor_items must declare an order, or edited lines move"
    assert columns[0].endswith("labor.created_at")


def test_parts_usage_is_ordered_by_insertion():
    columns = _order_by_columns("parts_usage")
    assert columns, "parts_usage must declare an order, or edited lines move"
    assert columns[0].endswith("parts_usage.created_at")


def test_both_break_ties_deterministically():
    # created_at comes from now(), which is the transaction timestamp — lines
    # added in one request share it, so a tiebreaker is required for a stable
    # order across reloads.
    for name, table in (("labor_items", "labor"), ("parts_usage", "parts_usage")):
        columns = _order_by_columns(name)
        assert len(columns) >= 2, f"{name} needs a tiebreaker after created_at"
        assert columns[1].endswith(f"{table}.id")
