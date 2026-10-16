"""DB132 exact decimal pricing. Selection/storage are deliberately separate.

An attachment records these inputs once; subsequent reads/edits never call this
resolver with current inventory. C1 can provide an explicitly selected revision.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any
from uuid import uuid4

from fastapi import HTTPException

CENT = Decimal('0.01')
MAX_MONEY = Decimal('99999999.99')
ZERO = Decimal('0')


def fail(code: str, message: str, status: int = 422, **safe):
    raise HTTPException(status, {'code': code, 'message': message, **safe})


def amount(value: Any, *, optional: bool = False, label: str = 'Amount') -> Decimal | None:
    if value is None and optional:
        return None
    try:
        if isinstance(value, bool) or value is None:
            raise ValueError()
        number = Decimal(str(value))
        if not number.is_finite() or number < 0 or number > MAX_MONEY or number != number.quantize(CENT):
            raise ValueError()
        return number.quantize(CENT)
    except (ValueError, InvalidOperation, TypeError):
        fail('invalid_price', f'{label} must be a finite non-negative amount with at most two decimal places.')


def cents(value: Any) -> str:
    return format(Decimal(str(value)).quantize(CENT, rounding=ROUND_HALF_UP), '.2f')


def line_total(price: Decimal, quantity: Decimal) -> Decimal:
    from app.core.work_value_validation import validate_part_quantity
    try:
        quantity = validate_part_quantity(quantity)
    except ValueError as exc:
        fail('invalid_quantity', str(exc))
    total = price * quantity
    if not total.is_finite() or total > MAX_MONEY:
        fail('price_overflow', 'This part quantity and price exceed the supported line amount.')
    return total.quantize(CENT)


def validate_bands(bands: list[dict]) -> list[dict[str, str | None]]:
    if not 1 <= len(bands) <= 30:
        fail('invalid_bands', 'Use between 1 and 30 contiguous cost bands.')
    expected = ZERO
    result = []
    for index, raw in enumerate(bands):
        if set(raw) != {'min_cost', 'max_cost', 'markup_percent'}:
            fail('invalid_bands', 'Each band requires a lower bound, upper bound and markup percent.')
        lo = amount(raw['min_cost'], label='Lower cost')
        hi = amount(raw['max_cost'], optional=True, label='Upper cost')
        pct = amount(raw['markup_percent'], label='Markup percent')
        if pct > Decimal('10000') or lo != expected or (hi is not None and hi <= lo) or (hi is None) != (index == len(bands)-1):
            fail('invalid_bands', 'Bands must start at zero, have no gaps or overlaps, and end with an open upper bound.')
        result.append({'min_cost': cents(lo), 'max_cost': cents(hi) if hi is not None else None, 'markup_percent': cents(pct)})
        expected = hi
    return result


@dataclass(frozen=True)
class PricePolicy:
    generation: int = 0
    matrix_id: Any = None
    revision_id: Any = None
    revision: int | None = None
    name: str | None = None
    bands: list[dict] | None = None


@dataclass(frozen=True)
class ResolvedPrice:
    default: Decimal
    charged: Decimal
    actual_cost: Decimal | None
    snapshot: dict
    revision_id: Any = None
    warning: str | None = None


def resolve_price(item, policy: PricePolicy, *, internal=False, ad_hoc=False,
                  actual_cost_known=True, intent='default', requested=None, reason=None,
                  actor_id=None, can_override=False, quantity=Decimal('1'), counter=False) -> ResolvedPrice:
    cost = amount(item.cost, optional=not actual_cost_known, label='Actual cost') if actual_cost_known else None
    catalog = amount(item.selling_price, optional=True, label='Catalog price')
    floor = amount(getattr(item, 'pricing_cost_floor', None), optional=True, label='Pricing cost floor')
    minimum = amount(getattr(item, 'minimum_sale_price', None), optional=True, label='Minimum sale price')
    fixed = bool(getattr(item, 'fixed_sales_price', False))
    requested = amount(requested, optional=True, label='Charged price')
    basis = band = revision_id = None
    warning = None
    managed = not internal and not ad_hoc and bool(policy.revision_id or fixed or minimum is not None)
    effective = max(cost or ZERO, minimum or ZERO) if managed else cost
    default_error = None
    if internal:
        if cost is None:
            fail('ad_hoc_cost_required' if ad_hoc else 'part_cost_required', 'Enter the actual part cost before adding internal work.')
        default, source = cost, 'internal'
        if requested is not None and requested != cost:
            fail('internal_price_fixed', 'Internal parts must use actual cost.')
    elif ad_hoc:
        if requested is None:
            fail('part_price_required', 'Enter a price for this new part.')
        default, source = requested, 'ad_hoc'
    elif fixed:
        if catalog is None: fail('part_price_required', 'Record a fixed catalog price for this part.')
        default, source = catalog, 'fixed'
    elif policy.revision_id:
        if cost is None or (getattr(item, 'is_placeholder', False) and cost == 0):
            fail('part_cost_required', 'Record a known actual cost before applying a price matrix.')
        basis = max(cost, floor or ZERO)
        band = next((b for b in validate_bands(policy.bands or []) if basis >= Decimal(b['min_cost']) and (b['max_cost'] is None or basis < Decimal(b['max_cost']))), None)
        if band is None:
            fail('invalid_bands', 'No price band covers this part.')
        default = basis * (1 + Decimal(band['markup_percent']) / 100)
        if default > MAX_MONEY:
            fail('price_overflow', 'The calculated part price exceeds the supported amount.')
        default = max(default.quantize(CENT, rounding=ROUND_HALF_UP), minimum or ZERO)
        source, revision_id = 'matrix', policy.revision_id
        if not basis and not minimum and catalog is not None and catalog > 0:
            default, source, revision_id, band = catalog, 'catalog', None, None
            warning = 'catalog_zero_cost'
        elif not default:
            default_error = ('part_price_required', 'Enter a usable price for this part.')
    else:
        if catalog is None: fail('part_price_required', 'Record a catalog price for this part.')
        default, source = catalog, 'catalog'
    if managed and default < effective:
        default_error = ('price_below_minimum', 'The configured part price is below its allowed minimum. Update pricing or enter a valid override.')
    if intent not in {'default', 'manual', 'stock'}:
        fail('price_intent_required', 'Choose an explicit pricing action.', 409)
    if ad_hoc:
        charged = default
    elif intent == 'default':
        if requested is not None and requested != default:
            fail('price_intent_required', 'Confirm an explicit manual price and reason.', 403 if not can_override else 409)
        charged = default
    else:
        if not can_override:
            fail('price_override_forbidden', 'You cannot override a part price.', 403)
        if intent == 'manual':
            reason = (reason or '').strip()
            if not 3 <= len(reason) <= 500:
                fail('price_reason_required', 'Enter a reason between 3 and 500 characters.')
            if requested is None:
                fail('part_price_required', 'Enter the charged unit price.')
            charged = requested
        else:
            if cost is None:
                fail('part_cost_required', 'The original actual cost is unknown.')
            if requested is not None and requested != cost:
                fail('price_intent_required', 'Stock pricing must match the original actual cost.', 409)
            charged, reason = cost, 'use_original_cost'
    if default_error and intent == 'default':
        fail(*default_error)
    if (managed or intent != 'default' or ad_hoc) and effective is not None and charged < effective:
        fail('price_below_minimum', 'This part price is below its allowed minimum.')
    if counter and charged <= 0:
        fail('part_price_required', 'Counter-sale prices must be greater than zero.')
    line_total(charged, quantity)
    snapshot = {
        'schema_version': 1, 'snapshot_id': str(uuid4()), 'managed': managed,
        'source': source, 'default_generation': policy.generation if not internal and not ad_hoc and not fixed else None,
        'matrix': {'id': str(policy.matrix_id), 'revision_id': str(revision_id), 'revision': policy.revision, 'name': policy.name, 'band': band} if revision_id else None,
        'actual_unit_cost': cents(cost) if cost is not None else None, 'actual_cost_known': cost is not None,
        'pricing_cost_floor': cents(floor) if floor is not None else None,
        'pricing_basis': cents(basis) if basis is not None else None,
        'minimum_sale_price': cents(minimum) if minimum is not None else None,
        'effective_minimum': cents(effective) if effective is not None else None,
        'fixed_catalog_price': fixed, 'catalog_unit_price': cents(catalog) if catalog is not None else None,
        'default_unit_price': cents(default), 'original_charged_unit_price': cents(charged),
        'initial_override': {'reason': reason or 'ad_hoc_price_entered', 'actor_id': str(actor_id), 'occurred_at': datetime.now(timezone.utc).isoformat()} if intent != 'default' or ad_hoc else None,
        'warning': warning,
    }
    return ResolvedPrice(default, charged, cost, snapshot, revision_id, warning)


def saved_floor(row):
    snapshot = getattr(row, 'pricing_snapshot', None) or {}
    if snapshot.get('managed'):
        return max(amount(snapshot.get('actual_unit_cost'), optional=True) or ZERO, amount(snapshot.get('minimum_sale_price'), optional=True) or ZERO)
    return amount(row.unit_cost, optional=True)


def safe_price(row, *, can_override=False, snapshot=None, price=None, default=None, quantity=None, persisted=True):
    snapshot = snapshot if snapshot is not None else (getattr(row, 'pricing_snapshot', None) or {})
    if price is None:
        price = getattr(row, 'unit_price', getattr(row, 'charged_unit_price', None))
    if default is None:
        default = getattr(row, 'list_price', getattr(row, 'list_unit_price', None))
    quantity = quantity if quantity is not None else row.quantity
    source = snapshot.get('source', 'legacy_unknown')
    if source not in {'matrix', 'fixed', 'catalog', 'ad_hoc', 'internal', 'legacy_unknown'}:
        source = 'catalog'
    return {**({'policy_source':snapshot['policy_source']} if snapshot.get('policy_source') in {'customer','shop','internal','legacy'} else {}), 'origin_source': source, 'current_source': getattr(row, '_pricing_current_source', None) or ('manual' if snapshot.get('initial_override') and source != 'ad_hoc' else source),
            'managed': bool(snapshot.get('managed')), 'default_unit_price': cents(default) if default is not None else None,
            'charged_unit_price': cents(price) if price is not None else None, 'line_total': format(line_total(price, quantity), '.2f') if price is not None else None,
            'pricing_version': getattr(row, 'pricing_version', None) if persisted else None, 'can_override': can_override}
