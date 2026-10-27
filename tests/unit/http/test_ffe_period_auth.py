"""The FFE credentials of a period answer in the period's own names.

The auth check replaces the block it was asked from, so a check made for
a rating period has to come back named for that period — otherwise the
period's fields turn into the tournament's, and the form ends up with
two of each.
"""

from collections.abc import Iterator

import pytest
from litestar.testing import TestClient

from data.loader import EventLoader
from tests.test_config import TestUtils

EVENT_ID = 'test-ffe-period-auth'
TOURNAMENT_NAME = 'test-ffe-period-auth-tournament'


@pytest.fixture
def event() -> Iterator[str]:
    TestUtils.create_event(EVENT_ID)
    TestUtils.create_tournament(EVENT_ID, TOURNAMENT_NAME, overrides={'rounds': 4})
    yield EVENT_ID
    EventLoader.unload_event(EVENT_ID)
    TestUtils.delete_event(EVENT_ID)


@pytest.mark.unit
def test_a_period_s_check_answers_in_its_own_names(http: TestClient, event: str):
    response = http.post(
        f'/ffe/test-auth/{event}',
        data={
            'ffe_id_period_3': '49944',
            'ffe_password_period_3': 'ABCDEFGHIJ',
            'ffe_password_visible': 'false',
            'field_suffix': '_period_3',
        },
    )
    assert response.status_code == 200
    assert 'name="ffe_id_period_3"' in response.text
    assert 'name="ffe_id"' not in response.text


@pytest.mark.unit
def test_the_tournament_s_check_answers_in_the_plain_ones(http: TestClient, event: str):
    response = http.post(
        f'/ffe/test-auth/{event}',
        data={
            'ffe_id': '49943',
            'ffe_password': 'ABCDEFGHIJ',
            'ffe_password_visible': 'false',
        },
    )
    assert response.status_code == 200
    assert 'name="ffe_id"' in response.text
    assert 'name="ffe_id_period_' not in response.text
