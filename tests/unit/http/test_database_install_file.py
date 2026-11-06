"""Installing a source database from a file the user provides, over HTTP."""

from pathlib import Path

import pytest
from litestar.testing import TestClient

from database.sqlite.fide.fide_database import FideDatabase
from database.sqlite.local_source_database.managers import LocalSourceDatabaseManager
from plugins.fra_schools.fra_schools_database import FRASchoolsDatabase

LARGE_FILE_SIZE = 20 * 1024 * 1024


@pytest.fixture
def installed_files(monkeypatch: pytest.MonkeyPatch) -> list[Path]:
    """The source files the databases were asked to install, in place of
    starting the update threads."""
    files: list[Path] = []

    def update(self: object, source_file: Path | None = None, **_: object) -> None:
        assert source_file is not None
        files.append(source_file)

    monkeypatch.setattr(FideDatabase, 'update', update)
    monkeypatch.setattr(FRASchoolsDatabase, 'update', update)
    monkeypatch.setattr(FideDatabase, 'is_active', True)
    return files


@pytest.mark.unit
def test_a_large_source_file_is_installed(
    http: TestClient, installed_files: list[Path]
):
    response = http.post(
        f'/database-install-file/{FideDatabase.static_id()}',
        files={'file': ('players.zip', b'0' * LARGE_FILE_SIZE)},
    )
    assert response.status_code == 200
    assert len(installed_files) == 1
    assert installed_files[0].stat().st_size == LARGE_FILE_SIZE
    installed_files[0].unlink()


@pytest.mark.unit
def test_the_schools_database_cannot_be_installed_from_a_file(
    http: TestClient, installed_files: list[Path]
):
    database_id = FRASchoolsDatabase.static_id()
    assert isinstance(
        LocalSourceDatabaseManager().get_object(database_id), FRASchoolsDatabase
    )
    response = http.post(
        f'/database-install-file/{database_id}',
        files={'file': ('schools.db', b'0')},
        follow_redirects=False,
    )
    assert response.status_code == 302
    assert response.headers['location'].endswith('/error/404')
    assert installed_files == []


@pytest.mark.unit
@pytest.mark.parametrize(
    ('database_id', 'offered'),
    [(FideDatabase.static_id(), True), (FRASchoolsDatabase.static_id(), False)],
)
def test_the_file_button_is_offered_only_where_a_file_can_be_installed(
    http: TestClient, database_id: str, offered: bool
):
    response = http.get(f'/database-status/{database_id}')
    assert response.status_code == 200
    assert (f'id="database-{database_id}-file-form"' in response.text) is offered
