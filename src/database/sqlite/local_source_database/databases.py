import atexit
import shutil
import tempfile
from time import time
from abc import ABC, abstractmethod
from datetime import datetime, timedelta
from math import floor
from pathlib import Path
import threading
from sqlite3 import connect, DatabaseError
from typing import override

from packaging.version import Version

from common import TEMPFILE_DIR, TMP_DIR, SharlyChessException
from common.i18n import _, set_locale
from common.logger import get_logger
from common.network import NetworkMonitor
from common.sharly_chess_config import SharlyChessConfig
from database.sqlite.event.event_store import StoredPlayer
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


class DatabaseLoaderProgress:
    """A utility class to display the progress of database operations."""

    def __init__(
        self,
        log_prefix: str,
        total_count: int,
        delay: int = 10,
    ):
        self.log_prefix = log_prefix
        self.total_count = total_count
        assert self.total_count > 0
        self.delay: int = delay
        assert self.delay > 0
        self.start_time: float = time()
        self.last_message_time: float = self.start_time
        self.last_message_count: int = 0

    def log(
        self,
        count: int,
    ):
        now: float = time()
        if now - self.last_message_time < self.delay:
            return
        remaining_count: int = self.total_count - count
        items_per_second: float = (
            (count - self.last_message_count) / (now - self.last_message_time)
            + count / (now - self.start_time)
        ) / 2
        eta: int = floor(remaining_count / items_per_second)
        logger.info(
            self.log_prefix + '%d%% ETA: %02d:%02d',
            floor(count / self.total_count * 100),
            eta // 60,
            eta % 60,
        )
        self.last_message_count = count
        self.last_message_time = now


class LocalSourceDatabase(SQLiteDatabase, IdentifiableEntity, ABC):
    """Represents the local databases used as data sources.
    These databases are downloaded and stored locally as SQLite databases.
    They can be periodically updated, or notify the user when outdated."""

    UPDATE_TIMEOUT = 10

    is_updating: bool = False
    update_status: bool | None = None
    max_update_time: datetime | None = None

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
        if self.max_update_time and datetime.now() > self.max_update_time:
            logger.error(self.log_prefix + 'Update failed (timeout).')
            self.stop_update(False)

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
    def _schema_file_path(self) -> Path:
        """Path to the SQL file describing the schema of the database."""
        # Default implementation - subclasses should override this if they don't use external generation
        raise NotImplementedError(
            'Subclass must implement _schema_file_path if _use_external_generator returns False'
        )

    @property
    @abstractmethod
    def _source_file_name(self) -> str:
        """Name of the file containing the sources."""

    @abstractmethod
    def _download_source_file(self, source_file_dir: Path) -> bool:
        """Download the source file to *source_file_dir*.
        Returns True if it succeeds and False if it fails."""

    def _use_external_generator(self) -> bool:
        """Determines of the database in generated by an external tool.
        If not, the database structure will be created then populated."""
        # Default implementation - subclasses can override this
        return False

    def _generate_from_source_file(
        self, source_file_path: Path, tmp_file: Path
    ) -> bool:
        """Creates the database at *tmp_file* from *source_file_path*."""
        # Default implementation - subclasses should override this if they use external generation
        raise NotImplementedError(
            'Subclass must implement _generate_from_source_file if _use_external_generator returns True'
        )

    def _populate_from_source_file(
        self, source_file_path: Path, database: SQLiteDatabase
    ) -> bool:
        """Populate the database from the source file at *source_file_path*.
        Database matches schema described at *schema_file_path*."""
        # Default implementation - subclasses should override this if they don't use external generation
        raise NotImplementedError(
            'Subclass must implement _populate_from_source_file if _use_external_generator returns False'
        )

    def _post_generation(self, tmp_file: Path) -> bool:
        """Perform post operations after the database has been populated."""
        # Default implementation - subclasses should override this if needed
        return True

    @classmethod
    @abstractmethod
    def _create_indexes(cls, database: SQLiteDatabase):
        """Create the indexes for the databases."""

    @property
    def outdate_delay(self) -> OutdatedDelay:
        from database.sqlite.local_source_database import OutdatedDelayManager

        return OutdatedDelayManager().get_object(
            self.stored_source_database.outdate_delay
        )

    @property
    def outdate_action(self) -> OutdatedAction:
        from database.sqlite.local_source_database import OutdatedActionManager

        return OutdatedActionManager().get_object(
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
        return f'Database [{self.name}] - '

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
                ['ws'],
            )
            channels_plugin.publish(
                {
                    'event': f'database-status-updated|{cls.static_id()}',
                    'data': '',
                },
                ['ws'],
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

    def stop_update(self, status: bool) -> None:
        cls = self.__class__
        cls.is_updating = False
        cls.update_status = status
        cls.max_update_time = None
        logger.debug(self.log_prefix + f'Update stopped with status {int(status)}')
        # Only push the SSE event if the server is connected, otherwise we enter a loop where the client gets the SSE event,
        # re-requests the updated badge, fails dues to the lack of internet, and so on.
        if NetworkMonitor.connected():
            self.publish_database_status_updated()

    @override
    def delete(self):
        super().delete()
        self.stored_source_database = self.default_stored_database
        with ConfigDatabase(write=True) as database:
            database.update_stored_local_source_database(self.default_stored_database)
        self.publish_database_status_updated()

    def check(self) -> bool:
        """Checks if the database exists and is up-to-date.
        If it exists and is outdated, execute the 'on_outdated' process.
        Returns True if the database is available after the call."""
        if not self.exists():
            if self.updated_at:
                logger.error(
                    'Database [%s] unexpectedly not found at path [%s].',
                    self.name,
                    self.file,
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

        # Set the locale (called in a new thread)
        set_locale(SharlyChessConfig().locale)

        self.__class__.is_updating = True
        self.__class__.max_update_time = datetime.now() + timedelta(
            minutes=self.UPDATE_TIMEOUT
        )

        if not NetworkMonitor.connected():
            logger.warning(self.log_prefix + 'Not connected, impossible to update.')
            return self.stop_update(False)
        self.publish_database_status_updated()
        with tempfile.TemporaryDirectory(dir=TEMPFILE_DIR) as tmpdir:
            tmp_dir: Path = Path(tmpdir)
            logger.info(self.log_prefix + 'Downloading source file…')
            if not self._download_source_file(tmp_dir):
                return self.stop_update(False)
            if self.stop_event.is_set():
                return self.stop_update(False)
            logger.info(self.log_prefix + 'Storing data…')
            tmp_file = tmp_dir / 'db.tmp'
            new_database = SQLiteDatabase(tmp_file, write=True)
            source_file_path: Path = tmp_dir / self._source_file_name

            try:
                success: bool
                if self._use_external_generator():
                    success = self._generate_from_source_file(
                        source_file_path, tmp_file
                    )
                else:
                    with open(self._schema_file_path, encoding='utf-8') as file:
                        new_database._create(file.read())
                    success = self._populate_from_source_file(
                        source_file_path, new_database
                    )
                if not success:
                    return self.stop_update(False)
            except (DatabaseError, SharlyChessException) as ex:
                logger.error(
                    self.log_prefix + 'Error while creating the database: %s.', ex
                )
                return self.stop_update(False)

            # Validate that the database file is actually a SQLite database before creating indexes
            try:
                # Test if we can open the database
                test_conn = connect(tmp_file)
                test_conn.execute('SELECT 1')  # Simple test query
                test_conn.close()
            except DatabaseError as e:
                logger.error(
                    self.log_prefix
                    + 'Generated database file is not a valid SQLite database: %s.',
                    e,
                )
                self.file.unlink(missing_ok=True)
                return self.stop_update(False)

            try:
                if not self._post_generation(tmp_file):
                    return self.stop_update(False)
            except (DatabaseError, SharlyChessException) as e:
                logger.error(
                    self.log_prefix + 'Could not perform post operations: %s.',
                    e,
                )
                return self.stop_update(False)

            try:
                logger.debug(self.log_prefix + 'Creating indices…')
                with SQLiteDatabase(tmp_file, True) as database:
                    self._create_indexes(database)
            except DatabaseError as e:
                logger.error(
                    self.log_prefix + 'Could not create database indices: %s.',
                    e,
                )
                return self.stop_update(False)

            try:
                # Copy the new database to its proper location
                self.file.unlink(missing_ok=True)
                shutil.copy(tmp_file, self.file)
                logger.debug(self.log_prefix + f'file copied to [{self.file}].')
            except OSError as e:
                logger.error(
                    self.log_prefix
                    + 'Could not copy generated database file to [%s]: %s.',
                    self.file,
                    e,
                )
                return self.stop_update(False)

        self.stored_source_database.updated_at = time()
        with ConfigDatabase(write=True) as database:
            database.update_stored_local_source_database(self.stored_source_database)
        logger.info(self.log_prefix + 'Database successfully updated.')
        return self.stop_update(True)


class LocalSourcePlayerDatabase(LocalSourceDatabase):
    """Represents a local database that provides player search functionality."""

    @abstractmethod
    def search_player(
        self,
        string: str,
        federation: str,
        page: int = 0,
        limit: int | None = None,
    ) -> list[StoredPlayer]:
        """Search a player in the database.
        Returns maximum *limit* results (no limit if *limit* is None)."""
