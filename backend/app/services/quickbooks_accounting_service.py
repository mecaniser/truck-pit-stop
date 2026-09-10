"""QuickBooks Online accounting synchronization.

DieselBridge remains the operational source of truth. These helpers create the
minimum QBO accounting mirror needed to reconcile an invoice, its captured
payment, and any refund. Every provider object is anchored by a stable local
identifier so retries do not intentionally create duplicates.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any, Optional

import httpx

from app.core.config import settings
from app.core.quickbooks_crypto import QuickBooksTokenEncryptionError, decrypt_quickbooks_token
from app.db.models.customer import Customer
from app.db.models.invoice import Invoice
from app.db.models.payment import Payment
from app.db.models.quickbooks_connection import QuickBooksConnection


class QuickBooksAccountingError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        retryable: bool = False,
        status_code: int | None = None,
        fault_code: int | None = None,
    ):
        super().__init__(message)
        self.retryable = retryable
        self.status_code = status_code
        self.fault_code = fault_code


def accounting_base_url() -> str:
    environment = settings.QUICKBOOKS_ACCOUNTING_ENVIRONMENT.strip().lower()
    if environment == "sandbox":
        return "https://sandbox-quickbooks.api.intuit.com"
    if environment == "production":
        return "https://quickbooks.api.intuit.com"
    raise QuickBooksAccountingError("QuickBooks Accounting environment must be sandbox or production")


def _escape_query(value: str) -> str:
    return value.replace("\\", "\\\\").replace("'", "\\'")


async def _request(
    connection: QuickBooksConnection,
    method: str,
    resource: str,
    *,
    json: dict[str, Any] | None = None,
    params: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if not connection.realm_id or not connection.encrypted_access_token:
        raise QuickBooksAccountingError("QuickBooks connection is unavailable")
    try:
        access_token = decrypt_quickbooks_token(connection.encrypted_access_token)
    except QuickBooksTokenEncryptionError as exc:
        raise QuickBooksAccountingError("QuickBooks credentials could not be read") from exc

    url = f"{accounting_base_url()}/v3/company/{connection.realm_id}/{resource.lstrip('/')}"
    query = {"minorversion": settings.QUICKBOOKS_MINOR_VERSION, **(params or {})}
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(settings.QUICKBOOKS_HTTP_TIMEOUT_SECONDS)) as client:
            response = await client.request(
                method,
                url,
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Accept": "application/json",
                    "Content-Type": "application/json",
                },
                params=query,
                json=json,
            )
    except (httpx.TimeoutException, httpx.NetworkError, httpx.RemoteProtocolError) as exc:
        raise QuickBooksAccountingError("Could not reach QuickBooks Accounting", retryable=True) from exc

    if response.status_code >= 400:
        retryable = response.status_code == 429 or response.status_code >= 500
        # Retain only a single bounded numeric provider code. Never propagate
        # Fault Message/Detail, which can echo credentials or customer values.
        fault_code = None
        try:
            failure = response.json()
            fault = failure.get("Fault") if isinstance(failure, dict) else None
            errors = fault.get("Error") if isinstance(fault, dict) else None
            code = errors[0].get("code") if isinstance(errors, list) and len(errors) == 1 and isinstance(errors[0], dict) else None
            if isinstance(code, str) and 1 <= len(code) <= 8 and all("0" <= char <= "9" for char in code):
                fault_code = int(code)
        except ValueError:
            pass
        raise QuickBooksAccountingError(
            f"QuickBooks Accounting returned HTTP {response.status_code}",
            retryable=retryable,
            status_code=response.status_code,
            fault_code=fault_code,
        )
    try:
        payload = response.json()
    except ValueError as exc:
        raise QuickBooksAccountingError("QuickBooks Accounting returned invalid JSON", retryable=True) from exc
    if not isinstance(payload, dict):
        raise QuickBooksAccountingError("QuickBooks Accounting returned an invalid response")
    return payload


async def get_company_identity(connection: QuickBooksConnection) -> dict[str, Any]:
    """Read allowlisted business identity without refreshing or changing a connection."""
    payload = await _request(connection, "GET", f"companyinfo/{connection.realm_id}")
    company = payload.get("CompanyInfo")
    if not isinstance(company, dict) or not company:
        raise QuickBooksAccountingError("QuickBooks company identity is unavailable")

    def text(value: Any, limit: int = 256) -> str | None:
        if not isinstance(value, str):
            return None
        return " ".join(value.split())[:limit] or None

    address = company.get("CompanyAddr")
    address = address if isinstance(address, dict) else {}
    lines = [text(address.get(f"Line{number}")) for number in range(1, 6)]
    locality = [text(address.get(key), 100) for key in ("City", "CountrySubDivisionCode", "PostalCode")]
    lines.extend([", ".join(value for value in locality if value), text(address.get("Country"), 100)])
    email = company.get("Email")
    phone = company.get("PrimaryPhone")
    identity = {
        "name": text(company.get("CompanyName")),
        "legal_name": text(company.get("LegalName")),
        "address_lines": [line for line in lines if line],
        "email": text(email.get("Address")) if isinstance(email, dict) else None,
        "phone": text(phone.get("FreeFormNumber"), 64) if isinstance(phone, dict) else None,
    }
    if not any(identity.values()):
        raise QuickBooksAccountingError("QuickBooks company identity is unavailable")
    return identity


async def _query(connection: QuickBooksConnection, statement: str) -> list[dict[str, Any]]:
    payload = await _request(connection, "GET", "query", params={"query": statement})
    query_response = payload.get("QueryResponse")
    if not isinstance(query_response, dict):
        return []
    for value in query_response.values():
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
    return []


async def change_data_capture(
    connection: QuickBooksConnection,
    *,
    changed_since: datetime,
) -> dict[str, list[dict[str, Any]]]:
    """Fetch changed entities to recover deliveries missed during an outage."""
    payload = await _request(
        connection,
        "GET",
        "cdc",
        params={
            "entities": "Customer,Invoice,Payment,RefundReceipt",
            "changedSince": changed_since.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
        },
    )
    collected: dict[str, list[dict[str, Any]]] = {}
    responses = payload.get("CDCResponse")
    if not isinstance(responses, list):
        return collected
    for response in responses:
        query_response = response.get("QueryResponse") if isinstance(response, dict) else None
        if not isinstance(query_response, dict):
            continue
        for entity_name, entities in query_response.items():
            if isinstance(entities, list):
                collected.setdefault(entity_name, []).extend(
                    entity for entity in entities if isinstance(entity, dict)
                )
    return collected


async def qbp_settlement_window(
    connection: QuickBooksConnection,
    *,
    date_from: date,
    date_to: date,
    page_size: int = 1000,
) -> dict[str, list[dict[str, Any]]]:
    """Read authoritative QBO payout and fee records for a bounded window.

    Deposit and Purchase are queried together instead of relying on their CDC
    delivery order. QuickBooks can publish a deposit before its processor-fee
    Purchase, so an overlapping window lets the importer observe both before
    freezing the settlement manifest.
    """
    if date_from > date_to:
        raise QuickBooksAccountingError("QuickBooks settlement date range is invalid")
    if page_size < 1 or page_size > 1000:
        raise QuickBooksAccountingError("QuickBooks settlement page size is invalid")

    collected: dict[str, list[dict[str, Any]]] = {
        "Deposit": [],
        "Purchase": [],
    }
    for entity_name in collected:
        start_position = 1
        while True:
            statement = (
                f"select * from {entity_name} "
                f"where TxnDate >= '{date_from.isoformat()}' "
                f"and TxnDate <= '{date_to.isoformat()}' "
                f"startposition {start_position} maxresults {page_size}"
            )
            page = await _query(connection, statement)
            collected[entity_name].extend(page)
            if len(page) < page_size:
                break
            start_position += page_size
    return collected


def _customer_display_name(customer: Customer) -> str:
    """Return the customer-facing QBO name without platform identifiers."""
    natural = (customer.company_name or f"{customer.first_name} {customer.last_name}").strip()
    return natural[:100] or "Customer"


def _legacy_customer_display_name(customer: Customer) -> str:
    natural = _customer_display_name(customer)
    return f"{natural[:75]} · DB-{str(customer.id)[:8]}"


def _tenant_customer_disambiguator(customer: Customer, tenant_name: Optional[str]) -> str:
    words = [word for word in str(tenant_name or "").split() if word and word[0].isalpha()]
    shop_prefix = "".join(word[0] for word in words[:3]).upper() or "SHOP"
    suffix = f" · {shop_prefix}"
    return f"{_customer_display_name(customer)[:100 - len(suffix)]}{suffix}"


def _qbo_customer_matches(
    customer: Customer,
    candidate: dict[str, Any],
    *,
    tenant_name: Optional[str] = None,
) -> bool:
    """Recognize current and legacy customer mirrors without exposing IDs."""
    display_name = str(candidate.get("DisplayName") or "").strip()
    if display_name == _legacy_customer_display_name(customer):
        return True
    notes = str(candidate.get("Notes") or "")
    if str(customer.id) in notes:
        return True
    if display_name not in {
        _customer_display_name(customer),
        _tenant_customer_disambiguator(customer, tenant_name),
    }:
        return False
    qbo_email = str((candidate.get("PrimaryEmailAddr") or {}).get("Address") or "").strip().lower()
    local_email = str(customer.email or "").strip().lower()
    # A natural/company name is not a unique identity. When either side has an
    # email, require the addresses to agree so two customers with the same
    # company name cannot share a QBO Customer record.
    if local_email or qbo_email:
        return bool(local_email and qbo_email and qbo_email == local_email)
    qbo_company = str(candidate.get("CompanyName") or "").strip().casefold()
    return bool(customer.company_name and qbo_company == customer.company_name.strip().casefold())


def quickbooks_invoice_memo(
    invoice: Invoice,
    *,
    tenant_name: Optional[str] = None,
) -> str:
    tenant = invoice.__dict__.get("tenant")
    resolved_tenant_name = (
        str(tenant_name or "").strip()
        or str(getattr(tenant, "name", "") or "").strip()
        or "Shop"
    )
    return f"{resolved_tenant_name} invoice {invoice.invoice_number}"


async def ensure_customer(
    connection: QuickBooksConnection,
    customer: Customer,
    *,
    tenant_name: Optional[str] = None,
) -> str:
    display_name = _customer_display_name(customer)
    if customer.quickbooks_customer_id and customer.quickbooks_customer_id != "qb-linked":
        linked_id = str(customer.quickbooks_customer_id)
        linked = await _query(
            connection,
            f"select * from Customer where Id = '{_escape_query(linked_id)}' maxresults 1",
        )
        if (
            linked
            and str(linked[0].get("Id") or "") == linked_id
            and _qbo_customer_matches(
                customer,
                linked[0],
                tenant_name=tenant_name,
            )
        ):
            linked_customer = linked[0]
            current_name = str(linked_customer.get("DisplayName") or "").strip()
            legacy_notes = str(linked_customer.get("Notes") or "")
            clear_legacy_notes = str(customer.id) in legacy_notes
            if (
                (current_name != display_name or clear_legacy_notes)
                and linked_customer.get("SyncToken") is not None
            ):
                target_name = current_name
                natural_name_matches = await _query(
                    connection,
                    f"select * from Customer where DisplayName = '{_escape_query(display_name)}' maxresults 2",
                )
                if current_name != display_name:
                    target_name = display_name
                    if any(str(row.get("Id") or "") != linked_id for row in natural_name_matches):
                        target_name = _tenant_customer_disambiguator(customer, tenant_name)
                        disambiguated_matches = await _query(
                            connection,
                            "select * from Customer where DisplayName = "
                            f"'{_escape_query(target_name)}' maxresults 2",
                        )
                        if any(
                            str(row.get("Id") or "") != linked_id
                            for row in disambiguated_matches
                        ):
                            raise QuickBooksAccountingError(
                                "QuickBooks customer display name is already in use"
                            )
                update_payload = {
                    "Id": linked_id,
                    "SyncToken": str(linked_customer["SyncToken"]),
                    "sparse": True,
                    "DisplayName": target_name,
                }
                if clear_legacy_notes:
                    update_payload["Notes"] = ""
                response = await _request(
                    connection,
                    "POST",
                    "customer",
                    params={
                        "operation": "update",
                        "requestid": f"customer-name-{customer.id}"[:50],
                    },
                    json=update_payload,
                )
                updated = response.get("Customer") if isinstance(response, dict) else None
                if not isinstance(updated, dict) or str(updated.get("Id") or "") != linked_id:
                    raise QuickBooksAccountingError("QuickBooks did not update the synchronized customer")
            return linked_id

        # Customer IDs are scoped to a QBO company. A disconnected tenant may
        # later authorize a different company after the connection realm was
        # cleared, so never trust a persisted ID without its deterministic
        # DieselBridge display-name marker in the active realm.
        customer.quickbooks_customer_id = None

    matches = await _query(
        connection,
        f"select * from Customer where DisplayName = '{_escape_query(display_name)}' maxresults 1",
    )
    if matches:
        matching_customer = next(
            (
                row
                for row in matches
                if row.get("Id")
                and _qbo_customer_matches(customer, row, tenant_name=tenant_name)
            ),
            None,
        )
        if matching_customer:
            customer.quickbooks_customer_id = str(matching_customer["Id"])
            return customer.quickbooks_customer_id
        display_name = _tenant_customer_disambiguator(customer, tenant_name)
        disambiguated = await _query(
            connection,
            f"select * from Customer where DisplayName = '{_escape_query(display_name)}' maxresults 2",
        )
        if disambiguated:
            matching_customer = next(
                (
                    row
                    for row in disambiguated
                    if row.get("Id")
                    and _qbo_customer_matches(customer, row, tenant_name=tenant_name)
                ),
                None,
            )
            if matching_customer:
                customer.quickbooks_customer_id = str(matching_customer["Id"])
                return customer.quickbooks_customer_id
            raise QuickBooksAccountingError("QuickBooks customer display name is already in use")

    billing = {
        "Line1": customer.billing_address_line1,
        "Line2": customer.billing_address_line2,
        "City": customer.billing_city,
        "CountrySubDivisionCode": customer.billing_state,
        "PostalCode": customer.billing_zip,
        "Country": customer.billing_country or "US",
    }
    payload: dict[str, Any] = {
        "DisplayName": display_name,
        "GivenName": customer.first_name[:100],
        "FamilyName": customer.last_name[:100],
        "CompanyName": (customer.company_name or "")[:255] or None,
        "PrimaryEmailAddr": {"Address": customer.email[:255]},
        "PrimaryPhone": {"FreeFormNumber": customer.phone[:30]} if customer.phone else None,
        "BillAddr": {key: value for key, value in billing.items() if value},
    }
    payload = {key: value for key, value in payload.items() if value not in (None, {}, "")}
    response = await _request(
        connection,
        "POST",
        "customer",
        json=payload,
        params={"requestid": f"customer-{customer.id}"[:50]},
    )
    qbo_customer = response.get("Customer")
    if not isinstance(qbo_customer, dict) or not qbo_customer.get("Id"):
        raise QuickBooksAccountingError("QuickBooks did not return the synchronized customer")
    customer.quickbooks_customer_id = str(qbo_customer["Id"])
    return customer.quickbooks_customer_id


async def _ensure_service_item(connection: QuickBooksConnection) -> str:
    item_name = "DieselBridge Repair Services"
    items = await _query(
        connection,
        f"select * from Item where Name = '{_escape_query(item_name)}' maxresults 1",
    )
    if items and items[0].get("Id"):
        return str(items[0]["Id"])

    accounts = await _query(
        connection,
        "select * from Account where AccountType = 'Income' maxresults 1",
    )
    if not accounts or not accounts[0].get("Id"):
        raise QuickBooksAccountingError("QuickBooks company has no income account for invoice synchronization")
    response = await _request(
        connection,
        "POST",
        "item",
        json={
            "Name": item_name,
            "Type": "Service",
            "IncomeAccountRef": {"value": str(accounts[0]["Id"])},
            "Description": "Repair work synchronized from DieselBridge",
        },
    )
    item = response.get("Item")
    if not isinstance(item, dict) or not item.get("Id"):
        raise QuickBooksAccountingError("QuickBooks did not return the synchronization item")
    return str(item["Id"])


async def sync_invoice(
    connection: QuickBooksConnection,
    invoice: Invoice,
    customer: Customer,
) -> str:
    from app.services.invoice_accounting_policy import require_exportable_invoice
    await require_exportable_invoice(invoice)
    invoice_status = getattr(invoice.status, "value", invoice.status)
    if invoice_status == "cancelled":
        if not invoice.quickbooks_invoice_id:
            invoice.quickbooks_sync_status = "voided"
            invoice.quickbooks_synced_at = datetime.now(timezone.utc)
            invoice.quickbooks_sync_error = None
            return ""
        current = await _request(connection, "GET", f"invoice/{invoice.quickbooks_invoice_id}")
        qbo_invoice = current.get("Invoice")
        if not isinstance(qbo_invoice, dict) or not qbo_invoice.get("SyncToken"):
            raise QuickBooksAccountingError("QuickBooks invoice could not be loaded for voiding")
        await _request(
            connection,
            "POST",
            "invoice",
            params={"operation": "void"},
            json={"Id": invoice.quickbooks_invoice_id, "SyncToken": str(qbo_invoice["SyncToken"])},
        )
        invoice.quickbooks_sync_status = "voided"
        invoice.quickbooks_synced_at = datetime.now(timezone.utc)
        invoice.quickbooks_sync_error = None
        return invoice.quickbooks_invoice_id
    if invoice.quickbooks_invoice_id:
        return invoice.quickbooks_invoice_id
    if invoice.is_internal:
        raise QuickBooksAccountingError("Internal fleet invoices are not customer receivables")

    customer_id = await ensure_customer(connection, customer)
    matches = await _query(
        connection,
        f"select * from Invoice where DocNumber = '{_escape_query(invoice.invoice_number)}' maxresults 1",
    )
    if matches and matches[0].get("Id"):
        invoice.quickbooks_invoice_id = str(matches[0]["Id"])
    else:
        item_id = await _ensure_service_item(connection)
        description = quickbooks_invoice_memo(invoice)
        response = await _request(
            connection,
            "POST",
            "invoice",
            json={
                "DocNumber": invoice.invoice_number[:21],
                "CustomerRef": {"value": customer_id},
                "TxnDate": (invoice.created_at or datetime.now(timezone.utc)).date().isoformat(),
                "DueDate": invoice.due_date.date().isoformat() if invoice.due_date else None,
                "PrivateNote": description,
                "CustomerMemo": {"value": description},
                "Line": [{
                    "Amount": float(Decimal(invoice.total_amount).quantize(Decimal("0.01"))),
                    "Description": description,
                    "DetailType": "SalesItemLineDetail",
                    "SalesItemLineDetail": {
                        "ItemRef": {"value": item_id},
                        "Qty": 1,
                        "UnitPrice": float(Decimal(invoice.total_amount).quantize(Decimal("0.01"))),
                    },
                }],
            },
        )
        qbo_invoice = response.get("Invoice")
        if not isinstance(qbo_invoice, dict) or not qbo_invoice.get("Id"):
            raise QuickBooksAccountingError("QuickBooks did not return the synchronized invoice")
        invoice.quickbooks_invoice_id = str(qbo_invoice["Id"])

    invoice.quickbooks_sync_status = "synced"
    invoice.quickbooks_synced_at = datetime.now(timezone.utc)
    invoice.quickbooks_sync_error = None
    return invoice.quickbooks_invoice_id


async def sync_payment(
    connection: QuickBooksConnection,
    payment: Payment,
    invoice: Invoice,
    customer: Customer,
) -> str:
    if payment.invoice_payment_attempt_id is not None:
        raise QuickBooksAccountingError(
            "Canonical invoice payments must use their settlement accounting writer"
        )
    if payment.quickbooks_payment_id:
        return payment.quickbooks_payment_id
    invoice_id = await sync_invoice(connection, invoice, customer)
    customer_id = await ensure_customer(connection, customer)
    reference = payment.payment_number[:21]
    matches = await _query(
        connection,
        f"select * from Payment where PaymentRefNum = '{_escape_query(reference)}' maxresults 1",
    )
    if matches and matches[0].get("Id"):
        payment.quickbooks_payment_id = str(matches[0]["Id"])
    else:
        response = await _request(
            connection,
            "POST",
            "payment",
            json={
                "CustomerRef": {"value": customer_id},
                "TotalAmt": float(Decimal(payment.amount).quantize(Decimal("0.01"))),
                "PaymentRefNum": reference,
                "PrivateNote": (
                    f"{quickbooks_invoice_memo(invoice)} payment {payment.payment_number}; "
                    f"Intuit charge {payment.quickbooks_charge_id}"
                ),
                "Line": [{
                    "Amount": float(Decimal(payment.amount).quantize(Decimal("0.01"))),
                    "LinkedTxn": [{"TxnId": invoice_id, "TxnType": "Invoice"}],
                }],
            },
        )
        qbo_payment = response.get("Payment")
        if not isinstance(qbo_payment, dict) or not qbo_payment.get("Id"):
            raise QuickBooksAccountingError("QuickBooks did not return the synchronized payment")
        payment.quickbooks_payment_id = str(qbo_payment["Id"])
    payment.quickbooks_reconciled_at = datetime.now(timezone.utc)
    payment.quickbooks_sync_error = None
    return payment.quickbooks_payment_id


async def create_refund_receipt(
    connection: QuickBooksConnection,
    payment: Payment,
    invoice: Invoice,
    customer: Customer,
    *,
    refund_id: str,
    amount: Decimal,
) -> str:
    from app.services.invoice_accounting_policy import require_exportable_invoice
    await require_exportable_invoice(invoice)
    if payment.quickbooks_refund_receipt_id:
        return payment.quickbooks_refund_receipt_id
    document_number = f"R-{payment.payment_number}"[:21]
    matches = await _query(
        connection,
        f"select * from RefundReceipt where DocNumber = '{_escape_query(document_number)}' maxresults 1",
    )
    if matches and matches[0].get("Id"):
        payment.quickbooks_refund_receipt_id = str(matches[0]["Id"])
        payment.quickbooks_reconciled_at = datetime.now(timezone.utc)
        payment.quickbooks_sync_error = None
        return payment.quickbooks_refund_receipt_id
    customer_id = await ensure_customer(connection, customer)
    item_id = await _ensure_service_item(connection)
    response = await _request(
        connection,
        "POST",
        "refundreceipt",
        json={
            "DocNumber": document_number,
            "CustomerRef": {"value": customer_id},
            "TxnDate": datetime.now(timezone.utc).date().isoformat(),
            "PrivateNote": f"{quickbooks_invoice_memo(invoice)} refund",
            "TxnSource": "IntuitPayment",
            "CreditCardPayment": {
                "CreditChargeInfo": {"ProcessPayment": True},
                "CreditChargeResponse": {"CCTransId": refund_id},
            },
            "Line": [{
                "Amount": float(amount.quantize(Decimal("0.01"))),
                "Description": f"Refund for invoice {invoice.invoice_number}",
                "DetailType": "SalesItemLineDetail",
                "SalesItemLineDetail": {
                    "ItemRef": {"value": item_id},
                    "Qty": 1,
                    "UnitPrice": float(amount.quantize(Decimal("0.01"))),
                },
            }],
        },
    )
    receipt = response.get("RefundReceipt")
    if not isinstance(receipt, dict) or not receipt.get("Id"):
        raise QuickBooksAccountingError("QuickBooks did not return the refund receipt")
    payment.quickbooks_refund_receipt_id = str(receipt["Id"])
    payment.quickbooks_reconciled_at = datetime.now(timezone.utc)
    payment.quickbooks_sync_error = None
    return payment.quickbooks_refund_receipt_id
