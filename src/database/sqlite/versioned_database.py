from abc import abstractmethod
from logging import Logger
from pathlib import Path
from sqlite3 import OperationalError
from typing import Self, TYPE_CHECKING

from packaging.version import Version

from common import PAPI_WEB_VERSION
from common.exception import PapiWebException
from common.logger import get_logger
from database.sqlite.sqlite_database import SQLiteDatabase

if TYPE_CHECKING:
    from database.sqlite.migration import AbstractMigrationManager

logger: Logger = get_logger()


class SQLiteVersionedDatabase(SQLiteDatabase):
    def __init__(self, file: Path, write: bool = False, auto_upgrade: bool = True):
        super().__init__(file, write)
        self._version: Version | None = None
        self.auto_upgrade = auto_upgrade

    @classmethod
    @abstractmethod
    def from_parent(cls, parent: Self) -> Self:
        pass

    @property
    @abstractmethod
    def stored_version(self) -> Version:
        """Version stored in the database."""

    @abstractmethod
    def set_version(self, version: Version):
        """Sets the version field stored in the database to `version`."""

    @property
    @abstractmethod
    def migration_manager(self) -> 'AbstractMigrationManager':
        """Manager to use for migrations."""

    @abstractmethod
    def insert_creation_values(self):
        """Insert into the database the creation values."""

    @property
    def version(self) -> Version:
        """Returns the Papi-web version which used the database."""
        if self._version is None:
            self._version = self.stored_version
        return self._version

    def upgrade(self):
        """Upgrades the database version from the stored database version
        to the latest version.
        This may change the structure of the database."""
        if self.version > self.migration_manager.latest_version:
            raise PapiWebException(
                f'Your Papi-web version ({PAPI_WEB_VERSION}) '
                f'can not open database {self.file.name} '
                f'(version {self.version}), please upgrade.'
            )
        logger.info('Upgrading database %s...', self.file.name)
        initial_version = self.version
        if self.migration_manager.migrate(self):
            logger.info(
                'Database %s has been upgraded from version %s to version %s.',
                self.file.name,
                initial_version,
                self.version,
            )

    def create(self):
        """Create a database by running the migrations from scratch.
        The file associated to this database must not exist before calling this method.
        """
        if self.exists():
            raise PapiWebException(
                f'The database can not be created because the '
                f'file [{self.file.resolve()}] already exists.'
            )
        try:
            self._create()
            with self.from_parent(
                SQLiteVersionedDatabase(self.file, True, False)
            ) as database:
                database._version = database.migration_manager.EMPTY_DATABASE_VERSION
                database.migration_manager.migrate(database)
                database.insert_creation_values()
                database.commit()
            logger.info('Database [%s] has been created.', self.file)
        except OperationalError as e:
            logger.warning('Database [%s] creation failed: %s', self.file, e.args)
            self.file.unlink(missing_ok=True)
            raise e

    def __enter__(self) -> Self:
        if not self.exists():
            raise PapiWebException(
                'Database could not be opened because file '
                f'[{self.file.resolve()}] does not exist.'
            )
        super().__enter__()

        if self.auto_upgrade and self.version < self.migration_manager.latest_version:
            if self.write:
                self.upgrade()
            else:
                with self.from_parent(SQLiteVersionedDatabase(self.file, True)):
                    # reopening the database in r/w mode forces the upgrade
                    pass
                # force self.version() to reload the new version number
                self._version = None
        return self
