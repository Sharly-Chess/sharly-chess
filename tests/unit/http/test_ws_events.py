"""The events the open pages receive over the websocket."""

import json
from typing import Any

from litestar.testing import TestClient

from web.channels import channels_plugin, publish_ws_event


async def _publish_and_receive() -> dict[str, Any]:
    async with channels_plugin.start_subscription(['ws']) as subscriber:
        publish_ws_event('admin-theme-updated', {'theme': 'light'})
        async for raw_event in subscriber.iter_events():
            return json.loads(raw_event)
    raise AssertionError('The subscription ended without an event.')


def test_an_event_is_published_with_its_detail(http: TestClient) -> None:
    with http.portal() as portal:
        message = portal.call(_publish_and_receive)
    assert message == {
        'event': 'admin-theme-updated',
        'data': {'detail': {'theme': 'light'}},
    }
