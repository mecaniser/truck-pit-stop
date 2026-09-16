"""Transaction-level serialization for a shop's financial aggregate.

Call before financial row locks or writes. Credits and provider reversals span
invoices, so the aggregate is the tenant, not a single invoice. Try-locking never
waits behind another transaction while the caller holds unrelated lifecycle rows.
SQLite is supported only for single-process tests; concurrency acceptance uses PG.
"""
from __future__ import annotations

import hashlib
from uuid import UUID

from sqlalchemy import inspect, text
from sqlalchemy.ext.asyncio import AsyncSession


def financial_lock_key(tenant_id: UUID) -> int:
    digest = hashlib.sha256(f"dieselbridge:financial:v1:{tenant_id}".encode()).digest()
    return int.from_bytes(digest[:8], "big", signed=True)


async def lock_tenant_financials(db: AsyncSession, tenant_id: UUID) -> None:
    """Acquire or raise retryable invoice_busy; ownership ends at transaction end.

    Reentrant calls are inexpensive. Keep the transaction object (not a boolean)
    so commit/rollback always requires a new database acquisition. Refresh clean
    financial identities on first acquisition to discard pre-lock discovery data.
    """
    if not isinstance(db, AsyncSession) or db.get_bind().dialect.name != "postgresql":
        return
    from app.services.invoice_settlement_service import SettlementDomainError

    # Suppress autoflush: discovery may have loaded an ORM object before entering
    # this boundary, and no queued write may precede the aggregate lock.
    with db.no_autoflush:
        transaction = (db.sync_session.get_nested_transaction() or db.sync_session.get_transaction())
        held = db.info.get("financial_transaction_locks")
        if held and held[0] is transaction and tenant_id in held[1]:
            return
        acquired = await db.scalar(
            text("SELECT pg_try_advisory_xact_lock(:financial_key)"),
            {"financial_key": financial_lock_key(tenant_id)},
        )
        if not acquired:
            raise SettlementDomainError(
                "invoice_busy", "Payment processing is in progress. Refresh and retry.",
                retryable=True,
            )
        transaction = (db.sync_session.get_nested_transaction() or db.sync_session.get_transaction())
        keys = held[1] if held and held[0] is transaction else set()
        keys.add(tenant_id)
        db.info["financial_transaction_locks"] = (transaction, keys)
        for obj in list(db.identity_map.values()):
            state = inspect(obj)
            # Preserve new/local edits and relationship loading. Only refresh
            # persisted columns; the caller still enforces lifecycle and access.
            if state.persistent and not state.modified and state.dict.get("tenant_id") == tenant_id:
                if state.mapper.local_table.name in {
                    "invoices", "repair_orders", "payments", "invoice_settlements",
                    "invoice_payment_attempts", "payment_refunds", "payment_overpayments",
                    "customer_credit_entries", "payment_accounting_links", "provider_outbox", "payment_provider_disputes", "provider_settlement_batches",
                    "tenant_payment_provider_configurations", "quickbooks_connections",
                }:
                    await db.refresh(obj, attribute_names=[p.key for p in state.mapper.column_attrs])


async def lock_tenants_financials(db: AsyncSession, tenant_ids) -> None:
    """Batch callers discover keys without row locks, then acquire all or abort."""
    for tenant_id in sorted(set(tenant_ids), key=str):
        await lock_tenant_financials(db, tenant_id)


async def lock_financial_query_tenants(db: AsyncSession, tenant_query) -> None:
    """Resolve immutable tenant identities before taking any financial row lock."""
    if not isinstance(db, AsyncSession) or db.get_bind().dialect.name != "postgresql":
        return
    with db.no_autoflush:
        tenant_ids = (await db.scalars(tenant_query)).all()
        await lock_tenants_financials(db, tenant_ids)
