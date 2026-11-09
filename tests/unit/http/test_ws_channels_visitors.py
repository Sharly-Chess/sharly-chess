"""Which event sockets a visitor on the network may open.

Kept apart from the administrator's tests: closing a visitor's client shuts the
application down for any client of the same module.
"""

from collections.abc import Iterator

import pytest
from litestar.exceptions import WebSocketDisconnect
from litestar.testing import TestClient

from tests.unit.http.events import EventUnderTest

PUBLIC_EVENT_ID = 'test-ws-visitors-public'
PRIVATE_EVENT_ID = 'test-ws-visitors-private'


@pytest.fixture
def events() -> Iterator[None]:
    public = EventUnderTest(PUBLIC_EVENT_ID)
    private = EventUnderTest(PRIVATE_EVENT_ID)
    public.create(event={'public': True})
    private.create(event={'public': False})
    yield
    public.delete()
    private.delete()


@pytest.mark.unit
def test_a_visitor_opens_the_screen_socket_of_a_public_event(
    lan: TestClient, events: None
) -> None:
    with lan.websocket_connect(f'/ws/event/{PUBLIC_EVENT_ID}/screens'):
        pass


@pytest.mark.unit
@pytest.mark.parametrize(
    'path',
    [f'/ws/event/{PRIVATE_EVENT_ID}/screens', f'/ws/event/{PRIVATE_EVENT_ID}'],
)
def test_a_visitor_cannot_open_the_sockets_of_a_private_event(
    lan: TestClient, events: None, path: str
) -> None:
    with pytest.raises(WebSocketDisconnect), lan.websocket_connect(path):
        pass
