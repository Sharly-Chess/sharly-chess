"""A request the browser drops before its body has arrived, as htmx does
when a newer request replaces it, is not an error of the application."""

import asyncio
import logging
from collections.abc import Coroutine, Iterator
from concurrent.futures import ThreadPoolExecutor
from typing import Any

import pytest
from litestar import Litestar
from litestar.types import Message

from common import APP_NAME
from tests.unit.http.conftest import FromLocalhost
from tests.unit.http.events import EventUnderTest

EVENT_ID = 'test-cancelled-requests-http'


def _run[T](coroutine: Coroutine[Any, Any, T]) -> T:
    """Drive a coroutine to completion on a loop of its own, out of the
    loops pytest-asyncio and playwright already own."""
    with ThreadPoolExecutor(max_workers=1) as executor:
        return executor.submit(asyncio.run, coroutine).result()


class _Records(logging.Handler):
    def __init__(self) -> None:
        super().__init__(logging.DEBUG)
        self.records: list[logging.LogRecord] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(record)


@pytest.fixture
def event() -> Iterator[None]:
    under_test = EventUnderTest(EVENT_ID)
    under_test.create()
    yield
    under_test.delete()


@pytest.fixture
def records() -> Iterator[list[logging.LogRecord]]:
    handler = _Records()
    loggers = [logging.getLogger('litestar'), logging.getLogger(APP_NAME)]
    levels = [logger.level for logger in loggers]
    for logger in loggers:
        logger.addHandler(handler)
        logger.setLevel(logging.DEBUG)
    yield handler.records
    for logger, level in zip(loggers, levels, strict=True):
        logger.removeHandler(handler)
        logger.setLevel(level)


async def _post_then_disconnect(app: Litestar, path: str) -> list[Message]:
    scope: dict[str, Any] = {
        'type': 'http',
        'asgi': {'version': '3.0'},
        'http_version': '1.1',
        'method': 'POST',
        'scheme': 'http',
        'path': path,
        'raw_path': path.encode(),
        'root_path': '',
        'query_string': b'',
        'headers': [
            (b'host', b'testserver'),
            (b'content-type', b'application/x-www-form-urlencoded'),
            (b'hx-request', b'true'),
        ],
        'client': ('127.0.0.1', 0),
        'server': ('testserver', 80),
        'state': {},
    }
    sent: list[Message] = []

    async def receive() -> Message:
        return {'type': 'http.disconnect'}

    async def send(message: Message) -> None:
        sent.append(message)

    await FromLocalhost(app)(scope, receive, send)  # type: ignore[arg-type]
    return sent


@pytest.mark.unit
def test_a_cancelled_request_is_not_logged_as_an_error(
    app: Litestar, event: None, records: list[logging.LogRecord]
) -> None:
    _run(_post_then_disconnect(app, f'/ffe/team-auth/{EVENT_ID}'))

    assert [r for r in records if r.levelno >= logging.ERROR] == []
    assert any(
        r.getMessage().startswith('Request cancelled by the client') for r in records
    )
