"""Localhost-only private PostgreSQL schema; never changes application tables."""
import asyncio
from contextlib import asynccontextmanager
import importlib.util
import os
from pathlib import Path
from uuid import uuid4

from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool


def load(number, name):
    path = Path(__file__).parents[1] / f'alembic/versions/{number}_{name}.py'
    spec = importlib.util.spec_from_file_location(f'migration{number}', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


async def main():
    dsn = os.environ['DB094_TEST_POSTGRES_DSN']
    assert make_url(dsn).host in {'localhost', '127.0.0.1', '::1'}
    engine = create_async_engine(dsn, poolclass=NullPool)
    schema = 'db094_owner_review_' + uuid4().hex
    tenant, other_tenant, owner, admin, inactive, outsider, target = [str(uuid4()) for _ in range(7)]
    old, new = load(195, 'historical_identity_proof'), load(196, 'historical_owner_self_review')

    @asynccontextmanager
    async def connection():
        async with engine.connect() as conn:
            await conn.execute(text(f'SET search_path TO {schema}'))
            yield conn

    def migrate(conn, module, direction):
        with Operations.context(MigrationContext.configure(conn)):
            getattr(module, direction)()

    async def rejects(statement, params=None):
        async with connection() as conn:
            try:
                await conn.execute(text(statement), params or {})
                await conn.commit()
            except DBAPIError as error:
                assert getattr(error.orig, 'sqlstate', None) == 'P0001', error
                await conn.rollback()
            else:
                raise AssertionError('Unsafe mutation accepted: ' + statement[:90])

    async def source(actor=owner):
        key = str(uuid4())
        async with connection() as conn:
            await conn.execute(text('INSERT INTO historical_invoice_evidence(id,tenant_id,recorded_by_user_id,source_document) VALUES (:id,:tenant,:actor,decode(\'01\',\'hex\'))'), {'id': key, 'tenant': tenant, 'actor': actor})
            await conn.commit()
        return key

    def verification(key, actor, mode):
        return ("UPDATE historical_invoice_evidence SET verified_at=now(),verified_by_user_id=:actor,verified_target_customer_id=:target,verification_mode=:mode WHERE id=:id",
                {'id': key, 'actor': actor, 'target': target, 'mode': mode})

    try:
        async with engine.begin() as conn:
            await conn.execute(text(f'CREATE SCHEMA {schema}'))
        async with connection() as conn:
            for statement in [
                'CREATE TABLE users(id uuid PRIMARY KEY,tenant_id uuid,role text NOT NULL,is_active boolean NOT NULL,deleted_at timestamptz)',
                'CREATE TABLE customers(id uuid PRIMARY KEY,tenant_id uuid,email text,first_name text,last_name text,company_name text,deleted_at timestamptz)',
                'CREATE TABLE historical_invoice_evidence(id uuid PRIMARY KEY,tenant_id uuid,recorded_by_user_id uuid,source_document bytea,verified_at timestamptz,verified_by_user_id uuid,verified_target_customer_id uuid,verified_target_legal_name text,verification_note text,updated_at timestamptz)',
                'CREATE TABLE historical_invoice_decisions(id uuid PRIMARY KEY,note text)',
                'CREATE TABLE historical_invoice_mappings(id uuid PRIMARY KEY,tenant_id uuid,target_customer_id uuid,evidence_id uuid)',
                'CREATE FUNCTION guard_historical_invoice_customer_identity() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RETURN NEW; END $$',
                'CREATE TRIGGER tr_guard_historical_invoice_customer_identity BEFORE UPDATE ON customers FOR EACH ROW EXECUTE FUNCTION guard_historical_invoice_customer_identity()',
            ]:
                await conn.execute(text(statement))
            for user, scope, role, active in [(owner,tenant,'garage_owner',True),(admin,tenant,'garage_admin',True),(inactive,tenant,'garage_owner',False),(outsider,other_tenant,'garage_owner',True)]:
                await conn.execute(text('INSERT INTO users VALUES(:id,:scope,:role,:active,NULL)'), dict(id=user,scope=scope,role=role,active=active))
            await conn.run_sync(migrate, old, 'upgrade')
            await conn.commit()
        legacy = await source()
        async with connection() as conn:
            await conn.execute(text('UPDATE historical_invoice_evidence SET verified_at=now(),verified_by_user_id=:reviewer,verified_target_customer_id=:target WHERE id=:id'),dict(reviewer=admin,target=target,id=legacy))
            await conn.run_sync(migrate,new,'upgrade')
            assert (await conn.execute(text('SELECT verification_mode FROM historical_invoice_evidence WHERE id=:id'),dict(id=legacy))).scalar_one() is None
            await conn.run_sync(migrate,new,'downgrade')
            await conn.run_sync(migrate,new,'upgrade')
            await conn.commit()
        print('PASS populated195 ->196 ->195 ->196; legacy independent evidence untouched')
        for actor, mode, uploader in [(owner,'independent',owner),(admin,'owner_self_review',admin),(inactive,'owner_self_review',inactive),(outsider,'owner_self_review',outsider),(owner,'owner_self_review',admin),(owner,None,owner)]:
            key=await source(uploader)
            statement,params=verification(key,actor,mode)
            await rejects(statement,params)
        await rejects('INSERT INTO historical_invoice_evidence(id,tenant_id,recorded_by_user_id,verified_at,verification_mode) VALUES(:id,:tenant,:actor,now(),\'owner_self_review\')',dict(id=str(uuid4()),tenant=tenant,actor=owner))
        fresh=await source()
        await rejects("UPDATE historical_invoice_evidence SET source_document=decode('02','hex') WHERE id=:id",dict(id=fresh))
        await rejects("UPDATE historical_invoice_evidence SET verification_mode='owner_self_review' WHERE id=:id",dict(id=fresh))
        async with connection() as conn:
            statement,params=verification(fresh,owner,'owner_self_review')
            await conn.execute(text(statement),params)
            await conn.execute(text("INSERT INTO historical_invoice_decisions VALUES(:id,'owner self-review',NULL,'owner_self_review')"),dict(id=str(uuid4())))
            await conn.commit()
        for statement in ["UPDATE historical_invoice_evidence SET verification_mode='independent' WHERE id=:id", "UPDATE historical_invoice_evidence SET verification_note='rewrite' WHERE id=:id", "DELETE FROM historical_invoice_evidence WHERE id=:id"]:
            await rejects(statement,dict(id=fresh))
        await rejects("UPDATE historical_invoice_decisions SET evidence_verification_mode='independent'")
        await rejects('DELETE FROM historical_invoice_decisions')
        print('PASS owner-only mode, independent separation, insertion/role/tenant/active denials, immutable evidence/decisions')

        # Role edit first: verification waits for the row lock, then rejects demoted owner.
        race=await source()
        async with connection() as edit, connection() as review:
            await edit.execute(text("UPDATE users SET role='garage_admin' WHERE id=:id"),dict(id=owner))
            statement,params=verification(race,owner,'owner_self_review')
            pending=asyncio.create_task(review.execute(text(statement),params))
            await asyncio.sleep(.15);assert not pending.done()
            await edit.commit()
            try: await asyncio.wait_for(pending,5)
            except DBAPIError as error:
                assert getattr(error.orig, 'sqlstate', None) == 'P0001', error
                assert 'owner self-review requires the shop owner uploader' in str(error)
                await review.rollback()
            else: raise AssertionError('Demoted owner review accepted')
        async with connection() as conn:
            await conn.execute(text("UPDATE users SET role='garage_owner' WHERE id=:id"),dict(id=owner));await conn.commit()
        # Verification first: role edit waits; historical owner mode remains frozen afterward.
        race=await source()
        async with connection() as review, connection() as edit:
            statement,params=verification(race,owner,'owner_self_review')
            await review.execute(text(statement),params)
            pending=asyncio.create_task(edit.execute(text("UPDATE users SET role='garage_admin' WHERE id=:id"),dict(id=owner)))
            await asyncio.sleep(.15);assert not pending.done()
            await review.commit();await asyncio.wait_for(pending,5);await edit.commit()
        async with connection() as conn:
            assert (await conn.execute(text('SELECT verification_mode FROM historical_invoice_evidence WHERE id=:id'),dict(id=race))).scalar_one()=='owner_self_review'
            try: await conn.run_sync(migrate,new,'downgrade')
            except DBAPIError as error:
                assert getattr(error.orig, 'sqlstate', None) == 'P0001', error
                assert 'preserve verification mode audit' in str(error)
                await conn.rollback()
            else: raise AssertionError('Audit-erasing downgrade accepted')
        print('PASS both reviewer-role concurrency orders; mode stays historical; audit-erasing downgrade denied')
    finally:
        async with engine.begin() as conn:
            await conn.execute(text(f'DROP SCHEMA IF EXISTS {schema} CASCADE'))
        await engine.dispose()
        print('CLEANUP private synthetic schema removed')


if __name__ == '__main__':
    asyncio.run(main())
