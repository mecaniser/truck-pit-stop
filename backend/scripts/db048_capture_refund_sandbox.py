"""One $1.03 sandbox capture and its full refund; provider evidence, not accounting.

Default: GET-only company preflight. --execute requires a new explicit UUID and
independent safety review. Never rerun after uncertain outcome: reconcile IDs
from stdout first. No source DB writes, OAuth refresh, existing-charge inputs,
raw-response logging, automatic cleanup, or production endpoint supported.

Primary Intuit sources:
https://github.com/intuit/PHP-Payments-SDK/blob/master/Readme.md (test card)
https://github.com/intuit/PHP-Payments-SDK/blob/master/src/Operations/ChargeOperations.php
(refundBy GET). Token shape matches frontend QuickBooksPaymentPanel.tsx.
The original capture scenario uses harness-only refund GET. --reconcile-known
uses the corrected application GET client/worker with the two fixed known IDs.
"""
from __future__ import annotations

import argparse
import asyncio
from datetime import datetime, timezone
from decimal import Decimal
import json
import logging
import os
from pathlib import Path
import re
import sys
from types import SimpleNamespace
from uuid import UUID

REALM = "9341457819957473"
HOST = "https://sandbox.api.intuit.com"
BASE = HOST + "/quickbooks/v4/payments"
COMPANY = f"https://sandbox-quickbooks.api.intuit.com/v3/company/{REALM}/companyinfo/{REALM}"
AMOUNT = Decimal("1.03")
KNOWN_CHARGE = "MT0359488296"
KNOWN_REFUND = "MT7353020517"


class SafetyError(RuntimeError):
    pass


def require(condition, message):
    if not condition:
        raise SafetyError(message)


def safe_id(value):
    require(isinstance(value, str) and re.fullmatch(r"[A-Za-z0-9_-]{1,100}", value),
            "Provider identifier is unsafe")
    return value


def emit(**values):
    print(json.dumps(values), flush=True)


def fenced_redirects(client_default, requested):
    # HTTPX passes a truthy USE_CLIENT_DEFAULT sentinel to send(). It is not
    # consent to redirect. Refuse an enabled client/request and force False.
    require(client_default is False and requested is not True, "Redirects forbidden")
    return False


def validate_company(payload, realm, url):
    require(realm == REALM and url == COMPANY, "Company request realm identity mismatch")
    entity = payload.get("CompanyInfo") if isinstance(payload, dict) else None
    # CompanyInfo.Id is an entity identifier (often "1"), not the OAuth realm.
    # OAuth row selection plus the exact sandbox URL bind the company request.
    require(isinstance(entity, dict) and isinstance(entity.get("Id"), str) and
            re.fullmatch(r"[0-9]+", entity["Id"]), "CompanyInfo entity identifier missing")


class Fence:
    def __init__(self, execute, run_id):
        self.execute, self.run_id = execute, run_id
        self.charge = self.refund = self.token = None
        self.calls = {"token": 0, "charge": 0, "refund": 0}

    def check(self, method, url, body=None, request_id=None):
        if method == "GET":
            allowed = {COMPANY}
            if self.charge:
                allowed.add(f"{BASE}/charges/{self.charge}")
                if self.refund:
                    allowed.add(f"{BASE}/charges/{self.charge}/refunds/{self.refund}")
            require(url in allowed, "GET is outside this run")
            return
        require(self.execute and method == "POST", "Explicit execute required; other verbs forbidden")
        body = body or {}
        if url == BASE + "/tokens":
            require(self.calls["token"] == 0 and body == test_card(), "Only one fixed Intuit test token allowed")
            self.calls["token"] += 1
        elif url == BASE + "/charges":
            require(self.token is not None and self.calls["charge"] < 2 and self.calls["refund"] == 0,
                    "Capture limit or sequence failed")
            require(request_id == self.run_id and body == {
                "amount": "1.03", "currency": "USD", "token": self.token,
                "capture": True, "description": "DB048 sandbox capture " + self.run_id},
                "Capture payload or replay identity changed")
            self.calls["charge"] += 1
        elif self.charge and url == f"{BASE}/charges/{self.charge}/refunds":
            require(self.calls["refund"] < 2 and self.calls["charge"] == 2,
                    "Refund limit or sequence failed")
            require(request_id == "refund-" + self.run_id and body == {
                "amount": "1.03", "description": "DB048 sandbox refund " + self.run_id},
                "Refund must match newly created charge and immutable request")
            self.calls["refund"] += 1
        else:
            raise SafetyError("Endpoint forbidden")


def test_card():
    # Public, synthetic Intuit SDK sample only. Never accept PAN as input.
    return {"card": {"number": "4111111111111111", "cvc": "123",
            "expMonth": "12", "expYear": str(datetime.now(timezone.utc).year + 2),
            "name": "emulate=0", "address": {"country": "US", "postalCode": "94086"}}}


def self_test():
    run_id = "00000000-0000-4000-8000-000000000048"
    f = Fence(True, run_id)
    negatives = [
        lambda: Fence(False, run_id).check("POST", BASE + "/tokens", test_card()),
        lambda: f.check("DELETE", COMPANY),
        lambda: f.check("GET", COMPANY.replace("sandbox-", "")),
        lambda: f.check("GET", BASE + "/charges/existing"),
        lambda: f.check("POST", BASE + "/charges/existing/refunds", {}),
        lambda: f.check("POST", BASE + "/tokens", {"card": {}}),
        lambda: f.check("POST", BASE + "/charges", {}),
        lambda: safe_id("../existing"),
        lambda: fenced_redirects(True, False),
        lambda: fenced_redirects(False, True),
        lambda: validate_company({"CompanyInfo": {"Id": "1"}}, "another-realm", COMPANY),
        lambda: validate_company({"CompanyInfo": {"Id": "1"}}, REALM, COMPANY.replace(REALM, "123")),
        lambda: validate_company({}, REALM, COMPANY),
    ]
    for test in negatives:
        try:
            test()
        except SafetyError:
            pass
        else:
            raise AssertionError("Negative safety case allowed")
    f.check("GET", COMPANY)
    require(fenced_redirects(False, object()) is False, "Default sentinel must disable redirects")
    require(fenced_redirects(False, False) is False, "Explicit False must disable redirects")
    validate_company({"CompanyInfo": {"Id": "1"}}, REALM, COMPANY)
    f.check("POST", BASE + "/tokens", test_card())
    try:
        f.check("POST", BASE + "/tokens", test_card())
    except SafetyError:
        pass
    else:
        raise AssertionError("Second token allowed")
    f.token = "synthetic-self-test-token"
    body = {"amount": "1.03", "currency": "USD", "token": f.token,
            "capture": True, "description": "DB048 sandbox capture " + run_id}
    more_negatives = [
        lambda: f.check("POST", BASE + "/charges", dict(body, amount="2.00"), run_id),
        lambda: f.check("POST", BASE + "/charges", body, "different-id"),
        lambda: f.check("POST", BASE.replace("sandbox.", "") + "/charges", body, run_id),
    ]
    for test in more_negatives:
        try:
            test()
        except SafetyError:
            pass
        else:
            raise AssertionError("Capture safety case allowed")
    f.check("POST", BASE + "/charges", body, run_id)
    f.charge = "NEW-CHARGE"
    f.check("POST", BASE + "/charges", body, run_id)
    f.check("GET", BASE + "/charges/NEW-CHARGE")
    refund_body = {"amount": "1.03", "description": "DB048 sandbox refund " + run_id}
    refund_url = BASE + "/charges/NEW-CHARGE/refunds"
    for test in [
        lambda: f.check("POST", BASE + "/charges", body, run_id),
        lambda: f.check("POST", refund_url, dict(refund_body, amount="2.00"), "refund-" + run_id),
        lambda: f.check("POST", refund_url, refund_body, "different-id"),
        lambda: f.check("POST", BASE + "/charges/EXISTING/refunds", refund_body, "refund-" + run_id),
    ]:
        try:
            test()
        except SafetyError:
            pass
        else:
            raise AssertionError("Refund safety case allowed")
    f.check("POST", refund_url, refund_body, "refund-" + run_id)
    f.refund = "NEW-REFUND"
    f.check("POST", refund_url, refund_body, "refund-" + run_id)
    f.check("GET", refund_url + "/NEW-REFUND")
    try:
        f.check("POST", refund_url, refund_body, "refund-" + run_id)
    except SafetyError:
        pass
    else:
        raise AssertionError("Third refund allowed")
    emit(self_test="passed", negative_cases=22, provider_calls=0)


async def run(args):
    logging.disable(logging.CRITICAL)
    from sqlalchemy.engine import make_url
    source_url = os.environ.get("DB048_SOURCE_DATABASE_URL") or os.environ.get("DATABASE_URL", "")
    source = make_url(source_url)
    require(source.database == "truckpitstop_db048" and source.host in {"localhost", "127.0.0.1", "db", "postgres"},
            "Source must be local truckpitstop_db048")
    require(os.environ.get("QUICKBOOKS_PAYMENTS_ENVIRONMENT") == "sandbox" and
            os.environ.get("QUICKBOOKS_ACCOUNTING_ENVIRONMENT") == "sandbox", "Explicit sandbox settings required")
    os.environ["DATABASE_URL"] = "sqlite+aiosqlite://"
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    import httpx
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import create_async_engine
    from app.services import quickbooks_payments_service as payments
    from app.core.quickbooks_crypto import decrypt_quickbooks_token
    require(payments.payments_base_url() == HOST, "Committed client must target sandbox")
    engine = create_async_engine(source_url)
    try:
        async with engine.connect() as db:
            await db.execute(text("SET TRANSACTION READ ONLY"))
            rows = (await db.execute(text("SELECT realm_id, scopes, encrypted_access_token, access_token_expires_at "
                "FROM quickbooks_connections WHERE realm_id=:realm AND status='connected' AND deleted_at IS NULL"),
                {"realm": REALM})).mappings().all()
            require(len(rows) == 1, "Exactly one connected sandbox realm required")
            connection = SimpleNamespace(**dict(rows[0]))
            await db.rollback()
    finally:
        await engine.dispose()
    require("com.intuit.quickbooks.payment" in connection.scopes.split(), "Payment OAuth scope missing")
    expiry = connection.access_token_expires_at
    require(expiry and expiry.replace(tzinfo=timezone.utc) > datetime.now(timezone.utc), "OAuth expired; refresh normally first")
    access = decrypt_quickbooks_token(connection.encrypted_access_token)
    fence = Fence(args.execute, args.run_id)
    original_send = httpx.AsyncClient.send

    async def guarded_send(client, request, **kwargs):
        kwargs["follow_redirects"] = fenced_redirects(client.follow_redirects, kwargs.get("follow_redirects"))
        body = json.loads(request.content) if request.content else None
        fence.check(request.method, str(request.url), body, request.headers.get("Request-Id"))
        result = await original_send(client, request, **kwargs)
        # Deliberately never log errors/messages from provider: may contain secrets.
        emit(provider_call=request.method, endpoint=request.url.path.split("/")[-1], http_status=result.status_code)
        return result

    httpx.AsyncClient.send = guarded_send
    try:
        async with httpx.AsyncClient(timeout=30, trust_env=False) as client:
            headers = {"Authorization": "Bearer " + access, "Accept": "application/json"}
            company = await client.get(COMPANY, headers=headers)
            require(company.status_code == 200, "Sandbox company GET failed")
            validate_company(company.json(), connection.realm_id, str(company.request.url))
            emit(preflight="passed", realm=REALM, execute=args.execute,
                 refund_get="application-client" if args.reconcile_known else "harness-only")
            if args.reconcile_known:
                # Only IDs returned by the already authorized sandbox run.
                # All HTTP POSTs remain forbidden by execute=False.
                fence.charge, fence.refund = KNOWN_CHARGE, KNOWN_REFUND
                sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tests"))
                import pytest
                import conftest
                import test_db048_qbp_refund_reconciliation as fixture
                from sqlalchemy.ext.asyncio import async_sessionmaker
                from app.services import db048_accounting_reconciliation as reconciliation
                engine_fixture = conftest._db_engine.__wrapped__()
                fixture_engine = await anext(engine_fixture)
                try:
                    with pytest.MonkeyPatch.context() as patch:
                        factory = async_sessionmaker(fixture_engine, expire_on_commit=False)
                        async with factory() as db:
                            refund, event, _, local_connection = await fixture.context(
                                db, patch, realm=REALM, charge_id=KNOWN_CHARGE)
                            refund.provider_reference = KNOWN_REFUND
                            local_connection.encrypted_access_token = connection.encrypted_access_token
                            local_connection.access_token_expires_at = connection.access_token_expires_at
                            await db.commit()
                            result = await reconciliation.process_due_db048_outbox_events(session_factory=factory)
                            await db.refresh(refund)
                            await db.refresh(event)
                            require(result["retried"] == 1 and refund.state == "pending" and
                                    refund.provider_reference == KNOWN_REFUND and
                                    event.provider_message_id == KNOWN_REFUND and event.status == "pending" and
                                    refund.last_error == "qbp_refund_accepted_pending" and
                                    refund.completed_at is None, "Corrected worker did not retain accepted pending refund")
                            require(sum(fence.calls.values()) == 0, "Reconciliation performed a POST")
                            emit(result="corrected worker GET-only acceptance passed", charge_id=KNOWN_CHARGE,
                                 refund_id=KNOWN_REFUND, state=refund.state, event_state=event.status,
                                 accepted_not_settled=True, provider_posts=0, shared_db_writes=0)
                finally:
                    await engine_fixture.aclose()
                return
            if not args.execute:
                return
            emit(run_id=args.run_id, capture_amount="1.03", refund_request_id="refund-" + args.run_id)
            response = await client.post(BASE + "/tokens", json=test_card(), headers={"Accept": "application/json"})
            require(response.status_code in {200, 201}, "Intuit test token rejected")
            token = response.json().get("value")
            require(isinstance(token, str) and 0 < len(token) <= 2048, "Intuit token unavailable")
            fence.token = token
            charge_args = dict(connection=connection, token=token, amount=AMOUNT,
                description="DB048 sandbox capture " + args.run_id, request_id=args.run_id)
            charge = await payments.create_charge(**charge_args)
            fence.charge = safe_id(charge.id)
            emit(charge_id=fence.charge, amount=str(charge.amount), status=charge.status)
            require(charge.amount == AMOUNT and payments.is_successful_charge(charge), "Capture not successful at fixed amount")
            replay = await payments.create_charge(**charge_args)
            require(replay.id == charge.id and replay.amount == AMOUNT and payments.is_successful_charge(replay), "Capture replay mismatch; stop and reconcile")
            readback = await payments.get_charge(connection=connection, charge_id=charge.id)
            require(readback.id == charge.id and readback.amount == AMOUNT and payments.is_successful_charge(readback), "Capture GET mismatch")
            refund_args = dict(connection=connection, charge_id=charge.id, amount=AMOUNT,
                description="DB048 sandbox refund " + args.run_id, request_id="refund-" + args.run_id)
            refund = await payments.refund_charge(**refund_args)
            fence.refund = safe_id(refund.id)
            emit(refund_id=fence.refund, amount=str(refund.amount), status=refund.status)
            require(refund.amount == AMOUNT and refund.status in {"REFUNDED", "SUCCEEDED", "COMPLETED", "ISSUED"}, "Refund is not confirmed")
            replay_refund = await payments.refund_charge(**refund_args)
            require(replay_refund.id == refund.id and replay_refund.amount == AMOUNT and replay_refund.status == refund.status, "Refund replay mismatch")
            result = await client.get(f"{BASE}/charges/{charge.id}/refunds/{refund.id}", headers=headers)
            require(result.status_code == 200, "Refund GET failed")
            raw = result.json()
            require(raw.get("id") == refund.id and Decimal(str(raw.get("amount"))) == AMOUNT and
                    str(raw.get("status")).upper() == refund.status, "Refund GET differs from accepted refund")
            emit(result="sandbox payment-provider acceptance passed", charge_id=charge.id, refund_id=refund.id,
                capture_replay_same_id=True, refund_replay_same_id=True, refund_get_verified=True,
                accounting_acceptance=False, payout_acceptance=False, calls=fence.calls)
    finally:
        httpx.AsyncClient.send = original_send


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--execute", action="store_true")
    modes.add_argument("--preflight", action="store_true")
    modes.add_argument("--self-test", action="store_true")
    modes.add_argument("--reconcile-known", action="store_true",
                       help="GET-only corrected worker test for fixed already-created sandbox IDs in isolated SQLite")
    parser.add_argument("--run-id")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return
    if args.execute:
        try:
            require(str(UUID(args.run_id)) == args.run_id, "Canonical UUID required")
        except (ValueError, TypeError, AttributeError, SafetyError):
            parser.error("--execute requires explicit canonical --run-id UUID; do not rerun after uncertain outcomes")
    try:
        asyncio.run(run(args))
    except Exception as exc:
        emit(result="failed", error_type=type(exc).__name__,
             error=str(exc) if isinstance(exc, SafetyError) else "Provider or runtime failure; inspect privately",
             outcome_unknown=bool(getattr(exc, "outcome_unknown", False)),
             action="Stop; retain printed IDs and request IDs for reconciliation; do not create another charge")
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
