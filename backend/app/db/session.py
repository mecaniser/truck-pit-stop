from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from app.core.config import settings

# Convert postgresql:// to postgresql+asyncpg:// for async operations
database_url = settings.DATABASE_URL
if database_url.startswith("postgresql://") and "+asyncpg" not in database_url:
    database_url = database_url.replace("postgresql://", "postgresql+asyncpg://", 1)


def _is_postgres(url: str) -> bool:
    return url.startswith("postgresql+") or url.startswith("postgresql://")


def build_engine_options(url: str) -> dict:
    """Return driver-safe engine options for the configured database URL."""
    options: dict = {
        "echo": False,
        "future": True,
        "pool_pre_ping": True,
    }

    # Pool and server-side limits are intentionally PostgreSQL-only. Passing
    # these to SQLite changes its pooling semantics and breaks the isolated
    # in-memory database setup used by the test suite.
    if _is_postgres(url):
        options.update(
            pool_size=settings.DATABASE_POOL_SIZE,
            max_overflow=settings.DATABASE_MAX_OVERFLOW,
            pool_timeout=settings.DATABASE_POOL_TIMEOUT_SECONDS,
            pool_recycle=settings.DATABASE_POOL_RECYCLE_SECONDS,
            connect_args={
                "timeout": settings.DATABASE_CONNECT_TIMEOUT_SECONDS,
                "command_timeout": settings.DATABASE_STATEMENT_TIMEOUT_MS / 1000,
                "server_settings": {
                    "application_name": "truck-pit-stop-api",
                    "statement_timeout": str(settings.DATABASE_STATEMENT_TIMEOUT_MS),
                    "lock_timeout": str(settings.DATABASE_LOCK_TIMEOUT_MS),
                    "idle_in_transaction_session_timeout": str(
                        settings.DATABASE_IDLE_TRANSACTION_TIMEOUT_MS
                    ),
                },
            },
        )
    return options


engine = create_async_engine(database_url, **build_engine_options(database_url))

AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)


async def get_db() -> AsyncSession:
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()
