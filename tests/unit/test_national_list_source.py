"""The order a list with an installed copy and an online version is read
in, and its fallback from one to the other."""

import asyncio
from collections.abc import Coroutine
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
from typing import Any

import pytest

from common.exception import SharlyChessException
from data.input_output.data_source import LocalDataSource, installed_copies_only


def _run[T](coroutine: Coroutine[Any, Any, T]) -> T:
    """Drive a coroutine to completion on a loop of its own, out of the
    way of the loops pytest-asyncio and playwright already own."""
    with ThreadPoolExecutor(max_workers=1) as executor:
        return executor.submit(asyncio.run, coroutine).result()


def _source(online_first: bool, installed: bool = True, online: bool = True) -> Any:
    return SimpleNamespace(
        name='FFE',
        is_installed=installed,
        online_version=SimpleNamespace(is_available=online),
        tries_online_first=online_first,
    )


def _read(source: Any, installed_answer: Any, online_answer: Any) -> Any:
    async def read_installed() -> Any:
        if isinstance(installed_answer, Exception):
            raise installed_answer
        return installed_answer

    async def read_online(__: Any) -> Any:
        if isinstance(online_answer, Exception):
            raise online_answer
        return online_answer

    return _run(LocalDataSource.first_answer(source, read_installed, read_online))


@pytest.mark.unit
def test_the_installed_copy_is_read_first_by_default():
    assert _read(_source(online_first=False), 'installed', 'online') == 'installed'


@pytest.mark.unit
def test_the_online_version_is_read_first_when_set():
    assert _read(_source(online_first=True), 'installed', 'online') == 'online'


@pytest.mark.unit
def test_the_other_one_stands_in_when_the_first_fails_or_finds_nothing():
    source = _source(online_first=True)
    assert _read(source, 'installed', SharlyChessException('offline')) == 'installed'
    assert _read(source, 'installed', None) == 'installed'
    assert (
        _read(_source(online_first=False, installed=False), None, 'online') == 'online'
    )


@pytest.mark.unit
def test_a_check_on_installed_copies_never_reads_online():
    async def read_installed() -> Any:
        return None

    async def read_online(__: Any) -> Any:
        return 'online'

    async def check() -> Any:
        with installed_copies_only():
            return await LocalDataSource.first_answer(
                _source(online_first=True), read_installed, read_online
            )

    def read() -> Any:
        return asyncio.run(check())

    with ThreadPoolExecutor(max_workers=1) as executor:
        assert executor.submit(read).result() is None
