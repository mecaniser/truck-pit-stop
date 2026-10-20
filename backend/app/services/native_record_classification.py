"""Private deployment read policy. It changes no financial source records."""
from __future__ import annotations

import hashlib
import hmac
import json
import re
from dataclasses import dataclass
from uuid import UUID

from app.core.config import settings

MAX_POLICY_BYTES = 65536
MAX_POLICY_ENTRIES = 256
FIELDS = {"tenant_id", "invoice_id", "invoice_number", "repair_order_id",
          "billed_customer_id", "resolved_customer_id", "classification"}
TOP_FIELDS = {"version", "review_reference", "review_snapshot_sha256", "entries", "policy_sha256"}
HEX = re.compile(r"[0-9a-f]{64}\Z")


def _strict_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate field")
        result[key] = value
    return result


def _uuid(value):
    if not isinstance(value, str) or str(UUID(value)) != value:
        raise ValueError("noncanonical identity")
    return value


def policy_digest(payload: dict) -> str:
    return hashlib.sha256(json.dumps({key: value for key, value in payload.items()
                                     if key != "policy_sha256"}, sort_keys=True,
                                    separators=(",", ":"), ensure_ascii=True).encode()).hexdigest()


@dataclass(frozen=True)
class NativeRecordPolicy:
    available: bool
    entries: dict

    def classify(self, invoice, order, resolved_customer_id: UUID | None, *, tenant_id: UUID) -> str:
        if (not self.available or invoice.tenant_id != tenant_id or order.tenant_id != tenant_id
                or invoice.repair_order_id != order.id or resolved_customer_id is None):
            return "unknown"
        identity = {"tenant_id": str(tenant_id), "invoice_id": str(invoice.id),
                    "invoice_number": invoice.invoice_number, "repair_order_id": str(order.id),
                    "billed_customer_id": str(invoice.billed_customer_id) if invoice.billed_customer_id else None,
                    "resolved_customer_id": str(resolved_customer_id)}
        entry = self.entries.get((str(tenant_id), str(invoice.id)))
        if not entry or any(entry[key] != value for key, value in identity.items()):
            return "unknown"
        return entry["classification"]


def load_native_record_policy(raw: str | None = None) -> NativeRecordPolicy:
    """Invalid or absent configuration fails closed without exposing its contents."""
    if raw is None:
        raw = settings.DB135_NATIVE_RECORD_POLICY_JSON
    try:
        if not isinstance(raw, str) or not raw or len(raw.encode()) > MAX_POLICY_BYTES:
            raise ValueError("unavailable")
        payload = json.loads(raw, object_pairs_hook=_strict_object,
                             parse_constant=lambda _: (_ for _ in ()).throw(ValueError("constant")))
        if not isinstance(payload, dict) or set(payload) != TOP_FIELDS:
            raise ValueError("fields")
        if type(payload["version"]) is not int or payload["version"] != 1:
            raise ValueError("version")
        reference = payload["review_reference"]
        if not isinstance(reference, str) or not reference.strip() or len(reference) > 200 or any(ord(c) < 32 for c in reference):
            raise ValueError("reference")
        for key in ("review_snapshot_sha256", "policy_sha256"):
            if not isinstance(payload[key], str) or not HEX.fullmatch(payload[key]):
                raise ValueError("digest")
        entries = payload["entries"]
        if not isinstance(entries, list) or len(entries) > MAX_POLICY_ENTRIES:
            raise ValueError("entries")
        mapped = {}
        identities = []
        for entry in entries:
            if not isinstance(entry, dict) or set(entry) != FIELDS:
                raise ValueError("entry fields")
            for key in ("tenant_id", "invoice_id", "repair_order_id", "resolved_customer_id"):
                _uuid(entry[key])
            if entry["billed_customer_id"] is not None:
                _uuid(entry["billed_customer_id"])
            number = entry["invoice_number"]
            if not isinstance(number, str) or not number.strip() or len(number) > 100 or any(ord(c) < 32 for c in number):
                raise ValueError("invoice number")
            if entry["classification"] not in ("real", "test", "unknown"):
                raise ValueError("classification")
            key = (entry["tenant_id"], entry["invoice_id"])
            if key in mapped:
                raise ValueError("duplicate identity")
            mapped[key] = entry
            identities.append(key)
        if identities != sorted(identities) or not hmac.compare_digest(policy_digest(payload), payload["policy_sha256"]):
            raise ValueError("integrity")
        return NativeRecordPolicy(True, mapped)
    except (ValueError, TypeError, KeyError, RecursionError, UnicodeError):
        return NativeRecordPolicy(False, {})
