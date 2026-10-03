"""Which source a national list with an installed copy and an online
source is read from."""

from types import SimpleNamespace

import pytest

from data.input_output.managers import DataSourceManager


def _sources(monkeypatch, read_online: bool, installed: bool = True):
    stored = SimpleNamespace(read_online=read_online)
    installed_source = (
        SimpleNamespace(database=SimpleNamespace(stored_source_database=stored))
        if installed
        else None
    )
    online_source = SimpleNamespace()
    monkeypatch.setattr(
        DataSourceManager,
        'installed_and_online_sources',
        lambda self, national_source_id: (installed_source, online_source),
    )
    return installed_source, online_source


@pytest.mark.unit
def test_the_installed_copy_is_read_by_default(monkeypatch):
    installed, __ = _sources(monkeypatch, read_online=False)
    manager = DataSourceManager()
    assert manager.list_source('ffe') is installed
    assert not manager.reads_online('ffe')


@pytest.mark.unit
def test_the_online_source_is_read_when_chosen(monkeypatch):
    installed, online = _sources(monkeypatch, read_online=True)
    manager = DataSourceManager()
    assert manager.list_source('ffe') is online
    assert manager.list_source('ffe', installed_only=True) is installed


@pytest.mark.unit
def test_the_online_source_stands_in_for_a_missing_copy(monkeypatch):
    __, online = _sources(monkeypatch, read_online=False, installed=False)
    manager = DataSourceManager()
    assert manager.list_source('ffe') is online
    assert manager.reads_online('ffe')
