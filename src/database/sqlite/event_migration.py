from functools import cached_property
from importlib import import_module
from pkgutil import iter_modules
import re
from abc import abstractmethod
from logging import Logger

from packaging.version import Version

from common.exception import PapiWebException
from common.logger import get_logger
from database.migrations import events
from database.sqlite.event_database import EventDatabase

logger: Logger = get_logger()


class AbstractEventMigration(EventDatabase):
    @abstractmethod
    def forward(self):
        pass


class EventMigrationManager:
    EMPTY_DATABASE_VERSION: Version = Version('0.0.0')
    MIGRATION_CLASS_NAME: str = 'EventMigration'

    @property
    def migration_modules(self) -> list[str]:
        return [
            f'{events.__name__}.{module}'
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
        return sorted([
            self._module_name_to_version(module)
            for module in self._migration_module_names
        ])

    def migrate(
            self,
            event_database: EventDatabase,
            target_version: Version,
            skip_commits: bool = False,
    ):
        if (
            event_database.version != self.EMPTY_DATABASE_VERSION
            and event_database.version < self.first_migration_version
        ):
            logger.error(
                'Database %s (%s) impossible to upgrade: version '
                'is prior to the first upgradable version (%s)',
                event_database.file.name,
                event_database.version,
                self.first_migration_version,
            )
            return
        if event_database.version > target_version:
            raise NotImplementedError('Migrations rollback not implemented')
        while migration_version := self._next_migration_version(
            event_database.version, target_version
        ):
            migration_class = self._version_to_migration_class(migration_version)
            migration_class.forward(event_database)
            event_database.set_version(migration_version)
            if not skip_commits:
                event_database.commit()
            if event_database.version == migration_version:
                logger.debug(
                    'Database %s has been upgraded to version %s.',
                    event_database.file.name,
                    migration_version,
                )
            else:
                raise PapiWebException(
                    f'Database {event_database.file.name} ({event_database.version})'
                    f' could not be upgraded to version {migration_version}.'
                )

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
