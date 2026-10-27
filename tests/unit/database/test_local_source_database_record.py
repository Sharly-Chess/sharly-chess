import sqlite3
from collections.abc import Iterator
from pathlib import Path

import pytest

from database.sqlite.config.config_database import ConfigDatabase
from database.sqlite.national.cfr_database import CfrDatabase


@pytest.fixture
def unrecorded_copy() -> Iterator[Path]:
    """An installed copy of a database the configuration has no record of."""
    file = CfrDatabase.file_path()
    file.parent.mkdir(parents=True, exist_ok=True)
    sqlite3.connect(file).close()
    with ConfigDatabase(write=True) as database:
        database.execute(
            'DELETE FROM `local_source_database` WHERE `name` = ?',
            (CfrDatabase.static_id(),),
        )
        database.commit()
    CfrDatabase._stored_source_database = None
    yield file
    file.unlink(missing_ok=True)
    cfr_database = CfrDatabase()
    cfr_database.update_stored_source_database(cfr_database.default_stored_database)


def test_an_installed_copy_without_a_record_is_kept(unrecorded_copy: Path) -> None:
    assert CfrDatabase().check()
    assert unrecorded_copy.exists()
    stored_database = CfrDatabase().stored_source_database
    assert stored_database.updated_at == unrecorded_copy.stat().st_mtime
