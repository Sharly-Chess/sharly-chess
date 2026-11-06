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


FOLLOWS = 'window.scFollowsApplicationTheme = true;'
KEEPS_ITS_OWN = 'window.scFollowsApplicationTheme = false;'
ADMIN_INTERFACE = """.attr('data-sc-interface', "admin")"""


def test_a_local_admin_page_follows_the_theme_of_the_application(
    http: TestClient,
) -> None:
    page = http.get('/home').text
    assert ADMIN_INTERFACE in page
    assert FOLLOWS in page


def test_an_admin_page_over_the_network_keeps_its_own_theme(lan: TestClient) -> None:
    page = lan.get('/home').text
    assert ADMIN_INTERFACE in page
    assert KEEPS_ITS_OWN in page


def test_the_page_of_the_application_window_keeps_its_own_theme(
    http: TestClient,
) -> None:
    assert KEEPS_ITS_OWN in http.get('/plugins?embedded=1').text
