from collections import defaultdict
import json
from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field
from logging import Logger
from pathlib import Path
from sqlite3 import Connection, Cursor, connect, OperationalError
from threading import RLock
from typing import Self, Any

from common.logger import get_logger

logger: Logger = get_logger()

locks: defaultdict[Path, RLock] = defaultdict(RLock)


@dataclass
class SQLiteDatabase:
    """
    The base generic class for SQLite databases.
    """

    file: Path
    write: bool = field(default=False)
    database: Connection | None = field(init=False, default=None)
    cursor: Cursor | None = field(init=False, default=None)

    def exists(self) -> bool:
        """Checks if the database file exists."""
        return self.file.exists()

    def delete(self):
        """Deletes the database if it exists."""
        self.file.unlink(missing_ok=True)

    def acquire_lock(self):
        locks[self.file].acquire()

    def release_lock(self):
        locks[self.file].release()

    def _create(self, script: str | None = None):
        database: Connection | None = None
        try:
            self.acquire_lock()
            database = connect(database=self.file, detect_types=1, uri=True)
            if script:
                database.executescript(script)
                database.commit()
            database.close()
            self.release_lock()
        except OperationalError as e:
            if database:
                database.close()
            self.file.unlink(missing_ok=True)
            self.release_lock()
            raise e

    def __enter__(self) -> Self:
        db_url: str = f'file:{self.file}?mode={"rw" if self.write else "ro"}'
        self.acquire_lock()
        self.database = connect(db_url, detect_types=1, uri=True)
        self.cursor = self.database.cursor()
        if self.write:
            self.cursor.execute('PRAGMA journal_mode=WAL')
            self.commit()
        return self

    def __exit__(self, exc_type, exc_value, tb):
        if self.cursor is not None:
            self.cursor.close()
            del self.cursor
            self.cursor = None
        if self.database is not None:
            self.database.close()
            del self.database
            self.database = None
        self.release_lock()

    def execute(self, query: str, params: tuple | dict[str, Any] = ()):
        assert self.cursor is not None
        self.cursor.execute(query, params)

    def executemany(self, query: str, params: Iterable[tuple | dict[str, Any]] = ()):
        assert self.cursor is not None
        self.cursor.executemany(query, params)

    def executescript(self, sql: str):
        assert self.cursor is not None
        self.cursor.executescript(sql)

    def fetchall(self) -> Iterator[dict[str, Any]]:
        assert self.cursor is not None
        columns = [column[0] for column in self.cursor.description]
        for row in self.cursor.fetchall():
            yield dict(zip(columns, row))

    def fetchone(self) -> dict[str, Any]:
        assert self.cursor is not None
        columns = [column[0] for column in self.cursor.description]
        result = self.cursor.fetchone()
        return {} if result is None else dict(zip(columns, result))

    def commit(self):
        assert self.database is not None
        self.database.commit()

    def _last_inserted_id(self) -> int | None:
        assert self.cursor is not None
        return self.cursor.lastrowid

    @staticmethod
    def load_bool_or_none_from_database_field(
        data: int | None, if_none: bool | None = None
    ) -> bool | None:
        """Returns True if `data` is 1, False if `data` is something else other
        than None, and `if_none` if `data` is None."""
        return data == 1 if data is not None else if_none

    @staticmethod
    def load_bool_from_database_field(data: int | None) -> bool:
        """Returns True if `data` is 1, False otherwise."""
        return data == 1

    @staticmethod
    def load_json_from_database_field(json_data: str | None, if_none=None) -> Any:
        """Decodes the JSON data `json_data` and returns the result.
        If `json_data` is None, returns `if_none`."""
        return json.loads(json_data) if json_data is not None else if_none

    @staticmethod
    def set_dict_int_keys(string_dict: dict[str, Any] | None) -> dict[int, Any] | None:
        """Maps the string keys to integer keys and returns the resulting dict.
        If `string_dict` is None, returns None."""
        # This method is needed because JSON turns all keys to strings
        return (
            None if string_dict is None else {int(k): v for k, v in string_dict.items()}
        )

    @staticmethod
    def dump_to_json_database_field(obj: Any, if_none=None) -> str | None:
        """Serializes the given object `obj` to JSON.
        Returns the JSON serialization of `if_none` otherwise (may be None)."""
        if obj is not None:
            return json.dumps(obj)
        if if_none is not None:
            return json.dumps(if_none)
        return None

    @classmethod
    def dump_to_json_database_timer_colors(cls, colors) -> str | None:
        """Serializes the timer colors into JSON.
        By default, returns a serialization of {i: None} (i in (1, 2, 3))."""
        return cls.dump_to_json_database_field(colors, {i: None for i in range(1, 4)})

    @classmethod
    def dump_to_json_database_timer_delays(cls, delays) -> str | None:
        """Serializes the timer delays into JSON.
        By default, returns a serialization of {i: None} (i in (1, 2, 3))."""
        return cls.dump_to_json_database_field(delays, {i: None for i in range(1, 4)})
