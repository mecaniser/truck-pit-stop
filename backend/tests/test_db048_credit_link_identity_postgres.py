"""Real PostgreSQL protection for cross-invoice customer credit provenance."""
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.exc import DBAPIError

from app.db.models.invoice_settlement import PaymentAccountingLink
from app.services import invoice_settlement_service as svc
from tests.test_db048_native_payment_races import database, make, confirm, consent, pytestmark
from tests.test_db048_cash import context
from tests.test_db048_invoice_settlements import _add_eligible_invoice


@pytest.mark.asyncio
async def test_cross_invoice_credit_link_requires_exact_origin_and_target(monkeypatch):
    engine, sessions = database()
    try:
        async with sessions() as db:
            ctx = await context(db, monkeypatch)
            foreign = await context(db, monkeypatch)
            attempt = (await make(db, ctx)).attempt
            paid = await confirm(db, ctx, attempt.id, Decimal('110'))
            credit = await consent(db, ctx, paid.overpayment.id)
            target = await _add_eligible_invoice(db, tenant=ctx[0], customer=ctx[2], reference_invoice=ctx[3], with_shadow_settlement=True)
            wrong_target = await _add_eligible_invoice(db, tenant=ctx[0], customer=ctx[2], reference_invoice=ctx[3], with_shadow_settlement=True)
            foreign_attempt = (await make(db, foreign)).attempt
            application, _ = await svc.apply_customer_credit(db, credit_id=credit.id, invoice=target,
                tenant=ctx[0], customer_id=ctx[2].id, amount=Decimal('10'), expected_settlement_version=1,
                actor=ctx[1], idempotency_key='valid-application')
            await db.flush()
            link = await db.scalar(select(PaymentAccountingLink).where(
                PaymentAccountingLink.financial_object_type == 'customer_credit_application',
                PaymentAccountingLink.financial_object_id == application.id))
            assert link.invoice_id == target.id and link.attempt_id == attempt.id
            values = {col.name: getattr(link, col.name) for col in PaymentAccountingLink.__table__.columns
                if col.name not in {'id', 'created_at', 'updated_at', 'deleted_at'}}
            # A replay/version of the same proven chain remains legitimate.
            db.add(PaymentAccountingLink(**{**values, 'operation_version': 2}))
            await db.flush()
            negatives = [
                {'financial_object_type': 'invoice_payment'},
                {'financial_object_id': uuid4()},
                {'financial_object_id': credit.id},  # issued is not applied
                {'invoice_id': wrong_target.id},
                {'attempt_id': foreign_attempt.id},
                {'tenant_id': foreign[0].id},
                {'qbo_realm_snapshot': 'unrelated-realm'},
            ]
            for change in negatives:
                with pytest.raises(DBAPIError, match='accounting link tenant identity mismatch'):
                    async with db.begin_nested():
                        db.add(PaymentAccountingLink(**{**values, 'operation_version': 3, **change}))
                        await db.flush()
            await db.rollback()
    finally:
        await engine.dispose()
