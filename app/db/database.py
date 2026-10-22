from typing import Any

from sqlalchemy import event
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)


class Database:
    """Owns the async engine and the session factory for the application lifetime."""

    def __init__(self, url: str, **engine_kwargs: Any) -> None:
        engine_kwargs.setdefault("pool_pre_ping", True)
        self.engine: AsyncEngine = create_async_engine(url, **engine_kwargs)
        if url.startswith("sqlite"):
            _enable_sqlite_foreign_keys(self.engine)
        self.sessionmaker: async_sessionmaker[AsyncSession] = async_sessionmaker(
            self.engine, expire_on_commit=False
        )

    async def dispose(self) -> None:
        await self.engine.dispose()


def _enable_sqlite_foreign_keys(engine: AsyncEngine) -> None:
    # SQLite ignores ON DELETE CASCADE unless foreign keys are switched on per connection.
    @event.listens_for(engine.sync_engine, "connect")
    def _on_connect(dbapi_connection, _record) -> None:  # type: ignore[no-untyped-def]
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()
