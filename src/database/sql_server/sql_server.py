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
    """Base class for SQL-server databases."""

    DEFAULT_TIMEOUT: int = 3

    def __init__(self, credentials_file: Path, timeout: int | None = None):
        """Initializes the database object, raises SharlyChessException on error."""
        self.credentials: SqlServerCredentials = SqlServerCredentials(credentials_file)
        self.timeout: int = timeout or self.DEFAULT_TIMEOUT
        self.database: aioodbc.Connection | None = None
        self.cursor: aioodbc.Cursor | None = None
        self.error: str | None = None

    async def __aenter__(self) -> Self:
        """Opens the database connection, raises SharlyChessException on error."""
        # Try to find an appropriate SQL Server driver
        available_drivers = pyodbc.drivers()

        # Preferred drivers in order of preference
        preferred_drivers = [
            'FreeTDS',      # Open source driver, works well with older servers
            'SQL Server'    # Legacy Windows driver, stable and reliable
        ]

        selected_driver = None
        for driver in preferred_drivers:
            if driver in available_drivers:
                selected_driver = driver
                break

        if selected_driver is None:
            logger.error('Installed ODBC drivers are:')
            for driver in available_drivers:
                logger.error(' - %s', driver)
            logger.error('No compatible SQL Server driver found. Supported drivers: %s', ', '.join(preferred_drivers))

            import platform
            if platform.system() == 'Darwin':  # macOS
                logger.error('On macOS, install FreeTDS: brew install freetds')
            elif platform.system() == 'Windows':  # Windows
                logger.error('Needed driver: SQL Server')
                install_url: str = (
                    'https://learn.microsoft.com/en-us/sql/connect/odbc/download-odbc-driver-for-sql-server'
                    '?view=sql-server-ver16#download-for-windows'
                )
                logger.error('Install the driver (see %s) and restart.', install_url)
            else:  # Linux
                logger.error('On Linux, install FreeTDS: apt-get install freetds-dev unixodbc-dev (Ubuntu/Debian) or equivalent')
            self.error = 'SQL server driver not found.'
            logger.error(self.error)
            return self

        logger.info('Using SQL Server driver: %s', selected_driver)

        common_params = [
            f'Driver={{{selected_driver}}}',
            f'Server={self.credentials.host}',
            f'Database={self.credentials.database}',
            f'UID={self.credentials.user}',
            f'PWD={self.credentials.password}'
        ]

        if 'FreeTDS' in selected_driver:
            # FreeTDS has different connection parameters
            conn_params = common_params + [
                'Port=1433',
                'TDS_Version=7.0'  # Very old SQL Server compatibility
            ]

        else:
            # Legacy SQL Server driver (Windows)
            conn_params = common_params + [
                ('Basic', common_params + ['Connection Timeout=30'])
            ]

        last_error = None
        db_url = ';'.join(conn_params)

        try:
            timeout = self.timeout or self.DEFAULT_TIMEOUT
            self.database = await asyncio.wait_for(
                aioodbc.connect(dsn=db_url), timeout=timeout
            )
            logger.info('Successfully connected')
        except (pyodbc.Error, TimeoutError, OSError) as e:
            last_error = e
            logger.warning('Connection failed: %s', str(e))

        if self.database is None:
            NetworkMonitor.set_connected(False)
            if isinstance(last_error, TimeoutError):
                error_msg = _('Connection to the server failed: {error}.').format(
                    error=_('timeout')
                )
            elif DEVEL_ENV and last_error:
                error_msg = _('Connection to the server failed: {error}.').format(
                    error=last_error.args if hasattr(last_error, 'args') else str(last_error)
                )
            else:
                error_msg = _('Connection to the server failed.')
            logger.error(error_msg)
            raise SharlyChessException(error_msg) from last_error

        assert self.database is not None
        try:
            self.cursor = await self.database.cursor()
        except pyodbc.Error as e:
            self.database = None
            if DEVEL_ENV:
                error: str = _('Connection to the database failed: {error}.').format(
                    error=e.args
                )
            else:
                error: str = _('Connection to the database failed.')
            logger.error(error)
            raise SharlyChessException(error) from e
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
                error: str = _('Request to the database failed: {error}.').format(
                    error=e.args
                )
            else:
                error: str = _('Request to the database failed.')
            logger.error(error)
            raise SharlyChessException(error) from e

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
        row = await self.cursor.fetchone()
        return dict(zip(columns, row)) if row else {}

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
