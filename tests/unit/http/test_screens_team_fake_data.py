"""Fake data on the screens of a team tournament: a made-up first round
among its teams, each fielding its first-round lineup. Nothing is written."""

from collections.abc import Iterator
from dataclasses import replace

import pytest
from litestar.testing import TestClient

from data.event import Event
from data.loader import EventLoader
from data.screens.fake_data import event_with_fake_data
from data.tournament import Tournament
from database.sqlite.event.event_database import EventDatabase
from database.sqlite.event.event_store import (
    StoredPlayer,
    StoredTeam,
    StoredTeamBoard,
    StoredTournament,
)
from tests.test_config import ScreenType, TestUtils
from tests.unit.http.client import ApiClient
from utils.enum import EventType, Result, TeamByeType

EVENT_ID = 'test-screens-team-fake-data-http'
BOARDS = 4


@pytest.fixture
def tournament(api: ApiClient) -> Iterator[StoredTournament]:
    TestUtils.create_event(EVENT_ID, overrides={'event_type': EventType.TEAM})
    stored_tournament = TestUtils.create_tournament(
        EVENT_ID,
        'Teams',
        overrides={
            'rounds': 3,
            'team_player_count': BOARDS,
            'pairing': 'TEAM_SWISS_STANDARD',
        },
    )
    with EventDatabase(EVENT_ID, write=True) as database:
        for seed in range(1, 4):
            team_id = database.add_stored_team(
                StoredTeam(
                    id=None,
                    name=f'Team {seed}',
                    tournament_id=stored_tournament.id,
                    pairing_number=seed,
                    check_in=True,
                )
            )
            for index in range(BOARDS):
                database.add_stored_player(
                    StoredPlayer(
                        id=None,
                        last_name=f'PLAYER{seed}{index}',
                        team_id=team_id,
                        team_index=index,
                        check_in=True,
                    )
                )
    EventLoader.unload_event(EVENT_ID)
    yield stored_tournament
    EventLoader.unload_event(EVENT_ID)
    TestUtils.delete_event(EVENT_ID)


def set_pairing(tournament: StoredTournament, variation_id: str) -> None:
    with EventDatabase(EVENT_ID, True) as database:
        stored = database.get_stored_tournament(tournament.id or 0)
        assert stored is not None
        database.update_stored_tournament(replace(stored, pairing=variation_id))
    EventLoader.unload_event(EVENT_ID)


def fake_tournament(tournament: StoredTournament) -> tuple[Event, Tournament]:
    event = event_with_fake_data(EventLoader().load_event(EVENT_ID))
    return event, event.tournaments_by_id[tournament.id or 0]


def stored_pairings(tournament: StoredTournament) -> tuple:
    """What the database holds of the tournament's pairings."""
    with EventDatabase(EVENT_ID) as database:
        stored_event = database.load_stored_event()
    stored = next(
        stored
        for stored in stored_event.stored_tournaments
        if stored.id == tournament.id
    )
    return (
        stored.published_round,
        dict(stored.stored_boards_by_round),
        dict(stored.stored_team_boards_by_round),
        [
            (player.player_id, list(player.stored_pairings))
            for player in stored.stored_tournament_players
        ],
    )


def screen_text(
    http: TestClient,
    api: ApiClient,
    tournament: StoredTournament,
    screen_type: ScreenType,
) -> str:
    stored_screen = TestUtils.create_screen(
        api,
        EVENT_ID,
        f'{screen_type.value} {tournament.name}',
        screen_type,
        {'init_set_tournament_ids': [tournament.id]},
    )
    response = http.get(f'/view/screen/{EVENT_ID}/{stored_screen.uniq_id}')
    assert response.status_code == 200
    return response.text


def set_fake_data(http: TestClient, on: bool) -> None:
    response = http.patch(f'/screens-fake-data/{EVENT_ID}/{int(on)}')
    assert response.status_code == 200
    assert 'HX-Refresh' in response.headers


@pytest.mark.unit
def test_the_teams_meet_with_their_lineups(tournament: StoredTournament):
    """Team 1 plays team 2, team 3 gets the bye, and every board of the
    match has a result giving the match to one team."""
    event, fake = fake_tournament(tournament)
    assert fake.id in event.fake_tournament_ids
    match, bye = fake.get_round_team_boards(1)
    assert {match.team_a.name, match.team_b and match.team_b.name} == {
        'Team 1',
        'Team 2',
    }
    assert len(match.boards) == BOARDS
    assert all(board.result != Result.NO_RESULT for board in match.boards)
    assert sorted(match.game_points) == [1.5, 2.5]
    assert bye.team_a.name == 'Team 3'
    assert bye.bye_type == TeamByeType.PAB


@pytest.mark.unit
def test_a_team_given_a_bye_keeps_it(tournament: StoredTournament):
    event = EventLoader().load_event(EVENT_ID)
    team_3 = next(team for team in event.teams_by_id.values() if team.name == 'Team 3')
    with EventDatabase(EVENT_ID, True) as database:
        database.add_stored_team_board(
            StoredTeamBoard(
                id=None,
                tournament_id=tournament.id or 0,
                round_=1,
                team_a_id=team_3.id,
                index=None,
                bye_type=TeamByeType.HPB,
            )
        )
    EventLoader.unload_event(EVENT_ID)
    _, fake = fake_tournament(tournament)
    byes = {
        team_board.team_a.name: team_board.bye_type
        for team_board in fake.get_round_team_boards(1)
        if team_board.is_bye
    }
    assert byes == {'Team 3': TeamByeType.HPB}


@pytest.mark.unit
@pytest.mark.parametrize(
    ('variation_id', 'draws'),
    [
        ('TEAM_ROUND_ROBIN_BERGER', True),
        ('TEAM_KNOCKOUT_STANDARD', False),
        ('TEAM_KNOCKOUT_DOUBLE_ELIMINATION_TWO_GAME', False),
    ],
)
def test_the_made_up_round_follows_the_system(
    tournament: StoredTournament, variation_id: str, draws: bool
):
    """A round robin and a knock-out set the first team against the last,
    and a knock-out game has a winner."""
    set_pairing(tournament, variation_id)
    _, fake = fake_tournament(tournament)
    match = next(tb for tb in fake.get_round_team_boards(1) if not tb.is_bye)
    assert {match.team_a.name, match.team_b and match.team_b.name} == {
        'Team 2',
        'Team 3',
    }
    assert (any(board.result == Result.DRAW for board in match.boards)) is draws


@pytest.mark.unit
def test_a_scheveningen_is_shown_from_its_table(tournament: StoredTournament):
    with EventDatabase(EVENT_ID, True) as database:
        stored_event = database.load_stored_event()
        team_3 = next(
            team for team in stored_event.stored_teams if team.name == 'Team 3'
        )
        database.delete_stored_team(team_3.id or 0)
    set_pairing(tournament, 'SCHEVENINGEN_STANDARD')
    _, fake = fake_tournament(tournament)
    (match,) = fake.get_round_team_boards(1)
    assert len(match.boards) == BOARDS
    assert all(
        board.optional_white_pairing is not None
        and board.optional_black_pairing is not None
        for board in match.boards
    )


@pytest.mark.unit
def test_a_molter_is_shown_from_its_table(tournament: StoredTournament):
    """The boards mix the players of the teams, each player meeting one of
    another team, with no match grouping them."""
    set_pairing(tournament, 'MOLTER_STANDARD')
    event, fake = fake_tournament(tournament)
    assert fake.id in event.fake_tournament_ids
    assert not fake.get_round_team_boards(1)
    boards = fake.get_round_boards(1)
    assert boards
    for board in boards:
        white = board.optional_white_pairing
        black = board.optional_black_pairing
        assert white is not None and black is not None
        assert white.tournament_player.team_id != black.tournament_player.team_id
        assert board.result != Result.NO_RESULT


@pytest.mark.unit
def test_a_molter_without_a_table_waits(tournament: StoredTournament):
    with EventDatabase(EVENT_ID, True) as database:
        stored_event = database.load_stored_event()
        team_3 = next(
            team for team in stored_event.stored_teams if team.name == 'Team 3'
        )
        database.delete_stored_team(team_3.id or 0)
    set_pairing(tournament, 'MOLTER_STANDARD')
    event, fake = fake_tournament(tournament)
    assert fake.id not in event.fake_tournament_ids
    assert not fake.get_round_boards(1)


@pytest.mark.unit
def test_the_boards_screen_shows_a_molter(
    http: TestClient, api: ApiClient, tournament: StoredTournament
):
    set_pairing(tournament, 'MOLTER_STANDARD')
    set_fake_data(http, True)
    shown = screen_text(http, api, tournament, ScreenType.BOARDS)
    assert 'data-testid="fake-data-notice"' in shown
    assert 'PLAYER10' in shown


@pytest.mark.unit
@pytest.mark.parametrize(
    ('screen_type', 'text'),
    [
        (ScreenType.BOARDS, 'PLAYER10'),
        (ScreenType.RESULTS, 'PLAYER10'),
        (ScreenType.RANKING, 'After round 1'),
    ],
)
def test_the_screens_show_the_made_up_round(
    http: TestClient,
    api: ApiClient,
    tournament: StoredTournament,
    screen_type: ScreenType,
    text: str,
):
    before = stored_pairings(tournament)
    set_fake_data(http, True)
    shown = screen_text(http, api, tournament, screen_type)
    assert 'data-testid="fake-data-notice"' in shown
    assert text in shown
    assert '/view/result-modal/' not in shown
    assert stored_pairings(tournament) == before


@pytest.mark.unit
def test_the_button_shows_for_a_team_tournament_not_started(
    http: TestClient, tournament: StoredTournament
):
    assert 'data-testid="screens-fake-data-toggle"' in (
        http.get(f'/event/{EVENT_ID}/screens').text
    )
