import re
from abc import abstractmethod, ABC
from functools import cached_property
from importlib import import_module
from logging import Logger
from pkgutil import iter_modules
from sqlite3 import OperationalError
from types import ModuleType

from packaging.version import Version

from common import PAPI_WEB_VERSION
from common.logger import print_interactive_error, get_logger
from database.sqlite.versioned_database import SQLiteVersionedDatabase

logger: Logger = get_logger()


class AbstractMigration(ABC):
    def __init__(self, database: SQLiteVersionedDatabase):
        self.database = database

    @abstractmethod
    def forward(self):
        pass

    def backward(self):
        raise NotImplementedError('Rollback not implemented for this migration')


class AbstractMigrationManager(ABC):
    EMPTY_DATABASE_VERSION: Version = Version('0.0.0')
    MIGRATION_CLASS_NAME: str = 'Migration'

    def __init__(self, cli_usage: bool = False):
        self._log_error = print_interactive_error if cli_usage else logger.error

    @property
    @abstractmethod
    def base_module(self) -> ModuleType:
        pass

    @property
    def migration_modules(self) -> list[str]:
        return [
            f'{self.base_module.__name__}.{module}'
            for module in self._migration_module_names
        ]

    @cached_property
    def migration_versions(self) -> list[Version]:
        return [
            self._module_name_to_version(module)
            for module in self._migration_module_names
        ]

    @property
    def _migration_module_names(self) -> list[str]:
        return [module for _, module, _ in iter_modules(self.base_module.__path__)]

    @property
    def first_migration_version(self) -> Version:
        return self._ordered_migration_versions[0]

    @property
    def last_migration_version(self) -> Version:
        return self._ordered_migration_versions[-1]

    @cached_property
    def _ordered_migration_versions(self) -> list[Version]:
        return sorted(self.migration_versions)

    @cached_property
    def _reverse_ordered_migration_versions(self) -> list[Version]:
        return sorted(self.migration_versions, reverse=True)

    @property
    def latest_version(self) -> Version:
        return PAPI_WEB_VERSION

    def get_version(self, database: SQLiteVersionedDatabase) -> Version:
        return database.version

    def set_version(self, database: SQLiteVersionedDatabase, version: Version):
        database.set_version(version)

    def migrate(
        self,
        database: SQLiteVersionedDatabase,
        target_version: Version | None = None,
        skip_commits: bool = False,
    ) -> bool:
        """Migrate *database* to the version *target_version*.
        *target_version* defaults to the latest version."""
        if target_version is None:
            target_version = self.latest_version
        current_version = self.get_version(database)
        if target_version == current_version:
            return True
        if (
            current_version != self.EMPTY_DATABASE_VERSION
            and current_version < self.first_migration_version
        ):
            self._log_error(
                'Database %s (%s) '
                'impossible to migrate: version is prior to the first '
                'database version (%s)',
                database.file.name,
                current_version,
                self.first_migration_version,
            )
            return False
        if (
            target_version != self.EMPTY_DATABASE_VERSION
            and target_version < self.first_migration_version
        ):
            self._log_error(
                'impossible to migrate to version [%s]: '
                'version is prior to the first database version [%s].',
                target_version.public,
                self.first_migration_version,
            )
            return False
        if current_version > self.latest_version:
            self._log_error(
                'Database [%s] impossible to migrate: version [%s] '
                'is after the latest version [%s] available '
                'in the current Papi-web version [%s].',
                database.file.name,
                current_version,
                self.latest_version.public,
                PAPI_WEB_VERSION.public,
            )
            return False
        if target_version > self.latest_version:
            self._log_error(
                'impossible to upgrade to version [%s]: '
                ' version is after the latest version '
                '[%s] available in this Papi-Web version [%s].',
                target_version.public,
                self.latest_version.public,
                PAPI_WEB_VERSION.public,
            )
            return False

        migration_status = (
            self._rollback(database, target_version, skip_commits)
            if current_version > target_version
            else self._upgrade(database, target_version, skip_commits)
        )
        if (
            migration_status
            and target_version != self.EMPTY_DATABASE_VERSION
            and self.get_version(database) != target_version
        ):
            self.set_version(database, target_version)
            if not skip_commits:
                database.commit()
        return migration_status

    def _upgrade(
        self,
        database: SQLiteVersionedDatabase,
        target_version: Version,
        skip_commits: bool,
    ) -> bool:
        while migration_version := self._next_migration_version(
            self.get_version(database), target_version
        ):
            migration_class = self._version_to_migration_class(migration_version)
            try:
                migration_class(database).forward()
                self.set_version(database, migration_version)
                if not skip_commits:
                    database.commit()
                logger.debug(
                    'Database %s has been upgraded to version %s.',
                    database.file.name,
                    migration_version,
                )
            except OperationalError as e:
                self._log_error(
                    'Database %s (%s) could not be upgraded to version %s: "%s"',
                    database.file.name,
                    self.get_version(database),
                    migration_version,
                    e,
                )
                return False
        return True

    def _rollback(
        self,
        database: SQLiteVersionedDatabase,
        target_version: Version,
        skip_commits: bool,
    ) -> bool:
        database_version = self.get_version(database)
        current_version = (
            database_version
            if database_version in self.migration_versions
            else self._previous_migration_version(database_version)
        )
        while current_version > target_version:
            migration_class = self._version_to_migration_class(current_version)
            previous_version = self._previous_migration_version(current_version)
            try:
                migration_class(database).backward()
                if previous_version != self.EMPTY_DATABASE_VERSION:
                    self.set_version(database, previous_version)
                if not skip_commits:
                    database.commit()
                current_version = previous_version
                logger.debug(
                    'Database %s has been downgraded to version %s.',
                    database.file.name,
                    previous_version,
                )
            except (OperationalError, NotImplementedError) as e:
                self._log_error(
                    'Database %s (%s) could not be downgraded to version %s: "%s"',
                    database.file.name,
                    self.get_version(database),
                    previous_version,
                    e,
                )
                return False
        return True

    def _next_migration_version(
        self, current_version: Version, max_version: Version
    ) -> Version | None:
        return next(
            (
                version
                for version in self._ordered_migration_versions
                if current_version < version <= max_version
            ),
            None,
        )

    def _previous_migration_version(self, current_version: Version) -> Version:
        return next(
            (
                version
                for version in self._reverse_ordered_migration_versions
                if version < current_version
            ),
            self.EMPTY_DATABASE_VERSION,
        )

    def _version_to_migration_class(self, version: Version) -> type[AbstractMigration]:
        return getattr(
            import_module(self._version_to_module(version)),
            self.MIGRATION_CLASS_NAME,
        )

    def _version_to_module(self, version: Version) -> str:
        return (
            f'{self.base_module.__name__}.'
            f'v{version.major}_{version.minor:02d}_{version.micro:02d}'
        )

    @staticmethod
    def _module_name_to_version(module_name: str) -> Version:
        if not re.match(r'^v\d+_\d+_\d+$', module_name):
            raise ValueError(
                f'Module name "{module_name}" does '
                'not match pattern "v{int}_{int}_{int}"'
            )
        return Version(module_name[1:].replace('_', '.'))
