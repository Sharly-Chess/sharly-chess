import time
from pathlib import Path
from typing import Any, Self
from logging import Logger
from dataclasses import dataclass, field
from collections.abc import Iterator
import pyodbc

from common.exception import PapiWebException
from common.logger import get_logger

logger: Logger = get_logger()

pyodbc.pooling = False
logger.info("Pooling ODBC : %s", "enabled" if pyodbc.pooling else "disabled")


@dataclass
class AccessDatabase:
    """Base class for Access-based databases."""

    file: Path
    write: bool = field(default=False)
    database: pyodbc.Connection | None = field(init=False, default=None)
    cursor: pyodbc.Cursor | None = field(init=False, default=None)

    def __enter__(self) -> Self:
        needed_driver: str = access_driver()
        if needed_driver not in pyodbc.drivers():
            logger.error("Installed ODBC drivers are:")
            for driver in odbc_drivers():
                logger.error(" - %s", driver)
            logger.error("Needed driver: %s", needed_driver)
            install_url: str = (
                "https://www.microsoft.com/en-us/download/details.aspx?id=54920"
            )
            logger.error("Install the driver (see %s) and restart.", install_url)
            logger.error(
                "Note: 32/64bits compatibility: accessdatabaseengine_X64.exe /passive"
            )
            raise PapiWebException("Microsoft Access driver not found.")
        db_url: str = f"DRIVER={{{needed_driver}}};DBQ={self.file.resolve()};"
        # Get rid of unresolved pyodbc.Error: ('HY000', 'The driver did not supply an error!')
        while self.database is None:
            try:
                self.database = pyodbc.connect(db_url, readonly=not self.write)
            except pyodbc.Error as e:
                logger.error("Connection to file %s failed: %s", self.file, e.args)
                time.sleep(1)
        self.cursor = self.database.cursor()
        return self

    def __exit__(self, exc_type, exc_value, tb):
        if self.database is not None:
            self.cursor.close()
            del self.cursor
            self.cursor = None
            self.database.close()
            del self.database
            self.database = None

    def _execute(self, query: str, params: tuple = ()):
        """Executes the prepare query with the given parameters."""
        self.cursor.execute(query, params)

    def _fetchall(self) -> Iterator[dict[str, Any]]:
        """Returns an iterator of dictionaries from the last executed query.
        Each dictionary is of the format {column_name : value, ...}."""
        columns = [column[0] for column in self.cursor.description]
        for row in self.cursor.fetchall():
            yield dict(zip(columns, row))

    def _fetchone(self) -> dict[str, Any]:
        """Returns a dictionary from the last executed query, in the format
        {column_name: value, ...}.
        Repeated applications of this method will advance the database cursor
        and return different row data."""
        columns = [column[0] for column in self.cursor.description]
        return dict(zip(columns, self.cursor.fetchone()))

    def _fetchval(self) -> Any:
        """Returns the next database cursor value."""
        return self.cursor.fetchval()

    def _commit(self):
        """Commits the pending transaction."""
        self.cursor.commit()


def odbc_drivers() -> list[str]:
    return pyodbc.drivers()


def access_driver() -> str:
    return "Microsoft Access Driver (*.mdb, *.accdb)"
