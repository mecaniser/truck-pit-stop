"""Safety contracts for the fast schema-copy test fixture."""
import sqlite3

import pytest
from sqlalchemy import text

from app.db.base import Base


@pytest.mark.asyncio
async def test_schema_copy_matches_fresh_ddl(_db_engine):
    # Compare table/index DDL, including constraints, with the original path.
    from sqlalchemy.ext.asyncio import create_async_engine
    reference = create_async_engine("sqlite+aiosqlite://")
    query = text("SELECT type, name, tbl_name, sql FROM sqlite_master ORDER BY type, name")
    try:
        async with reference.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
            expected = (await conn.execute(query)).all()
        async with _db_engine.connect() as conn:
            assert (await conn.execute(query)).all() == expected
    finally:
        await reference.dispose()


@pytest.mark.asyncio
@pytest.mark.parametrize("iteration", range(2))
async def test_commits_and_schema_changes_cannot_leak(_db_engine, _sqlite_schema_template, iteration):
    # Every parametrized invocation must see no previous invocation's DDL/data.
    async with _db_engine.begin() as conn:
        assert not (await conn.execute(text(
            "SELECT name FROM sqlite_master WHERE name='isolation_probe'"
        ))).all()
        await conn.execute(text("CREATE TABLE isolation_probe (id INTEGER PRIMARY KEY, value TEXT UNIQUE)"))
        await conn.execute(text("INSERT INTO isolation_probe VALUES (1, 'committed')"))
    async with _db_engine.connect() as conn:
        assert (await conn.execute(text("SELECT value FROM isolation_probe"))).scalar_one() == "committed"
    with sqlite3.connect(_sqlite_schema_template.as_uri() + "?mode=ro", uri=True) as source:
        assert source.execute("SELECT name FROM sqlite_master WHERE name='isolation_probe'").fetchall() == []
        for (table,) in source.execute("SELECT name FROM sqlite_master WHERE type='table'"):
            assert source.execute('SELECT COUNT(*) FROM "' + table.replace('"', '""') + '"').fetchone()[0] == 0
        with pytest.raises(sqlite3.OperationalError, match="readonly"):
            source.execute("CREATE TABLE forbidden (id INTEGER)")
