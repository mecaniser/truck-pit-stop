"""Transaction-only rehearsal against an isolated schema on local development PG."""
import asyncio
import importlib.util
from pathlib import Path
from uuid import uuid4
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from alembic.migration import MigrationContext
from alembic.operations import Operations

root = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('equipment_migration', root / 'backend/alembic/versions/193_vehicle_equipment_type.py')
migration = importlib.util.module_from_spec(spec)
spec.loader.exec_module(migration)

async def main():
    engine = create_async_engine('postgresql+asyncpg://dieselbridge:dieselbridge_dev@127.0.0.1:5432/truckpitstop')
    schema = 'db148_rehearsal_' + uuid4().hex
    async with engine.connect() as conn:
        transaction = await conn.begin()
        try:
            await conn.execute(text(f'CREATE SCHEMA {schema}'))
            await conn.execute(text(f'SET LOCAL search_path TO {schema}'))
            await conn.execute(text('CREATE TABLE vehicles (id integer PRIMARY KEY, unit_number text)'))
            await conn.execute(text("INSERT INTO vehicles VALUES (1, '603'), (2, 'T1003130')"))
            def run(sync, fn):
                with Operations.context(MigrationContext.configure(sync)):
                    fn()
            await conn.run_sync(lambda sync: run(sync, migration.upgrade))
            assert (await conn.execute(text('SELECT equipment_type FROM vehicles ORDER BY id'))).scalars().all() == ['unknown', 'unknown']
            await conn.execute(text("UPDATE vehicles SET equipment_type='trailer' WHERE id=2"))
            for value in ('invalid', None):
                savepoint = await conn.begin_nested()
                try:
                    await conn.execute(text('UPDATE vehicles SET equipment_type=:value WHERE id=1'), {'value': value})
                except IntegrityError:
                    await savepoint.rollback()
                else:
                    raise AssertionError('invalid equipment type accepted')
            await conn.run_sync(lambda sync: run(sync, migration.downgrade))
            assert (await conn.execute(text('SELECT count(*) FROM vehicles'))).scalar_one() == 2
            await conn.run_sync(lambda sync: run(sync, migration.upgrade))
            assert (await conn.execute(text('SELECT equipment_type FROM vehicles ORDER BY id'))).scalars().all() == ['unknown', 'unknown']
            print('PASS: populated legacy defaults, typed write, invalid/null constraints, downgrade/re-upgrade, preserved identity; transaction rolled back')
        finally:
            await transaction.rollback()
    await engine.dispose()

asyncio.run(main())
