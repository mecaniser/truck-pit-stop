"""Synthetic private-schema PostgreSQL rehearsal; never touches application tables."""
import asyncio
from contextlib import asynccontextmanager
import importlib.util
import os
from pathlib import Path
from uuid import uuid4

from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool


async def main():
    dsn = os.environ['DB094_TEST_POSTGRES_DSN']
    from sqlalchemy.engine import make_url
    assert make_url(dsn).host in {'localhost', '127.0.0.1', '::1'}
    engine = create_async_engine(dsn, poolclass=NullPool)
    schema = 'db094_identity_rehearsal_' + uuid4().hex
    tenant, target, other, evidence, uploader, reviewer = [str(uuid4()) for _ in range(6)]
    spec = importlib.util.spec_from_file_location('migration195', Path(__file__).parents[1] / 'alembic/versions/195_historical_identity_proof.py')
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)

    @asynccontextmanager
    async def connection():
        async with engine.connect() as conn:
            await conn.execute(text(f'SET search_path TO {schema}'))
            await conn.commit()
            yield conn

    def migrate(conn, direction):
        with Operations.context(MigrationContext.configure(conn)):
            getattr(migration, direction)()

    async def rejected(sql):
        async with connection() as conn:
            try:
                await conn.execute(text(sql))
                await conn.commit()
            except Exception:
                await conn.rollback()
                return
            raise AssertionError('unsafe mutation accepted')

    async def unique(conn):
        await conn.execute(text('SELECT pg_advisory_xact_lock(hashtextextended(:tenant,94094))'), {'tenant': tenant})
        return (await conn.execute(text("SELECT count(*) FROM customers WHERE tenant_id=:t AND deleted_at IS NULL AND lower(btrim(email))='target@example.com'"), {'t': tenant})).scalar_one() == 1

    mapping_sql = f"INSERT INTO historical_invoice_mappings VALUES ('{uuid4()}','{tenant}','{target}','{evidence}')"
    try:
        async with engine.begin() as conn:
            await conn.execute(text(f'CREATE SCHEMA {schema}'))
        async with connection() as conn:
            for statement in [
                'CREATE TABLE customers (id uuid PRIMARY KEY,tenant_id uuid,email text,first_name text,last_name text,company_name text,deleted_at timestamptz)',
                'CREATE TABLE historical_invoice_evidence (id uuid PRIMARY KEY,tenant_id uuid,recorded_by_user_id uuid,source_document bytea,verified_at timestamptz,verified_by_user_id uuid,verified_target_customer_id uuid,verified_target_legal_name text,verification_note text,updated_at timestamptz)',
                'CREATE TABLE historical_invoice_decisions (id uuid PRIMARY KEY,note text)',
                'CREATE TABLE historical_invoice_mappings (id uuid PRIMARY KEY,tenant_id uuid,target_customer_id uuid,evidence_id uuid)',
                'CREATE FUNCTION guard_historical_invoice_customer_identity() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RETURN NEW; END $$',
                'CREATE TRIGGER tr_guard_historical_invoice_customer_identity BEFORE UPDATE ON customers FOR EACH ROW EXECUTE FUNCTION guard_historical_invoice_customer_identity()',
                f"INSERT INTO customers VALUES ('{target}','{tenant}','target@example.com','Synthetic','Target',NULL,NULL),('{other}','{tenant}','other@example.com','Synthetic','Other',NULL,NULL)",
            ]:
                await conn.execute(text(statement))
            await conn.run_sync(migrate, 'upgrade')
            await conn.run_sync(migrate, 'downgrade')
            await conn.run_sync(migrate, 'upgrade')
            await conn.commit()
        print('PASS actual asyncpg migration upgrade/downgrade/upgrade with legacy rows')
        async with connection() as conn:
            await conn.execute(text(f"INSERT INTO historical_invoice_evidence(id,tenant_id,recorded_by_user_id,source_document) VALUES ('{evidence}','{tenant}','{uploader}',decode('01','hex'))"))
            await conn.commit()
        await rejected("UPDATE historical_invoice_evidence SET source_document=decode('02','hex')")
        await rejected(f"UPDATE historical_invoice_evidence SET verified_at=now(),verified_by_user_id='{uploader}',verified_target_customer_id='{target}'")
        async with connection() as conn:
            await conn.execute(text(f"UPDATE historical_invoice_evidence SET verified_at=now(),verified_by_user_id='{reviewer}',verified_target_customer_id='{target}',identity_proof='synthetic',identity_proof_sha256=repeat('a',64)"))
            await conn.execute(text(f"INSERT INTO historical_invoice_decisions VALUES ('{uuid4()}','synthetic',repeat('a',64))"))
            await conn.commit()
        await rejected("UPDATE historical_invoice_evidence SET verification_note='rewrite'")
        await rejected('DELETE FROM historical_invoice_evidence')
        await rejected("UPDATE historical_invoice_decisions SET note='rewrite'")
        await rejected('DELETE FROM historical_invoice_decisions')
        async with connection() as conn:
            try:
                await conn.run_sync(migrate, 'downgrade')
            except Exception:
                await conn.rollback()
            else:
                raise AssertionError('proof downgrade accepted')
        print('PASS source/verified evidence immutability, independent verifier, append-only decisions, downgrade fence')

        # Competing edit wins: approval waits, then sees ambiguity and must deny.
        async with connection() as edit, connection() as approval:
            await edit.execute(text(f"UPDATE customers SET email='target@example.com' WHERE id='{other}'"))
            pending = asyncio.create_task(unique(approval))
            await asyncio.sleep(.15)
            assert not pending.done(), 'approval did not serialize with customer edit'
            await edit.commit()
            assert not await asyncio.wait_for(pending, 5)
            await approval.rollback()
        async with connection() as conn:
            await conn.execute(text(f"UPDATE customers SET email='other@example.com' WHERE id='{other}'"))
            await conn.commit()
        # Approval wins: later shared contact cannot move UUID-pinned mapping.
        async with connection() as approval, connection() as edit:
            assert await unique(approval)
            await approval.execute(text(mapping_sql))
            pending = asyncio.create_task(edit.execute(text(f"UPDATE customers SET email='target@example.com' WHERE id='{other}'")))
            await asyncio.sleep(.15)
            assert not pending.done(), 'customer edit did not serialize with approval'
            await approval.commit()
            await asyncio.wait_for(pending, 5)
            await edit.commit()
        async with connection() as conn:
            assert (await conn.execute(text('SELECT target_customer_id::text FROM historical_invoice_mappings'))).scalar_one() == target
            assert not await unique(conn)
            await conn.rollback()
        print('PASS both concurrency orders; future ambiguous approval denies, existing grant stays UUID-pinned')
        await rejected(f"UPDATE customers SET email='changed@example.com' WHERE id='{target}'")
        await rejected(f"UPDATE customers SET deleted_at=now() WHERE id='{target}'")
        await rejected(f"UPDATE customers SET tenant_id='{uuid4()}' WHERE id='{target}'")
        await rejected(f"DELETE FROM customers WHERE id='{target}'")
        # Advisory-serialized synthetic removal: tests trigger ordering, not the revoke route.
        # The actual route may require retrying an edit after committed revocation.
        async with connection() as revoke, connection() as edit:
            assert not await unique(revoke)
            await revoke.execute(text('DELETE FROM historical_invoice_mappings'))
            pending = asyncio.create_task(edit.execute(text(f"UPDATE customers SET email='changed@example.com' WHERE id='{target}'")))
            await asyncio.sleep(.15)
            assert not pending.done()
            await revoke.commit()
            await asyncio.wait_for(pending, 5)
            await edit.commit()
        print('PASS mapped target guards; advisory-serialized synthetic removal/edit trigger ordering')
    finally:
        async with engine.begin() as conn:
            await conn.execute(text(f'DROP SCHEMA IF EXISTS {schema} CASCADE'))
        await engine.dispose()
        print('CLEANUP private synthetic schema removed')


if __name__ == '__main__':
    asyncio.run(main())
