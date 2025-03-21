import base64
import json
from pathlib import Path
from typing import Any, Self
from logging import Logger
from collections.abc import Iterator
import pyodbc

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
            with (open(file, 'r') as f):
                (
                    self.host,
                    self.user,
                    self.password,
                    self.database
                ) = json.loads(
                    base64.b64decode(
                        f.read().encode('ascii')
                    ).decode('ascii'))
        except FileNotFoundError as e:
            if DEVEL_ENV:
                raise PapiWebException(f'Could not read SQL server credentials ({e}), please run generate_ffe_sql_server_credentials.py.') from e
            else:
                raise PapiWebException('Could not read SQL server credentials.')

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
        with (open(credentials_file, 'w') as f):
            f.write(
                base64.b64encode(
                    json.dumps(
                        (
                            host,
                            user,
                            password,
                            database,
                        )
                    ).encode(
                        'ascii')
                ).decode('ascii')
            )


class SqlServer:
    """Base class for SQL-server databases."""

    DEFAULT_TIMEOUT: int = 3

    def __init__(
        self,
        credentials_file: Path,
        timeout: int | None = None
    ):
        """Initializes the database object, raises PapiWebException on error."""
        self.credentials: SqlServerCredentials = SqlServerCredentials(credentials_file)
        self.timeout: int = timeout | self.DEFAULT_TIMEOUT
        self.database: pyodbc.Connection | None = None
        self.cursor: pyodbc.Cursor | None = None

    def __enter__(self) -> Self:
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
        try:
            self.database = pyodbc.connect(db_url)
            self.database.timeout = self.timeout or self.DEFAULT_TIMEOUT
        except pyodbc.Error as e:
            if DEVEL_ENV:
                error: str = _('Connection to the FFE server failed: {error}.').format(error=e.args)
            else:
                error: str = _('Connection to the FFE server failed.')
            logger.error(error)
            raise PapiWebException(error)
        try:
            self.cursor = self.database.cursor()
        except pyodbc.Error as e:
            self.database = None
            if DEVEL_ENV:
                error: str = _('Connection to the FFE database failed: {error}.').format(error=e.args)
            else:
                error: str = _('Connection to the FFE database failed.')
            logger.error(error)
            raise PapiWebException(error)
        return self

    def __exit__(self, exc_type, exc_value, tb):
        """Closes the database connection."""
        if self.database is not None:
            self.cursor.close()
            del self.cursor
            self.cursor = None
            self.database.close()
            del self.database
            self.database = None

    def execute(self, query: str, params: tuple = ()):
        """Executes the prepare query with the given parameters."""
        try:
            self.cursor.execute(query, params)
        except pyodbc.Error as e:
            if DEVEL_ENV:
                error: str = _('Request to the FFE database failed: {error}.').format(error=e.args)
            else:
                error: str = _('Request to the FFE database failed.')
            logger.error(error)
            raise PapiWebException(error)

    def fetchall(self) -> Iterator[dict[str, Any]]:
        """Returns an iterator of dictionaries from the last executed query.
        Each dictionary is of the format {column_name : value, ...}."""
        columns = [column[0] for column in self.cursor.description]
        while row := self.cursor.fetchone():
            yield dict(zip(columns, row))

    def fetchone(self) -> dict[str, Any]:
        """Returns a dictionary from the last executed query, in the format
        {column_name: value, ...}.
        Repeated applications of this method will advance the database cursor
        and return different row data."""
        columns = [column[0] for column in self.cursor.description]
        return dict(zip(columns, self.cursor.fetchone()))

    def fetchval(self) -> Any:
        """Returns the next database cursor value."""
        return self.cursor.fetchval()

    def commit(self):
        """Commits the pending transaction."""
        self.cursor.commit()
