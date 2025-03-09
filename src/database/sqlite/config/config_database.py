from logging import Logger
from pathlib import Path
from sqlite3 import OperationalError
from typing import Self, Any

from packaging.version import Version

from common.exception import PapiWebException
from common.logger import get_logger
from database.sqlite.config.config_migration import ConfigMigrationManager
from database.sqlite.config.config_store import StoredConfig
from database.sqlite.sqlite_database import SQLiteDatabase

logger: Logger = get_logger()


class ConfigDatabase(SQLiteDatabase):
    """
    The SQLite database class for Papi-web config.
    """

    # The current Papi-web version
    papi_web_version: Version = Version('2.4.24')

    # The file holding the configuration of the application.
    config_database_path: Path = Path('.scc')

    def __init__(
        self,
        write: bool = False,
        auto_upgrade: bool = True,
    ):
        self._version: Version | None = None
        self._auto_upgrade = auto_upgrade
        super().__init__(self.config_database_path, write)
        if not self.exists():
            try:
                self._create()
                with ConfigDatabase(write=True, auto_upgrade=False) as config_database:
                    config_database._version = ConfigMigrationManager.EMPTY_DATABASE_VERSION
                    ConfigMigrationManager().migrate(config_database, self.papi_web_version)
                    config_database._execute(
                        "INSERT INTO `info`(`version`, `force_edit`) VALUES(?, ?)",
                        (
                            f'{self.papi_web_version.major}.{self.papi_web_version.minor}.{self.papi_web_version.micro}',
                            True,
                        )
                    )
                    config_database.commit()
                logger.info('Database [%s] has been created.', self.file)
            except OperationalError as e:
                logger.warning('Database [%s] creation failed: %s', self.file, e.args)
                self.file.unlink(missing_ok=True)
                raise e

    def __enter__(self) -> Self:
        if not self.exists():
            raise PapiWebException(
                f'Database could not be opened because file [{self.file.resolve()}] does not exist.'
            )
        super().__enter__()
        if self._auto_upgrade and self.version < self.papi_web_version:
            if self.write:
                self.upgrade()
            else:
                with ConfigDatabase(write=True):
                    # reopening the database in r/w mode forces the upgrade
                    pass
                # force self.version() to reload the new version number
                self._version = None
        return self

    """
    ---------------------------------------------------------------------------------
    StoredConfig
    ---------------------------------------------------------------------------------
    """

    def _row_to_stored_config(self, row: dict[str, Any]) -> StoredConfig:
        """Convert a row to a StoredConfig record."""
        return StoredConfig(
            version=row['version'],
            force_edit=self.load_bool_from_database_field(row['force_edit']),
            log_level=row['log_level'],
            federation=row['federation'],
            launch_browser=self.load_bool_from_database_field(row['launch_browser']),
            locale=row['locale'],
        )

    def _get_stored_config(self) -> StoredConfig:
        """Gets all the information about the config and returns a corresponding StoredConfig record."""
        self._execute(
            'SELECT * FROM `info`',
            (),
        )
        return self._row_to_stored_config(self._fetchone())

    def load_stored_config(self) -> StoredConfig:
        return self._get_stored_config()

    @property
    def version(self) -> Version:
        """Returns the Papi-web version which created the database."""
        if self._version is None:
            self._version = Version(self._get_stored_config().version)
        return self._version

    def set_version(self, version: Version):
        """Sets the version field stored in the database to `version`."""
        self._execute(
            'UPDATE `info` SET `version` = ?',
            (f'{version.major}.{version.minor}.{version.micro}', ),
        )
        self._version = version

    def _upgrade(self):
        initial_version = self.version
        if ConfigMigrationManager().migrate(self, self.papi_web_version):
            logger.info(
                'Database %s has been upgraded from version %s to version %s.',
                self.file.name,
                initial_version,
                self.version,
            )

    def upgrade(self):
        """Upgrades the database version from the stored database version to the current Papi-web version.
        This may change the structure of the database."""
        papi_web_version: Version = self.papi_web_version
        if self.version > papi_web_version:
            raise PapiWebException(
                f'Your Papi-web version ({papi_web_version}) can not open database {self.file.name} (version '
                f'{self.version}), please upgrade.'
            )
        logger.info(f'Upgrading database {self.file.name}...')
        self._upgrade()

    def update_stored_config(self, stored_config: StoredConfig) -> StoredConfig:
        """Updates the config database with the information in the provided `stored_config`."""
        fields: list[str] = [
            'force_edit',
            'log_level',
            'launch_browser',
            'federation',
            'locale',
        ]
        params: tuple = (
            False,
            stored_config.log_level,
            stored_config.launch_browser,
            stored_config.federation,
            stored_config.locale,
        )
        field_sets = (f'`{f}` = ?' for f in fields)
        self._execute(f'UPDATE `info` SET {", ".join(field_sets)}', tuple(params))
        return self._get_stored_config()

