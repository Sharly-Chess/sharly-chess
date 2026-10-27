import json
import logging
import os
import shutil
import sqlite3
import sys
from enum import StrEnum
from functools import cached_property
from pathlib import Path

from packaging.version import Version

from utils.instance_lock import InstanceLock
from utils.program_variables import ProgramVar

README_FILE_NAME = 'README.txt'
MOVED_DIR_SUFFIX = ' (moved to AppData)'
STAGING_DIR_SUFFIX = '.partial'
MAX_ATTEMPTS = 3
_DATABASE_SUFFIXES = ('.sce', '.scch', '.scc')
_ONEDRIVE_VARIABLES = ('OneDrive', 'OneDriveConsumer', 'OneDriveCommercial')
# The variables of the folders where Dropbox writes the folders it synchronises.
_DROPBOX_INFO_VARIABLES = ('APPDATA', 'LOCALAPPDATA')
# The drive Google Drive streams the files to.
_GOOGLE_DRIVE_VOLUME_LABEL = 'Google Drive'

# Written before the logger, and so before the translations, exist.
_README_TEXT = """\
The data of Sharly Chess has moved to:
{target}

This folder is a copy of the data as it was when it moved. Sharly Chess no
longer uses it and deletes it two versions later.

---

Les données de Sharly Chess ont été déplacées vers :
{target}

Ce dossier est une copie des données telles qu'elles étaient au moment du
déplacement. Sharly Chess ne l'utilise plus et le supprime deux versions plus tard.
"""


class DataDirMoveState(StrEnum):
    NONE = ''
    # Asked by the user, run at the next start.
    REQUESTED = 'requested'
    # The user keeps the data where it is, never asked again.
    DECLINED = 'declined'
    # The data has moved, the user is still to be told.
    MOVED = 'moved'
    # The number of failed attempts follows.
    FAILED = 'failed'


class DataDirMoveReason(StrEnum):
    # The data is in the former default folder, in the Documents.
    LEGACY_DEFAULT = 'legacy_default'
    # The user chose a folder that a cloud service synchronises.
    SYNCHRONISED = 'synchronised'


def _same_path(first: Path, second: Path) -> bool:
    return os.path.normcase(os.path.normpath(first)) == os.path.normcase(
        os.path.normpath(second)
    )


def _is_within(path: Path, directory: Path) -> bool:
    path_str = os.path.normcase(os.path.normpath(path))
    directory_str = os.path.normcase(os.path.normpath(directory))
    return path_str == directory_str or path_str.startswith(
        directory_str.rstrip(os.sep) + os.sep
    )


def _dropbox_dirs() -> list[Path]:
    directories: list[Path] = []
    for variable in _DROPBOX_INFO_VARIABLES:
        if not (value := os.getenv(variable)):
            continue
        try:
            accounts = json.loads(
                (Path(value) / 'Dropbox' / 'info.json').read_text(encoding='utf-8')
            )
        except (OSError, ValueError):
            continue
        if isinstance(accounts, dict):
            directories += [
                Path(account['path'])
                for account in accounts.values()
                if isinstance(account, dict) and isinstance(account.get('path'), str)
            ]
    return directories or [Path.home() / 'Dropbox']


def _volume_label(path: Path) -> str | None:
    label: str | None = None
    if sys.platform == 'win32':
        import ctypes

        buffer = ctypes.create_unicode_buffer(261)
        if ctypes.windll.kernel32.GetVolumeInformationW(
            ctypes.c_wchar_p(path.anchor),
            buffer,
            len(buffer),
            None,
            None,
            None,
            None,
            0,
        ):
            label = buffer.value
    return label


def synchronised_dirs() -> dict[str, list[Path]]:
    """The folders that cloud services synchronise, by service."""
    return {
        'OneDrive': [
            Path(value) for name in _ONEDRIVE_VARIABLES if (value := os.getenv(name))
        ],
        'Google Drive': [Path.home() / 'My Drive', Path.home() / 'Google Drive'],
        'Dropbox': _dropbox_dirs(),
        'iCloud Drive': [Path.home() / 'iCloudDrive'],
    }


def sync_service(path: Path) -> str | None:
    """The cloud service that synchronises the folder, if any."""
    for service, directories in synchronised_dirs().items():
        if any(_is_within(path, directory) for directory in directories):
            return service
    if _volume_label(path) == _GOOGLE_DRIVE_VOLUME_LABEL:
        return 'Google Drive'
    return None


class DataDirMigration:
    """Moves the data folder out of the Documents or a folder synchronised by a
    cloud service, to the local application data, which cloud services do not
    synchronise.

    It runs on start, before anything reads or writes the data, and never stops
    the application from starting: the data is copied, the copy is checked,
    and only then does the application switch to it. On a failure the data
    stays where it was and the move is tried again on the next start. The data
    is copied rather than moved, as moving a folder out of a cloud service
    deletes it from the cloud and from the other computers it synchronises
    with."""

    def __init__(self, data_dir: Path, legacy_default_dir: Path, target_dir: Path):
        self.data_dir = data_dir
        self.legacy_default_dir = legacy_default_dir
        self.target_dir = target_dir
        # The logger does not exist yet: the messages are logged once it does.
        self.messages: list[tuple[int, str]] = []
        self.moved: bool = False

    @cached_property
    def reason(self) -> DataDirMoveReason | None:
        if _same_path(self.data_dir, self.target_dir):
            return None
        if _same_path(self.data_dir, self.legacy_default_dir):
            return DataDirMoveReason.LEGACY_DEFAULT
        if sync_service(self.data_dir):
            return DataDirMoveReason.SYNCHRONISED
        return None

    @staticmethod
    def state() -> DataDirMoveState:
        value = ProgramVar.DATA_DIR_MOVE.read_value() or ''
        if value.startswith(DataDirMoveState.FAILED):
            return DataDirMoveState.FAILED
        try:
            return DataDirMoveState(value)
        except ValueError:
            return DataDirMoveState.NONE

    @staticmethod
    def failed_attempts() -> int:
        value = ProgramVar.DATA_DIR_MOVE.read_value() or ''
        if not value.startswith(DataDirMoveState.FAILED):
            return 0
        try:
            return int(value.removeprefix(DataDirMoveState.FAILED).strip(':'))
        except ValueError:
            return 0

    def should_run(self) -> bool:
        if self.reason is None:
            return False
        state = self.state()
        if state == DataDirMoveState.REQUESTED:
            return True
        return (
            self.reason == DataDirMoveReason.LEGACY_DEFAULT
            and state in (DataDirMoveState.NONE, DataDirMoveState.FAILED)
            and self.failed_attempts() < MAX_ATTEMPTS
        )

    def should_ask(self) -> bool:
        """Whether the user is to be asked to move their data, which is only
        done for a folder they chose themselves."""
        return (
            self.reason == DataDirMoveReason.SYNCHRONISED
            and self.state() == DataDirMoveState.NONE
        )

    def can_be_requested(self) -> bool:
        """Whether the user can ask for the move from the settings."""
        return not self.moved and self.reason is not None and not self.should_run()

    @staticmethod
    def request() -> None:
        ProgramVar.DATA_DIR_MOVE.write_value(DataDirMoveState.REQUESTED)

    @staticmethod
    def decline() -> None:
        ProgramVar.DATA_DIR_MOVE.write_value(DataDirMoveState.DECLINED)

    @staticmethod
    def notice_shown() -> None:
        ProgramVar.DATA_DIR_MOVE.clear_value()

    @property
    def staging_dir(self) -> Path:
        return self.target_dir.with_name(self.target_dir.name + STAGING_DIR_SUFFIX)

    def run(self, version: Version) -> Path:
        """Moves the data if it is to be, returns the data folder to use."""
        if not self.should_run():
            return self.data_dir
        source = self.data_dir
        if not source.is_dir():
            # Moved by another launch started at the same time.
            return self.target_dir if self.target_dir.is_dir() else source
        self._log(
            logging.INFO, f'Moving the data from [{source}] to [{self.target_dir}]...'
        )
        if InstanceLock.is_held_by_another_process(source):
            self._log(
                logging.WARNING,
                'Sharly Chess is running on the data, the move is postponed.',
            )
            return source
        try:
            self._check_not_in_use(source)
        except OSError as error:
            # Not counted as a failure: a former version of Sharly Chess left
            # open, which does not lock its folder, is a likely cause.
            self._log(
                logging.WARNING,
                f'The data is in use, the move is postponed: {error}',
            )
            return source
        try:
            # Held while copying, so that a launch started at the same time
            # neither copies nor runs on the data meanwhile.
            lock = InstanceLock(source)
            if not lock.acquire():
                raise OSError(f'Sharly Chess has just been started on [{source}].')
            try:
                if self.target_dir.exists() and any(self.target_dir.iterdir()):
                    raise OSError(f'The folder [{self.target_dir}] is not empty.')
                shutil.rmtree(self.staging_dir, ignore_errors=True)
                shutil.copytree(source, self.staging_dir)
                self._check_copy(source, self.staging_dir)
                if self.target_dir.exists():
                    self.target_dir.rmdir()
                self.staging_dir.rename(self.target_dir)
            finally:
                lock.release()
        except (OSError, sqlite3.Error) as error:
            shutil.rmtree(self.staging_dir, ignore_errors=True)
            attempts = self.failed_attempts() + 1
            ProgramVar.DATA_DIR_MOVE.write_value(
                f'{DataDirMoveState.FAILED}:{attempts}'
            )
            self._log(
                logging.ERROR,
                f'The data could not be moved (attempt {attempts}/{MAX_ATTEMPTS}), '
                f'it stays at [{source}]: {error}',
            )
            return source

        ProgramVar.write_variables(
            {
                ProgramVar.DATA_DIR: str(self.target_dir),
                ProgramVar.DATA_DIR_MOVE: DataDirMoveState.MOVED,
            }
        )
        self.moved = True
        moved_dir = self._set_aside(source)
        ProgramVar.write_variables(
            {
                ProgramVar.MOVED_DATA_DIR: str(moved_dir),
                ProgramVar.MOVED_DATA_DIR_VERSION: str(version),
            }
        )
        self._log(
            logging.INFO,
            f'Data moved to [{self.target_dir}], the previous folder is kept at '
            f'[{moved_dir}].',
        )
        return self.target_dir

    @staticmethod
    def _check_not_in_use(directory: Path) -> None:
        """A folder holding a file opened by another program (a former version
        of Sharly Chess writing its log, say) can not be renamed on Windows,
        which tells it is in use."""
        probe = directory.with_name(directory.name + ' (checking)')
        directory.rename(probe)
        probe.rename(directory)

    @staticmethod
    def _check_copy(source: Path, copy: Path) -> None:
        for directory, __, files in os.walk(source):
            for name in files:
                source_file = Path(directory) / name
                copied_file = copy / source_file.relative_to(source)
                if (
                    not copied_file.is_file()
                    or copied_file.stat().st_size != source_file.stat().st_size
                ):
                    raise OSError(f'[{copied_file}] was not copied.')
                if (
                    copied_file.suffix in _DATABASE_SUFFIXES
                    and not DataDirMigration._is_sound(copied_file)
                    and DataDirMigration._is_sound(source_file)
                ):
                    raise OSError(f'[{copied_file}] was not copied soundly.')

    @staticmethod
    def _is_sound(database_file: Path) -> bool:
        try:
            connection = sqlite3.connect(
                f'{database_file.resolve().as_uri()}?mode=ro', uri=True
            )
            try:
                row = connection.execute('PRAGMA quick_check').fetchone()
                return bool(row == ('ok',))
            finally:
                connection.close()
        except sqlite3.Error:
            return False

    def _set_aside(self, source: Path) -> Path:
        """Renames the previous folder, so that it is not taken for the data,
        and tells where the data went."""
        moved_dir = source.with_name(source.name + MOVED_DIR_SUFFIX)
        index = 2
        while moved_dir.exists():
            moved_dir = source.with_name(f'{source.name}{MOVED_DIR_SUFFIX} {index}')
            index += 1
        try:
            source.rename(moved_dir)
        except OSError as error:
            self._log(logging.WARNING, f'[{source}] could not be renamed: {error}')
            moved_dir = source
        try:
            (moved_dir / README_FILE_NAME).write_text(
                _README_TEXT.format(target=self.target_dir), encoding='utf-8'
            )
        except OSError as error:
            self._log(logging.WARNING, f'[{moved_dir}] could not be marked: {error}')
        return moved_dir

    def _log(self, level: int, message: str) -> None:
        self.messages.append((level, message))


def moved_data_dir_to_delete(current_version: Version) -> Path | None:
    """The folder a move left behind, once the version that moved it is out of
    the two minor versions supported: by then the data has long been in use at
    its new location."""
    moved_dir = ProgramVar.MOVED_DATA_DIR.read_path_value()
    moved_version_str = ProgramVar.MOVED_DATA_DIR_VERSION.read_value()
    if not moved_dir or not moved_version_str:
        return None
    try:
        moved_version = Version(moved_version_str)
    except ValueError:
        return None
    if current_version.major < moved_version.major or (
        current_version.major == moved_version.major
        and current_version.minor < moved_version.minor + 2
    ):
        return None
    return moved_dir


def is_left_by_a_move(directory: Path) -> bool:
    """Whether the folder is still the one a move left behind, which the user
    may have deleted or reused since."""
    return (directory / README_FILE_NAME).is_file()


def forget_moved_data_dir() -> None:
    ProgramVar.MOVED_DATA_DIR.clear_value()
    ProgramVar.MOVED_DATA_DIR_VERSION.clear_value()
