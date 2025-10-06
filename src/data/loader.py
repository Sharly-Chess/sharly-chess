import re
import shutil
import time
from collections.abc import Callable
from dataclasses import dataclass
from functools import cached_property
from logging import Logger
from pathlib import Path
from typing import Literal

from common.i18n.utils import by, normalized_key
from litestar.plugins.htmx import HTMXRequest
from packaging.version import Version

from common import (
    format_timestamp_date_time,
    SHARLY_CHESS_VERSION,
    EVENTS_DIR,
)
from common.exception import SharlyChessException
from common.sharly_chess_config import SharlyChessConfig
from common.logger import get_logger
from data.event import Event
from database.sqlite.event.event_database import EventDatabase
from database.sqlite.event.event_store import EventMetadata
from utils import StaticUtils

logger: Logger = get_logger()


class EventLoader:
    _valid_event_ids: set[str] = set()
    _invalid_uniq_ids: set[str] = set()

    @classmethod
    def get(cls, request: HTMXRequest | None):
        if not request:
            return cls()
        event_loader: EventLoader = request.state.get('event_loader', None)
        if not event_loader:
            request.state['event_loader'] = cls()
        return request.state['event_loader']

    @classmethod
    def unload_event(cls, uniq_id: str):
        cls._valid_event_ids.remove(uniq_id)
        cls.load_event_ids()

    @classmethod
    def load_event_ids(cls, uniq_id: str | None = None):
        cls._clean_not_existing_event_database_files(cls._valid_event_ids)
        cls._clean_not_existing_event_database_files(cls._invalid_uniq_ids)
        known_event_ids = cls._valid_event_ids | cls._invalid_uniq_ids
        event_ids = [uniq_id] if uniq_id is not None else cls.all_event_ids()
        for event_id in event_ids:
            if event_id in known_event_ids:
                continue
            try:
                database = EventDatabase(event_id)
                if not database.check_status():
                    database.upgrade()
                cls._valid_event_ids.add(event_id)
            except SharlyChessException as e:
                logger.error(e)
                cls._invalid_uniq_ids.add(event_id)

    @classmethod
    def _clean_not_existing_event_database_files(cls, event_uniq_ids: set[str]):
        to_remove = [
            uniq_id
            for uniq_id in event_uniq_ids
            if not EventDatabase.event_database_path(uniq_id).exists()
        ]
        for uniq_id in to_remove:
            event_uniq_ids.remove(uniq_id)

    @cached_property
    def event_uniq_ids(self) -> list[str]:
        self.load_event_ids()
        return list(self._valid_event_ids)

    @classmethod
    def all_event_ids(cls) -> list[str]:
        ids: list[str] = []
        for file in EVENTS_DIR.glob(f'*.{SharlyChessConfig.event_database_ext}'):
            if SharlyChessConfig.uniq_id_regex.match(file.stem):
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
        return StaticUtils.get_unused_item_uniq_id(base_uniq_id, self.all_event_ids())

    def get_unused_event_name(self, base_name: str) -> str:
        return StaticUtils.get_unused_item_name(
            base_name, [event.name for event in self.get_events_metadata()]
        )

    def load_event(self, uniq_id: str) -> Event:
        self.load_event_ids(uniq_id)
        with EventDatabase(uniq_id) as event_database:
            event = Event(event_database.load_stored_event())
        return event

    @cached_property
    def events_sorted_by_name(self) -> list[Event]:
        # TODO (Molrn) Remove (loading all the events at once should be avoided at all cost)
        events_by_id: dict[str, Event] = {}
        for uniq_id in self.event_uniq_ids:
            try:
                events_by_id[uniq_id] = self.load_event(uniq_id)
            except SharlyChessException as pwe:
                logger.error(pwe)
        return sorted(events_by_id.values(), key=by('name'))

    @classmethod
    def load_event_metadata(cls, uniq_id: str) -> EventMetadata:
        with EventDatabase(uniq_id) as database:
            event_metadata = database.load_stored_event_metadata()
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
            key=lambda event: (-event.stop, -event.start, normalized_key('name')),
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

    def restore(self) -> str:
        event_uniq_id = EventLoader().get_unused_event_uniq_id(self.name.split('#')[0])
        self.file.rename(EventDatabase.event_database_path(event_uniq_id))
        return event_uniq_id


class ArchiveLoader:
    """This class help loading archives (deleted events) efficiently."""

    @staticmethod
    def get_sorted_archives() -> list[Archive]:
        return sorted(
            [
                Archive(file, file.stem, file.lstat().st_ctime)
                for file in SharlyChessConfig.event_archive_base_path.glob(
                    f'*.{SharlyChessConfig.event_archive_ext}'
                )
            ],
            key=lambda archive: archive.date,
        )

    @classmethod
    def get_archive(cls, archive_name: str) -> Archive | None:
        """Get an archive by its name if it exists, None if it does not."""
        arch_file = cls.get_archive_path(archive_name)
        if not arch_file.exists():
            return None
        return Archive(arch_file, arch_file.stem, arch_file.lstat().st_ctime)

    @staticmethod
    def get_archive_path(archive_name: str) -> Path:
        return (
            SharlyChessConfig.event_archive_base_path
            / f'{archive_name}.{SharlyChessConfig.event_archive_ext}'
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
