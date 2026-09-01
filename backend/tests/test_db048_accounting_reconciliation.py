from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.core.config import settings
from app.db.models.customer import Customer
from app.db.models.invoice import Invoice, InvoiceStatus
from app.db.models.invoice_settlement import (
    CustomerCreditEntry,
    InvoicePaymentAttempt,
    InvoiceSettlement,
    PaymentAccountingLink,
    PaymentOverpayment,
    PaymentRefund,
    ProviderSettlementBatch,
    ProviderSettlementEntry,
    TenantPaymentProviderConfiguration,
)
from app.db.models.provider_outbox import ProviderOutboxEvent, ProviderOutboxStatus
from app.db.models.quickbooks_connection import QuickBooksConnection
from app.db.models.repair_order import RepairOrder, RepairOrderStatus
from app.db.models.tenant import Tenant
from app.db.models.user import User, UserRole
from app.db.models.vehicle import Vehicle
from app.api.v1.endpoints.invoice_settlements import retry_payout_reconciliation
from app.services.db048_accounting_reconciliation import (
    CREDIT_ACCOUNTING_EVENT,
    DB048ReconciliationError,
    _book_stripe_payout_batch,
    _payment_lines_with_delta,
    _project_accounting_dead_letter,
    _qbo_request_id,
    db048_qbo_adjustment_payloads,
    db048_qbo_credit_application_payload,
    db048_qbo_invoice_payload,
    db048_qbo_overpayment_refund_payload,
    db048_qbo_payment_payload,
    db048_qbo_unapplied_payment_payload,
    finalize_provider_refund,
    process_due_db048_outbox_events,
    reconcile_stripe_payout,
    stripe_payout_equation,
    sync_db048_payment,
    sync_db048_credit_application,
    sync_db048_refund,
    sync_db048_reversal,
)
from app.services.invoice_settlement_service import (
    SettlementDomainError,
    bind_settlement_accounting_realm,
)


def _invoice(*, principal: Decimal = Decimal("100.00")) -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid4(),
        invoice_number="INV-DB048-1001",
        created_at=datetime(2026, 8, 30, 12, 0, tzinfo=timezone.utc),
        due_date=datetime(2026, 9, 29, 12, 0, tzinfo=timezone.utc),
        subtotal=principal,
        tax_amount=Decimal("0.00"),
        service_fee_amount=Decimal("3.15"),
        total_amount=principal + Decimal("3.15"),
        tenant=SimpleNamespace(name="DB048 Garage"),
    )


def _payment(number: str, amount: Decimal) -> SimpleNamespace:
    return SimpleNamespace(
        payment_number=number,
        amount=amount,
        invoice_payment_attempt_id=uuid4(),
    )


def test_canonical_qbo_invoice_contains_principal_only() -> None:
    invoice = _invoice()

    payload = db048_qbo_invoice_payload(
        invoice=invoice,
        qbo_customer_id="qbo-customer-1",
        qbo_item_id="qbo-item-1",
        principal_total=Decimal("100.00"),
    )

    assert payload["DocNumber"] == invoice.invoice_number
    assert payload["CustomerRef"] == {"value": "qbo-customer-1"}
    assert payload["Line"] == [
        {
            "Amount": 100.0,
            "Description": "DB048 Garage invoice INV-DB048-1001",
            "DetailType": "SalesItemLineDetail",
            "SalesItemLineDetail": {
                "ItemRef": {"value": "qbo-item-1"},
                "Qty": 1,
                "UnitPrice": 100.0,
            },
        }
    ]
    assert payload["Line"][0]["Amount"] != float(invoice.total_amount)
    assert "principal-only A/R" in payload["PrivateNote"]


def test_multiple_qbo_payments_link_to_one_invoice_and_sum_principal() -> None:
    invoice = _invoice()
    payments = [
        db048_qbo_payment_payload(
            payment=_payment("PAY-CARD-40", Decimal("40.00")),
            invoice=invoice,
            qbo_customer_id="qbo-customer-1",
            qbo_invoice_id="qbo-invoice-1",
            principal_amount=Decimal("40.00"),
            deposit_account="Stripe Clearing",
        ),
        db048_qbo_payment_payload(
            payment=_payment("PAY-ZELLE-60", Decimal("60.00")),
            invoice=invoice,
            qbo_customer_id="qbo-customer-1",
            qbo_invoice_id="qbo-invoice-1",
            principal_amount=Decimal("60.00"),
            deposit_account="Zelle Clearing",
        ),
    ]

    assert sum(Decimal(str(payload["TotalAmt"])) for payload in payments) == Decimal("100.00")
    assert [payload["DepositToAccountRef"]["value"] for payload in payments] == [
        "Stripe Clearing",
        "Zelle Clearing",
    ]
    for payload in payments:
        assert payload["Line"][0]["Amount"] == payload["TotalAmt"]
        assert payload["Line"][0]["LinkedTxn"] == [
            {"TxnId": "qbo-invoice-1", "TxnType": "Invoice"}
        ]


def test_card_fee_tax_is_separate_and_processor_expense_waits_for_payout_evidence() -> None:
    attempt = SimpleNamespace(
        provider="stripe_connect",
        card_fee_amount=Decimal("3.00"),
        card_fee_tax_amount=Decimal("0.15"),
        applied_card_fee_amount=Decimal("3.00"),
        applied_card_fee_tax_amount=Decimal("0.15"),
        processor_fee_amount=Decimal("2.75"),
    )

    payloads = db048_qbo_adjustment_payloads(
        attempt=attempt,
        payment=_payment("PAY-CARD-100", Decimal("100.00")),
        mappings={
            "stripe_clearing_account": "Stripe Clearing",
            "card_fee_income_account": "Card Fee Income",
            "sales_tax_liability_account": "Sales Tax Payable",
            "processor_fee_expense_account": "Processor Fees",
        },
    )

    assert [document_number for document_number, _payload in payloads] == [
        "F-PAY-CARD-100",
    ]
    fee_lines = payloads[0][1]["Line"]
    assert [(line["Amount"], line["JournalEntryLineDetail"]["PostingType"]) for line in fee_lines] == [
        (3.15, "Debit"),
        (3.0, "Credit"),
        (0.15, "Credit"),
    ]
    assert [line["JournalEntryLineDetail"]["AccountRef"]["value"] for line in fee_lines] == [
        "Stripe Clearing",
        "Card Fee Income",
        "Sales Tax Payable",
    ]
    # The attempt snapshot is not authoritative settlement evidence for the
    # processor fee. It is booked exactly once from Stripe balance/payout data.
    assert attempt.processor_fee_amount == Decimal("2.75")


@pytest.mark.asyncio
async def test_zero_applied_late_card_success_skips_qbo_ar_and_books_full_gross_unapplied(
    monkeypatch,
) -> None:
    calls: list[tuple[str, str, dict | None]] = []

    async def fake_ensure(**_kwargs):
        return "qbo-customer-1", "qbo-invoice-1"

    async def fake_query(_connection, _query_text):
        if "from Account" in _query_text:
            return [{"Id": "qbo-ar"}]
        return []

    async def fake_request(_connection, method: str, path: str, json=None, params=None):
        calls.append((method, path, json))
        if method == "POST" and path == "payment":
            return {"Payment": {"Id": "qbo-unapplied-full-gross"}}
        if method == "POST" and path == "journalentry":
            return {"JournalEntry": {"Id": "qbo-unearned-surcharge"}}
        raise AssertionError(f"Unexpected QBO call: {method} {path}")

    monkeypatch.setattr(
        "app.services.db048_accounting_reconciliation._ensure_db048_qbo_invoice",
        fake_ensure,
    )
    monkeypatch.setattr(
        "app.services.db048_accounting_reconciliation._query",
        fake_query,
    )
    monkeypatch.setattr(
        "app.services.db048_accounting_reconciliation._request",
        fake_request,
    )
    payment = SimpleNamespace(
        invoice_payment_attempt_id=uuid4(),
        payment_number="PAY-LATE-100",
        quickbooks_payment_id=None,
        quickbooks_reconciled_at=None,
        quickbooks_sync_error=None,
    )
    link = SimpleNamespace(
        account_mapping_snapshot={
            "stripe_clearing_account": "Stripe Clearing",
            "card_fee_income_account": "Card Fee Income",
            "sales_tax_liability_account": "Sales Tax Payable",
            "processor_fee_expense_account": "Processor Fees",
        },
        provider_deposit_id=None,
    )
    envelope = SimpleNamespace(
        settlement=SimpleNamespace(principal_total=Decimal("100.00")),
        connection=SimpleNamespace(),
        invoice=_invoice(),
        customer=SimpleNamespace(),
        payment=payment,
        link=link,
        attempt=SimpleNamespace(
            id=payment.invoice_payment_attempt_id,
            provider="stripe_connect",
            rail="card",
            provider_charge_amount=Decimal("103.15"),
            received_amount=Decimal("100.00"),
            principal_amount=Decimal("100.00"),
            applied_principal_amount=Decimal("0.00"),
            unapplied_amount=Decimal("103.15"),
            card_fee_amount=Decimal("3.00"),
            card_fee_tax_amount=Decimal("0.15"),
            applied_card_fee_amount=Decimal("0.00"),
            applied_card_fee_tax_amount=Decimal("0.00"),
            processor_fee_amount=Decimal("0.00"),
        ),
    )

    provider_object_id = await sync_db048_payment(envelope)

    assert provider_object_id == "qbo-unapplied-full-gross"
    assert payment.quickbooks_payment_id == "qbo-unapplied-full-gross"
    assert link.provider_deposit_id == "qbo-unapplied-full-gross"
    assert calls[0] == (
        "POST",
        "payment",
        {
            "CustomerRef": {"value": "qbo-customer-1"},
            "TotalAmt": 100.0,
            "PaymentRefNum": "PAY-LATE-100",
            "DepositToAccountRef": {"value": "Stripe Clearing"},
            "PrivateNote": (
                f"DB048 Garage invoice INV-DB048-1001 DB-048 attempt="
                f"{payment.invoice_payment_attempt_id}; receipt=PAY-LATE-100; unapplied=100.00"
            ),
            "Line": [],
        },
    )
    assert calls[1][0:2] == ("POST", "journalentry")
    assert calls[1][2]["DocNumber"] == "UF-PAY-LATE-100"
    assert [line["Amount"] for line in calls[1][2]["Line"]] == [3.15, 3.15]
    assert db048_qbo_adjustment_payloads(
        attempt=envelope.attempt,
        payment=payment,
        mappings=link.account_mapping_snapshot,
    ) == []


def test_unapplied_overpayment_is_customer_payment_without_revenue_lines() -> None:
    payload = db048_qbo_unapplied_payment_payload(
        payment=_payment("PAY-OVER-20", Decimal("20.00")),
        qbo_customer_id="qbo-customer-1",
        amount=Decimal("20.00"),
        deposit_account="Stripe Clearing",
    )

    assert payload == {
        "CustomerRef": {"value": "qbo-customer-1"},
        "TotalAmt": 20.0,
        "PaymentRefNum": "U-PAY-OVER-20",
        "DepositToAccountRef": {"value": "Stripe Clearing"},
        "PrivateNote": "DB-048 unapplied customer overpayment pending refund or explicit credit consent",
        "Line": [],
    }
    serialized = repr(payload)
    assert "CreditMemo" not in serialized
    assert "SalesItemLineDetail" not in serialized
    assert "Income" not in serialized


def test_consented_credit_stays_the_same_unapplied_qbo_payment() -> None:
    unapplied = db048_qbo_unapplied_payment_payload(
        payment=_payment("PAY-CREDIT-100", Decimal("100.00")),
        qbo_customer_id="qbo-customer-1",
        amount=Decimal("100.00"),
        deposit_account="Stripe Clearing",
    )
    source_payment = {
        "Id": "qbo-unapplied-payment-1",
        "SyncToken": "4",
        **unapplied,
    }

    payload = db048_qbo_credit_application_payload(
        source_payment=source_payment,
        applications=[],
    )

    assert {
        key: payload[key]
        for key in (
            "Id",
            "SyncToken",
            "CustomerRef",
            "TotalAmt",
            "PaymentRefNum",
            "DepositToAccountRef",
        )
    } == {
        key: source_payment[key]
        for key in (
            "Id",
            "SyncToken",
            "CustomerRef",
            "TotalAmt",
            "PaymentRefNum",
            "DepositToAccountRef",
        )
    }
    assert payload["Line"] == []
    assert payload["PrivateNote"] == (
        "DB-048 credit-source=qbo-unapplied-payment-1; customer-approved "
        "store credit applications; no new receipt or revenue"
    )
    serialized = repr(payload).lower()
    assert "creditmemo" not in serialized
    assert "income" not in serialized
    assert "salesitemlinedetail" not in serialized


def test_credit_applications_aggregate_per_invoice_and_preserve_source_payment() -> None:
    source_payment = {
        "Id": "qbo-unapplied-payment-1",
        "SyncToken": "4",
        "CustomerRef": {"value": "qbo-customer-1"},
        "TotalAmt": 100.0,
        "PaymentRefNum": "U-PAY-CREDIT-100",
        "DepositToAccountRef": {"value": "Stripe Clearing"},
        "PrivateNote": "provider-owned note is not part of the required sparse update",
        "Line": [{"Amount": 1.0, "LinkedTxn": [{"TxnId": "stale", "TxnType": "Invoice"}]}],
    }
    applications = [
        ("qbo-invoice-b", Decimal("25.00")),
        ("qbo-invoice-a", Decimal("30.00")),
        ("qbo-invoice-a", Decimal("20.00")),
    ]

    payload = db048_qbo_credit_application_payload(
        source_payment=source_payment,
        applications=applications,
    )
    replay = db048_qbo_credit_application_payload(
        source_payment=source_payment,
        applications=applications,
    )

    assert payload == replay
    assert payload == {
        "Id": "qbo-unapplied-payment-1",
        "SyncToken": "4",
        "CustomerRef": {"value": "qbo-customer-1"},
        "TotalAmt": 100.0,
        "PaymentRefNum": "U-PAY-CREDIT-100",
        "DepositToAccountRef": {"value": "Stripe Clearing"},
        "PrivateNote": (
            "DB-048 credit-source=qbo-unapplied-payment-1; customer-approved "
            "store credit applications; no new receipt or revenue"
        ),
        "Line": [
            {
                "Amount": 50.0,
                "LinkedTxn": [{"TxnId": "qbo-invoice-a", "TxnType": "Invoice"}],
            },
            {
                "Amount": 25.0,
                "LinkedTxn": [{"TxnId": "qbo-invoice-b", "TxnType": "Invoice"}],
            },
        ],
    }
    assert sum(Decimal(str(line["Amount"])) for line in payload["Line"]) == Decimal("75.00")
    assert sum(Decimal(str(line["Amount"])) for line in payload["Line"]) <= Decimal(
        str(payload["TotalAmt"])
    )
    assert "stale" not in repr(payload)


def test_credit_application_can_consume_exact_source_ceiling() -> None:
    source_payment = {
        "Id": "qbo-unapplied-payment-1",
        "SyncToken": "4",
        "CustomerRef": {"value": "qbo-customer-1"},
        "TotalAmt": 100.0,
        "PaymentRefNum": "U-PAY-CREDIT-100",
        "DepositToAccountRef": {"value": "Stripe Clearing"},
        "Line": [],
    }

    payload = db048_qbo_credit_application_payload(
        source_payment=source_payment,
        applications=[("qbo-invoice-1", Decimal("100.00"))],
    )

    assert payload["TotalAmt"] == 100.0
    assert payload["Line"] == [
        {
            "Amount": 100.0,
            "LinkedTxn": [{"TxnId": "qbo-invoice-1", "TxnType": "Invoice"}],
        }
    ]


def test_credit_application_rejects_source_overallocation() -> None:
    source_payment = {
        "Id": "qbo-unapplied-payment-1",
        "SyncToken": "4",
        "CustomerRef": {"value": "qbo-customer-1"},
        "TotalAmt": 100.0,
        "PaymentRefNum": "U-PAY-CREDIT-100",
        "DepositToAccountRef": {"value": "Stripe Clearing"},
        "Line": [],
    }

    with pytest.raises(DB048ReconciliationError, match="exceed"):
        db048_qbo_credit_application_payload(
            source_payment=source_payment,
            applications=[
                ("qbo-invoice-1", Decimal("90.00")),
                ("qbo-invoice-2", Decimal("10.01")),
            ],
        )


@pytest.mark.parametrize("missing_key", ["Id", "SyncToken", "CustomerRef", "TotalAmt"])
def test_credit_application_rejects_missing_source_identity(missing_key: str) -> None:
    source_payment = {
        "Id": "qbo-unapplied-payment-1",
        "SyncToken": "4",
        "CustomerRef": {"value": "qbo-customer-1"},
        "TotalAmt": 100.0,
        "PaymentRefNum": "U-PAY-CREDIT-100",
        "DepositToAccountRef": {"value": "Stripe Clearing"},
        "Line": [],
    }
    source_payment.pop(missing_key)

    with pytest.raises(DB048ReconciliationError, match="identity"):
        db048_qbo_credit_application_payload(
            source_payment=source_payment,
            applications=[("qbo-invoice-1", Decimal("10.00"))],
        )


def test_overpayment_refund_reverses_customer_money_without_sales_income() -> None:
    payload = db048_qbo_overpayment_refund_payload(
        refund=SimpleNamespace(id=uuid4(), amount=Decimal("20.00")),
        qbo_customer_id="qbo-customer-1",
        receivable_account="Accounts Receivable",
        source_account="Stripe Clearing",
    )

    lines = payload["Line"]
    assert [(line["Amount"], line["JournalEntryLineDetail"]["PostingType"]) for line in lines] == [
        (20.0, "Debit"),
        (20.0, "Credit"),
    ]
    assert lines[0]["JournalEntryLineDetail"]["AccountRef"] == {
        "value": "Accounts Receivable"
    }
    assert lines[0]["JournalEntryLineDetail"]["Entity"] == {
        "Type": "Customer",
        "EntityRef": {"value": "qbo-customer-1"},
    }
    assert lines[1]["JournalEntryLineDetail"]["AccountRef"] == {
        "value": "Stripe Clearing"
    }
    assert "income" not in repr(payload).lower()
    assert "creditmemo" not in repr(payload).lower()


@pytest.mark.asyncio
async def test_qbo_reversal_voids_original_payment_to_reopen_accounts_receivable(monkeypatch) -> None:
    calls: list[tuple[str, str, dict | None, dict | None]] = []
    attempt_id = uuid4()
    financial_object_id = uuid4()

    async def fake_request(_connection, method: str, path: str, json=None, params=None):
        calls.append((method, path, json, params))
        if method == "GET":
            return {
                "Payment": {
                    "Id": "qbo-payment-1",
                    "SyncToken": "7",
                    "TxnStatus": "Paid",
                    "TotalAmt": 40.0,
                    "PaymentRefNum": "PAY-REVERSAL",
                    "PrivateNote": f"DB-048 attempt={attempt_id}",
                }
            }
        return {
            "Payment": {
                "Id": "qbo-payment-1",
                "SyncToken": "8",
                "TxnStatus": "Voided",
                "TotalAmt": 0.0,
            }
        }

    monkeypatch.setattr(
        "app.services.db048_accounting_reconciliation._request",
        fake_request,
    )
    envelope = SimpleNamespace(
        payment=SimpleNamespace(
            quickbooks_payment_id="qbo-payment-1",
            payment_number="PAY-REVERSAL",
        ),
        attempt=SimpleNamespace(id=attempt_id),
        link=SimpleNamespace(
            provider_deposit_id=None,
            financial_object_id=financial_object_id,
        ),
        connection=SimpleNamespace(realm_id="realm-1"),
    )

    result = await sync_db048_reversal(envelope)

    assert result == "qbo-payment-1"
    assert calls == [
        ("GET", "payment/qbo-payment-1", None, None),
        (
            "POST",
            "payment?operation=void",
            {"Id": "qbo-payment-1", "SyncToken": "7"},
            {
                "requestid": _qbo_request_id(
                    "reversal", f"{financial_object_id}:qbo-payment-1"
                )
            },
        ),
    ]


@pytest.mark.asyncio
async def test_qbo_reversal_also_voids_unapplied_payment_with_credit_links(monkeypatch) -> None:
    calls: list[tuple[str, str, dict | None, dict | None]] = []
    attempt_id = uuid4()
    financial_object_id = uuid4()

    async def fake_request(_connection, method: str, path: str, json=None, params=None):
        calls.append((method, path, json, params))
        payment_id = path.rsplit("/", 1)[-1] if method == "GET" else str(json["Id"])
        return {
            "Payment": {
                "Id": payment_id,
                "SyncToken": "4",
                "TxnStatus": "Paid" if method == "GET" else "Voided",
                "TotalAmt": 10.0 if method == "GET" else 0.0,
                "PaymentRefNum": "PAY-CREDIT",
                "PrivateNote": f"DB-048 attempt={attempt_id}",
            }
        }

    monkeypatch.setattr(
        "app.services.db048_accounting_reconciliation._request",
        fake_request,
    )
    envelope = SimpleNamespace(
        payment=SimpleNamespace(
            quickbooks_payment_id="qbo-principal-payment",
            payment_number="PAY-CREDIT",
        ),
        attempt=SimpleNamespace(id=attempt_id),
        link=SimpleNamespace(
            provider_deposit_id="qbo-unapplied-payment",
            financial_object_id=financial_object_id,
        ),
        connection=SimpleNamespace(realm_id="realm-1"),
    )

    result = await sync_db048_reversal(envelope)

    assert result == "qbo-principal-payment"
    assert [call[:2] for call in calls] == [
        ("GET", "payment/qbo-principal-payment"),
        ("POST", "payment?operation=void"),
        ("GET", "payment/qbo-unapplied-payment"),
        ("POST", "payment?operation=void"),
    ]
    assert calls[1][2]["Id"] == "qbo-principal-payment"
    assert calls[3][2]["Id"] == "qbo-unapplied-payment"


def test_stripe_payout_equation_reconciles_gross_fees_refunds_and_expense() -> None:
    assert stripe_payout_equation(
        gross_receipts=Decimal("1000.00"),
        customer_card_fees=Decimal("30.00"),
        card_fee_tax=Decimal("1.50"),
        refunds=Decimal("100.00"),
        disputes=Decimal("25.00"),
        processor_fees=Decimal("29.30"),
    ) == Decimal("877.20")


def test_dispute_payment_lines_reverse_and_restore_exact_credit_targets() -> None:
    source = {
        "Line": [
            {
                "Amount": 100.0,
                "LinkedTxn": [{"TxnId": "qbo-source", "TxnType": "Invoice"}],
            },
            {
                "Amount": 6.0,
                "LinkedTxn": [{"TxnId": "qbo-target-a", "TxnType": "Invoice"}],
            },
            {
                "Amount": 9.0,
                "LinkedTxn": [{"TxnId": "qbo-target-b", "TxnType": "Invoice"}],
            },
        ]
    }
    reversed_lines = _payment_lines_with_delta(
        source,
        source_invoice_id="qbo-source",
        source_principal_delta=Decimal("-100.00"),
        allocation_deltas={"qbo-target-a": Decimal("-6.00")},
    )
    assert reversed_lines == [{
        "Amount": 9.0,
        "LinkedTxn": [{"TxnId": "qbo-target-b", "TxnType": "Invoice"}],
    }]
    restored_lines = _payment_lines_with_delta(
        {"Line": reversed_lines},
        source_invoice_id="qbo-source",
        source_principal_delta=Decimal("100.00"),
        allocation_deltas={"qbo-target-a": Decimal("3.00")},
    )
    assert restored_lines == [
        {
            "Amount": 100.0,
            "LinkedTxn": [{"TxnId": "qbo-source", "TxnType": "Invoice"}],
        },
        {
            "Amount": 3.0,
            "LinkedTxn": [{"TxnId": "qbo-target-a", "TxnType": "Invoice"}],
        },
        {
            "Amount": 9.0,
            "LinkedTxn": [{"TxnId": "qbo-target-b", "TxnType": "Invoice"}],
        },
    ]


@pytest.mark.asyncio
async def test_refund_journal_has_stable_requestid_and_collision_fence(monkeypatch) -> None:
    refund_id = uuid4()
    calls: list[dict] = []

    async def fake_query(*_args, **_kwargs):
        return [{"Id": "Accounts Receivable"}]

    async def fake_customer(*_args, **_kwargs):
        return "qbo-customer"

    async def no_existing(*_args, **_kwargs):
        return None

    async def fake_request(_connection, method, path, json=None, params=None):
        calls.append({"method": method, "path": path, "json": json, "params": params})
        return {"JournalEntry": {"Id": "qbo-refund-je"}}

    monkeypatch.setattr(
        "app.services.db048_accounting_reconciliation._query", fake_query,
    )
    monkeypatch.setattr(
        "app.services.db048_accounting_reconciliation.ensure_customer",
        fake_customer,
    )
    monkeypatch.setattr(
        "app.services.db048_accounting_reconciliation._qbo_find_by_doc_number",
        no_existing,
    )
    monkeypatch.setattr(
        "app.services.db048_accounting_reconciliation._request", fake_request,
    )
    envelope = SimpleNamespace(
        refund=SimpleNamespace(id=refund_id, amount=Decimal("10.00")),
        link=SimpleNamespace(account_mapping_snapshot={
            "stripe_clearing_account": "Stripe Clearing",
        }),
        attempt=SimpleNamespace(provider="stripe_connect", rail="card"),
        connection=SimpleNamespace(realm_id="realm-refund"),
        customer=SimpleNamespace(id=uuid4()),
    )
    assert await sync_db048_refund(envelope) == "qbo-refund-je"
    assert calls[0]["params"] == {
        "requestid": _qbo_request_id("refund", refund_id)
    }
    assert f"refund={refund_id}" in calls[0]["json"]["PrivateNote"]

    async def unrelated_existing(*_args, **_kwargs):
        return {"Id": "qbo-unrelated", "PrivateNote": "unrelated"}

    monkeypatch.setattr(
        "app.services.db048_accounting_reconciliation._qbo_find_by_doc_number",
        unrelated_existing,
    )
    with pytest.raises(DB048ReconciliationError, match="collides"):
        await sync_db048_refund(envelope)
    assert len(calls) == 1


@pytest.mark.asyncio
async def test_credit_update_has_stable_requestid_and_source_collision_fence(
    db_session,
    monkeypatch,
) -> None:
    tenant = Tenant(name="Credit Fence Garage", slug=f"credit-fence-{uuid4().hex}")
    db_session.add(tenant)
    await db_session.flush()
    customer = Customer(
        tenant_id=tenant.id,
        first_name="Credit",
        last_name="Customer",
        email=f"credit-fence-{uuid4().hex}@example.com",
    )
    db_session.add(customer)
    await db_session.flush()
    vehicle = Vehicle(
        tenant_id=tenant.id,
        customer_id=customer.id,
        make="Volvo",
        model="VNL",
    )
    db_session.add(vehicle)
    await db_session.flush()
    order = RepairOrder(
        tenant_id=tenant.id,
        customer_id=customer.id,
        vehicle_id=vehicle.id,
        order_number=f"RO-{uuid4().hex[:10]}",
        status=RepairOrderStatus.INVOICED,
        total_parts_cost=Decimal("0"),
        total_labor_cost=Decimal("25"),
        total_cost=Decimal("25"),
    )
    db_session.add(order)
    await db_session.flush()
    invoice = Invoice(
        tenant_id=tenant.id,
        repair_order_id=order.id,
        invoice_number=f"INV-{uuid4().hex[:10]}",
        status=InvoiceStatus.SENT,
        subtotal=Decimal("25"),
        shop_supplies_amount=Decimal("0"),
        service_fee_amount=Decimal("0"),
        tax_amount=Decimal("0"),
        discount_amount=Decimal("0"),
        total_amount=Decimal("25"),
    )
    db_session.add(invoice)
    await db_session.flush()
    settlement = InvoiceSettlement(
        tenant_id=tenant.id,
        invoice_id=invoice.id,
        customer_id=customer.id,
        principal_total=Decimal("25"),
        max_card_fee=Decimal("0"),
        max_card_fee_tax=Decimal("0"),
        sales_tax_rate_snapshot=Decimal("0"),
        card_fee_rate_snapshot=Decimal("0"),
        confirmed_principal=Decimal("25"),
        active_pending_principal=Decimal("0"),
        unapplied_credit=Decimal("0"),
        refund_pending=Decimal("0"),
        state="paid",
        currency="USD",
        version=1,
        last_event_sequence=1,
        accounting_sync_status="accounting_sync_pending",
    )
    origin = CustomerCreditEntry(
        tenant_id=tenant.id,
        customer_id=customer.id,
        entry_type="issued",
        amount=Decimal("100"),
        actor_name_snapshot="Customer",
        idempotency_key="credit-fence-origin",
        request_hash="0" * 64,
    )
    db_session.add_all([settlement, origin])
    await db_session.flush()
    application = CustomerCreditEntry(
        tenant_id=tenant.id,
        customer_id=customer.id,
        entry_type="applied",
        amount=Decimal("25"),
        target_invoice_id=invoice.id,
        source_entry_id=origin.id,
        actor_name_snapshot="Customer",
        idempotency_key="credit-fence-application",
        request_hash="1" * 64,
    )
    db_session.add(application)
    await db_session.flush()
    source_attempt_id = uuid4()
    calls: list[dict] = []

    async def fake_request(_connection, method, path, json=None, params=None):
        calls.append({"method": method, "path": path, "json": json, "params": params})
        if method == "GET":
            return {"Payment": {
                "Id": "qbo-credit-source",
                "SyncToken": "4",
                "CustomerRef": {"value": "qbo-customer"},
                "TotalAmt": 100.0,
                "PaymentRefNum": "PAY-CREDIT-FENCE",
                "PrivateNote": f"DB-048 attempt={source_attempt_id}",
                "Line": [],
            }}
        return {"Payment": {"Id": "qbo-credit-source"}}

    async def fake_invoice(**_kwargs):
        return "qbo-customer", "qbo-target-invoice"

    monkeypatch.setattr(
        "app.services.db048_accounting_reconciliation._request", fake_request,
    )
    monkeypatch.setattr(
        "app.services.db048_accounting_reconciliation._ensure_db048_qbo_invoice",
        fake_invoice,
    )
    envelope = SimpleNamespace(
        config=SimpleNamespace(writer_strategy="dieselbridge"),
        tenant=tenant,
        origin=origin,
        source_accounting_link=SimpleNamespace(
            provider_deposit_id="qbo-credit-source",
        ),
        source_attempt=SimpleNamespace(
            id=source_attempt_id,
            received_amount=Decimal("100"),
            principal_amount=Decimal("100"),
        ),
        source_payment=SimpleNamespace(payment_number="PAY-CREDIT-FENCE"),
        connection=SimpleNamespace(realm_id="realm-credit"),
    )
    assert await sync_db048_credit_application(db_session, envelope) == "qbo-credit-source"
    assert calls[-1]["params"] == {
        "requestid": _qbo_request_id("credit", origin.id)
    }
    assert calls[-1]["json"]["Line"] == [{
        "Amount": 25.0,
        "LinkedTxn": [{"TxnId": "qbo-target-invoice", "TxnType": "Invoice"}],
    }]

    calls.clear()

    async def unrelated_source(_connection, method, path, json=None, params=None):
        return {"Payment": {
            "Id": "qbo-credit-source",
            "SyncToken": "4",
            "CustomerRef": {"value": "qbo-customer"},
            "TotalAmt": 100.0,
            "PaymentRefNum": "OTHER-PAYMENT",
            "PrivateNote": "unrelated",
            "Line": [],
        }}

    monkeypatch.setattr(
        "app.services.db048_accounting_reconciliation._request",
        unrelated_source,
    )
    with pytest.raises(DB048ReconciliationError, match="collides"):
        await sync_db048_credit_application(db_session, envelope)


@pytest.mark.asyncio
async def test_refund_failure_remains_retryable_then_succeeds_once(db_session) -> None:
    tenant = Tenant(name="DB048 Refund Garage", slug=f"db048-refund-{uuid4().hex}")
    db_session.add(tenant)
    await db_session.flush()
    customer = Customer(
        tenant_id=tenant.id,
        first_name="Refund",
        last_name="Customer",
        email=f"refund-{uuid4().hex}@example.com",
    )
    db_session.add(customer)
    await db_session.flush()
    invoice = Invoice(
        tenant_id=tenant.id,
        repair_order_id=uuid4(),
        invoice_number=f"INV-{uuid4().hex[:12]}",
        status=InvoiceStatus.PAID,
        subtotal=Decimal("100.00"),
        shop_supplies_amount=Decimal("0.00"),
        service_fee_amount=Decimal("0.00"),
        tax_amount=Decimal("0.00"),
        discount_amount=Decimal("0.00"),
        total_amount=Decimal("100.00"),
    )
    db_session.add(invoice)
    await db_session.flush()
    settlement = InvoiceSettlement(
        tenant_id=tenant.id,
        invoice_id=invoice.id,
        customer_id=customer.id,
        principal_total=Decimal("100.00"),
        max_card_fee=Decimal("0.00"),
        max_card_fee_tax=Decimal("0.00"),
        sales_tax_rate_snapshot=Decimal("0.00"),
        card_fee_rate_snapshot=Decimal("0.00"),
        currency="USD",
        confirmed_principal=Decimal("100.00"),
        active_pending_principal=Decimal("0.00"),
        unapplied_credit=Decimal("10.00"),
        refund_pending=Decimal("10.00"),
        state="overpayment_resolution",
        version=1,
        last_event_sequence=0,
    )
    db_session.add(settlement)
    await db_session.flush()
    attempt = InvoicePaymentAttempt(
        tenant_id=tenant.id,
        invoice_id=invoice.id,
        settlement_id=settlement.id,
        customer_id=customer.id,
        source="customer_portal",
        rail="card",
        provider="stripe_connect",
        state="confirmed",
        principal_amount=Decimal("100.00"),
        card_fee_amount=Decimal("0.00"),
        card_fee_tax_amount=Decimal("0.00"),
        provider_charge_amount=Decimal("110.00"),
        received_amount=Decimal("110.00"),
        applied_principal_amount=Decimal("100.00"),
        unapplied_amount=Decimal("10.00"),
        processor_fee_amount=Decimal("0.00"),
        currency="USD",
        provider_configuration_version=1,
        provider_account_id="acct_refund",
        provider_charge_id="ch_refund",
        actor_name_snapshot="Customer",
        subject_type="customer",
        subject_id=customer.id,
        idempotency_key="refund-attempt",
        request_hash="1" * 64,
        version=1,
    )
    db_session.add(attempt)
    await db_session.flush()
    overpayment = PaymentOverpayment(
        tenant_id=tenant.id,
        invoice_id=invoice.id,
        settlement_id=settlement.id,
        source_attempt_id=attempt.id,
        customer_id=customer.id,
        amount=Decimal("10.00"),
        state="refund_required",
    )
    db_session.add(overpayment)
    await db_session.flush()
    refund = PaymentRefund(
        tenant_id=tenant.id,
        invoice_id=invoice.id,
        source_attempt_id=attempt.id,
        overpayment_id=overpayment.id,
        amount=Decimal("10.00"),
        reason="Accidental provider overpayment",
        destination_rail="card",
        mode="automatic",
        state="pending",
            actor_name_snapshot="System",
            idempotency_key="refund-10",
            request_hash="3" * 64,
        )
    db_session.add_all([
        refund,
        TenantPaymentProviderConfiguration(
            tenant_id=tenant.id,
            version=1,
            selected_provider="stripe_connect",
            readiness_state="ready",
            is_active=True,
            actor_user_id=uuid4(),
            actor_name_snapshot="Garage Owner",
            provider_account_snapshot="acct_refund",
            writer_strategy="dieselbridge",
            idempotency_key="refund-provider-configuration",
            request_hash="2" * 64,
            stripe_clearing_account="Stripe Clearing",
        ),
    ])
    await db_session.commit()

    failed = await finalize_provider_refund(
        db_session,
        refund_id=refund.id,
        tenant_id=tenant.id,
        provider_account_id="acct_refund",
        provider_reference="re_refund",
        provider_event_id="evt_refund_failed",
        provider_status="failed",
    )
    await db_session.flush()

    assert failed.state == "failed"
    assert failed.last_error == "provider_refund_failed"
    assert overpayment.state == "refund_required"
    assert settlement.unapplied_credit == Decimal("10.00")
    assert settlement.refund_pending == Decimal("10.00")
    assert await db_session.scalar(select(func.count()).select_from(PaymentAccountingLink)) == 0

    succeeded = await finalize_provider_refund(
        db_session,
        refund_id=refund.id,
        tenant_id=tenant.id,
        provider_account_id="acct_refund",
        provider_reference="re_refund",
        provider_event_id="evt_refund_succeeded",
        provider_status="succeeded",
    )
    await db_session.flush()
    replay = await finalize_provider_refund(
        db_session,
        refund_id=refund.id,
        tenant_id=tenant.id,
        provider_account_id="acct_refund",
        provider_reference="re_refund",
        provider_event_id="evt_refund_succeeded_replay",
        provider_status="succeeded",
    )
    await db_session.flush()

    assert succeeded.state == replay.state == "succeeded"
    assert succeeded.last_error is None
    assert overpayment.state == "refunded"
    assert settlement.unapplied_credit == Decimal("0.00")
    assert settlement.refund_pending == Decimal("0.00")
    assert await db_session.scalar(select(func.count()).select_from(PaymentAccountingLink)) == 1
    assert await db_session.scalar(
        select(func.count()).select_from(ProviderOutboxEvent).where(
            ProviderOutboxEvent.event_type == "invoice_refund.accounting_sync"
        )
    ) == 1


@pytest.mark.asyncio
async def test_credit_accounting_retry_and_dead_letter_remain_visible_without_duplicates(
    _db_engine,
    monkeypatch,
) -> None:
    factory = async_sessionmaker(_db_engine, expire_on_commit=False)
    async with factory() as db:
        tenant = Tenant(name="DB048 Credit Worker", slug=f"db048-worker-{uuid4().hex}")
        db.add(tenant)
        await db.flush()
        retry_event = ProviderOutboxEvent(
            tenant_id=tenant.id,
            event_type=CREDIT_ACCOUNTING_EVENT,
            aggregate_type="customer_credit_entry",
            aggregate_id=uuid4(),
            payload={"accounting_link_id": str(uuid4()), "credit_entry_id": str(uuid4())},
            idempotency_key="credit-worker-retry",
            status=ProviderOutboxStatus.PENDING.value,
            available_at=datetime.now(timezone.utc) - timedelta(seconds=1),
        )
        db.add(retry_event)
        await db.commit()
        retry_event_id = retry_event.id

    monkeypatch.setattr(settings, "PROVIDER_OUTBOX_MAX_ATTEMPTS", 3)
    delivery_attempts: dict = {}
    qbo_payment_objects: set[str] = set()
    terminal_event_id = None

    async def fake_loader(_db, event):
        return SimpleNamespace(event_id=event.id)

    async def fake_delivery(_db, envelope):
        delivery_attempts[envelope.event_id] = delivery_attempts.get(envelope.event_id, 0) + 1
        if envelope.event_id == terminal_event_id:
            raise DB048ReconciliationError("credit source mismatch")
        if delivery_attempts[envelope.event_id] == 1:
            raise DB048ReconciliationError("QuickBooks temporarily unavailable", retryable=True)
        qbo_payment_objects.add("qbo-unapplied-payment-1")
        return "qbo-unapplied-payment-1"

    monkeypatch.setattr(
        "app.services.db048_accounting_reconciliation.load_credit_accounting_envelope",
        fake_loader,
    )
    monkeypatch.setattr(
        "app.services.db048_accounting_reconciliation.deliver_credit_accounting_envelope",
        fake_delivery,
    )

    first = await process_due_db048_outbox_events(session_factory=factory, batch_size=10)
    assert first == {
        "claimed": 1, "succeeded": 0, "retried": 1, "dead": 0, "lease_lost": 0,
    }
    async with factory() as db:
        visible_retry = await db.get(ProviderOutboxEvent, retry_event_id)
        assert visible_retry.status == ProviderOutboxStatus.PENDING.value
        assert visible_retry.attempt_count == 1
        assert "temporarily unavailable" in visible_retry.last_error
        visible_retry.available_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        await db.commit()

    second = await process_due_db048_outbox_events(session_factory=factory, batch_size=10)
    assert second == {
        "claimed": 1, "succeeded": 1, "retried": 0, "dead": 0, "lease_lost": 0,
    }
    async with factory() as db:
        visible_success = await db.get(ProviderOutboxEvent, retry_event_id)
        assert visible_success.status == ProviderOutboxStatus.SUCCEEDED.value
        assert visible_success.attempt_count == 2
        assert visible_success.provider_message_id == "qbo-unapplied-payment-1"
        terminal_event = ProviderOutboxEvent(
            tenant_id=tenant.id,
            event_type=CREDIT_ACCOUNTING_EVENT,
            aggregate_type="customer_credit_entry",
            aggregate_id=uuid4(),
            payload={"accounting_link_id": str(uuid4()), "credit_entry_id": str(uuid4())},
            idempotency_key="credit-worker-dead",
            status=ProviderOutboxStatus.PENDING.value,
            available_at=datetime.now(timezone.utc) - timedelta(seconds=1),
        )
        db.add(terminal_event)
        await db.commit()
        terminal_event_id = terminal_event.id

    third = await process_due_db048_outbox_events(session_factory=factory, batch_size=10)
    assert third == {
        "claimed": 1, "succeeded": 0, "retried": 0, "dead": 1, "lease_lost": 0,
    }
    async with factory() as db:
        visible_dead = await db.get(ProviderOutboxEvent, terminal_event_id)
        assert visible_dead.status == ProviderOutboxStatus.DEAD.value
        assert visible_dead.attempt_count == 1
        assert "credit source mismatch" in visible_dead.last_error
        assert await db.scalar(select(func.count()).select_from(ProviderOutboxEvent)) == 2

    assert delivery_attempts == {retry_event_id: 2, terminal_event_id: 1}
    assert qbo_payment_objects == {"qbo-unapplied-payment-1"}


async def _tenant_with_stripe_configuration(
    db_session,
    *,
    account_id: str,
    qbo_realm: str | None = "realm-db048",
) -> Tenant:
    tenant = Tenant(name="DB048 Garage", slug=f"db048-{uuid4().hex}")
    db_session.add(tenant)
    await db_session.flush()
    db_session.add(TenantPaymentProviderConfiguration(
        tenant_id=tenant.id,
        version=1,
        selected_provider="stripe_connect",
        readiness_state="ready",
        is_active=True,
        actor_user_id=uuid4(),
        actor_name_snapshot="Garage Owner",
        provider_account_snapshot=account_id,
        qbo_realm_snapshot=qbo_realm,
        writer_strategy="dieselbridge",
        idempotency_key=f"provider-{uuid4().hex}",
        request_hash="0" * 64,
        stripe_clearing_account="Stripe Clearing",
        processor_fee_expense_account="Processor Fees",
        checking_account="Checking",
    ))
    await db_session.commit()
    return tenant


async def _payout_attempt(
    db_session,
    *,
    tenant: Tenant,
    account_id: str,
    gross: Decimal,
    configuration_version: int = 1,
) -> InvoicePaymentAttempt:
    attempt = InvoicePaymentAttempt(
        tenant_id=tenant.id,
        invoice_id=uuid4(),
        settlement_id=uuid4(),
        customer_id=uuid4(),
        source="staff",
        rail="card",
        provider="stripe_connect",
        state="confirmed",
        principal_amount=gross,
        card_fee_amount=Decimal("0.00"),
        card_fee_tax_amount=Decimal("0.00"),
        applied_card_fee_amount=Decimal("0.00"),
        applied_card_fee_tax_amount=Decimal("0.00"),
        provider_charge_amount=gross,
        received_amount=gross,
        applied_principal_amount=gross,
        unapplied_amount=Decimal("0.00"),
        processor_fee_amount=Decimal("0.00"),
        currency="USD",
        provider_configuration_version=configuration_version,
        provider_account_id=account_id,
        provider_intent_id=f"pi_{uuid4().hex}",
        provider_charge_id=f"ch_{uuid4().hex}",
        actor_name_snapshot="Garage Owner",
        subject_type="user",
        idempotency_key=f"attempt-{uuid4().hex}",
        request_hash="a" * 64,
        confirmed_at=datetime.now(timezone.utc),
    )
    db_session.add(attempt)
    await db_session.flush()
    return attempt


@pytest.mark.asyncio
async def test_provider_config_and_accounting_link_orm_identity_is_frozen(
    db_session,
) -> None:
    tenant = await _tenant_with_stripe_configuration(
        db_session, account_id="acct_orm_frozen", qbo_realm="realm-orm",
    )
    tenant_id = tenant.id
    config = await db_session.scalar(select(
        TenantPaymentProviderConfiguration
    ).where(TenantPaymentProviderConfiguration.tenant_id == tenant_id))
    config.qbo_realm_snapshot = "realm-tampered"
    with pytest.raises(ValueError, match="frozen fields are immutable"):
        await db_session.flush()
    await db_session.rollback()

    config = await db_session.scalar(select(
        TenantPaymentProviderConfiguration
    ).where(TenantPaymentProviderConfiguration.tenant_id == tenant_id))
    config.is_active = False
    config.deactivated_at = datetime.now(timezone.utc)
    await db_session.commit()

    link = PaymentAccountingLink(
        tenant_id=tenant_id,
        invoice_id=uuid4(),
        attempt_id=uuid4(),
        financial_object_type="invoice_payment",
        financial_object_id=uuid4(),
        operation_version=1,
        principal_amount_snapshot=Decimal("25.00"),
        gross_amount_snapshot=Decimal("25.75"),
        owning_writer="dieselbridge",
        account_mapping_snapshot={"stripe_clearing_account": "Stripe Clearing"},
        qbo_realm_snapshot="realm-orm",
        sync_state="pending",
    )
    db_session.add(link)
    await db_session.commit()
    link.sync_state = "synced"
    link.provider_object_id = "qbo-payment-1"
    await db_session.commit()
    link.account_mapping_snapshot = {"stripe_clearing_account": "Tampered"}
    with pytest.raises(ValueError, match="frozen fields are immutable"):
        await db_session.flush()


@pytest.mark.asyncio
async def test_settlement_realm_initial_bind_succeeds_then_is_orm_frozen(
    db_session,
) -> None:
    tenant = await _tenant_with_stripe_configuration(
        db_session, account_id="acct_settlement_frozen", qbo_realm="realm-frozen",
    )
    config = await db_session.scalar(select(
        TenantPaymentProviderConfiguration
    ).where(
        TenantPaymentProviderConfiguration.tenant_id == tenant.id,
        TenantPaymentProviderConfiguration.version == 1,
    ))
    settlement = InvoiceSettlement(
        tenant_id=tenant.id,
        invoice_id=uuid4(),
        customer_id=uuid4(),
        principal_total=Decimal("25.00"),
        max_card_fee=Decimal("0.00"),
        max_card_fee_tax=Decimal("0.00"),
        sales_tax_rate_snapshot=Decimal("0.00"),
        card_fee_rate_snapshot=Decimal("0.00"),
        currency="USD",
    )
    db_session.add(settlement)
    await db_session.flush()

    await bind_settlement_accounting_realm(
        db_session,
        settlement=settlement,
        config=config,
    )
    await db_session.flush()
    assert settlement.qbo_realm_snapshot == "realm-frozen"
    assert settlement.initial_provider_configuration_version == 1

    settlement.accounting_sync_status = "accounting_sync_pending"
    await db_session.flush()
    settlement.qbo_realm_snapshot = "realm-rebound"
    with pytest.raises(ValueError, match="accounting realm binding is immutable"):
        await db_session.flush()


@pytest.mark.asyncio
async def test_settlement_realm_bind_allows_only_realm_free_legacy_attempts(
    db_session,
) -> None:
    tenant = await _tenant_with_stripe_configuration(
        db_session,
        account_id="acct_legacy_realm",
        qbo_realm=None,
    )
    tenant_id = tenant.id
    legacy_config = await db_session.scalar(select(
        TenantPaymentProviderConfiguration
    ).where(
        TenantPaymentProviderConfiguration.tenant_id == tenant_id,
        TenantPaymentProviderConfiguration.version == 1,
    ))
    legacy_config.is_active = False
    legacy_config.deactivated_at = datetime.now(timezone.utc)
    connected_config = TenantPaymentProviderConfiguration(
        tenant_id=tenant_id,
        version=2,
        selected_provider="stripe_connect",
        readiness_state="ready",
        is_active=True,
        actor_user_id=uuid4(),
        actor_name_snapshot="Garage Owner",
        provider_account_snapshot="acct_legacy_realm",
        qbo_realm_snapshot="realm-connected",
        writer_strategy="dieselbridge",
        idempotency_key=f"provider-{uuid4().hex}",
        request_hash="1" * 64,
        stripe_clearing_account="Stripe Clearing",
        processor_fee_expense_account="Processor Fees",
        checking_account="Checking",
    )
    db_session.add(connected_config)

    legacy_settlement = InvoiceSettlement(
        tenant_id=tenant_id,
        invoice_id=uuid4(),
        customer_id=uuid4(),
        principal_total=Decimal("25.00"),
        max_card_fee=Decimal("0.00"),
        max_card_fee_tax=Decimal("0.00"),
        sales_tax_rate_snapshot=Decimal("0.00"),
        card_fee_rate_snapshot=Decimal("0.00"),
        currency="USD",
    )
    db_session.add(legacy_settlement)
    await db_session.flush()
    legacy_attempt = InvoicePaymentAttempt(
        tenant_id=tenant_id,
        invoice_id=legacy_settlement.invoice_id,
        settlement_id=legacy_settlement.id,
        customer_id=legacy_settlement.customer_id,
        source="backfill",
        rail="check",
        provider="manual",
        state="confirmed",
        principal_amount=Decimal("5.00"),
        provider_charge_amount=Decimal("5.00"),
        received_amount=Decimal("5.00"),
        applied_principal_amount=Decimal("5.00"),
        unapplied_amount=Decimal("0.00"),
        processor_fee_amount=Decimal("0.00"),
        currency="USD",
        provider_configuration_version=1,
        actor_name_snapshot="Legacy import",
        subject_type="backfill",
        idempotency_key=f"attempt-{uuid4().hex}",
        request_hash="2" * 64,
    )
    db_session.add(legacy_attempt)
    await db_session.flush()

    await bind_settlement_accounting_realm(
        db_session,
        settlement=legacy_settlement,
        config=connected_config,
    )
    await db_session.flush()
    assert legacy_settlement.qbo_realm_snapshot == "realm-connected"
    assert legacy_settlement.initial_provider_configuration_version == 2

    native_settlement = InvoiceSettlement(
        tenant_id=tenant_id,
        invoice_id=uuid4(),
        customer_id=uuid4(),
        principal_total=Decimal("25.00"),
        max_card_fee=Decimal("0.00"),
        max_card_fee_tax=Decimal("0.00"),
        sales_tax_rate_snapshot=Decimal("0.00"),
        card_fee_rate_snapshot=Decimal("0.00"),
        currency="USD",
    )
    db_session.add(native_settlement)
    await db_session.flush()
    native_attempt = InvoicePaymentAttempt(
        tenant_id=tenant_id,
        invoice_id=native_settlement.invoice_id,
        settlement_id=native_settlement.id,
        customer_id=native_settlement.customer_id,
        source="staff",
        rail="check",
        provider="manual",
        state="pending",
        principal_amount=Decimal("5.00"),
        provider_charge_amount=Decimal("5.00"),
        currency="USD",
        provider_configuration_version=1,
        actor_name_snapshot="Garage Owner",
        subject_type="user",
        idempotency_key=f"attempt-{uuid4().hex}",
        request_hash="3" * 64,
    )
    db_session.add(native_attempt)
    await db_session.flush()
    await bind_settlement_accounting_realm(
        db_session,
        settlement=native_settlement,
        config=connected_config,
    )
    with pytest.raises(ValueError, match="accounting realm binding is immutable"):
        await db_session.flush()


@pytest.mark.asyncio
async def test_stripe_payout_persists_match_mismatch_and_deduplicates(db_session) -> None:
    tenant = await _tenant_with_stripe_configuration(db_session, account_id="acct_db048")
    matched_attempt = await _payout_attempt(
        db_session, tenant=tenant, account_id="acct_db048", gross=Decimal("100.00"),
    )
    mismatch_attempt = await _payout_attempt(
        db_session, tenant=tenant, account_id="acct_db048", gross=Decimal("100.00"),
    )
    occurred_at = datetime(2026, 8, 30, 12, 0, tzinfo=timezone.utc)
    matched_entries = [
        {"id": "ch_1", "type": "charge", "amount": "100.00", "attempt_id": str(matched_attempt.id), "occurred_at": occurred_at},
        {"id": "fee_1", "type": "stripe_fee", "amount": "3.00", "attempt_id": str(matched_attempt.id), "occurred_at": occurred_at},
    ]

    matched = await reconcile_stripe_payout(
        db_session,
        tenant_id=tenant.id,
        provider_account_id="acct_db048",
        payout_id="po_matched",
        net_payout=Decimal("97.00"),
        entries=matched_entries,
    )
    mismatch = await reconcile_stripe_payout(
        db_session,
        tenant_id=tenant.id,
        provider_account_id="acct_db048",
        payout_id="po_mismatch",
        net_payout=Decimal("96.99"),
        entries=[
            {"id": "ch_2", "type": "charge", "amount": "100.00", "attempt_id": str(mismatch_attempt.id), "occurred_at": occurred_at},
            {"id": "fee_2", "type": "stripe_fee", "amount": "3.00", "attempt_id": str(mismatch_attempt.id), "occurred_at": occurred_at},
        ],
    )
    await db_session.flush()
    duplicate = await reconcile_stripe_payout(
        db_session,
        tenant_id=tenant.id,
        provider_account_id="acct_db048",
        payout_id="po_matched",
        net_payout=Decimal("97.00"),
        entries=matched_entries,
    )
    with pytest.raises(DB048ReconciliationError, match="immutable manifest"):
        await reconcile_stripe_payout(
            db_session,
            tenant_id=tenant.id,
            provider_account_id="acct_db048",
            payout_id="po_matched",
            net_payout=Decimal("1.00"),
            entries=matched_entries,
        )
    await db_session.flush()

    assert matched.reconciliation_state == "matched"
    assert matched.mismatch_reason is None
    assert mismatch.reconciliation_state == "mismatch"
    assert mismatch.mismatch_reason == "expected 97.00 got 96.99"
    assert duplicate.id == matched.id
    assert await db_session.scalar(select(func.count()).select_from(ProviderSettlementBatch)) == 2
    assert await db_session.scalar(select(func.count()).select_from(ProviderSettlementEntry)) == 4


@pytest.mark.asyncio
async def test_stripe_payout_rejects_foreign_provider_account(db_session) -> None:
    tenant = await _tenant_with_stripe_configuration(db_session, account_id="acct_owned")

    with pytest.raises(
        DB048ReconciliationError,
        match="Stripe payout account does not belong to this tenant",
    ):
        await reconcile_stripe_payout(
            db_session,
            tenant_id=tenant.id,
            provider_account_id="acct_foreign",
            payout_id="po_foreign",
            net_payout=Decimal("10.00"),
            entries=[{"id": "ch_foreign", "type": "charge", "amount": "10.00"}],
        )

    assert await db_session.scalar(select(func.count()).select_from(ProviderSettlementBatch)) == 0
    assert await db_session.scalar(select(func.count()).select_from(ProviderSettlementEntry)) == 0


@pytest.mark.asyncio
async def test_payout_booking_is_pinned_to_snapshotted_qbo_realm_before_io(
    db_session,
    monkeypatch,
) -> None:
    tenant = await _tenant_with_stripe_configuration(
        db_session,
        account_id="acct_realm_pin",
        qbo_realm="realm-original",
    )
    db_session.add(QuickBooksConnection(
        tenant_id=tenant.id,
        realm_id="realm-current",
        status="connected",
        scopes="com.intuit.quickbooks.accounting",
        encrypted_access_token="test",
    ))
    attempt = await _payout_attempt(
        db_session,
        tenant=tenant,
        account_id="acct_realm_pin",
        gross=Decimal("100.00"),
    )
    occurred_at = datetime(2026, 8, 30, 12, 0, tzinfo=timezone.utc)
    batch = await reconcile_stripe_payout(
        db_session,
        tenant_id=tenant.id,
        provider_account_id="acct_realm_pin",
        payout_id="po_realm_pin",
        net_payout=Decimal("97.00"),
        entries=[
            {"id": "ch_realm", "type": "charge", "amount": "100.00", "attempt_id": str(attempt.id), "occurred_at": occurred_at},
            {"id": "fee_realm", "type": "stripe_fee", "amount": "3.00", "attempt_id": str(attempt.id), "occurred_at": occurred_at},
        ],
    )
    provider_io = 0

    async def unexpected_lookup(*_args, **_kwargs):
        nonlocal provider_io
        provider_io += 1
        return None

    monkeypatch.setattr(
        "app.services.db048_accounting_reconciliation._qbo_find_by_doc_number",
        unexpected_lookup,
    )
    with pytest.raises(
        DB048ReconciliationError,
        match="accounting configuration is unavailable",
    ):
        await _book_stripe_payout_batch(db_session, batch=batch)
    assert provider_io == 0
    assert batch.qbo_realm_snapshot == "realm-original"


@pytest.mark.asyncio
async def test_payout_booking_has_stable_requestid_and_rejects_doc_collision(
    db_session,
    monkeypatch,
) -> None:
    tenant = await _tenant_with_stripe_configuration(
        db_session,
        account_id="acct_payout_fence",
        qbo_realm="realm-payout",
    )
    connection = QuickBooksConnection(
        tenant_id=tenant.id,
        realm_id="realm-payout",
        status="connected",
        scopes="com.intuit.quickbooks.accounting",
        encrypted_access_token="test",
    )
    db_session.add(connection)
    attempt = await _payout_attempt(
        db_session,
        tenant=tenant,
        account_id="acct_payout_fence",
        gross=Decimal("100.00"),
    )
    collision_attempt = await _payout_attempt(
        db_session,
        tenant=tenant,
        account_id="acct_payout_fence",
        gross=Decimal("10.00"),
    )
    occurred_at = datetime(2026, 8, 30, 12, 0, tzinfo=timezone.utc)
    batch = await reconcile_stripe_payout(
        db_session,
        tenant_id=tenant.id,
        provider_account_id="acct_payout_fence",
        payout_id="po_requestid",
        net_payout=Decimal("97.00"),
        entries=[
            {"id": "ch_requestid", "type": "charge", "amount": "100.00", "attempt_id": str(attempt.id), "occurred_at": occurred_at},
            {"id": "fee_requestid", "type": "stripe_fee", "amount": "3.00", "attempt_id": str(attempt.id), "occurred_at": occurred_at},
        ],
    )
    calls: list[dict] = []

    async def no_existing(*_args, **_kwargs):
        return None

    async def fake_request(_connection, method, path, json=None, params=None):
        calls.append({"method": method, "path": path, "json": json, "params": params})
        return {"JournalEntry": {"Id": "qbo-payout-je-1"}}

    monkeypatch.setattr(
        "app.services.db048_accounting_reconciliation._qbo_find_by_doc_number",
        no_existing,
    )
    monkeypatch.setattr(
        "app.services.db048_accounting_reconciliation._request",
        fake_request,
    )
    assert await _book_stripe_payout_batch(db_session, batch=batch) == "qbo-payout-je-1"
    assert calls[0]["params"] == {
        "requestid": _qbo_request_id("payout", batch.id)
    }
    assert f"payout={batch.provider_batch_id}" in calls[0]["json"]["PrivateNote"]

    collision = await reconcile_stripe_payout(
        db_session,
        tenant_id=tenant.id,
        provider_account_id="acct_payout_fence",
        payout_id="po_collision",
        net_payout=Decimal("10.00"),
        entries=[{"id": "ch_collision", "type": "charge", "amount": "10.00", "attempt_id": str(collision_attempt.id), "occurred_at": occurred_at}],
    )

    async def unrelated_existing(*_args, **_kwargs):
        return {"Id": "qbo-unrelated", "PrivateNote": "unrelated journal"}

    monkeypatch.setattr(
        "app.services.db048_accounting_reconciliation._qbo_find_by_doc_number",
        unrelated_existing,
    )
    with pytest.raises(DB048ReconciliationError, match="collides"):
        await _book_stripe_payout_batch(db_session, batch=collision)
    assert len(calls) == 1


@pytest.mark.asyncio
async def test_payout_books_same_realm_historical_configs_as_one_partitioned_journal(
    db_session,
    monkeypatch,
) -> None:
    tenant = await _tenant_with_stripe_configuration(
        db_session, account_id="acct_partitioned", qbo_realm="realm-shared",
    )
    config_v1 = await db_session.scalar(select(
        TenantPaymentProviderConfiguration
    ).where(
        TenantPaymentProviderConfiguration.tenant_id == tenant.id,
        TenantPaymentProviderConfiguration.version == 1,
    ))
    switched_at = datetime(2026, 8, 30, 13, 0, tzinfo=timezone.utc)
    config_v1.is_active = False
    config_v1.deactivated_at = switched_at
    await db_session.flush()
    db_session.add(TenantPaymentProviderConfiguration(
        tenant_id=tenant.id,
        version=2,
        selected_provider="stripe_connect",
        readiness_state="ready",
        is_active=True,
        effective_at=switched_at,
        actor_user_id=uuid4(),
        actor_name_snapshot="Garage Owner",
        provider_account_snapshot="acct_partitioned",
        qbo_realm_snapshot="realm-shared",
        writer_strategy="dieselbridge",
        idempotency_key=f"provider-{uuid4().hex}",
        request_hash="b" * 64,
        stripe_clearing_account="Stripe Clearing V2",
        processor_fee_expense_account="Processor Fees V2",
        checking_account="Checking",
    ))
    await db_session.flush()
    first = await _payout_attempt(
        db_session,
        tenant=tenant,
        account_id="acct_partitioned",
        gross=Decimal("100.00"),
        configuration_version=1,
    )
    second = await _payout_attempt(
        db_session,
        tenant=tenant,
        account_id="acct_partitioned",
        gross=Decimal("50.00"),
        configuration_version=2,
    )
    batch = await reconcile_stripe_payout(
        db_session,
        tenant_id=tenant.id,
        provider_account_id="acct_partitioned",
        payout_id="po_partitioned",
        net_payout=Decimal("145.50"),
        entries=[
            {"id": "ch_partition_v1", "type": "charge", "amount": "100.00", "attempt_id": str(first.id), "occurred_at": switched_at - timedelta(minutes=1)},
            {"id": "fee_partition_v1", "type": "stripe_fee", "amount": "3.00", "attempt_id": str(first.id), "occurred_at": switched_at - timedelta(minutes=1)},
            {"id": "ch_partition_v2", "type": "charge", "amount": "50.00", "attempt_id": str(second.id), "occurred_at": switched_at + timedelta(minutes=1)},
            {"id": "fee_partition_v2", "type": "stripe_fee", "amount": "1.50", "attempt_id": str(second.id), "occurred_at": switched_at + timedelta(minutes=1)},
        ],
    )
    db_session.add(QuickBooksConnection(
        tenant_id=tenant.id,
        realm_id="realm-shared",
        status="connected",
        scopes="com.intuit.quickbooks.accounting",
        encrypted_access_token="test",
    ))
    calls: list[dict] = []

    async def no_existing(*_args, **_kwargs):
        return None

    async def fake_request(_connection, method, path, json=None, params=None):
        calls.append({"json": json, "params": params})
        return {"JournalEntry": {"Id": "qbo-partitioned"}}

    monkeypatch.setattr(
        "app.services.db048_accounting_reconciliation._qbo_find_by_doc_number",
        no_existing,
    )
    monkeypatch.setattr(
        "app.services.db048_accounting_reconciliation._request", fake_request,
    )
    assert await _book_stripe_payout_batch(db_session, batch=batch) == "qbo-partitioned"
    lines = calls[0]["json"]["Line"]
    checking_lines = [
        line for line in lines
        if line["JournalEntryLineDetail"]["AccountRef"]["value"] == "Checking"
    ]
    assert len(checking_lines) == 1
    assert checking_lines[0]["Amount"] == 145.5
    accounts = {
        line["JournalEntryLineDetail"]["AccountRef"]["value"] for line in lines
    }
    assert {"Stripe Clearing", "Stripe Clearing V2"} <= accounts
    snapshots = list((await db_session.execute(select(
        ProviderSettlementEntry.provider_configuration_version,
        ProviderSettlementEntry.account_mapping_snapshot,
    ).where(ProviderSettlementEntry.batch_id == batch.id))).all())
    assert {row.provider_configuration_version for row in snapshots} == {1, 2}


@pytest.mark.asyncio
async def test_mixed_realm_payout_persists_manual_proof_and_performs_zero_qbo_io(
    db_session,
    monkeypatch,
) -> None:
    tenant = await _tenant_with_stripe_configuration(
        db_session, account_id="acct_mixed_realm", qbo_realm="realm-one",
    )
    config_v1 = await db_session.scalar(select(
        TenantPaymentProviderConfiguration
    ).where(TenantPaymentProviderConfiguration.tenant_id == tenant.id))
    switched_at = datetime(2026, 8, 30, 13, 0, tzinfo=timezone.utc)
    config_v1.is_active = False
    config_v1.deactivated_at = switched_at
    await db_session.flush()
    db_session.add(TenantPaymentProviderConfiguration(
        tenant_id=tenant.id,
        version=2,
        selected_provider="stripe_connect",
        readiness_state="ready",
        is_active=True,
        effective_at=switched_at,
        actor_user_id=uuid4(),
        actor_name_snapshot="Garage Owner",
        provider_account_snapshot="acct_mixed_realm",
        qbo_realm_snapshot="realm-two",
        writer_strategy="dieselbridge",
        idempotency_key=f"provider-{uuid4().hex}",
        request_hash="c" * 64,
        stripe_clearing_account="Stripe Clearing Two",
        processor_fee_expense_account="Processor Fees Two",
        checking_account="Checking Two",
    ))
    await db_session.flush()
    first = await _payout_attempt(
        db_session, tenant=tenant, account_id="acct_mixed_realm",
        gross=Decimal("40.00"), configuration_version=1,
    )
    second = await _payout_attempt(
        db_session, tenant=tenant, account_id="acct_mixed_realm",
        gross=Decimal("60.00"), configuration_version=2,
    )
    batch = await reconcile_stripe_payout(
        db_session,
        tenant_id=tenant.id,
        provider_account_id="acct_mixed_realm",
        payout_id="po_mixed_realm",
        net_payout=Decimal("100.00"),
        entries=[
            {"id": "ch_mixed_one", "type": "charge", "amount": "40.00", "attempt_id": str(first.id), "occurred_at": switched_at - timedelta(minutes=1)},
            {"id": "ch_mixed_two", "type": "charge", "amount": "60.00", "attempt_id": str(second.id), "occurred_at": switched_at + timedelta(minutes=1)},
        ],
    )
    provider_io = 0

    async def unexpected_provider_io(*_args, **_kwargs):
        nonlocal provider_io
        provider_io += 1
        return None

    monkeypatch.setattr(
        "app.services.db048_accounting_reconciliation._qbo_find_by_doc_number",
        unexpected_provider_io,
    )
    assert batch.reconciliation_state == "manual_reconciliation_required"
    assert batch.qbo_realm_snapshot is None
    with pytest.raises(DB048ReconciliationError, match="manual reconciliation"):
        await _book_stripe_payout_batch(db_session, batch=batch)
    assert provider_io == 0
    assert await db_session.scalar(select(func.count()).select_from(
        ProviderSettlementEntry,
    ).where(ProviderSettlementEntry.batch_id == batch.id)) == 2


@pytest.mark.asyncio
async def test_payout_dead_letter_is_visible_tenant_scoped_and_idempotently_retryable(
    db_session,
) -> None:
    tenant = await _tenant_with_stripe_configuration(
        db_session,
        account_id="acct_payout_dead",
        qbo_realm="realm-payout-dead",
    )
    owner = User(
        email=f"payout-owner-{uuid4().hex}@example.com",
        hashed_password="hash",
        first_name="Payout",
        last_name="Owner",
        role=UserRole.GARAGE_OWNER,
        tenant_id=tenant.id,
        is_active=True,
        is_verified=True,
    )
    db_session.add(owner)
    attempt = await _payout_attempt(
        db_session,
        tenant=tenant,
        account_id="acct_payout_dead",
        gross=Decimal("100.00"),
    )
    occurred_at = datetime(2026, 8, 30, 12, 0, tzinfo=timezone.utc)
    batch = await reconcile_stripe_payout(
        db_session,
        tenant_id=tenant.id,
        provider_account_id="acct_payout_dead",
        payout_id="po_dead",
        net_payout=Decimal("97.00"),
        entries=[
            {"id": "ch_dead", "type": "charge", "amount": "100.00", "attempt_id": str(attempt.id), "occurred_at": occurred_at},
            {"id": "fee_dead", "type": "stripe_fee", "amount": "3.00", "attempt_id": str(attempt.id), "occurred_at": occurred_at},
        ],
    )
    operation = ProviderOutboxEvent(
        tenant_id=tenant.id,
        event_type="stripe_payout.reconcile",
        aggregate_type="stripe_payout",
        aggregate_id=tenant.id,
        payload={
            "payout_id": "po_dead",
            "provider_account_id": "acct_payout_dead",
            "net_payout": "97.00",
        },
        idempotency_key="stripe-payout:acct_payout_dead:po_dead",
        status=ProviderOutboxStatus.DEAD.value,
        available_at=datetime.now(timezone.utc),
        completed_at=datetime.now(timezone.utc),
        last_error="QuickBooksAccountingError: provider unavailable",
    )
    db_session.add(operation)
    await db_session.flush()
    await _project_accounting_dead_letter(db_session, operation)
    assert batch.reconciliation_state == "accounting_failed"
    assert "provider unavailable" in batch.mismatch_reason

    result = await retry_payout_reconciliation(
        operation_id=operation.id,
        idempotency_header="retry-po-dead",
        db=db_session,
        current_user=owner,
    )
    assert result.operation_id == operation.id
    assert result.state == ProviderOutboxStatus.PENDING.value
    assert batch.reconciliation_state == "matched"
    replay = await retry_payout_reconciliation(
        operation_id=operation.id,
        idempotency_header="retry-po-dead",
        db=db_session,
        current_user=owner,
    )
    assert replay.state == ProviderOutboxStatus.PENDING.value
    assert await db_session.scalar(select(func.count()).select_from(
        ProviderOutboxEvent,
    ).where(
        ProviderOutboxEvent.event_type == "stripe_payout.retry_requested",
        ProviderOutboxEvent.idempotency_key == "stripe-payout-retry:retry-po-dead",
    )) == 1

    foreign_tenant = Tenant(name="Foreign Garage", slug=f"foreign-{uuid4().hex}")
    db_session.add(foreign_tenant)
    await db_session.flush()
    foreign_owner = User(
        email=f"foreign-owner-{uuid4().hex}@example.com",
        hashed_password="hash",
        first_name="Foreign",
        last_name="Owner",
        role=UserRole.GARAGE_OWNER,
        tenant_id=foreign_tenant.id,
        is_active=True,
        is_verified=True,
    )
    db_session.add(foreign_owner)
    await db_session.flush()
    with pytest.raises(SettlementDomainError) as error:
        await retry_payout_reconciliation(
            operation_id=operation.id,
            idempotency_header="foreign-retry",
            db=db_session,
            current_user=foreign_owner,
        )
    assert getattr(error.value, "code", None) == "invoice_not_found"
