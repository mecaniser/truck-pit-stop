"""Process-local asyncio runtime for synchronous Celery task wrappers.

Celery's prefork workers execute synchronous task functions repeatedly in the
same child process. Reusing one event loop per child keeps SQLAlchemy/asyncpg
pooled connections attached to the loop that created them. Calling
``asyncio.run`` per task would close that loop while the shared engine still
holds its connections, causing intermittent ``Event loop is closed`` errors.
"""
from __future__ import annotations

import asyncio
from typing import Awaitable, Optional, TypeVar

from celery.signals import worker_process_shutdown

from app.db.session import engine


ResultT = TypeVar("ResultT")
_worker_loop: Optional[asyncio.AbstractEventLoop] = None


def _get_worker_loop() -> asyncio.AbstractEventLoop:
    global _worker_loop
    if _worker_loop is not None and not _worker_loop.is_closed():
        return _worker_loop

    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

    if loop.is_closed():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

    _worker_loop = loop
    return loop


def run_async(awaitable: Awaitable[ResultT]) -> ResultT:
    """Run async task logic on the current Celery child process's event loop."""
    loop = _get_worker_loop()
    if loop.is_running():
        raise RuntimeError("Celery async runtime cannot enter an already-running event loop")
    return loop.run_until_complete(awaitable)


@worker_process_shutdown.connect
def close_worker_async_runtime(**_kwargs) -> None:
    """Dispose loop-bound database connections before a worker child exits."""
    global _worker_loop
    loop = _worker_loop
    if loop is None or loop.is_closed():
        _worker_loop = None
        return

    if not loop.is_running():
        loop.run_until_complete(engine.dispose())
        loop.close()
    _worker_loop = None
