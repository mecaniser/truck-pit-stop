from datetime import datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

import pytest

from scripts.easytruck_sync import import_to_truckpitstop as importer


class Cursor:
    def __init__(self, reads, writes):
        self.reads, self.writes, self.rows = reads, writes, []

    def execute(self, sql, args=None):
        self.writes.append((sql, args))
        if self.reads is not None:
            self.rows = self.reads(sql)

    def fetchall(self):
        return self.rows

    def close(self):
        pass


def run_import_plan(monkeypatch, tmp_path, *, source_invoice=True, sibling=False, existing=False, held=False, bad_source=False):
    tenant, customer, vehicle, order_id = uuid4(), uuid4(), uuid4(), uuid4()
    stamp = datetime(2026, 1, 1)
    existing_profile = dict(created_at=stamp, updated_at=stamp + timedelta(days=1))
    order = dict(order_number="ETS-9001-100", service_no="9001", ets_customer_id="100",
                 ets_vehicle_id="200", tenant_id=tenant, status="completed", description="PM service",
                 mileage=None, total_cost=Decimal("0.00"), labor_hours=Decimal("1.00"),
                 labor_rate=Decimal("0.00"), work_completed_at=stamp, source=importer.IMPORT_SOURCE)
    orders = [order]
    if sibling:
        orders.append({**order, "order_number": "ETS-9001-100-2", "description": "Other service",
                       "total_cost": Decimal("25.00"), "labor_rate": Decimal("25.00")})
    recs = dict(customers=[{"ets_external_id": "100", "tenant_id": tenant}],
                vehicles=[{"ets_external_id": "200", "ets_customer_id": "100"}], repair_orders=orders)
    data = tmp_path / "customers.json"
    data.write_text("[]")
    monkeypatch.setattr(importer, "DATA_FILE", data)
    monkeypatch.setattr(importer, "INVOICES_FILE", tmp_path / "invoices.json")
    monkeypatch.setattr(importer, "build_records", lambda *_: recs)
    monkeypatch.setenv("ETS_SHOP", "test-shop")
    invoice = source_invoice_fixture()
    invoice["laborHours"] = "1.25"
    if bad_source:
        invoice["total"] = "550.00"
    monkeypatch.setattr(importer, "_load_invoices", lambda: {"9001": invoice} if source_invoice else {})
    monkeypatch.setattr(importer, "_sync_payments_for_existing_invoices", lambda *_: None)
    monkeypatch.setattr(importer, "_preserve_source_evidence", lambda *_: None)
    invoice_calls = []

    def retained_invoice_writer(w, tenant_id, ro_id, number, service, invoices, known, stats, now):
        # Observe the existing creation path; no invoice or payment is created.
        invoice_calls.append(number)
        if service in invoices and not held:
            known.add("ETSINV-" + invoices[service]["invoiceNumber"])

    monkeypatch.setattr(importer, "_create_invoice_and_payments", retained_invoice_writer)

    def reads(sql):
        if "FROM customers" in sql:
            return [{"id": customer, "ets_external_id": "100", **existing_profile}]
        if "FROM vehicles " in sql:
            return [{"id": vehicle, "ets_external_id": "200", **existing_profile}]
        if "FROM repair_orders" in sql:
            return [{"id": order_id, "order_number": order["order_number"]}] if existing else []
        if "SELECT invoice_number" in sql:
            return [{"invoice_number": "ETSINV-8001"}] if existing else []
        if "SELECT DISTINCT repair_order_id" in sql:
            return [{"repair_order_id": order_id}] if existing else []
        return []

    read_calls, writes = [], []
    conn = SimpleNamespace(
        cursor=lambda **kw: Cursor(reads, read_calls) if kw else Cursor(None, writes),
        rollback=lambda: None,
    )
    stats = importer.resync(conn, tenant, commit=False)
    return writes, invoice_calls, stats


def test_new_source_invoice_keeps_labor_and_work_subtotal_consistent(monkeypatch, tmp_path):
    writes, _, _ = run_import_plan(monkeypatch, tmp_path)
    ro = next(args for sql, args in writes if "INSERT INTO repair_orders" in sql)
    labor = next(args for sql, args in writes if "INSERT INTO labor" in sql)
    assert ro[9:12] == (Decimal("339.52"), Decimal("150.00"), Decimal("489.52"))
    assert labor[4:7] == (Decimal("1.25"), Decimal("120.00"), Decimal("150.00"))
    assert not any("UPDATE" in sql or "INSERT INTO invoices" in sql or "INSERT INTO payments" in sql for sql, _ in writes)


def test_sibling_does_not_repeat_invoice_labor_or_parts(monkeypatch, tmp_path):
    writes, _, _ = run_import_plan(monkeypatch, tmp_path, sibling=True)
    rows = [args for sql, args in writes if "INSERT INTO repair_orders" in sql]
    assert rows[1][9:12] == (Decimal("0.00"), Decimal("25.00"), Decimal("25.00"))


def test_held_invoice_does_not_repeat_money_across_siblings(monkeypatch, tmp_path):
    writes, _, _ = run_import_plan(monkeypatch, tmp_path, sibling=True, held=True)
    rows = [args for sql, args in writes if "INSERT INTO repair_orders" in sql]
    assert rows[0][9:12] == (Decimal("339.52"), Decimal("150.00"), Decimal("489.52"))
    assert rows[1][9:12] == (Decimal("0.00"), Decimal("25.00"), Decimal("25.00"))


def test_disputed_source_breakdown_is_not_written_to_operational_rows(monkeypatch, tmp_path):
    writes, _, _ = run_import_plan(monkeypatch, tmp_path, sibling=True, bad_source=True)
    rows = [args for sql, args in writes if "INSERT INTO repair_orders" in sql]
    assert rows[0][9:12] == (Decimal("0.00"),) * 3
    assert rows[1][9:12] == (Decimal("0.00"), Decimal("25.00"), Decimal("25.00"))


def test_no_source_invoice_retains_history_fallback(monkeypatch, tmp_path):
    writes, _, _ = run_import_plan(monkeypatch, tmp_path, source_invoice=False, sibling=True)
    rows = [args for sql, args in writes if "INSERT INTO repair_orders" in sql]
    assert rows[0][9:12] == (Decimal("0.00"),) * 3
    assert rows[1][9:12] == (Decimal("0.00"), Decimal("25.00"), Decimal("25.00"))


def test_existing_imported_order_is_never_rewritten(monkeypatch, tmp_path):
    writes, invoice_calls, stats = run_import_plan(monkeypatch, tmp_path, existing=True)
    assert stats["ro_exists"] == 1
    assert writes == []
    assert invoice_calls == []


def source_invoice_fixture(balance="0.00"):
    def money(value):
        return {"amount": value, "currency": "USD"}

    allocated = str(Decimal("534.41") - Decimal(balance))
    return dict(invoiceNumber="8001", subtotal="494.02", tax="40.39", total="534.41",
        laborTotal="150.00", partsTotal="339.52", fees="4.50", discount="0",
        payments=[{"amount": allocated, "date": "10/17/2026"}],
        sourceEvidence=dict(schema_version=1, source="easy_truck_shop", service_id="9001",
            observed_at_source=datetime.now(timezone.utc).isoformat(),
            invoice_id="8001", invoice_number="8001", service_internal_id="source-service",
            invoice_service_id="source-service", ets_shop_id="test-shop", currency="USD",
            invoice_status="10" if balance == "0.00" else "5", total=money("534.41"),
            balance=money(balance), payment_lines_truncated=False,
            invoice_manifest={"complete": True, "evidence_kind": "verified_source_service_invoice_manifest",
                "service_internal_id": "source-service", "invoice_ids": ["8001"]},
            payment_lines=[{"id": "allocation-1", "amount": money(allocated),
                "payment": {"id": "payment-1", "status": "20", "type": "0", "provider": "0",
                    "canceled": False, "total": money(allocated), "credit_total": money("0"),
                    "unapplied_amount": money("0")}}]))


def test_source_financial_disagreement_holds_without_any_writer_call(monkeypatch):
    monkeypatch.setenv("ETS_SHOP", "test-shop")
    data = source_invoice_fixture()
    data["total"] = "550.00"
    writes, stats, known = [], {}, set()
    with pytest.warns(RuntimeWarning, match="financial_source_conflict"):
        importer._create_invoice_and_payments(Cursor(None, writes), uuid4(), uuid4(),
            "ETS-9001-100", "9001", {"9001": data}, known, stats, datetime.utcnow())
    assert writes == [] and known == set()
    assert stats == {"inv_financial_hold": 1}


@pytest.mark.parametrize("change,reason", [
    (lambda d: d.pop("sourceEvidence"), "source_evidence_missing"),
    (lambda d: d["sourceEvidence"].update(observed_at_source="not-a-time"), "source_observation_unverified"),
    (lambda d: d["sourceEvidence"].update(ets_shop_id="other-shop"), "source_identity_unverified"),
    (lambda d: d.update(subtotal="495.02"), "financial_source_conflict"),
    (lambda d: d.update(payments=[{"amount": "533.00", "date": "10/17/2026"}]), "source_payment_allocation_conflict"),
    (lambda d: d["sourceEvidence"]["payment_lines"][0]["payment"].update(canceled=True), "source_payment_state_unverified"),
])
def test_future_insert_inputs_hold_uncertain_source(monkeypatch, change, reason):
    monkeypatch.setenv("ETS_SHOP", "test-shop")
    data = source_invoice_fixture()
    change(data)
    assert importer._invoice_insert_hold(data, "9001") == reason


def test_exact_future_source_input_is_valid_but_one_cent_remaining_is_not_paid(monkeypatch):
    monkeypatch.setenv("ETS_SHOP", "test-shop")
    data = source_invoice_fixture(balance="0.01")
    assert importer._invoice_insert_hold(data, "9001") is None
    writes, stats = [], {"inv_ins": 0, "pay_ins": 0}
    importer._create_invoice_and_payments(Cursor(None, writes), uuid4(), uuid4(),
        "ETS-9001-100", "9001", {"9001": data}, set(), stats, datetime.utcnow())
    invoice = next(args for sql, args in writes if "INSERT INTO invoices" in sql)
    assert invoice[5] == "sent"
    assert invoice[11] == Decimal("534.41")
