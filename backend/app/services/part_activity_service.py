"""Append-only Activity writer and stable read-contract helpers (DB-045)."""
from __future__ import annotations

import base64
import hashlib
import json
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Iterable
from uuid import UUID, uuid4

from fastapi import HTTPException, status
from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.inventory import Inventory
from app.db.models.inventory_lifecycle import PartActivityEvent
from app.db.models.user import User
from app.services.parts_operations_service import actor_name, decimal_money


ALLOWED_VALUE_FIELDS = frozenset({
    "sku", "name", "description", "category", "category_id", "location",
    "unit_type", "image_url", "reorder_level", "cost", "selling_price",
    "core_charge", "supplier_name", "supplier_contact", "is_placeholder",
    "unit_cost", "unit_price", "list_price",
    "supplier_id", "supplier_part_number", "is_preferred",
    "minimum_order_quantity", "pack_quantity", "lead_time_days", "is_active",
    "stock_quantity", "status", "quantity", "tender", "disposition",
})
ACTIVITY_CATEGORIES = frozenset({"catalog", "stock", "repairs", "purchasing", "returns", "sales"})
ACTIVITY_EVENT_TYPES = {
    "catalog": frozenset({
        "part.created", "part.baseline", "part.identity_changed",
        "part.category_changed", "part.location_changed", "part.unit_changed",
        "part.photo_changed", "part.reorder_level_changed", "part.cost_changed",
        "part.selling_price_changed", "supplier_source.created",
        "supplier_source.updated", "supplier_source.preferred_changed",
        "supplier_source.removed",
    }),
    "stock": frozenset({
        "stock.adjusted", "stock.received", "stock.repair_reserved",
        "stock.repair_released", "stock.counter_sale_completed",
        "stock.counter_sale_returned",
    }),
    "repairs": frozenset({
        "repair_usage.added", "repair_usage.changed", "repair_usage.removed",
        "repair_usage.current_snapshot",
    }),
    "purchasing": frozenset({
        "purchase_order.created", "purchase_order.updated",
        "purchase_order.submitted", "purchase_order.cancelled",
        "receipt.recorded", "receipt.current_snapshot", "core.status_changed",
        "core.current_snapshot",
    }),
    "returns": frozenset({
        "vendor_return.created", "vendor_return.submitted",
        "vendor_return.shipped", "vendor_return.credited",
        "vendor_return.cancelled", "vendor_return.reversed",
        "vendor_return.current_snapshot",
    }),
    "sales": frozenset({
        "counter_sale.created", "counter_sale.updated",
        "counter_sale.awaiting_payment", "counter_sale.payment_succeeded",
        "counter_sale.payment_failed", "counter_sale.completed",
        "counter_sale.cancelled", "counter_sale.return_requested",
        "counter_sale.refund_succeeded", "counter_sale.refund_failed",
        "counter_sale.return_completed", "counter_sale.late_success_refunded",
    }),
}
ORIGINS = frozenset({"live", "baseline", "backfill_snapshot"})
PAYMENT_SAFE_FIELDS = frozenset({
    "tender", "state", "provider_object_id", "brand", "last_four", "failure_code",
})
STOCK_FIELDS = frozenset({
    "physical_on_hand", "held_for_checkout", "available_to_sell", "delta",
    "bucket", "stock_version",
})
MONEY_FIELDS = frozenset({
    "currency", "cost", "cost_before", "cost_after", "wac_before", "wac_after",
    "list_price", "charged_price", "discount", "item_subtotal", "tax",
    "service_fee", "total", "refund_allocations", "cost_basis", "unit_cost",
    "selling_price", "core_value", "expected_credit", "actual_credit",
    "before_unit_cost", "unit_price", "line_total",
})
REFUND_ALLOCATION_FIELDS = frozenset({"item", "tax", "fee", "total"})
SOURCE_FIELDS = frozenset({
    "number", "title", "summary", "purchase_order_id", "po_number",
    "reverses_return_id", "stock_shortage_override",
})
SENSITIVE_KEY_PARTS = frozenset({
    "token", "secret", "password", "authorization", "credential", "api_key",
    "card_number", "account_number", "routing_number", "pan", "cvv", "cvc",
})


def _json_scalar(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, bool)):
        return value
    if isinstance(value, Decimal):
        return str(decimal_money(value))
    if isinstance(value, (UUID, datetime)):
        return value.isoformat() if isinstance(value, datetime) else str(value)
    raise ValueError("Activity values must be typed JSON scalars")


def safe_values(values: dict[str, Any] | None) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in (values or {}).items():
        if key not in ALLOWED_VALUE_FIELDS:
            raise ValueError(f"Undocumented Activity value: {key}")
        result[key] = _json_scalar(value)
    return result


def _reject_sensitive_keys(snapshot: dict[str, Any] | None) -> None:
    def walk(value: Any) -> None:
        if isinstance(value, dict):
            for key, nested in value.items():
                normalized = str(key).lower().replace("-", "_")
                if any(part in normalized for part in SENSITIVE_KEY_PARTS):
                    raise ValueError("Sensitive Activity snapshot field is forbidden")
                walk(nested)
        elif isinstance(value, list):
            for nested in value:
                walk(nested)
    walk(snapshot or {})


def safe_stock_snapshot(snapshot: dict[str, Any] | None) -> dict[str, Any] | None:
    if snapshot is None:
        return None
    _reject_sensitive_keys(snapshot)
    if set(snapshot) - STOCK_FIELDS:
        raise ValueError("Undocumented Activity stock snapshot field")
    required = {"physical_on_hand", "held_for_checkout", "available_to_sell", "delta", "bucket"}
    if not required.issubset(snapshot):
        raise ValueError("Incomplete Activity stock snapshot")
    result: dict[str, Any] = {}
    for key in ("physical_on_hand", "held_for_checkout", "available_to_sell", "delta"):
        value = snapshot[key]
        if isinstance(value, bool) or not isinstance(value, int):
            raise ValueError("Activity stock quantities must be integers")
        result[key] = value
    bucket = snapshot["bucket"]
    if not isinstance(bucket, str) or not bucket or len(bucket) > 40:
        raise ValueError("Invalid Activity stock bucket")
    result["bucket"] = bucket
    version = snapshot.get("stock_version")
    if version is not None and (isinstance(version, bool) or not isinstance(version, int) or version < 0):
        raise ValueError("Invalid Activity stock version")
    result["stock_version"] = version
    return result


def _money_string(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, bool) or isinstance(value, (dict, list)):
        raise ValueError("Activity money values must be decimal scalars")
    try:
        return str(decimal_money(Decimal(str(value))))
    except Exception as exc:
        raise ValueError("Invalid Activity money value") from exc


def safe_money_snapshot(snapshot: dict[str, Any] | None) -> dict[str, Any] | None:
    if snapshot is None:
        return None
    _reject_sensitive_keys(snapshot)
    if set(snapshot) - MONEY_FIELDS:
        raise ValueError("Undocumented Activity money snapshot field")
    if snapshot.get("currency") != "USD":
        raise ValueError("Activity money currency must be USD")
    result: dict[str, Any] = {"currency": "USD"}
    for key, value in snapshot.items():
        if key == "currency":
            continue
        if key == "refund_allocations":
            if isinstance(value, dict):
                if set(value) - REFUND_ALLOCATION_FIELDS:
                    raise ValueError("Undocumented refund allocation field")
                result[key] = {
                    nested_key: _money_string(nested_value)
                    for nested_key, nested_value in value.items()
                }
            else:
                result[key] = _money_string(value)
        else:
            result[key] = _money_string(value)
    return result


def safe_source_snapshot(snapshot: dict[str, Any] | None) -> dict[str, Any] | None:
    if snapshot is None:
        return None
    _reject_sensitive_keys(snapshot)
    if set(snapshot) - SOURCE_FIELDS:
        raise ValueError("Undocumented Activity source snapshot field")
    result: dict[str, Any] = {}
    for key, value in snapshot.items():
        if key == "stock_shortage_override":
            if not isinstance(value, bool):
                raise ValueError("Invalid Activity source boolean")
            result[key] = value
        else:
            scalar = _json_scalar(value)
            if scalar is not None and len(str(scalar)) > 500:
                raise ValueError("Activity source value is too long")
            result[key] = scalar
    return result


def safe_payment_snapshot(snapshot: dict[str, Any] | None) -> dict[str, Any] | None:
    if snapshot is None:
        return None
    _reject_sensitive_keys(snapshot)
    if set(snapshot) - PAYMENT_SAFE_FIELDS:
        raise ValueError("Undocumented Activity payment snapshot field")
    result = {key: _json_scalar(value) for key, value in snapshot.items()}
    if result.get("last_four") is not None:
        last_four = str(result["last_four"])
        if len(last_four) != 4 or not last_four.isdigit():
            raise ValueError("Invalid Activity payment last-four")
        result["last_four"] = last_four
    return result


async def append_part_activity(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    inventory_id: UUID,
    category: str,
    event_type: str,
    idempotency_key: str,
    actor: User | None = None,
    occurred_at: datetime | None = None,
    correlation_id: UUID | None = None,
    source_type: str | None = None,
    source_id: UUID | None = None,
    source_number: str | None = None,
    part_sku_snapshot: str | None = None,
    part_name_snapshot: str | None = None,
    reason_code: str | None = None,
    note: str | None = None,
    origin: str = "live",
    before: dict[str, Any] | None = None,
    after: dict[str, Any] | None = None,
    stock: dict[str, Any] | None = None,
    money: dict[str, Any] | None = None,
    payment: dict[str, Any] | None = None,
    source: dict[str, Any] | None = None,
) -> PartActivityEvent:
    """Append one safe event inside the caller's transaction.

    Unique deterministic keys make mutation finalizers, live/backfill races,
    provider deliveries, and command reruns naturally idempotent.
    """
    if category not in ACTIVITY_CATEGORIES or origin not in ORIGINS:
        raise ValueError("Invalid Activity category or origin")
    if event_type not in ACTIVITY_EVENT_TYPES[category]:
        raise ValueError("Invalid Activity event type for category")
    existing = (await db.execute(select(PartActivityEvent).where(
        PartActivityEvent.tenant_id == tenant_id,
        PartActivityEvent.idempotency_key == idempotency_key,
    ))).scalar_one_or_none()
    if existing is not None:
        return existing
    before_values = safe_values(before)
    after_values = safe_values(after)
    if origin == "live" and before_values == after_values and (before or after):
        # Normalized no-op catalog/source commands deliberately leave no event.
        raise ValueError("Activity no-op")
    if part_sku_snapshot is None or part_name_snapshot is None:
        # db.get() consults the identity map first, preserving a normalized
        # in-transaction rename/create value even when the session deliberately
        # has autoflush disabled.  The event therefore captures event-time part
        # identity rather than joining mutable catalog values during reads.
        part = await db.get(Inventory, inventory_id)
        if part is None or part.tenant_id != tenant_id:
            raise ValueError("Activity part is unavailable")
        part_sku_snapshot = part_sku_snapshot or str(part.sku)
        part_name_snapshot = part_name_snapshot or str(part.name)
    event = PartActivityEvent(
        id=uuid4(), tenant_id=tenant_id, inventory_id=inventory_id,
        category=category, event_type=event_type,
        occurred_at=occurred_at or datetime.now(timezone.utc),
        correlation_id=correlation_id or uuid4(), source_type=source_type,
        source_id=source_id, source_number_snapshot=(source_number or None),
        part_sku_snapshot=part_sku_snapshot,
        part_name_snapshot=part_name_snapshot,
        actor_id=actor.id if actor else None,
        actor_name_snapshot=actor_name(actor) if actor else "System",
        reason_code=reason_code, note=note, origin=origin, payload_version=1,
        idempotency_key=idempotency_key, before_values=before_values,
        after_values=after_values, stock_snapshot=safe_stock_snapshot(stock),
        money_snapshot=safe_money_snapshot(money),
        payment_snapshot=safe_payment_snapshot(payment),
        source_snapshot=safe_source_snapshot(source),
    )
    db.add(event)
    return event


def normalized_filter_fingerprint(filters: dict[str, Any]) -> str:
    payload = json.dumps(filters, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(payload.encode()).hexdigest()


def encode_cursor(*, occurred_at: datetime, event_id: UUID, fingerprint: str) -> str:
    # PostgreSQL returns aware timestamps, while SQLite-based focused tests (and
    # some import paths) may materialize a timezone column as naive UTC. Never
    # let the host's local timezone shift a cursor boundary into the future.
    occurred_at_utc = (
        occurred_at.replace(tzinfo=timezone.utc)
        if occurred_at.tzinfo is None
        else occurred_at.astimezone(timezone.utc)
    )
    raw = json.dumps({
        "v": 1, "occurred_at": occurred_at_utc.isoformat(),
        "id": str(event_id), "filters": fingerprint,
    }, separators=(",", ":"), sort_keys=True).encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def decode_cursor(value: str, *, fingerprint: str) -> tuple[datetime, UUID]:
    try:
        padded = value + ("=" * (-len(value) % 4))
        payload = json.loads(base64.urlsafe_b64decode(padded).decode())
        if payload.get("v") != 1 or payload.get("filters") != fingerprint:
            raise ValueError
        occurred_at = datetime.fromisoformat(str(payload["occurred_at"]).replace("Z", "+00:00"))
        if occurred_at.tzinfo is None:
            raise ValueError
        return occurred_at, UUID(str(payload["id"]))
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid Activity cursor") from exc


def cursor_condition(occurred_at: datetime, event_id: UUID):
    return or_(
        PartActivityEvent.occurred_at < occurred_at,
        and_(PartActivityEvent.occurred_at == occurred_at, PartActivityEvent.id < event_id),
    )


def source_href(event: PartActivityEvent) -> str | None:
    if not event.source_type or not event.source_id:
        return None
    routes = {
        "repair_order": f"/dashboard/repair-orders/{event.source_id}",
        "purchase_order": f"/dashboard/garage/purchasing?purchaseOrder={event.source_id}",
        "purchase_receipt": f"/dashboard/garage/purchasing?receipt={event.source_id}",
        "vendor_return": f"/dashboard/garage/purchasing?return={event.source_id}",
        "counter_sale": f"/dashboard/garage/inventory/sales?sale={event.source_id}",
    }
    return routes.get(event.source_type, f"/dashboard/garage/inventory?activity={event.id}")


def serialize_activity(event: PartActivityEvent) -> dict[str, Any]:
    return {
        "id": str(event.id), "inventory_id": str(event.inventory_id),
        "part": {
            "id": str(event.inventory_id),
            "sku": event.part_sku_snapshot,
            "name": event.part_name_snapshot,
        },
        "category": event.category, "event_type": event.event_type,
        "occurred_at": event.occurred_at.isoformat(),
        "correlation_id": str(event.correlation_id), "origin": event.origin,
        "actor": {"id": str(event.actor_id) if event.actor_id else None, "name": event.actor_name_snapshot},
        "reason": {"code": event.reason_code, "note": event.note},
        "before": event.before_values or {}, "after": event.after_values or {},
        "stock": event.stock_snapshot, "money": event.money_snapshot,
        "payment": event.payment_snapshot,
        "source": {
            "type": event.source_type, "id": str(event.source_id) if event.source_id else None,
            "number": event.source_number_snapshot, "href": source_href(event),
            "snapshot": event.source_snapshot,
        },
    }


def escape_csv_text(value: Any) -> str:
    text_value = "" if value is None else str(value)
    if text_value[:1] in {"=", "+", "-", "@", "\t", "\r"}:
        return "'" + text_value
    return text_value
