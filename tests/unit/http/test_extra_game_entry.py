"""The games a team match counts beyond its boards, on the pairings page:
they are shown under the boards of their match and take a result from a
modal of their own."""

import contextlib
from dataclasses import replace
from collections.abc import Iterator

import pytest
from litestar.testing import TestClient

from data.event import Event
from data.input_output.managers import TournamentExporterManager
from data.loader import EventLoader
from data.teams.extra_game import ExtraGame
from data.tournament import Tournament
from database.sqlite.event.event_database import EventDatabase
from database.sqlite.event.event_store import (
    StoredPlayer,
    StoredTeam,
    StoredTieBreak,
    StoredTournamentPlayer,
)
from tests.test_config import ScreenType, TestUtils
from tests.unit.http.client import ApiClient
from utils.enum import EventType, Result
from web.controllers.admin.tournament_admin_controller import (
    TournamentAdminController,
)

EVENT_ID = 'test-extra-games-http'
TOURNAMENT_NAME = 'tournament'
BOARDS = 4
SCREEN_ID = 'test-extra-games-screen'

_loaded: list[Event] = []


def load() -> Tournament:
    with contextlib.suppress(KeyError):
        EventLoader.unload_event(EVENT_ID)
    event = EventLoader().load_event(EVENT_ID)
    _loaded[:] = [event]
    return event.tournaments_by_name[TOURNAMENT_NAME]


def second_game(tournament: Tournament) -> ExtraGame:
    (team_board,) = tournament.get_round_team_boards(1)
    (extra_game,) = team_board.extra_games
    return extra_game


def pairings_page(http: TestClient, tournament: Tournament) -> str:
    response = http.get(
        f'/event/{EVENT_ID}/pairings?tournament_id={tournament.id}&round=1'
    )
    assert response.status_code == 200
    return response.text


def result_url(tournament: Tournament, extra_game: ExtraGame, result: int) -> str:
    return (
        f'/pairing/set-extra-game-result/{EVENT_ID}/{tournament.id}/1'
        f'/{extra_game.team_board.id}/{extra_game.key}/{result}'
    )


@pytest.fixture
def tournament() -> Iterator[Tournament]:
    """Two teams of four whose last board plays its opponent twice, round 1
    paired."""
    TestUtils.create_event(EVENT_ID, overrides={'event_type': EventType.TEAM})
    stored_tournament = TestUtils.create_tournament(
        EVENT_ID,
        TOURNAMENT_NAME,
        overrides={
            'rounds': 1,
            'team_player_count': BOARDS,
            'color_pattern': 'WBWB',
            'pairing': 'TEAM_ROUND_ROBIN_BERGER',
            'game_points': {
                Result.WIN.value: 2.0,
                Result.DRAW.value: 0.0,
                Result.LOSS.value: 0.0,
            },
            'rule_set': 'ffe-interclubs-jeunes-n3',
        },
    )
    with EventDatabase(EVENT_ID, write=True) as database:
        for seed in (1, 2):
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
                player_id = database.add_stored_player(
                    StoredPlayer(
                        id=None,
                        last_name=f'T{seed}P{index}',
                        team_id=team_id,
                        team_index=index,
                        check_in=True,
                    )
                )
                database.add_stored_tournament_player(
                    StoredTournamentPlayer(
                        tournament_id=stored_tournament.id,
                        player_id=player_id,
                        pairing_number=index + 1,
                    )
                )
    assert load().generate_round_pairings(1) == ''
    yield load()
    EventLoader.unload_event(EVENT_ID)
    TestUtils.delete_event(EVENT_ID)


@pytest.mark.unit
def test_the_second_game_is_shown_under_the_boards(
    http: TestClient, tournament: Tournament
):
    extra_game = second_game(tournament)
    page = pairings_page(http, tournament)
    row_id = f'pairing-row-{extra_game.row_id}'
    assert f'id="{row_id}"' in page
    assert 'Board 4, second game' in page
    assert '>4b</span>' in page
    row = page[page.index(f'id="{row_id}"') :]
    row = row[: row.index('</tr>')]
    assert f'data-board-id="{extra_game.row_id}"' in row
    assert 'data-extra-game="1"' in row


@pytest.mark.unit
def test_the_second_game_takes_a_result_from_its_modal(
    http: TestClient, tournament: Tournament
):
    extra_game = second_game(tournament)
    modal = http.get(
        f'/event/{EVENT_ID}/extra-game/{tournament.id}/1'
        f'/{extra_game.team_board.id}/{extra_game.key}'
    )
    assert modal.status_code == 200
    assert result_url(tournament, extra_game, Result.WIN.value) in modal.text

    response = http.put(result_url(tournament, extra_game, Result.WIN.value))
    assert response.status_code == 200
    stored = second_game(load())
    assert stored.result == Result.WIN
    assert stored.team_board.game_points == (1.0, 0.0)
    assert '1-0' in response.text


@pytest.mark.unit
def test_the_result_of_a_second_game_is_cleared(
    http: TestClient, tournament: Tournament
):
    extra_game = second_game(tournament)
    http.put(result_url(tournament, extra_game, Result.DRAW.value))
    assert not second_game(load()).pending
    response = http.put(result_url(tournament, extra_game, Result.NO_RESULT.value))
    assert response.status_code == 200
    assert second_game(load()).pending


@pytest.mark.unit
def test_a_second_game_refuses_a_result_it_cannot_take(
    http: TestClient, tournament: Tournament
):
    extra_game = second_game(tournament)
    http.put(result_url(tournament, extra_game, Result.ADJOURNED.value))
    assert second_game(load()).pending
    assert load().stored_tournament.stored_extra_games == []


@pytest.mark.unit
def test_a_result_for_an_unknown_second_game_is_not_recorded(
    http: TestClient, tournament: Tournament
):
    extra_game = second_game(tournament)
    http.put(
        f'/pairing/set-extra-game-result/{EVENT_ID}/{tournament.id}/1'
        f'/{extra_game.team_board.id}/9-9/{Result.WIN.value}'
    )
    assert load().stored_tournament.stored_extra_games == []


@pytest.mark.unit
def test_the_header_counts_the_second_game_among_those_to_play(
    http: TestClient, tournament: Tournament
):
    assert 'Board (5)' in pairings_page(http, tournament)
    http.put(result_url(tournament, second_game(tournament), Result.DRAW.value))
    assert 'Board (4)' in pairings_page(http, tournament)


@pytest.mark.unit
def test_the_match_sheets_list_the_second_game(
    http: TestClient, tournament: Tournament
):
    response = http.get(
        f'/document-view/{EVENT_ID}/match-sheets',
        params={'options': f'tournament={tournament.id}'},
    )
    assert response.status_code == 200
    assert '>4b</div>' in response.text


@pytest.mark.unit
def test_a_screen_of_the_boards_lists_the_second_game(
    api: ApiClient, http: TestClient, tournament: Tournament
):
    TestUtils.create_screen(
        api,
        EVENT_ID,
        SCREEN_ID,
        ScreenType.BOARDS,
        {'init_set_tournament_ids': [tournament.id]},
    )
    http.put(f'/pairings/publish/{EVENT_ID}/{tournament.id}/1')
    http.put(result_url(tournament, second_game(tournament), Result.WIN.value))
    markup = http.get(f'/view/screen/{EVENT_ID}/{SCREEN_ID}').text
    assert '>4b</div>' in markup
    assert '1 - 0' in markup


@pytest.mark.unit
def test_the_tournament_is_not_exported(http: TestClient, tournament: Tournament):
    for exporter in TournamentExporterManager(tournament.event).objects():
        assert exporter.unavailable_message(tournament), exporter.id
    response = http.get(f'/tournament-export/{EVENT_ID}/{tournament.id}/trf-26')
    assert 'content-disposition' not in response.headers


@pytest.mark.unit
def test_the_rule_set_is_kept_once_the_tournament_is_paired(tournament: Tournament):
    assert tournament.rule_set_is_locked
    assert tournament.exports_forbidden_message
    assert not tournament.rule_set_managed_tie_breaks


@pytest.mark.unit
def test_a_tournament_whose_rule_set_is_gone_keeps_its_second_games_from_exports(
    http: TestClient, tournament: Tournament
):
    http.put(result_url(tournament, second_game(tournament), Result.WIN.value))
    with EventDatabase(EVENT_ID, write=True) as database:
        stored = load().stored_tournament
        stored.rule_set = 'a-rule-set-of-a-plugin-turned-off'
        database.update_stored_tournament(stored)
    tournament = load()
    assert tournament.rule_set is None
    (team_board,) = tournament.get_round_team_boards(1)
    assert team_board.extra_games == []
    assert tournament.exports_forbidden_message


@pytest.mark.unit
def test_the_record_of_a_player_shows_their_second_game(
    http: TestClient, tournament: Tournament
):
    extra_game = second_game(tournament)
    http.put(result_url(tournament, extra_game, Result.WIN.value))
    white = extra_game.white_tournament_player
    black = extra_game.black_tournament_player
    assert white is not None and black is not None
    record = http.get(f'/record-modal/{EVENT_ID}/{white.id}')
    assert record.status_code == 200
    assert 'Board 4, second game' in record.text
    assert black.full_name in record.text
    assert 'not towards the points of the player' in record.text
    history = http.get(f'/history-popover/{EVENT_ID}/{tournament.id}/{black.id}')
    assert history.status_code == 200
    assert 'Board 4, second game' in history.text


@pytest.mark.unit
def test_the_record_of_a_player_without_a_second_game_says_nothing_of_it(
    http: TestClient, tournament: Tournament
):
    (team_board,) = tournament.get_round_team_boards(1)
    player = team_board.boards[0].optional_white_tournament_player
    assert player is not None
    record = http.get(f'/record-modal/{EVENT_ID}/{player.id}')
    assert record.status_code == 200
    assert 'second game' not in record.text


def screen_result_url(
    tournament: Tournament, extra_game: ExtraGame, result: int
) -> str:
    return (
        f'/view/update-extra-game-result/1/{EVENT_ID}/{SCREEN_ID}/{tournament.id}'
        f'/{extra_game.team_board.id}/{extra_game.key}/{result}'
    )


@pytest.fixture
def input_screen(api: ApiClient, http: TestClient, tournament: Tournament) -> str:
    """A screen of the boards taking results, round 1 published."""
    TestUtils.create_screen(
        api,
        EVENT_ID,
        SCREEN_ID,
        ScreenType.BOARDS,
        {'init_set_tournament_ids': [tournament.id], 'accepts_input': True},
    )
    http.put(f'/pairings/publish/{EVENT_ID}/{tournament.id}/1')
    return f'/view/screen/{EVENT_ID}/{SCREEN_ID}'


@pytest.mark.unit
def test_a_round_awaiting_publication_takes_a_second_game_result_once_unlocked(
    api: ApiClient, http: TestClient, tournament: Tournament
):
    TestUtils.create_screen(
        api,
        EVENT_ID,
        SCREEN_ID,
        ScreenType.BOARDS,
        {'init_set_tournament_ids': [tournament.id]},
    )
    tournament = load()
    assert tournament.awaits_publication(1)
    extra_game = second_game(tournament)
    url = result_url(tournament, extra_game, Result.WIN.value)

    refused = http.put(url)
    assert second_game(load()).pending
    assert f'{url}?unlock=1' not in refused.text
    assert '?unlock=1' in refused.text

    modal = http.get(
        f'/event/{EVENT_ID}/extra-game/{tournament.id}/1'
        f'/{extra_game.team_board.id}/{extra_game.key}?unlock=1'
    )
    assert f'{url}?unlock=1' in modal.text
    http.put(f'{url}?unlock=1')
    assert second_game(load()).result == Result.WIN


@pytest.mark.unit
def test_a_screen_taking_results_opens_the_modal_of_the_second_game(
    http: TestClient, tournament: Tournament, input_screen: str
):
    extra_game = second_game(tournament)
    modal_url = (
        f'/view/extra-game-result-modal/1/{EVENT_ID}/{SCREEN_ID}/{tournament.id}'
        f'/{extra_game.team_board.id}/{extra_game.key}'
    )
    assert modal_url in http.get(input_screen).text
    modal = http.get(modal_url)
    assert modal.status_code == 200
    assert 'Board 4, second game' in modal.text
    assert f'{screen_result_url(tournament, extra_game, 3)}?shown=0' in modal.text


@pytest.mark.unit
def test_a_screen_records_the_result_of_the_second_game(
    http: TestClient, tournament: Tournament, input_screen: str
):
    extra_game = second_game(tournament)
    response = http.put(f'{screen_result_url(tournament, extra_game, 3)}?shown=0')
    assert response.status_code == 200
    assert second_game(load()).result == Result.WIN


@pytest.mark.unit
def test_a_screen_that_had_not_caught_up_records_nothing(
    http: TestClient, tournament: Tournament, input_screen: str
):
    extra_game = second_game(tournament)
    http.put(f'{screen_result_url(tournament, extra_game, 3)}?shown=0')
    http.put(f'{screen_result_url(tournament, extra_game, 1)}?shown=0')
    assert second_game(load()).result == Result.WIN


@pytest.mark.unit
def test_a_screen_showing_results_only_does_not_take_one(
    api: ApiClient, http: TestClient, tournament: Tournament
):
    TestUtils.create_screen(
        api,
        EVENT_ID,
        SCREEN_ID,
        ScreenType.BOARDS,
        {'init_set_tournament_ids': [tournament.id]},
    )
    http.put(f'/pairings/publish/{EVENT_ID}/{tournament.id}/1')
    extra_game = second_game(tournament)
    assert 'extra-game-result-modal' not in (
        http.get(f'/view/screen/{EVENT_ID}/{SCREEN_ID}').text
    )
    http.put(f'{screen_result_url(tournament, extra_game, 3)}?shown=0')
    assert second_game(load()).pending


@pytest.mark.unit
def test_the_national_divisions_are_played_as_a_round_robin(
    http: TestClient, tournament: Tournament
):
    response = http.patch(
        f'/tournament-update/{EVENT_ID}/{tournament.id}',
        data={
            'name': TOURNAMENT_NAME,
            'pairing_system': 'TEAM_SWISS',
            'TEAM_SWISS_pairing_variation': 'TEAM_SWISS_STANDARD',
            'rule_set': 'ffe-interclubs-jeunes',
            'team_player_count': '8',
            'rounds': '1',
        },
    )
    assert response.status_code == 200
    assert 'is played with the pairing system' in response.text
    assert load().pairing_system.id == 'TEAM_ROUND_ROBIN'


def hotkey(
    http: TestClient,
    tournament: Tournament,
    extra_game: ExtraGame,
    key: str,
    validate: bool = False,
) -> str:
    response = http.put(
        f'/pairing/set-result-hotkey/{EVENT_ID}/{tournament.id}/1',
        data={
            'key': key,
            'board_id': extra_game.row_id,
            'validate_result': 'true' if validate else 'false',
        },
    )
    assert response.status_code == 200
    return response.text


@pytest.mark.unit
def test_the_keys_of_a_board_enter_the_result_of_the_second_game(
    http: TestClient, tournament: Tournament
):
    """Team A sits on the left, with white in the second game of its last
    board: the first key has it win."""
    extra_game = second_game(tournament)
    assert extra_game.team_a_is_white
    text = hotkey(http, tournament, extra_game, 'Digit1')
    assert second_game(load()).result == Result.WIN
    assert f'id="pairing-row-{extra_game.row_id}"' in text
    assert 'hx-swap-oob' in text
    hotkey(http, tournament, extra_game, 'Numpad2')
    assert second_game(load()).result == Result.LOSS
    hotkey(http, tournament, extra_game, 'Digit3')
    assert second_game(load()).result == Result.DRAW
    hotkey(http, tournament, extra_game, 'Digit0')
    assert second_game(load()).pending


@pytest.mark.unit
def test_the_check_of_the_results_flags_a_second_game_that_differs(
    http: TestClient, tournament: Tournament
):
    extra_game = second_game(tournament)
    hotkey(http, tournament, extra_game, 'Digit1')
    agreed = hotkey(http, tournament, extra_game, 'Digit1', validate=True)
    assert 'highlight-warning' not in agreed
    differs = hotkey(http, tournament, extra_game, 'Digit2', validate=True)
    assert 'highlight-warning' in differs
    assert second_game(load()).result == Result.WIN


@pytest.mark.unit
def test_a_key_that_is_no_result_of_a_second_game_is_ignored(
    http: TestClient, tournament: Tournament
):
    hotkey(http, tournament, second_game(tournament), 'KeyA')
    assert second_game(load()).pending


def _criteria(database: EventDatabase, tournament: Tournament) -> list[str]:
    return [
        stored_tie_break.type
        for stored_tie_break in sorted(
            database.load_tournament_stored_tie_breaks(tournament.id),
            key=lambda stored_tie_break: stored_tie_break.index,
        )
    ]


@pytest.mark.unit
def test_the_criteria_of_the_rule_set_are_written_once_and_left_to_the_arbiter(
    tournament: Tournament,
):
    stored = tournament.stored_tournament
    with EventDatabase(EVENT_ID, write=True) as database:
        TournamentAdminController._apply_rule_set_tie_breaks(
            database, tournament.event, stored
        )
        assert _criteria(database, tournament)[1] == 'ffe-MUTUAL-RESULTS'
        database.delete_all_tournament_stored_tie_breaks(tournament.id)
        database.add_stored_tie_break(
            StoredTieBreak(
                id=None,
                tournament_id=tournament.id,
                type='POINTS',
                options={},
                index=0,
            )
        )
        TournamentAdminController._apply_rule_set_tie_breaks(
            database, tournament.event, stored, stored
        )
        assert _criteria(database, tournament) == ['POINTS']
        TournamentAdminController._apply_rule_set_tie_breaks(
            database, tournament.event, stored, replace(stored, rule_set=None)
        )
        assert _criteria(database, tournament)[1] == 'ffe-MUTUAL-RESULTS'
