"""Timers and their hours, over HTTP.

A timer counts a venue down to the start of a round, and its hours are
the moments it counts to. Both are edited from modals nothing but a
browser had opened.
"""

from collections.abc import Iterator

import pytest
from litestar.testing import TestClient

from tests.unit.http.events import EventUnderTest

EVENT_ID = 'test-timers-http'
EVENT = EventUnderTest(EVENT_ID)


@pytest.fixture
def event() -> Iterator[str]:
    EVENT.create()
    yield EVENT_ID
    EVENT.delete()


def timer_names() -> list[str]:
    return [timer.name for timer in EVENT.load().timers_by_id.values()]


def create_timer(http: TestClient, **fields: str):
    return http.post(f'/timer-create/{EVENT_ID}', data={'name': 'Round one'} | fields)


@pytest.mark.unit
def test_a_timer_is_created_renamed_and_deleted(http: TestClient, event: str):
    assert create_timer(http).status_code == 200
    assert timer_names() == ['Round one']
    timer_id = next(iter(EVENT.load().timers_by_id))
    renamed = http.patch(
        f'/timer-update/{EVENT_ID}/{timer_id}', data={'name': 'Round two'}
    )
    assert renamed.status_code == 200
    assert timer_names() == ['Round two']
    deleted = http.delete(f'/timer-delete/{EVENT_ID}/{timer_id}')
    assert deleted.status_code == 200
    assert timer_names() == []


@pytest.mark.unit
def test_a_timer_needs_a_name(http: TestClient, event: str):
    response = create_timer(http, name='')
    assert response.status_code == 200
    assert 'This field is required.' in response.text
    assert timer_names() == []


@pytest.mark.unit
def test_two_timers_cannot_share_a_name(http: TestClient, event: str):
    assert create_timer(http).status_code == 200
    response = create_timer(http)
    assert response.status_code == 200
    assert 'This name is already used.' in response.text
    assert timer_names() == ['Round one']


@pytest.mark.unit
def test_a_cloned_timer_stands_beside_the_first(http: TestClient, event: str):
    create_timer(http)
    timer_id = next(iter(EVENT.load().timers_by_id))
    response = http.post(
        f'/timer-clone/{EVENT_ID}/{timer_id}', data={'name': 'Round one (copy)'}
    )
    assert response.status_code == 200
    assert sorted(timer_names()) == ['Round one', 'Round one (copy)']


@pytest.mark.unit
@pytest.mark.parametrize('action', ['update', 'clone', 'delete'])
def test_the_timer_modal_opens_for_every_action(
    http: TestClient, event: str, action: str
):
    create_timer(http)
    timer_id = next(iter(EVENT.load().timers_by_id))
    response = http.get(f'/timer-modal/{action}/{EVENT_ID}/{timer_id}')
    assert response.status_code == 200


@pytest.mark.unit
def test_the_default_colours_modal_opens(http: TestClient, event: str):
    """The delays and colours a new timer starts from belong to the
    event, not to any one timer."""
    response = http.get(f'/default-timers-modal/{EVENT_ID}')
    assert response.status_code == 200


@pytest.mark.unit
def test_the_hours_of_a_timer_are_listed(http: TestClient, event: str):
    create_timer(http)
    timer_id = next(iter(EVENT.load().timers_by_id))
    response = http.get(f'/timer-hours-modal/{EVENT_ID}/{timer_id}')
    assert response.status_code == 200
