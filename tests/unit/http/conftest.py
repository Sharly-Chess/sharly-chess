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
from common.sharly_chess_config import SharlyChessConfig
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


class FromTheInternet:
    """A visitor who reached the server through the tunnel.

    The tunnel client runs on the machine it exposes, so its requests arrive
    from the loopback address exactly as the local browser's do. What tells
    them apart is the listener they land on, so that is what is dressed up
    here — the address is left as loopback on purpose, because a test that
    faked a distant address would not be testing what the application reads.
    """

    def __init__(self, app: Any) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope['type'] in ('http', 'websocket'):
            scope['client'] = (LOCALHOST_IP, 0)
            scope['server'] = (LOCALHOST_IP, TUNNEL_PORT)
        await self.app(scope, receive, send)


LAN_IP = '192.168.1.25'

#: The listener the tunnel client connects to. Nothing binds it in this tier;
#: the application only ever compares it with what it recorded at startup.
TUNNEL_PORT = 19000


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


@pytest.fixture
def remote(app: Litestar) -> Iterator[TestClient]:
    """A visitor from the internet, for the same reason as `lan`."""
    config = SharlyChessConfig()
    previous = config.web_tunnel_port
    config.web_tunnel_port = TUNNEL_PORT
    try:
        with TestClient(FromTheInternet(app)) as client:
            yield client
    finally:
        config.web_tunnel_port = previous


@pytest.fixture(scope='module')
def api(http: TestClient) -> ApiClient:
    return ApiClient(http)
