from functools import cached_property
from importlib import import_module
from pkgutil import iter_modules
import re
from abc import abstractmethod
from logging import Logger
from sqlite3 import OperationalError

from packaging.version import Version

from common.logger import get_logger, print_interactive_error
from database.migrations import events
from database.sqlite.event_database import EventDatabase

logger: Logger = get_logger()


class AbstractEventMigration(EventDatabase):
    @abstractmethod
    def forward(self):
        pass

    def backward(self):
        raise NotImplementedError(
            "Rollback not implemented for this migration"
        )


class EventMigrationManager:
    EMPTY_DATABASE_VERSION: Version = Version('0.0.0')
    MIGRATION_CLASS_NAME: str = 'EventMigration'

    def __init__(self, cli_usage: bool = False):
        self._log_error = (
            print_interactive_error if cli_usage else logger.error
        )

    @property
    def migration_modules(self) -> list[str]:
        return [
            f'{events.__name__}.{module}'
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
        return [module for _, module, _ in iter_modules(events.__path__)]

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

    def migrate(
        self,
        database: EventDatabase,
        target_version: Version,
        skip_commits: bool = False,
    ) -> bool:
        if (
            database.version != self.EMPTY_DATABASE_VERSION
            and database.version < self.first_migration_version
        ):
            self._log_error(
                f'Database %{database.file.name} ({database.version}) '
                'impossible to upgrade: version is prior to the first '
                f'upgradable version ({self.first_migration_version})'
            )
            return False
        if database.version > target_version:
            return self._rollback(database, target_version, skip_commits)
        else:
            return self._upgrade(database, target_version, skip_commits)

    def _upgrade(
        self,
        database: EventDatabase,
        target_version: Version,
        skip_commits: bool,
    ) -> bool:
        while migration_version := self._next_migration_version(
            database.version, target_version
        ):
            migration_class = self._version_to_migration_class(
                migration_version
            )
            try:
                migration_class.forward(database)
                database.set_version(migration_version)
                if not skip_commits:
                    database.commit()
                logger.debug(
                    'Database %s has been upgraded to version %s.',
                    database.file.name,
                    migration_version,
                )
            except OperationalError as e:
                self._log_error(
                    f'Database {database.file.name} '
                    f'({database.version}) could not be upgraded '
                    f'to version {migration_version}: "{e}"'
                )
                return False
        return True

    def _rollback(
        self,
        database: EventDatabase,
        target_version: Version,
        skip_commits: bool,
    ) -> bool:
        while database.version > target_version:
            if database.version not in self.migration_versions:
                self._log_error(
                    'No migration for current database version, '
                    'impossible to rollback.'
                )
                return False

            migration_class = self._version_to_migration_class(
                database.version
            )
            previous_version = self._previous_migration_version(
                database.version
            )
            try:
                migration_class.backward(database)
                database.set_version(previous_version)
                if not skip_commits:
                    database.commit()
                logger.debug(
                    'Database %s has been downgraded to version %s.',
                    database.file.name,
                    previous_version,
                )
            except (OperationalError, NotImplementedError) as e:
                self._log_error(
                    f'Database {database.file.name} '
                    f'({database.version}) could not be downgraded '
                    f'to version {previous_version}: "{e}"'
                )
                return False
        return True

    def _next_migration_version(
        self, current_version: Version, max_version: Version
    ) -> Version | None:
        return next(
            (
                version for version in self._ordered_migration_versions
                if current_version < version <= max_version
            ),
            None,
        )

    def _previous_migration_version(
        self, current_version: Version
    ) -> Version:
        return next(
            (
                version for version in
                self._reverse_ordered_migration_versions
                if version < current_version
            ),
            self.EMPTY_DATABASE_VERSION,
        )

    def _version_to_migration_class(
        self, version: Version
    ) -> type[AbstractEventMigration]:
        return getattr(
            import_module(self._version_to_module(version)),
            self.MIGRATION_CLASS_NAME,
        )

    @staticmethod
    def _version_to_module(version: Version) -> str:
        return (
            f'{events.__name__}.'
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
