"""The check-in screen, rendered in this process.

Each row of the screen is a player; it opens the check-in modal while the
check-in is open, and shows whether the player has arrived.
"""

from collections.abc import Iterator

import pytest
from AdvancedHTMLParser import AdvancedHTMLParser, AdvancedTag
from litestar.testing import TestClient

from data.tournament import Tournament
from tests.test_config import ScreenType, TestUtils
from tests.unit.http.client import ApiClient
from tests.unit.http.events import EventUnderTest

EVENT_ID = 'test-check-in-http'
TOURNAMENT_NAME = 'test-check-in-http-tournament'
SCREEN_ID = 'test-check-in-http-screen'

EVENT = EventUnderTest(EVENT_ID, TOURNAMENT_NAME)


@pytest.fixture
def tournament(api: ApiClient) -> Iterator[Tournament]:
    EVENT.create(json_file='test-screens-unpaired')
    tournament = EVENT.tournament()
    TestUtils.create_screen(
        api,
        EVENT_ID,
        SCREEN_ID,
        ScreenType.CHECK_IN,
        {'init_set_tournament_id': tournament.id},
    )
    yield tournament
    EVENT.delete()


def player_rows(http: TestClient) -> list[AdvancedTag]:
    response = http.get(f'/view/screen/{EVENT_ID}/{SCREEN_ID}')
    assert response.status_code == 200
    parser = AdvancedHTMLParser()
    parser.parseStr(response.text)
    return [
        element
        for element in parser.getElementsByTagName('div')
        if 'player-row' in (element.getAttribute('class') or '').split()
    ]


def row_for(name: str, http: TestClient) -> str:
    rows = [row for row in player_rows(http) if name in row.textContent]
    assert len(rows) == 1
    return rows[0].getHTML()


@pytest.mark.unit
def test_every_player_has_a_row(http: TestClient, tournament: Tournament):
    assert len(player_rows(http)) == 16


@pytest.mark.unit
def test_a_row_opens_the_modal_and_shows_the_arrival(
    http: TestClient, tournament: Tournament
):
    before = row_for('AMOS', http)
    assert 'checkin-modal' in before
    assert 'bi-square' in before
    assert 'bi-check-square-fill' not in before

    amos = next(
        player for player in tournament.tournament_players if player.last_name == 'AMOS'
    )
    response = http.patch(
        f'/view/toggle-check-in/1/{EVENT_ID}/{SCREEN_ID}/{tournament.id}/{amos.id}'
    )
    assert response.status_code == 200
    assert 'bi-check-square-fill' in row_for('AMOS', http)


@pytest.mark.unit
def test_a_closed_check_in_takes_the_modal_off_the_rows(
    http: TestClient, tournament: Tournament
):
    response = http.post(f'/check-in/tournament-toggle-open/{EVENT_ID}/{tournament.id}')
    assert response.status_code == 200
    assert 'checkin-modal' not in row_for('AMOS', http)
