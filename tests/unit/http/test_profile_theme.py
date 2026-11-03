"""The theme of the administration chosen in the profile.

The server shows the theme set in the application window. A client on the
network follows the appearance of its own system until it picks a theme in
its profile, which then holds for its session.
"""

import re
from collections.abc import Iterator

import pytest
from litestar.testing import TestClient

from data.loader import EventLoader
from tests.test_config import TestUtils
from tests.unit.http.client import ApiClient

EVENT_ID = 'test-profile-theme'
PROFILE_URL = f'/profile-modal/{EVENT_ID}'


@pytest.fixture(scope='module')
def event(api: ApiClient) -> Iterator[None]:
    TestUtils.create_event(EVENT_ID, overrides={'public': True})
    yield
    EventLoader.unload_event(EVENT_ID)
    TestUtils.delete_event(EVENT_ID)


def requested_theme(html: str) -> str:
    match = re.search(r'window\.scRequestedTheme = "(\w+)"', html)
    assert match, 'the page sets no theme'
    return match.group(1)


@pytest.mark.unit
def test_a_network_client_follows_its_system_by_default(
    event: None, lan: TestClient
) -> None:
    response = lan.get(PROFILE_URL)
    assert response.status_code == 200
    assert requested_theme(response.text) == 'auto'
    assert 'hx-vals="{&#34;theme&#34;: &#34;dark&#34;}"' in response.text


@pytest.mark.unit
def test_a_network_client_keeps_the_theme_it_picks(
    event: None, lan: TestClient
) -> None:
    assert requested_theme(lan.get(PROFILE_URL, params={'theme': 'light'}).text) == (
        'light'
    )
    assert requested_theme(lan.get(PROFILE_URL).text) == 'light'
    assert requested_theme(lan.get(PROFILE_URL, params={'theme': 'pink'}).text) == (
        'light'
    )


@pytest.mark.unit
def test_the_server_keeps_the_theme_of_its_window(
    event: None, http: TestClient
) -> None:
    response = http.get(PROFILE_URL, params={'theme': 'light'})
    assert requested_theme(response.text) == 'auto'
    assert '&#34;theme&#34;' not in response.text
