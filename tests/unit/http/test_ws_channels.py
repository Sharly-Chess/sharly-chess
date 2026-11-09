"""Which websocket events the pages of an event receive."""

from collections.abc import Iterator
from typing import Any

import pytest
from litestar.testing import TestClient
from litestar.testing.websocket_test_session import WebSocketTestSession

from tests.unit.http.events import EventUnderTest
from web.channels import publish_ws_event

EVENT_ID = 'test-ws-channels'
OTHER_EVENT_ID = 'test-ws-channels-other'
PROBE = 'probe'


@pytest.fixture
def events() -> Iterator[None]:
    created = [EventUnderTest(EVENT_ID), EventUnderTest(OTHER_EVENT_ID)]
    for event in created:
        event.create()
    yield
    for event in created:
        event.delete()


def publish(http: TestClient, event: str, event_uniq_id: str | None = None) -> None:
    async def _publish() -> None:
        publish_ws_event(event, event_uniq_id=event_uniq_id)

    with http.portal() as portal:
        portal.call(_publish)


def wait_until_subscribed(http: TestClient, socket: WebSocketTestSession) -> None:
    """The socket is accepted before its subscription starts: what is published
    in between never reaches it."""
    for _ in range(50):
        publish(http, PROBE, EVENT_ID)
        try:
            socket.receive_json(timeout=0.1)
        except TimeoutError:
            continue
        return
    raise AssertionError('The socket never subscribed.')


def receive(socket: WebSocketTestSession) -> dict[str, Any]:
    while (message := socket.receive_json(timeout=1))['event'] == PROBE:
        pass
    return message


@pytest.mark.unit
def test_a_screen_receives_only_the_events_of_its_event(
    http: TestClient, events: None
) -> None:
    with http.websocket_connect(f'/ws/event/{EVENT_ID}/screens') as socket:
        wait_until_subscribed(http, socket)
        publish(http, 'plugins-updated')
        publish(http, f'new-checkins|{OTHER_EVENT_ID}', OTHER_EVENT_ID)
        publish(http, f'new-checkins|{EVENT_ID}', EVENT_ID)
        assert receive(socket) == {'event': f'new-checkins|{EVENT_ID}', 'data': ''}


@pytest.mark.unit
def test_an_admin_page_of_an_event_also_receives_the_events_of_the_application(
    http: TestClient, events: None
) -> None:
    with http.websocket_connect(f'/ws/event/{EVENT_ID}') as socket:
        wait_until_subscribed(http, socket)
        publish(http, f'new-checkins|{OTHER_EVENT_ID}', OTHER_EVENT_ID)
        publish(http, 'plugins-updated')
        publish(http, f'new-checkins|{EVENT_ID}', EVENT_ID)
        assert [receive(socket)['event'] for _ in range(2)] == [
            'plugins-updated',
            f'new-checkins|{EVENT_ID}',
        ]


@pytest.mark.unit
def test_a_page_outside_any_event_receives_only_the_events_of_the_application(
    http: TestClient, events: None
) -> None:
    with http.websocket_connect('/ws') as socket:
        for _ in range(50):
            publish(http, PROBE)
            try:
                socket.receive_json(timeout=0.1)
            except TimeoutError:
                continue
            break
        publish(http, f'new-checkins|{EVENT_ID}', EVENT_ID)
        publish(http, 'plugins-updated')
        assert receive(socket)['event'] == 'plugins-updated'
