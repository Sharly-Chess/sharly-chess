import asyncio
import base64
import json
from typing import Self, Any, NoReturn
from pathlib import Path
from logging import Logger
from collections.abc import AsyncIterator
from common.network import NetworkMonitor
import pytds

from common import DEVEL_ENV
from common.exception import SharlyChessException
from common.i18n import _
from common.logger import get_logger

logger: Logger = get_logger()


class SqlServerCredentials:
    def __init__(
        self,
        file: Path,
    ):
        """Reads credentials from the given file, raises SharlyChessException on error."""
        self.host: str
        self.user: str
        self.password: str
        self.database: str
        try:
            with open(file, 'r') as f:
                (self.host, self.user, self.password, self.database) = json.loads(
                    base64.b64decode(f.read().encode('ascii')).decode('ascii')
                )
        except FileNotFoundError as e:
            if DEVEL_ENV:
                raise SharlyChessException(
                    f'Could not read SQL server credentials ({e}), please run generate_xxx_sql_server_credentials.py.'
                ) from e
            else:
                raise SharlyChessException(
                    'Could not read SQL server credentials.'
                ) from None

    @staticmethod
    def dump(
        credentials_file: Path,
        host: str,
        user: str,
        password: str,
        database: str,
    ):
        """Dumps credentials to the given file.
        The credentials can be read by `creds = SqlServerCredentials(file)`."""
        credentials_file.parent.mkdir(exist_ok=True, parents=True)
        with open(credentials_file, 'w') as f:
            f.write(
                base64.b64encode(
                    json.dumps(
                        (
                            host,
                            user,
                            password,
                            database,
                        )
                    ).encode('ascii')
                ).decode('ascii')
            )


class SqlServer:
    """Base class for SQL-server databases using python-tds."""

    DEFAULT_TIMEOUT: int = 3

    def __init__(self, credentials_file: Path, timeout: int | None = None):
        """Initializes the database object, raises SharlyChessException on error."""
        self.credentials: SqlServerCredentials = SqlServerCredentials(credentials_file)
        self.timeout: int = timeout or self.DEFAULT_TIMEOUT
        self.database: pytds.Connection | None = None
        self.cursor: pytds.Cursor | None = None
        self.error: str | None = None

    async def __aenter__(self) -> Self:
        """Opens the database connection, raises SharlyChessException on error."""
        try:
            # Connect using python-tds (pure Python, no ODBC needed)
            self.database = await asyncio.to_thread(
                pytds.connect,
                server=self.credentials.host,
                database=self.credentials.database,
                user=self.credentials.user,
                password=self.credentials.password,
                timeout=self.timeout,
                autocommit=True,
            )

            if self.database is not None:
                self.cursor = self.database.cursor()
                logger.info('Successfully connected using python-tds')
        except (pytds.Error, TimeoutError) as e:
            NetworkMonitor.set_connected(False)
            if DEVEL_ENV:
                error_msg = _('Connection to the server failed: {error}.').format(
                    error=str(e)
                )
            else:
                error_msg = _('Connection to the server failed.')
            logger.error(error_msg)
            raise SharlyChessException(error_msg) from e
        except Exception as e:
            NetworkMonitor.set_connected(False)
            if DEVEL_ENV:
                error_msg = _('Connection to the server failed: {error}.').format(
                    error=str(e)
                )
            else:
                error_msg = _('Connection to the server failed.')
            logger.error(error_msg)
            raise SharlyChessException(error_msg) from e
        return self

    async def __aexit__(self, exc_type, exc_value, tb):
        """Closes the database connection."""
        if self.database:
            if self.cursor:
                await asyncio.to_thread(self.cursor.close)
                self.cursor = None
            await asyncio.to_thread(self.database.close)
            self.database = None

    def _check_cursor(self):
        """Check that the cursor is available."""
        if not self.cursor:
            raise RuntimeError('Database connection not established')

    def _handle_database_error(self, e: Exception) -> NoReturn:
        """Handle database errors consistently."""
        NetworkMonitor.set_connected(False)
        if DEVEL_ENV:
            error_msg = _('Request to the database failed: {error}.').format(
                error=str(e)
            )
        else:
            error_msg = _('Request to the database failed.')
        logger.error(error_msg)
        raise SharlyChessException(error_msg) from e

    async def execute(self, query: str, params: tuple = ()) -> None:
        """Executes the prepared query with the given parameters."""
        self._check_cursor()
        assert self.cursor is not None
        try:
            await asyncio.to_thread(self.cursor.execute, query, params)
        except (pytds.Error, TimeoutError) as e:
            self._handle_database_error(e)

    async def fetchall(self) -> AsyncIterator[dict[str, Any]]:
        """Returns an iterator of dictionaries from the last executed query.
        Each dictionary is of the format {column_name : value, ...}."""
        self._check_cursor()
        assert self.cursor is not None

        try:
            # Get column names
            columns = [column[0] for column in self.cursor.description]

            # Fetch all rows and convert to dictionaries
            rows = await asyncio.to_thread(self.cursor.fetchall)
            for row in rows:
                yield dict(zip(columns, row))
        except (pytds.Error, TimeoutError) as e:
            self._handle_database_error(e)

    async def fetchone(self) -> dict[str, Any] | None:
        """Returns a dictionary from the last executed query, in the format
        {column_name: value, ...}.
        Repeated applications of this method will advance the database cursor
        and return different row data."""
        self._check_cursor()
        assert self.cursor is not None

        try:
            # Get column names
            columns = [column[0] for column in self.cursor.description]

            # Fetch one row
            row = await asyncio.to_thread(self.cursor.fetchone)
            return dict(zip(columns, row)) if row else None
        except (pytds.Error, TimeoutError) as e:
            self._handle_database_error(e)

    async def fetchval(self) -> Any:
        """Returns the next database cursor value."""
        self._check_cursor()
        assert self.cursor is not None
        try:
            row = await asyncio.to_thread(self.cursor.fetchone)
            return row[0] if row else None
        except (pytds.Error, TimeoutError) as e:
            self._handle_database_error(e)

    async def commit(self):
        """Commits the pending transaction."""
        if self.database:
            await asyncio.to_thread(self.database.commit)
