import errno
import sqlite3
import sys
from pathlib import Path

import pytest

from database.sqlite.sqlite_database import SQLiteDatabase


def _create_database(file: Path) -> None:
    connection = sqlite3.connect(file)
    connection.execute('CREATE TABLE t (x)')
    connection.close()


def test_an_accessible_file_has_no_system_error(tmp_path: Path):
    file = tmp_path / 'event.sce'
    _create_database(file)

    assert SQLiteDatabase(file)._system_access_error() == ''
    assert SQLiteDatabase(file, write=True)._system_access_error() == ''


@pytest.mark.skipif(sys.platform == 'win32', reason='file modes are POSIX')
def test_a_refused_file_reports_the_system_error(tmp_path: Path):
    file = tmp_path / 'event.sce'
    _create_database(file)
    file.chmod(0)
    try:
        with pytest.raises(sqlite3.OperationalError), SQLiteDatabase(file):
            pass
        error = SQLiteDatabase(file)._system_access_error()
    finally:
        file.chmod(0o644)

    assert f'errno {errno.EACCES}' in error


@pytest.mark.skipif(sys.platform == 'win32', reason='file modes are POSIX')
def test_a_read_only_file_reports_the_refused_write(tmp_path: Path):
    file = tmp_path / 'event.sce'
    _create_database(file)
    file.chmod(0o444)
    try:
        read_error = SQLiteDatabase(file)._system_access_error()
        write_error = SQLiteDatabase(file, write=True)._system_access_error()
    finally:
        file.chmod(0o644)

    assert read_error == ''
    assert f'errno {errno.EACCES}' in write_error
