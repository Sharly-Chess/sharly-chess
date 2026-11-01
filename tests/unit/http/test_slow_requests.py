"""Slow requests are written to the log, as the server and as the browser
timed them."""

import asyncio
from collections.abc import Coroutine
from concurrent.futures import ThreadPoolExecutor
from logging import WARNING
from typing import Any
from unittest.mock import patch

import pytest
from litestar.testing import TestClient

from web.performance import PerformanceMiddleware


def _run[T](coroutine: Coroutine[Any, Any, T]) -> T:
    """Drive a coroutine to completion on a loop of its own, out of the
    way of the loops pytest-asyncio and playwright already own."""
    with ThreadPoolExecutor(max_workers=1) as executor:
        return executor.submit(asyncio.run, coroutine).result()


def _serve(delay: float, log_all: bool = False) -> list[tuple]:
    async def app(scope: Any, receive: Any, send: Any) -> None:
        await asyncio.sleep(delay)
        await send({'type': 'http.response.start', 'status': 200, 'headers': []})
        await send({'type': 'http.response.body', 'body': b'ok'})

    async def receive() -> Any:
        return {'type': 'http.request'}

    async def send(message: Any) -> None:
        pass

    scope: Any = {
        'type': 'http',
        'method': 'GET',
        'path': '/view/screen/event/screen',
        'client': ('192.168.1.2', 50000),
    }
    with (
        patch.object(PerformanceMiddleware, 'SLOW_REQUEST_SECONDS', 0.05),
        patch('web.performance.logger.log') as log,
    ):
        _run(PerformanceMiddleware(app, log_all=log_all)(scope, receive, send))
    return [call.args for call in log.call_args_list]


@pytest.mark.unit
def test_a_slow_request_is_logged_with_its_client():
    [args] = _serve(0.1)
    assert args[0] == WARNING
    assert '192.168.1.2' in args
    assert '/view/screen/event/screen' in args


@pytest.mark.unit
def test_a_quick_request_is_logged_only_when_profiling():
    assert _serve(0) == []
    assert len(_serve(0, log_all=True)) == 1


@pytest.mark.unit
def test_a_page_reports_the_phases_of_a_slow_request(http: TestClient):
    with patch('web.controllers.index_controller.logger.warning') as warning:
        response = http.post(
            '/slow-request',
            json={
                'url': '/view/screen/event/screen\nforged line',
                'kind': 'xmlhttprequest',
                'total': 12000,
                'queued': 0,
                'before_request': 11500,
                'connect': 0,
                'server': 400,
                'download': 100,
                'transfer_size': 0,
            },
        )
    assert response.status_code == 204
    args = warning.call_args.args
    assert '/view/screen/event/screen\\nforged line' in args
    assert 11500 in args
