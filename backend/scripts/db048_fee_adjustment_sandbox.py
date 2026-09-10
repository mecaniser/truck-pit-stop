"""DB-048 fee-tax/dispute/recovery acceptance, ACCOUNTING ONLY.

Default mode is GET-only preflight; --self-test performs no provider calls.
--execute permits only one new labelled sandbox customer, invoice and receipt,
then signed invoice and receipt adjustments on those exact returned IDs. No
charge API, existing-object adoption, cleanup, refresh or shared-domain writes.
Source OAuth is copied from a READ ONLY local transaction into disposable
SQLite. Stripe dispute events are synthetic local fixtures, NOT real disputes
or capture/refund evidence. Independent safety review must precede --execute.
"""
from __future__ import annotations

import argparse
import asyncio
from copy import deepcopy
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
import json
import os
from pathlib import Path
import re
import sys
from types import SimpleNamespace
from urllib.parse import urlsplit
from uuid import uuid4

from db048_gross_sandbox_acceptance import HOST, REALM, SafetyError, new_marker


def sanitized_faults(payload):
    """Never expose Detail, identifiers, echoed values or unknown messages."""
    messages = {
        "Invalid Reference Id", "Business Validation Error", "ValidationFault",
        "A business validation error has occurred while processing your request",
        "Invalid Number", "Invalid String", "Required param missing, need to supply the required value for the API",
        "Duplicate Document Number Error", "Stale Object Error", "Invalid ID",
        "AuthenticationFailed", "AuthorizationFailed", "Unsupported Operation",
        "Request has invalid or unsupported property", "Invalid TaxCode Reference Id",
    }
    fault = payload.get("Fault", {}) if isinstance(payload, dict) else {}
    errors = fault.get("Error", []) if isinstance(fault, dict) else []
    if not isinstance(errors, list):
        return []
    result = []
    for error in errors[:5]:
        if not isinstance(error, dict):
            continue
        code = str(error.get("code", ""))
        message = error.get("Message")
        result.append({"code": code if re.fullmatch(r"[0-9]{1,8}", code) else "redacted",
                       "message": message if isinstance(message, str) and message in messages else "Unrecognized provider message redacted"})
    return result


class WriteFence:
    def __init__(self, execute, marker, gross):
        self.execute, self.marker, self.gross = execute, marker, gross
        self.ids = {kind: set() for kind in ("customer", "invoice", "payment")}
        self.posts = []

    def check(self, method, resource, payload=None, params=None):
        if method == "GET":
            if resource.split("/")[0] not in {
                "query", "preferences", "companyinfo", "item", "account",
                "invoice", "payment", "taxcode", "taxrate",
            }:
                raise SafetyError("GET outside accounting acceptance")
            return
        if method != "POST" or not self.execute:
            raise SafetyError("Mutation requires explicit --execute")
        body = payload or {}
        if any(key in json.dumps(body) for key in ("ProcessPayment", "CreditCardPayment", "CreditCardInfo")):
            raise SafetyError("Payment processing forbidden")
        if set(params or {}) - {"requestid"}:
            raise SafetyError("Alternate query operation forbidden")
        if len(self.posts) >= 12:
            raise SafetyError("Write budget exhausted")
        kind = resource.split("?")[0]
        if resource == "customer":
            if body.get("Id") or self.ids[kind] or not str(body.get("DisplayName", "")).startswith(self.marker):
                raise SafetyError("Only one new labelled customer allowed")
            return
        if resource not in {"invoice", "invoice?operation=update", "payment", "payment?operation=update", "payment?operation=void"}:
            raise SafetyError("Accounting mutation outside frozen routes")
        updating = "?" in resource
        if updating:
            if str(body.get("Id")) not in self.ids[kind] or body.get("SyncToken") is None:
                raise SafetyError("Update requires this run's exact returned ID/token")
        elif body.get("Id") or self.ids[kind]:
            raise SafetyError("Only one new entity of each kind allowed")
        if resource == "payment?operation=void":
            if set(body) != {"Id", "SyncToken"}:
                raise SafetyError("Void payload outside scope")
            return
        if resource == "invoice?operation=update":
            if set(body) != {"Id", "SyncToken", "sparse", "Line", "TxnTaxDetail"} or body.get("sparse") is not True:
                raise SafetyError("Invoice update must be exact writer-owned sparse lines/tax")
            return
        if str((body.get("CustomerRef") or {}).get("value")) not in self.ids["customer"]:
            raise SafetyError("Entity must belong to newly created customer")
        if kind == "invoice":
            if body.get("DocNumber") != self.marker:
                raise SafetyError("Invoice marker changed")
            return
        total = Decimal(str(body.get("TotalAmt")))
        if total not in {Decimal(0), self.gross}:
            raise SafetyError("Receipt total outside frozen scenario")
        if str((body.get("DepositToAccountRef") or {}).get("value")) != "1150040000":
            raise SafetyError("Receipt clearing account changed")
        expected = [{"Amount": float(self.gross), "LinkedTxn": [
            {"TxnId": next(iter(self.ids["invoice"]), ""), "TxnType": "Invoice"}]}] if total else []
        if body.get("Line") != expected:
            raise SafetyError("Receipt allocation outside newly created invoice")

    def record(self, resource, response):
        kind = resource.split("?")[0]
        entity = response.get(kind.title()) or {}
        identifier = str(entity.get("Id") or "")
        if not identifier:
            raise SafetyError("Provider write returned no entity identity; stop")
        if "?" in resource and identifier not in self.ids[kind]:
            raise SafetyError("Provider update returned a foreign identity; stop")
        self.ids[kind].add(identifier)
        self.posts.append(resource)
        print(json.dumps({"sandbox_write": resource, "id": identifier, "total": entity.get("TotalAmt")}), flush=True)


def self_test():
    marker = new_marker()
    negative = [
        (False, "POST", "customer", {}), (True, "DELETE", "invoice/1", {}),
        (True, "POST", "charge", {}), (True, "POST", "journalentry", {}),
        (True, "POST", "customer", {"DisplayName": "Existing customer"}),
        (True, "POST", "invoice?operation=update", {"Id": "old", "SyncToken": "1"}),
        (True, "POST", "payment?operation=void", {"Id": "old", "SyncToken": "1"}),
        (True, "POST", "payment?operation=update", {"Id": "old", "SyncToken": "1"}),
        (True, "POST", "payment", {"ProcessPayment": False}),
        (True, "POST", "invoice", {"DocNumber": marker, "CustomerRef": {"value": "old"}}),
    ]
    for execute, method, route, payload in negative:
        try:
            WriteFence(execute, marker, Decimal("103.23")).check(method, route, payload)
        except SafetyError:
            continue
        raise AssertionError("Negative safety case allowed")
    fence = WriteFence(True, marker, Decimal("103.23"))
    fence.ids = {"customer": {"new-c"}, "invoice": {"new-i"}, "payment": {"new-p"}}
    fence.check("POST", "payment?operation=void", {"Id": "new-p", "SyncToken": "1"})
    fence.check("POST", "invoice?operation=update", {"Id": "new-i", "SyncToken": "1",
        "sparse": True, "Line": [], "TxnTaxDetail": {}})
    fence.check("GET", "taxcode/2")
    assert sanitized_faults({"Fault": {"Error": [{"code": "2500", "Message": "Invalid Reference Id",
        "Detail": "private customer and access token"}]}}) == [{"code": "2500", "message": "Invalid Reference Id"}]
    sanitized = sanitized_faults({"Fault": {"Error": [{"code": "secret", "Message": "private customer",
        "Detail": "private access token"}]}})
    assert "private" not in json.dumps(sanitized) and "secret" not in json.dumps(sanitized)
    assert len("Stripe " + new_reference()) == 21
    print(json.dumps({"self_test": "passed", "negative_cases": len(negative), "provider_calls": 0}))


def new_reference():
    # QBO PaymentRefNum retains only 21 characters including "Stripe ".
    return "S" + uuid4().hex[:13]


async def run(args):
    from sqlalchemy.engine import make_url
    source_url = os.environ.get("DB048_SOURCE_DATABASE_URL") or os.environ.get("DATABASE_URL", "")
    source = make_url(source_url)
    if source.database != "truckpitstop_db048" or source.host not in {"localhost", "127.0.0.1", "db", "postgres"}:
        raise SafetyError("Source must be local truckpitstop_db048")
    os.environ["DATABASE_URL"] = "sqlite+aiosqlite://"
    os.environ["QUICKBOOKS_ACCOUNTING_ENVIRONMENT"] = "sandbox"
    os.environ["QUICKBOOKS_PAYMENTS_ENVIRONMENT"] = "sandbox"
    backend = Path(__file__).resolve().parents[1]
    sys.path[:0] = [str(backend), str(backend / "tests")]
    import pytest
    import conftest
    import test_db048_invoice_settlements as fixture
    from sqlalchemy import select, text
    from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
    from app.core.config import settings
    from app.db.models.quickbooks_connection import QuickBooksConnection
    from app.db.models.invoice_settlement import PaymentAccountingLink, TenantPaymentProviderConfiguration
    from app.services import quickbooks_accounting_service as qbo
    from app.services import db048_accounting_reconciliation as r
    from app.services.invoice_settlement_service import get_or_create_settlement, create_attempt, confirm_attempt

    source_engine = create_async_engine(source_url)
    try:
        async with async_sessionmaker(source_engine)() as source_db:
            await source_db.execute(text("SET TRANSACTION READ ONLY"))
            row = (await source_db.execute(select(QuickBooksConnection).where(
                QuickBooksConnection.realm_id == REALM, QuickBooksConnection.status == "connected",
                QuickBooksConnection.deleted_at.is_(None)))).scalar_one()
            detached = SimpleNamespace(**{c.name: deepcopy(getattr(row, c.name)) for c in row.__table__.columns})
            await source_db.rollback()
    finally:
        await source_engine.dispose()
    if not detached.access_token_expires_at or detached.access_token_expires_at.replace(tzinfo=timezone.utc) <= datetime.now(timezone.utc):
        raise SafetyError("Refresh existing OAuth separately before acceptance")
    fee_tax = (Decimal("3") * args.tax_rate / 100).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    gross = Decimal("103") + fee_tax
    marker = new_marker()
    fence = WriteFence(args.execute, marker, gross)
    real_request = qbo._request

    async def guarded(connection, method, resource, **kwargs):
        if connection.realm_id != REALM or qbo.accounting_base_url() != HOST or settings.QUICKBOOKS_ACCOUNTING_ENVIRONMENT != "sandbox" or settings.QUICKBOOKS_PAYMENTS_ENVIRONMENT != "sandbox":
            raise SafetyError("Sandbox realm/host/environment mismatch")
        fence.check(method, resource, kwargs.get("json"), kwargs.get("params"))
        response = await real_request(connection, method, resource, **kwargs)
        if method == "POST":
            fence.record(resource, response)
        return response

    with pytest.MonkeyPatch.context() as patch:
        original_http_request = qbo.httpx.AsyncClient.request

        async def observed_http_request(client, method, url, **kwargs):
            # Observation only: execute exactly the original client call once,
            # preserving its headers, timeout, body, response and exceptions.
            response = await original_http_request(client, method, url, **kwargs)
            parsed = urlsplit(str(url))
            if response.status_code >= 400 and parsed.scheme == "https" and parsed.netloc == urlsplit(HOST).netloc and parsed.path.startswith(f"/v3/company/{REALM}/"):
                try:
                    faults = sanitized_faults(response.json())
                except ValueError:
                    faults = []
                print(json.dumps({"provider_fault": {"http_status": response.status_code, "errors": faults}}), flush=True)
            return response

        patch.setattr(qbo.httpx.AsyncClient, "request", observed_http_request)
        patch.setattr(qbo, "_request", guarded)
        patch.setattr(r, "_request", guarded)
        await guarded(detached, "GET", f"companyinfo/{REALM}")
        for item_id, income_id in (("19", "85"), ("1", "1")):
            item = (await guarded(detached, "GET", f"item/{item_id}"))["Item"]
            if str(item.get("Id")) != item_id or item.get("Active") is False or str(item.get("IncomeAccountRef", {}).get("value")) != income_id:
                raise SafetyError("Frozen service/fee item mapping mismatch")
        service = await qbo._query(detached, "select * from Item where Name = 'DieselBridge Repair Services' maxresults 2")
        if len(service) != 1 or str(service[0]["Id"]) != "19":
            raise SafetyError("Committed service resolver differs from item19")
        for account in ("1", "1150040000", "1150040001"):
            await r._resolve_qbo_account_reference(detached, account)
        code = (await guarded(detached, "GET", "taxcode/2"))["TaxCode"]
        details = code.get("SalesTaxRateList", {}).get("TaxRateDetail", [])
        rate = (await guarded(detached, "GET", "taxrate/3"))["TaxRate"]
        if str(code.get("Id")) != "2" or code.get("Active") is False or len(details) != 1 or str(details[0].get("TaxRateRef", {}).get("value")) != "3" or str(rate.get("Id")) != "3" or Decimal(str(rate.get("RateValue"))) != args.tax_rate:
            raise SafetyError("Frozen single-rate TaxCode2/TaxRate3 mismatch")
        print(json.dumps({"preflight": "passed", "realm": REALM, "tax_rate": str(args.tax_rate), "fee_tax": str(fee_tax), "gross": str(gross), "mode": "execute" if args.execute else "GET-only"}), flush=True)
        if not args.execute:
            return
        engine_fixture = conftest._db_engine.__wrapped__()
        engine = await anext(engine_fixture)
        try:
            async with async_sessionmaker(engine, expire_on_commit=False)() as db:
                klass = fixture.TenantPaymentProviderConfiguration
                patch.setattr(fixture, "TenantPaymentProviderConfiguration", lambda **kw: klass(**dict(
                    kw, qbo_realm_snapshot=REALM, stripe_clearing_account="1150040000",
                    qbp_clearing_account="1150040000", zelle_ach_account="1150040001",
                    card_fee_income_account="1"), qbo_card_fee_item_id="1", qbo_card_fee_tax_code_id="2"))
                tenant, owner, customer, invoice = await fixture._financial_context(db, patch)
                connection = await db.scalar(select(QuickBooksConnection))
                connection.realm_id = REALM
                connection.encrypted_access_token = detached.encrypted_access_token
                connection.access_token_expires_at = detached.access_token_expires_at
                tenant.name = customer.company_name = invoice.invoice_number = marker
                customer.first_name, customer.last_name = "Synthetic", "Fee-tax accounting only"
                customer.email = "sandbox-accounting@example.invalid"
                patch.setattr(settings, "DB048_GROSS_QBO_ACCOUNTING_ENABLED", True)
                settlement = await get_or_create_settlement(db, invoice=invoice, customer_id=customer.id, tenant=tenant)
                # Same explicit pre-attempt frozen fee-tax fixture as the real
                # SQLite domain regression. Never rewrite a posted attempt.
                settlement.max_card_fee_tax = fee_tax
                await db.commit()
                config = await db.scalar(select(TenantPaymentProviderConfiguration))
                created = await create_attempt(db, invoice=invoice, tenant=tenant, customer_id=customer.id,
                    actor=owner, amount=Decimal("100"), rail="card", expected_settlement_version=settlement.version,
                    idempotency_key="fee-tax-card", source="customer_portal", subject_type="customer", subject_id=customer.id)
                ref = new_reference()
                created.attempt.provider_intent_id = ref
                result = await confirm_attempt(db, attempt_id=created.attempt.id, tenant=tenant, actor=owner,
                    expected_attempt_version=created.attempt.version, idempotency_key="fee-tax-confirm",
                    received_principal=Decimal("100"), reference=ref, provider_charge_id=ref, provider_event_id="evt-" + ref)
                original = tuple(getattr(result.attempt, field) for field in (
                    "provider_charge_amount", "applied_principal_amount", "applied_card_fee_amount", "applied_card_fee_tax_amount"))

                async def deliver(kind, amounts, tax, total, balance, receipt):
                    link = await db.scalar(select(PaymentAccountingLink).where(
                        PaymentAccountingLink.attempt_id == created.attempt.id,
                        PaymentAccountingLink.financial_object_type == kind))
                    if link is None:
                        raise SafetyError("Domain did not create expected immutable accounting link")
                    env = r.AccountingEnvelope(uuid4(), tenant, link, result.attempt, result.payment,
                                              invoice, customer, connection, config, settlement)
                    await r.deliver_accounting_envelope(db, env)
                    if str(invoice.quickbooks_invoice_id) not in fence.ids["invoice"]:
                        raise SafetyError("Writer adopted invoice not created by this run")
                    inv = (await guarded(connection, "GET", f"invoice/{invoice.quickbooks_invoice_id}"))["Invoice"]
                    lines = [line for line in inv.get("Line", []) if line.get("DetailType") == "SalesItemLineDetail"]
                    if [Decimal(str(line["Amount"])) for line in lines] != list(map(Decimal, amounts)) or Decimal(str(inv["TxnTaxDetail"]["TotalTax"])) != tax or Decimal(str(inv["TotalAmt"])) != total or Decimal(str(inv["Balance"])) != balance:
                        raise SafetyError("Provider signed fee/tax/net invoice readback mismatch")
                    payment_id = next(iter(fence.ids["payment"]))
                    payment = (await guarded(connection, "GET", f"payment/{payment_id}"))["Payment"]
                    if Decimal(str(payment["TotalAmt"])) != receipt or Decimal(str(payment.get("UnappliedAmt", 0))) != 0:
                        raise SafetyError("Provider receipt net readback mismatch")
                    posted = len(fence.posts)
                    await r.deliver_accounting_envelope(db, env)
                    if len(fence.posts) != posted:
                        raise SafetyError("Replay issued a provider POST")
                    if link.provider_fee_journal_id:
                        raise SafetyError("Duplicate fee journal created")
                    print(json.dumps({"phase": kind, "invoice": inv["Id"], "payment": payment_id,
                        "fee_lines": amounts[1:], "tax": str(tax), "total": str(total),
                        "balance": str(balance), "receipt": str(receipt), "replay_posts": 0}), flush=True)

                await deliver("invoice_payment", ["100", "3"], fee_tax, gross, Decimal(0), gross)
                await r.record_stripe_dispute(db, provider_account_id=tenant.stripe_account_id,
                    provider_charge_id=ref, provider_dispute_id="dp-" + ref, provider_event_id="evt-open-" + ref,
                    amount=gross, currency="USD", reason="Synthetic sandbox accounting acceptance")
                await deliver("payment_dispute", ["100", "3", "-3"], Decimal(0), Decimal(100), Decimal(100), Decimal(0))
                await r.close_stripe_dispute(db, provider_account_id=tenant.stripe_account_id,
                    provider_charge_id=ref, provider_dispute_id="dp-" + ref, provider_event_id="evt-won-" + ref,
                    amount=gross, currency="USD", outcome="won")
                await deliver("payment_dispute_recovery", ["100", "3", "-3", "3"], fee_tax, gross, Decimal(0), gross)
                if original != tuple(getattr(result.attempt, field) for field in (
                    "provider_charge_amount", "applied_principal_amount", "applied_card_fee_amount", "applied_card_fee_tax_amount")):
                    raise SafetyError("Original posted attempt amounts were mutated")
                print(json.dumps({"result": "fee-tax signed adjustment accounting acceptance passed",
                    "ids": {key: sorted(value) for key, value in fence.ids.items()}, "realm": REALM,
                    "provider_posts": len(fence.posts), "card_capture_proven": False, "payout_proven": False}), flush=True)
        finally:
            await engine_fixture.aclose()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--execute", action="store_true")
    mode.add_argument("--preflight", action="store_true")
    mode.add_argument("--self-test", action="store_true")
    parser.add_argument("--tax-rate", type=Decimal, help="Previously discovered exact TaxRate3 percent; verified GET-only before writes")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return
    if args.tax_rate is None or not args.tax_rate.is_finite() or not Decimal(0) < args.tax_rate <= Decimal(100):
        parser.error("A previously discovered positive --tax-rate is required")
    try:
        asyncio.run(run(args))
    except Exception as exc:
        import traceback
        print(json.dumps({"result": "failed", "error_type": type(exc).__name__,
            "safe_error": str(exc) if isinstance(exc, SafetyError) else "Inspect privately; no provider or credential payload logged",
            "frames": [{"file": Path(frame.filename).name, "function": frame.name, "line": frame.lineno}
                       for frame in traceback.extract_tb(exc.__traceback__)]}), flush=True)
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
