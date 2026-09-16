"""Validate credit application accounting links across same-customer invoices.

The target invoice differs from the receipt invoice by design. Only the exact
applied -> issued -> overpayment -> source attempt chain admits that difference.
All preexisting tenant/realm/refund and other financial-object guards remain.
"""
from alembic import op
import sqlalchemy as sa

revision = "147_credit_link_identity"
down_revision = "142_qbo_shop_activation"
branch_labels = None
depends_on = None

_ORIGINAL_FUNCTION = r"""
CREATE OR REPLACE FUNCTION enforce_db048_tenant_integrity() RETURNS trigger AS $$
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
"""
_OLD_ATTEMPT_INVOICE_GUARD = 'AND (NEW.invoice_id IS NULL OR a.invoice_id = NEW.invoice_id)'
_CREDIT_ATTEMPT_INVOICE_GUARD = r"""AND (
                        NEW.invoice_id IS NULL OR a.invoice_id = NEW.invoice_id
                        OR (
                          NEW.financial_object_type = 'customer_credit_application'
                          AND EXISTS (
                            SELECT 1 FROM customer_credit_entries applied
                            JOIN customer_credit_entries issued
                              ON issued.id = applied.source_entry_id
                              AND issued.entry_type = 'issued'
                              AND issued.tenant_id = applied.tenant_id
                              AND issued.customer_id = applied.customer_id
                            JOIN payment_overpayments origin
                              ON origin.id = issued.origin_overpayment_id
                              AND origin.tenant_id = issued.tenant_id
                              AND origin.customer_id = issued.customer_id
                            JOIN invoices target ON target.id = applied.target_invoice_id
                            JOIN repair_orders target_order ON target_order.id = target.repair_order_id
                            WHERE applied.id = NEW.financial_object_id
                              AND applied.entry_type = 'applied'
                              AND applied.tenant_id = NEW.tenant_id
                              AND applied.target_invoice_id = NEW.invoice_id
                              AND applied.customer_id = a.customer_id
                              AND origin.source_attempt_id = a.id
                              AND origin.invoice_id = a.invoice_id
                              AND target.tenant_id = NEW.tenant_id
                              AND target_order.tenant_id = NEW.tenant_id
                              AND target_order.customer_id = applied.customer_id
                          )
                        )
                      )"""


def upgrade():
    if op.get_bind().dialect.name != "postgresql":
        return
    assert _ORIGINAL_FUNCTION.count(_OLD_ATTEMPT_INVOICE_GUARD) == 1
    op.execute(sa.text(_ORIGINAL_FUNCTION.replace(
        _OLD_ATTEMPT_INVOICE_GUARD, _CREDIT_ATTEMPT_INVOICE_GUARD,
    )))


def downgrade():
    if op.get_bind().dialect.name != "postgresql":
        return
    # Never restore the old incompatible trigger over valid cross-invoice links.
    # Application rollback can keep this backward-compatible integrity extension.
    count = op.get_bind().scalar(sa.text("""
        SELECT count(*) FROM payment_accounting_links link
        JOIN invoice_payment_attempts attempt ON attempt.id = link.attempt_id
        WHERE link.invoice_id IS NOT NULL AND link.invoice_id <> attempt.invoice_id
    """))
    if count:
        raise RuntimeError("Cannot downgrade credit identity while cross-invoice links exist; retain migration for application rollback")
    op.execute(sa.text(_ORIGINAL_FUNCTION))
