import re
import shutil
import time
from contextlib import suppress
from dataclasses import dataclass
from functools import cached_property
from logging import Logger
from operator import attrgetter
from pathlib import Path

from litestar.contrib.htmx.request import HTMXRequest
from packaging.version import Version

from common import (
    format_timestamp_date_time,
    unicode_normalize,
    PAPI_WEB_VERSION,
    EVENTS_DIR,
)
from common.exception import PapiWebException
from common.papi_web_config import PapiWebConfig
from common.logger import get_logger
from data.event import Event
from database.sqlite.event.event_database import EventDatabase
from database.sqlite.event.event_store import StoredEvent

logger: Logger = get_logger()


class EventLoader:
    _valid_event_ids: list[str] = []
    _invalid_uniq_ids: list[str] = []

    def __init__(self):
        self._loaded_stored_events_by_id: dict[str, StoredEvent] = {}
        self._loaded_events_by_id: dict[str, Event] = {}

    @classmethod
    def get(cls, request: HTMXRequest | None):
        if not request:
            return cls()
        event_loader: EventLoader = request.state.get('event_loader', None)
        if not event_loader:
            request.state['event_loader'] = cls()
        return request.state['event_loader']

    def clear_cache(self, event_uniq_id: str | None = None):
        """If `event_uniq_id` is provided, clears the load cache regarding the
        given event."""
        if event_uniq_id:
            with suppress(KeyError):
                del self._loaded_stored_events_by_id[event_uniq_id]
            with suppress(KeyError):
                del self._loaded_events_by_id[event_uniq_id]
            with suppress(ValueError):
                self.__class__._valid_event_ids.remove(event_uniq_id)
        with suppress(AttributeError):
            del self.event_uniq_ids
        with suppress(AttributeError):
            del self.stored_events_by_id
        with suppress(AttributeError):
            del self.stored_events_sorted_by_name
        with suppress(AttributeError):
            del self.events_by_id
        with suppress(AttributeError):
            del self.events_sorted_by_name

    def load_stored_event(self, uniq_id: str) -> StoredEvent:
        try:
            return self._loaded_stored_events_by_id[uniq_id]
        except KeyError:
            with EventDatabase(uniq_id) as event_database:
                self._loaded_stored_events_by_id[uniq_id] = (
                    event_database.load_stored_event()
                )
            return self._loaded_stored_events_by_id[uniq_id]

    @classmethod
    def load_event_ids(cls, uniq_id: str | None = None):
        known_event_ids = cls._valid_event_ids + cls._invalid_uniq_ids
        for event_id in cls.all_event_ids():
            if (
                event_id in known_event_ids or
                (uniq_id and event_id != event_id)
            ):
                continue
            try:
                with EventDatabase(event_id) as database:
                    status = database.check_status()
                if not status:
                    with EventDatabase(event_id, True) as database:
                        database.upgrade()
                cls._valid_event_ids.append(event_id)
            except PapiWebException as e:
                logger.error(e)
                cls._invalid_uniq_ids.append(event_id)

    @cached_property
    def event_uniq_ids(self) -> list[str]:
        self.load_event_ids()
        return self._valid_event_ids

    @classmethod
    def all_event_ids(cls) -> list[str]:
        return [
            file.stem
            for file in EVENTS_DIR.glob(f'*.{PapiWebConfig.event_database_ext}')
        ]

    def get_unused_event_uniq_id(self, base_uniq_id: str) -> str:
        """Returns the first unused event uniq_id looking like base_uniq_id:
        base_uniq_id, or base_uniq_id-2, or base_uniq_id-n+1..."""
        index: int
        uniq_id: str
        base_uniq_id = unicode_normalize(base_uniq_id)
        if matches := re.match(r'^(.*)-(\d+)$', base_uniq_id):
            base_uniq_id = matches.group(1)
            index = int(matches.group(2))
            uniq_id = f'{base_uniq_id}-{index + 1}'
        else:
            index = 1
            uniq_id = base_uniq_id
        while uniq_id in self.all_event_ids():
            index += 1
            uniq_id = f'{base_uniq_id}-{index}'
        return uniq_id

    def get_unused_event_name(self, base_name: str) -> str:
        """Returns the first unused event name looking like base_name:
        base_name, or base_name (2), or base_name (n+1)..."""
        index: int
        name: str
        if matches := re.match(r'^(.*) \((\d+)\)$', base_name):
            base_name = matches.group(1)
            index = int(matches.group(2))
            name = f'{base_name} ({index + 1})'
        else:
            index = 1
            name = base_name
        event_names: list[str] = [event.name for event in self.events_by_id.values()]
        while name in event_names:
            index += 1
            name = f'{base_name} ({index})'
        return name

    @cached_property
    def stored_events_by_id(self) -> dict[str, StoredEvent]:
        return {
            uniq_id: self.load_stored_event(uniq_id) for uniq_id in self.event_uniq_ids
        }

    @cached_property
    def stored_events_sorted_by_name(self) -> list[StoredEvent]:
        return sorted(self.stored_events_by_id.values(), key=lambda event: event.name)

    def _load_event(self, uniq_id: str, reload: bool) -> Event:
        if reload:
            self.clear_cache(uniq_id)
        try:
            return self._loaded_events_by_id[uniq_id]
        except KeyError:
            self.load_event_ids(uniq_id)
            stored_event: StoredEvent = self.load_stored_event(uniq_id)
            self._loaded_events_by_id[uniq_id] = Event(stored_event)
            return self._loaded_events_by_id[uniq_id]

    def load_event(self, uniq_id: str) -> Event:
        return self._load_event(uniq_id, reload=False)

    def reload_event(self, uniq_id: str) -> Event:
        return self._load_event(uniq_id, reload=True)

    @cached_property
    def events_by_id(self) -> dict[str, Event]:
        events_by_id: dict[str, Event] = {}
        for uniq_id in self.event_uniq_ids:
            try:
                events_by_id[uniq_id] = self.load_event(uniq_id)
            except PapiWebException as pwe:
                logger.error(pwe)
        return events_by_id

    @cached_property
    def events_sorted_by_name(self) -> list[Event]:
        return sorted(self.events_by_id.values(), key=lambda event: event.name)

    @cached_property
    def events_with_tournaments_sorted_by_name(self) -> list[Event]:
        return [
            event for event in self.events_sorted_by_name if event.tournaments_by_id
        ]

    @cached_property
    def passed_events(self) -> list[Event]:
        return sorted(
            [event for event in self.events_by_id.values() if event.stop < time.time()],
            key=lambda event: (-event.stop, -event.start, event.name),
        )

    @cached_property
    def current_events(self) -> list[Event]:
        return sorted(
            [
                event
                for event in self.events_by_id.values()
                if event.start < time.time() < event.stop
            ],
            key=lambda event: (event.stop, event.start, event.name),
        )

    @cached_property
    def coming_events(self) -> list[Event]:
        return sorted(
            [
                event
                for event in self.events_by_id.values()
                if time.time() < event.start
            ],
            key=lambda event: (event.stop, event.start, event.name),
        )

    @cached_property
    def public_events(self) -> list[Event]:
        return sorted(
            filter(attrgetter('public'), self.events_by_id.values()),
            key=attrgetter('name'),
        )

    @cached_property
    def passed_public_events(self) -> list[Event]:
        return sorted(
            [
                event
                for event in self.events_by_id.values()
                if event.public and event.stop < time.time()
            ],
            key=lambda event: (-event.stop, -event.start, event.name),
        )

    @cached_property
    def current_public_events(self) -> list[Event]:
        return sorted(
            [
                event
                for event in self.events_by_id.values()
                if event.public and event.start < time.time() < event.stop
            ],
            key=lambda event: (-event.stop, -event.start, event.name),
        )

    @cached_property
    def coming_public_events(self) -> list[Event]:
        return sorted(
            [
                event
                for event in self.events_by_id.values()
                if event.public and time.time() < event.start
            ],
            key=lambda event: (-event.stop, -event.start, event.name),
        )


@dataclass
class Archive:
    """This class implements archives (deleted events)."""

    file: Path
    name: str
    date: float

    @property
    def date_str(self):
        return format_timestamp_date_time(self.date)


class ArchiveLoader:
    """
    This class help loading archives (deleted events) efficiently.
    Usage:
    archive_loader: ArchiveLoader = ArchiveLoader.get(request)
    archives: list[Archives] = archive_loader.archives_sorted_by_date()
    """

    @classmethod
    def get(cls, request: HTMXRequest | None):
        if not request:
            return cls()
        archive_loader: ArchiveLoader = request.state.get('archive_loader')
        if not archive_loader:
            request.state['archive_loader'] = cls()
        return request.state['archive_loader']

    @cached_property
    def archives_sorted_by_date(self) -> list[Archive]:
        return sorted(
            [
                Archive(file, file.stem, file.lstat().st_ctime)
                for file in EVENTS_DIR.glob(f'*.{PapiWebConfig.event_archive_ext}')
            ],
            key=lambda archive: archive.date,
        )


@dataclass
class EventBackup:
    """This class implements backups (copies of event databases)."""

    name: str
    version: Version

    @property
    def file(self) -> Path:
        return (
            PapiWebConfig.event_backup_base_path
            / self.version.public
            / f'{self.name}.{PapiWebConfig.event_backup_ext}'
        )

    @property
    def exists(self) -> bool:
        return self.file.exists()

    def restore(self):
        """Restores the backup of the event. If another event
        with the same name exists, overwrites it"""
        assert self.exists
        shutil.copy(self.file, EventDatabase.event_database_path(self.name))


class EventBackupLoader:
    """This class helps loading backups (copied events)."""

    def __init__(self):
        PapiWebConfig.event_backup_base_path.mkdir(exist_ok=True, parents=True)

    @staticmethod
    def event_backups(event_id: str) -> list[EventBackup]:
        backups: list[EventBackup] = []
        for version_dir in PapiWebConfig.event_backup_base_path.iterdir():
            if not version_dir.is_dir():
                continue
            backup = EventBackup(event_id, Version(version_dir.name))
            if backup.exists:
                backups.append(backup)
        return backups

    @staticmethod
    def version_backups(version: Version) -> list[EventBackup]:
        version_dir: Path = PapiWebConfig.event_backup_base_path / version.public
        return [
            EventBackup(file.stem, version)
            for file in version_dir.glob(f'*.{PapiWebConfig.event_backup_ext}')
        ]

    def versions(self, event_id: str | None = None) -> list[Version]:
        if not PapiWebConfig.event_backup_base_path.exists():
            return []
        if event_id:
            return [backup.version for backup in self.event_backups(event_id)]
        return [
            Version(version_dir.name)
            for version_dir in PapiWebConfig.event_backup_base_path.iterdir()
            if version_dir.is_dir()
        ]

    def latest_compatible_version(self, event_id: str | None = None) -> Version | None:
        compatible_versions = [
            version
            for version in self.versions(event_id)
            if version <= PAPI_WEB_VERSION
        ]
        if not compatible_versions:
            return None
        return max(compatible_versions)
