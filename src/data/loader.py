import re
import shutil
import time
from collections.abc import Callable
from contextlib import suppress
from dataclasses import dataclass
from datetime import datetime, timedelta
from functools import cached_property
from logging import Logger
from pathlib import Path
from typing import Literal

from litestar.plugins.htmx import HTMXRequest
from packaging.version import Version

from common import (
    format_timestamp_date_time,
    unicode_normalize,
    SHARLY_CHESS_VERSION,
    EVENTS_DIR,
)
from common.exception import SharlyChessException
from common.sharly_chess_config import SharlyChessConfig
from common.logger import get_logger
from data.event import Event
from database.sqlite.event.event_database import EventDatabase
from database.sqlite.event.event_store import EventMetadata

logger: Logger = get_logger()


class EventLoader:
    id_regex = re.compile(r'^[0-9a-zA-Z_\-]+$')
    _valid_event_ids: list[str] = []
    _invalid_uniq_ids: list[str] = []
    _loaded_events_metadata_by_id: dict[str, EventMetadata] = {}
    _loaded_events_by_id: dict[str, Event] = {}
    _loaded_events_expire_at: dict[str, datetime] = {}
    _loaded_events_last_known_update: dict[str, float] = {}

    def __init__(self):
        to_unload: list[str] = []
        for uniq_id, expires_at in self._loaded_events_expire_at.items():
            if expires_at < datetime.now():
                to_unload.append(uniq_id)
        for uniq_id in to_unload:
            self.unload_event(uniq_id)
            logger.debug(f'Cached event [{uniq_id}] expired')

    @classmethod
    def get(cls, request: HTMXRequest | None):
        if not request:
            return cls()
        event_loader: EventLoader = request.state.get('event_loader', None)
        if not event_loader:
            request.state['event_loader'] = cls()
        return request.state['event_loader']

    @classmethod
    def unload_event(cls, event_uniq_id: str):
        with suppress(KeyError):
            del cls._loaded_events_metadata_by_id[event_uniq_id]
        with suppress(KeyError):
            del cls._loaded_events_by_id[event_uniq_id]
        with suppress(KeyError):
            del cls._loaded_events_expire_at[event_uniq_id]
        with suppress(KeyError):
            del cls._loaded_events_last_known_update[event_uniq_id]
        with suppress(ValueError):
            cls._valid_event_ids.remove(event_uniq_id)

    @classmethod
    def unload_all_events(cls):
        for event_uniq_id in cls._valid_event_ids:
            cls.unload_event(event_uniq_id)

    def clear_cache(self, event_uniq_id: str | None = None):
        """If `event_uniq_id` is provided, clears the load cache regarding the
        given event."""
        if event_uniq_id:
            self.unload_event(event_uniq_id)
        cached_property_names = [
            name
            for name in dir(self)
            if isinstance(getattr(type(self), name, None), cached_property)
        ]
        for property_name in cached_property_names:
            if property_name in self.__dict__:
                del self.__dict__[property_name]

    @classmethod
    def load_event_ids(cls, uniq_id: str | None = None):
        known_event_ids = cls._valid_event_ids + cls._invalid_uniq_ids
        event_ids = [uniq_id] if uniq_id is not None else cls.all_event_ids()
        for event_id in event_ids:
            if event_id in known_event_ids:
                continue
            try:
                with EventDatabase(event_id) as database:
                    status = database.check_status()
                if not status:
                    with EventDatabase(event_id, True) as database:
                        database.upgrade()
                cls._valid_event_ids.append(event_id)
            except SharlyChessException as e:
                logger.error(e)
                cls._invalid_uniq_ids.append(event_id)

    @cached_property
    def event_uniq_ids(self) -> list[str]:
        self.load_event_ids()
        return self._valid_event_ids

    @classmethod
    def all_event_ids(cls) -> list[str]:
        ids: list[str] = []
        for file in EVENTS_DIR.glob(f'*.{SharlyChessConfig.event_database_ext}'):
            if cls.id_regex.match(file.stem):
                ids.append(file.stem)
            else:
                new_id: str = re.sub(r'[^a-zA-Z0-9_\-]', '_', file.stem)
                index: int = 1
                new_file: Path = (
                    file.parent / f'{new_id}.{SharlyChessConfig.event_database_ext}'
                )
                while new_file.exists():
                    index += 1
                    new_file = (
                        file.parent
                        / f'{new_id}-{index}.{SharlyChessConfig.event_database_ext}'
                    )
                shutil.move(file, new_file)
                for old_file in [
                    file.with_suffix(f'.{SharlyChessConfig.event_database_ext}-shm'),
                    file.with_suffix(f'.{SharlyChessConfig.event_database_ext}-wal'),
                ]:
                    old_file.unlink(missing_ok=True)
                logger.warning(
                    'File [%s] has been renamed [%s]', file.name, new_file.name
                )
                ids.append(new_file.stem)
        return ids

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

    def _load_event(self, uniq_id: str, reload: bool) -> Event:
        cls = self.__class__
        cls._loaded_events_expire_at[uniq_id] = datetime.now() + timedelta(minutes=30)
        if uniq_id not in cls._loaded_events_last_known_update:
            cls._loaded_events_last_known_update[uniq_id] = (
                EventDatabase.database_modified_timestamp(uniq_id)
            )
        if reload:
            self.clear_cache(uniq_id)
        if uniq_id in self._loaded_events_by_id:
            last_modified = EventDatabase.database_modified_timestamp(uniq_id)
            if last_modified > cls._loaded_events_last_known_update[uniq_id]:
                # The database has been updated since the last time we loaded the event
                # This can happen using the ChessEvent engine.
                self.clear_cache(uniq_id)
            else:
                return self._loaded_events_by_id[uniq_id]

        self.load_event_ids(uniq_id)
        with EventDatabase(uniq_id) as event_database:
            event = Event(event_database.load_stored_event())
        cls._loaded_events_by_id[uniq_id] = event
        return event

    def load_event(self, uniq_id: str) -> Event:
        return self._load_event(uniq_id, reload=False)

    def reload_event(self, uniq_id: str) -> Event:
        return self._load_event(uniq_id, reload=True)

    @classmethod
    def set_last_known_update(cls, uniq_id: str, last_known_update: float):
        cls._loaded_events_last_known_update[uniq_id] = last_known_update

    @cached_property
    def events_by_id(self) -> dict[str, Event]:
        events_by_id: dict[str, Event] = {}
        for uniq_id in self.event_uniq_ids:
            try:
                events_by_id[uniq_id] = self.load_event(uniq_id)
            except SharlyChessException as pwe:
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

    @classmethod
    def load_event_metadata(cls, uniq_id: str) -> EventMetadata:
        try:
            return cls._loaded_events_metadata_by_id[uniq_id]
        except KeyError:
            with EventDatabase(uniq_id) as database:
                event_metadata = database.load_stored_event_metadata()
            cls._loaded_events_metadata_by_id[uniq_id] = event_metadata
            return event_metadata

    @classmethod
    def get_events_metadata(
        cls,
        status: Literal['passed', 'current', 'coming'] | None = None,
        public_only: bool = False,
    ) -> list[EventMetadata]:
        conditions: list[Callable[[EventMetadata], bool]] = []
        if public_only:
            conditions.append(lambda event: event.public)
        now = time.time()
        match status:
            case 'passed':
                conditions.append(lambda event: event.stop < now)
            case 'current':
                conditions.append(lambda event: event.start <= now <= event.stop)
            case 'coming':
                conditions.append(lambda event: now < event.start)
        return sorted(
            cls._filter_events_metadata(conditions),
            key=lambda event: (-event.stop, -event.start, event.name),
        )

    @classmethod
    def _filter_events_metadata(
        cls, conditions: list[Callable[[EventMetadata], bool]]
    ) -> list[EventMetadata]:
        cls.load_event_ids()
        events_metadata = [
            cls.load_event_metadata(uniq_id) for uniq_id in cls._valid_event_ids
        ]
        return [
            event_metadata
            for event_metadata in events_metadata
            if all(condition(event_metadata) for condition in conditions)
        ]


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
                for file in EVENTS_DIR.glob(f'*.{SharlyChessConfig.event_archive_ext}')
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
            SharlyChessConfig.event_backup_base_path
            / self.version.public
            / f'{self.name}.{SharlyChessConfig.event_backup_ext}'
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
        SharlyChessConfig.event_backup_base_path.mkdir(exist_ok=True, parents=True)

    @staticmethod
    def event_backups(event_id: str) -> list[EventBackup]:
        backups: list[EventBackup] = []
        for version_dir in SharlyChessConfig.event_backup_base_path.iterdir():
            if not version_dir.is_dir():
                continue
            backup = EventBackup(event_id, Version(version_dir.name))
            if backup.exists:
                backups.append(backup)
        return backups

    @staticmethod
    def version_backups(version: Version) -> list[EventBackup]:
        version_dir: Path = SharlyChessConfig.event_backup_base_path / version.public
        return [
            EventBackup(file.stem, version)
            for file in version_dir.glob(f'*.{SharlyChessConfig.event_backup_ext}')
        ]

    def versions(self, event_id: str | None = None) -> list[Version]:
        if not SharlyChessConfig.event_backup_base_path.exists():
            return []
        if event_id:
            return [backup.version for backup in self.event_backups(event_id)]
        return [
            Version(version_dir.name)
            for version_dir in SharlyChessConfig.event_backup_base_path.iterdir()
            if version_dir.is_dir()
        ]

    def latest_compatible_version(self, event_id: str | None = None) -> Version | None:
        compatible_versions = [
            version
            for version in self.versions(event_id)
            if version <= SHARLY_CHESS_VERSION
        ]
        if not compatible_versions:
            return None
        return max(compatible_versions)
