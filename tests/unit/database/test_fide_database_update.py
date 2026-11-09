"""How the FIDE database keeps its copy current: a daily update that asks
the server what it holds before rebuilding anything."""

from datetime import datetime, timedelta, UTC
from pathlib import Path

import pytest

from common.network import NetworkMonitor
from database.sqlite.fide.fide_database import FideDatabase, FideSource, FIDE_SOURCE
from database.sqlite.local_source_database.actions import AutoUpdateOutdatedAction


@pytest.mark.unit
def test_the_database_updates_itself_daily() -> None:
    database = FideDatabase()
    stored_database = database.default_stored_database
    assert stored_database.outdate_delay == 'daily'
    assert stored_database.outdate_action == 'auto_update'


@pytest.mark.unit
def test_the_database_is_installed_without_being_asked_for() -> None:
    assert FideDatabase().default_is_active


@pytest.mark.unit
@pytest.mark.parametrize(
    ('published_hours_ago', 'changed'),
    [(1, True), (3, False)],
)
def test_the_source_counts_as_changed_when_the_server_published_later(
    monkeypatch: pytest.MonkeyPatch, published_hours_ago: int, changed: bool
) -> None:
    if FIDE_SOURCE != FideSource.OFFICIAL_LIST:
        pytest.skip('the ready-made database carries no publication date')
    now = datetime.now(UTC)
    database = FideDatabase()
    monkeypatch.setattr(
        FideDatabase,
        '_source_last_modified',
        lambda self, url: now - timedelta(hours=published_hours_ago),
    )
    updated_at = (now - timedelta(hours=2)).astimezone().replace(tzinfo=None)
    assert database._source_changed_since(updated_at) is changed


@pytest.mark.unit
def test_a_silent_server_leaves_the_update_to_go_ahead(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database = FideDatabase()
    monkeypatch.setattr(FideDatabase, '_source_last_modified', lambda self, url: None)
    assert database._source_changed_since(datetime.now()) is None


@pytest.mark.unit
def test_an_outdated_database_is_only_signalled_without_a_connection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database = FideDatabase()
    updates: list[dict[str, bool]] = []
    monkeypatch.setattr(
        NetworkMonitor, 'connected', classmethod(lambda cls, **_: False)
    )
    monkeypatch.setattr(
        FideDatabase, 'update', lambda self, **kwargs: updates.append(kwargs)
    )

    AutoUpdateOutdatedAction().on_outdated(database)

    assert not updates
    assert database.outdated_warning


@pytest.mark.unit
def test_an_outdated_database_updates_itself_with_a_connection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database = FideDatabase()
    updates: list[dict[str, bool]] = []
    monkeypatch.setattr(NetworkMonitor, 'connected', classmethod(lambda cls, **_: True))
    monkeypatch.setattr(
        FideDatabase, 'update', lambda self, **kwargs: updates.append(kwargs)
    )

    AutoUpdateOutdatedAction().on_outdated(database)

    assert updates == [{'notify': False}]
    assert not database.outdated_warning


def _run_update(
    monkeypatch: pytest.MonkeyPatch,
    published_at: datetime,
    copy_published_at: datetime | None,
    force: bool,
) -> bool:
    """Runs an update of an installed copy against a server publishing at
    *published_at*, and tells whether the source was downloaded."""
    if FIDE_SOURCE != FideSource.OFFICIAL_LIST:
        pytest.skip('the ready-made database carries no publication date')
    database = FideDatabase()
    downloads: list[Path] = []

    def download(self: FideDatabase, source_file_dir: Path) -> bool:
        downloads.append(source_file_dir)
        return False

    monkeypatch.setattr(NetworkMonitor, 'connected', classmethod(lambda cls, **_: True))
    monkeypatch.setattr(FideDatabase, '_source_published_at', lambda self: published_at)
    monkeypatch.setattr(FideDatabase, 'exists', lambda self: True)
    monkeypatch.setattr(FideDatabase, '_mark_updated', lambda self, published_at: None)
    monkeypatch.setattr(
        FideDatabase, 'publish_database_status_updated', classmethod(lambda cls: None)
    )
    monkeypatch.setattr(FideDatabase, '_download_source_file', download)
    stored_database = database.default_stored_database
    stored_database.updated_at = datetime.now().timestamp()
    stored_database.published_at = (
        copy_published_at.timestamp() if copy_published_at is not None else None
    )
    monkeypatch.setattr(FideDatabase, '_stored_source_database', stored_database)
    monkeypatch.setattr(FideDatabase, 'is_updating', False)
    monkeypatch.setattr(FideDatabase, 'update_status', None)
    monkeypatch.setattr(FideDatabase, 'max_update_time', None)

    database._update(force=force)

    return bool(downloads)


@pytest.mark.unit
def test_an_update_keeps_a_copy_of_what_the_server_still_publishes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    published_at = datetime.now(UTC) - timedelta(days=1)
    assert not _run_update(monkeypatch, published_at, published_at, force=False)


@pytest.mark.unit
def test_an_update_rebuilds_a_copy_older_than_what_the_server_publishes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    published_at = datetime.now(UTC) - timedelta(days=1)
    assert _run_update(
        monkeypatch, published_at, published_at - timedelta(days=1), force=False
    )


@pytest.mark.unit
def test_an_update_rebuilds_a_copy_of_unknown_publication(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    published_at = datetime.now(UTC) - timedelta(days=1)
    assert _run_update(monkeypatch, published_at, None, force=False)


@pytest.mark.unit
def test_a_forced_update_rebuilds_a_current_copy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    published_at = datetime.now(UTC) - timedelta(days=1)
    assert _run_update(monkeypatch, published_at, published_at, force=True)
