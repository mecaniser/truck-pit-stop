"""Bounded DB-048 accounting-only acceptance; never captures cards or proves payouts.

Run from backend with its test dependencies available. Default --preflight is
GET-only. --execute creates one NEW sandbox customer/invoice and four synthetic
accounting receipts, leaving them in place for review (no automatic cleanup).
The source DATABASE_URL must identify local truckpitstop_db048; it is used in a
read-only transaction solely to detach an existing sandbox OAuth connection.
All domain writes use a disposable in-memory SQLite fixture. Refresh credentials
through the normal owner-controlled workflow BEFORE running this script.
"""
from __future__ import annotations

import argparse
import asyncio
from copy import deepcopy
from datetime import datetime, timezone
from decimal import Decimal
import json
import os
from pathlib import Path
import re
import sys
from types import SimpleNamespace
import traceback
from uuid import uuid4

REALM = "9341457819957473"
HOST = "https://sandbox-quickbooks.api.intuit.com"
PREFIX = "TPS-DB048-SBX-"


def new_marker():
    marker = PREFIX + uuid4().hex[:7]
    if not marker.startswith(PREFIX) or len(marker) > 21:
        raise SafetyError("Sandbox invoice marker exceeds the committed 21-character contract")
    return marker


class SafetyError(RuntimeError):
    pass


class WriteFence:
    """Reject unrelated updates, provider charges, and extra accounting writes."""

    def __init__(self, execute, marker):
        self.execute, self.marker = execute, marker
        self.ids = {"customer": set(), "invoice": set(), "payment": set()}
        self.posts = []

    def check(self, method, resource, payload=None, params=None):
        if method == "GET":
            if resource.split("/")[0] not in {
                "query", "preferences", "companyinfo", "item", "account",
                "invoice", "payment", "taxcode", "taxrate",
            }:
                raise SafetyError("GET resource outside accounting acceptance")
            return
        if not self.execute or method != "POST":
            raise SafetyError("Provider mutation requires explicit --execute")
        body = payload or {}
        if any(k in json.dumps(body) for k in ("ProcessPayment", "CreditCardPayment", "CreditCardInfo")):
            raise SafetyError("Payment-processing payload forbidden")
        if resource == "invoice?operation=update":
            if str(body.get("Id")) not in self.ids["invoice"]:
                raise SafetyError("Only this run's newly created invoice can be updated")
        elif resource == "customer":
            if body.get("Id") or self.ids["customer"] or not str(body.get("DisplayName", "")).startswith(self.marker):
                raise SafetyError("Only one new synthetic customer permitted")
        elif resource == "invoice":
            if body.get("Id") or self.ids["invoice"] or body.get("DocNumber") != self.marker:
                raise SafetyError("Only one new marked invoice permitted")
            if str((body.get("CustomerRef") or {}).get("value")) not in self.ids["customer"]:
                raise SafetyError("Invoice must belong to this run's new customer")
        elif resource == "payment":
            if body.get("Id") or len(self.ids["payment"]) >= 4:
                raise SafetyError("Only four new accounting receipts permitted")
            if str((body.get("CustomerRef") or {}).get("value")) not in self.ids["customer"]:
                raise SafetyError("Receipt customer must be owned by this run")
            lines = body.get("Line") or []
            if len(lines) != 1 or lines[0].get("LinkedTxn") != [
                {"TxnId": next(iter(self.ids["invoice"]), ""), "TxnType": "Invoice"}
            ]:
                raise SafetyError("Receipt must allocate only to the new invoice")
            if Decimal(str(body.get("TotalAmt"))) not in map(Decimal, ("206", "309", "103", "400")):
                raise SafetyError("Receipt amount outside frozen scenario")
        else:
            raise SafetyError("Resource mutation forbidden")
        if (params or {}).get("operation"):
            raise SafetyError("Alternate operation forbidden")
        if len(self.posts) >= 12:
            raise SafetyError("Bounded write limit reached")

    def record(self, resource, response):
        kind = resource.split("?")[0]
        entity = response.get(kind.title()) or {}
        if entity.get("Id"):
            self.ids[kind].add(str(entity["Id"]))
        self.posts.append(resource)
        print(json.dumps({"sandbox_write": resource, "id": entity.get("Id"),
                          "total": entity.get("TotalAmt")}), flush=True)


def self_test():
    if len(new_marker()) != 21:
        raise AssertionError("Sandbox invoice marker does not fit QBO")
    for execute, method, resource, payload in [
        (False, "POST", "customer", {}), (True, "POST", "charge", {}),
        (True, "DELETE", "invoice/1", {}),
        (True, "POST", "invoice?operation=update", {"Id": "existing"}),
        (True, "POST", "customer", {"DisplayName": "real customer"}),
        (True, "POST", "payment", {"ProcessPayment": False}),
    ]:
        try:
            WriteFence(execute, PREFIX + "1234567").check(method, resource, payload)
        except SafetyError:
            continue
        raise AssertionError("Safety negative case unexpectedly allowed")
    WriteFence(False, PREFIX + "1234567").check("GET", "preferences")
    print(json.dumps({"self_test": "passed", "negative_cases": 6, "marker_length": 21, "provider_calls": 0}))


async def run(args):
    source_url = os.environ.get("DB048_SOURCE_DATABASE_URL") or os.environ.get("DATABASE_URL", "")
    from sqlalchemy.engine import make_url
    source = make_url(source_url)
    if source.database != "truckpitstop_db048" or source.host not in {"localhost", "127.0.0.1", "db", "postgres"}:
        raise SafetyError("Source must be the existing local truckpitstop_db048 database")
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
    from app.services import db048_qbo_gross_accounting as g
    from app.services.invoice_settlement_service import get_or_create_settlement, create_attempt, confirm_attempt

    source_engine = create_async_engine(source_url)
    try:
        async with async_sessionmaker(source_engine)() as source_db:
            await source_db.execute(text("SET TRANSACTION READ ONLY"))
            row = (await source_db.execute(select(QuickBooksConnection).where(
                QuickBooksConnection.realm_id == REALM,
                QuickBooksConnection.status == "connected",
                QuickBooksConnection.deleted_at.is_(None),
            ))).scalar_one()
            detached = SimpleNamespace(**{c.name: deepcopy(getattr(row, c.name)) for c in row.__table__.columns})
            await source_db.rollback()
    finally:
        await source_engine.dispose()
    expiry = detached.access_token_expires_at
    if not expiry or expiry.replace(tzinfo=timezone.utc) <= datetime.now(timezone.utc):
        raise SafetyError("Access token expired; use normal OAuth refresh separately")
    marker = new_marker()
    fence = WriteFence(args.execute, marker)
    real_request = qbo._request

    async def guarded(connection, method, resource, **kwargs):
        if (connection.realm_id != REALM or settings.QUICKBOOKS_ACCOUNTING_ENVIRONMENT != "sandbox"
                or settings.QUICKBOOKS_PAYMENTS_ENVIRONMENT != "sandbox" or qbo.accounting_base_url() != HOST):
            raise SafetyError("Sandbox identity fence failed")
        fence.check(method, resource, kwargs.get("json"), kwargs.get("params"))
        response = await real_request(connection, method, resource, **kwargs)
        if method == "POST":
            fence.record(resource, response)
        return response

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(qbo, "_request", guarded)
        patch.setattr(r, "_request", guarded)
        await guarded(detached, "GET", f"companyinfo/{REALM}")
        for item_id, income_id in [(args.service_item, None), (args.fee_item, args.fee_income)]:
            item = (await guarded(detached, "GET", f"item/{item_id}"))["Item"]
            if str(item.get("Id")) != item_id or item.get("Active") is False:
                raise SafetyError("Mapped item unavailable")
            if income_id and str(item.get("IncomeAccountRef", {}).get("value")) != income_id:
                raise SafetyError("Fee item income mapping mismatch")
        service = await qbo._query(detached, "select * from Item where Name = 'DieselBridge Repair Services' maxresults 2")
        if len(service) != 1 or str(service[0]["Id"]) != args.service_item:
            raise SafetyError("Committed service-item resolver does not match supplied mapping")
        for account in (args.fee_income, args.card_deposit, args.zelle_deposit):
            await r._resolve_qbo_account_reference(detached, account)
        print(json.dumps({"preflight": "passed", "realm": REALM, "mode": "execute" if args.execute else "GET-only",
                          "scenario": "synthetic accounting receipts only; no captures, signed tax, or payout proof"}), flush=True)
        if not args.execute:
            return
        engine_fixture = conftest._db_engine.__wrapped__()
        engine = await anext(engine_fixture)
        try:
            async with async_sessionmaker(engine, expire_on_commit=False)() as db:
                klass = fixture.TenantPaymentProviderConfiguration
                patch.setattr(fixture, "TenantPaymentProviderConfiguration", lambda **kw: klass(
                    **dict(kw, selected_provider="quickbooks_payments", provider_account_snapshot=REALM,
                           qbo_realm_snapshot=REALM, qbp_clearing_account=args.card_deposit,
                           zelle_ach_account=args.zelle_deposit, card_fee_income_account=args.fee_income),
                    qbo_card_fee_item_id=args.fee_item, qbo_card_fee_tax_code_id="NON"))
                tenant, owner, customer, invoice = await fixture._financial_context(
                    db, patch, principal=Decimal("1000"), fee=Decimal("30"))
                local_connection = await db.scalar(select(QuickBooksConnection))
                local_connection.realm_id = REALM
                local_connection.scopes = "com.intuit.quickbooks.accounting com.intuit.quickbooks.payment"
                local_connection.encrypted_access_token = detached.encrypted_access_token
                local_connection.access_token_expires_at = detached.access_token_expires_at
                tenant.name = marker
                customer.company_name = marker
                customer.first_name, customer.last_name = "Synthetic", "Accounting only"
                customer.email = "sandbox-accounting@example.invalid"
                invoice.invoice_number = marker
                patch.setattr(settings, "DB048_GROSS_QBO_ACCOUNTING_ENABLED", True)
                patch.setattr(settings, "QUICKBOOKS_PAYMENTS_INVOICE_PAYMENTS_APPROVED", True)
                await db.commit()
                config = await db.scalar(select(TenantPaymentProviderConfiguration))
                settlement = await get_or_create_settlement(db, invoice=invoice, customer_id=customer.id, tenant=tenant)
                envelopes = []
                for index, (rail, amount) in enumerate((("card", "200"), ("card", "300"), ("card", "100"), ("zelle", "400"))):
                    manual = rail == "zelle"
                    ref = f"SBXACCOUNTING-{uuid4().hex[:12]}"
                    created = await create_attempt(db, invoice=invoice, tenant=tenant, customer_id=customer.id,
                        actor=owner, amount=Decimal(amount), rail=rail, expected_settlement_version=settlement.version,
                        idempotency_key=f"sandbox-{index}", source="staff" if manual else "customer_portal",
                        subject_type="staff" if manual else "customer", subject_id=owner.id if manual else customer.id,
                        **({"sender_evidence": {"reference_number": ref}} if manual else {}))
                    if not manual:
                        created.attempt.provider_intent_id = ref
                    confirmed = await confirm_attempt(db, attempt_id=created.attempt.id, tenant=tenant, actor=owner,
                        expected_attempt_version=created.attempt.version, idempotency_key=f"confirm-{index}",
                        received_principal=Decimal(amount), reference=ref,
                        **({} if manual else {"provider_charge_id": ref, "provider_event_id": f"evt-{ref}"}))
                    link = await db.scalar(select(PaymentAccountingLink).where(PaymentAccountingLink.attempt_id == created.attempt.id))
                    env = r.AccountingEnvelope(uuid4(), tenant, link, confirmed.attempt, confirmed.payment,
                                              invoice, customer, local_connection, config, settlement)
                    await g.sync_gross_payment(db, env)
                    envelopes.append(env)
                final = (await guarded(local_connection, "GET", f"invoice/{invoice.quickbooks_invoice_id}"))["Invoice"]
                if Decimal(str(final["TotalAmt"])) != Decimal("1018") or Decimal(str(final["Balance"])) != 0:
                    raise SafetyError("Provider total or balance differs from frozen acceptance")
                if settlement.confirmed_principal != Decimal("1000") or any(e.link.provider_fee_journal_id for e in envelopes):
                    raise SafetyError("Local principal or fee-journal invariant failed")
                before = len(fence.posts)
                for env in envelopes:
                    await g.sync_gross_payment(db, env)
                if len(fence.posts) != before:
                    raise SafetyError("Replay issued a provider POST")
                print(json.dumps({"result": "accounting-only acceptance passed", "realm": REALM,
                    "ids": {k: sorted(v) for k, v in fence.ids.items()}, "invoice_total": "1018.00",
                    "balance": "0.00", "principal": "1000.00", "receipt_amounts": ["206.00", "309.00", "103.00", "400.00"],
                    "replay_posts": 0, "card_capture_proven": False, "payout_linkage_proven": False}), flush=True)
        finally:
            await engine_fixture.aclose()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--preflight", action="store_true")
    modes.add_argument("--execute", action="store_true")
    modes.add_argument("--self-test", action="store_true")
    for name in ("service-item", "fee-item", "fee-income", "card-deposit", "zelle-deposit"):
        parser.add_argument("--" + name)
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return
    if any(not re.fullmatch(r"[0-9]+", getattr(args, key) or "") for key in
           ("service_item", "fee_item", "fee_income", "card_deposit", "zelle_deposit")):
        parser.error("All five discovered numeric item/account mapping IDs are required")
    try:
        asyncio.run(run(args))
    except Exception as exc:
        # Never print provider bodies, credentials, connection URLs, or domain PII.
        safe_messages = {
            "Invoice number is not valid for QuickBooks synchronization",
            "QuickBooks card fee item mapping is missing",
            "QuickBooks fee item does not match the frozen income account",
            "QuickBooks invoice readback differs from the earned fee/tax projection",
            "QuickBooks invoice has unexpected edits; gross update was not applied",
            "Gross receipt identity, allocation, or unapplied money does not match",
            "QuickBooks accounting period dates are invalid",
            "QuickBooks closing-period preferences are unavailable",
        }
        print(json.dumps({"result": "failed", "error_type": type(exc).__name__,
                          "safe_error": str(exc) if isinstance(exc, SafetyError) or str(exc) in safe_messages
                          else "Inspect separately without exposing provider or credential payloads",
                          "frames": [{"file": Path(frame.filename).name, "function": frame.name, "line": frame.lineno}
                                     for frame in traceback.extract_tb(exc.__traceback__)]}), flush=True)
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
