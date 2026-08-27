"""Additive, source-distinct reporting projections for DB-045 counter sales.

Counter sales never create repair orders or invoices.  This module projects
their immutable completion/return records into the existing reporting date
boundaries without changing any repair-domain source record.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.inventory_lifecycle import (
    CounterSale,
    CounterSaleLine,
    CounterSaleReturn,
    CounterSaleReturnLine,
)


CENT = Decimal("0.01")
RECOGNIZED_SALE_STATES = ("completed", "partially_returned", "returned")


def money(value: object) -> Decimal:
    return Decimal(str(value or 0)).quantize(CENT, rounding=ROUND_HALF_UP)


@dataclass(frozen=True)
class CounterSaleReportEntry:
    occurred_on: date
    entry_type: str
    sale_id: UUID
    sale_number: str
    customer_id: UUID | None
    buyer_name: str | None
    item_sales: Decimal
    discounts: Decimal
    tax: Decimal
    fees: Decimal
    cogs: Decimal
    units: int

    @property
    def net_total(self) -> Decimal:
        return money(self.item_sales + self.tax + self.fees)

    @property
    def margin(self) -> Decimal:
        return money(self.item_sales - self.cogs)


async def load_counter_sale_report_entries(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    start: date,
    end: date,
) -> list[CounterSaleReportEntry]:
    """Return completed sales and completed returns in one reporting window.

    A return completed in the window nets that window even when its original
    sale completed earlier.  Restocked returns reverse cost basis; damaged
    returns deliberately do not. Pending/failed records never enter reports.
    """
    sale_rows = (await db.execute(
        select(CounterSale).where(
            CounterSale.tenant_id == tenant_id,
            CounterSale.status.in_(RECOGNIZED_SALE_STATES),
            CounterSale.completed_at.is_not(None),
            func.date(CounterSale.completed_at) >= start,
            func.date(CounterSale.completed_at) <= end,
            CounterSale.deleted_at.is_(None),
        )
    )).scalars().all()
    sale_ids = [row.id for row in sale_rows]
    lines_by_sale: dict[UUID, list[CounterSaleLine]] = {}
    if sale_ids:
        for line in (await db.execute(select(CounterSaleLine).where(
            CounterSaleLine.tenant_id == tenant_id,
            CounterSaleLine.sale_id.in_(sale_ids),
            CounterSaleLine.deleted_at.is_(None),
        ))).scalars().all():
            lines_by_sale.setdefault(line.sale_id, []).append(line)

    entries: list[CounterSaleReportEntry] = []
    for sale in sale_rows:
        lines = lines_by_sale.get(sale.id, [])
        entries.append(CounterSaleReportEntry(
            occurred_on=sale.completed_at.date(),
            entry_type="sale",
            sale_id=sale.id,
            sale_number=sale.sale_number,
            customer_id=sale.customer_id,
            buyer_name=sale.buyer_name_snapshot,
            item_sales=money(sale.charged_subtotal),
            discounts=money(sale.discount_total),
            tax=money(sale.tax_total),
            fees=money(sale.service_fee_total),
            cogs=money(sum((money(line.cost_total) for line in lines), Decimal("0"))),
            units=sum(int(line.quantity) for line in lines),
        ))

    return_rows = (await db.execute(
        select(CounterSaleReturn, CounterSale)
        .join(
            CounterSale,
            (CounterSale.id == CounterSaleReturn.sale_id)
            & (CounterSale.tenant_id == CounterSaleReturn.tenant_id),
        )
        .where(
            CounterSaleReturn.tenant_id == tenant_id,
            CounterSaleReturn.state == "completed",
            CounterSaleReturn.completed_at.is_not(None),
            func.date(CounterSaleReturn.completed_at) >= start,
            func.date(CounterSaleReturn.completed_at) <= end,
            CounterSaleReturn.deleted_at.is_(None),
            CounterSale.deleted_at.is_(None),
        )
    )).all()
    return_ids = [row.id for row, _sale in return_rows]
    lines_by_return: dict[UUID, list[CounterSaleReturnLine]] = {}
    if return_ids:
        for line in (await db.execute(select(CounterSaleReturnLine).where(
            CounterSaleReturnLine.tenant_id == tenant_id,
            CounterSaleReturnLine.return_id.in_(return_ids),
            CounterSaleReturnLine.deleted_at.is_(None),
        ))).scalars().all():
            lines_by_return.setdefault(line.return_id, []).append(line)

    for return_row, sale in return_rows:
        lines = lines_by_return.get(return_row.id, [])
        restocked_cost = sum(
            (money(line.cost_amount) for line in lines if line.disposition == "restock"),
            Decimal("0"),
        )
        entries.append(CounterSaleReportEntry(
            occurred_on=return_row.completed_at.date(),
            entry_type="return",
            sale_id=sale.id,
            sale_number=sale.sale_number,
            customer_id=sale.customer_id,
            buyer_name=sale.buyer_name_snapshot,
            item_sales=-money(return_row.item_amount),
            # Discounts are recognized at sale completion and are not charged
            # again on return; the stored item allocation is already net.
            discounts=Decimal("0.00"),
            tax=-money(return_row.tax_amount),
            fees=-money(return_row.fee_amount),
            cogs=-money(restocked_cost),
            units=-sum(int(line.quantity) for line in lines),
        ))

    entries.sort(key=lambda row: (row.occurred_on, row.sale_number, row.entry_type))
    return entries

