"""Bounded, current account-phone evidence. No financial or editable-field writes."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import hashlib
import json
import re

REASONS = {"read_unavailable", "account_mismatch", "filtered", "page_incomplete", "schema_unsupported"}


def instant(value):
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("source timestamp must be aware")
    return parsed.astimezone(timezone.utc)


def phone(value):
    if not isinstance(value, str) or len(value) > 100 or re.search(r"[^0-9+().\s-]", value):
        raise ValueError("unsupported phone")
    digits = re.sub(r"\D", "", value)
    if len(digits) == 11 and digits.startswith("1"):
        digits = digits[1:]
    if not re.fullmatch(r"[2-9][0-9]{2}[2-9][0-9]{6}", digits):
        raise ValueError("unsupported phone")
    return "+1" + digits


def digest(snapshot):
    facts = {key: value for key, value in snapshot.items() if key not in {"observed_at", "semantic_hash"}}
    return hashlib.sha256(json.dumps(facts, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()).hexdigest()


def normalize(raw, *, customer_id, dbn_customer_id):
    """Legacy files have no evidence and cannot become fresh observations."""
    if not isinstance(raw, dict):
        return None
    try:
        observed = instant(raw["observed_at"])
    except (KeyError, ValueError, TypeError):
        return None
    if observed > datetime.now(timezone.utc) + timedelta(minutes=5):
        return None
    shop = raw.get("source_shop_id")
    if not isinstance(shop, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,140}", shop):
        return None
    account = str(customer_id) if customer_id is not None else None
    reason = raw.get("reason")
    complete = raw.get("complete") is True
    if account is None or not re.fullmatch(r"[0-9]{1,50}", account) or raw.get("source_customer_id") != account:
        complete, reason = False, "account_mismatch"
        account = account if account and re.fullmatch(r"[0-9]{1,50}", account) else None
    contacts = []
    if complete:
        try:
            values = raw["phones"]
            if not isinstance(values, list) or len(values) > 200:
                raise ValueError("too many phones")
            contacts = [{"source_contact_id": None, "phone": value} for value in sorted({phone(v) for v in values if v != ""})]
            reason = None
        except (KeyError, ValueError, TypeError):
            complete, reason = False, "schema_unsupported"
    if not complete:
        contacts = []
        reason = reason if reason in REASONS else "schema_unsupported"
    result = {"source_system": "easy_truck_shop", "source_shop_id": shop,
              "source_customer_id": account, "dbn_customer_id": str(dbn_customer_id),
              "observed_at": observed.isoformat(), "complete": complete, "reason": reason,
              "contacts": contacts}
    result["semantic_hash"] = digest(result)
    return result


def latest(previous, incoming):
    """Replays cannot clear newer failures; equal-time conflicting facts hold."""
    if incoming is None:
        return previous
    if not isinstance(previous, dict):
        return incoming
    try:
        old, new = instant(previous["observed_at"]), instant(incoming["observed_at"])
    except (KeyError, ValueError, TypeError):
        return incoming
    if new < old:
        return previous
    if new == old and previous.get("semantic_hash") != incoming.get("semantic_hash"):
        result = deepcopy(incoming)
        result.update(complete=False, reason="account_mismatch", contacts=[])
        result["semantic_hash"] = digest(result)
        return result
    return incoming


def for_history(snapshot, *, customer_id, dbn_customer_id, shop_id, source):
    if not isinstance(snapshot, dict):
        return None
    result = deepcopy(snapshot)
    if (source != "easy_truck_shop_import" or not shop_id or result.get("source_shop_id") != shop_id
            or result.get("source_customer_id") != customer_id
            or result.get("dbn_customer_id") != str(dbn_customer_id)
            or result.get("semantic_hash") != digest(result)):
        result.update(source_customer_id=customer_id, dbn_customer_id=str(dbn_customer_id),
                      complete=False, reason="account_mismatch", contacts=[])
        # Retain the last configured source shop for a safe invalidation only.
        if shop_id:
            result["source_shop_id"] = shop_id
        result["semantic_hash"] = digest(result)
    return result
