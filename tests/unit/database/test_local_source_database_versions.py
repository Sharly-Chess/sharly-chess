import sqlite3
from pathlib import Path

import pytest

from common.network import NetworkMonitor
from database.sqlite.local_source_database.actions import AutoUpdateOutdatedAction
from plugins.ffe.ffe_database import FfeDatabase


@pytest.fixture
def previous_version_file():
    current = FfeDatabase.file_path()
    previous = current.with_name(f'{FfeDatabase.static_id()}-1.db')
    previous.parent.mkdir(parents=True, exist_ok=True)
    current.unlink(missing_ok=True)
    sqlite3.connect(previous).close()
    yield previous
    previous.unlink(missing_ok=True)
    current.unlink(missing_ok=True)
    database = FfeDatabase()
    database.update_stored_source_database(database.default_stored_database)
    FfeDatabase.update_status = None
    FfeDatabase.previous_version_update_started = False


def test_previous_version_is_replaced_by_the_current_one(
    previous_version_file: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    stored_database = FfeDatabase().stored_source_database
    stored_database.outdate_action = AutoUpdateOutdatedAction.static_id()
    stored_database.updated_at = 1.0
    FfeDatabase.update_stored_source_database(stored_database)

    updates: list[FfeDatabase] = []

    def update(self: FfeDatabase) -> None:
        updates.append(self)

    monkeypatch.setattr(FfeDatabase, 'update', update)
    assert not FfeDatabase().check()
    assert not FfeDatabase().check()
    assert len(updates) == 1
    assert previous_version_file.exists()
    assert FfeDatabase.previous_version_file_paths() == [previous_version_file]

    def download(self: FfeDatabase, source_file_dir: Path) -> bool:
        connection = sqlite3.connect(source_file_dir / self._source_file_name)
        connection.execute(
            'CREATE TABLE player (ffe_arbiter_title TEXT, fide_arbiter_title TEXT)'
        )
        connection.commit()
        connection.close()
        return True

    monkeypatch.setattr(FfeDatabase, '_download_source_file', download)
    monkeypatch.setattr(NetworkMonitor, 'connected', staticmethod(lambda: True))
    updates[0]._update()

    assert FfeDatabase.file_path().exists()
    assert not previous_version_file.exists()
    stored_database = FfeDatabase().stored_source_database
    assert stored_database.outdate_action == AutoUpdateOutdatedAction.static_id()
    assert stored_database.updated_at and stored_database.updated_at > 1.0
