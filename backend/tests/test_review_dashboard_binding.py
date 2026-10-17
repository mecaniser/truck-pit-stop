"""The operator CLI binds the reviewed manifest to complete source evidence."""

import hashlib
import json
from datetime import timedelta
from uuid import uuid4

import pytest
from app.schemas.dashboard_vehicle_binding import BindingManifest
from app.services.fleet_telemetry import now
from scripts.motive_sync.review_binding import verify_evidence


def proof():
    stamp = now()
    evidence = {
        "version": 1,
        "company_id": "KT123",
        "company_label": "Synthetic Fleet",
        "provider_vehicle_id": "123",
        "vin": None,
        "source_vin_state": "not_displayed",
        "company_verified_before": True,
        "company_verified_after": True,
        "summary_verified_before": True,
        "summary_verified_after": True,
        "before_read_at": (stamp - timedelta(seconds=10)).isoformat(),
        "after_read_at": stamp.isoformat(),
        "summary_before_sha256": "a" * 64,
        "summary_after_sha256": "b" * 64,
        "reader_sha256": "c" * 64,
    }
    manifest = BindingManifest(
        vehicle_id=uuid4(),
        fleet_customer_id=uuid4(),
        fleet_membership_id=uuid4(),
        source_company_id="KT123",
        source_company_label="Synthetic Fleet",
        provider_vehicle_id="123",
        placeholder_vin="PENDING-26",
        review_note="Reviewed synthetic before and after source snapshots",
        source_evidence_sha256="d" * 64,
        source_evidence_read_at=stamp,
        source_vin_state="not_displayed",
    )
    return evidence, manifest


def encoded(evidence, manifest):
    raw = json.dumps(evidence, sort_keys=True).encode()
    return raw, manifest.model_copy(
        update={"source_evidence_sha256": hashlib.sha256(raw).hexdigest()}
    )


def test_evidence_is_exactly_hashed_and_matches_review_manifest():
    evidence, manifest = proof()
    raw, manifest = encoded(evidence, manifest)
    verify_evidence(raw, manifest)
    with pytest.raises(ValueError, match="hash mismatch"):
        verify_evidence(raw + b" ", manifest)
    assert manifest.effective_to is None


@pytest.mark.parametrize(
    "changes",
    [
        {"company_id": "KT999"},
        {"company_label": "Other Fleet"},
        {"provider_vehicle_id": "124"},
        {"vin": "PENDING-26"},
        {"source_vin_state": "explicitly_empty"},
        {"summary_verified_after": False},
        {"company_verified_before": 1},
        {"reader_sha256": "not-a-hash"},
        {"summary_before_sha256": ""},
        {"summary_after_sha256": ""},
        {"after_read_at": "2020-01-01T00:00:00"},
        {"before_read_at": "2099-01-01T00:00:00+00:00"},
    ],
)
def test_incomplete_changed_or_untrusted_source_review_rejected(changes):
    evidence, manifest = proof()
    evidence.update(changes)
    raw, manifest = encoded(evidence, manifest)
    with pytest.raises(ValueError):
        verify_evidence(raw, manifest)


def collector_proof():
    from scripts.motive_sync.import_locations import time_value
    from tests.test_motive_driver_worker import document

    evidence, manifest = document(), proof()[1]
    row = evidence["drivers"][0]
    row.update(vin=None, source_vin_state="not_displayed", provider_vehicle_id="123")
    manifest = manifest.model_copy(
        update={"source_evidence_read_at": time_value(row["source_read_at"])}
    )
    return evidence, manifest


def test_untouched_final_collector_document_is_supported_source_evidence():
    evidence, manifest = collector_proof()
    raw, manifest = encoded(evidence, manifest)
    verify_evidence(raw, manifest)


@pytest.mark.parametrize(
    "change",
    [
        "company",
        "incomplete",
        "assignment",
        "provider",
        "vin",
        "state",
        "missing_proof",
        "read_time",
    ],
)
def test_collector_evidence_requires_verified_exact_vehicle_and_complete_source(change):
    evidence, manifest = collector_proof()
    row = evidence["drivers"][0]
    if change == "company":
        evidence["company_id"] = "KT999"
    if change == "incomplete":
        evidence["complete"] = False
    if change == "assignment":
        row["assignment_verified_after"] = False
    if change == "provider":
        row["provider_vehicle_id"] = "999"
    if change == "vin":
        row.update(vin="1FUJGLDR9CLBU2344", source_vin_state=None)
    if change == "state":
        row["source_vin_state"] = "explicitly_empty"
    if change == "missing_proof":
        row.pop("source_vin_state")
    if change == "read_time":
        manifest = manifest.model_copy(update={"source_evidence_read_at": now()})
    raw, manifest = encoded(evidence, manifest)
    with pytest.raises(ValueError):
        verify_evidence(raw, manifest)
