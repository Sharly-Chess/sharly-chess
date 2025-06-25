import atexit
import time
from abc import ABC, abstractmethod
from datetime import datetime
from pathlib import Path
import threading
from sqlite3 import OperationalError, IntegrityError
from typing import override

from packaging.version import Version

from common import TMP_DIR
from common.i18n import _
from common.logger import get_logger
from common.network import NetworkMonitor
from common.sharly_chess_config import SharlyChessConfig
from data.player import Player
from database.sqlite.local_source_database.actions import (
    OutdatedAction,
    NotifOutdatedAction,
)
from database.sqlite.local_source_database.delays import (
    OutdatedDelay,
    DisabledOutdatedDelay,
)
from utils.entity import IdentifiableEntity
from database.sqlite.config.config_database import ConfigDatabase
from database.sqlite.config.config_store import StoredLocalSourceDatabase
from database.sqlite.sqlite_database import SQLiteDatabase
from web.channels import channels_plugin

logger = get_logger()


class LocalSourceDatabase(SQLiteDatabase, IdentifiableEntity, ABC):
    """Represents the local databases used as data sources.
    These databases are downloaded and stored locally as SQLite databases.
    They can be periodically updated, or notify the user when outdated."""

    is_updating: bool = False
    update_status: bool | None = None

    def __init__(self, write: bool = False):
        super().__init__(self.file_path(), write)
        self.stop_event = threading.Event()
        self.outdated_warning: bool = False
        self.stored_source_database: StoredLocalSourceDatabase

        with ConfigDatabase() as database:
            stored_source_database = database.load_stored_local_source_database(self.id)
        if stored_source_database:
            self.stored_source_database = stored_source_database
        else:
            self.file.unlink(missing_ok=True)
            with ConfigDatabase(write=True) as database:
                self.stored_source_database = self.default_stored_database
                database.insert_stored_local_source_database(
                    self.stored_source_database
                )
                database.commit()

    @staticmethod
    def _dir() -> Path:
        """Path to the SQlite file."""
        return TMP_DIR

    @classmethod
    def file_path(cls) -> Path:
        return (
            cls._dir()
            / f'{cls.static_id()}.{SharlyChessConfig.federation_database_ext}'
        )

    @property
    @abstractmethod
    def min_recovery_version(self) -> Version:
        """The minimal app version for which the database can be recovered."""

    @property
    @abstractmethod
    def _schema_file_path(self) -> Path:
        """Path to the SQL file describing the schema of the database."""

    @property
    @abstractmethod
    def _source_file_path(self) -> Path:
        """Path of the file containing the sources."""

    @abstractmethod
    def _download_source_file(self) -> bool:
        """Download the source file to *source_file_path*.
        Returns True if it succeeds and False if it fails."""

    @abstractmethod
    def _populate_from_source_file(self, database: SQLiteDatabase) -> bool:
        """Populate the database from the source file at *source_file_path*.
        Database matches schema described at *schema_file_path*."""

    @abstractmethod
    def _create_indexes(self):
        """Create the indexes for the databases."""

    @abstractmethod
    def search_player(
        self,
        string: str,
        limit: int | None = None,
    ) -> list[Player]:
        """Search a player in the database.
        Returns maximum *limit* results (no limit if *limit* is None)."""

    @property
    def outdate_delay(self) -> OutdatedDelay:
        from database.sqlite.local_source_database import OutdatedDelayManager

        return OutdatedDelayManager.get_object(
            self.stored_source_database.outdate_delay
        )

    @property
    def outdate_action(self) -> OutdatedAction:
        from database.sqlite.local_source_database import OutdatedActionManager

        return OutdatedActionManager.get_object(
            self.stored_source_database.outdate_action
        )

    @property
    def updated_at_timestamp(self) -> float | None:
        return self.stored_source_database.updated_at

    @property
    def updated_at(self) -> datetime | None:
        if self.updated_at_timestamp:
            return datetime.fromtimestamp(self.updated_at_timestamp)
        return None

    @property
    def is_outdated(self) -> bool:
        if not self.updated_at:
            return False
        return self.outdate_delay.is_expired(self.updated_at)

    @property
    def default_stored_database(self) -> StoredLocalSourceDatabase:
        return StoredLocalSourceDatabase(
            name=self.id,
            outdate_delay=DisabledOutdatedDelay.static_id(),
            outdate_action=NotifOutdatedAction.static_id(),
        )

    @property
    def log_prefix(self) -> str:
        return _('Database [{database}] - ').format(database=self.name)

    @classmethod
    def publish_database_status_updated(cls):
        # The auto-update can start before the channels plugin is initialized,
        # so we check if it exists before trying to publish.
        if channels_plugin and channels_plugin._pub_queue is not None:
            channels_plugin.publish(
                {
                    'event': 'database-status-updated',
                    'data': '',
                },
                ['sse'],
            )
            channels_plugin.publish(
                {
                    'event': f'database-status-updated/{cls.static_id()}',
                    'data': '',
                },
                ['sse'],
            )

    def on_outdated(self):
        self.outdate_action.on_outdated(self)
        self.publish_database_status_updated()

    @property
    def updated_at_str(self) -> str:
        if self.is_updating:
            return _('Ongoing')
        if not self.updated_at:
            return ''

        days_since_update = (datetime.now() - self.updated_at).days
        match days_since_update:
            case 0:
                return _('Today')
            case 1:
                return _('Yesterday')
            case _:
                return _('{days} days ago').format(days=days_since_update)

    @classmethod
    def stop_update(cls, status: bool) -> None:
        cls.is_updating = False
        cls.update_status = status
        cls.publish_database_status_updated()

    @override
    def delete(self):
        super().delete()
        self.stored_source_database = self.default_stored_database
        with ConfigDatabase(write=True) as database:
            database.update_stored_local_source_database(self.default_stored_database)
            database.commit()
        self.publish_database_status_updated()

    def check(self) -> bool:
        """Checks if the database exists and is up-to-date.
        If it exists and is outdated, execute the 'on_outdated' process.
        Returns True if the database is available after the call."""
        if not self.exists():
            if self.updated_at:
                logger.error(
                    _(
                        'Database [{database}] unexpectedly not found at path [{path}].'
                    ).format(database=self.name, path=self.file)
                )
                self.delete()
            return False
        if self.is_outdated:
            self.outdate_action.on_outdated(self)
        return True

    def update(self):
        """Start a thread updating the database."""
        update_thread = threading.Thread(target=self._update, daemon=True)
        update_thread.start()
        atexit.register(self._stop_background_thread, update_thread)

    def _stop_background_thread(self, thread: threading.Thread):
        self.stop_event.set()
        thread.join()

    def _update(self):
        """Update the source database:
        1. Download the source file
        2. Create a temp database
        3. Populate the temp database from the source file
        4. Copy the temp file to the correct file location"""
        self.__class__.is_updating = True
        self.publish_database_status_updated()
        if not NetworkMonitor.connected():
            logger.warning(self.log_prefix + _('Not connected, impossible to update.'))
            return self.stop_update(False)
        logger.info(self.log_prefix + _('Downloading source file…'))
        if not self._download_source_file():
            return self.stop_update(False)
        if self.stop_event.is_set():
            return self.stop_update(False)
        logger.info(self.log_prefix + _('Storing data…'))
        tmp_file = self.file.with_suffix('.tmp')
        tmp_file.unlink(missing_ok=True)
        new_database = SQLiteDatabase(tmp_file, write=True)

        try:
            with open(self._schema_file_path, encoding='utf-8') as file:
                new_database._create(file.read())
            if not self._populate_from_source_file(new_database):
                tmp_file.unlink(missing_ok=True)
                return self.stop_update(False)
        except (OperationalError, IntegrityError) as ex:
            logger.error(
                self.log_prefix
                + _('Error while creating the database: {error}.').format(error=ex)
            )
            tmp_file.unlink(missing_ok=True)
            return self.stop_update(False)
        finally:
            self._source_file_path.unlink(missing_ok=True)

        # Copy the new database to its proper location
        self.acquire_lock()
        self.file.unlink(missing_ok=True)
        tmp_file.rename(self.file)
        self.release_lock()
        self._create_indexes()

        self.stored_source_database.updated_at = time.time()
        with ConfigDatabase(write=True) as database:
            database.update_stored_local_source_database(self.stored_source_database)
            database.commit()
        logger.info(self.log_prefix + _('Database successfully updated.'))
        return self.stop_update(True)
