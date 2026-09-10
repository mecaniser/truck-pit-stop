"""Add DB-048 partial invoice settlement and immutable payment audit.

Revision ID: 135_invoice_partial_payments
Revises: 134_fleet_membership_ended_by
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "135_invoice_partial_payments"
down_revision = "134_fleet_membership_ended_by"
branch_labels = None
depends_on = None

UUID = postgresql.UUID(as_uuid=True)
JSON = postgresql.JSONB(astext_type=sa.Text())
MONEY = sa.Numeric(12, 2)


def _identity_columns():
    return [
        sa.Column("id", UUID, primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    ]


def _append_only_trigger(table_name: str, function_name: str) -> None:
    op.execute(sa.text(f"""
        CREATE FUNCTION {function_name}() RETURNS trigger AS $$
        BEGIN
          RAISE EXCEPTION '{table_name} is append-only';
        END;
        $$ LANGUAGE plpgsql
    """))
    op.execute(sa.text(f"""
        CREATE TRIGGER trg_{table_name}_no_update_delete
        BEFORE UPDATE OR DELETE ON {table_name}
        FOR EACH ROW EXECUTE FUNCTION {function_name}()
    """))


def _tenant_integrity_trigger(table_name: str) -> None:
    op.execute(sa.text(f"""
        CREATE TRIGGER trg_{table_name}_tenant_integrity
        BEFORE INSERT OR UPDATE ON {table_name}
        FOR EACH ROW EXECUTE FUNCTION enforce_db048_tenant_integrity()
    """))


def upgrade() -> None:
    op.add_column(
        "tenants",
        sa.Column("invoice_split_payments_enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column("repair_orders", sa.Column("vehicle_released_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("repair_orders", sa.Column("vehicle_released_by_user_id", UUID, nullable=True))
    op.add_column("repair_orders", sa.Column("vehicle_release_reason", sa.Text(), nullable=True))
    op.create_foreign_key(
        "fk_repair_orders_vehicle_released_by_user",
        "repair_orders", "users", ["vehicle_released_by_user_id"], ["id"],
    )
    op.create_index("ix_repair_orders_vehicle_released_at", "repair_orders", ["vehicle_released_at"])

    op.create_table(
        "tenant_payment_provider_configurations",
        *_identity_columns(),
        sa.Column("tenant_id", UUID, sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("selected_provider", sa.String(32), nullable=False),
        sa.Column("readiness_state", sa.String(48), nullable=False, server_default="not_ready"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("effective_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("deactivated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("actor_user_id", UUID, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("actor_name_snapshot", sa.String(255), nullable=False),
        sa.Column("provider_account_snapshot", sa.String(255), nullable=True),
        sa.Column("qbo_realm_snapshot", sa.String(255), nullable=True),
        sa.Column("writer_strategy", sa.String(32), nullable=False, server_default="dieselbridge"),
        sa.Column("idempotency_key", sa.String(255), nullable=False),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("stripe_clearing_account", sa.String(255), nullable=True),
        sa.Column("qbp_clearing_account", sa.String(255), nullable=True),
        sa.Column("check_deposit_account", sa.String(255), nullable=True),
        sa.Column("zelle_ach_account", sa.String(255), nullable=True),
        sa.Column("card_fee_income_account", sa.String(255), nullable=True),
        sa.Column("processor_fee_expense_account", sa.String(255), nullable=True),
        sa.Column("sales_tax_liability_account", sa.String(255), nullable=True),
        sa.Column("checking_account", sa.String(255), nullable=True),
        sa.UniqueConstraint("tenant_id", "version", name="uq_tenant_payment_provider_version"),
        sa.UniqueConstraint("tenant_id", "idempotency_key", name="uq_tenant_payment_provider_idempotency"),
        sa.CheckConstraint("version >= 1", name="ck_tenant_payment_provider_version"),
        sa.CheckConstraint("selected_provider IN ('stripe_connect','quickbooks_payments')", name="ck_tenant_payment_provider_name"),
        sa.CheckConstraint("writer_strategy IN ('dieselbridge','intuit_native')", name="ck_tenant_payment_provider_writer"),
    )
    op.create_index("ix_tenant_payment_provider_active", "tenant_payment_provider_configurations", ["tenant_id", "is_active"])
    op.create_index(
        "uq_tenant_payment_provider_one_active",
        "tenant_payment_provider_configurations",
        ["tenant_id"],
        unique=True,
        postgresql_where=sa.text("is_active"),
    )

    op.create_table(
        "invoice_settlements",
        *_identity_columns(),
        sa.Column("tenant_id", UUID, sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("invoice_id", UUID, sa.ForeignKey("invoices.id"), nullable=False),
        sa.Column("customer_id", UUID, sa.ForeignKey("customers.id"), nullable=False),
        sa.Column("principal_total", MONEY, nullable=False),
        sa.Column("max_card_fee", MONEY, nullable=False, server_default="0"),
        sa.Column("max_card_fee_tax", MONEY, nullable=False, server_default="0"),
        sa.Column("sales_tax_rate_snapshot", sa.Numeric(7, 4), nullable=False, server_default="0"),
        sa.Column("card_fee_rate_snapshot", sa.Numeric(7, 4), nullable=False, server_default="0"),
        sa.Column("currency", sa.String(3), nullable=False, server_default="USD"),
        sa.Column("confirmed_principal", MONEY, nullable=False, server_default="0"),
        sa.Column("active_pending_principal", MONEY, nullable=False, server_default="0"),
        sa.Column("unapplied_credit", MONEY, nullable=False, server_default="0"),
        sa.Column("refund_pending", MONEY, nullable=False, server_default="0"),
        sa.Column("state", sa.String(40), nullable=False, server_default="unpaid"),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("last_event_sequence", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("accounting_sync_status", sa.String(32), nullable=False, server_default="not_required"),
        sa.Column("qbo_realm_snapshot", sa.String(255), nullable=True),
        sa.Column("initial_provider_configuration_version", sa.Integer(), nullable=True),
        sa.Column("legacy_reconciliation_status", sa.String(48), nullable=False, server_default="native"),
        sa.Column("legacy_reconciliation_note", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(
            ["tenant_id", "initial_provider_configuration_version"],
            [
                "tenant_payment_provider_configurations.tenant_id",
                "tenant_payment_provider_configurations.version",
            ],
            name="fk_invoice_settlement_initial_provider_configuration",
        ),
        sa.UniqueConstraint("invoice_id", name="uq_invoice_settlements_invoice"),
        sa.UniqueConstraint("tenant_id", "invoice_id", name="uq_invoice_settlements_tenant_invoice"),
        sa.CheckConstraint("currency = 'USD'", name="ck_invoice_settlement_currency"),
        sa.CheckConstraint("principal_total >= 0", name="ck_invoice_settlement_principal"),
        sa.CheckConstraint("confirmed_principal >= 0", name="ck_invoice_settlement_confirmed"),
        sa.CheckConstraint("active_pending_principal >= 0", name="ck_invoice_settlement_pending"),
        sa.CheckConstraint("unapplied_credit >= 0", name="ck_invoice_settlement_unapplied"),
        sa.CheckConstraint("refund_pending >= 0", name="ck_invoice_settlement_refund_pending"),
        sa.CheckConstraint("version >= 1", name="ck_invoice_settlement_version"),
        sa.CheckConstraint(
            "(qbo_realm_snapshot IS NULL AND initial_provider_configuration_version IS NULL) "
            "OR (qbo_realm_snapshot IS NOT NULL AND initial_provider_configuration_version >= 1)",
            name="ck_invoice_settlement_accounting_realm_pair",
        ),
    )
    op.create_index("ix_invoice_settlements_tenant_state", "invoice_settlements", ["tenant_id", "state"])
    op.create_index("ix_invoice_settlements_invoice_id", "invoice_settlements", ["invoice_id"])

    op.create_table(
        "invoice_payment_attempts",
        *_identity_columns(),
        sa.Column("tenant_id", UUID, sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("invoice_id", UUID, sa.ForeignKey("invoices.id"), nullable=False),
        sa.Column("settlement_id", UUID, sa.ForeignKey("invoice_settlements.id"), nullable=False),
        sa.Column("customer_id", UUID, sa.ForeignKey("customers.id"), nullable=False),
        sa.Column("payment_id", UUID, sa.ForeignKey("payments.id"), nullable=True),
        sa.Column("source", sa.String(40), nullable=False),
        sa.Column("rail", sa.String(16), nullable=False),
        sa.Column("provider", sa.String(32), nullable=False),
        sa.Column("state", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("principal_amount", MONEY, nullable=False),
        sa.Column("card_fee_amount", MONEY, nullable=False, server_default="0"),
        sa.Column("card_fee_tax_amount", MONEY, nullable=False, server_default="0"),
        sa.Column("applied_card_fee_amount", MONEY, nullable=False, server_default="0"),
        sa.Column("applied_card_fee_tax_amount", MONEY, nullable=False, server_default="0"),
        sa.Column("provider_charge_amount", MONEY, nullable=False),
        sa.Column("received_amount", MONEY, nullable=True),
        sa.Column("applied_principal_amount", MONEY, nullable=False, server_default="0"),
        sa.Column("unapplied_amount", MONEY, nullable=False, server_default="0"),
        sa.Column("processor_fee_amount", MONEY, nullable=False, server_default="0"),
        sa.Column("currency", sa.String(3), nullable=False, server_default="USD"),
        sa.Column("provider_configuration_version", sa.Integer(), nullable=False),
        sa.Column("provider_account_id", sa.String(255), nullable=True),
        sa.Column("provider_intent_id", sa.String(255), nullable=True),
        sa.Column("provider_charge_id", sa.String(255), nullable=True),
        sa.Column("provider_event_id", sa.String(255), nullable=True),
        sa.Column("provider_reference", sa.String(255), nullable=True),
        sa.Column("manual_reference_fingerprint", sa.String(64), nullable=True),
        sa.Column("manual_evidence", JSON, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("actor_user_id", UUID, sa.ForeignKey("users.id"), nullable=True),
        sa.Column("actor_name_snapshot", sa.String(255), nullable=False),
        sa.Column("actor_role_snapshot", sa.String(64), nullable=True),
        sa.Column("subject_type", sa.String(32), nullable=False),
        sa.Column("subject_id", UUID, nullable=True),
        sa.Column("idempotency_key", sa.String(255), nullable=False),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("failed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("failure_code", sa.String(100), nullable=True),
        sa.UniqueConstraint("tenant_id", "idempotency_key", name="uq_invoice_payment_attempt_idempotency"),
        sa.UniqueConstraint("provider", "provider_account_id", "provider_event_id", name="uq_invoice_payment_provider_event"),
        sa.UniqueConstraint(
            "tenant_id", "customer_id", "rail", "manual_reference_fingerprint",
            name="uq_invoice_payment_manual_reference",
        ),
        sa.UniqueConstraint("payment_id", name="uq_invoice_payment_attempt_payment"),
        sa.CheckConstraint("currency = 'USD'", name="ck_invoice_payment_attempt_currency"),
        sa.CheckConstraint("principal_amount > 0", name="ck_invoice_payment_attempt_principal"),
        sa.CheckConstraint("card_fee_amount >= 0", name="ck_invoice_payment_attempt_card_fee"),
        sa.CheckConstraint("card_fee_tax_amount >= 0", name="ck_invoice_payment_attempt_fee_tax"),
        sa.CheckConstraint("applied_card_fee_amount >= 0", name="ck_invoice_payment_attempt_applied_card_fee"),
        sa.CheckConstraint("applied_card_fee_tax_amount >= 0", name="ck_invoice_payment_attempt_applied_fee_tax"),
        sa.CheckConstraint(
            "received_amount IS NULL OR received_amount >= 0",
            name="ck_invoice_payment_attempt_received_nonnegative",
        ),
        sa.CheckConstraint(
            "applied_principal_amount >= 0 AND applied_principal_amount <= principal_amount",
            name="ck_invoice_payment_attempt_applied_principal_bounds",
        ),
        sa.CheckConstraint(
            "received_amount IS NULL OR applied_principal_amount <= received_amount",
            name="ck_invoice_payment_attempt_applied_not_over_received",
        ),
        sa.CheckConstraint(
            "unapplied_amount >= 0",
            name="ck_invoice_payment_attempt_unapplied_nonnegative",
        ),
        sa.CheckConstraint(
            "applied_card_fee_amount <= card_fee_amount",
            name="ck_invoice_payment_attempt_applied_card_fee_bound",
        ),
        sa.CheckConstraint(
            "applied_card_fee_tax_amount <= card_fee_tax_amount",
            name="ck_invoice_payment_attempt_applied_fee_tax_bound",
        ),
        sa.CheckConstraint(
            "(state IN ('pending','failed','expired') AND received_amount IS NULL "
            "AND applied_principal_amount = 0 AND unapplied_amount = 0 "
            "AND applied_card_fee_amount = 0 AND applied_card_fee_tax_amount = 0 "
            "AND processor_fee_amount = 0) "
            "OR (state IN ('confirmed','refunded','reversed') "
            "AND received_amount IS NOT NULL AND received_amount > 0)",
            name="ck_invoice_payment_attempt_state_money",
        ),
        sa.CheckConstraint(
            "received_amount IS NULL OR "
            "(source = 'backfill' AND state = 'refunded' "
            "AND received_amount = provider_charge_amount "
            "AND card_fee_amount = 0 AND card_fee_tax_amount = 0 "
            "AND applied_principal_amount = 0 AND unapplied_amount = 0 "
            "AND applied_card_fee_amount = 0 AND applied_card_fee_tax_amount = 0 "
            "AND processor_fee_amount = 0) OR "
            "(received_amount + (card_fee_amount - applied_card_fee_amount) "
            "+ (card_fee_tax_amount - applied_card_fee_tax_amount) "
            "= applied_principal_amount + unapplied_amount)",
            name="ck_invoice_payment_attempt_received_allocation",
        ),
        sa.CheckConstraint("provider_charge_amount > 0", name="ck_invoice_payment_attempt_charge"),
        sa.CheckConstraint("processor_fee_amount >= 0", name="ck_invoice_payment_attempt_processor_fee"),
        sa.CheckConstraint("rail IN ('card','zelle','check','ach')", name="ck_invoice_payment_attempt_rail"),
        sa.CheckConstraint("provider IN ('stripe_connect','quickbooks_payments','manual')", name="ck_invoice_payment_attempt_provider"),
        sa.CheckConstraint("state IN ('pending','confirmed','failed','expired','refunded','reversed')", name="ck_invoice_payment_attempt_state"),
        sa.CheckConstraint("version >= 1", name="ck_invoice_payment_attempt_version"),
    )
    op.create_index("ix_invoice_payment_attempt_invoice_created", "invoice_payment_attempts", ["tenant_id", "invoice_id", "created_at", "id"])
    op.create_index("ix_invoice_payment_attempt_pending", "invoice_payment_attempts", ["tenant_id", "state", "expires_at"])
    op.create_index("ix_invoice_payment_attempt_provider_identity", "invoice_payment_attempts", ["provider", "provider_account_id", "provider_intent_id"])
    op.add_column("payments", sa.Column("invoice_payment_attempt_id", UUID, nullable=True))
    op.create_foreign_key("fk_payments_invoice_payment_attempt", "payments", "invoice_payment_attempts", ["invoice_payment_attempt_id"], ["id"])
    op.create_unique_constraint("uq_payments_invoice_payment_attempt", "payments", ["invoice_payment_attempt_id"])
    op.create_index("ix_payments_invoice_payment_attempt_id", "payments", ["invoice_payment_attempt_id"])

    op.create_table(
        "invoice_payment_ledger_events",
        sa.Column("id", UUID, primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("tenant_id", UUID, sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("invoice_id", UUID, sa.ForeignKey("invoices.id"), nullable=False),
        sa.Column("settlement_id", UUID, sa.ForeignKey("invoice_settlements.id"), nullable=False),
        sa.Column("attempt_id", UUID, sa.ForeignKey("invoice_payment_attempts.id"), nullable=True),
        sa.Column("customer_id", UUID, sa.ForeignKey("customers.id"), nullable=False),
        sa.Column("actor_user_id", UUID, sa.ForeignKey("users.id"), nullable=True),
        sa.Column("actor_name_snapshot", sa.String(255), nullable=False),
        sa.Column("actor_role_snapshot", sa.String(64), nullable=True),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("correlation_id", UUID, nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("idempotency_key", sa.String(255), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("event_type", sa.String(64), nullable=False),
        sa.Column("prior_state", sa.String(32), nullable=True),
        sa.Column("new_state", sa.String(32), nullable=True),
        sa.Column("principal_delta", MONEY, nullable=False, server_default="0"),
        sa.Column("pending_delta", MONEY, nullable=False, server_default="0"),
        sa.Column("unapplied_delta", MONEY, nullable=False, server_default="0"),
        sa.Column("refund_pending_delta", MONEY, nullable=False, server_default="0"),
        sa.Column("money_snapshot", JSON, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("evidence_snapshot", JSON, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.UniqueConstraint("settlement_id", "sequence", name="uq_invoice_payment_ledger_sequence"),
        sa.UniqueConstraint("tenant_id", "idempotency_key", name="uq_invoice_payment_ledger_idempotency"),
    )
    op.create_index("ix_invoice_payment_ledger_invoice", "invoice_payment_ledger_events", ["tenant_id", "invoice_id", sa.text("occurred_at DESC"), sa.text("id DESC")])
    op.create_index("ix_invoice_payment_ledger_attempt", "invoice_payment_ledger_events", ["tenant_id", "attempt_id", "occurred_at"])

    op.create_table(
        "payment_overpayments",
        *_identity_columns(),
        sa.Column("tenant_id", UUID, sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("invoice_id", UUID, sa.ForeignKey("invoices.id"), nullable=False),
        sa.Column("settlement_id", UUID, sa.ForeignKey("invoice_settlements.id"), nullable=False),
        sa.Column("source_attempt_id", UUID, sa.ForeignKey("invoice_payment_attempts.id"), nullable=False),
        sa.Column("customer_id", UUID, sa.ForeignKey("customers.id"), nullable=False),
        sa.Column("amount", MONEY, nullable=False),
        sa.Column("state", sa.String(40), nullable=False, server_default="refund_required"),
        sa.Column("consent_channel", sa.String(32), nullable=True),
        sa.Column("consent_note", sa.Text(), nullable=True),
        sa.Column("consent_actor_user_id", UUID, sa.ForeignKey("users.id"), nullable=True),
        sa.Column("consented_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("source_attempt_id", name="uq_payment_overpayment_attempt"),
        sa.CheckConstraint("amount > 0", name="ck_payment_overpayment_amount"),
    )
    op.create_index("ix_payment_overpayment_tenant_state", "payment_overpayments", ["tenant_id", "state"])

    op.create_table(
        "customer_credit_entries",
        sa.Column("id", UUID, primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("tenant_id", UUID, sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("customer_id", UUID, sa.ForeignKey("customers.id"), nullable=False),
        sa.Column("entry_type", sa.String(20), nullable=False),
        sa.Column("amount", MONEY, nullable=False),
        sa.Column("origin_overpayment_id", UUID, sa.ForeignKey("payment_overpayments.id"), nullable=True),
        sa.Column("target_invoice_id", UUID, sa.ForeignKey("invoices.id"), nullable=True),
        sa.Column("source_entry_id", UUID, sa.ForeignKey("customer_credit_entries.id"), nullable=True),
        sa.Column("actor_user_id", UUID, sa.ForeignKey("users.id"), nullable=True),
        sa.Column("actor_name_snapshot", sa.String(255), nullable=False),
        sa.Column("consent_channel", sa.String(32), nullable=True),
        sa.Column("consent_note", sa.Text(), nullable=True),
        sa.Column("idempotency_key", sa.String(255), nullable=False),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("tenant_id", "idempotency_key", name="uq_customer_credit_entry_idempotency"),
        sa.CheckConstraint("amount > 0", name="ck_customer_credit_entry_amount"),
        sa.CheckConstraint("entry_type IN ('issued','applied','refunded','reversed')", name="ck_customer_credit_entry_type"),
    )
    op.create_index("ix_customer_credit_entries_customer", "customer_credit_entries", ["tenant_id", "customer_id", sa.text("occurred_at DESC"), sa.text("id DESC")])

    op.create_table(
        "customer_credit_due_diligence_events",
        sa.Column("id", UUID, primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("tenant_id", UUID, sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("customer_id", UUID, sa.ForeignKey("customers.id"), nullable=False),
        sa.Column("credit_id", UUID, sa.ForeignKey("customer_credit_entries.id"), nullable=False),
        sa.Column("actor_user_id", UUID, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("actor_name_snapshot", sa.String(255), nullable=False),
        sa.Column("channel", sa.String(24), nullable=False),
        sa.Column("note", sa.Text(), nullable=False),
        sa.Column("next_review_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("idempotency_key", sa.String(255), nullable=False),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint(
            "tenant_id", "idempotency_key",
            name="uq_customer_credit_due_diligence_idempotency",
        ),
        sa.CheckConstraint(
            "channel IN ('email','phone','mail','in_person','other')",
            name="ck_customer_credit_due_diligence_channel",
        ),
    )
    op.create_index(
        "ix_customer_credit_due_diligence_credit",
        "customer_credit_due_diligence_events",
        ["tenant_id", "credit_id", sa.text("occurred_at DESC"), sa.text("id DESC")],
    )

    op.create_table(
        "payment_refunds",
        *_identity_columns(),
        sa.Column("tenant_id", UUID, sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("invoice_id", UUID, sa.ForeignKey("invoices.id"), nullable=False),
        sa.Column("source_attempt_id", UUID, sa.ForeignKey("invoice_payment_attempts.id"), nullable=False),
        sa.Column("overpayment_id", UUID, sa.ForeignKey("payment_overpayments.id"), nullable=True),
        sa.Column("amount", MONEY, nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("destination_rail", sa.String(16), nullable=False),
        sa.Column("mode", sa.String(16), nullable=False),
        sa.Column("state", sa.String(32), nullable=False, server_default="pending"),
        sa.Column("provider_reference", sa.String(255), nullable=True),
        sa.Column("actor_user_id", UUID, sa.ForeignKey("users.id"), nullable=True),
        sa.Column("actor_name_snapshot", sa.String(255), nullable=False),
        sa.Column("idempotency_key", sa.String(255), nullable=False),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("retry_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("tenant_id", "idempotency_key", name="uq_payment_refund_idempotency"),
        sa.CheckConstraint("amount > 0", name="ck_payment_refund_amount"),
        sa.CheckConstraint("state IN ('pending','manual_action_required','succeeded','failed','cancelled')", name="ck_payment_refund_state"),
    )
    op.create_index("ix_payment_refunds_tenant_state", "payment_refunds", ["tenant_id", "state"])

    op.create_table(
        "payment_provider_disputes",
        *_identity_columns(),
        sa.Column("tenant_id", UUID, sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("attempt_id", UUID, sa.ForeignKey("invoice_payment_attempts.id"), nullable=False),
        sa.Column("provider", sa.String(32), nullable=False, server_default="stripe_connect"),
        sa.Column("provider_account_id", sa.String(255), nullable=False),
        sa.Column("provider_dispute_id", sa.String(255), nullable=False),
        sa.Column("provider_charge_id", sa.String(255), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False, server_default="USD"),
        sa.Column("disputed_gross_amount", MONEY, nullable=False),
        sa.Column("reversed_principal_amount", MONEY, nullable=False, server_default="0"),
        sa.Column("reversed_card_fee_amount", MONEY, nullable=False, server_default="0"),
        sa.Column("reversed_card_fee_tax_amount", MONEY, nullable=False, server_default="0"),
        sa.Column("reversed_unapplied_amount", MONEY, nullable=False, server_default="0"),
        sa.Column("reversed_unapplied_principal_amount", MONEY, nullable=False, server_default="0"),
        sa.Column("reversed_unearned_surcharge_amount", MONEY, nullable=False, server_default="0"),
        sa.Column("state", sa.String(16), nullable=False, server_default="open"),
        sa.Column("reason", sa.String(100), nullable=True),
        sa.Column("created_provider_event_id", sa.String(255), nullable=False),
        sa.Column("closed_provider_event_id", sa.String(255), nullable=True),
        sa.Column("opened_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint(
            "provider", "provider_account_id", "provider_dispute_id",
            name="uq_payment_provider_dispute_identity",
        ),
        sa.CheckConstraint("currency = 'USD'", name="ck_payment_provider_dispute_currency"),
        sa.CheckConstraint("disputed_gross_amount > 0", name="ck_payment_provider_dispute_gross"),
        sa.CheckConstraint("reversed_principal_amount >= 0", name="ck_payment_provider_dispute_principal"),
        sa.CheckConstraint("reversed_card_fee_amount >= 0", name="ck_payment_provider_dispute_fee"),
        sa.CheckConstraint("reversed_card_fee_tax_amount >= 0", name="ck_payment_provider_dispute_fee_tax"),
        sa.CheckConstraint("reversed_unapplied_amount >= 0", name="ck_payment_provider_dispute_unapplied"),
        sa.CheckConstraint("reversed_unapplied_principal_amount >= 0", name="ck_payment_provider_dispute_unapplied_principal"),
        sa.CheckConstraint("reversed_unearned_surcharge_amount >= 0", name="ck_payment_provider_dispute_unearned_surcharge"),
        sa.CheckConstraint("state IN ('open','won','lost')", name="ck_payment_provider_dispute_state"),
    )
    op.create_index(
        "ix_payment_provider_dispute_attempt",
        "payment_provider_disputes", ["tenant_id", "attempt_id", "state"],
    )

    op.create_table(
        "payment_accounting_links",
        *_identity_columns(),
        sa.Column("tenant_id", UUID, sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("invoice_id", UUID, sa.ForeignKey("invoices.id"), nullable=True),
        sa.Column("attempt_id", UUID, sa.ForeignKey("invoice_payment_attempts.id"), nullable=True),
        sa.Column("refund_id", UUID, sa.ForeignKey("payment_refunds.id"), nullable=True),
        sa.Column("financial_object_type", sa.String(40), nullable=False),
        sa.Column("financial_object_id", UUID, nullable=False),
        sa.Column("operation_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("principal_amount_snapshot", MONEY, nullable=False, server_default="0"),
        sa.Column("gross_amount_snapshot", MONEY, nullable=False, server_default="0"),
        sa.Column("owning_writer", sa.String(32), nullable=False),
        sa.Column("account_mapping_snapshot", JSON, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("qbo_realm_snapshot", sa.String(255), nullable=True),
        sa.Column("sync_state", sa.String(32), nullable=False, server_default="pending"),
        sa.Column("provider_object_id", sa.String(255), nullable=True),
        sa.Column("provider_deposit_id", sa.String(255), nullable=True),
        sa.Column("sync_error", sa.Text(), nullable=True),
        sa.Column("synced_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("tenant_id", "financial_object_type", "financial_object_id", "operation_version", name="uq_payment_accounting_object_version"),
    )
    op.create_index("ix_payment_accounting_links_tenant_state", "payment_accounting_links", ["tenant_id", "sync_state"])

    op.create_table(
        "provider_settlement_batches",
        *_identity_columns(),
        sa.Column("tenant_id", UUID, sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("provider", sa.String(32), nullable=False),
        sa.Column("provider_account_id", sa.String(255), nullable=False),
        sa.Column("provider_batch_id", sa.String(255), nullable=False),
        sa.Column("qbo_realm_snapshot", sa.String(255), nullable=True),
        sa.Column("currency", sa.String(3), nullable=False, server_default="USD"),
        sa.Column("gross_receipts", MONEY, nullable=False, server_default="0"),
        sa.Column("customer_card_fees", MONEY, nullable=False, server_default="0"),
        sa.Column("card_fee_tax", MONEY, nullable=False, server_default="0"),
        sa.Column("refunds", MONEY, nullable=False, server_default="0"),
        sa.Column("disputes", MONEY, nullable=False, server_default="0"),
        sa.Column("processor_fees", MONEY, nullable=False, server_default="0"),
        sa.Column("net_payout", MONEY, nullable=False, server_default="0"),
        sa.Column("entry_manifest_hash", sa.String(64), nullable=False),
        sa.Column("reconciliation_state", sa.String(32), nullable=False, server_default="pending"),
        sa.Column("qbo_deposit_id", sa.String(255), nullable=True),
        sa.Column("qbo_journal_id", sa.String(255), nullable=True),
        sa.Column("mismatch_reason", sa.Text(), nullable=True),
        sa.Column("settled_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("provider", "provider_account_id", "provider_batch_id", name="uq_provider_settlement_batch"),
        sa.CheckConstraint("currency = 'USD'", name="ck_provider_settlement_batch_currency"),
    )
    op.create_index("ix_provider_settlement_batch_tenant_state", "provider_settlement_batches", ["tenant_id", "reconciliation_state"])

    op.create_table(
        "provider_settlement_entries",
        sa.Column("id", UUID, primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("tenant_id", UUID, sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("batch_id", UUID, sa.ForeignKey("provider_settlement_batches.id"), nullable=False),
        sa.Column("provider", sa.String(32), nullable=False),
        sa.Column("provider_account_id", sa.String(255), nullable=False),
        sa.Column("provider_entry_id", sa.String(255), nullable=False),
        sa.Column("entry_type", sa.String(32), nullable=False),
        sa.Column("amount", MONEY, nullable=False),
        sa.Column("attempt_id", UUID, sa.ForeignKey("invoice_payment_attempts.id"), nullable=True),
        sa.Column("refund_id", UUID, sa.ForeignKey("payment_refunds.id"), nullable=True),
        sa.Column("dispute_id", UUID, sa.ForeignKey("payment_provider_disputes.id"), nullable=True),
        sa.Column("provider_configuration_version", sa.Integer(), nullable=False),
        sa.Column("qbo_realm_snapshot", sa.String(255), nullable=False),
        sa.Column("owning_writer", sa.String(32), nullable=False),
        sa.Column("account_mapping_snapshot", JSON, nullable=False),
        sa.Column("account_mapping_hash", sa.String(64), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("safe_payload_hash", sa.String(64), nullable=False),
        sa.ForeignKeyConstraint(
            ["tenant_id", "provider_configuration_version"],
            [
                "tenant_payment_provider_configurations.tenant_id",
                "tenant_payment_provider_configurations.version",
            ],
            name="fk_provider_settlement_entry_configuration",
        ),
        sa.UniqueConstraint("provider", "provider_account_id", "provider_entry_id", name="uq_provider_settlement_entry"),
    )
    op.create_index("ix_provider_settlement_entry_batch", "provider_settlement_entries", ["tenant_id", "batch_id"])

    op.create_table(
        "invoice_settlement_backfill_runs",
        *_identity_columns(),
        sa.Column("tenant_id", UUID, sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("cutoff_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("state", sa.String(24), nullable=False, server_default="running"),
        sa.Column("batch_cursor", sa.String(255), nullable=True),
        sa.Column("source_counts", JSON, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("inserted_counts", JSON, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("source_checksums", JSON, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("error_summary", sa.Text(), nullable=True),
        sa.Column("reconciled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("tenant_id", "cutoff_at", name="uq_invoice_settlement_backfill_run"),
        sa.CheckConstraint("state IN ('running','failed','reconciled','verified')", name="ck_invoice_settlement_backfill_state"),
    )

    if op.get_bind().dialect.name == "postgresql":
        op.execute(sa.text("""
            CREATE FUNCTION enforce_db048_tenant_integrity() RETURNS trigger AS $$
            BEGIN
              IF TG_TABLE_NAME = 'invoice_settlements' THEN
                IF NOT EXISTS (
                  SELECT 1
                  FROM invoices i
                  JOIN repair_orders ro ON ro.id = i.repair_order_id
                  JOIN customers c ON c.id = NEW.customer_id
                  WHERE i.id = NEW.invoice_id
                    AND i.tenant_id = NEW.tenant_id
                    AND ro.tenant_id = NEW.tenant_id
                    AND ro.customer_id = NEW.customer_id
                    AND c.tenant_id = NEW.tenant_id
                ) THEN
                  RAISE EXCEPTION 'DB-048 settlement tenant identity mismatch';
                END IF;
              ELSIF TG_TABLE_NAME = 'invoice_payment_attempts' THEN
                IF NOT EXISTS (
                  SELECT 1 FROM invoice_settlements s
                  WHERE s.id = NEW.settlement_id
                    AND s.tenant_id = NEW.tenant_id
                    AND s.invoice_id = NEW.invoice_id
                    AND s.customer_id = NEW.customer_id
                ) OR NOT EXISTS (
                  SELECT 1 FROM invoices i
                  WHERE i.id = NEW.invoice_id AND i.tenant_id = NEW.tenant_id
                ) OR NOT EXISTS (
                  SELECT 1 FROM customers c
                  WHERE c.id = NEW.customer_id AND c.tenant_id = NEW.tenant_id
                ) OR (
                  NEW.payment_id IS NOT NULL AND NOT EXISTS (
                    SELECT 1 FROM payments p
                    WHERE p.id = NEW.payment_id
                      AND p.tenant_id = NEW.tenant_id
                      AND p.invoice_id = NEW.invoice_id
                  )
                ) THEN
                  RAISE EXCEPTION 'DB-048 payment attempt tenant identity mismatch';
                END IF;
              ELSIF TG_TABLE_NAME = 'invoice_payment_ledger_events' THEN
                IF NOT EXISTS (
                  SELECT 1 FROM invoice_settlements s
                  WHERE s.id = NEW.settlement_id
                    AND s.tenant_id = NEW.tenant_id
                    AND s.invoice_id = NEW.invoice_id
                    AND s.customer_id = NEW.customer_id
                ) OR (
                  NEW.attempt_id IS NOT NULL AND NOT EXISTS (
                    SELECT 1 FROM invoice_payment_attempts a
                    WHERE a.id = NEW.attempt_id
                      AND a.tenant_id = NEW.tenant_id
                      AND a.invoice_id = NEW.invoice_id
                      AND a.settlement_id = NEW.settlement_id
                      AND a.customer_id = NEW.customer_id
                  )
                ) THEN
                  RAISE EXCEPTION 'DB-048 ledger tenant identity mismatch';
                END IF;
              ELSIF TG_TABLE_NAME = 'payment_overpayments' THEN
                IF NOT EXISTS (
                  SELECT 1 FROM invoice_payment_attempts a
                  WHERE a.id = NEW.source_attempt_id
                    AND a.tenant_id = NEW.tenant_id
                    AND a.invoice_id = NEW.invoice_id
                    AND a.settlement_id = NEW.settlement_id
                    AND a.customer_id = NEW.customer_id
                ) THEN
                  RAISE EXCEPTION 'DB-048 overpayment tenant identity mismatch';
                END IF;
              ELSIF TG_TABLE_NAME = 'customer_credit_entries' THEN
                IF (
                  NEW.origin_overpayment_id IS NOT NULL AND NOT EXISTS (
                    SELECT 1 FROM payment_overpayments o
                    WHERE o.id = NEW.origin_overpayment_id
                      AND o.tenant_id = NEW.tenant_id
                      AND o.customer_id = NEW.customer_id
                  )
                ) OR (
                  NEW.source_entry_id IS NOT NULL AND NOT EXISTS (
                    SELECT 1 FROM customer_credit_entries e
                    WHERE e.id = NEW.source_entry_id
                      AND e.tenant_id = NEW.tenant_id
                      AND e.customer_id = NEW.customer_id
                  )
                ) OR (
                  NEW.target_invoice_id IS NOT NULL AND NOT EXISTS (
                    SELECT 1 FROM invoices i
                    JOIN repair_orders ro ON ro.id = i.repair_order_id
                    WHERE i.id = NEW.target_invoice_id
                      AND i.tenant_id = NEW.tenant_id
                      AND ro.tenant_id = NEW.tenant_id
                      AND ro.customer_id = NEW.customer_id
                  )
                ) THEN
                  RAISE EXCEPTION 'DB-048 customer credit tenant identity mismatch';
                END IF;
              ELSIF TG_TABLE_NAME = 'customer_credit_due_diligence_events' THEN
                IF NOT EXISTS (
                  SELECT 1 FROM customer_credit_entries e
                  WHERE e.id = NEW.credit_id
                    AND e.tenant_id = NEW.tenant_id
                    AND e.customer_id = NEW.customer_id
                ) THEN
                  RAISE EXCEPTION 'DB-048 due-diligence tenant identity mismatch';
                END IF;
              ELSIF TG_TABLE_NAME = 'payment_refunds' THEN
                IF NOT EXISTS (
                  SELECT 1 FROM invoice_payment_attempts a
                  WHERE a.id = NEW.source_attempt_id
                    AND a.tenant_id = NEW.tenant_id
                    AND a.invoice_id = NEW.invoice_id
                ) OR (
                  NEW.overpayment_id IS NOT NULL AND NOT EXISTS (
                    SELECT 1 FROM payment_overpayments o
                    WHERE o.id = NEW.overpayment_id
                      AND o.tenant_id = NEW.tenant_id
                      AND o.invoice_id = NEW.invoice_id
                      AND o.source_attempt_id = NEW.source_attempt_id
                  )
                ) THEN
                  RAISE EXCEPTION 'DB-048 refund tenant identity mismatch';
                END IF;
              ELSIF TG_TABLE_NAME = 'payment_provider_disputes' THEN
                IF NOT EXISTS (
                  SELECT 1 FROM invoice_payment_attempts a
                  WHERE a.id = NEW.attempt_id
                    AND a.tenant_id = NEW.tenant_id
                    AND a.provider = NEW.provider
                    AND a.provider_account_id = NEW.provider_account_id
                    AND a.provider_charge_id = NEW.provider_charge_id
                ) THEN
                  RAISE EXCEPTION 'DB-048 dispute tenant identity mismatch';
                END IF;
              ELSIF TG_TABLE_NAME = 'payment_accounting_links' THEN
                IF (
                  NEW.invoice_id IS NOT NULL AND NOT EXISTS (
                    SELECT 1 FROM invoices i
                    WHERE i.id = NEW.invoice_id AND i.tenant_id = NEW.tenant_id
                  )
                ) OR (
                  NEW.attempt_id IS NOT NULL AND NOT EXISTS (
                    SELECT 1 FROM invoice_payment_attempts a
                    WHERE a.id = NEW.attempt_id AND a.tenant_id = NEW.tenant_id
                      AND (NEW.invoice_id IS NULL OR a.invoice_id = NEW.invoice_id)
                  )
                ) OR (
                  NEW.refund_id IS NOT NULL AND NOT EXISTS (
                    SELECT 1 FROM payment_refunds r
                    WHERE r.id = NEW.refund_id AND r.tenant_id = NEW.tenant_id
                      AND (NEW.invoice_id IS NULL OR r.invoice_id = NEW.invoice_id)
                  )
                ) OR (
                  NEW.invoice_id IS NOT NULL AND (
                    NEW.qbo_realm_snapshot IS NULL OR NOT EXISTS (
                      SELECT 1 FROM invoice_settlements s
                      WHERE s.tenant_id = NEW.tenant_id
                        AND s.invoice_id = NEW.invoice_id
                        AND s.qbo_realm_snapshot = NEW.qbo_realm_snapshot
                    )
                  )
                ) THEN
                  RAISE EXCEPTION 'DB-048 accounting link tenant identity mismatch';
                END IF;
              ELSIF TG_TABLE_NAME = 'provider_settlement_entries' THEN
                IF NOT EXISTS (
                  SELECT 1 FROM provider_settlement_batches b
                  WHERE b.id = NEW.batch_id
                    AND b.tenant_id = NEW.tenant_id
                    AND b.provider = NEW.provider
                    AND b.provider_account_id = NEW.provider_account_id
                ) OR (
                  NEW.attempt_id IS NOT NULL AND NOT EXISTS (
                    SELECT 1 FROM invoice_payment_attempts a
                    WHERE a.id = NEW.attempt_id AND a.tenant_id = NEW.tenant_id
                      AND a.provider = NEW.provider
                      AND a.provider_account_id = NEW.provider_account_id
                  )
                ) OR (
                  NEW.refund_id IS NOT NULL AND NOT EXISTS (
                    SELECT 1 FROM payment_refunds r
                    WHERE r.id = NEW.refund_id AND r.tenant_id = NEW.tenant_id
                  )
                ) OR (
                  NEW.dispute_id IS NOT NULL AND NOT EXISTS (
                    SELECT 1 FROM payment_provider_disputes d
                    WHERE d.id = NEW.dispute_id AND d.tenant_id = NEW.tenant_id
                      AND (NEW.attempt_id IS NULL OR d.attempt_id = NEW.attempt_id)
                  )
                ) OR NOT EXISTS (
                  SELECT 1 FROM tenant_payment_provider_configurations c
                  WHERE c.tenant_id = NEW.tenant_id
                    AND c.version = NEW.provider_configuration_version
                    AND c.selected_provider = NEW.provider
                    AND c.provider_account_snapshot = NEW.provider_account_id
                    AND c.qbo_realm_snapshot IS NOT DISTINCT FROM NEW.qbo_realm_snapshot
                    AND c.writer_strategy = NEW.owning_writer
                    AND NEW.account_mapping_snapshot = jsonb_build_object(
                      'stripe_clearing_account', c.stripe_clearing_account,
                      'qbp_clearing_account', c.qbp_clearing_account,
                      'check_deposit_account', c.check_deposit_account,
                      'zelle_ach_account', c.zelle_ach_account,
                      'card_fee_income_account', c.card_fee_income_account,
                      'processor_fee_expense_account', c.processor_fee_expense_account,
                      'sales_tax_liability_account', c.sales_tax_liability_account,
                      'checking_account', c.checking_account
                    )
                ) OR (
                  NEW.entry_type IN ('charge','customer_card_fee','card_fee_tax')
                  AND (NEW.attempt_id IS NULL OR NEW.refund_id IS NOT NULL OR NEW.dispute_id IS NOT NULL)
                ) OR (
                  NEW.entry_type = 'refund'
                  AND (
                    NEW.refund_id IS NULL OR NEW.attempt_id IS NULL OR NEW.dispute_id IS NOT NULL
                    OR NOT EXISTS (
                      SELECT 1 FROM payment_refunds r
                      WHERE r.id = NEW.refund_id AND r.source_attempt_id = NEW.attempt_id
                    )
                  )
                ) OR (
                  NEW.entry_type = 'dispute'
                  AND (NEW.dispute_id IS NULL OR NEW.attempt_id IS NULL OR NEW.refund_id IS NOT NULL)
                ) OR (
                  NEW.entry_type = 'stripe_fee'
                  AND (NEW.refund_id IS NOT NULL OR NEW.dispute_id IS NOT NULL)
                ) THEN
                  RAISE EXCEPTION 'DB-048 provider settlement tenant identity mismatch';
                END IF;
              END IF;
              RETURN NEW;
            END;
            $$ LANGUAGE plpgsql
        """))
        for table_name in (
            "invoice_settlements",
            "invoice_payment_attempts",
            "invoice_payment_ledger_events",
            "payment_overpayments",
            "customer_credit_entries",
            "customer_credit_due_diligence_events",
            "payment_refunds",
            "payment_provider_disputes",
            "payment_accounting_links",
            "provider_settlement_entries",
        ):
            _tenant_integrity_trigger(table_name)

        op.execute(sa.text("""
            CREATE FUNCTION guard_db048_attempt_frozen_fields() RETURNS trigger AS $$
            BEGIN
              IF TG_OP = 'DELETE' THEN
                RAISE EXCEPTION 'DB-048 payment attempts cannot be deleted';
              END IF;
              IF NEW.deleted_at IS DISTINCT FROM OLD.deleted_at THEN
                RAISE EXCEPTION 'DB-048 payment attempts cannot be deleted';
              END IF;
              IF NEW.tenant_id IS DISTINCT FROM OLD.tenant_id
                OR NEW.invoice_id IS DISTINCT FROM OLD.invoice_id
                OR NEW.settlement_id IS DISTINCT FROM OLD.settlement_id
                OR NEW.customer_id IS DISTINCT FROM OLD.customer_id
                OR NEW.source IS DISTINCT FROM OLD.source
                OR NEW.rail IS DISTINCT FROM OLD.rail
                OR NEW.provider IS DISTINCT FROM OLD.provider
                OR NEW.principal_amount IS DISTINCT FROM OLD.principal_amount
                OR NEW.card_fee_amount IS DISTINCT FROM OLD.card_fee_amount
                OR NEW.card_fee_tax_amount IS DISTINCT FROM OLD.card_fee_tax_amount
                OR NEW.provider_charge_amount IS DISTINCT FROM OLD.provider_charge_amount
                OR NEW.currency IS DISTINCT FROM OLD.currency
                OR NEW.provider_configuration_version IS DISTINCT FROM OLD.provider_configuration_version
                OR NEW.provider_account_id IS DISTINCT FROM OLD.provider_account_id
                OR NEW.actor_user_id IS DISTINCT FROM OLD.actor_user_id
                OR NEW.actor_name_snapshot IS DISTINCT FROM OLD.actor_name_snapshot
                OR NEW.actor_role_snapshot IS DISTINCT FROM OLD.actor_role_snapshot
                OR NEW.subject_type IS DISTINCT FROM OLD.subject_type
                OR NEW.subject_id IS DISTINCT FROM OLD.subject_id
                OR NEW.idempotency_key IS DISTINCT FROM OLD.idempotency_key
                OR NEW.request_hash IS DISTINCT FROM OLD.request_hash
                OR NEW.created_at IS DISTINCT FROM OLD.created_at
              THEN
                RAISE EXCEPTION 'DB-048 payment attempt frozen fields are immutable';
              END IF;
              IF (OLD.payment_id IS NOT NULL AND NEW.payment_id IS DISTINCT FROM OLD.payment_id)
                OR (OLD.provider_intent_id IS NOT NULL AND NEW.provider_intent_id IS DISTINCT FROM OLD.provider_intent_id)
                OR (OLD.provider_charge_id IS NOT NULL AND NEW.provider_charge_id IS DISTINCT FROM OLD.provider_charge_id)
                OR (OLD.provider_event_id IS NOT NULL AND NEW.provider_event_id IS DISTINCT FROM OLD.provider_event_id)
                OR (OLD.provider_reference IS NOT NULL AND NEW.provider_reference IS DISTINCT FROM OLD.provider_reference)
                OR (OLD.manual_reference_fingerprint IS NOT NULL AND NEW.manual_reference_fingerprint IS DISTINCT FROM OLD.manual_reference_fingerprint)
              THEN
                RAISE EXCEPTION 'DB-048 authoritative payment snapshots cannot be replaced';
              END IF;
              RETURN NEW;
            END;
            $$ LANGUAGE plpgsql
        """))
        op.execute(sa.text("""
            CREATE TRIGGER trg_invoice_payment_attempts_frozen_fields
            BEFORE UPDATE OR DELETE ON invoice_payment_attempts
            FOR EACH ROW EXECUTE FUNCTION guard_db048_attempt_frozen_fields()
        """))
        op.execute(sa.text("""
            CREATE FUNCTION enforce_db048_attempt_accounting_realm() RETURNS trigger AS $$
            BEGIN
              IF NOT EXISTS (
                SELECT 1
                FROM invoice_settlements s
                JOIN tenant_payment_provider_configurations c
                  ON c.tenant_id = NEW.tenant_id
                 AND c.version = NEW.provider_configuration_version
                WHERE s.id = NEW.settlement_id
                  AND s.tenant_id = NEW.tenant_id
                  AND s.invoice_id = NEW.invoice_id
                  AND (
                    (
                      NEW.source = 'backfill'
                      AND s.qbo_realm_snapshot IS NULL
                      AND s.initial_provider_configuration_version IS NULL
                      AND c.qbo_realm_snapshot IS NULL
                    ) OR (
                      s.qbo_realm_snapshot IS NOT NULL
                      AND s.initial_provider_configuration_version IS NOT NULL
                      AND c.qbo_realm_snapshot = s.qbo_realm_snapshot
                    )
                  )
              ) THEN
                RAISE EXCEPTION 'DB-048 payment attempt accounting realm mismatch';
              END IF;
              RETURN NEW;
            END;
            $$ LANGUAGE plpgsql
        """))
        op.execute(sa.text("""
            CREATE CONSTRAINT TRIGGER trg_attempts_db048_accounting_realm
            AFTER INSERT OR UPDATE OF settlement_id, tenant_id, invoice_id,
              provider_configuration_version ON invoice_payment_attempts
            DEFERRABLE INITIALLY DEFERRED
            FOR EACH ROW EXECUTE FUNCTION enforce_db048_attempt_accounting_realm()
        """))
        op.execute(sa.text("""
            CREATE FUNCTION guard_db048_settlement_accounting_realm() RETURNS trigger AS $$
            BEGIN
              IF NEW.qbo_realm_snapshot IS NOT DISTINCT FROM OLD.qbo_realm_snapshot
                AND NEW.initial_provider_configuration_version IS NOT DISTINCT FROM
                  OLD.initial_provider_configuration_version
              THEN
                RETURN NEW;
              END IF;
              IF OLD.qbo_realm_snapshot IS NULL
                AND OLD.initial_provider_configuration_version IS NULL
                AND NEW.qbo_realm_snapshot IS NOT NULL
                AND NEW.initial_provider_configuration_version IS NOT NULL
                AND NOT EXISTS (
                  SELECT 1
                  FROM invoice_payment_attempts a
                  LEFT JOIN tenant_payment_provider_configurations historical_config
                    ON historical_config.tenant_id = a.tenant_id
                   AND historical_config.version = a.provider_configuration_version
                  WHERE a.settlement_id = OLD.id
                    AND (
                      a.source IS DISTINCT FROM 'backfill'
                      OR historical_config.id IS NULL
                      OR historical_config.qbo_realm_snapshot IS NOT NULL
                    )
                )
                AND NOT EXISTS (
                  SELECT 1 FROM payment_accounting_links l
                  WHERE l.tenant_id = OLD.tenant_id
                    AND l.invoice_id = OLD.invoice_id
                )
                AND EXISTS (
                  SELECT 1 FROM tenant_payment_provider_configurations c
                  WHERE c.tenant_id = OLD.tenant_id
                    AND c.version = NEW.initial_provider_configuration_version
                    AND c.qbo_realm_snapshot = NEW.qbo_realm_snapshot
                    AND c.qbo_realm_snapshot IS NOT NULL
                    AND c.deleted_at IS NULL
                )
              THEN
                RETURN NEW;
              END IF;
              RAISE EXCEPTION 'DB-048 invoice settlement accounting realm binding is immutable';
            END;
            $$ LANGUAGE plpgsql
        """))
        op.execute(sa.text("""
            CREATE TRIGGER trg_invoice_settlements_accounting_realm_frozen
            BEFORE UPDATE OF qbo_realm_snapshot,
              initial_provider_configuration_version ON invoice_settlements
            FOR EACH ROW EXECUTE FUNCTION guard_db048_settlement_accounting_realm()
        """))
        op.execute(sa.text("""
            CREATE FUNCTION guard_db048_provider_configuration() RETURNS trigger AS $$
            BEGIN
              IF TG_OP = 'DELETE' THEN
                RAISE EXCEPTION 'DB-048 provider configurations cannot be deleted';
              END IF;
              IF NEW.id IS DISTINCT FROM OLD.id
                OR NEW.tenant_id IS DISTINCT FROM OLD.tenant_id
                OR NEW.version IS DISTINCT FROM OLD.version
                OR NEW.selected_provider IS DISTINCT FROM OLD.selected_provider
                OR NEW.effective_at IS DISTINCT FROM OLD.effective_at
                OR NEW.actor_user_id IS DISTINCT FROM OLD.actor_user_id
                OR NEW.actor_name_snapshot IS DISTINCT FROM OLD.actor_name_snapshot
                OR NEW.provider_account_snapshot IS DISTINCT FROM OLD.provider_account_snapshot
                OR NEW.qbo_realm_snapshot IS DISTINCT FROM OLD.qbo_realm_snapshot
                OR NEW.writer_strategy IS DISTINCT FROM OLD.writer_strategy
                OR NEW.idempotency_key IS DISTINCT FROM OLD.idempotency_key
                OR NEW.request_hash IS DISTINCT FROM OLD.request_hash
                OR NEW.stripe_clearing_account IS DISTINCT FROM OLD.stripe_clearing_account
                OR NEW.qbp_clearing_account IS DISTINCT FROM OLD.qbp_clearing_account
                OR NEW.check_deposit_account IS DISTINCT FROM OLD.check_deposit_account
                OR NEW.zelle_ach_account IS DISTINCT FROM OLD.zelle_ach_account
                OR NEW.card_fee_income_account IS DISTINCT FROM OLD.card_fee_income_account
                OR NEW.processor_fee_expense_account IS DISTINCT FROM OLD.processor_fee_expense_account
                OR NEW.sales_tax_liability_account IS DISTINCT FROM OLD.sales_tax_liability_account
                OR NEW.checking_account IS DISTINCT FROM OLD.checking_account
                OR NEW.created_at IS DISTINCT FROM OLD.created_at
                OR NEW.deleted_at IS DISTINCT FROM OLD.deleted_at
              THEN
                RAISE EXCEPTION 'DB-048 provider configuration frozen fields are immutable';
              END IF;
              IF NEW.is_active IS DISTINCT FROM OLD.is_active
                OR NEW.deactivated_at IS DISTINCT FROM OLD.deactivated_at
              THEN
                IF NOT (
                  OLD.is_active IS TRUE AND NEW.is_active IS FALSE
                  AND OLD.deactivated_at IS NULL AND NEW.deactivated_at IS NOT NULL
                ) THEN
                  RAISE EXCEPTION 'DB-048 provider configuration lifecycle transition is invalid';
                END IF;
              END IF;
              RETURN NEW;
            END;
            $$ LANGUAGE plpgsql
        """))
        op.execute(sa.text("""
            CREATE TRIGGER trg_tenant_payment_provider_configurations_frozen
            BEFORE UPDATE OR DELETE ON tenant_payment_provider_configurations
            FOR EACH ROW EXECUTE FUNCTION guard_db048_provider_configuration()
        """))
        op.execute(sa.text("""
            CREATE FUNCTION guard_db048_accounting_link() RETURNS trigger AS $$
            BEGIN
              IF TG_OP = 'DELETE' THEN
                RAISE EXCEPTION 'DB-048 accounting links cannot be deleted';
              END IF;
              IF NEW.id IS DISTINCT FROM OLD.id
                OR NEW.tenant_id IS DISTINCT FROM OLD.tenant_id
                OR NEW.invoice_id IS DISTINCT FROM OLD.invoice_id
                OR NEW.attempt_id IS DISTINCT FROM OLD.attempt_id
                OR NEW.refund_id IS DISTINCT FROM OLD.refund_id
                OR NEW.financial_object_type IS DISTINCT FROM OLD.financial_object_type
                OR NEW.financial_object_id IS DISTINCT FROM OLD.financial_object_id
                OR NEW.operation_version IS DISTINCT FROM OLD.operation_version
                OR NEW.principal_amount_snapshot IS DISTINCT FROM OLD.principal_amount_snapshot
                OR NEW.gross_amount_snapshot IS DISTINCT FROM OLD.gross_amount_snapshot
                OR NEW.owning_writer IS DISTINCT FROM OLD.owning_writer
                OR NEW.account_mapping_snapshot IS DISTINCT FROM OLD.account_mapping_snapshot
                OR NEW.qbo_realm_snapshot IS DISTINCT FROM OLD.qbo_realm_snapshot
                OR NEW.created_at IS DISTINCT FROM OLD.created_at
                OR NEW.deleted_at IS DISTINCT FROM OLD.deleted_at
              THEN
                RAISE EXCEPTION 'DB-048 accounting link frozen fields are immutable';
              END IF;
              RETURN NEW;
            END;
            $$ LANGUAGE plpgsql
        """))
        op.execute(sa.text("""
            CREATE TRIGGER trg_payment_accounting_links_frozen
            BEFORE UPDATE OR DELETE ON payment_accounting_links
            FOR EACH ROW EXECUTE FUNCTION guard_db048_accounting_link()
        """))
        op.execute(sa.text("""
            CREATE FUNCTION enforce_db048_payment_attempt_from_payment() RETURNS trigger AS $$
            BEGIN
              IF NEW.invoice_payment_attempt_id IS NOT NULL THEN
                IF NOT EXISTS (
                  SELECT 1 FROM invoice_payment_attempts a
                  WHERE a.id = NEW.invoice_payment_attempt_id
                    AND a.payment_id = NEW.id
                    AND a.tenant_id = NEW.tenant_id
                    AND a.invoice_id = NEW.invoice_id
                ) THEN
                  RAISE EXCEPTION 'DB-048 payment attempt link is not reciprocal';
                END IF;
              END IF;
              RETURN NEW;
            END;
            $$ LANGUAGE plpgsql
        """))
        op.execute(sa.text("""
            CREATE FUNCTION enforce_db048_payment_from_attempt() RETURNS trigger AS $$
            BEGIN
              IF NEW.payment_id IS NOT NULL THEN
                IF NOT EXISTS (
                  SELECT 1 FROM payments p
                  WHERE p.id = NEW.payment_id
                    AND p.invoice_payment_attempt_id = NEW.id
                    AND p.tenant_id = NEW.tenant_id
                    AND p.invoice_id = NEW.invoice_id
                ) THEN
                  RAISE EXCEPTION 'DB-048 payment attempt link is not reciprocal';
                END IF;
              END IF;
              RETURN NEW;
            END;
            $$ LANGUAGE plpgsql
        """))
        op.execute(sa.text("""
            CREATE CONSTRAINT TRIGGER trg_payments_db048_attempt_reciprocity
            AFTER INSERT OR UPDATE OF invoice_payment_attempt_id ON payments
            DEFERRABLE INITIALLY DEFERRED
            FOR EACH ROW EXECUTE FUNCTION enforce_db048_payment_attempt_from_payment()
        """))
        op.execute(sa.text("""
            CREATE CONSTRAINT TRIGGER trg_attempts_db048_payment_reciprocity
            AFTER INSERT OR UPDATE OF payment_id ON invoice_payment_attempts
            DEFERRABLE INITIALLY DEFERRED
            FOR EACH ROW EXECUTE FUNCTION enforce_db048_payment_from_attempt()
        """))
        op.execute(sa.text("""
            CREATE FUNCTION guard_db048_payment_attempt_link_frozen() RETURNS trigger AS $$
            BEGIN
              IF OLD.invoice_payment_attempt_id IS NOT NULL
                AND NEW.invoice_payment_attempt_id IS DISTINCT FROM OLD.invoice_payment_attempt_id
              THEN
                RAISE EXCEPTION 'DB-048 payment attempt link cannot be replaced or removed';
              END IF;
              RETURN NEW;
            END;
            $$ LANGUAGE plpgsql
        """))
        op.execute(sa.text("""
            CREATE TRIGGER trg_payments_db048_attempt_link_frozen
            BEFORE UPDATE OF invoice_payment_attempt_id ON payments
            FOR EACH ROW EXECUTE FUNCTION guard_db048_payment_attempt_link_frozen()
        """))
        _append_only_trigger("invoice_payment_ledger_events", "reject_invoice_payment_ledger_mutation")
        _append_only_trigger("customer_credit_entries", "reject_customer_credit_entry_mutation")
        _append_only_trigger("customer_credit_due_diligence_events", "reject_customer_credit_due_diligence_mutation")
        _append_only_trigger("provider_settlement_entries", "reject_provider_settlement_entry_mutation")


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        has_rows = bind.execute(sa.text("""
            SELECT EXISTS (
                SELECT 1 FROM tenant_payment_provider_configurations
                UNION ALL SELECT 1 FROM invoice_payment_attempts
                UNION ALL SELECT 1 FROM invoice_settlements
                UNION ALL SELECT 1 FROM invoice_payment_ledger_events
                UNION ALL SELECT 1 FROM payment_overpayments
                UNION ALL SELECT 1 FROM customer_credit_entries
                UNION ALL SELECT 1 FROM customer_credit_due_diligence_events
                UNION ALL SELECT 1 FROM payment_refunds
                UNION ALL SELECT 1 FROM payment_provider_disputes
                UNION ALL SELECT 1 FROM payment_accounting_links
                UNION ALL SELECT 1 FROM provider_settlement_batches
                UNION ALL SELECT 1 FROM provider_settlement_entries
            )
        """)).scalar()
        if has_rows:
            raise RuntimeError("DB-048 downgrade refused: financial ledger rows exist")
        for table_name, function_name in (
            ("provider_settlement_entries", "reject_provider_settlement_entry_mutation"),
            ("customer_credit_due_diligence_events", "reject_customer_credit_due_diligence_mutation"),
            ("customer_credit_entries", "reject_customer_credit_entry_mutation"),
            ("invoice_payment_ledger_events", "reject_invoice_payment_ledger_mutation"),
        ):
            op.execute(sa.text(f"DROP TRIGGER IF EXISTS trg_{table_name}_no_update_delete ON {table_name}"))
            op.execute(sa.text(f"DROP FUNCTION IF EXISTS {function_name}()"))
        op.execute(sa.text(
            "DROP TRIGGER IF EXISTS trg_invoice_payment_attempts_frozen_fields "
            "ON invoice_payment_attempts"
        ))
        op.execute(sa.text("DROP FUNCTION IF EXISTS guard_db048_attempt_frozen_fields()"))
        op.execute(sa.text(
            "DROP TRIGGER IF EXISTS trg_attempts_db048_accounting_realm "
            "ON invoice_payment_attempts"
        ))
        op.execute(sa.text("DROP FUNCTION IF EXISTS enforce_db048_attempt_accounting_realm()"))
        op.execute(sa.text(
            "DROP TRIGGER IF EXISTS trg_invoice_settlements_accounting_realm_frozen "
            "ON invoice_settlements"
        ))
        op.execute(sa.text("DROP FUNCTION IF EXISTS guard_db048_settlement_accounting_realm()"))
        op.execute(sa.text(
            "DROP TRIGGER IF EXISTS trg_tenant_payment_provider_configurations_frozen "
            "ON tenant_payment_provider_configurations"
        ))
        op.execute(sa.text("DROP FUNCTION IF EXISTS guard_db048_provider_configuration()"))
        op.execute(sa.text(
            "DROP TRIGGER IF EXISTS trg_payment_accounting_links_frozen "
            "ON payment_accounting_links"
        ))
        op.execute(sa.text("DROP FUNCTION IF EXISTS guard_db048_accounting_link()"))
        op.execute(sa.text(
            "DROP TRIGGER IF EXISTS trg_payments_db048_attempt_link_frozen ON payments"
        ))
        op.execute(sa.text("DROP FUNCTION IF EXISTS guard_db048_payment_attempt_link_frozen()"))
        op.execute(sa.text(
            "DROP TRIGGER IF EXISTS trg_payments_db048_attempt_reciprocity ON payments"
        ))
        op.execute(sa.text(
            "DROP TRIGGER IF EXISTS trg_attempts_db048_payment_reciprocity "
            "ON invoice_payment_attempts"
        ))
        op.execute(sa.text("DROP FUNCTION IF EXISTS enforce_db048_payment_attempt_from_payment()"))
        op.execute(sa.text("DROP FUNCTION IF EXISTS enforce_db048_payment_from_attempt()"))
        for table_name in (
            "provider_settlement_entries",
            "payment_accounting_links",
            "payment_provider_disputes",
            "payment_refunds",
            "customer_credit_due_diligence_events",
            "customer_credit_entries",
            "payment_overpayments",
            "invoice_payment_ledger_events",
            "invoice_payment_attempts",
            "invoice_settlements",
        ):
            op.execute(sa.text(
                f"DROP TRIGGER IF EXISTS trg_{table_name}_tenant_integrity ON {table_name}"
            ))
        op.execute(sa.text("DROP FUNCTION IF EXISTS enforce_db048_tenant_integrity()"))

    op.drop_table("invoice_settlement_backfill_runs")
    op.drop_index("ix_provider_settlement_entry_batch", table_name="provider_settlement_entries")
    op.drop_table("provider_settlement_entries")
    op.drop_index("ix_provider_settlement_batch_tenant_state", table_name="provider_settlement_batches")
    op.drop_table("provider_settlement_batches")
    op.drop_index("ix_payment_accounting_links_tenant_state", table_name="payment_accounting_links")
    op.drop_table("payment_accounting_links")
    op.drop_index("ix_payment_provider_dispute_attempt", table_name="payment_provider_disputes")
    op.drop_table("payment_provider_disputes")
    op.drop_index("ix_payment_refunds_tenant_state", table_name="payment_refunds")
    op.drop_table("payment_refunds")
    op.drop_index("ix_customer_credit_due_diligence_credit", table_name="customer_credit_due_diligence_events")
    op.drop_table("customer_credit_due_diligence_events")
    op.drop_index("ix_customer_credit_entries_customer", table_name="customer_credit_entries")
    op.drop_table("customer_credit_entries")
    op.drop_index("ix_payment_overpayment_tenant_state", table_name="payment_overpayments")
    op.drop_table("payment_overpayments")
    op.drop_index("ix_invoice_payment_ledger_attempt", table_name="invoice_payment_ledger_events")
    op.drop_index("ix_invoice_payment_ledger_invoice", table_name="invoice_payment_ledger_events")
    op.drop_table("invoice_payment_ledger_events")
    op.drop_index("ix_payments_invoice_payment_attempt_id", table_name="payments")
    op.drop_constraint("uq_payments_invoice_payment_attempt", "payments", type_="unique")
    op.drop_constraint("fk_payments_invoice_payment_attempt", "payments", type_="foreignkey")
    op.drop_column("payments", "invoice_payment_attempt_id")
    op.drop_index("ix_invoice_payment_attempt_provider_identity", table_name="invoice_payment_attempts")
    op.drop_index("ix_invoice_payment_attempt_pending", table_name="invoice_payment_attempts")
    op.drop_index("ix_invoice_payment_attempt_invoice_created", table_name="invoice_payment_attempts")
    op.drop_table("invoice_payment_attempts")
    op.drop_index("ix_invoice_settlements_invoice_id", table_name="invoice_settlements")
    op.drop_index("ix_invoice_settlements_tenant_state", table_name="invoice_settlements")
    op.drop_table("invoice_settlements")
    op.drop_index("uq_tenant_payment_provider_one_active", table_name="tenant_payment_provider_configurations")
    op.drop_index("ix_tenant_payment_provider_active", table_name="tenant_payment_provider_configurations")
    op.drop_table("tenant_payment_provider_configurations")
    op.drop_index("ix_repair_orders_vehicle_released_at", table_name="repair_orders")
    op.drop_constraint("fk_repair_orders_vehicle_released_by_user", "repair_orders", type_="foreignkey")
    op.drop_column("repair_orders", "vehicle_release_reason")
    op.drop_column("repair_orders", "vehicle_released_by_user_id")
    op.drop_column("repair_orders", "vehicle_released_at")
    op.drop_column("tenants", "invoice_split_payments_enabled")
