import re
import traceback
from abc import abstractmethod, ABC
from dataclasses import dataclass, field
from functools import cached_property
from importlib import import_module
from logging import Logger
from pkgutil import iter_modules
from sqlite3 import OperationalError
from types import ModuleType
from typing import Callable, Any

from packaging.version import Version

from common import DEVEL_ENV, SHARLY_CHESS_VERSION, APP_NAME
from common.exception import SharlyChessException
from common.logger import get_logger
from database.sqlite.migration_database import MigrationDatabase

logger: Logger = get_logger()


@dataclass
class PostUpgradeTask:
    """Class representing a task to execute once the database
    has been upgraded to its latest version.
    The function executed by this task can contain imports from the core project."""

    function: Callable
    args: list = field(default_factory=list)
    kwargs: dict[str, Any] = field(default_factory=dict[str, Any])

    def execute(self):
        self.function(*self.args, **self.kwargs)


class BaseMigration(ABC):
    """Base class for all migrations."""

    def __init__(self, database: MigrationDatabase):
        self.database = database
        self.post_upgrade_tasks: list[PostUpgradeTask] = []

    @staticmethod
    def are_foreign_keys_enabled() -> bool:
        """Defines if the foreign keys are enabled or disabled when running the migration.
        Useful when a table needs to be recreated without triggering the `ON DELETE` constraints."""
        return True

    @abstractmethod
    def forward(self):
        """Apply the migration."""

    def backward(self):
        """Rollback the migration. Does not have to be implemented,
        but raises an error on rollback if it is not."""
        raise NotImplementedError('Rollback not implemented for this migration')


class MigrationManager[T: MigrationDatabase](ABC):
    """Class managing a timeline of migrations of a *MigrationDatabase*.
    Migration classes are stored in a similar base module.
    Each submodule of this file should implement a class named "Migration"
    inheriting from the *BaseMigration* class.
    A submodule should be named according the pattern [m\\d{3}_[a-z_]+]
    Example: m001_create_info_table
    This name is stored in the database in a *migration* field.
    It represents the position of the database in the timeline.
    The class also handles a *version* field.
    Both should be stored in a *metadata* table.
    """

    MIGRATION_CLASS_NAME: str = 'Migration'
    MIGRATION_ZERO: str = 'm000_no_migration'

    def __init__(self, base_database: T, base_migration_module: ModuleType):
        self.base_database = base_database
        self.base_migration_module = base_migration_module
        self.post_upgrade_tasks: list[PostUpgradeTask] = []

    def get_database(self, write: bool = False, enable_foreign_keys: bool = True) -> T:
        return self.base_database.get_migration_instance(write, enable_foreign_keys)

    @abstractmethod
    def is_metadata_installed(self, database: T) -> bool:
        """Check if the metadata fields are installed.
        These fields are used to store the version and the migration."""

    @abstractmethod
    def install_metadata(self, database: T):
        """Install the metadata field into the database.
        There must be one for the version and one for the migration."""

    @abstractmethod
    def get_migration(self, database: T) -> str:
        """Retrieve the migration from the database."""

    @abstractmethod
    def set_migration(self, migration: str, database: T):
        """Set the migration field of the database to *migration*."""

    @abstractmethod
    def get_version(self, database: T) -> Version:
        """Retrieve the version from the database."""

    @abstractmethod
    def set_version(self, version: Version, database: T):
        """Set the version field of the database to *version*."""

    @property
    @abstractmethod
    def latest_version(self) -> Version:
        """Latest expected version for this migration manager."""

    @abstractmethod
    def get_migration_from_legacy_version(self, database: T) -> str | None:
        """Migrations used to be handled through version number.
        This method ensures the compatibility between the two systems."""
        # TODO remove once all legacy migrations have been squashed

    @abstractmethod
    def remove_legacy_version_field(self, database: T):
        """Remove the version field which was used
        as the migration field in the legacy migration system.
        Field might not exist."""
        # TODO remove once all legacy migrations have been squashed

    @property
    def migration_modules(self) -> list[str]:
        return [
            self._get_migration_module_name(migration) for migration in self.migrations
        ]

    @cached_property
    def migrations(self) -> list[str]:
        return sorted(
            [
                module
                for _, module, _ in iter_modules(self.base_migration_module.__path__)
            ]
        )

    def check_status(self, database: T) -> bool:
        """Check if the database is migrated to the latest migration.
        Raise a SharlyChessException if the stored migration is unknown.
        Assert that the timeline is valid."""
        if DEVEL_ENV:
            self._check_timeline()
        if not self.is_metadata_installed(database):
            self.get_migration_from_legacy_version(database)
            return False

        version = self.get_version(database)
        if version > self.latest_version:
            raise SharlyChessException(
                self.log_prefix
                + (
                    f'Database version [{version}] is after '
                    f'current app version {self.latest_version}.'
                )
            )
        status = True
        if version < self.latest_version:
            status = False
        migration = self.get_migration(database)
        if migration not in self.migrations + [self.MIGRATION_ZERO]:
            if migration > self.migrations[-1]:
                message = (
                    f'Database can only be opened by a later version of {APP_NAME}.'
                )
            elif migration < self.migrations[0]:
                message = (
                    f'Database can only be opened by a previous version of {APP_NAME}.'
                )
            else:
                message = 'A migration was most likely renamed.'
            raise SharlyChessException(
                self.log_prefix + 'unknown migration '
                f'[{migration}] in the database. {message}'
            )
        elif migration != self.migrations[-1]:
            status = False
        return status

    def _check_timeline(self):
        indexes = []
        for migration in self.migrations:
            assert re.match(r'^m\d{3}_[a-z0-9_]+$', migration), (
                f'Migration [{migration}] does not match expected pattern'
            )
            index = self._migration_index(migration)
            assert index != 0, 'Prefix [m000] not allowed'
            assert index not in indexes, (
                f'2 migrations found with prefix [m{index:03d}]'
            )
            indexes.append(index)
            migration_module = import_module(self._get_migration_module_name(migration))
            assert hasattr(migration_module, self.MIGRATION_CLASS_NAME)
            migration_class = getattr(migration_module, self.MIGRATION_CLASS_NAME)
            assert issubclass(migration_class, BaseMigration)

    def _get_migration_module_name(self, migration: str) -> str:
        return f'{self.base_migration_module.__name__}.{migration}'

    def _get_migration_class(self, migration: str) -> type[BaseMigration]:
        return getattr(
            import_module(self._get_migration_module_name(migration)),
            self.MIGRATION_CLASS_NAME,
        )

    @cached_property
    def migration_by_index(self) -> dict[int, str]:
        return {
            self._migration_index(module_name): module_name
            for module_name in self.migrations
        }

    @staticmethod
    def _migration_index(migration: str) -> int:
        return int(migration[1:4])

    @property
    def log_prefix(self) -> str:
        return self.base_database.log_prefix

    def _next_migration(self, current_migration: str, max_migration: str) -> str | None:
        return next(
            (
                migration
                for migration in self.migrations
                if current_migration < migration <= max_migration
            ),
            None,
        )

    def _previous_migration(self, current_migration: str) -> str:
        return next(
            migration
            for migration in reversed([self.MIGRATION_ZERO] + self.migrations)
            if current_migration > migration
        )

    def migrate(self, target_migration: str | None = None):
        """Migrate *database* to the migration *target_migration*.
        *target_migration* defaults to the latest migration.
        Raises a SharlyChessException if it fails."""
        if target_migration is None:
            target_migration = self.migrations[-1]
        elif target_migration not in self.migrations + [self.MIGRATION_ZERO]:
            raise ValueError(
                self.log_prefix + f'unknown migration [{target_migration}]'
            )
        try:
            with self.get_database(True) as database:
                if not self.is_metadata_installed(database):
                    logger.debug(self.log_prefix + 'Installing metadata...')
                    self.install_metadata(database)
                    if migration := self.get_migration_from_legacy_version(database):
                        self.set_migration(migration, database)
                    self.remove_legacy_version_field(database)

                version = self.get_version(database)
                if version != self.latest_version:
                    self.set_version(self.latest_version, database)
                    logger.debug(
                        self.log_prefix
                        + f'Version updated from [{version}] to [{self.latest_version}]'
                    )

                current_migration = self.get_migration(database)
            if target_migration == current_migration:
                logger.debug(self.log_prefix + 'No migration to run')
            else:
                logger.debug(
                    self.log_prefix
                    + f'Migrating from [{current_migration}] to [{target_migration}]...'
                )
                if current_migration > target_migration:
                    self._rollback(current_migration, target_migration)
                else:
                    self._upgrade(current_migration, target_migration)
                logger.debug(self.log_prefix + 'Migration complete.')
        except Exception as error:
            logger.debug(self.log_prefix + traceback.format_exc())
            raise SharlyChessException(self.log_prefix + f'Migration failed: {error}')

    def _upgrade(self, current_migration: str, target_migration: str):
        migration: str | None = current_migration
        while migration := self._next_migration(migration or '', target_migration):
            migration_class = self._get_migration_class(migration)
            with self.get_database(
                True, migration_class.are_foreign_keys_enabled()
            ) as database:
                migration_object = migration_class(database)
                migration_object.forward()
                self.set_migration(migration, database)
                self.post_upgrade_tasks += migration_object.post_upgrade_tasks
            logger.debug(self.log_prefix + f'\t{migration} applied')

    def _rollback(self, current_migration: str, target_migration: str):
        migration = current_migration
        while migration != target_migration:
            migration_class = self._get_migration_class(migration)
            with self.get_database(
                True, migration_class.are_foreign_keys_enabled()
            ) as database:
                migration_object = migration_class(database)
                migration_object.backward()
                previous_migration = self._previous_migration(migration)
                self.set_migration(previous_migration, database)
            logger.debug(self.log_prefix + f'\t{migration} rolled back')
            migration = previous_migration
        with self.get_database(True) as database:
            self.set_migration(target_migration, database)


class DatabaseMigrationManager(MigrationManager[MigrationDatabase]):
    """Migration manager for full databases,
    where the migrations start from an empty database."""

    def get_migration(self, database: MigrationDatabase) -> str:
        return database.get_migration()

    def set_migration(self, migration: str, database: MigrationDatabase):
        database.set_migration(migration)

    def get_version(self, database: MigrationDatabase) -> Version:
        return database.get_version()

    def set_version(self, version: Version, database: MigrationDatabase):
        database.set_version(version)

    @property
    def latest_version(self) -> Version:
        return SHARLY_CHESS_VERSION

    def is_metadata_installed(self, database: MigrationDatabase) -> bool:
        return database.is_metadata_table_installed()

    def install_metadata(self, database: MigrationDatabase):
        database.create_metadata_table()

    def remove_legacy_version_field(self, database: MigrationDatabase):
        try:
            database.execute('ALTER TABLE `info` DROP COLUMN `version`')
        except OperationalError:
            pass

    def get_migration_from_legacy_version(
        self, database: MigrationDatabase
    ) -> str | None:
        return database.get_migration_from_legacy_version()
