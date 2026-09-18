"""Creating, renaming and archiving an event, over HTTP."""

from collections.abc import Iterator

import pytest
from litestar.testing import TestClient

from data.loader import EventLoader
from database.sqlite.event.event_database import EventDatabase
from tests.test_config import TestUtils

EVENT_ID = 'test-events-http'
RENAMED_EVENT_ID = 'test-events-http-renamed'


@pytest.fixture
def cleanup() -> Iterator[None]:
    yield
    for event_id in (EVENT_ID, RENAMED_EVENT_ID):
        EventLoader.unload_event(event_id)
        # One of the two ran, and which one is what the test was about.
        if EventDatabase(event_id).file.exists():
            EventDatabase(event_id).delete()


def current_events(http: TestClient) -> str:
    response = http.get('/current_events')
    assert response.status_code == 200
    return response.text


@pytest.mark.unit
def test_the_home_page_is_served(http: TestClient):
    response = http.get('/')
    assert response.status_code == 200
    assert '<title>Sharly Chess</title>' in response.text


@pytest.mark.unit
def test_an_event_is_created_and_then_archived(http: TestClient, cleanup: None):
    created = http.post(
        '/current_events/create-event',
        data={'name': EVENT_ID, 'federation': 'FRA'},
    )
    assert created.status_code == 200
    assert EVENT_ID in current_events(http)

    event = EventLoader().load_event(EVENT_ID)
    EventLoader.unload_event(EVENT_ID)
    archived = http.delete(
        f'/current_events/event-delete/{event.uniq_id}', params={'archive': 'on'}
    )
    assert archived.status_code == 200
    assert (
        http.get(f'/event/{EVENT_ID}/tournaments', follow_redirects=False).status_code
        == 302
    )


@pytest.mark.unit
def test_an_event_keeps_its_contents_when_its_id_changes(
    http: TestClient, cleanup: None
):
    """The id is in every link to the event, so renaming is its own
    form rather than a field of the event's."""
    TestUtils.create_event(EVENT_ID)
    TestUtils.create_tournament(EVENT_ID, 'A tournament')

    response = http.patch(
        f'/event-uniq-id-update/{EVENT_ID}', data={'uniq_id': RENAMED_EVENT_ID}
    )
    assert response.status_code == 200

    EventLoader.unload_event(EVENT_ID)
    renamed = EventLoader().load_event(RENAMED_EVENT_ID)
    assert list(renamed.tournaments_by_name) == ['A tournament']
    assert http.get(f'/event/{RENAMED_EVENT_ID}/tournaments').status_code == 200


@pytest.mark.unit
def test_an_oauth_callback_without_a_state_goes_home(http: TestClient):
    """The identity provider answers with whatever it was given; a reply
    to a request this installation never made is sent to the home page
    rather than acted on."""
    response = http.get(
        '/sce/oauth/callback/import-event',
        params={
            'code': 'test-code',
            'state': 'unknown-state',
            'event_id': 'test-event-id',
        },
        follow_redirects=False,
    )
    assert response.status_code == 302
    assert response.headers['location'] == '/'
