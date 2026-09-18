"""The application, driven over HTTP in this process.

Litestar's test client calls the same handlers the server does, without
a browser or a socket, so the answers to a bad form or a missing record
can be asserted in a millisecond.
"""

from collections.abc import Iterator
from typing import Any

import pytest
from litestar import Litestar
from litestar.testing import TestClient
from litestar.types import Receive, Scope, Send

from common.logger import set_logging_config
from common.network import LOCALHOST_IP
from tests.unit.http.client import ApiClient
from web.server_engine import ServerEngine


class FromLocalhost:
    """The application grants the machine it runs on the administrator's
    rights, and the test client calls itself ``testclient``."""

    def __init__(self, app: Any) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope['type'] in ('http', 'websocket'):
            scope['client'] = (LOCALHOST_IP, 0)
        await self.app(scope, receive, send)


class FromTheNetwork:
    """A visitor on the venue's network, who is granted nothing the
    application does not grant every client."""

    def __init__(self, app: Any) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope['type'] in ('http', 'websocket'):
            scope['client'] = (LAN_IP, 0)
        await self.app(scope, receive, send)


LAN_IP = '192.168.1.25'


@pytest.fixture(scope='module')
def app() -> Litestar:
    return ServerEngine(handle_signals=False).build_app(set_logging_config())


@pytest.fixture(scope='module')
def http(app: Litestar) -> Iterator[TestClient]:
    with TestClient(FromLocalhost(app)) as client:
        yield client


@pytest.fixture
def lan(app: Litestar) -> Iterator[TestClient]:
    """A client of its own, so a session signed in by one test is not
    carried into the next."""
    with TestClient(FromTheNetwork(app)) as client:
        yield client


@pytest.fixture(scope='module')
def api(http: TestClient) -> ApiClient:
    return ApiClient(http)
