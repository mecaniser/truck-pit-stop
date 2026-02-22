from __future__ import annotations

from uuid import uuid4

import pytest
from pydantic import ValidationError

pytest.importorskip("stripe")
pytest.importorskip("aiosqlite")

from app.api.v1.endpoints.payments import (
    ManualPaymentRequest,
    _is_placeholder_walkin_customer,
    _normalize_email,
    _normalize_phone,
)
from app.db.models.customer import Customer


def test_normalize_phone_strips_non_digits():
    assert _normalize_phone("(555) 123-4567") == "5551234567"
    assert _normalize_phone("+1 414-555-0909") == "14145550909"
    assert _normalize_phone("   ") is None
    assert _normalize_phone(None) is None


def test_normalize_email_trims_and_lowercases():
    assert _normalize_email("  TEST@Example.COM ") == "test@example.com"
    assert _normalize_email(" ") is None
    assert _normalize_email(None) is None


def test_is_placeholder_walkin_customer_detects_placeholder_email():
    customer = Customer(
        tenant_id=uuid4(),
        first_name="John",
        last_name="Doe",
        email="walkin+5551231234@placeholder.dieselbridge.network",
    )
    assert _is_placeholder_walkin_customer(customer) is True


def test_is_placeholder_walkin_customer_detects_walk_in_source():
    customer = Customer(
        tenant_id=uuid4(),
        first_name="John",
        last_name="Doe",
        email="john@example.com",
        source="walk_in",
    )
    assert _is_placeholder_walkin_customer(customer) is True


def test_is_placeholder_walkin_customer_false_for_normal_customer():
    customer = Customer(
        tenant_id=uuid4(),
        first_name="Jane",
        last_name="Driver",
        email="jane@example.com",
        source="portal",
    )
    assert _is_placeholder_walkin_customer(customer) is False


def test_manual_payment_request_rejects_invalid_sender_email():
    try:
        ManualPaymentRequest(
            invoice_id=uuid4(),
            method="zelle",
            zelle_sender_email="asdf",
            update_customer_from_sender=True,
        )
        assert False, "Expected invalid email to raise ValidationError"
    except ValidationError:
        pass
