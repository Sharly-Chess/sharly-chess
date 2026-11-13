"""The round-robin grid screens: every player of a round robin against every other,
or every team, with the results of the games played and the rounds of those
to come. Only round robins can be shown on them.

Built on the TEC round-robin fixture (6 players, 5 rounds, every game
played), whose results of rounds 4 and 5 are cleared to leave them to play.
"""

import contextlib
from collections.abc import Iterator

import pytest
from AdvancedHTMLParser import AdvancedHTMLParser
from litestar.testing import TestClient

from data.loader import EventLoader
from data.pairings.round_robin_grid import player_grid, team_grid
from database.sqlite.event.event_database import EventDatabase
from database.sqlite.event.event_store import (
    StoredTournament,
)
from tests.test_config import ScreenType, TestUtils
from tests.unit.http.client import ApiClient
from tests.unit.http.conftest import TEAM_EVENT_ID
from utils.enum import Result

EVENT_ID = 'test-round-robin-grid-screen-http'
UNPLAYED_ROUNDS = (4, 5)


def load_event():
    with contextlib.suppress(KeyError):
        EventLoader.unload_event(EVENT_ID)
    return EventLoader().load_event(EVENT_ID)


@pytest.fixture
def round_robin() -> Iterator[StoredTournament]:
    TestUtils.create_event(EVENT_ID)
    stored = TestUtils.create_tournament(
        EVENT_ID, 'Closed', json_file='tec-round-robin'
    )
    event = load_event()
    tournament = event.tournaments_by_id[stored.id]
    with EventDatabase(EVENT_ID, write=True) as database:
        for player in tournament.tournament_players:
            for round_ in UNPLAYED_ROUNDS:
                player.pairings_by_round[round_].update_result(
                    database, Result.NO_RESULT
                )
    yield stored
    EventLoader.unload_event(EVENT_ID)
    TestUtils.delete_event(EVENT_ID)


def grid_rows(html: str, squares: bool = False) -> list[list[str]]:
    """The cells of the rows of the grid as text, or only its squares."""
    parser = AdvancedHTMLParser()
    parser.parseStr(html)
    return [
        [
            ' '.join(cell.textContent.split())
            for cell in row.children
            if cell.tagName == 'td'
            and (not squares or 'grid-cell' in (cell.getAttribute('class') or ''))
        ]
        for row in parser.getElementsByTagName('tr')
        if 'player-row' in (row.getAttribute('class') or '').split()
    ]


def grid_screen(
    http: TestClient,
    api: ApiClient,
    tournament: StoredTournament,
    overrides: dict | None = None,
) -> str:
    stored_screen = TestUtils.create_screen(
        api,
        EVENT_ID,
        'Grid',
        ScreenType.ROUND_ROBIN_GRID,
        {'init_set_tournament_ids': [tournament.id]} | (overrides or {}),
    )
    response = http.get(f'/view/screen/{EVENT_ID}/{stored_screen.uniq_id}')
    assert response.status_code == 200
    return response.text


@pytest.mark.unit
def test_the_grid_shows_the_results_and_the_rounds_still_to_play(
    round_robin: StoredTournament,
):
    event = load_event()
    tournament = event.tournaments_by_id[round_robin.id]
    cells = player_grid(tournament, lambda round_: True)
    for player_id, opponents in cells.items():
        assert len(opponents) == 5
        for opponent_id, encounters in opponents.items():
            assert len(encounters) == 1
            encounter = encounters[0]
            pairing = tournament.tournament_players_by_id[player_id].pairings_by_round[
                encounter.round
            ]
            assert pairing.opponent_id == opponent_id
            if encounter.round in UNPLAYED_ROUNDS:
                assert encounter.result is None
            else:
                assert encounter.result == pairing.result.to_berger_table


@pytest.mark.unit
def test_results_of_rounds_not_to_show_are_kept_back(
    round_robin: StoredTournament,
):
    event = load_event()
    tournament = event.tournaments_by_id[round_robin.id]
    cells = player_grid(tournament, lambda round_: round_ < 2)
    for opponents in cells.values():
        for encounters in opponents.values():
            for encounter in encounters:
                assert (encounter.result is not None) is (encounter.round < 2)


@pytest.mark.unit
def test_the_screen_draws_the_grid_by_berger_number(
    http: TestClient, api: ApiClient, round_robin: StoredTournament
):
    shown = grid_screen(http, api, round_robin)
    rows = grid_rows(shown)
    assert [row[0] for row in rows] == ['1', '2', '3', '4', '5', '6']
    assert 'ALYX' in rows[0]
    squares = grid_rows(shown, squares=True)[0]
    assert len(squares) == 6
    assert squares[0] == ''
    assert {square for square in squares if square.startswith('R ')} == {
        'R 4',
        'R 5',
    }


@pytest.mark.unit
def test_the_screen_can_order_the_grid_by_rank(
    http: TestClient, api: ApiClient, round_robin: StoredTournament
):
    rows = grid_rows(
        grid_screen(http, api, round_robin, {'round_robin_grid_by_rank': True})
    )
    assert [row[-1] for row in rows] == ['1', '2', '3', '4', '5', '6']


@pytest.mark.unit
def test_hidden_columns_are_left_out(
    http: TestClient, api: ApiClient, round_robin: StoredTournament
):
    shown = grid_screen(
        http,
        api,
        round_robin,
        {'ranking_columns': 'on', 'ranking_column_rating': False},
    )
    rows = grid_rows(shown)
    assert '2200 F' not in rows[0]


@pytest.mark.unit
def test_only_round_robins_are_offered_and_accepted(
    http: TestClient, api: ApiClient, round_robin: StoredTournament
):
    swiss = TestUtils.create_tournament(EVENT_ID, 'Open', json_file='test-screens')
    modal = http.get(
        f'/screen-modal/create/{EVENT_ID}/{ScreenType.ROUND_ROBIN_GRID.value}'
    )
    assert modal.status_code == 200
    parser = AdvancedHTMLParser()
    parser.parseStr(modal.text)
    offered = {
        option.getAttribute('value')
        for option in parser.getElementsByTagName('option')
        if option.parentNode.getAttribute('name') == 'init_set_tournament_ids'
    }
    assert offered == {str(round_robin.id)}

    before = len(load_event().sorted_basic_screens)
    http.post(
        f'/screen-create/{EVENT_ID}/{ScreenType.ROUND_ROBIN_GRID.value}',
        data={'name': 'Wrong', 'init_set_tournament_ids': str(swiss.id)},
    )
    assert len(load_event().sorted_basic_screens) == before


@pytest.mark.unit
def test_a_new_round_robin_gets_a_round_robin_grid_screen(api: ApiClient):
    TestUtils.create_event(EVENT_ID)
    try:
        round_robin = {
            'pairing_system': 'ROUND_ROBIN',
            'ROUND_ROBIN_pairing_variation': 'ROUND_ROBIN_BERGER',
        }
        for name, pairing in (('Closed', round_robin), ('Open', {})):
            TestUtils.create_tournament(
                EVENT_ID,
                name,
                via_api_request_context=api,
                overrides={'add_screens': True} | pairing,
            )
        event = load_event()
        grids = event.sorted_basic_screens_by_screen_type[
            ScreenType.ROUND_ROBIN_GRID.value
        ]
        assert [
            screen_set.tournament.name
            for screen in grids
            for screen_set in screen.sorted_screen_sets
        ] == ['Closed']
    finally:
        EventLoader.unload_event(EVENT_ID)
        TestUtils.delete_event(EVENT_ID)


@pytest.mark.unit
def test_the_team_grid_shows_the_matches_and_the_round_still_to_play(
    http: TestClient, api: ApiClient, team_round_robin: int
):
    event = EventLoader().load_event(TEAM_EVENT_ID)
    tournament = event.tournaments_by_id[team_round_robin]
    cells = team_grid(tournament, lambda round_: True)
    outcomes = sorted(
        encounter.result or f'R{encounter.round}'
        for opponents in cells.values()
        for encounters in opponents.values()
        for encounter in encounters
    )
    # Four matches won and lost, two of round 3 still to play, both ways.
    assert outcomes == ['0'] * 4 + ['1'] * 4 + ['R3'] * 4

    stored_screen = TestUtils.create_screen(
        api,
        TEAM_EVENT_ID,
        'Grid',
        ScreenType.ROUND_ROBIN_GRID,
        {'init_set_tournament_ids': [team_round_robin]},
    )
    response = http.get(f'/view/screen/{TEAM_EVENT_ID}/{stored_screen.uniq_id}')
    assert response.status_code == 200
    rows = grid_rows(response.text)
    assert [row[1] for row in rows] == ['Team 1', 'Team 2', 'Team 3', 'Team 4']
    assert sum(row.count('R 3') for row in rows) == 4


@pytest.mark.unit
def test_the_team_grid_can_show_a_row_per_player(
    http: TestClient, api: ApiClient, team_round_robin: int
):
    stored_screen = TestUtils.create_screen(
        api,
        TEAM_EVENT_ID,
        'Players',
        ScreenType.ROUND_ROBIN_GRID,
        {
            'init_set_tournament_ids': [team_round_robin],
            'round_robin_grid_players': True,
        },
    )
    response = http.get(f'/view/screen/{TEAM_EVENT_ID}/{stored_screen.uniq_id}')
    assert response.status_code == 200
    rows = grid_rows(response.text)
    assert len(rows) == 8
    assert [row[2] for row in rows] == [
        'Team 1',
        '',
        'Team 2',
        '',
        'Team 3',
        '',
        'Team 4',
        '',
    ]
    squares = grid_rows(response.text, squares=True)
    # Each player has played two games, one against each of two teams.
    assert all(sum(bool(square) for square in row) == 2 for row in squares)
