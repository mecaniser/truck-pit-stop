"""Cost-based discount capacity; read-only until a caller validates its draft."""
from decimal import Decimal, ROUND_CEILING, ROUND_FLOOR

ZERO = Decimal('0.00')
CENT = Decimal('0.01')


def amount(value):
    if value is None:
        return None
    value = Decimal(str(value))
    return value if value.is_finite() and value >= 0 else None


def part_cost(part):
    cost = amount(part.unit_cost)
    if cost is None:
        inventory = part.inventory_item
        if inventory is not None and inventory.tenant_id == part.tenant_id:
            cost = amount(inventory.cost)
    return cost


def proposed_part_price(part, mode):
    cost = part_cost(part)
    if mode == 'stock':
        if cost is None:
            raise ValueError('Set the shop cost for every part before using stock pricing.')
        return cost
    inventory = part.inventory_item
    fallback = inventory.selling_price if inventory is not None and inventory.tenant_id == part.tenant_id else part.unit_price
    price = amount(part.list_price if part.list_price is not None else fallback)
    return max(price or ZERO, cost or ZERO)


def discount_limits(order, mode=None):
    rate = amount(order.tenant.internal_labor_rate)
    labor_margin = ZERO
    labor_reason = None
    for line in order.labor_items:
        sale = amount(line.total_cost) or ZERO
        if getattr(line.line_type, 'value', line.line_type) == 'sublet':
            floor = amount(line.vendor_cost)
        else:
            hours = amount(line.hours)
            floor = rate * hours if rate and hours else (ZERO if sale == 0 else None)
        if floor is None:
            labor_reason = 'Set internal fleet labor cost, billed hours, and any sublet vendor costs before discounting labor.'
        else:
            labor_margin += sale - floor.quantize(CENT, rounding=ROUND_CEILING)
    if labor_margin < 0:
        labor_reason = 'Labor is already priced below shop cost.'
    labor_max = ZERO if labor_reason else max(ZERO, labor_margin).quantize(CENT, rounding=ROUND_FLOOR)
    parts_margin = ZERO
    parts_reason = None
    for part in order.parts_usage:
        cost = part_cost(part)
        quantity = amount(part.quantity)
        if cost is None or quantity is None:
            parts_reason = 'Set the shop cost for every part before applying an order discount.'
            continue
        sale = (proposed_part_price(part, mode) * quantity) if mode else (amount(part.total_price) or ZERO)
        floor = (cost * quantity).quantize(CENT, rounding=ROUND_CEILING)
        if sale < floor:
            parts_reason = 'A part is already priced below shop cost.'
        parts_margin += sale - floor
    reason = labor_reason or parts_reason
    return {
        'labor_discount_max': labor_max,
        'combined_discount_max': ZERO if reason else max(ZERO, labor_margin + parts_margin).quantize(CENT, rounding=ROUND_FLOOR),
        'labor_discount_block_reason': labor_reason,
        'order_discount_block_reason': reason,
    }


def validate_discounts(order, labor=None, total=None, mode=None):
    labor = Decimal(str(order.labor_discount_amount or 0)) if labor is None else Decimal(str(labor))
    total = Decimal(str(order.order_discount_amount or 0)) if total is None else Decimal(str(total))
    if not labor.is_finite() or not total.is_finite() or labor < 0 or total < 0:
        raise ValueError('Discounts must be finite, non-negative amounts.')
    # Preserve legacy undiscounted orders; never silently reprice base charges.
    if not labor and not total:
        return
    limits = discount_limits(order, mode)
    if labor > limits['labor_discount_max']:
        raise ValueError(limits['labor_discount_block_reason'] or f"Labor discount cannot exceed ${limits['labor_discount_max']:,.2f}; shop labor cost is protected.")
    if total and limits['order_discount_block_reason']:
        raise ValueError(limits['order_discount_block_reason'])
    if total and labor + total > limits['combined_discount_max']:
        maximum = max(ZERO, limits['combined_discount_max'] - labor)
        raise ValueError(f'Order discount cannot exceed ${maximum:,.2f} after the labor discount; shop costs are protected.')
