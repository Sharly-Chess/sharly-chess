"""Generating rating-band prize categories, over HTTP.

The bands are generated from a form with four fields that constrain each
other, and the arbiter meets the refusals more often than the success.
"""

from collections.abc import Iterator

import pytest
from litestar.testing import TestClient

from tests.unit.http.events import EventUnderTest

EVENT_ID = 'test-prizes-http'
TOURNAMENT_NAME = 'test-prizes-http-tournament'

EVENT = EventUnderTest(EVENT_ID, TOURNAMENT_NAME)


@pytest.fixture
def prize_group(http: TestClient) -> Iterator[tuple[int, int]]:
    """A tournament with players and an empty prize group to fill."""
    EVENT.create(json_file='tec-swiss')
    tournament = EVENT.tournament()
    assert tournament.id is not None
    response = http.post(f'/prizes/prize-group/create/{EVENT_ID}/{tournament.id}')
    assert response.status_code == 200
    group_id = next(iter(EVENT.tournament().prize_groups)).id
    assert group_id is not None
    yield tournament.id, group_id
    EVENT.delete()


def generate(
    http: TestClient, prize_group: tuple[int, int], **fields: str
) -> tuple[str, int]:
    tournament_id, group_id = prize_group
    response = http.post(
        f'/prizes/prize-categories/generate-rating/'
        f'{EVENT_ID}/{tournament_id}/{group_id}',
        data={
            'rating_min': '1400',
            'rating_max': '2200',
            'method': 'groups',
            'group_count': '2',
        }
        | fields,
    )
    assert response.status_code == 200
    group = next(iter(EVENT.tournament().prize_groups))
    return response.text, len(group.sorted_categories)


@pytest.mark.unit
def test_the_bands_need_both_ends_of_the_range(
    http: TestClient, prize_group: tuple[int, int]
):
    text, categories = generate(http, prize_group, rating_max='')
    assert 'A minimum and a maximum rating are expected.' in text
    assert categories == 0


@pytest.mark.unit
def test_the_range_runs_upwards(http: TestClient, prize_group: tuple[int, int]):
    text, categories = generate(http, prize_group, rating_min='2200', rating_max='1400')
    assert 'Minimum rating is expected to be lower than the maximum rating.' in text
    assert categories == 0


@pytest.mark.unit
def test_the_range_is_split_into_at_least_one_group(
    http: TestClient, prize_group: tuple[int, int]
):
    text, categories = generate(http, prize_group, group_count='0')
    assert 'A positive number of groups is expected.' in text
    assert categories == 0


@pytest.mark.unit
def test_a_range_nobody_is_rated_in_is_sent_to_the_other_method(
    http: TestClient, prize_group: tuple[int, int]
):
    """Splitting an empty range in three yields three empty categories,
    so the form says which method does work here."""
    text, categories = generate(http, prize_group, rating_min='3000', rating_max='3500')
    assert 'use the rating step method instead' in text
    assert categories == 0


@pytest.mark.unit
def test_the_step_method_needs_a_step(http: TestClient, prize_group: tuple[int, int]):
    text, categories = generate(http, prize_group, method='step', step='0')
    assert 'A positive rating step is expected.' in text
    assert categories == 0


@pytest.mark.unit
def test_a_range_the_form_accepts_is_split_into_bands(
    http: TestClient, prize_group: tuple[int, int]
):
    _text, categories = generate(http, prize_group, group_count='3')
    assert categories == 3
