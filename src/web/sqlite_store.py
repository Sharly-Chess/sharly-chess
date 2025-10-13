from datetime import datetime, timedelta

from litestar.stores.base import StorageObject, Store
from aiosqlitepool import SQLiteConnectionPool


class SQLiteStore(Store):
    """SQLite-based asynchronous key/value store."""

    def __init__(self, pool: SQLiteConnectionPool) -> None:
        self.pool = pool

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

            storage_object = StorageObject(
                datetime.fromisoformat(row[1]), bytes(row[0])
            )

            if storage_object.expired:
                await db.execute('DELETE FROM store WHERE key = ?', parameters=(key,))
                await db.commit()
                return None

            if renew_for and storage_object.expires_at:
                storage_object = StorageObject.new(storage_object.data, renew_for)
                await db.execute(
                    'UPDATE store(expires_at) WHERE key = ?', parameters=(key,)
                )
                await db.commit()

        return storage_object.data

    async def set(
        self, key: str, value: str | bytes, expires_in: int | timedelta | None = None
    ) -> None:
        if isinstance(value, str):
            value = value.encode('utf-8')

        storage_object = StorageObject.new(value, expires_in)
        async with self.pool.connection() as db:
            await db.execute(
                """
                INSERT INTO store (key, data, expires_at) VALUES (?, ?, ?)
                ON CONFLICT(key) DO
                UPDATE SET data = excluded.data, expires_at = excluded.expires_at""",
                parameters=(key, storage_object.data, storage_object.expires_at),
            )
            await db.commit()

    async def delete(self, key: str):
        async with self.pool.connection() as db:
            await db.execute('DELETE FROM store WHERE key = ?', parameters=(key,))
            await db.commit()

    async def delete_all(self):
        async with self.pool.connection() as db:
            await db.execute('DELETE FROM store')
            await db.commit()

    async def delete_expired(self):
        async with self.pool.connection() as db:
            await db.execute("DELETE FROM store WHERE exprires_at >= datetime('now')")
            await db.commit()

    async def exists(self, key: str) -> bool:
        async with self.pool.connection() as db:
            async with db.execute(
                'SELECT EXISTS(SELECT 1 from store where key = ?) as exists',
                parameters=(key,),
            ) as cursor:
                row = await cursor.fetchone()
            await db.commit()
        return int(row[0]) == 1

    async def expires_in(self, key: str) -> int | None:
        async with self.pool.connection() as db:
            async with db.execute(
                'SELECT expires_at FROM store where key = ?', parameters=(key,)
            ) as cursor:
                row = await cursor.fetchone()
            await db.commit()
        if not row:
            return None
        return datetime.fromisoformat(row[0])
