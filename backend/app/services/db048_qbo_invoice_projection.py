"""Pure, opt-in gross-invoice values; not a provider payload or runtime writer.

Callers must supply immutable, confirmed-earned snapshots, never reservations or
legacy principal-only accounting links. Tax mapping, concurrency, provider writes,
refunds and historical migration deliberately remain outside this foundation.
The input type is not an eligibility or authorization check: callers must verify
confirmed state and access before constructing snapshots.
"""

from dataclasses import dataclass
from decimal import Decimal
import hashlib
import json
from typing import Iterable


COMPOSITION_VERSION = "gross_invoice_v1"
MAX_AMOUNT = Decimal("9999999999.99")
MAX_CENTS = 999999999999


@dataclass(frozen=True)
class InvoiceIdentity:
    tenant_id: str
    realm_id: str
    invoice_id: str


@dataclass(frozen=True)
class ConfirmedEarnedAttempt:
    identity: InvoiceIdentity
    attempt_id: str
    composition_version: str
    rail: str
    principal: Decimal
    fee: Decimal
    fee_tax: Decimal
    captured_gross: Decimal
    unapplied_excess: Decimal


@dataclass(frozen=True)
class PaymentProjection:
    attempt_id: str
    rail: str
    principal: Decimal
    fee: Decimal
    fee_tax: Decimal
    captured_gross: Decimal
    invoice_allocation: Decimal
    unapplied_excess: Decimal


@dataclass(frozen=True)
class InvoiceProjection:
    identity: InvoiceIdentity
    composition_version: str
    principal_base: Decimal
    invoice_total: Decimal
    remaining_principal: Decimal
    payments: tuple[PaymentProjection, ...]
    revision: str


def _identity(value: InvoiceIdentity) -> None:
    if not isinstance(value, InvoiceIdentity):
        raise ValueError("Invalid invoice identity")
    for field in (value.tenant_id, value.realm_id, value.invoice_id):
        if not isinstance(field, str) or not field or field.strip() != field:
            raise ValueError("Invoice identity fields must be nonempty canonical strings")


def _cents(value: Decimal) -> int:
    # Integer arithmetic avoids ambient Decimal precision rounding money/hashes.
    if not isinstance(value, Decimal) or not value.is_finite() or value < 0:
        raise ValueError("Amounts must be finite nonnegative Decimal values")
    if value > MAX_AMOUNT:
        raise ValueError("Amount exceeds NUMERIC(12,2) limit")
    if value.is_zero():
        return 0
    _, digits, exponent = value.as_tuple()
    if exponent < -2 and -exponent - 2 >= len(digits):
        raise ValueError("Amounts must have exact cent precision")
    coefficient = int("".join(map(str, digits)))
    if exponent >= -2:
        return coefficient * 10 ** (exponent + 2)
    divisor = 10 ** (-exponent - 2)
    cents, remainder = divmod(coefficient, divisor)
    if remainder:
        raise ValueError("Amounts must have exact cent precision")
    return cents


def _money(cents: int) -> Decimal:
    if not 0 <= cents <= MAX_CENTS:
        raise ValueError("Projected amount exceeds NUMERIC(12,2) limit")
    return Decimal(f"{cents // 100}.{cents % 100:02d}")


def project_gross_invoice(
    *,
    identity: InvoiceIdentity,
    composition_version: str,
    principal_base: Decimal,
    attempts: Iterable[ConfirmedEarnedAttempt],
) -> InvoiceProjection:
    """Project one canonical invoice and its separately traceable gross receipts.

    Rejects duplicate membership (including exact duplicates), foreign identity,
    legacy composition, overallocated principal and inconsistent excess. Revision
    identifies the complete monetary membership, not input/event delivery order.
    """
    _identity(identity)
    if composition_version != COMPOSITION_VERSION:
        raise ValueError("Unsupported invoice composition version")
    base = _cents(principal_base)
    seen: set[str] = set()
    members = []
    for attempt in attempts:
        if not isinstance(attempt, ConfirmedEarnedAttempt):
            raise ValueError("Expected confirmed-earned attempt snapshot")
        _identity(attempt.identity)
        if attempt.identity != identity:
            raise ValueError("Foreign tenant, realm or invoice")
        if attempt.composition_version != composition_version:
            raise ValueError("Unsupported attempt composition version")
        if attempt.rail not in {"card", "zelle", "check", "ach"}:
            raise ValueError("Unsupported payment rail")
        if (
            not isinstance(attempt.attempt_id, str)
            or not attempt.attempt_id
            or attempt.attempt_id.strip() != attempt.attempt_id
        ):
            raise ValueError("Invalid attempt identity")
        if attempt.attempt_id in seen:
            raise ValueError("Duplicate attempt identity")
        seen.add(attempt.attempt_id)
        principal, fee, tax, gross, excess = map(
            _cents,
            (attempt.principal, attempt.fee, attempt.fee_tax,
             attempt.captured_gross, attempt.unapplied_excess),
        )
        if gross != principal + fee + tax + excess:
            raise ValueError("Captured gross does not equal allocation plus actual excess")
        if not gross:
            raise ValueError("Confirmed capture must be positive")
        if not principal and (fee or tax):
            raise ValueError("Earned fee requires positive principal")
        if attempt.rail != "card" and (fee or tax):
            raise ValueError("Non-card payment cannot carry a card fee or fee tax")
        if tax and not fee:
            raise ValueError("Fee tax requires an earned fee")
        members.append((attempt.attempt_id, principal, fee, tax, gross, excess, attempt.rail))
    members.sort(key=lambda row: row[0])
    allocated = sum(row[1] for row in members)
    if allocated > base:
        raise ValueError("Principal over-allocation")
    invoice_total = base + sum(row[2] + row[3] for row in members)
    manifest = [composition_version, identity.tenant_id, identity.realm_id,
                identity.invoice_id, base, members]
    revision = hashlib.sha256(
        json.dumps(manifest, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    ).hexdigest()
    payments = tuple(
        PaymentProjection(
            attempt_id=attempt_id,
            rail=rail,
            principal=_money(principal), fee=_money(fee), fee_tax=_money(tax),
            captured_gross=_money(gross),
            invoice_allocation=_money(principal + fee + tax),
            unapplied_excess=_money(excess),
        )
        for attempt_id, principal, fee, tax, gross, excess, rail in members
    )
    return InvoiceProjection(
        identity=identity, composition_version=composition_version,
        principal_base=_money(base), invoice_total=_money(invoice_total),
        remaining_principal=_money(base - allocated), payments=payments,
        revision=revision,
    )
