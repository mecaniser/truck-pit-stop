"""Bounded ETS provenance only. Never supplies settlement eligibility."""
import json
import re
from datetime import datetime
from decimal import Decimal, InvalidOperation


def normalize_source_evidence(value):
    if not isinstance(value, dict) or value.get("schema_version") != 1 or value.get("source") != "easy_truck_shop":
        return None

    def ident(v):
        if type(v) is int and v >= 0:
            return str(v)
        if isinstance(v, str) and re.fullmatch(r"[A-Za-z0-9_.:-]{1,160}", v):
            return v
        return None

    def date(v):
        if not isinstance(v, str) or len(v) > 40 or not re.fullmatch(r"\d{4}-\d{2}-\d{2}T.*", v):
            return None
        try:
            datetime.fromisoformat(v.replace("Z", "+00:00"))
            return v  # retain offset and precision, including unknown timezone
        except ValueError:
            return None

    def money(v):
        if not isinstance(v, dict):
            return None
        a = v.get("amount")
        if isinstance(a, bool) or not isinstance(a, (str, int, float)) or len(str(a)) > 32:
            return None
        try:
            if not Decimal(str(a)).is_finite():
                return None
        except InvalidOperation:
            return None
        c = v.get("currency")
        return {"amount": str(a), "currency": c if isinstance(c, str) and re.fullmatch(r"[A-Z]{3}", c) else None}

    lines = value.get("payment_lines")
    if not isinstance(lines, list) or len(lines) > 200:
        return None
    service_id, invoice_id = ident(value.get("service_id")), ident(value.get("invoice_id"))
    internal_id = ident(value.get("service_internal_id"))
    if not internal_id or internal_id != ident(value.get("invoice_service_id")):
        return None
    if not service_id or not invoice_id:
        return None
    result = {"schema_version": 1, "source": "easy_truck_shop", "settlement_semantics": "unverified",
              "service_id": service_id, "invoice_id": invoice_id,
              "ets_shop_id": ident(value.get("ets_shop_id")),
              "observed_at_source": date(value.get("observed_at_source")),
              "invoice_number": ident(value.get("invoice_number")),
              "service_internal_id": internal_id, "invoice_service_id": internal_id,
              "completed_at_source": date(value.get("completed_at_source")),
              "completed": value.get("completed") if type(value.get("completed")) is bool else None,
              "service_status": value.get("service_status") if type(value.get("service_status")) is int else None,
              "invoice_status": ident(value.get("invoice_status")),
              "currency": value.get("currency") if re.fullmatch(r"[A-Z]{3}", str(value.get("currency"))) else None,
              "total": money(value.get("total")), "balance": money(value.get("balance")),
              "payment_lines_truncated": value.get("payment_lines_truncated") is True, "payment_lines": []}
    manifest = value.get("invoice_manifest")
    result["invoice_manifest"] = None
    if (isinstance(manifest, dict) and manifest.get("complete") is True
            and manifest.get("evidence_kind") == "verified_source_service_invoice_manifest"
            and ident(manifest.get("service_internal_id")) == internal_id
            and isinstance(manifest.get("invoice_ids"), list) and 0 < len(manifest["invoice_ids"]) <= 200
            and all(ident(item) for item in manifest["invoice_ids"])
            and len(set(manifest["invoice_ids"])) == len(manifest["invoice_ids"])):
        result["invoice_manifest"] = {"complete": True, "evidence_kind": manifest["evidence_kind"],
            "service_internal_id": internal_id, "invoice_ids": [ident(item) for item in manifest["invoice_ids"]]}
    for line in lines:
        if not isinstance(line, dict) or not isinstance(line.get("payment"), dict):
            return None
        p = line["payment"]
        result["payment_lines"].append({"id": ident(line.get("id")), "amount": money(line.get("amount")), "payment": {
            "id": ident(p.get("id")), "date_source": date(p.get("date_source")),
            "date_semantics": "source_datetime_unverified",
            **{k: ident(p.get(k)) for k in ("status", "type", "provider", "qb_reference")},
            **{k: money(p.get(k)) for k in ("total", "credit_total", "unapplied_amount")},
            "canceled": p.get("canceled") if type(p.get("canceled")) is bool else None}})
    return result if len(json.dumps(result)) <= 131072 else None


def append_source_evidence(existing, evidence):
    """Immutable observations; bounded saturation is explicit, never replacement."""
    import hashlib
    import warnings
    digest = hashlib.sha256(json.dumps(evidence, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    if existing is None:
        existing = {"schema_version": 1, "observations": []}
    if not isinstance(existing, dict) or existing.get("schema_version") != 1 or not isinstance(existing.get("observations"), list):
        warnings.warn("ETS evidence envelope invalid; preservation held", RuntimeWarning)
        return existing
    rows = existing["observations"]
    if any(not isinstance(row, dict) or not isinstance(row.get("evidence"), dict)
           or any(row["evidence"].get(k) != evidence.get(k) for k in ("service_id", "invoice_id", "invoice_number", "service_internal_id", "invoice_service_id"))
           for row in rows):
        warnings.warn("ETS evidence source identity mismatch; preservation held", RuntimeWarning)
        return existing
    if any(isinstance(row, dict) and row.get("sha256") == digest for row in rows):
        return existing
    if len(rows) >= 20:
        warnings.warn("ETS evidence revision capacity reached; preservation held", RuntimeWarning)
        return existing
    return {"schema_version": 1, "observations": [*rows, {"sha256": digest, "evidence": evidence}]}
