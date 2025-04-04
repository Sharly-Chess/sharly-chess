import atexit
import time
from abc import ABC, abstractmethod
from datetime import datetime, timedelta, date
from pathlib import Path
import threading
from sqlite3 import OperationalError, IntegrityError
from typing import override

from common import TMP_DIR, get_logger
from common.i18n import _
from common.network import NetworkMonitor
from common.papi_web_config import PapiWebConfig
from utils.entity import IdentifiableEntity
from database.sqlite.config.config_database import ConfigDatabase
from database.sqlite.config.config_store import StoredLocalSourceDatabase
from database.sqlite.sqlite_database import SQLiteDatabase


logger = get_logger()


# ---------------------------------------------------------------------------------
# Outdate delay
# ---------------------------------------------------------------------------------


class OutdateDelay(IdentifiableEntity, ABC):
    """Delay according to which a database becomes outdated."""

    @abstractmethod
    def is_expired(self, start_time: datetime) -> bool:
        """Determines if the delay since *start_time* is expired."""


class DisabledOutdateDelay(OutdateDelay):
    @staticmethod
    def static_id() -> str:
        return 'disabled'

    @staticmethod
    def static_name() -> str:
        return _('Disabled')

    def is_expired(self, start_time: datetime) -> bool:
        return False


class DayCountOutdateDelay(OutdateDelay, ABC):
    """Represents the delays that expire after a specific amount of days."""

    @property
    @abstractmethod
    def days_expired(self) -> int:
        """Number of days for the delay to expire."""

    def is_expired(self, start_time: datetime) -> bool:
        return datetime.now() > start_time + timedelta(days=self.days_expired)


class DailyOutdateDelay(DayCountOutdateDelay):
    @staticmethod
    def static_id() -> str:
        return 'daily'

    @staticmethod
    def static_name() -> str:
        return _('Daily')

    @property
    def days_expired(self) -> int:
        return 1


class Days2OutdateDelay(DayCountOutdateDelay):
    @staticmethod
    def static_id() -> str:
        return '2days'

    @staticmethod
    def static_name() -> str:
        return _('{days} days').format(days=2)

    @property
    def days_expired(self) -> int:
        return 2


class Days3OutdateDelay(DayCountOutdateDelay):
    @staticmethod
    def static_id() -> str:
        return '3days'

    @staticmethod
    def static_name() -> str:
        return _('{days} days').format(days=3)

    @property
    def days_expired(self) -> int:
        return 3


class WeeklyOutdateDelay(DayCountOutdateDelay):
    @staticmethod
    def static_id() -> str:
        return 'weekly'

    @staticmethod
    def static_name() -> str:
        return _('Weekly')

    @property
    def days_expired(self) -> int:
        return 7


class MonthFirstDayOutdateDelay(OutdateDelay):
    @staticmethod
    def static_id() -> str:
        return 'month_1st'

    @staticmethod
    def static_name() -> str:
        return _('1st day of the month')

    def is_expired(self, start_time: datetime) -> bool:
        now = datetime.now()
        first_day = date(now.year, now.month, 1)
        return start_time < datetime.combine(first_day, datetime.min.time())


# ---------------------------------------------------------------------------------
# Outdate Actions
# ---------------------------------------------------------------------------------

class OutdateAction(IdentifiableEntity, ABC):
    @abstractmethod
    def on_outdated(self, database: 'LocalSourceDatabase'):
        """Action to execute when a database is outdated."""


class NotifOutdateAction(OutdateAction):
    @staticmethod
    def static_id() -> str:
        return 'notif'

    @staticmethod
    def static_name() -> str:
        return _('Notification')

    def on_outdated(self, database: 'LocalSourceDatabase'):
        database.outdated_warning = True


class AutoUpdateOutdateAction(OutdateAction):
    @staticmethod
    def static_id() -> str:
        return 'auto_update'

    @staticmethod
    def static_name() -> str:
        return _('Auto-update')

    def on_outdated(self, database: 'LocalSourceDatabase'):
        if not database.is_updating:
            database.update()


# ---------------------------------------------------------------------------------
# Offline Source Database
# ---------------------------------------------------------------------------------


class LocalSourceDatabase(SQLiteDatabase, IdentifiableEntity, ABC):
    """Represents the databases used as data sources for an offline usage."""

    is_updating: bool = False
    update_status: bool | None = None

    def __init__(self, write: bool = False):
        super().__init__(
            TMP_DIR / f'{self.id}.{PapiWebConfig.federation_database_ext}',
            write,
        )
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

    @property
    def outdate_delay(self) -> OutdateDelay:
        from data.entity_managers import OutdateDelayManager

        return OutdateDelayManager.get_object(self.stored_source_database.outdate_delay)

    @property
    def outdate_action(self) -> OutdateAction:
        from data.entity_managers import OutdateActionManager

        return OutdateActionManager.get_object(
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
            outdate_delay=DisabledOutdateDelay.static_id(),
            outdate_action=NotifOutdateAction.static_id(),
        )

    @property
    def log_prefix(self) -> str:
        return _('Database [{database}] - ').format(database=self.name)

    def on_outdated(self):
        self.outdate_action.on_outdated(self)

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

    @override
    def delete(self):
        super().delete()
        self.stored_source_database = self.default_stored_database
        with ConfigDatabase(write=True) as database:
            database.update_stored_local_source_database(self.default_stored_database)
            database.commit()

    def check(self):
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
        if not NetworkMonitor.connected():
            logger.warning(self.log_prefix + _('Not connected, impossible to update.'))
            return self.stop_update(False)
        logger.info(self.log_prefix + _('Downloading source file...'))
        if not self._download_source_file():
            return self.stop_update(False)
        if self.stop_event.is_set():
            return self.stop_update(False)
        logger.info(self.log_prefix + _('Storing data...'))
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
