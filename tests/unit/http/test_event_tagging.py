"""Tags: a registry of the installation, worn by events.

They are created in a modal of their own, selected on an event, and used
to narrow the event list. The filter is kept in the session, so it holds
across the pages that follow.
"""

from collections.abc import Iterator

import pytest
from litestar.testing import TestClient

from data.loader import EventLoader
from database.sqlite.config.config_database import ConfigDatabase
from tests.test_config import TestUtils

EVENT_ID = 'test-tags-http'
OTHER_EVENT_ID = 'test-tags-http-untagged'
TAG_NAME = 'Youth'
SECOND_TAG_NAME = 'Blitz'


@pytest.fixture
def events(http: TestClient) -> Iterator[None]:
    TestUtils.create_event(EVENT_ID)
    TestUtils.create_event(OTHER_EVENT_ID)
    clear_tags(http)
    yield
    clear_tags(http)
    for event_id in (EVENT_ID, OTHER_EVENT_ID):
        EventLoader.unload_event(event_id)
        TestUtils.delete_event(event_id)


def stored_tags() -> list:
    with ConfigDatabase() as database:
        return database.load_stored_tags()


def clear_tags(http: TestClient) -> None:
    for tag in stored_tags():
        assert http.post(f'/tag/delete/{tag.id}').status_code == 200


def create_tag(http: TestClient, name: str, add_another: bool = False):
    data = {'tag_name': name, 'tag_color': '#123456'}
    if add_another:
        data['add_other'] = 'on'
    response = http.post('/tag/create', data=data)
    assert response.status_code == 200
    return response


def tag_id(name: str) -> int:
    return next(tag.id for tag in stored_tags() if tag.name == name)


def events_listed(http: TestClient, **params: str) -> str:
    response = http.get('/current_events', params=params)
    assert response.status_code == 200
    return response.text


@pytest.mark.unit
def test_a_tag_is_created_and_deleted(http: TestClient, events: None):
    create_tag(http, TAG_NAME)
    assert [tag.name for tag in stored_tags()] == [TAG_NAME]

    response = http.post(f'/tag/delete/{tag_id(TAG_NAME)}')
    assert response.status_code == 200
    assert stored_tags() == []


@pytest.mark.unit
def test_creating_and_adding_another_leaves_the_form_open(
    http: TestClient, events: None
):
    """The second tag is entered into the form the first one left open,
    rather than reached through the list again."""
    response = create_tag(http, TAG_NAME, add_another=True)
    assert 'tag-name' in response.text
    assert [tag.name for tag in stored_tags()] == [TAG_NAME]


@pytest.mark.unit
def test_an_event_wears_the_tag_it_was_given(http: TestClient, events: None):
    create_tag(http, TAG_NAME)
    identifier = tag_id(TAG_NAME)
    response = http.patch(
        f'/event-update/{EVENT_ID}',
        data={'name': EVENT_ID, 'federation': 'FRA', 'tags': str(identifier)},
    )
    assert response.status_code == 200

    EventLoader.unload_event(EVENT_ID)
    assert EventLoader().load_event(EVENT_ID).tag_ids == [identifier]
    assert TAG_NAME in events_listed(http)


@pytest.mark.unit
def test_the_filter_narrows_the_list_and_lets_it_back(http: TestClient, events: None):
    create_tag(http, TAG_NAME)
    identifier = tag_id(TAG_NAME)
    http.patch(
        f'/event-update/{EVENT_ID}',
        data={'name': EVENT_ID, 'federation': 'FRA', 'tags': str(identifier)},
    )

    filtered = events_listed(http, filter_tags=str(identifier))
    assert EVENT_ID in filtered
    assert OTHER_EVENT_ID not in filtered

    # The filter is remembered, so the next page is narrowed too.
    assert OTHER_EVENT_ID not in events_listed(http)

    cleared = events_listed(http, filter_tags='')
    assert OTHER_EVENT_ID in cleared


@pytest.mark.unit
def test_a_deleted_tag_stops_showing_on_the_events(http: TestClient, events: None):
    """The registry is what the list reads, so a tag deleted from it
    leaves the events that wore it."""
    create_tag(http, TAG_NAME)
    identifier = tag_id(TAG_NAME)
    http.patch(
        f'/event-update/{EVENT_ID}',
        data={'name': EVENT_ID, 'federation': 'FRA', 'tags': str(identifier)},
    )

    assert http.post(f'/tag/delete/{identifier}').status_code == 200
    assert TAG_NAME not in events_listed(http)


@pytest.mark.unit
def test_an_empty_registry_proposes_ready_made_sets(http: TestClient, events: None):
    """Nobody starts with tags, so the manager offers a few sets rather
    than an empty box."""
    response = http.post('/tag/manager')
    assert response.status_code == 200
    assert 'tag/add-sets' in response.text
