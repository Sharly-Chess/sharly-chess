import sqlite3
import sys
from pathlib import Path

import pytest
from packaging.version import Version

from utils import program_variables
from utils.data_dir_migration import (
    MAX_ATTEMPTS,
    README_FILE_NAME,
    DataDirMigration,
    DataDirMoveReason,
    DataDirMoveState,
    forget_moved_data_dir,
    is_left_by_a_move,
    moved_data_dir_to_delete,
)
from utils.instance_lock import InstanceLock
from utils.program_variables import ProgramVar

VERSION = Version('5.2.0')


@pytest.fixture(autouse=True)
def program_vars(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The variables are stored in a file of the test, not in the registry or
    the property list of the user."""
    monkeypatch.setattr(sys, 'platform', 'linux')
    monkeypatch.setattr(
        program_variables, 'LINUX_DATA_FILE', tmp_path / 'program_vars.json'
    )
    for name in ('OneDrive', 'OneDriveConsumer', 'OneDriveCommercial'):
        monkeypatch.delenv(name, raising=False)


def _fill_data_dir(data_dir: Path) -> None:
    events_dir = data_dir / 'v5.1.7' / 'events'
    events_dir.mkdir(parents=True)
    connection = sqlite3.connect(events_dir / 'open.sce')
    connection.execute('CREATE TABLE player (name)')
    connection.execute("INSERT INTO player VALUES ('Carlsen')")
    connection.commit()
    connection.close()
    (data_dir / 'archives').mkdir()
    (data_dir / 'archives' / 'old.sca').write_bytes(b'archive')


def _migration(tmp_path: Path, data_dir: Path | None = None) -> DataDirMigration:
    legacy_default_dir = tmp_path / 'Documents' / 'Sharly Chess'
    return DataDirMigration(
        data_dir=data_dir or legacy_default_dir,
        legacy_default_dir=legacy_default_dir,
        target_dir=tmp_path / 'AppData' / 'Local' / 'Sharly Chess',
    )


def test_the_data_of_the_former_default_folder_is_moved(tmp_path: Path):
    migration = _migration(tmp_path)
    assert migration.reason == DataDirMoveReason.LEGACY_DEFAULT
    assert migration.should_run()
    assert not migration.should_ask()


def test_a_folder_chosen_in_onedrive_is_asked_for(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setenv('OneDrive', str(tmp_path / 'OneDrive'))
    migration = _migration(tmp_path, tmp_path / 'OneDrive' / 'Chess')

    assert migration.reason == DataDirMoveReason.ONEDRIVE
    assert migration.should_ask()
    assert not migration.should_run()

    DataDirMigration.request()
    assert migration.should_run()
    assert not migration.should_ask()


def test_a_declined_move_is_not_asked_again(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setenv('OneDriveCommercial', str(tmp_path / 'OneDrive - Club'))
    migration = _migration(tmp_path, tmp_path / 'OneDrive - Club' / 'Chess')

    DataDirMigration.decline()

    assert not migration.should_ask()
    assert not migration.should_run()
    assert migration.can_be_requested()


def test_a_folder_chosen_elsewhere_stays(tmp_path: Path):
    migration = _migration(tmp_path, tmp_path / 'D' / 'Chess')

    assert migration.reason is None
    assert not migration.should_run()
    assert not migration.should_ask()
    assert migration.run(VERSION) == tmp_path / 'D' / 'Chess'


def test_the_move_copies_the_data_and_sets_the_previous_folder_aside(
    tmp_path: Path,
):
    migration = _migration(tmp_path)
    _fill_data_dir(migration.data_dir)

    data_dir = migration.run(VERSION)

    assert data_dir == migration.target_dir
    connection = sqlite3.connect(data_dir / 'v5.1.7' / 'events' / 'open.sce')
    assert connection.execute('SELECT name FROM player').fetchall() == [('Carlsen',)]
    connection.close()
    assert (data_dir / 'archives' / 'old.sca').read_bytes() == b'archive'
    assert not migration.staging_dir.exists()
    assert not migration.data_dir.exists()
    moved_dir = migration.data_dir.with_name('Sharly Chess (moved to AppData)')
    assert str(data_dir) in (moved_dir / README_FILE_NAME).read_text()
    assert ProgramVar.DATA_DIR.read_path_value() == data_dir
    assert ProgramVar.MOVED_DATA_DIR.read_path_value() == moved_dir
    assert ProgramVar.MOVED_DATA_DIR_VERSION.read_value() == '5.2.0'
    assert DataDirMigration.state() == DataDirMoveState.MOVED
    assert any('Data moved' in message for __, message in migration.messages)


def test_a_failed_move_keeps_the_data_where_it_is(tmp_path: Path):
    migration = _migration(tmp_path)
    _fill_data_dir(migration.data_dir)
    migration.target_dir.mkdir(parents=True)
    (migration.target_dir / 'unexpected.txt').write_text('')

    for attempt in range(1, MAX_ATTEMPTS + 1):
        assert migration.should_run()
        assert migration.run(VERSION) == migration.data_dir
        assert DataDirMigration.failed_attempts() == attempt

    assert (migration.data_dir / 'v5.1.7' / 'events' / 'open.sce').is_file()
    assert not migration.staging_dir.exists()
    assert ProgramVar.DATA_DIR.read_value() is None
    assert not migration.should_run()
    assert migration.can_be_requested()

    DataDirMigration.request()
    assert migration.should_run()


def test_the_move_waits_for_the_running_instance(tmp_path: Path):
    migration = _migration(tmp_path)
    _fill_data_dir(migration.data_dir)
    running = InstanceLock(migration.data_dir)
    assert running.acquire()
    try:
        assert migration.run(VERSION) == migration.data_dir
    finally:
        running.release()

    assert DataDirMigration.state() == DataDirMoveState.NONE
    assert not migration.target_dir.exists()


def test_a_launch_after_the_move_runs_on_the_new_folder(tmp_path: Path):
    first = _migration(tmp_path)
    _fill_data_dir(first.data_dir)
    second = _migration(tmp_path)

    first.run(VERSION)
    ProgramVar.DATA_DIR_MOVE.clear_value()

    assert second.run(VERSION) == first.target_dir


@pytest.mark.parametrize(
    ('current', 'deleted'),
    [('5.2.3', False), ('5.3.0', False), ('5.4.0', True), ('6.0.0', True)],
)
def test_the_previous_folder_is_deleted_two_versions_later(
    tmp_path: Path, current: str, deleted: bool
):
    ProgramVar.MOVED_DATA_DIR.write_value(str(tmp_path / 'moved'))
    ProgramVar.MOVED_DATA_DIR_VERSION.write_value('5.2.0')

    expected = tmp_path / 'moved' if deleted else None
    assert moved_data_dir_to_delete(Version(current)) == expected


def test_only_the_folder_left_by_the_move_is_deleted(tmp_path: Path):
    moved_dir = tmp_path / 'moved'
    moved_dir.mkdir()
    assert not is_left_by_a_move(moved_dir)
    (moved_dir / README_FILE_NAME).write_text('')
    assert is_left_by_a_move(moved_dir)

    ProgramVar.MOVED_DATA_DIR.write_value(str(moved_dir))
    ProgramVar.MOVED_DATA_DIR_VERSION.write_value('5.2.0')
    forget_moved_data_dir()
    assert moved_data_dir_to_delete(Version('9.0.0')) is None


def test_a_folder_in_use_postpones_the_move_without_a_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    migration = _migration(tmp_path)
    _fill_data_dir(migration.data_dir)

    def refuse_rename(directory: Path) -> None:
        raise PermissionError(5, 'Access is denied')

    monkeypatch.setattr(
        DataDirMigration, '_check_not_in_use', staticmethod(refuse_rename)
    )

    assert migration.run(VERSION) == migration.data_dir
    assert DataDirMigration.failed_attempts() == 0
    assert migration.should_run()
