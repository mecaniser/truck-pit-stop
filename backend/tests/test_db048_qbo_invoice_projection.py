from dataclasses import FrozenInstanceError, replace
from decimal import Decimal, localcontext

import pytest

from app.services.db048_qbo_invoice_projection import (
    COMPOSITION_VERSION,
    ConfirmedEarnedAttempt,
    InvoiceIdentity,
    project_gross_invoice,
)


D = Decimal
IDENTITY = InvoiceIdentity("tenant-1", "realm-1", "invoice-1")


def attempt(attempt_id="card-1", **changes):
    return replace(ConfirmedEarnedAttempt(
        identity=IDENTITY, attempt_id=attempt_id,
        composition_version=COMPOSITION_VERSION, rail="card",
        principal=D("200"), fee=D("6"), fee_tax=D("0"),
        captured_gross=D("206"), unapplied_excess=D("0"),
    ), **changes)


def project(attempts=(), **changes):
    values = dict(identity=IDENTITY, composition_version=COMPOSITION_VERSION,
                  principal_base=D("1000"), attempts=attempts)
    values.update(changes)
    return project_gross_invoice(**values)


def mixed():
    return [attempt(), attempt("card-2", principal=D("300"), fee=D("9"),
                              captured_gross=D("309")),
            attempt("card-3", principal=D("100"), fee=D("3"), captured_gross=D("103")),
            attempt("zelle-1", rail="zelle", principal=D("400"), fee=D("0"),
                    captured_gross=D("400"))]


def test_three_cards_and_zelle_one_invoice():
    result = project(mixed())
    assert result.principal_base == D("1000")
    assert result.invoice_total == D("1018")
    assert result.remaining_principal == D("0")
    assert [p.captured_gross for p in result.payments] == list(map(D, ["206", "309", "103", "400"]))
    assert sum(p.invoice_allocation for p in result.payments) == result.invoice_total
    assert sum(p.unapplied_excess for p in result.payments) == 0


def test_reordered_membership_has_identical_projection():
    assert project(mixed()) == project(reversed(mixed()))


def test_empty_and_zero_fee():
    assert project().invoice_total == D("1000")
    assert project().remaining_principal == D("1000")
    result = project([attempt(fee=D("0"), captured_gross=D("200"))])
    assert result.invoice_total == D("1000")
    assert result.remaining_principal == D("800")


def test_fee_tax_and_actual_excess_are_distinct():
    result = project([attempt(fee_tax=D("0.60"), captured_gross=D("211.60"),
                              unapplied_excess=D("5"))])
    payment = result.payments[0]
    assert result.invoice_total == D("1006.60")
    assert payment.invoice_allocation == D("206.60")
    assert payment.unapplied_excess == D("5")
    assert result.remaining_principal == D("800")


@pytest.mark.parametrize("amount", [1.0, 1, "1", D("NaN"), D("sNaN"), D("Infinity"), D("-Infinity"), D("-0.01"), D("0.001")])
@pytest.mark.parametrize("field", ["principal", "fee", "fee_tax", "captured_gross", "unapplied_excess"])
def test_invalid_attempt_money(field, amount):
    with pytest.raises(ValueError):
        project([attempt(**{field: amount})])


@pytest.mark.parametrize("amount", [1.0, D("NaN"), D("-1"), D("0.001")])
def test_invalid_base(amount):
    with pytest.raises(ValueError):
        project(principal_base=amount)


@pytest.mark.parametrize("second", [attempt(), attempt(fee=D("7"), captured_gross=D("207"))])
def test_duplicate_or_conflicting_identity_rejected(second):
    with pytest.raises(ValueError, match="Duplicate"):
        project([attempt(), second])


@pytest.mark.parametrize("field", ["tenant_id", "realm_id", "invoice_id"])
def test_foreign_identity(field):
    with pytest.raises(ValueError, match="Foreign"):
        project([attempt(identity=replace(IDENTITY, **{field: "foreign"}))])


@pytest.mark.parametrize("version", [None, "", "legacy", "gross_invoice_v2"])
def test_unknown_version(version):
    with pytest.raises(ValueError, match="version"):
        project(composition_version=version)
    with pytest.raises(ValueError, match="version"):
        project([attempt(composition_version=version)])


@pytest.mark.parametrize("rail", ["zelle", "check", "ach"])
def test_noncard_fee_rejected(rail):
    with pytest.raises(ValueError, match="Non-card"):
        project([attempt(rail=rail)])


@pytest.mark.parametrize("rail", ["cash", "unknown", "", None])
def test_unsupported_rail_rejected_even_without_fee(rail):
    with pytest.raises(ValueError, match="Unsupported payment rail"):
        project([attempt(rail=rail, fee=D("0"), captured_gross=D("200"))])


@pytest.mark.parametrize("changes", [dict(captured_gross=D("205")),
                                     dict(captured_gross=D("210")),
                                     dict(unapplied_excess=D("6"))])
def test_excess_not_inferred_and_fee_not_credit(changes):
    with pytest.raises(ValueError, match="Captured gross"):
        project([attempt(**changes)])


def test_principal_overallocation():
    with pytest.raises(ValueError, match="over-allocation"):
        project(mixed() + [attempt("extra")])


def test_tax_without_fee_rejected():
    with pytest.raises(ValueError, match="requires"):
        project([attempt(fee=D("0"), fee_tax=D("6"))])


@pytest.mark.parametrize("identity", ["", "  ", " bad", None])
def test_invalid_attempt_identity(identity):
    with pytest.raises(ValueError, match="identity"):
        project([attempt(attempt_id=identity)])


def test_revision_tracks_money_scope_and_membership():
    baseline = project([attempt()]).revision
    variants = [project([attempt(fee=D("7"), captured_gross=D("207"))]),
                project([attempt("another")]), project([attempt()], principal_base=D("1001")),
                project()]
    assert all(value.revision != baseline for value in variants)


def test_immutable_values():
    result = project([attempt()])
    with pytest.raises(FrozenInstanceError):
        result.invoice_total = D("0")
    with pytest.raises(FrozenInstanceError):
        result.payments[0].fee = D("0")


def test_exact_money_independent_of_decimal_context():
    expected = project([attempt()])
    with localcontext() as context:
        context.prec = 2
        assert project([attempt()]) == expected


def test_equivalent_decimal_scale_same_revision():
    assert project([attempt(fee=D("6.000"))]) == project([attempt()])


@pytest.mark.parametrize("amount", [D("1e999999999"), D("1e-999999999"), D("10000000000")])
def test_numeric_limit_and_extreme_exponents(amount):
    with pytest.raises(ValueError):
        project(principal_base=amount)


def test_extreme_zero_exponents_safe():
    assert project(principal_base=D("0e999999999")).invoice_total == 0
    assert project(principal_base=D("0e-999999999")).invoice_total == 0


def test_aggregate_invoice_limit():
    with pytest.raises(ValueError, match="NUMERIC"):
        project([attempt()], principal_base=D("9999999999.99"))


def test_zero_capture_rejected():
    with pytest.raises(ValueError, match="positive"):
        project([attempt(principal=D("0"), fee=D("0"), captured_gross=D("0"))])


def test_zero_principal_cannot_earn_fee():
    with pytest.raises(ValueError, match="positive principal"):
        project([attempt(principal=D("0"), captured_gross=D("6"))])


def test_entire_capture_actual_excess_is_not_fee_income():
    result = project([attempt(principal=D("0"), fee=D("0"), captured_gross=D("5"),
                              unapplied_excess=D("5"))])
    assert result.invoice_total == D("1000")
    assert result.remaining_principal == D("1000")
    assert result.payments[0].invoice_allocation == 0
    assert result.payments[0].unapplied_excess == D("5")
