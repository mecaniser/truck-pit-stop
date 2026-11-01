"""Bounded ETS provenance only. Never supplies settlement eligibility."""
import json
import re
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation



def _receipt_reference(value):
    if isinstance(value, str) and re.fullmatch(r"DBN-RECEIPT:[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}", value):
        return "DBN-RECEIPT:" + value.split(":", 1)[1].lower()
    return None


def _payment_date_semantics(value, claimed):
    if claimed != "source_datetime_utc" or not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,9})?(?:Z|\+00:00)", value):
        return "source_datetime_unverified"
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return "source_datetime_utc" if parsed.utcoffset() == timedelta(0) else "source_datetime_unverified"
    except ValueError:
        return "source_datetime_unverified"


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
    # Optional additive proof keeps legacy evidence hashes intact. Never infer
    # a numeric internal customer ID from the public ID or UUID.
    if (value.get("source_customer_binding_kind") == "embedded_service_customer"
            and re.fullmatch(r"[0-9]{1,160}", str(value.get("source_customer_id", "")))
            and re.fullmatch(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}", str(value.get("source_customer_uuid", "")))
            and type(value.get("source_customer_deleted")) is bool):
        result.update(source_customer_id=str(value["source_customer_id"]),
                      source_customer_uuid=value["source_customer_uuid"].lower(),
                      source_customer_deleted=value["source_customer_deleted"],
                      source_customer_binding_kind="embedded_service_customer")
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
            "date_semantics": _payment_date_semantics(p.get("date_source"), p.get("date_semantics")),
            **({"dbn_receipt_reference": _receipt_reference(p.get("dbn_receipt_reference"))} if _receipt_reference(p.get("dbn_receipt_reference")) else {}),
            **{k: ident(p.get(k)) for k in ("status", "type", "provider", "qb_reference")},
            **{k: money(p.get(k)) for k in ("total", "credit_total", "unapplied_amount")},
            "canceled": p.get("canceled") if type(p.get("canceled")) is bool else None}})
    return result if len(json.dumps(result)) <= 131072 else None


def _instant(value):
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed if parsed.utcoffset() is not None else None
    except (AttributeError, TypeError, ValueError):
        return None


def _facts(evidence):
    return {key: value for key, value in evidence.items() if key != "observed_at_source"}


def _digest(evidence):
    import hashlib
    return hashlib.sha256(json.dumps(evidence, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def latest_source_evidence(envelope):
    """Return the last immutable facts with their verified latest observation.

    The refresh is bound to the exact last immutable row digest. It cannot
    refresh different facts or replace the original source observation.
    """
    rows = envelope.get("observations", [])
    if not rows:
        return {}
    row = rows[-1]
    evidence = dict(row.get("evidence") or {})
    refresh = envelope.get("latest_confirmation") or {}
    stamp = _instant(refresh.get("observed_at_source"))
    prior = _instant(evidence.get("observed_at_source"))
    if (stamp and prior and stamp >= prior
            and refresh.get("sha256") == _digest(evidence)):
        evidence["observed_at_source"] = refresh["observed_at_source"]
    return evidence


def append_source_evidence(existing, evidence):
    """Preserve fact revisions; same-fact reads refresh a digest-bound watermark.

    Legacy timestamp-only rows remain immutable. Count consecutive fact changes
    for the existing 20-revision ceiling, rather than consuming it on each scan.
    A later A->B->A is a new revision; a delayed old observation is not.
    """
    import warnings
    if existing is None:
        existing = {"schema_version": 1, "observations": []}
    if not isinstance(existing, dict) or existing.get("schema_version") != 1 or not isinstance(existing.get("observations"), list):
        warnings.warn("ETS evidence envelope invalid; preservation held", RuntimeWarning)
        return existing
    rows = existing["observations"]
    if any(not isinstance(row, dict) or not isinstance(row.get("evidence"), dict)
           or any(row["evidence"].get(k) != evidence.get(k) for k in ("service_id", "invoice_id", "invoice_number", "service_internal_id", "invoice_service_id", "ets_shop_id"))
           for row in rows):
        warnings.warn("ETS evidence source identity mismatch; preservation held", RuntimeWarning)
        return existing
    current = latest_source_evidence(existing)
    stamp, prior = _instant(evidence.get("observed_at_source")), _instant(current.get("observed_at_source"))
    failed = _instant(existing.get("source_read_unavailable_at"))
    capacity_at = _instant(existing.get("revision_capacity_observed_at"))
    if capacity_at and (not failed or capacity_at > failed):
        failed = capacity_at
    if rows and ((prior and (not stamp or stamp <= prior)) or (failed and (not stamp or stamp <= failed))):
        return existing
    if rows and _facts(rows[-1]["evidence"]) == _facts(evidence):
        if not stamp:
            return existing
        updated = dict(existing, latest_confirmation={"sha256": _digest(rows[-1]["evidence"]),
                                                       "observed_at_source": evidence["observed_at_source"]})
        updated.pop("source_read_unavailable_at", None)
        # A capacity hold means a changed revision was not retained. Only a
        # newer complete source read matching the retained facts can clear it.
        updated.pop("revision_capacity_exceeded", None)
        updated.pop("revision_capacity_observed_at", None)
        return updated
    if rows and not stamp and any(row.get("sha256") == _digest(evidence) for row in rows):
        return existing  # old pre-timestamp import replay has no ordering proof
    revisions = sum(index == 0 or _facts(row["evidence"]) != _facts(rows[index - 1]["evidence"])
                    for index, row in enumerate(rows))
    if revisions >= 20 or len(rows) >= 39:
        warnings.warn("ETS evidence revision capacity reached; preservation held", RuntimeWarning)
        return dict(existing, revision_capacity_exceeded=True,
                    revision_capacity_observed_at=evidence.get("observed_at_source"))
    return {"schema_version": 1, "observations": [*rows, {"sha256": _digest(evidence), "evidence": evidence}]}
