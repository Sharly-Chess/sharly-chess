import json
import logging
import os
import shutil
import sqlite3
import sys
import time
from enum import StrEnum
from functools import cached_property
from pathlib import Path

from utils.file import is_within
from utils.instance_lock import InstanceLock
from utils.program_variables import ProgramVar

STAGING_DIR_SUFFIX = '.partial'
MAX_ATTEMPTS = 3
#: How long a move waits for the instance that asked for it to let the data go.
#: A move asked from the settings is completed by the next start, often started
#: before the previous one has finished leaving: Windows holds the log file of
#: a process until it is gone, and a folder holding an open file can neither be
#: renamed nor deleted.
MOVE_WAIT_SECONDS = 15.0
_MOVE_RETRY_SECONDS = 0.5
_RENAME_WAIT_SECONDS = 3.0
_DATABASE_SUFFIXES = ('.sce', '.scch', '.scc')
_ONEDRIVE_VARIABLES = ('OneDrive', 'OneDriveConsumer', 'OneDriveCommercial')
# The variables of the folders where Dropbox writes the folders it synchronises.
_DROPBOX_INFO_VARIABLES = ('APPDATA', 'LOCALAPPDATA')
# The drive Google Drive streams the files to.
_GOOGLE_DRIVE_VOLUME_LABEL = 'Google Drive'


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
        if any(is_within(path, directory) for directory in directories):
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
    and only then does the application switch to it and delete the folder it
    came from. On a failure the data stays where it was and the move is tried
    again on the next start.

    The data is copied and checked before anything is deleted, rather than
    moved: a copy that went wrong leaves the data where it was. The previous
    folder goes once the copy answers for it, and a cloud service that
    synchronised it removes its own copy in turn, which is the point of taking
    the data out of such a folder."""

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
    def _stored() -> tuple[str, int]:
        """The state the variable holds and the failed attempts that follow
        it, the two being written as one value."""
        value = ProgramVar.DATA_DIR_MOVE.read_value() or ''
        name, __, attempts = value.partition(':')
        try:
            return name, int(attempts)
        except ValueError:
            return name, 0

    @staticmethod
    def state() -> DataDirMoveState:
        try:
            return DataDirMoveState(DataDirMigration._stored()[0])
        except ValueError:
            return DataDirMoveState.NONE

    @staticmethod
    def failed_attempts() -> int:
        return DataDirMigration._stored()[1]

    def should_run(self) -> bool:
        if self.reason is None:
            return False
        state = self.state()
        if state == DataDirMoveState.REQUESTED:
            return self.failed_attempts() < MAX_ATTEMPTS
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

    def run(self, wait_seconds: float = MOVE_WAIT_SECONDS) -> Path:
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
        if not _free_to_move(source, time.monotonic() + wait_seconds):
            # Not counted as a failure: an instance that is still leaving, or a
            # former version of Sharly Chess left open, which does not lock its
            # folder, are the likely causes.
            self._log(
                logging.WARNING,
                f'The data at [{source}] is in use, the move is postponed.',
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
                check_copy(source, self.staging_dir)
                if self.target_dir.exists():
                    self.target_dir.rmdir()
                self.staging_dir.rename(self.target_dir)
            finally:
                lock.release()
        except (OSError, sqlite3.Error) as error:
            shutil.rmtree(self.staging_dir, ignore_errors=True)
            attempts = self.failed_attempts() + 1
            # A move the user asked for stays asked for: the next start tries
            # it again, as many times as a move of the legacy folder, and the
            # settings offer it again once the attempts are spent.
            state = (
                DataDirMoveState.REQUESTED
                if self.state() == DataDirMoveState.REQUESTED
                else DataDirMoveState.FAILED
            )
            ProgramVar.DATA_DIR_MOVE.write_value(f'{state}:{attempts}')
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
        self._delete(source, wait_seconds)
        return self.target_dir

    def _delete(self, source: Path, wait_seconds: float) -> None:
        """Deletes the folder the data came from, the copy having answered for
        it. A folder left behind is reported and nothing else: the data is at
        its new location, so the start goes on and the user can delete the
        remains themselves."""
        if not _deleted(source, time.monotonic() + wait_seconds):
            self._log(
                logging.WARNING,
                f'Data moved to [{self.target_dir}], the previous folder [{source}] '
                'could not be deleted entirely.',
            )
            return
        self._log(
            logging.INFO,
            f'Data moved to [{self.target_dir}], the previous folder has been deleted.',
        )

    def _log(self, level: int, message: str) -> None:
        self.messages.append((level, message))


def check_copy(source: Path, copy: Path) -> None:
    """Checks that a copy of the data holds every file of the source, whole
    and readable. Raises OSError on the first one that does not."""
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
                and not _is_sound(copied_file)
                and _is_sound(source_file)
            ):
                raise OSError(f'[{copied_file}] was not copied soundly.')


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


def _free_to_move(directory: Path, deadline: float) -> bool:
    """Whether the data can be taken out of the folder, waiting until the
    deadline for the instance that holds it to be gone.

    A move is completed by the start that follows the one the user asked it
    from, which often begins before that one has finished leaving: Windows
    holds the log file of a process until the process itself is gone, and a
    folder holding an open file can neither be renamed nor deleted."""
    while True:
        if not InstanceLock.is_held_by_another_process(directory) and _not_in_use(
            directory
        ):
            return True
        if time.monotonic() >= deadline:
            return False
        time.sleep(_MOVE_RETRY_SECONDS)


def _not_in_use(directory: Path) -> bool:
    """A folder holding a file opened by another program (a former version of
    Sharly Chess writing its log, say) can not be renamed on Windows, which
    tells it is in use."""
    probe = directory.with_name(directory.name + ' (checking)')
    try:
        directory.rename(probe)
    except OSError:
        return False
    probe.rename(directory)
    return True


def _deleted(directory: Path, deadline: float) -> bool:
    """Whether the folder could be deleted, trying again until the deadline for
    as long as something holds a file of it open."""
    while True:
        shutil.rmtree(directory, ignore_errors=True)
        if not directory.exists():
            return True
        if time.monotonic() >= deadline:
            return False
        time.sleep(_MOVE_RETRY_SECONDS)


class DataDirInUse(OSError):
    """Sharly Chess is still running on the folder the data is to leave."""


def complete_requested_move(
    previous_dir: Path, data_dir: Path, wait_seconds: float = MOVE_WAIT_SECONDS
) -> Path | None:
    """Moves the data to the folder the user chose in the settings.

    The data is copied, the copy is checked, and only then does it take the
    place of the empty folder the start has just made: nothing is given up
    before the copy answers for it, and a move that fails leaves the data
    where it was for the next start to try again.

    The folder is deleted last, and a folder that could not be deleted is
    returned rather than raised: the data is at its new location by then, and
    calling that a failure would send the user back to a folder that no longer
    holds their events.
    """
    deadline = time.monotonic() + wait_seconds
    while InstanceLock.is_held_by_another_process(previous_dir):
        if time.monotonic() >= deadline:
            raise DataDirInUse(f'Sharly Chess is running on [{previous_dir}].')
        time.sleep(_MOVE_RETRY_SECONDS)
    # The rename is the whole move at once, and is only given the few seconds
    # the process leaving takes to let go: it also fails for good when the two
    # folders are on different drives, and copying is then the only way.
    if _renamed(
        previous_dir,
        data_dir,
        min(deadline, time.monotonic() + _RENAME_WAIT_SECONDS),
    ):
        return None
    staging_dir = data_dir.with_name(data_dir.name + STAGING_DIR_SUFFIX)
    try:
        shutil.rmtree(staging_dir, ignore_errors=True)
        shutil.copytree(previous_dir, staging_dir)
        check_copy(previous_dir, staging_dir)
        if data_dir.exists():
            data_dir.rmdir()
        staging_dir.rename(data_dir)
    except (OSError, sqlite3.Error):
        shutil.rmtree(staging_dir, ignore_errors=True)
        data_dir.mkdir(parents=True, exist_ok=True)
        raise
    return None if _deleted(previous_dir, deadline) else previous_dir


def _renamed(previous_dir: Path, data_dir: Path, deadline: float) -> bool:
    """Whether the folder could simply be renamed, which is the whole move at
    once when both are on the same drive."""
    while True:
        try:
            if data_dir.exists():
                data_dir.rmdir()
            previous_dir.rename(data_dir)
            return True
        except OSError:
            data_dir.mkdir(parents=True, exist_ok=True)
            if time.monotonic() >= deadline:
                return False
            time.sleep(_MOVE_RETRY_SECONDS)
