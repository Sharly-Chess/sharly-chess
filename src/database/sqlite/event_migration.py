import importlib
from abc import abstractmethod
from logging import Logger

from packaging.version import Version

from common.exception import PapiWebException
from common.logger import get_logger
from database.sqlite.event_database import EventDatabase

logger: Logger = get_logger()


class AbstractEventMigration(EventDatabase):
    @abstractmethod
    def forward(self):
        pass


class EventMigrationManager:
    FIRST_UPGRADABLE_VERSION: Version = Version('2.4.0')
    MIGRATION_BASE_MODULE_PATH: list[str] = ['database', 'migrations', 'events']
    MIGRATION_MODULES: dict[Version, str] = {
        Version('2.4.2'): 'migration_001',
        Version('2.4.4'): 'migration_002',
        Version('2.4.5'): 'migration_003',
        Version('2.4.8'): 'migration_004',
        Version('2.4.12'): 'migration_005',
        Version('2.4.13'): 'migration_006',
        Version('2.4.16'): 'migration_007',
        Version('2.4.20'): 'migration_008',
        Version('2.4.21'): 'migration_009',
        Version('2.4.22'): 'migration_010',
    }
    MIGRATION_CLASS_NAME: str = 'EventMigration'

    def migrate(self, event_database: EventDatabase, target_version: Version):
        if event_database.version < self.FIRST_UPGRADABLE_VERSION:
            logger.error(
                'Database %s impossible to upgrade: version %s '
                'is prior to the first upgradable version %s',
                event_database.file.name,
                event_database.version,
                self.FIRST_UPGRADABLE_VERSION
            )
            return
        if event_database.version > target_version:
            raise NotImplementedError('Backwards compatibility not implemented')

        while migration_version := self._next_migration_version(
            event_database.version, target_version
        ):
            migration_class = self._version_to_migration_class(migration_version)
            migration_class.forward(event_database)
            event_database.set_version(migration_version)
            event_database.commit()
            if event_database.version == migration_version:
                logger.debug(
                    'Database %s has been upgraded to version %s.',
                    event_database.file.name,
                    target_version,
                )
            else:
                raise PapiWebException(
                    f'Database {event_database.file.name} ({event_database.version})'
                    f' could not be upgraded to version {target_version}.'
                )

    def _next_migration_version(
        self, current_version: Version, max_version: Version
    ) -> Version | None:
        return next(
            (
                version for version in sorted(self.MIGRATION_MODULES.keys())
                if current_version < version <= max_version
            ),
            None,
        )

    def _version_to_migration_class(
        self, version: Version
    ) -> type[AbstractEventMigration]:
        return getattr(
            importlib.import_module(
                '.'.join(
                    self.MIGRATION_BASE_MODULE_PATH + [self.MIGRATION_MODULES[version]]
                ),
            ),
            self.MIGRATION_CLASS_NAME,
        )
