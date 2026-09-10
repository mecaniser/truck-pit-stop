"""Public DB-048 settlement DTOs shared by staff, portal, and guest flows."""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any, Literal, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


Money = Decimal
PaymentRail = Literal["card", "zelle", "check", "ach"]


class SettlementError(BaseModel):
    code: str
    message: str
    retryable: bool = False
    current_version: Optional[int] = None


class SettlementAllowedActions(BaseModel):
    create_attempt: bool = False
    rails: list[PaymentRail] = Field(default_factory=list)
    confirm_manual: bool = False
    resolve_overpayment: bool = False
    apply_customer_credit: bool = False
    authorize_early_release: bool = False
    retry_accounting: bool = False
    configure_provider: bool = False
    confirm_cash: bool = False
    cash_unavailable_reason: Optional[str] = None
    payment_unavailable_reason: Optional[str] = None


class InvoiceSettlementSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    invoice_id: UUID
    currency: str = "USD"
    principal_total: Money
    confirmed_principal: Money
    active_pending_principal: Money
    outstanding_balance: Money
    allocatable_balance: Money
    unapplied_credit: Money
    refund_pending: Money
    state: str
    version: int
    card_provider: Optional[str] = None
    card_provider_status: str
    accounting_sync_status: str
    feature_enabled: bool
    allowed_actions: SettlementAllowedActions


class SenderEvidence(BaseModel):
    sender_name: Optional[str] = Field(default=None, max_length=255)
    sender_email: Optional[str] = Field(default=None, max_length=255)
    sender_phone: Optional[str] = Field(default=None, max_length=40)
    reference: Optional[str] = Field(default=None, max_length=255)
    reference_number: Optional[str] = Field(default=None, max_length=255)
    note: Optional[str] = Field(default=None, max_length=1000)


class PaymentAttemptCreate(BaseModel):
    amount: Money
    rail: PaymentRail
    expected_settlement_version: int = Field(ge=1)
    sender_evidence: Optional[SenderEvidence] = None

    @field_validator("amount")
    @classmethod
    def validate_amount(cls, value: Decimal) -> Decimal:
        value = Decimal(str(value)).quantize(Decimal("0.01"))
        if value < Decimal("0.01"):
            raise ValueError("amount must be at least 0.01")
        return value


class QuickBooksAttemptCharge(BaseModel):
    model_config = ConfigDict(extra="forbid")

    token: str = Field(min_length=8, max_length=2048)
    expected_attempt_version: int = Field(ge=1)


class PaymentAttemptResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    attempt_id: UUID
    invoice_id: UUID
    principal_amount: Money
    card_fee_amount: Money
    card_fee_tax_amount: Money
    applied_card_fee_amount: Money
    applied_card_fee_tax_amount: Money
    provider_charge_amount: Money
    rail: str
    provider: str
    # Compatibility aliases keep the public contract usable while existing
    # clients migrate from provider/configuration naming.
    card_provider: Optional[str] = None
    state: str
    expires_at: Optional[datetime] = None
    provider_configuration_version: int
    configuration_version: int
    attempt_version: int
    failure_code: Optional[str] = None
    provider_client_secret: Optional[str] = None
    provider_token_url: Optional[str] = None
    provider_account_id: Optional[str] = None
    stripe_account_id: Optional[str] = None
    settlement: InvoiceSettlementSummary


class PaymentAllocationItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    attempt_id: UUID
    created_at: datetime
    rail: str
    provider: str
    state: str
    attempt_version: int
    failure_code: Optional[str] = None
    principal_amount: Money
    applied_principal_amount: Money
    card_fee_amount: Money
    card_fee_tax_amount: Money
    applied_card_fee_amount: Money
    applied_card_fee_tax_amount: Money
    provider_charge_amount: Money
    received_amount: Optional[Money] = None
    unapplied_amount: Money
    expires_at: Optional[datetime] = None
    confirmed_at: Optional[datetime] = None
    reference: Optional[str] = None
    reference_number: Optional[str] = None
    actor_name: Optional[str] = None
    accounting_sync_status: Optional[str] = None
    overpayment_id: Optional[UUID] = None
    overpayment_state: Optional[str] = None
    refund_id: Optional[UUID] = None
    refund_state: Optional[str] = None


class PaymentAllocationPage(BaseModel):
    items: list[PaymentAllocationItem]
    next_cursor: Optional[str] = None


class CashConfirmationCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_settlement_version: int = Field(ge=1)
    note: Optional[str] = Field(default=None, max_length=1000)


class CashConfirmationResponse(BaseModel):
    payment_id: UUID
    settlement: InvoiceSettlementSummary


class PaymentAttemptConfirm(BaseModel):
    expected_attempt_version: int = Field(ge=1)
    received_amount: Optional[Money] = None
    reference: Optional[str] = Field(default=None, max_length=255)
    reference_number: Optional[str] = Field(default=None, max_length=255)
    provider_reference: Optional[str] = Field(default=None, max_length=255)
    note: Optional[str] = Field(default=None, max_length=1000)

    @field_validator("received_amount")
    @classmethod
    def validate_received(cls, value: Optional[Decimal]) -> Optional[Decimal]:
        if value is None:
            return None
        value = Decimal(str(value)).quantize(Decimal("0.01"))
        if value < Decimal("0.01"):
            raise ValueError("received_amount must be at least 0.01")
        return value

    @property
    def resolved_reference(self) -> Optional[str]:
        return self.reference or self.reference_number or self.provider_reference


class PaymentAttemptFail(BaseModel):
    expected_attempt_version: int = Field(ge=1)
    failure_code: str = Field(min_length=1, max_length=100)


class PaymentRefundCreate(BaseModel):
    amount: Money
    reason: str = Field(min_length=1, max_length=1000)

    @field_validator("amount")
    @classmethod
    def validate_amount(cls, value: Decimal) -> Decimal:
        value = Decimal(str(value)).quantize(Decimal("0.01"))
        if value < Decimal("0.01"):
            raise ValueError("amount must be at least 0.01")
        return value


class ManualRefundConfirm(BaseModel):
    reference: str = Field(min_length=1, max_length=255)


class CreditConsentCreate(BaseModel):
    channel: Literal["customer_portal", "guest_token", "in_person", "phone"]
    note: str = Field(min_length=1, max_length=1000)


class CreditDueDiligenceCreate(BaseModel):
    channel: Literal["email", "phone", "mail", "in_person", "other"]
    note: str = Field(min_length=1, max_length=1000)
    next_review_at: Optional[datetime] = None


class CreditApplicationCreate(BaseModel):
    invoice_id: UUID
    amount: Money
    expected_settlement_version: int = Field(ge=1)

    @field_validator("amount")
    @classmethod
    def validate_amount(cls, value: Decimal) -> Decimal:
        value = Decimal(str(value)).quantize(Decimal("0.01"))
        if value < Decimal("0.01"):
            raise ValueError("amount must be at least 0.01")
        return value


class CardProviderConfigurationRead(BaseModel):
    selected_provider: Optional[str] = None
    readiness_state: str
    version: Optional[int] = None
    effective_at: Optional[datetime] = None
    writer_strategy: Optional[str] = None
    provider_account_snapshot: Optional[str] = None
    qbo_realm_snapshot: Optional[str] = None
    mappings: dict[str, Optional[str]] = Field(default_factory=dict)


class CardProviderConfigurationUpdate(BaseModel):
    selected_provider: Optional[Literal["stripe_connect", "quickbooks_payments"]] = None
    provider: Optional[Literal["stripe_connect", "quickbooks_payments"]] = None
    expected_version: Optional[int] = None
    writer_strategy: Optional[Literal["dieselbridge", "intuit_native"]] = None
    stripe_clearing_account: Optional[str] = Field(default=None, max_length=255)
    qbp_clearing_account: Optional[str] = Field(default=None, max_length=255)
    check_deposit_account: Optional[str] = Field(default=None, max_length=255)
    zelle_ach_account: Optional[str] = Field(default=None, max_length=255)
    card_fee_income_account: Optional[str] = Field(default=None, max_length=255)
    qbo_card_fee_item_id: Optional[str] = Field(default=None, min_length=1, max_length=255)
    qbo_card_fee_tax_code_id: Optional[str] = Field(default=None, min_length=1, max_length=255)
    processor_fee_expense_account: Optional[str] = Field(default=None, max_length=255)
    sales_tax_liability_account: Optional[str] = Field(default=None, max_length=255)
    checking_account: Optional[str] = Field(default=None, max_length=255)

    @model_validator(mode="after")
    def validate_provider(self):
        if self.selected_provider and self.provider and self.selected_provider != self.provider:
            raise ValueError("provider fields must match")
        if not self.selected_provider and not self.provider:
            raise ValueError("provider is required")
        return self

    @property
    def resolved_provider(self) -> str:
        return self.selected_provider or self.provider  # type: ignore[return-value]


class ProviderOptionReadiness(BaseModel):
    approved: bool
    tenant_ready: bool
    status: str
    message: Optional[str] = None


class CardProviderReadiness(BaseModel):
    feature_enabled: bool
    selected_provider: Optional[str] = None
    selected_provider_status: str
    configuration_version: Optional[int] = None
    stripe_connect: ProviderOptionReadiness
    quickbooks_payments: ProviderOptionReadiness
    accounting_ready: bool
    accounting_message: Optional[str] = None
    writer_strategy: Optional[str] = None
    qbo_realm_snapshot: Optional[str] = None
    mappings: dict[str, Optional[str]] = Field(default_factory=dict)
    allowed_actions: SettlementAllowedActions
    # Detailed diagnostic fields are additive and used by operators/tests.
    provider: Optional[str] = None
    status: str
    split_payment_global_gate: bool
    split_payment_tenant_gate: bool
    provider_global_gate: bool
    provider_onboarding_ready: bool
    qbo_accounting_ready: bool
    mappings_ready: bool
    reasons: list[str] = Field(default_factory=list)


class AccountingReconciliationRead(BaseModel):
    invoice_id: UUID
    state: str
    pending_operations: int
    failed_operations: int
    synced_operations: int
    links: list[dict[str, Any]] = Field(default_factory=list)


class AccountingRetryResponse(BaseModel):
    operation_id: UUID
    state: str


class CreditAgingItem(BaseModel):
    credit_id: UUID
    customer_id: UUID
    customer_name: str
    origin_amount: Money
    remaining_amount: Money
    issued_at: datetime
    age_days: int
    consent_channel: Optional[str] = None
    consent_note: Optional[str] = None
    last_contact_at: Optional[datetime] = None
    last_contact_channel: Optional[str] = None
    last_contact_note: Optional[str] = None
    next_review_at: Optional[datetime] = None
    disposition: str


class EligibleCreditItem(BaseModel):
    credit_id: UUID
    origin_overpayment_id: Optional[UUID] = None
    origin_amount: Money
    remaining_amount: Money
    issued_at: datetime
    consent_channel: Optional[str] = None


class EarlyReleaseOverride(BaseModel):
    invoice_id: UUID
    reason: str = Field(min_length=1, max_length=1000)
    expected_settlement_version: int = Field(ge=1)
