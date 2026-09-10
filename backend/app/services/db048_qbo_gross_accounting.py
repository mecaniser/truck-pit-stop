"""Versioned canonical gross QBO invoices and receipts.

Only the persisted composition selects this writer. The deployment flag is not
a runtime kill switch: historical composition must never be reinterpreted.
Provider writes are accounting-only (never ProcessPayment).
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP

from sqlalchemy import select
from app.services.quickbooks_shop_activation import accounting_operation

from app.db.models.invoice_settlement import (
    InvoiceSettlement, InvoicePaymentAttempt, PaymentAccountingLink,
    PaymentProviderDispute, PaymentRefund, PaymentOverpayment,
)
from app.services.db048_qbo_invoice_projection import (
    COMPOSITION_VERSION, InvoiceIdentity, ConfirmedEarnedAttempt,
    project_gross_invoice,
)


def _r():
    # Avoid a module initialization cycle; existing helpers remain the shared
    # provider/identity boundary and can be patched in provider-free tests.
    from app.services import db048_accounting_reconciliation as reconciliation
    return reconciliation


def is_gross(settlement):
    from app.services.new_receipt_accounting import effective_gross
    return effective_gross(settlement)


def _fail(message):
    raise _r().DB048ReconciliationError(message)


def _amount(value):
    from app.services.db048_qbo_invoice_projection import _cents, _money
    try:
        return _money(_cents(Decimal(str(value))))
    except (ValueError, TypeError, ArithmeticError):
        _fail("Gross accounting amount is invalid")


def _signed_amount(value):
    parsed = Decimal(str(value))
    return -_amount(-parsed) if parsed < 0 else _amount(parsed)


def _ref(entity, key):
    return str((entity.get(key) or {}).get("value") or "")


def invoice_semantics(entity):
    """Strict accounting semantics; provider line IDs are stored separately."""
    _usd_exchange(entity)
    lines = []
    for line in entity.get("Line", []):
        if line.get("DetailType") == "SubTotalLineDetail":
            continue  # QBO-generated display line, not another obligation.
        if line.get("DetailType") != "SalesItemLineDetail":
            _fail("QuickBooks invoice contains an unmanaged accounting line")
        detail = line.get("SalesItemLineDetail") or {}
        lines.append({
            "description": str(line.get("Description") or ""),
            "amount": str(_signed_amount(line.get("Amount"))),
            "item": _ref(detail, "ItemRef"),
            "qty": str(Decimal(str(detail.get("Qty", 1))).normalize()),
            "unit": str(_signed_amount(detail.get("UnitPrice", line.get("Amount")))),
            "tax_code": _ref(detail, "TaxCodeRef"),
        })
    tax = entity.get("TxnTaxDetail") or {}
    tax_groups={}
    for line in tax.get("TaxLine") or []:
        detail=line.get("TaxLineDetail") or {}
        if line.get("DetailType")!="TaxLineDetail" or detail.get("PercentBased") is not True or not _ref(detail,"TaxRateRef"):
            _fail("QuickBooks tax line does not match the mapped rate")
        percent=Decimal(str(detail.get("TaxPercent")))
        if not percent.is_finite() or percent<0:
            _fail("QuickBooks tax percentage is invalid")
        key=(_ref(detail,"TaxRateRef"),str(percent.normalize()))
        amount,base=tax_groups.get(key,(Decimal(0),Decimal(0)))
        tax_groups[key]=(amount+_signed_amount(line.get("Amount")),base+_signed_amount(detail.get("NetAmountTaxable")))
    semantics = {"lines": lines, "tax": str(_amount(tax.get("TotalTax", 0))),
            "tax_lines":[[key[0],key[1],str(_signed_amount(value[0])),str(_signed_amount(value[1]))] for key,value in sorted(tax_groups.items())],
            "total": str(_amount(entity.get("TotalAmt"))),
            "currency": _ref(entity, "CurrencyRef") or "USD"}
    # Preserve persisted no-tax snapshots byte-for-byte. A taxable US invoice
    # must also retain its transaction-level tax identity on every readback.
    if _ref(tax, "TxnTaxCodeRef"):
        semantics["transaction_tax_code"] = _ref(tax, "TxnTaxCodeRef")
    return semantics


def _usd_exchange(entity):
    try:
        exchange = Decimal(str(entity.get("ExchangeRate", 1)))
    except (ValueError, ArithmeticError):
        _fail("Gross accounting exchange rate is invalid")
    if not exchange.is_finite() or exchange != 1:
        _fail("Gross accounting requires exact USD exchange rate")


async def _assert_open_period(connection,entity):
    preferences=(await _r()._request(connection,"GET","preferences")).get("Preferences") or {}
    accounting=preferences.get("AccountingInfoPrefs")
    if not isinstance(accounting,dict):
        _fail("QuickBooks closing-period preferences are unavailable")
    close_date=accounting.get("BookCloseDate")
    if close_date:
        from datetime import date
        try:
            closed=date.fromisoformat(str(entity.get("TxnDate")))<=date.fromisoformat(str(close_date))
        except ValueError:
            _fail("QuickBooks accounting period dates are invalid")
        if closed:
            _fail("QuickBooks transaction is in a closed accounting period")


async def _locked_settlement(db, settlement):
    row = await db.scalar(select(InvoiceSettlement).where(
        InvoiceSettlement.id == settlement.id,
        InvoiceSettlement.tenant_id == settlement.tenant_id,
        InvoiceSettlement.invoice_id == settlement.invoice_id,
    ).with_for_update().execution_options(populate_existing=True))
    if row is None or not is_gross(row):
        _fail("Gross accounting settlement identity changed")
    return row


async def _projection(db, settlement, connection, *, original_attempt_id=None):
    """Current earned obligations, retaining immutable original capture data."""
    identity = InvoiceIdentity(str(settlement.tenant_id), str(connection.realm_id), str(settlement.invoice_id))
    attempts = (await db.execute(select(InvoicePaymentAttempt).where(
        InvoicePaymentAttempt.tenant_id == settlement.tenant_id,
        InvoicePaymentAttempt.invoice_id == settlement.invoice_id,
        InvoicePaymentAttempt.settlement_id == settlement.id,
        InvoicePaymentAttempt.state.in_(["confirmed", "refunded", "reversed"]),
    ).order_by(InvoicePaymentAttempt.created_at, InvoicePaymentAttempt.id))).scalars().all()
    members, mappings, fee_components = [], {}, []
    for attempt in attempts:
        from app.services.new_receipt_accounting import scoped_invoice, valid_attempt_authorization
        if scoped_invoice(settlement) and not await valid_attempt_authorization(db, attempt):
            continue
        link = await db.scalar(select(PaymentAccountingLink).where(
            PaymentAccountingLink.tenant_id == settlement.tenant_id,
            PaymentAccountingLink.invoice_id == settlement.invoice_id,
            PaymentAccountingLink.attempt_id == attempt.id,
            PaymentAccountingLink.financial_object_type == "invoice_payment",
            PaymentAccountingLink.operation_version == 1,
        ))
        if not link or link.owning_writer != "dieselbridge" or link.qbo_realm_snapshot != connection.realm_id:
            _fail("Gross invoice attempt ownership or realm does not match")
        if link.provider_fee_journal_id:
            _fail("Gross invoice cannot adopt a legacy fee journal")
        p, f, t, g, x = map(_amount, (
            attempt.applied_principal_amount, attempt.applied_card_fee_amount,
            attempt.applied_card_fee_tax_amount, attempt.provider_charge_amount,
            attempt.unapplied_amount,
        ))
        # Original capture projection is validated even when later reversed.
        original = ConfirmedEarnedAttempt(identity, str(attempt.id), COMPOSITION_VERSION,
                                         attempt.rail, p, f, t, g, x)
        project_gross_invoice(identity=identity, composition_version=COMPOSITION_VERSION,
                             principal_base=_amount(settlement.principal_total), attempts=[original])
        mapping = dict(link.account_mapping_snapshot or {},
            _fee_description=f"Card processing fee — {attempt.provider_charge_id or attempt.provider_reference or 'Card payment'}")
        mappings[str(attempt.id)] = mapping
        if f:
            fee_components.append((str(attempt.id), original, mapping))
        if attempt.id != original_attempt_id:
            changes = await _attempt_changes(db, attempt, connection.realm_id)
            for change in changes:
                p += change["principal"]
                f += change["fee"]
                t += change["tax"]
                g += change["gross"]
                if change["fee"]:
                    component = replace(original, fee=change["fee"], fee_tax=change["tax"])
                    component_mapping = dict(mapping, _fee_description=f"Card fee {change['label']} — {attempt.provider_charge_id}")
                    fee_components.append((change["key"], component, component_mapping))
            if min(p, f, t, g) < 0:
                _fail("Adjustment components exceed the original earned allocation")
            x = g - p - f - t
            if not g:
                continue
        members.append(ConfirmedEarnedAttempt(identity, str(attempt.id), COMPOSITION_VERSION,
                                             attempt.rail, p, f, t, g, x))
    mappings["_fee_components"] = fee_components
    return project_gross_invoice(identity=identity, composition_version=COMPOSITION_VERSION,
                                 principal_base=_amount(settlement.principal_total), attempts=members), mappings


async def _attempt_changes(db, attempt, realm):
    """Immutable accounting links, not mutable dispute status, define history."""
    links = (await db.execute(select(PaymentAccountingLink).where(
        PaymentAccountingLink.tenant_id == attempt.tenant_id,
        PaymentAccountingLink.invoice_id == attempt.invoice_id,
        PaymentAccountingLink.attempt_id == attempt.id,
        PaymentAccountingLink.financial_object_type.in_([
            "payment_dispute", "payment_dispute_recovery", "payment_reversal"]),
    ).order_by(PaymentAccountingLink.created_at, PaymentAccountingLink.id))).scalars().all()
    changes = []
    for link in links:
        if link.qbo_realm_snapshot != realm or link.owning_writer != "dieselbridge":
            _fail("Gross adjustment ownership or realm changed")
        kind = link.financial_object_type
        if kind == "payment_reversal":
            p, f, t, gross = map(_amount, (attempt.applied_principal_amount,
                attempt.applied_card_fee_amount, attempt.applied_card_fee_tax_amount, attempt.provider_charge_amount))
            sign, label = -1, "reversal"
        else:
            dispute = await db.scalar(select(PaymentProviderDispute).where(
                PaymentProviderDispute.id == link.financial_object_id,
                PaymentProviderDispute.tenant_id == attempt.tenant_id,
                PaymentProviderDispute.attempt_id == attempt.id,
            ))
            if not dispute:
                _fail("Gross adjustment dispute identity is missing")
            p = _amount(link.principal_amount_snapshot)
            f, t = _amount(dispute.reversed_card_fee_amount), _amount(dispute.reversed_card_fee_tax_amount)
            gross = _amount(link.gross_amount_snapshot)
            sign, label = (-1, "dispute") if kind == "payment_dispute" else (1, "recovery")
            if sign > 0:
                original_p = _amount(dispute.reversed_principal_amount)
                if p > original_p:
                    _fail("Gross recovery exceeds disputed principal")
                if original_p:
                    f = _r().money(f * p / original_p)
                    t = _r().money(t * p / original_p)
                else:
                    f = t = Decimal("0.00")
        changes.append({"key":str(link.id), "principal":sign*p, "fee":sign*f,
                        "tax":sign*t, "gross":sign*gross,
                        "label":f"{label} {str(link.financial_object_id)[:8]}"})
    return changes


async def _fee_line(connection, member, mapping):
    r = _r()
    item_id = str(mapping.get("qbo_card_fee_item_id") or "")
    if not item_id:
        _fail("QuickBooks card fee item mapping is missing")
    response = await r._request(connection, "GET", f"item/{item_id}")
    item = response.get("Item") or {}
    income_id = await r._resolve_qbo_account_reference(connection, mapping.get("card_fee_income_account"))
    if (str(item.get("Id")) != item_id or item.get("Active") is False
            or _ref(item, "IncomeAccountRef") != income_id
            or item.get("Type") not in {"Service", "NonInventory"}):
        _fail("QuickBooks fee item does not match the frozen income account")
    code, tax_line = "NON", None
    if member.fee_tax:
        code = str(mapping.get("qbo_card_fee_tax_code_id") or "")
        if not code:
            _fail("QuickBooks earned fee tax mapping is missing")
        tax_code = (await r._request(connection, "GET", f"taxcode/{code}")).get("TaxCode") or {}
        rates = (tax_code.get("SalesTaxRateList") or {}).get("TaxRateDetail") or []
        if str(tax_code.get("Id")) != code or tax_code.get("Active") is False or len(rates) != 1:
            _fail("QuickBooks fee tax code must identify one verified sales tax rate")
        rate_id = _ref(rates[0], "TaxRateRef")
        rate = (await r._request(connection, "GET", f"taxrate/{rate_id}")).get("TaxRate") or {}
        if str(rate.get("Id")) != rate_id or rate.get("Active") is False:
            _fail("QuickBooks fee tax rate is unavailable")
        percent = Decimal(str(rate.get("RateValue")))
        if (member.fee * percent / 100).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP) != member.fee_tax:
            _fail("QuickBooks fee tax rate differs from the earned tax")
        tax_line = {"Amount": float(member.fee_tax), "DetailType": "TaxLineDetail",
                    "TaxLineDetail": {"TaxRateRef": {"value": rate_id},
                                      "PercentBased": True, "TaxPercent": float(percent),
                                      "NetAmountTaxable": float(member.fee)}}
    return {"Amount": float(member.fee), "Description": mapping["_fee_description"],
            "DetailType": "SalesItemLineDetail", "SalesItemLineDetail": {
                "ItemRef": {"value": item_id}, "Qty": 1,
                # US line-level taxability is TAX/NON, never a tax-code ID.
                # The verified ID belongs in TxnTaxDetail.TxnTaxCodeRef.
                "UnitPrice": float(member.fee), "TaxCodeRef": {"value": "TAX" if tax_line else "NON"}}}, tax_line


@accounting_operation
async def ensure_gross_invoice(db, *, connection, invoice, customer, settlement, tenant_name=None,
                               original_attempt_id=None):
    from app.services.invoice_accounting_policy import require_exportable_invoice
    await require_exportable_invoice(invoice)
    r = _r()
    settlement = await _locked_settlement(db, settlement)
    if (settlement.qbo_realm_snapshot != connection.realm_id
            or settlement.tenant_id != connection.tenant_id
            or invoice.tenant_id != settlement.tenant_id
            or customer.tenant_id != settlement.tenant_id
            or customer.id != settlement.customer_id
            or settlement.invoice_id != invoice.id):
        _fail("Gross canonical invoice tenant or realm does not match")
    projection, mappings = await _projection(db, settlement, connection, original_attempt_id=original_attempt_id)
    customer_id = await r.ensure_customer(connection, customer, tenant_name=tenant_name)
    item_id = await r._ensure_service_item(connection)
    payload = r.db048_qbo_invoice_payload(invoice=invoice, qbo_customer_id=customer_id,
        qbo_item_id=item_id, principal_total=projection.principal_base, tenant_name=tenant_name)
    payload["CurrencyRef"] = {"value": "USD"}
    payload["Line"][0]["SalesItemLineDetail"]["TaxCodeRef"] = {"value": "NON"}
    tax_lines = []
    components = mappings.get("_fee_components", [(p.attempt_id, p, mappings[p.attempt_id]) for p in projection.payments if p.fee])
    transaction_tax_codes = {str(mapping.get("qbo_card_fee_tax_code_id") or "")
                             for _, member, mapping in components if member.fee_tax}
    if len(transaction_tax_codes) > 1:
        _fail("QuickBooks US invoice requires a single transaction tax code")
    for component_key, member, mapping in components:
        if member.fee:
            line, tax_line = await _fee_line(connection, member, mapping)
            payload["Line"].append(line)
            if tax_line:
                tax_lines.append(tax_line)
    payload["TxnTaxDetail"] = {"TotalTax": float(sum((p.fee_tax for p in projection.payments), Decimal(0))),
                               "TaxLine": tax_lines}
    if tax_lines:
        payload["TxnTaxDetail"]["TxnTaxCodeRef"] = {"value": next(iter(transaction_tax_codes))}
    previous = (settlement.accounting_projection_snapshot or {}).get("invoice")
    if previous:
        owned_order={line["description"]:index for index,line in enumerate(previous["lines"])}
        payload["Line"].sort(key=lambda line:owned_order.get(line["Description"],len(owned_order)))
        if not set(owned_order).issubset({line["Description"] for line in payload["Line"]}):
            _fail("Gross accounting would remove an already posted invoice line")
    desired = invoice_semantics(dict(payload, TotalAmt=float(projection.invoice_total)))
    revision = hashlib.sha256(json.dumps([projection.revision, desired], sort_keys=True).encode()).hexdigest()
    current = None
    if invoice.quickbooks_invoice_id:
        # Unlike legacy migration, missing persisted identity never clears here.
        current = (await r._request(connection, "GET", f"invoice/{invoice.quickbooks_invoice_id}")).get("Invoice")
        if not current or str(current.get("Id")) != str(invoice.quickbooks_invoice_id):
            _fail("Persisted gross invoice is unavailable")
    else:
        rows = await r._query(connection, f"select * from Invoice where DocNumber = '{r._escape_query(r._qbo_invoice_document_number(invoice))}' maxresults 2")
        if len(rows) > 1:
            _fail("Gross invoice number is ambiguous")
        current = rows[0] if rows else None
    for retry in range(3):
        if current:
            r._validate_qbo_invoice_identity(current, qbo_customer_id=customer_id, invoice=invoice,
                discovered_by_doc_number=not bool(invoice.quickbooks_invoice_id), tenant_name=tenant_name)
            actual = invoice_semantics(current)
            if actual == desired:
                break
            if previous is None or actual != previous:
                _fail("QuickBooks invoice has unexpected edits; gross update was not applied")
            if current.get("SyncToken") is None:
                _fail("QuickBooks gross invoice lacks a SyncToken")
            await _assert_open_period(connection,current)
            write = {"Id": str(current["Id"]), "SyncToken": str(current["SyncToken"]),
                     "sparse": True, "Line": payload["Line"], "TxnTaxDetail": payload["TxnTaxDetail"]}
            # Preserve existing line IDs only for the same owned description.
            ids = {str(l.get("Description")): l.get("Id") for l in current.get("Line", [])}
            for line in write["Line"]:
                if ids.get(line["Description"]):
                    line["Id"] = ids[line["Description"]]
            route = "invoice?operation=update"
        else:
            write, route = payload, "invoice"
            await _assert_open_period(connection,write)
        try:
            response = await r._request(connection, "POST", route, json=write,
                params={"requestid": r._qbo_request_id("grossinv", f"{invoice.id}:{revision}")})
        except r.QuickBooksAccountingError as exc:
            if not current or exc.status_code != 400 or exc.fault_code != 5010 or retry == 2:
                raise
            current = (await r._request(connection, "GET", f"invoice/{current['Id']}")).get("Invoice")
            continue
        result = response.get("Invoice") or {}
        if not result.get("Id") or (current and str(result["Id"]) != str(current["Id"])):
            _fail("QuickBooks did not confirm the canonical gross invoice")
        current = (await r._request(connection, "GET", f"invoice/{result['Id']}")).get("Invoice")
        if not current or str(current.get("Id")) != str(result["Id"]) or invoice_semantics(current) != desired:
            _fail("QuickBooks invoice readback differs from the earned fee/tax projection")
        r._validate_qbo_invoice_identity(current, qbo_customer_id=customer_id, invoice=invoice,
                                         discovered_by_doc_number=True, tenant_name=tenant_name)
        break
    else:
        _fail("QuickBooks gross invoice update exhausted its bounded retries")
    invoice.quickbooks_invoice_id = str(current["Id"])
    invoice.quickbooks_sync_status = "synced"
    invoice.quickbooks_synced_at = datetime.now(timezone.utc)
    invoice.quickbooks_sync_error = None
    settlement.accounting_projection_revision = revision
    settlement.accounting_projection_snapshot = dict(settlement.accounting_projection_snapshot or {},
                                                     invoice=desired, realm=str(connection.realm_id))
    returned_ids = {str(line.get("Description")): str(line["Id"])
                    for line in current.get("Line", []) if line.get("Id")}
    settlement.accounting_fee_line_ids = {key: returned_ids[mapping["_fee_description"]]
        for key, member, mapping in components if member.fee and mapping["_fee_description"] in returned_ids}
    await db.flush()
    return str(customer_id), str(current["Id"])


def validate_payment(entity, *, envelope, customer_id, invoice_id, gross, allocation, deposit_account):
    r = _r()
    _usd_exchange(entity)
    lines = entity.get("Line") or []
    expected_lines = [] if not allocation else [(str(invoice_id), _amount(allocation))]
    actual_lines = []
    for line in lines:
        txns = line.get("LinkedTxn") or []
        if len(txns) != 1 or txns[0].get("TxnType") != "Invoice":
            _fail("Gross receipt has an unexpected allocation")
        actual_lines.append((str(txns[0].get("TxnId")), _amount(line.get("Amount"))))
    if (_ref(entity, "CustomerRef") != customer_id
            or (_ref(entity, "CurrencyRef") or "USD") != "USD"
            or _ref(entity, "DepositToAccountRef") != deposit_account
            or _amount(entity.get("TotalAmt")) != _amount(gross)
            or _amount(entity.get("UnappliedAmt")) != _amount(gross - allocation)
            or actual_lines != expected_lines
            or str(entity.get("PaymentRefNum") or "") != r.db048_qbo_payment_reference(attempt=envelope.attempt, payment=envelope.payment)
            or not r._qbo_payment_note_matches(entity.get("PrivateNote"), attempt=envelope.attempt,
                payment=envelope.payment, invoice=envelope.invoice)):
        _fail("Gross receipt identity, allocation, or unapplied money does not match")


async def _deposit_account(envelope):
    key = {"stripe_connect": "stripe_clearing_account", "quickbooks_payments": "qbp_clearing_account"}.get(
        envelope.attempt.provider, "check_deposit_account" if envelope.attempt.rail in {"check", "fleet_payment"} else "zelle_ach_account")
    return await _r()._resolve_qbo_account_reference(envelope.connection, (envelope.link.account_mapping_snapshot or {}).get(key))


@accounting_operation
async def sync_gross_payment(db, envelope):
    from app.services.invoice_accounting_policy import require_exportable_invoice
    await require_exportable_invoice(envelope.invoice)
    r = _r()
    await _locked_settlement(db,envelope.settlement)
    from sqlalchemy import inspect
    if inspect(envelope.link,raiseerr=False) is not None:
        persisted=await db.scalar(select(PaymentAccountingLink).where(
            PaymentAccountingLink.id==envelope.link.id,
            PaymentAccountingLink.tenant_id==envelope.tenant.id,
            PaymentAccountingLink.attempt_id==envelope.attempt.id,
        ).with_for_update().execution_options(populate_existing=True))
        if persisted is None:
            _fail("Gross accounting operation disappeared")
        if persisted.sync_state=="synced":
            if not persisted.provider_object_id:
                _fail("Gross accounting replay lacks its receipt identity")
            return str(persisted.provider_object_id)
    customer_id, invoice_id = await ensure_gross_invoice(db, connection=envelope.connection,
        invoice=envelope.invoice, customer=envelope.customer, settlement=envelope.settlement,
        tenant_name=envelope.tenant.name, original_attempt_id=envelope.attempt.id)
    gross = _amount(envelope.attempt.provider_charge_amount)
    allocation = sum(map(_amount, (envelope.attempt.applied_principal_amount,
        envelope.attempt.applied_card_fee_amount, envelope.attempt.applied_card_fee_tax_amount)), Decimal(0))
    if gross - allocation != _amount(envelope.attempt.unapplied_amount):
        _fail("Gross capture does not reconcile to earned allocation and excess")
    deposit = await _deposit_account(envelope)
    payment_id = envelope.payment.quickbooks_payment_id
    if payment_id:
        current = (await r._request(envelope.connection, "GET", f"payment/{payment_id}")).get("Payment") or {}
        if str(current.get("Id")) != str(payment_id):
            _fail("Persisted gross receipt is unavailable")
    else:
        reference = r.db048_qbo_payment_reference(attempt=envelope.attempt, payment=envelope.payment)
        rows = await r._query(envelope.connection,
            f"select * from Payment where PaymentRefNum = '{r._escape_query(reference)}' maxresults 2")
        if len(rows) > 1:
            _fail("Gross receipt reference is ambiguous")
        current = rows[0] if rows else None
        if current is None:
            payload = r.db048_qbo_payment_payload(payment=envelope.payment, invoice=envelope.invoice,
                qbo_customer_id=customer_id, qbo_invoice_id=invoice_id, principal_amount=allocation,
                received_principal_amount=gross, deposit_account=deposit, attempt=envelope.attempt)
            payload["TxnDate"]=(getattr(envelope.attempt,"confirmed_at",None) or datetime.now(timezone.utc)).date().isoformat()
            await _assert_open_period(envelope.connection,payload)
            response = await r._request(envelope.connection, "POST", "payment", json=payload,
                params={"requestid": r._qbo_request_id("grosspay", envelope.attempt.id)})
            created = response.get("Payment") or {}
            if not created.get("Id"):
                _fail("QuickBooks did not return the gross receipt")
            current = (await r._request(envelope.connection, "GET", f"payment/{created['Id']}")).get("Payment") or {}
            if str(current.get("Id")) != str(created["Id"]):
                _fail("QuickBooks gross receipt readback identity does not match create")
    validate_payment(current, envelope=envelope, customer_id=customer_id, invoice_id=invoice_id,
                     gross=gross, allocation=allocation, deposit_account=deposit)
    envelope.payment.quickbooks_payment_id = str(current["Id"])
    envelope.payment.quickbooks_reconciled_at = datetime.now(timezone.utc)
    envelope.payment.quickbooks_sync_error = None
    # The same receipt can acquire genuine excess after a dispute recovery.
    envelope.link.provider_deposit_id = str(current["Id"])
    return str(current["Id"])


def _receipt_deposit_matches(entity, expected, *, allow_empty_zero=False):
    actual = _ref(entity, "DepositToAccountRef")
    if actual == str(expected):
        return True
    # QBO omits the deposit account after a receipt becomes exactly zero.
    # This is not an exemption for positive, allocated, or unapplied money.
    return (allow_empty_zero and entity.get("DepositToAccountRef") is None and entity.get("Line") == []
            and "TotalAmt" in entity and "UnappliedAmt" in entity
            and _amount(entity["TotalAmt"]) == 0 and _amount(entity["UnappliedAmt"]) == 0)


async def _source_deposit_account(envelope, source):
    key = {"stripe_connect":"stripe_clearing_account", "quickbooks_payments":"qbp_clearing_account"}.get(
        envelope.attempt.provider,"check_deposit_account" if envelope.attempt.rail in {"check", "fleet_payment"} else "zelle_ach_account")
    return await _r()._resolve_qbo_account_reference(envelope.connection,(source.account_mapping_snapshot or {}).get(key))


async def _gross_source(db, envelope, *, allow_empty_zero_deposit=False):
    r = _r()
    await _locked_settlement(db, envelope.settlement)
    source = await db.scalar(select(PaymentAccountingLink).where(
        PaymentAccountingLink.tenant_id == envelope.tenant.id,
        PaymentAccountingLink.invoice_id == envelope.invoice.id,
        PaymentAccountingLink.attempt_id == envelope.attempt.id,
        PaymentAccountingLink.financial_object_type == "invoice_payment",
        PaymentAccountingLink.operation_version == 1,
    ))
    payment_id = envelope.payment.quickbooks_payment_id
    if (not source or source.sync_state != "synced" or not payment_id
            or source.provider_object_id != payment_id
            or source.qbo_realm_snapshot != envelope.connection.realm_id):
        raise r.DB048ReconciliationError("Original gross receipt is not synchronized yet", retryable=True)
    entity = (await r._request(envelope.connection, "GET", f"payment/{payment_id}")).get("Payment") or {}
    _usd_exchange(entity)
    customer_id = await r.ensure_customer(envelope.connection, envelope.customer, tenant_name=envelope.tenant.name)
    deposit = await _source_deposit_account(envelope,source)
    if (str(entity.get("Id")) != str(payment_id)
            or _ref(entity, "CustomerRef") != str(customer_id)
            or not _receipt_deposit_matches(entity,deposit,allow_empty_zero=allow_empty_zero_deposit)
            or (_ref(entity, "CurrencyRef") or "USD") != "USD"
            or str(entity.get("PaymentRefNum") or "") != r.db048_qbo_payment_reference(attempt=envelope.attempt, payment=envelope.payment)
            or not r._qbo_payment_note_matches(entity.get("PrivateNote"), attempt=envelope.attempt,
                payment=envelope.payment, invoice=envelope.invoice)):
        _fail("Gross adjustment source identity does not match")
    return source, entity, str(customer_id)


@accounting_operation
async def sync_gross_refund(db, envelope):
    """Return only genuine excess; earned invoice income is never reversed."""
    from app.services.invoice_accounting_policy import require_exportable_invoice
    await require_exportable_invoice(envelope.invoice)
    r = _r()
    await _locked_settlement(db,envelope.settlement)
    refund = envelope.refund
    if refund is None or refund.state != "succeeded":
        _fail("Gross excess refund source is missing")
    changes = await _attempt_changes(db,envelope.attempt,envelope.connection.realm_id)
    gross = _amount(envelope.attempt.provider_charge_amount) + sum((c["gross"] for c in changes),Decimal(0))
    allocation = sum(map(_amount,(envelope.attempt.applied_principal_amount,
        envelope.attempt.applied_card_fee_amount,envelope.attempt.applied_card_fee_tax_amount)),Decimal(0))
    allocation += sum((c["principal"]+c["fee"]+c["tax"] for c in changes),Decimal(0))
    from app.services.db048_gross_credit_accounting import gross_credit_allocations
    credits = await gross_credit_allocations(db,attempt=envelope.attempt,tenant=envelope.tenant,
                                             connection=envelope.connection,ensure_invoices=False)
    excess = gross-allocation-sum(credits.values(),Decimal(0))
    overpayment = await db.scalar(select(PaymentOverpayment).where(
        PaymentOverpayment.id == refund.overpayment_id,
        PaymentOverpayment.tenant_id == envelope.tenant.id,
        PaymentOverpayment.source_attempt_id == envelope.attempt.id,
    ))
    refunds = (await db.execute(select(PaymentRefund).where(
        PaymentRefund.tenant_id == envelope.tenant.id,
        PaymentRefund.source_attempt_id == envelope.attempt.id,
        PaymentRefund.state.in_(["succeeded", "pending", "manual_action_required", "failed"]),
    ))).scalars().all()
    if (not overpayment or _amount(refund.amount) <= 0 or _amount(overpayment.amount) > gross-allocation
            or sum((_amount(item.amount) for item in refunds), Decimal(0)) > excess):
        _fail("Refund exceeds genuine gross receipt excess")
    source, payment, customer_id = await _gross_source(db, envelope)
    mappings = source.account_mapping_snapshot or {}
    key = {"stripe_connect": "stripe_clearing_account", "quickbooks_payments": "qbp_clearing_account"}.get(
        envelope.attempt.provider, "check_deposit_account" if envelope.attempt.rail in {"check", "fleet_payment"} else "zelle_ach_account")
    account = await r._resolve_qbo_account_reference(envelope.connection, mappings.get(key))
    accounts = await r._query(envelope.connection,
        "select * from Account where AccountType = 'Accounts Receivable' maxresults 2")
    if len(accounts) != 1 or not accounts[0].get("Id"):
        _fail("Gross refund Accounts Receivable mapping is ambiguous")
    payload = r.db048_qbo_overpayment_refund_payload(refund=refund,
        qbo_customer_id=customer_id, receivable_account=str(accounts[0]["Id"]), source_account=account)
    payload["TxnDate"]=(refund.completed_at or datetime.now(timezone.utc)).date().isoformat()
    payload["PrivateNote"] = f"DB-048 refund={refund.id}; unapplied customer overpayment"
    current = await r._qbo_find_by_doc_number(envelope.connection, "JournalEntry", payload["DocNumber"])
    if current is None:
        await _assert_open_period(envelope.connection,payload)
        response = await r._request(envelope.connection, "POST", "journalentry", json=payload,
            params={"requestid": r._qbo_request_id("grossref", refund.id)})
        created = response.get("JournalEntry") or {}
        if not created.get("Id"):
            _fail("QuickBooks did not confirm the excess refund")
        current = (await r._request(envelope.connection, "GET", f"journalentry/{created['Id']}")).get("JournalEntry") or {}
        if str(current.get("Id"))!=str(created["Id"]):
            _fail("QuickBooks refund readback identity differs from create")
    if (not current.get("Id") or current.get("PrivateNote") != payload["PrivateNote"]
            or refund_semantics(current) != refund_semantics(payload)):
        _fail("Gross refund journal does not match its exact excess reversal")
    return str(current["Id"])


def refund_semantics(entity):
    if (_ref(entity, "CurrencyRef") or "USD") != "USD" or Decimal(str(entity.get("ExchangeRate", 1))) != 1:
        _fail("Gross refund currency does not match")
    lines = []
    for line in entity.get("Line") or []:
        detail = line.get("JournalEntryLineDetail") or {}
        customer = detail.get("Entity") or {}
        if line.get("DetailType") != "JournalEntryLineDetail":
            _fail("Gross refund has an unexpected journal line")
        lines.append((str(detail.get("PostingType")), _ref(detail, "AccountRef"),
            str(_amount(line.get("Amount"))), str(customer.get("Type") or ""),
            _ref(customer, "EntityRef")))
    return (str(entity.get("DocNumber")), sorted(lines))


def _payment_state(entity):
    lines = []
    for line in entity.get("Line") or []:
        linked = line.get("LinkedTxn") or []
        if len(linked) != 1 or linked[0].get("TxnType") != "Invoice":
            _fail("Gross adjustment contains an unexpected payment allocation")
        amount = _amount(line.get("Amount"))
        if amount:
            lines.append((str(linked[0].get("TxnId")), str(amount)))
    if len({item[0] for item in lines}) != len(lines):
        _fail("Gross adjustment contains duplicate invoice allocations")
    return {"total": str(_amount(entity.get("TotalAmt"))), "lines": sorted(lines),
            "unapplied": str(_amount(entity.get("UnappliedAmt", 0)))}


@accounting_operation
async def sync_gross_adjustment(db, envelope, *, reversal=False):
    from app.services.invoice_accounting_policy import require_exportable_invoice
    await require_exportable_invoice(envelope.invoice)
    """Absolute receipt state makes duplicate/out-of-order deliveries converge.

    No delta is blindly replayed and no fee income journal is emitted. The
    original invoice keeps its principal; only earned fee obligations change.
    """
    r = _r()
    await _locked_settlement(db, envelope.settlement)
    original_gross = _amount(envelope.attempt.provider_charge_amount)
    original_allocation = sum(map(_amount, (envelope.attempt.applied_principal_amount,
        envelope.attempt.applied_card_fee_amount, envelope.attempt.applied_card_fee_tax_amount)), Decimal(0))
    invoice_id = str(envelope.invoice.quickbooks_invoice_id or "")
    if not invoice_id:
        _fail("Gross adjustment has no canonical invoice")
    changes = await _attempt_changes(db, envelope.attempt, envelope.connection.realm_id)
    desired_total = original_gross + sum((c["gross"] for c in changes), Decimal(0))
    desired_allocation = original_allocation + sum((c["principal"] + c["fee"] + c["tax"] for c in changes), Decimal(0))
    refunds = (await db.execute(select(PaymentRefund).where(
        PaymentRefund.tenant_id == envelope.tenant.id,
        PaymentRefund.source_attempt_id == envelope.attempt.id,
        PaymentRefund.state.in_(["succeeded", "pending", "manual_action_required", "failed"]),
    ))).scalars().all()
    refunded = sum((_amount(item.amount) for item in refunds), Decimal(0))
    if refunded > desired_total - desired_allocation:
        _fail("Gross adjustment conflicts with already refunded excess")
    if desired_total < 0 or desired_allocation < 0 or desired_allocation > desired_total:
        _fail("Gross dispute components exceed the original receipt")
    source, current, customer_id = await _gross_source(db, envelope, allow_empty_zero_deposit=True)
    invoice_before = (envelope.settlement.accounting_projection_snapshot or {}).get("invoice") or {}
    # Tax mapping/readback must agree before changing the gross receipt.
    await ensure_gross_invoice(db, connection=envelope.connection, invoice=envelope.invoice,
        customer=envelope.customer, settlement=envelope.settlement, tenant_name=envelope.tenant.name)
    from app.services.db048_gross_credit_accounting import gross_credit_allocations
    targets = await gross_credit_allocations(db, attempt=envelope.attempt,
        tenant=envelope.tenant, connection=envelope.connection)
    if desired_allocation:
        targets[invoice_id] = targets.get(invoice_id, Decimal(0)) + desired_allocation
    allocated = sum(targets.values(), Decimal(0))
    if allocated + refunded > desired_total:
        _fail("Gross adjustment credit and refunds exceed retained receipt")
    snapshots = dict(envelope.settlement.accounting_projection_snapshot or {})
    adjustments = dict(snapshots.get("payments") or {})
    previous = adjustments.get(str(envelope.attempt.id))
    original_state = {"total": str(original_gross),
                      "lines": [(invoice_id, str(original_allocation))] if original_allocation else [],
                      "unapplied": str(original_gross - original_allocation)}
    desired_state = {"total": str(desired_total),
                     "lines": [(key, str(_amount(value))) for key,value in sorted(targets.items())],
                     "unapplied": str(desired_total - allocated)}
    payment_id = str(current["Id"])
    expected_reference = current.get("PaymentRefNum")
    expected_note = current.get("PrivateNote")
    expected_deposit = str(await _source_deposit_account(envelope,source))
    def check_identity(entity):
        if (str(entity.get("Id")) != payment_id or _ref(entity,"CustomerRef") != customer_id
                or entity.get("PaymentRefNum") != expected_reference or entity.get("PrivateNote") != expected_note
                or not _receipt_deposit_matches(entity,expected_deposit,allow_empty_zero=True)
                or (_ref(entity,"CurrencyRef") or "USD") != "USD"
                or Decimal(str(entity.get("ExchangeRate",1))) != 1):
            _fail("Gross adjustment readback identity changed")
    # JSON persists tuples as lists; compare canonical encodings.
    canonical = lambda value: json.dumps(value, sort_keys=True)
    allowed_states = {canonical(original_state), canonical(previous)}
    # QBO can cap this receipt's allocation and advance its SyncToken as a
    # side-effect of our signed invoice reduction. Permit only that exact cap:
    # same gross, same unrelated allocations, released cents become unapplied.
    # Derive it from persisted expected states, NEVER from arbitrary readback.
    for expected in (original_state, previous):
        if expected is None:
            continue
        for invoice_snapshot in (invoice_before, snapshots.get("invoice") or {}):
            if invoice_snapshot.get("total") is None:
                continue
            cap = _amount(invoice_snapshot["total"])
            lines = [(key, _amount(value)) for key, value in expected["lines"]]
            released = sum((max(Decimal(0), value-cap) for key,value in lines if key == invoice_id), Decimal(0))
            if released:
                clipped = {"total": expected["total"],
                           "lines": [(key,str(min(value,cap) if key == invoice_id else value))
                                     for key,value in lines if key != invoice_id or cap],
                           "unapplied": str(_amount(expected["unapplied"])+released)}
                allowed_states.add(canonical(clipped))
    # The invoice update can mutate linked Payment state. Fetch a fresh token
    # and validate it against the original identity and exact allowed states.
    current = (await r._request(envelope.connection, "GET", f"payment/{payment_id}")).get("Payment") or {}
    for retry in range(3):
        check_identity(current)
        actual = _payment_state(current)
        if canonical(actual) == canonical(desired_state):
            break
        if canonical(actual) not in allowed_states:
            _fail("QuickBooks gross receipt has unexpected adjustments")
        if current.get("SyncToken") is None:
            _fail("QuickBooks gross receipt lacks a SyncToken")
        await _assert_open_period(envelope.connection,current)
        lines = [{"Amount": float(value), "LinkedTxn": [{"TxnId": key, "TxnType": "Invoice"}]}
                 for key,value in sorted(targets.items())]
        payload = r._qbo_payment_update_payload(current, total_amount=desired_total,
                                                lines=lines, note=current["PrivateNote"])
        # Restore the frozen original clearing account when recovering from a
        # zero receipt whose provider representation omitted that reference.
        payload["DepositToAccountRef"] = {"value": expected_deposit}
        if reversal:
            route, payload = "payment?operation=void", {"Id": str(current["Id"]), "SyncToken": str(current["SyncToken"])}
        else:
            route = "payment?operation=update"
        revision = hashlib.sha256(canonical(desired_state).encode()).hexdigest()
        try:
            await r._request(envelope.connection, "POST", route, json=payload,
                params={"requestid": r._qbo_request_id("grossadj", f"{envelope.attempt.id}:{revision}")})
        except r.QuickBooksAccountingError as exc:
            if exc.status_code != 400 or exc.fault_code != 5010 or retry == 2:
                raise
        current = (await r._request(envelope.connection, "GET", f"payment/{current['Id']}")).get("Payment") or {}
        check_identity(current)
        if canonical(_payment_state(current)) == canonical(desired_state):
            break  # The third successful POST must be acknowledged as well.
    else:
        _fail("QuickBooks gross adjustment exhausted its bounded retries")
    check_identity(current)
    if canonical(_payment_state(current)) != canonical(desired_state):
        _fail("QuickBooks gross adjustment readback does not match")
    adjustments[str(envelope.attempt.id)] = desired_state
    snapshots["payments"] = adjustments
    envelope.settlement.accounting_projection_snapshot = snapshots
    return str(current["Id"])


@accounting_operation
async def deliver_gross_envelope(db, envelope):
    if envelope.config.writer_strategy != "dieselbridge" or envelope.link.owning_writer != "dieselbridge":
        _fail("Gross accounting requires the persisted DieselBridge writer")
    kind = envelope.link.financial_object_type
    if kind in {"payment_dispute", "payment_dispute_recovery", "payment_reversal"}:
        return await sync_gross_adjustment(db, envelope, reversal=kind == "payment_reversal")
    if envelope.refund:
        return await sync_gross_refund(db, envelope)
    return await sync_gross_payment(db, envelope)
