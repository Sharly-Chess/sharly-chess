import asyncio
import logging
import sqlite3
from datetime import datetime, timedelta

from litestar.stores.base import StorageObject, Store
from aiosqlitepool import SQLiteConnectionPool

logger = logging.getLogger(__name__)

_MAX_RETRIES = 5
_BASE_DELAY = (
    0.05  # seconds – exponential backoff: 50 ms, 100 ms, 200 ms, 400 ms, 800 ms
)


class SQLiteStore(Store):
    """SQLite-based asynchronous key/value store."""

    def __init__(self, pool: SQLiteConnectionPool) -> None:
        self.pool = pool

    # ------------------------------------------------------------------
    # Retry helper
    # ------------------------------------------------------------------

    @staticmethod
    async def _retry_on_locked(operation):
        """Retry *operation* with exponential back-off on ``database is locked``."""
        for attempt in range(_MAX_RETRIES):
            try:
                return await operation()
            except sqlite3.OperationalError as exc:
                if 'locked' not in str(exc) or attempt == _MAX_RETRIES - 1:
                    raise
                delay = _BASE_DELAY * (2**attempt)
                logger.warning(
                    'SQLiteStore: database locked, retry %d/%d in %.0f ms',
                    attempt + 1,
                    _MAX_RETRIES - 1,
                    delay * 1000,
                )
                await asyncio.sleep(delay)

    async def __aenter__(self) -> None:
        return

    async def __aexit__(self, exc_type, exc_value, exc_tb):
        pass

    async def get(
        self, key: str, renew_for: int | timedelta | None = None
    ) -> bytes | None:
        async with self.pool.connection() as db:
            async with db.execute(
                'SELECT data, expires_at FROM store WHERE key = ?', parameters=(key,)
            ) as cursor:
                row = await cursor.fetchone()
        if not row:
            return None

        storage_object = StorageObject(datetime.fromisoformat(row[1]), bytes(row[0]))

        if storage_object.expired:

            async def _delete_expired_key():
                async with self.pool.connection() as db:
                    await db.execute(
                        'DELETE FROM store WHERE key = ?', parameters=(key,)
                    )
                    await db.commit()

            await self._retry_on_locked(_delete_expired_key)
            return None

        if renew_for and storage_object.expires_at:
            storage_object = StorageObject.new(storage_object.data, renew_for)

            async def _renew():
                async with self.pool.connection() as db:
                    await db.execute(
                        'UPDATE store SET expires_at = ? WHERE key = ?',
                        parameters=(storage_object.expires_at, key),
                    )
                    await db.commit()

            await self._retry_on_locked(_renew)

        return storage_object.data

    async def set(
        self, key: str, value: str | bytes, expires_in: int | timedelta | None = None
    ) -> None:
        if isinstance(value, str):
            value = value.encode('utf-8')

        storage_object = StorageObject.new(value, expires_in)

        async def _write():
            async with self.pool.connection() as db:
                await db.execute(
                    """
                    INSERT INTO store (key, data, expires_at) VALUES (?, ?, ?)
                    ON CONFLICT(key) DO
                    UPDATE SET data = excluded.data, expires_at = excluded.expires_at""",
                    parameters=(key, storage_object.data, storage_object.expires_at),
                )
                await db.commit()

        await self._retry_on_locked(_write)

    async def delete(self, key: str):
        async def _write():
            async with self.pool.connection() as db:
                await db.execute('DELETE FROM store WHERE key = ?', parameters=(key,))
                await db.commit()

        await self._retry_on_locked(_write)

    async def delete_all(self):
        async def _write():
            async with self.pool.connection() as db:
                await db.execute('DELETE FROM store')
                await db.commit()

        await self._retry_on_locked(_write)

    async def delete_expired(self):
        async def _write():
            async with self.pool.connection() as db:
                await db.execute(
                    "DELETE FROM store WHERE expires_at <= datetime('now')"
                )
                await db.commit()

        await self._retry_on_locked(_write)

    async def exists(self, key: str) -> bool:
        async with self.pool.connection() as db:
            async with db.execute(
                'SELECT EXISTS(SELECT 1 from store where key = ?) as exists',
                parameters=(key,),
            ) as cursor:
                row = await cursor.fetchone()
        return int(row[0]) == 1

    async def expires_in(self, key: str) -> int | None:
        async with self.pool.connection() as db:
            async with db.execute(
                'SELECT expires_at FROM store where key = ?', parameters=(key,)
            ) as cursor:
                row = await cursor.fetchone()
        if not row:
            return None
        return int((datetime.fromisoformat(row[0]) - datetime.now()).total_seconds())
