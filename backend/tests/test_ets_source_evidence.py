from unittest.mock import Mock
import pytest
from scripts.easytruck_sync.source_evidence import normalize_source_evidence
from scripts.easytruck_sync.import_to_truckpitstop import _preserve_source_evidence


def source():
    return {"schema_version": 1, "source": "easy_truck_shop", "service_id": 123,
            "invoice_id": 34, "invoice_number": 456, "service_internal_id": 999, "invoice_service_id": 999, "completed_at_source": "2026-10-07T07:00:00.000Z",
            "payment_lines": [{"id": 56, "payment": {"id": 78,
                "date_source": "2026-10-07T07:00:00.000Z", "qb_reference": "123"}}]}


def test_retains_exact_source_not_settlement():
    value = source()
    value["settlement_semantics"] = "verified"
    value["secret"] = "not-retained"
    value["payment_lines"][0]["payment"]["token"] = "not-retained"
    out = normalize_source_evidence(value)
    assert out["service_id"] == "123"
    assert out["payment_lines"][0]["payment"]["id"] == "78"
    assert out["completed_at_source"] == "2026-10-07T07:00:00.000Z"
    assert out["settlement_semantics"] == "unverified"
    assert "not-retained" not in str(out)
    assert out["payment_lines"][0]["payment"]["date_semantics"] == "source_datetime_unverified"


@pytest.mark.parametrize("bad", [None, [], {}, {"schema_version": 2}, {"source": "native"}])
def test_rejects_invalid_source(bad):
    assert normalize_source_evidence(bad) is None


def test_bounded_and_dates_never_invented():
    value = source()
    value["completed_at_source"] = "2026-02-30T01:00:00Z"
    value["payment_lines"][0]["payment"]["date_source"] = "2026-10-07T07:00:00"
    out = normalize_source_evidence(value)
    assert out["completed_at_source"] is None
    assert out["payment_lines"][0]["payment"]["date_source"] == "2026-10-07T07:00:00"
    value["payment_lines"] *= 201
    assert normalize_source_evidence(value) is None



def test_missing_evidence_and_wildcard_service_cannot_write():
    cursor = Mock()
    cursor.fetchone.return_value = (True,)
    _preserve_source_evidence(cursor, "tenant", {"12%": {"sourceEvidence": source()}, "123": {}})
    assert cursor.execute.call_count == 1


def test_actual_storage_is_scoped_idempotent_and_financial_state_untouched():
    import sqlite3
    import json
    db = sqlite3.connect(":memory:")
    db.executescript("""
      CREATE TABLE invoices(id TEXT, tenant_id TEXT, source TEXT, deleted_at TEXT,
        status TEXT, ets_source_evidence TEXT, invoice_number TEXT, repair_order_id TEXT,
        paid_at TEXT, total_amount INTEGER);
      CREATE TABLE repair_orders(id TEXT, tenant_id TEXT, source TEXT, deleted_at TEXT, order_number TEXT);
    """)
    for key, tenant, src, status, svc in [
        ("valid", "tenant", "easy_truck_shop_import", "paid", "123"),
        ("foreign", "other", "easy_truck_shop_import", "paid", "123"),
        ("native", "tenant", "native", "paid", "123"),
        ("cancelled", "tenant", "easy_truck_shop_import", "cancelled", "123"),
        ("other-service", "tenant", "easy_truck_shop_import", "paid", "124"),
    ]:
        db.execute("INSERT INTO repair_orders VALUES(?,?,?,?,?)", (key, tenant, src, None, f"ETS-{svc}-789"))
        db.execute("INSERT INTO invoices VALUES(?,?,?,?,?,?,?,?,?,?)", (key, tenant, src, None, status, None, "ETSINV-457" if key == "cancelled" else "ETSINV-456", key, "2026-10-07", 100))

    class Cursor:
        def execute(self, sql, args=()):
            if "information_schema.columns" in sql:
                self.cursor = db.execute("SELECT 1")
                return
            self.cursor = db.execute(sql.replace("%s", "?").replace("FOR UPDATE OF i", ""), [json.dumps(a.adapted) if hasattr(a, "adapted") else a for a in args])

        def fetchone(self):
            return self.cursor.fetchone()

        def fetchall(self):
            return [(row[0], json.loads(row[1]) if row[1] else None) for row in self.cursor.fetchall()]

    batch = {"123": {"invoiceNumber": "456", "sourceEvidence": source()}}
    _preserve_source_evidence(Cursor(), "tenant", batch)
    before = db.execute("SELECT * FROM invoices ORDER BY id").fetchall()
    _preserve_source_evidence(Cursor(), "tenant", batch)
    assert db.execute("SELECT * FROM invoices ORDER BY id").fetchall() == before
    assert [r[0] for r in before if r[5] is not None] == ["valid"]
    assert all(r[-2:] == ("2026-10-07", 100) for r in before)


def test_revisioned_evidence_preserves_unpaid_then_paid_and_replay():
    from scripts.easytruck_sync.source_evidence import append_source_evidence
    first = normalize_source_evidence(source())
    first["payment_lines"] = []
    envelope = append_source_evidence(None, first)
    second = normalize_source_evidence(source())
    updated = append_source_evidence(envelope, second)
    assert len(updated["observations"]) == 2
    assert updated["observations"][0] == envelope["observations"][0]
    assert append_source_evidence(updated, first) == updated
    assert append_source_evidence(updated, second) == updated
    full = {"schema_version": 1, "observations": [
        {"evidence": dict(first, completed=index % 2 == 0)} for index in range(20)]}
    with pytest.warns(RuntimeWarning, match="capacity"):
        held = append_source_evidence(full, second)
        assert held["observations"] == full["observations"]
        assert held["revision_capacity_exceeded"] is True


def test_provider_identity_changes_are_held():
    from scripts.easytruck_sync.source_evidence import append_source_evidence
    first = normalize_source_evidence(source())
    envelope = append_source_evidence(None, first)
    changed = dict(first, invoice_id="another")
    with pytest.warns(RuntimeWarning, match="identity mismatch"):
        assert append_source_evidence(envelope, changed) == envelope
    cursor = Mock()
    cursor.fetchone.return_value = (True,)
    _preserve_source_evidence(cursor, "tenant", {"124": {"invoiceNumber": "456", "sourceEvidence": source()}})
    assert cursor.execute.call_count == 1


def test_missing_migration_defers_capture_without_financial_writes():
    cursor = Mock()
    cursor.fetchone.return_value = (False,)
    with pytest.warns(RuntimeWarning, match="migration unavailable"):
        _preserve_source_evidence(cursor, "tenant", {"123": {"invoiceNumber": "456", "sourceEvidence": source()}})
    assert cursor.execute.call_count == 1


def test_cancelled_source_observations_are_not_filtered_out():
    cursor = Mock()
    cursor.fetchone.return_value = (True,)
    cursor.fetchall.return_value = []
    _preserve_source_evidence(cursor, "tenant", {"123": {"invoiceNumber": "456", "sourceEvidence": source()}})
    query = cursor.execute.call_args_list[1].args[0]
    assert "status <> 'cancelled'" not in query


def test_failed_source_read_only_invalidates_previously_verified_service():
    from scripts.easytruck_sync.import_to_truckpitstop import _preserve_source_read_failures
    cursor = Mock()
    cursor.fetchone.return_value = (True,)
    prior = {"schema_version": 1, "observations": [{"evidence": {"service_id": "123"}}]}
    cursor.fetchall.return_value = [("invoice", prior)]
    _preserve_source_read_failures(cursor, "tenant", [{"serviceNo": "123", "observed_at_source": "2020-01-01T00:00:00Z"}])
    sql, params = cursor.execute.call_args.args
    assert sql.startswith("UPDATE invoices SET ets_source_evidence=")
    assert "paid_at" not in sql
    assert params[0].adapted["observations"] == prior["observations"]
    assert params[0].adapted["source_read_unavailable_at"] == "2020-01-01T00:00:00+00:00"


def test_refreshes_preserve_original_and_do_not_consume_capacity():
    from scripts.easytruck_sync.source_evidence import append_source_evidence, latest_source_evidence
    from datetime import datetime, timedelta, timezone
    first = dict(normalize_source_evidence(source()), observed_at_source="2020-01-01T00:00:00+00:00")
    envelope = append_source_evidence(None, first)
    original = envelope["observations"][:]
    for day in range(1, 80):
        stamp = (datetime(2020, 1, 1, tzinfo=timezone.utc) + timedelta(days=day)).isoformat()
        envelope = append_source_evidence(envelope, dict(first, observed_at_source=stamp))
    assert envelope["observations"] == original
    assert latest_source_evidence(envelope)["observed_at_source"] == stamp
    assert not envelope.get("revision_capacity_exceeded")


def test_new_return_to_prior_facts_is_not_old_replay():
    from scripts.easytruck_sync.source_evidence import append_source_evidence, latest_source_evidence
    first = dict(normalize_source_evidence(source()), observed_at_source="2020-01-01T00:00:00Z")
    second = dict(first, completed=True, observed_at_source="2020-01-02T00:00:00Z")
    third = dict(first, observed_at_source="2020-01-03T00:00:00Z")
    envelope = append_source_evidence(append_source_evidence(append_source_evidence(None, first), second), third)
    assert len(envelope["observations"]) == 3
    assert append_source_evidence(envelope, second) == envelope
    assert latest_source_evidence(envelope) == third


def test_legacy_twenty_refreshes_are_preserved_and_can_continue():
    from scripts.easytruck_sync.source_evidence import append_source_evidence, latest_source_evidence
    first = normalize_source_evidence(source())
    rows = [{"evidence": dict(first, observed_at_source=f"2020-01-{day:02}T00:00:00Z")} for day in range(1, 21)]
    legacy = {"schema_version": 1, "observations": rows}
    fresh = dict(first, observed_at_source="2020-01-21T00:00:00Z")
    envelope = append_source_evidence(legacy, fresh)
    assert envelope["observations"] == rows
    assert latest_source_evidence(envelope) == fresh
    changed = append_source_evidence(envelope, dict(fresh, completed=False, observed_at_source="2020-01-22T00:00:00Z"))
    assert len(changed["observations"]) == 21
    assert changed["observations"][:20] == rows


def test_old_success_cannot_clear_newer_failure_and_mismatched_digest_cannot_refresh():
    from scripts.easytruck_sync.source_evidence import append_source_evidence, latest_source_evidence
    first = dict(normalize_source_evidence(source()), observed_at_source="2020-01-01T00:00:00Z")
    envelope = append_source_evidence(None, first)
    envelope["source_read_unavailable_at"] = "2020-01-03T00:00:00Z"
    assert append_source_evidence(envelope, dict(first, observed_at_source="2020-01-02T00:00:00Z")) == envelope
    renewed = append_source_evidence(envelope, dict(first, observed_at_source="2020-01-04T00:00:00Z"))
    assert "source_read_unavailable_at" not in renewed
    renewed["latest_confirmation"]["sha256"] = "wrong"
    assert latest_source_evidence(renewed) == first


def test_capacity_hold_cannot_be_cleared_by_older_matching_read():
    from scripts.easytruck_sync.source_evidence import append_source_evidence
    first = normalize_source_evidence(source())
    rows = [{'evidence': dict(first, completed=index % 2 == 0, observed_at_source=f'2020-01-{index+1:02}T00:00:00Z')}
            for index in range(20)]
    original = {'schema_version': 1, 'observations': rows}
    with pytest.warns(RuntimeWarning, match='capacity'):
        held = append_source_evidence(original, dict(first, completed=True, observed_at_source='2020-01-25T00:00:00Z'))
    older = dict(first, completed=False, observed_at_source='2020-01-24T00:00:00Z')
    assert append_source_evidence(held, older) == held
    fresh = append_source_evidence(held, dict(older, observed_at_source='2020-01-26T00:00:00Z'))
    assert not fresh.get('revision_capacity_exceeded')
    assert fresh['observations'] == rows


def test_failure_older_than_confirmation_does_not_invalidate_source():
    from scripts.easytruck_sync.source_evidence import append_source_evidence
    from scripts.easytruck_sync.import_to_truckpitstop import _preserve_source_read_failures
    first = dict(normalize_source_evidence(source()), observed_at_source='2020-01-01T00:00:00Z')
    envelope = append_source_evidence(append_source_evidence(None, first), dict(first, observed_at_source='2020-01-03T00:00:00Z'))
    cursor = Mock()
    cursor.fetchone.return_value = (True,)
    cursor.fetchall.return_value = [('invoice', envelope)]
    _preserve_source_read_failures(cursor, 'tenant', [{'serviceNo': '123', 'observed_at_source': '2020-01-02T00:00:00Z'}])
    assert not any('UPDATE invoices' in call.args[0] for call in cursor.execute.call_args_list)


def test_older_failed_replay_cannot_erase_newer_failure_hold():
    from scripts.easytruck_sync.source_evidence import append_source_evidence
    from scripts.easytruck_sync.import_to_truckpitstop import _preserve_source_read_failures
    first = dict(normalize_source_evidence(source()), observed_at_source='2020-01-01T00:00:00Z')
    envelope = append_source_evidence(None, first)
    envelope['source_read_unavailable_at'] = '2020-01-05T00:00:00Z'
    cursor = Mock()
    cursor.fetchone.return_value = (True,)
    cursor.fetchall.return_value = [('invoice', envelope)]
    _preserve_source_read_failures(cursor, 'tenant', [{'serviceNo': '123', 'observed_at_source': '2020-01-03T00:00:00Z'}])
    assert not any('UPDATE invoices' in call.args[0] for call in cursor.execute.call_args_list)
    assert append_source_evidence(envelope, dict(first, observed_at_source='2020-01-04T00:00:00Z')) == envelope
    newer = append_source_evidence(envelope, dict(first, observed_at_source='2020-01-06T00:00:00Z'))
    assert 'source_read_unavailable_at' not in newer
