"""Canonical staff-verified Fleet instruments; no provider redemption or IO."""
from __future__ import annotations

import hashlib
import json

FLEET_PROVIDERS = {"EFS", "Comchek", "T-Chek", "Other"}


def _text(value, *, maximum, required=False):
    if value is not None and not isinstance(value, str):
        raise ValueError("Fleet instrument evidence must be text.")
    result = value.strip() if value else None
    if (required and not result) or (result and len(result) > maximum):
        raise ValueError("Fleet instrument evidence is missing or too long.")
    return result or None


def normalize_fleet_evidence(evidence):
    if not isinstance(evidence, dict):
        raise ValueError("Fleet provider and instrument reference are required.")
    result = dict(evidence)
    provider = _text(evidence.get("fleet_provider"), maximum=100, required=True)
    if provider not in FLEET_PROVIDERS:
        raise ValueError("Choose EFS, Comchek, T-Chek or Other provider.")
    name = _text(evidence.get("fleet_provider_name"), maximum=100, required=provider == "Other")
    if provider != "Other" and name:
        raise ValueError("A provider name is only used for Other provider.")
    if name and _identity_text(name) in {"efs", "efs / moneycode", "moneycode", "comchek", "t-chek", "tchek"}:
        raise ValueError("Select the named Fleet provider instead of Other.")
    reference = _text(evidence.get("reference"), maximum=255)
    number = _text(evidence.get("reference_number"), maximum=255)
    if reference and number and reference != number:
        raise ValueError("Fleet instrument reference aliases must agree.")
    number = number or reference
    if not number:
        raise ValueError("A Fleet instrument reference is required.")
    result.update(fleet_provider=provider, fleet_provider_name=name,
                  reference_number=number, reference=number,
                  authorization_number=_text(evidence.get("authorization_number"), maximum=255),
                  note=_text(evidence.get("note"), maximum=1000))
    return result


def _identity_text(value):
    return " ".join(value.casefold().split())


def fleet_provider_label(evidence):
    evidence = normalize_fleet_evidence(evidence)
    return evidence["fleet_provider_name"] if evidence["fleet_provider"] == "Other" else evidence["fleet_provider"]


def fleet_reference_fingerprint(evidence):
    evidence = normalize_fleet_evidence(evidence)
    identity = [_identity_text(fleet_provider_label(evidence)), _identity_text(evidence["reference_number"])]
    return hashlib.sha256(json.dumps(identity, separators=(",", ":")).encode()).hexdigest()
