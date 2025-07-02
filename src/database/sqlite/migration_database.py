from abc import abstractmethod, ABC
from functools import cached_property
from pathlib import Path
from sqlite3 import OperationalError
from typing import Self, TYPE_CHECKING

from packaging.version import Version

from common import SHARLY_CHESS_VERSION
from common.exception import SharlyChessException
from database.sqlite.sqlite_database import SQLiteDatabase

if TYPE_CHECKING:
    from database.sqlite.migration import DatabaseMigrationManager


class MigrationDatabase(SQLiteDatabase, ABC):
    """Abstract class representing databases which
    can handle one or more timelines of migrations."""

    @classmethod
    @abstractmethod
    def create_instance(cls, file: Path, write: bool = False) -> Self:
        """Alternative constructor with base params."""

    @cached_property
    @abstractmethod
    def migration_managers(self) -> list['DatabaseMigrationManager']:
        """Managers to use for migrations.
        The order determines which migration timeline is migrated first."""

    @property
    @abstractmethod
    def migration_by_legacy_version(self) -> dict[Version, str]:
        """Name of migration by version
        according to the legacy migration system."""

    # ---------------------------------------------------------------------------------
    # Metadata
    # ---------------------------------------------------------------------------------

    def create_metadata_table(self):
        self.execute(
            'CREATE TABLE IF NOT EXISTS `metadata` ('
            '   `version` TEXT NOT NULL,'
            "   `migration` TEXT NOT NULL DEFAULT 'm000_no_migration'"
            ')'
        )
        self.execute(
            'INSERT INTO `metadata` (`version`) VALUES (?)',
            (str(SHARLY_CHESS_VERSION),),
        )

    def is_metadata_table_installed(self) -> bool:
        try:
            self.execute('SELECT 1 FROM `metadata`')
            return '1' in self.fetchone()
        except OperationalError:
            return False

    def get_migration(self) -> str:
        self.execute('SELECT `migration` FROM `metadata`')
        return self.fetchone()['migration']

    def set_migration(self, migration: str):
        self.execute('UPDATE `metadata` SET `migration` = ?', (migration,))

    def get_version(self) -> Version:
        self.execute('SELECT `version` FROM `metadata`')
        return Version(self.fetchone()['version'])

    def set_version(self, version: Version):
        self.execute('UPDATE `metadata` SET `version` = ?', (str(version),))

    def get_migration_from_legacy_version(self) -> str | None:
        try:
            self.execute('SELECT `version` FROM `info`')
        except OperationalError:
            return None
        database_version = Version(self.fetchone()['version'])
        ordered_versions = sorted(self.migration_by_legacy_version.keys())
        migration_version = next(
            (
                version
                for version in reversed(ordered_versions)
                if version <= database_version
            ),
            None,
        )
        if migration_version is None:
            raise SharlyChessException(
                f'Database [{self.file.name}] - Unsupported version '
                f'[{database_version}], impossible to migrate '
                f'(min supported version: {ordered_versions[0]})'
            )
        return self.migration_by_legacy_version[migration_version]

    # ---------------------------------------------------------------------------------
    # Database management
    # ---------------------------------------------------------------------------------

    def check_status(self) -> bool:
        """Checks if the database can be used
        in the current version the application.
        Returns True if it can, False if it needs an upgrade.
        If it can't be upgraded, raises a *SharlyChessException*."""
        return all(manager.check_status() for manager in self.migration_managers)

    def upgrade(self):
        """Upgrades the database to the latest version.
        This may change the structure of the database."""
        for manager in self.migration_managers:
            manager.migrate()

    def create(self):
        """Create a database by running the migrations from scratch.
        The file associated to this database must not already exist.
        """
        if self.exists():
            raise SharlyChessException(
                f'The database can not be created because the '
                f'file [{self.file.resolve()}] already exists.'
            )

        self._create()
        with self.create_instance(self.file, True) as database:
            for manager in database.migration_managers:
                manager.migrate()

    def __enter__(self) -> Self:
        if not self.exists():
            raise SharlyChessException(
                'Database could not be opened because file '
                f'[{self.file.resolve()}] does not exist.'
            )
        return super().__enter__()
