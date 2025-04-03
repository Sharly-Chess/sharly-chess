import asyncio
import base64
import json
from pathlib import Path
from typing import Any, Self
from logging import Logger
from collections.abc import AsyncIterator
from common.network import NetworkMonitor
import pyodbc  # type: ignore
import aioodbc

from common import DEVEL_ENV
from common.exception import PapiWebException
from common.i18n import _
from common.logger import get_logger

logger: Logger = get_logger()


class SqlServerCredentials:
    def __init__(
        self,
        file: Path,
    ):
        """Reads credentials from the given file, raises PapiWebException on error."""
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
                raise PapiWebException(
                    f'Could not read SQL server credentials ({e}), please run generate_ffe_sql_server_credentials.py.'
                ) from e
            else:
                raise PapiWebException(
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
    """Base class for SQL-server databases."""

    DEFAULT_TIMEOUT: int = 3

    def __init__(self, credentials_file: Path, timeout: int | None = None):
        """Initializes the database object, raises PapiWebException on error."""
        self.credentials: SqlServerCredentials = SqlServerCredentials(credentials_file)
        self.timeout: int = timeout or self.DEFAULT_TIMEOUT
        self.database: aioodbc.Connection | None = None
        self.cursor: aioodbc.Cursor | None = None
        self.error: str | None = None

    async def __aenter__(self) -> Self:
        """Opens the database connection, raises PapiWebException on error."""
        needed_driver: str = 'SQL Server'
        if needed_driver not in pyodbc.drivers():
            logger.error('Installed ODBC drivers are:')
            for driver in pyodbc.drivers():
                logger.error(' - %s', driver)
            logger.error('Needed driver: %s', needed_driver)
            install_url: str = (
                'https://learn.microsoft.com/en-us/sql/connect/odbc/download-odbc-driver-for-sql-server'
                '?view=sql-server-ver16#download-for-windows'
            )
            logger.error('Install the driver (see %s) and restart.', install_url)
            self.error = 'SQL server driver not found.'
            logger.error(self.error)
            return self

        db_url: str = f'Driver={{{needed_driver}}};Server={self.credentials.host};Database={self.credentials.database};UID={self.credentials.user};PWD={self.credentials.password}'
        timeout = self.timeout or self.DEFAULT_TIMEOUT

        async def connect_to_server():
            nonlocal self, db_url
            self.database = await aioodbc.connect(dsn=db_url)

        try:
            await asyncio.wait_for(connect_to_server(), timeout=timeout)
        except (TimeoutError, pyodbc.Error) as e:
            NetworkMonitor.set_connected(False)
            if DEVEL_ENV:
                error: str = _('Connection to the FFE server failed: {error}.').format(
                    error=e.args
                )
            else:
                error: str = _('Connection to the FFE server failed.')
            logger.error(error)
            raise PapiWebException(
                error or _('Connection to the FFE server failed.')
            ) from e

        assert self.database is not None
        try:
            self.cursor = await self.database.cursor()
        except pyodbc.Error as e:
            self.database = None
            if DEVEL_ENV:
                error: str = _(
                    'Connection to the FFE database failed: {error}.'
                ).format(error=e.args)
            else:
                error: str = _('Connection to the FFE database failed.')
            logger.error(error)
            raise PapiWebException(error) from e
        return self

    async def __aexit__(self, exc_type, exc_value, tb):
        """Closes the database connection."""
        if self.database is not None:
            if self.cursor is not None:
                await self.cursor.close()
                del self.cursor
                self.cursor = None
            await self.database.close()
            del self.database
            self.database = None

    def _check_cursor(self):
        """Check that the cursor is available."""
        if self.cursor is None:
            raise RuntimeError('Database connection not established')

    async def execute(self, query: str, params: tuple = ()):
        """Executes the prepare query with the given parameters."""
        self._check_cursor()
        assert self.cursor is not None
        try:
            await self.cursor.execute(query, params)
        except pyodbc.Error as e:
            if DEVEL_ENV:
                error: str = _('Request to the FFE database failed: {error}.').format(
                    error=e.args
                )
            else:
                error: str = _('Request to the FFE database failed.')
            logger.error(error)
            raise PapiWebException(error) from e

    async def fetchall(self) -> AsyncIterator[dict[str, Any]]:
        """Returns an iterator of dictionaries from the last executed query.
        Each dictionary is of the format {column_name : value, ...}."""
        self._check_cursor()
        assert self.cursor is not None
        columns = [column[0] for column in self.cursor.description]
        while row := await self.cursor.fetchone():
            yield dict(zip(columns, row))

    async def fetchone(self) -> dict[str, Any]:
        """Returns a dictionary from the last executed query, in the format
        {column_name: value, ...}.
        Repeated applications of this method will advance the database cursor
        and return different row data."""
        self._check_cursor()
        assert self.cursor is not None
        columns = [column[0] for column in self.cursor.description]
        return dict(zip(columns, await self.cursor.fetchone()))

    async def fetchval(self) -> Any:
        """Returns the next database cursor value."""
        self._check_cursor()
        assert self.cursor is not None
        return await self.cursor.fetchval()

    async def commit(self):
        """Commits the pending transaction."""
        self._check_cursor()
        assert self.cursor is not None
        await self.cursor.commit()
