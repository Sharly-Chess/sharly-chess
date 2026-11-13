"""Screens that accept input: results on the pairings screens, check-ins on the
check-in screens. A screen that does not accept input only shows, and may go
through a rotator."""

from collections.abc import Iterator

import pytest
from AdvancedHTMLParser import AdvancedHTMLParser
from httpx import Response
from litestar.testing import TestClient

from data.loader import EventLoader
from database.sqlite.event.event_database import EventDatabase
from database.sqlite.event.event_store import StoredTournament
from tests.test_config import ScreenType, TestUtils
from tests.unit.http.client import ApiClient
from tests.unit.http.conftest import TEAM_EVENT_ID

EVENT_ID = 'test-screen-input-http'


@pytest.fixture
def tournament(api: ApiClient) -> Iterator[StoredTournament]:
    TestUtils.create_event(EVENT_ID)
    stored = TestUtils.create_tournament(
        EVENT_ID, 'Club tournament', json_file='test-screens'
    )
    yield stored
    EventLoader.unload_event(EVENT_ID)
    TestUtils.delete_event(EVENT_ID)


def screen_html(
    http: TestClient,
    api: ApiClient,
    tournament: StoredTournament,
    screen_type: ScreenType,
    accepts_input: bool,
) -> str:
    stored_screen = TestUtils.create_screen(
        api,
        EVENT_ID,
        f'{screen_type.value} {accepts_input}',
        screen_type,
        {'init_set_tournament_ids': [tournament.id], 'accepts_input': accepts_input},
    )
    response = http.get(f'/view/screen/{EVENT_ID}/{stored_screen.uniq_id}')
    assert response.status_code == 200
    return response.text


@pytest.mark.unit
@pytest.mark.parametrize('screen_type', [ScreenType.BOARDS, ScreenType.PLAYERS])
def test_a_pairings_screen_takes_results_only_when_it_accepts_input(
    http: TestClient,
    api: ApiClient,
    tournament: StoredTournament,
    screen_type: ScreenType,
):
    shown = screen_html(http, api, tournament, screen_type, accepts_input=False)
    assert '/view/result-modal/' not in shown
    assert 'input-screen' not in shown

    entered = screen_html(http, api, tournament, screen_type, accepts_input=True)
    assert '/view/result-modal/' in entered
    assert 'input-screen' in entered
    assert 'enter-result-button' in entered


@pytest.mark.unit
def test_a_check_in_screen_checks_in_only_when_it_accepts_input(
    http: TestClient, api: ApiClient, tournament: StoredTournament
):
    shown = screen_html(http, api, tournament, ScreenType.CHECK_IN, accepts_input=False)
    assert '/view/checkin-modal/' not in shown
    checked_in = screen_html(
        http, api, tournament, ScreenType.CHECK_IN, accepts_input=True
    )
    assert '/view/checkin-modal/' in checked_in


@pytest.mark.unit
@pytest.mark.parametrize(
    'screen_type', [ScreenType.BOARDS, ScreenType.PLAYERS, ScreenType.CHECK_IN]
)
def test_only_a_screen_that_does_not_accept_input_goes_in_a_rotator(
    http: TestClient,
    api: ApiClient,
    tournament: StoredTournament,
    screen_type: ScreenType,
):
    rotator_id = TestUtils.create_rotator(api, EVENT_ID, 'Lobby')
    for accepts_input in (False, True):
        stored_screen = TestUtils.create_screen(
            api,
            EVENT_ID,
            f'{screen_type.value} {accepts_input}',
            screen_type,
            {
                'init_set_tournament_ids': [tournament.id],
                'accepts_input': accepts_input,
            },
        )
        http.post(
            f'/rotating-screens/create/{EVENT_ID}/{rotator_id}',
            data={'item_id': f'screen:{stored_screen.id}'},
        )
        EventLoader.unload_event(EVENT_ID)
        event = EventLoader().load_event(EVENT_ID)
        rotator = event.rotators_by_id[rotator_id]
        screen_ids = [screen.id for screen in rotator.screens]
        assert (stored_screen.id in screen_ids) is not accepts_input


@pytest.mark.unit
@pytest.mark.parametrize(
    ('screen_type', 'label'),
    [
        (ScreenType.BOARDS, 'Results can be entered on this screen'),
        (ScreenType.PLAYERS, 'Results can be entered on this screen'),
        (ScreenType.CHECK_IN, 'Players can check in on this screen'),
    ],
)
def test_the_create_modal_offers_the_input_switch(
    http: TestClient, tournament: StoredTournament, screen_type: ScreenType, label: str
):
    response = http.get(f'/screen-modal/create/{EVENT_ID}/{screen_type.value}')
    assert response.status_code == 200
    assert 'name="accepts_input"' in response.text
    assert label in response.text


@pytest.mark.unit
def test_a_new_tournament_gets_a_results_entry_screen(http: TestClient, api: ApiClient):
    TestUtils.create_event(EVENT_ID)
    try:
        TestUtils.create_tournament(
            EVENT_ID,
            'Club tournament',
            via_api_request_context=api,
            overrides={'add_screens': True},
        )
        EventLoader.unload_event(EVENT_ID)
        event = EventLoader().load_event(EVENT_ID)
        boards = event.sorted_basic_screens_by_screen_type['boards']
        assert sorted(screen.accepts_input for screen in boards) == [False, True]
        check_in = event.sorted_basic_screens_by_screen_type['check-in']
        assert [screen.accepts_input for screen in check_in] == [True]
    finally:
        EventLoader.unload_event(EVENT_ID)
        TestUtils.delete_event(EVENT_ID)


@pytest.mark.unit
def test_a_player_row_opens_the_result_of_the_players_board(
    http: TestClient, api: ApiClient, tournament: StoredTournament
):
    """In the test tournament ALYX plays board 1 and BRUNO board 2."""
    shown = screen_html(http, api, tournament, ScreenType.PLAYERS, accepts_input=True)
    parser = AdvancedHTMLParser()
    parser.parseStr(shown)
    links = {
        ' '.join(row.textContent.split()).split()[0]: row.getAttribute('hx-get')
        for row in parser.getElementsByTagName('div')
        if 'player-row' in (row.getAttribute('class') or '').split()
    }
    assert links['ALYX'].endswith(f'/{tournament.id}/1')
    assert links['BRUNO'].endswith(f'/{tournament.id}/2')


def refused(response: Response) -> bool:
    """A refusal is a redirect to the page saying so."""
    return response.status_code == 302 and response.headers['location'].endswith(
        '/error/403'
    )


def created(
    api: ApiClient,
    tournament: StoredTournament,
    screen_type: ScreenType,
    accepts_input: bool,
    name: str,
) -> str:
    return TestUtils.create_screen(
        api,
        EVENT_ID,
        name,
        screen_type,
        {'init_set_tournament_ids': [tournament.id], 'accepts_input': accepts_input},
    ).uniq_id


@pytest.mark.unit
def test_a_result_is_taken_only_through_a_screen_taking_results(
    http: TestClient, api: ApiClient, tournament: StoredTournament
):
    """Whoever may enter results still needs a screen that takes them, for the
    tournament it shows."""
    taking = created(api, tournament, ScreenType.BOARDS, True, 'Entry')
    read_only = created(api, tournament, ScreenType.BOARDS, False, 'Pairings')
    check_in = created(api, tournament, ScreenType.CHECK_IN, True, 'Check-in')
    other = TestUtils.create_tournament(
        EVENT_ID, 'Other tournament', json_file='test-screens'
    )

    def modal(screen_uniq_id: str, tournament_id: int | None) -> bool:
        return refused(
            http.get(
                f'/view/result-modal/1/{EVENT_ID}/{screen_uniq_id}/{tournament_id}/1',
                follow_redirects=False,
            )
        )

    assert not modal(taking, tournament.id)
    assert modal(read_only, tournament.id)
    assert modal(check_in, tournament.id)
    assert modal(taking, other.id)
    assert refused(
        http.put(
            f'/view/update-result/1/{EVENT_ID}/{read_only}/{tournament.id}/1/1/1',
            follow_redirects=False,
        )
    )


@pytest.mark.unit
def test_a_check_in_is_taken_only_through_a_screen_taking_check_ins(
    http: TestClient, api: ApiClient, tournament: StoredTournament
):
    taking = created(api, tournament, ScreenType.CHECK_IN, True, 'Check-in')
    read_only = created(api, tournament, ScreenType.CHECK_IN, False, 'Arrivals')
    results = created(api, tournament, ScreenType.BOARDS, True, 'Entry')
    event = EventLoader().load_event(EVENT_ID)
    assert tournament.id is not None
    player = event.tournaments_by_id[tournament.id].sorted_tournament_players[0]

    def toggle(screen_uniq_id: str) -> bool:
        return refused(
            http.patch(
                f'/view/toggle-check-in/1/{EVENT_ID}/{screen_uniq_id}'
                f'/{tournament.id}/{player.id}',
                follow_redirects=False,
            )
        )

    assert not toggle(taking)
    assert toggle(read_only)
    assert toggle(results)


@pytest.mark.unit
def test_a_screen_taking_results_shows_the_boards_of_the_matches(
    http: TestClient, api: ApiClient, team_round_robin: int
):
    """The boards are where results are entered, so a team screen taking
    them cannot show the matches only."""
    stored_screen = TestUtils.create_screen(
        api,
        TEAM_EVENT_ID,
        'Matches',
        ScreenType.BOARDS,
        {
            'init_set_tournament_ids': [team_round_robin],
            'accepts_input': True,
            'boards_hide_players': True,
        },
    )
    with EventDatabase(TEAM_EVENT_ID) as database:
        stored = database.get_stored_screen(stored_screen.id or 0)
    assert stored is not None
    assert stored.accepts_input and not stored.boards_hide_players

    response = http.get(f'/view/screen/{TEAM_EVENT_ID}/{stored_screen.uniq_id}')
    assert response.status_code == 200
    assert 'T1P0' in response.text
