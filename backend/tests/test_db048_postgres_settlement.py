"""DB-048 database invariants that require an isolated PostgreSQL 15 database."""
from __future__ import annotations

import os
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine


POSTGRES_URL = "DB048_POSTGRES_URL"
pytestmark = pytest.mark.skipif(
    not os.environ.get(POSTGRES_URL), reason="requires isolated PostgreSQL 15"
)


def _ids() -> dict[str, object]:
    return {
        "tenant_a": uuid4(),
        "tenant_b": uuid4(),
        "customer_a": uuid4(),
        "customer_b": uuid4(),
        "user_a": uuid4(),
        "user_b": uuid4(),
        "vehicle_a": uuid4(),
        "vehicle_b": uuid4(),
        "order_a": uuid4(),
        "order_a2": uuid4(),
        "order_b": uuid4(),
        "order_native_realm": uuid4(),
        "invoice_a": uuid4(),
        "invoice_a2": uuid4(),
        "invoice_b": uuid4(),
        "invoice_native_realm": uuid4(),
        "settlement_a": uuid4(),
        "settlement_a2": uuid4(),
        "settlement_b": uuid4(),
        "settlement_invalid": uuid4(),
        "settlement_native_realm": uuid4(),
        "attempt_pending": uuid4(),
        "attempt_failed": uuid4(),
        "attempt_expired": uuid4(),
        "attempt_confirmed_manual": uuid4(),
        "attempt_confirmed_card": uuid4(),
        "attempt_overpayment": uuid4(),
        "attempt_reversed": uuid4(),
        "attempt_backfill_refunded": uuid4(),
        "attempt_one_sided": uuid4(),
        "attempt_one_sided_reverse": uuid4(),
        "attempt_live": uuid4(),
        "attempt_backfill": uuid4(),
        "attempt_cross_invoice": uuid4(),
        "attempt_cross_tenant": uuid4(),
        "attempt_realm_mismatch": uuid4(),
        "attempt_legacy_realm": uuid4(),
        "attempt_native_realm": uuid4(),
        "payment_one_sided": uuid4(),
        "payment_one_sided_reverse": uuid4(),
        "payment_live": uuid4(),
        "payment_backfill": uuid4(),
        "payment_cross_invoice": uuid4(),
        "payment_cross_tenant": uuid4(),
        "payment_projection": uuid4(),
        "ledger_a": uuid4(),
        "batch_a": uuid4(),
        "link_a": uuid4(),
        "link_realm_mismatch": uuid4(),
        "entry_a": uuid4(),
    }


@pytest.mark.asyncio
async def test_paid_invoice_read_model_includes_required_payment_identity():
    engine = create_async_engine(os.environ[POSTGRES_URL])
    ids = _ids()
    suffix = uuid4().hex
    try:
        await _seed_financial_identity(engine, ids, suffix)
        await _execute(
            engine,
            """
            INSERT INTO payments (
              id, tenant_id, invoice_id, payment_number, amount, method,
              status, quickbooks_charge_status, quickbooks_reconciled_at
            ) VALUES (
              :payment_projection, :tenant_a, :invoice_a,
              :payment_number, 100, 'quickbooks', 'completed', 'CAPTURED',
              '2026-09-01T12:00:00+00:00'
            );
            UPDATE invoices
            SET status='paid', paid_at='2026-09-01T12:00:00+00:00'
            WHERE id=:invoice_a
            """,
            {
                **ids,
                "payment_number": f"DB048-PROJECTION-{suffix}",
            },
        )

        async with engine.connect() as connection:
            payment = (
                await connection.execute(
                    text(
                        "SELECT payload->'payment' "
                        "FROM invoice_read_models WHERE invoice_id=:invoice_a"
                    ),
                    ids,
                )
            ).scalar_one()

        assert payment["id"] == str(ids["payment_projection"])
        assert payment["amount"] == 100
        assert payment["method"] == "quickbooks"
        assert payment["quickbooks_charge_status"] == "CAPTURED"
        assert payment["quickbooks_reconciled_at"] == "2026-09-01T12:00:00+00:00"
    finally:
        await engine.dispose()


async def _execute(engine: AsyncEngine, sql: str, params: dict[str, object]) -> None:
    async with engine.begin() as connection:
        for statement in (part.strip() for part in sql.split(";")):
            if statement:
                await connection.execute(text(statement), params)


async def _seed_financial_identity(
    engine: AsyncEngine,
    ids: dict[str, object],
    suffix: str,
) -> None:
    """Create two tenants and three invoice/settlement identities."""
    await _execute(
        engine,
        """
        INSERT INTO tenants (
          id, name, slug, sms_enabled, timezone, default_core_hours_minutes,
          default_shift_start_local, default_shift_end_local,
          internal_labor_rate
        ) VALUES
          (:tenant_a, 'DB048 tenant A', :slug_a, false,
           'America/New_York', 480, '08:00', '17:00', 100),
          (:tenant_b, 'DB048 tenant B', :slug_b, false,
           'America/New_York', 480, '08:00', '17:00', 100);

        INSERT INTO customers (
          id, tenant_id, first_name, last_name, email,
          sms_opt_out, is_internal_fleet
        ) VALUES
          (:customer_a, :tenant_a, 'Customer', 'A', :email_a, false, false),
          (:customer_b, :tenant_b, 'Customer', 'B', :email_b, false, false);

        INSERT INTO vehicles (
          id, tenant_id, customer_id, make, model, pm_interval_miles
        ) VALUES
          (:vehicle_a, :tenant_a, :customer_a, 'Test', 'A', 10000),
          (:vehicle_b, :tenant_b, :customer_b, 'Test', 'B', 10000);

        INSERT INTO users (
          id, email, first_name, last_name, role, is_active, is_verified,
          permissions, can_access_messaging, tenant_id
        ) VALUES
          (:user_a, :user_email_a, 'DB048', 'Owner A', 'garage_owner', true,
           true, '{}', false, :tenant_a),
          (:user_b, :user_email_b, 'DB048', 'Owner B', 'garage_owner', true,
           true, '{}', false, :tenant_b);

        INSERT INTO tenant_payment_provider_configurations (
          id, tenant_id, version, selected_provider, readiness_state,
          is_active, deactivated_at, actor_user_id, actor_name_snapshot,
          provider_account_snapshot, qbo_realm_snapshot, writer_strategy,
          idempotency_key, request_hash, stripe_clearing_account,
          processor_fee_expense_account, checking_account
        ) VALUES
          (gen_random_uuid(), :tenant_a, 1, 'stripe_connect', 'ready', true, NULL,
           :user_a, 'DB048 Owner A', :account_a, :realm_a, 'dieselbridge',
           :config_key_a, repeat('a', 64), 'Stripe Clearing A',
           'Processor Fees A', 'Checking A'),
          (gen_random_uuid(), :tenant_b, 1, 'stripe_connect', 'ready', true, NULL,
           :user_b, 'DB048 Owner B', :account_b, :realm_b, 'dieselbridge',
           :config_key_b, repeat('b', 64), 'Stripe Clearing B',
           'Processor Fees B', 'Checking B'),
          (gen_random_uuid(), :tenant_a, 2, 'stripe_connect', 'legacy', false,
           now(), :user_a, 'Legacy import', :account_a, NULL, 'dieselbridge',
           :config_key_legacy, repeat('c', 64), 'Stripe Clearing A',
           'Processor Fees A', 'Checking A');

        INSERT INTO repair_orders (
          id, tenant_id, customer_id, vehicle_id, order_number, status,
          is_internal, is_pm, labor_discount_amount, order_discount_amount
        ) VALUES
          (:order_a, :tenant_a, :customer_a, :vehicle_a, :order_no_a,
           'completed', false, false, 0, 0),
          (:order_a2, :tenant_a, :customer_a, :vehicle_a, :order_no_a2,
           'completed', false, false, 0, 0),
          (:order_b, :tenant_b, :customer_b, :vehicle_b, :order_no_b,
           'completed', false, false, 0, 0);

        INSERT INTO invoices (
          id, tenant_id, repair_order_id, invoice_number, status,
          subtotal, total_amount, zelle_pending_reminder_count
        ) VALUES
          (:invoice_a, :tenant_a, :order_a, :invoice_no_a,
           'sent', 100, 100, 0),
          (:invoice_a2, :tenant_a, :order_a2, :invoice_no_a2,
           'sent', 100, 100, 0),
          (:invoice_b, :tenant_b, :order_b, :invoice_no_b,
           'sent', 100, 100, 0);

        INSERT INTO invoice_settlements (
          id, tenant_id, invoice_id, customer_id, principal_total,
          max_card_fee, max_card_fee_tax, sales_tax_rate_snapshot,
          card_fee_rate_snapshot, currency, qbo_realm_snapshot,
          initial_provider_configuration_version
        ) VALUES
          (:settlement_a, :tenant_a, :invoice_a, :customer_a,
           100, 3, 0.15, 0.05, 0.03, 'USD', :realm_a, 1),
          (:settlement_a2, :tenant_a, :invoice_a2, :customer_a,
           100, 3, 0.15, 0.05, 0.03, 'USD', NULL, NULL),
          (:settlement_b, :tenant_b, :invoice_b, :customer_b,
           100, 3, 0.15, 0.05, 0.03, 'USD', :realm_b, 1);
        """,
        {
            **ids,
            "slug_a": f"db048-pg-a-{suffix}",
            "slug_b": f"db048-pg-b-{suffix}",
            "email_a": f"db048-pg-a-{suffix}@example.test",
            "email_b": f"db048-pg-b-{suffix}@example.test",
            "user_email_a": f"db048-pg-owner-a-{suffix}@example.test",
            "user_email_b": f"db048-pg-owner-b-{suffix}@example.test",
            "account_a": f"acct_db048_a_{suffix}",
            "account_b": f"acct_db048_b_{suffix}",
            "realm_a": f"realm-db048-a-{suffix}",
            "realm_b": f"realm-db048-b-{suffix}",
            "config_key_a": f"db048-config-a-{suffix}",
            "config_key_b": f"db048-config-b-{suffix}",
            "config_key_legacy": f"db048-config-legacy-{suffix}",
            "order_no_a": f"DB048-A-{suffix}",
            "order_no_a2": f"DB048-A2-{suffix}",
            "order_no_b": f"DB048-B-{suffix}",
            "invoice_no_a": f"DB048-INV-A-{suffix}",
            "invoice_no_a2": f"DB048-INV-A2-{suffix}",
            "invoice_no_b": f"DB048-INV-B-{suffix}",
        },
    )


@pytest.mark.asyncio
async def test_db048_postgres_attempt_money_and_immutability_guards():
    engine = create_async_engine(os.environ[POSTGRES_URL])
    ids = _ids()
    suffix = uuid4().hex
    try:
        await _seed_financial_identity(engine, ids, suffix)
        await _execute(
            engine,
            """
            INSERT INTO invoice_payment_attempts (
              id, tenant_id, invoice_id, settlement_id, customer_id,
              source, rail, provider, state, principal_amount,
              provider_charge_amount, received_amount,
              applied_principal_amount, unapplied_amount, currency,
              provider_configuration_version, actor_name_snapshot,
              subject_type, idempotency_key, request_hash
            ) VALUES (
              :attempt_legacy_realm, :tenant_a, :invoice_a2, :settlement_a2,
              :customer_a, 'backfill', 'check', 'manual', 'confirmed', 5, 5,
              5, 5, 0, 'USD', 2, 'Legacy import', 'backfill',
              :legacy_attempt_key, repeat('d', 64)
            )
            """,
            {**ids, "legacy_attempt_key": f"db048-legacy-realm-{suffix}"},
        )
        await _execute(
            engine,
            "UPDATE invoice_settlements SET qbo_realm_snapshot=:realm_a, "
            "initial_provider_configuration_version=1 "
            "WHERE id=:settlement_a2",
            {**ids, "realm_a": f"realm-db048-a-{suffix}"},
        )
        with pytest.raises(
            DBAPIError,
            match="invoice settlement accounting realm binding is immutable",
        ):
            await _execute(
                engine,
                """
                INSERT INTO repair_orders (
                  id, tenant_id, customer_id, vehicle_id, order_number, status,
                  is_internal, is_pm, labor_discount_amount,
                  order_discount_amount
                ) VALUES (
                  :order_native_realm, :tenant_a, :customer_a, :vehicle_a,
                  :native_order_number, 'completed', false, false, 0, 0
                );
                INSERT INTO invoices (
                  id, tenant_id, repair_order_id, invoice_number, status,
                  subtotal, total_amount, zelle_pending_reminder_count
                ) VALUES (
                  :invoice_native_realm, :tenant_a, :order_native_realm,
                  :native_invoice_number, 'sent', 10, 10, 0
                );
                INSERT INTO invoice_settlements (
                  id, tenant_id, invoice_id, customer_id, principal_total,
                  max_card_fee, max_card_fee_tax, sales_tax_rate_snapshot,
                  card_fee_rate_snapshot, currency
                ) VALUES (
                  :settlement_native_realm, :tenant_a, :invoice_native_realm,
                  :customer_a, 10, 0, 0, 0, 0, 'USD'
                );
                INSERT INTO invoice_payment_attempts (
                  id, tenant_id, invoice_id, settlement_id, customer_id,
                  source, rail, provider, state, principal_amount,
                  provider_charge_amount, currency,
                  provider_configuration_version, actor_name_snapshot,
                  subject_type, idempotency_key, request_hash
                ) VALUES (
                  :attempt_native_realm, :tenant_a, :invoice_native_realm,
                  :settlement_native_realm, :customer_a, 'staff', 'check',
                  'manual', 'pending', 5, 5, 'USD', 1, 'Garage Owner', 'user',
                  :native_attempt_key, repeat('e', 64)
                );
                UPDATE invoice_settlements
                SET qbo_realm_snapshot=:realm_a,
                    initial_provider_configuration_version=1
                WHERE id=:settlement_native_realm
                """,
                {
                    **ids,
                    "native_order_number": f"DB048-NATIVE-{suffix}",
                    "native_invoice_number": f"DB048-INV-NATIVE-{suffix}",
                    "native_attempt_key": f"db048-native-realm-{suffix}",
                    "realm_a": f"realm-db048-a-{suffix}",
                },
            )
        for settlement_rebind in (
            "UPDATE invoice_settlements SET qbo_realm_snapshot='realm-rebound' "
            "WHERE id=:settlement_a",
            "UPDATE invoice_settlements SET qbo_realm_snapshot=NULL, "
            "initial_provider_configuration_version=NULL WHERE id=:settlement_a",
        ):
            with pytest.raises(
                DBAPIError,
                match="invoice settlement accounting realm binding is immutable",
            ):
                await _execute(engine, settlement_rebind, ids)
        await _execute(
            engine,
            "UPDATE invoice_settlements "
            "SET accounting_sync_status='accounting_sync_pending' "
            "WHERE id=:settlement_a",
            ids,
        )
        await _execute(
            engine,
            """
            INSERT INTO invoice_payment_attempts (
              id, tenant_id, invoice_id, settlement_id, customer_id,
              source, rail, provider, state, principal_amount,
              card_fee_amount, card_fee_tax_amount, provider_charge_amount,
              currency, provider_configuration_version, actor_name_snapshot,
              subject_type, idempotency_key, request_hash
            ) VALUES (
              :attempt_pending, :tenant_a, :invoice_a, :settlement_a,
              :customer_a, 'staff', 'check', 'manual', 'pending', 25,
              0, 0, 25, 'USD', 1, 'DB048 owner', 'user',
              :pending_key, repeat('a', 64)
            );

            INSERT INTO invoice_payment_attempts (
              id, tenant_id, invoice_id, settlement_id, customer_id,
              source, rail, provider, state, principal_amount,
              provider_charge_amount, currency,
              provider_configuration_version, actor_name_snapshot,
              subject_type, idempotency_key, request_hash
            ) VALUES (
              :attempt_backfill_refunded, :tenant_a, :invoice_a,
              :settlement_a, :customer_a, 'backfill', 'check', 'manual',
              'pending', 10, 10, 'USD', 1, 'Legacy payment', 'backfill',
              :backfill_refund_key, repeat('b', 64)
            );

            INSERT INTO invoice_payment_ledger_events (
              id, tenant_id, invoice_id, settlement_id, attempt_id,
              customer_id, actor_name_snapshot, sequence, idempotency_key,
              event_type, money_snapshot, evidence_snapshot
            ) VALUES (
              :ledger_a, :tenant_a, :invoice_a, :settlement_a,
              :attempt_pending, :customer_a, 'DB048 owner', 1, :ledger_key,
              'payment.attempt_created', '{}', '{}'
            );

            INSERT INTO provider_settlement_batches (
              id, tenant_id, provider, provider_account_id,
              provider_batch_id, currency, entry_manifest_hash
            ) VALUES (
              :batch_a, :tenant_a, 'stripe_connect', :provider_account,
              :provider_batch, 'USD', repeat('f', 64)
            );
            """,
            {
                **ids,
                "pending_key": f"db048-pending-{suffix}",
                "backfill_refund_key": f"db048-backfill-refund-{suffix}",
                "ledger_key": f"db048-ledger-{suffix}",
                "provider_account": f"acct_db048_a_{suffix}",
                "provider_batch": f"po_{suffix}",
            },
        )

        with pytest.raises(DBAPIError, match="append-only"):
            await _execute(
                engine,
                "UPDATE invoice_payment_ledger_events "
                "SET event_type='tampered' WHERE id=:ledger_a",
                ids,
            )
        with pytest.raises(DBAPIError, match="append-only"):
            await _execute(
                engine,
                "DELETE FROM invoice_payment_ledger_events WHERE id=:ledger_a",
                ids,
            )
        with pytest.raises(DBAPIError, match="settlement tenant identity mismatch"):
            await _execute(
                engine,
                """
                INSERT INTO invoice_settlements (
                  id, tenant_id, invoice_id, customer_id, principal_total,
                  max_card_fee, max_card_fee_tax, sales_tax_rate_snapshot,
                  card_fee_rate_snapshot, currency
                ) VALUES (
                  :settlement_invalid, :tenant_b, :invoice_a, :customer_b,
                  100, 0, 0, 0, 0, 'USD'
                )
                """,
                ids,
            )
        with pytest.raises(DBAPIError, match="frozen fields are immutable"):
            await _execute(
                engine,
                "UPDATE invoice_payment_attempts "
                "SET principal_amount=26 WHERE id=:attempt_pending",
                ids,
            )
        with pytest.raises(DBAPIError, match="attempts cannot be deleted"):
            await _execute(
                engine,
                "UPDATE invoice_payment_attempts SET deleted_at=now() "
                "WHERE id=:attempt_pending",
                ids,
            )
        with pytest.raises(DBAPIError, match="attempts cannot be deleted"):
            await _execute(
                engine,
                "DELETE FROM invoice_payment_attempts WHERE id=:attempt_pending",
                ids,
            )

        impossible_money_updates = (
            "state='confirmed', received_amount=-1, applied_principal_amount=0, unapplied_amount=0",
            "state='confirmed', received_amount=1, applied_principal_amount=-1, unapplied_amount=2",
            "state='confirmed', received_amount=26, applied_principal_amount=26, unapplied_amount=0",
            "state='confirmed', received_amount=20, applied_principal_amount=21, unapplied_amount=0",
            "state='confirmed', received_amount=25, applied_principal_amount=25, unapplied_amount=-1",
            "state='confirmed', received_amount=25, applied_principal_amount=25, unapplied_amount=0, applied_card_fee_amount=1",
            "state='confirmed', received_amount=25, applied_principal_amount=25, unapplied_amount=0, applied_card_fee_tax_amount=1",
            "state='confirmed', received_amount=25, applied_principal_amount=20, unapplied_amount=0",
            "state='pending', received_amount=25, applied_principal_amount=25, unapplied_amount=0",
            "state='pending', received_amount=NULL, applied_principal_amount=0, unapplied_amount=0, processor_fee_amount=1",
            "state='failed', received_amount=1, applied_principal_amount=0, unapplied_amount=1",
            "state='expired', received_amount=NULL, applied_principal_amount=1, unapplied_amount=0",
            "state='confirmed', received_amount=NULL, applied_principal_amount=0, unapplied_amount=0",
            "state='reversed', received_amount=0, applied_principal_amount=0, unapplied_amount=0",
            "state='refunded', received_amount=25, applied_principal_amount=0, unapplied_amount=0",
            "state='confirmed', received_amount=25, applied_principal_amount=25, unapplied_amount=0, processor_fee_amount=-1",
        )
        for assignments in impossible_money_updates:
            with pytest.raises(DBAPIError):
                await _execute(
                    engine,
                    f"UPDATE invoice_payment_attempts SET {assignments} "
                    "WHERE id=:attempt_pending",
                    ids,
                )

        # The legacy-refund exception is intentionally narrow: it cannot hide
        # a provider amount mismatch or a non-zero processing projection.
        for assignments in (
            "state='refunded', received_amount=9, applied_principal_amount=0, unapplied_amount=0",
            "state='refunded', received_amount=10, applied_principal_amount=0, unapplied_amount=0, processor_fee_amount=1",
        ):
            with pytest.raises(DBAPIError):
                await _execute(
                    engine,
                    f"UPDATE invoice_payment_attempts SET {assignments} "
                    "WHERE id=:attempt_backfill_refunded",
                    ids,
                )

        # All supported state/money envelopes must survive the same PostgreSQL
        # constraints that reject the impossible matrix above.
        await _execute(
            engine,
            """
            INSERT INTO invoice_payment_attempts (
              id, tenant_id, invoice_id, settlement_id, customer_id,
              source, rail, provider, state, principal_amount,
              provider_charge_amount, currency,
              provider_configuration_version, actor_name_snapshot,
              subject_type, idempotency_key, request_hash
            ) VALUES
              (:attempt_failed, :tenant_a, :invoice_a, :settlement_a,
               :customer_a, 'staff', 'check', 'manual', 'failed', 10, 10,
               'USD', 1, 'DB048 owner', 'user', :failed_key, repeat('c', 64)),
              (:attempt_expired, :tenant_a, :invoice_a, :settlement_a,
               :customer_a, 'customer_portal', 'zelle', 'manual', 'expired',
               10, 10, 'USD', 1, 'DB048 customer', 'customer', :expired_key,
               repeat('d', 64));

            INSERT INTO invoice_payment_attempts (
              id, tenant_id, invoice_id, settlement_id, customer_id,
              source, rail, provider, state, principal_amount,
              provider_charge_amount, received_amount,
              applied_principal_amount, unapplied_amount, currency,
              provider_configuration_version, actor_name_snapshot,
              subject_type, idempotency_key, request_hash
            ) VALUES
              (:attempt_confirmed_manual, :tenant_a, :invoice_a, :settlement_a,
               :customer_a, 'staff', 'ach', 'manual', 'confirmed', 25, 25,
               25, 25, 0, 'USD', 1, 'DB048 owner', 'user', :manual_key,
               repeat('e', 64)),
              (:attempt_reversed, :tenant_a, :invoice_a, :settlement_a,
               :customer_a, 'staff', 'check', 'manual', 'reversed', 15, 15,
               15, 15, 0, 'USD', 1, 'DB048 owner', 'user', :reversed_key,
               repeat('f', 64));

            INSERT INTO invoice_payment_attempts (
              id, tenant_id, invoice_id, settlement_id, customer_id,
              source, rail, provider, state, principal_amount,
              card_fee_amount, card_fee_tax_amount, applied_card_fee_amount,
              applied_card_fee_tax_amount, provider_charge_amount,
              received_amount, applied_principal_amount, unapplied_amount,
              processor_fee_amount, currency, provider_configuration_version,
              provider_account_id, actor_name_snapshot, subject_type,
              idempotency_key, request_hash
            ) VALUES
              (:attempt_confirmed_card, :tenant_a, :invoice_a, :settlement_a,
               :customer_a, 'customer_portal', 'card', 'stripe_connect',
               'confirmed', 40, 1.20, 0.06, 1.20, 0.06, 41.26,
               40, 40, 0, 0.95, 'USD', 1, :account_a, 'DB048 customer',
               'customer', :card_key, repeat('1', 64)),
              (:attempt_overpayment, :tenant_a, :invoice_a, :settlement_a,
               :customer_a, 'customer_portal', 'card', 'stripe_connect',
               'confirmed', 100, 3, 0.15, 1.20, 0.06, 103.15,
               100, 40, 61.89, 0, 'USD', 1, :account_a, 'DB048 customer',
               'customer', :overpayment_key, repeat('2', 64));

            UPDATE invoice_payment_attempts
            SET state='refunded', received_amount=10,
                applied_principal_amount=0, unapplied_amount=0
            WHERE id=:attempt_backfill_refunded;
            """,
            {
                **ids,
                "failed_key": f"db048-failed-{suffix}",
                "expired_key": f"db048-expired-{suffix}",
                "manual_key": f"db048-manual-{suffix}",
                "reversed_key": f"db048-reversed-{suffix}",
                "card_key": f"db048-card-{suffix}",
                "overpayment_key": f"db048-over-{suffix}",
                "account_a": f"acct_db048_a_{suffix}",
            },
        )

        # Historical provider/accounting identity is frozen while operational
        # synchronization state remains mutable.
        with pytest.raises(DBAPIError, match="provider configuration frozen fields"):
            await _execute(
                engine,
                "UPDATE tenant_payment_provider_configurations "
                "SET qbo_realm_snapshot='realm-tampered' "
                "WHERE tenant_id=:tenant_a AND version=1",
                ids,
            )
        with pytest.raises(DBAPIError, match="lifecycle transition is invalid"):
            await _execute(
                engine,
                "UPDATE tenant_payment_provider_configurations SET is_active=false "
                "WHERE tenant_id=:tenant_a AND version=1",
                ids,
            )
        with pytest.raises(DBAPIError, match="provider configurations cannot be deleted"):
            await _execute(
                engine,
                "DELETE FROM tenant_payment_provider_configurations "
                "WHERE tenant_id=:tenant_a AND version=1",
                ids,
            )

        await _execute(
            engine,
            """
            INSERT INTO tenant_payment_provider_configurations (
              id, tenant_id, version, selected_provider, readiness_state,
              is_active, deactivated_at, actor_user_id, actor_name_snapshot,
              provider_account_snapshot, qbo_realm_snapshot, writer_strategy,
              idempotency_key, request_hash, stripe_clearing_account,
              processor_fee_expense_account, checking_account
            ) VALUES (
              gen_random_uuid(), :tenant_a, 3, 'stripe_connect', 'ready', false,
              now(), :user_a, 'DB048 Owner A', :account_a, 'realm-other',
              'dieselbridge', :config_v2_key, repeat('9', 64),
              'Stripe Clearing Other', 'Processor Fees Other', 'Checking Other'
            );
            """,
            {
                **ids,
                "account_a": f"acct_db048_a_{suffix}",
                "config_v2_key": f"db048-config-v2-{suffix}",
            },
        )
        with pytest.raises(DBAPIError, match="payment attempt accounting realm mismatch"):
            await _execute(
                engine,
                """
                INSERT INTO invoice_payment_attempts (
                  id, tenant_id, invoice_id, settlement_id, customer_id,
                  source, rail, provider, state, principal_amount,
                  provider_charge_amount, currency,
                  provider_configuration_version, actor_name_snapshot,
                  subject_type, idempotency_key, request_hash
                ) VALUES (
                  :attempt_realm_mismatch, :tenant_a, :invoice_a,
                  :settlement_a, :customer_a, 'staff', 'card',
                  'stripe_connect', 'pending', 10, 10, 'USD', 3,
                  'DB048 owner', 'user', :realm_attempt_key, repeat('8', 64)
                )
                """,
                {**ids, "realm_attempt_key": f"db048-realm-attempt-{suffix}"},
            )

        with pytest.raises(DBAPIError, match="accounting link tenant identity mismatch"):
            await _execute(
                engine,
                """
                INSERT INTO payment_accounting_links (
                  id, tenant_id, invoice_id, attempt_id, financial_object_type,
                  financial_object_id, operation_version, owning_writer,
                  account_mapping_snapshot, qbo_realm_snapshot, sync_state
                ) VALUES (
                  :link_realm_mismatch, :tenant_a, :invoice_a,
                  :attempt_confirmed_card, 'invoice_payment',
                  :attempt_confirmed_card, 2, 'dieselbridge', '{}',
                  'realm-other', 'pending'
                )
                """,
                ids,
            )

        await _execute(
            engine,
            """
            INSERT INTO payment_accounting_links (
              id, tenant_id, invoice_id, attempt_id, financial_object_type,
              financial_object_id, operation_version,
              principal_amount_snapshot, gross_amount_snapshot, owning_writer,
              account_mapping_snapshot, qbo_realm_snapshot, sync_state
            ) VALUES (
              :link_a, :tenant_a, :invoice_a, :attempt_confirmed_card,
              'invoice_payment', :attempt_confirmed_card, 1, 40, 41.26,
              'dieselbridge', jsonb_build_object(
                'stripe_clearing_account', 'Stripe Clearing A',
                'qbp_clearing_account', NULL,
                'check_deposit_account', NULL,
                'zelle_ach_account', NULL,
                'card_fee_income_account', NULL,
                'processor_fee_expense_account', 'Processor Fees A',
                'sales_tax_liability_account', NULL,
                'checking_account', 'Checking A'
              ), :realm_a, 'pending'
            );
            UPDATE payment_accounting_links
            SET sync_state='synced', provider_object_id='qbo-payment-1',
                synced_at=now()
            WHERE id=:link_a;
            """,
            {**ids, "realm_a": f"realm-db048-a-{suffix}"},
        )
        for mutation in (
            "SET principal_amount_snapshot=41",
            "SET qbo_realm_snapshot='realm-tampered'",
            "SET account_mapping_snapshot='{}'::jsonb",
            "SET deleted_at=now()",
        ):
            with pytest.raises(DBAPIError, match="accounting link frozen fields"):
                await _execute(
                    engine,
                    f"UPDATE payment_accounting_links {mutation} WHERE id=:link_a",
                    ids,
                )
        with pytest.raises(DBAPIError, match="accounting links cannot be deleted"):
            await _execute(
                engine,
                "DELETE FROM payment_accounting_links WHERE id=:link_a",
                ids,
            )

        await _execute(
            engine,
            """
            INSERT INTO provider_settlement_entries (
              id, tenant_id, batch_id, provider, provider_account_id,
              provider_entry_id, entry_type, amount, attempt_id,
              provider_configuration_version, qbo_realm_snapshot,
              owning_writer, account_mapping_snapshot, account_mapping_hash,
              occurred_at, safe_payload_hash
            ) VALUES (
              :entry_a, :tenant_a, :batch_a, 'stripe_connect', :account_a,
              :provider_entry, 'charge', 40, :attempt_confirmed_card, 1,
              :realm_a, 'dieselbridge', jsonb_build_object(
                'stripe_clearing_account', 'Stripe Clearing A',
                'qbp_clearing_account', NULL,
                'check_deposit_account', NULL,
                'zelle_ach_account', NULL,
                'card_fee_income_account', NULL,
                'processor_fee_expense_account', 'Processor Fees A',
                'sales_tax_liability_account', NULL,
                'checking_account', 'Checking A'
              ), repeat('c', 64), now(), repeat('d', 64)
            );
            """,
            {
                **ids,
                "account_a": f"acct_db048_a_{suffix}",
                "realm_a": f"realm-db048-a-{suffix}",
                "provider_entry": f"txn_db048_{suffix}",
            },
        )
        with pytest.raises(DBAPIError, match="append-only"):
            await _execute(
                engine,
                "UPDATE provider_settlement_entries SET amount=41 WHERE id=:entry_a",
                ids,
            )
        with pytest.raises(DBAPIError, match="append-only"):
            await _execute(
                engine,
                "DELETE FROM provider_settlement_entries WHERE id=:entry_a",
                ids,
            )

        async with engine.connect() as connection:
            result = (
                await connection.execute(
                    text(
                        """
                        SELECT
                          (SELECT count(*) FROM invoice_payment_ledger_events
                           WHERE id=:ledger_a) AS ledger_rows,
                          (SELECT count(*) FROM invoice_settlements
                           WHERE id=:settlement_invalid) AS cross_tenant_rows,
                          (SELECT count(*) FROM provider_settlement_batches
                           WHERE id=:batch_a) AS empty_batch_rows,
                          (SELECT count(*) FROM provider_settlement_entries
                           WHERE batch_id=:batch_a) AS empty_batch_entries,
                          (SELECT count(*) FROM invoice_payment_attempts
                           WHERE id IN (
                             :attempt_pending, :attempt_failed,
                             :attempt_expired, :attempt_confirmed_manual,
                             :attempt_confirmed_card, :attempt_overpayment,
                             :attempt_reversed, :attempt_backfill_refunded
                           )) AS valid_shape_rows,
                          (SELECT count(*) FROM invoice_payment_attempts
                           WHERE id=:attempt_pending AND state='pending'
                             AND received_amount IS NULL
                             AND applied_principal_amount=0
                             AND unapplied_amount=0) AS pending_unchanged,
                          (SELECT count(*) FROM invoice_payment_attempts
                           WHERE id=:attempt_backfill_refunded
                             AND source='backfill' AND state='refunded'
                             AND received_amount=provider_charge_amount
                             AND applied_principal_amount=0
                             AND unapplied_amount=0) AS narrow_refund_rows
                        """
                    ),
                    ids,
                )
            ).one()
        assert result.ledger_rows == 1
        assert result.cross_tenant_rows == 0
        assert result.empty_batch_rows == 1
        assert result.empty_batch_entries == 1
        assert result.valid_shape_rows == 8
        assert result.pending_unchanged == 1
        assert result.narrow_refund_rows == 1
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_db048_postgres_reciprocal_payment_links_are_atomic_and_frozen():
    engine = create_async_engine(os.environ[POSTGRES_URL])
    ids = _ids()
    suffix = uuid4().hex
    try:
        await _seed_financial_identity(engine, ids, suffix)
        await _execute(
            engine,
            """
            INSERT INTO invoice_payment_attempts (
              id, tenant_id, invoice_id, settlement_id, customer_id,
              source, rail, provider, state, principal_amount,
              provider_charge_amount, received_amount,
              applied_principal_amount, unapplied_amount, currency,
              provider_configuration_version, actor_name_snapshot,
              subject_type, idempotency_key, request_hash
            ) VALUES (
              :attempt_one_sided, :tenant_a, :invoice_a, :settlement_a,
              :customer_a, 'staff', 'check', 'manual', 'confirmed', 25, 25,
              25, 25, 0, 'USD', 1, 'DB048 owner', 'user', :one_sided_key,
              repeat('3', 64)
            );
            """,
            {**ids, "one_sided_key": f"db048-one-sided-{suffix}"},
        )

        # Neither direction may commit a half-link.
        with pytest.raises(DBAPIError, match="link is not reciprocal"):
            await _execute(
                engine,
                """
                INSERT INTO payments (
                  id, tenant_id, invoice_id, payment_number, amount, method,
                  status, invoice_payment_attempt_id
                ) VALUES (
                  :payment_one_sided, :tenant_a, :invoice_a,
                  :one_sided_number, 25, 'check', 'completed',
                  :attempt_one_sided
                )
                """,
                {**ids, "one_sided_number": f"DB048-ONE-{suffix}"},
            )
        with pytest.raises(DBAPIError, match="link is not reciprocal"):
            await _execute(
                engine,
                """
                INSERT INTO payments (
                  id, tenant_id, invoice_id, payment_number, amount, method,
                  status
                ) VALUES (
                  :payment_one_sided_reverse, :tenant_a, :invoice_a,
                  :reverse_number, 9, 'check', 'completed'
                );
                INSERT INTO invoice_payment_attempts (
                  id, tenant_id, invoice_id, settlement_id, customer_id,
                  payment_id, source, rail, provider, state, principal_amount,
                  provider_charge_amount, received_amount,
                  applied_principal_amount, unapplied_amount, currency,
                  provider_configuration_version, actor_name_snapshot,
                  subject_type, idempotency_key, request_hash
                ) VALUES (
                  :attempt_one_sided_reverse, :tenant_a, :invoice_a,
                  :settlement_a, :customer_a, :payment_one_sided_reverse,
                  'backfill', 'check', 'manual', 'confirmed', 9, 9, 9, 9, 0,
                  'USD', 1, 'Legacy payment', 'backfill', :reverse_key,
                  repeat('4', 64)
                )
                """,
                {
                    **ids,
                    "reverse_number": f"DB048-REVERSE-{suffix}",
                    "reverse_key": f"db048-reverse-{suffix}",
                },
            )

        # Live confirmation writes attempt -> payment -> reciprocal attempt
        # link; the legacy backfill writes payment -> attempt -> reciprocal
        # payment link. Deferred triggers permit both atomic orders.
        await _execute(
            engine,
            """
            INSERT INTO invoice_payment_attempts (
              id, tenant_id, invoice_id, settlement_id, customer_id,
              source, rail, provider, state, principal_amount,
              provider_charge_amount, received_amount,
              applied_principal_amount, unapplied_amount, currency,
              provider_configuration_version, actor_name_snapshot,
              subject_type, idempotency_key, request_hash
            ) VALUES (
              :attempt_live, :tenant_a, :invoice_a, :settlement_a,
              :customer_a, 'staff', 'ach', 'manual', 'confirmed', 20, 20,
              20, 20, 0, 'USD', 1, 'DB048 owner', 'user', :live_key,
              repeat('5', 64)
            );
            INSERT INTO payments (
              id, tenant_id, invoice_id, payment_number, amount, method,
              status, invoice_payment_attempt_id
            ) VALUES (
              :payment_live, :tenant_a, :invoice_a, :live_number,
              20, 'ach', 'completed', :attempt_live
            );
            UPDATE invoice_payment_attempts SET payment_id=:payment_live
            WHERE id=:attempt_live;

            INSERT INTO payments (
              id, tenant_id, invoice_id, payment_number, amount, method, status
            ) VALUES (
              :payment_backfill, :tenant_a, :invoice_a, :backfill_number,
              10, 'check', 'completed'
            );
            INSERT INTO invoice_payment_attempts (
              id, tenant_id, invoice_id, settlement_id, customer_id, payment_id,
              source, rail, provider, state, principal_amount,
              provider_charge_amount, received_amount,
              applied_principal_amount, unapplied_amount, currency,
              provider_configuration_version, actor_name_snapshot,
              subject_type, idempotency_key, request_hash
            ) VALUES (
              :attempt_backfill, :tenant_a, :invoice_a, :settlement_a,
              :customer_a, :payment_backfill, 'backfill', 'check', 'manual',
              'confirmed', 10, 10, 10, 10, 0, 'USD', 1, 'Legacy payment',
              'backfill', :backfill_key, repeat('6', 64)
            );
            UPDATE payments SET invoice_payment_attempt_id=:attempt_backfill
            WHERE id=:payment_backfill;
            """,
            {
                **ids,
                "live_key": f"db048-live-{suffix}",
                "live_number": f"DB048-LIVE-{suffix}",
                "backfill_key": f"db048-backfill-{suffix}",
                "backfill_number": f"DB048-BACKFILL-{suffix}",
            },
        )

        # Same-tenant cross-invoice and cross-tenant pairs fail atomically.
        with pytest.raises(DBAPIError, match="tenant identity mismatch"):
            await _execute(
                engine,
                """
                INSERT INTO payments (
                  id, tenant_id, invoice_id, payment_number, amount, method,
                  status
                ) VALUES (
                  :payment_cross_invoice, :tenant_a, :invoice_a2,
                  :cross_invoice_number, 8, 'check', 'completed'
                );
                INSERT INTO invoice_payment_attempts (
                  id, tenant_id, invoice_id, settlement_id, customer_id,
                  payment_id, source, rail, provider, state, principal_amount,
                  provider_charge_amount, received_amount,
                  applied_principal_amount, unapplied_amount, currency,
                  provider_configuration_version, actor_name_snapshot,
                  subject_type, idempotency_key, request_hash
                ) VALUES (
                  :attempt_cross_invoice, :tenant_a, :invoice_a,
                  :settlement_a, :customer_a, :payment_cross_invoice,
                  'backfill', 'check', 'manual', 'confirmed', 8, 8, 8, 8, 0,
                  'USD', 1, 'Legacy payment', 'backfill', :cross_invoice_key,
                  repeat('7', 64)
                )
                """,
                {
                    **ids,
                    "cross_invoice_number": f"DB048-CROSS-INV-{suffix}",
                    "cross_invoice_key": f"db048-cross-inv-{suffix}",
                },
            )
        with pytest.raises(DBAPIError, match="tenant identity mismatch"):
            await _execute(
                engine,
                """
                INSERT INTO payments (
                  id, tenant_id, invoice_id, payment_number, amount, method,
                  status
                ) VALUES (
                  :payment_cross_tenant, :tenant_b, :invoice_b,
                  :cross_tenant_number, 7, 'check', 'completed'
                );
                INSERT INTO invoice_payment_attempts (
                  id, tenant_id, invoice_id, settlement_id, customer_id,
                  payment_id, source, rail, provider, state, principal_amount,
                  provider_charge_amount, received_amount,
                  applied_principal_amount, unapplied_amount, currency,
                  provider_configuration_version, actor_name_snapshot,
                  subject_type, idempotency_key, request_hash
                ) VALUES (
                  :attempt_cross_tenant, :tenant_a, :invoice_a,
                  :settlement_a, :customer_a, :payment_cross_tenant,
                  'backfill', 'check', 'manual', 'confirmed', 7, 7, 7, 7, 0,
                  'USD', 1, 'Legacy payment', 'backfill', :cross_tenant_key,
                  repeat('8', 64)
                )
                """,
                {
                    **ids,
                    # payments.payment_number is varchar(50); keep this
                    # negative-case fixture focused on tenant identity.
                    "cross_tenant_number": f"DB048-XTEN-{suffix}",
                    "cross_tenant_key": f"db048-cross-tenant-{suffix}",
                },
            )

        # Once a reciprocal pair exists, neither side may remove or replace
        # its link. Each failed transaction must leave both valid pairs intact.
        for sql, expected_error in (
            (
                "UPDATE payments SET invoice_payment_attempt_id=NULL "
                "WHERE id=:payment_live",
                "cannot be replaced or removed",
            ),
            (
                "UPDATE payments SET invoice_payment_attempt_id=:attempt_one_sided "
                "WHERE id=:payment_live",
                "cannot be replaced or removed",
            ),
            (
                "UPDATE invoice_payment_attempts SET payment_id=NULL "
                "WHERE id=:attempt_live",
                "authoritative payment snapshots cannot be replaced",
            ),
            (
                "UPDATE invoice_payment_attempts SET payment_id=:payment_backfill "
                "WHERE id=:attempt_live",
                "authoritative payment snapshots cannot be replaced",
            ),
        ):
            with pytest.raises(DBAPIError, match=expected_error):
                await _execute(engine, sql, ids)

        async with engine.connect() as connection:
            result = (
                await connection.execute(
                    text(
                        """
                        SELECT
                          (SELECT count(*) FROM payments
                           WHERE id IN (
                             :payment_one_sided,
                             :payment_one_sided_reverse,
                             :payment_cross_invoice,
                             :payment_cross_tenant
                           )) AS failed_payment_rows,
                          (SELECT count(*) FROM invoice_payment_attempts
                           WHERE id IN (
                             :attempt_one_sided_reverse,
                             :attempt_cross_invoice,
                             :attempt_cross_tenant
                           )) AS failed_attempt_rows,
                          (SELECT count(*) FROM payments p
                           JOIN invoice_payment_attempts a
                             ON a.id=p.invoice_payment_attempt_id
                            AND p.id=a.payment_id
                            AND p.tenant_id=a.tenant_id
                            AND p.invoice_id=a.invoice_id
                           WHERE (p.id=:payment_live AND a.id=:attempt_live)
                              OR (p.id=:payment_backfill
                                  AND a.id=:attempt_backfill)) AS intact_pairs,
                          (SELECT count(*) FROM invoice_payment_attempts
                           WHERE id=:attempt_one_sided
                             AND payment_id IS NULL) AS unlinked_control_rows
                        """
                    ),
                    ids,
                )
            ).one()
        assert result.failed_payment_rows == 0
        assert result.failed_attempt_rows == 0
        assert result.intact_pairs == 2
        assert result.unlinked_control_rows == 1
    finally:
        await engine.dispose()
