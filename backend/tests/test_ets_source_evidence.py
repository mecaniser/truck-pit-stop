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
    _preserve_source_evidence(cursor, "tenant", {"12%": {"sourceEvidence": source()}, "123": {}})
    cursor.execute.assert_not_called()


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
        db.execute("INSERT INTO invoices VALUES(?,?,?,?,?,?,?,?,?,?)", (key, tenant, src, None, status, None, "ETSINV-456", key, "2026-10-07", 100))

    class Cursor:
        def execute(self, sql, args):
            self.cursor = db.execute(sql.replace("%s", "?").replace("FOR UPDATE OF i", ""), [json.dumps(a.adapted) if hasattr(a, "adapted") else a for a in args])

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
    full = {"schema_version": 1, "observations": envelope["observations"] * 20}
    with pytest.warns(RuntimeWarning, match="capacity"):
        assert append_source_evidence(full, second) == full


def test_provider_identity_changes_are_held():
    from scripts.easytruck_sync.source_evidence import append_source_evidence
    first = normalize_source_evidence(source())
    envelope = append_source_evidence(None, first)
    changed = dict(first, invoice_id="another")
    with pytest.warns(RuntimeWarning, match="identity mismatch"):
        assert append_source_evidence(envelope, changed) == envelope
    cursor = Mock()
    _preserve_source_evidence(cursor, "tenant", {"124": {"invoiceNumber": "456", "sourceEvidence": source()}})
    cursor.execute.assert_not_called()
