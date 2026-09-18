"""Admin pages driven over HTTP, in this process.

The end-to-end suite drives a browser against a server, which is slow
enough that it only covers the path a user takes when nothing goes
wrong. The same handlers answer here through Litestar's test client, so
the answers to a bad form or a name already taken can be asserted
without a browser.
"""

from collections.abc import Iterator

import pytest
from litestar.testing import TestClient

from data.loader import EventLoader
from tests.test_config import TestUtils

EVENT_ID = 'test-admin-http'
TOURNAMENT_NAME = 'test-admin-http-tournament'


@pytest.fixture
def event() -> Iterator[str]:
    TestUtils.create_event(EVENT_ID)
    TestUtils.create_tournament(EVENT_ID, TOURNAMENT_NAME, json_file='tec-swiss')
    yield EVENT_ID
    EventLoader.unload_event(EVENT_ID)
    TestUtils.delete_event(EVENT_ID)


@pytest.mark.unit
def test_the_events_tab_lists_the_events(http: TestClient, event: str):
    response = http.get('/current_events')
    assert response.status_code == 200
    assert event in response.text


@pytest.mark.unit
def test_an_unknown_event_is_sent_to_the_error_page(http: TestClient):
    """A link to an event that has been deleted lands on the error page
    rather than a stack trace."""
    response = http.get('/event/no-such-event', follow_redirects=False)
    assert response.status_code == 302
    assert response.headers['location'].endswith('/error/404')


@pytest.mark.unit
def test_the_tournaments_tab_names_the_tournament(http: TestClient, event: str):
    response = http.get(f'/event/{event}/tournaments')
    assert response.status_code == 200
    assert TOURNAMENT_NAME in response.text


@pytest.mark.unit
def test_a_tournament_needs_a_name(http: TestClient, event: str):
    """The modal comes back with the field marked rather than the
    tournament being created."""
    response = http.post(
        f'/tournament-create/{event}',
        data={'name': '', 'rounds': '5', 'pairing_system': 'SWISS'},
    )
    assert response.status_code == 200
    assert 'is-invalid' in response.text
    loaded = EventLoader().load_event(event)
    assert list(loaded.tournaments_by_name) == [TOURNAMENT_NAME]


ADMIN_TABS = ['home', 'current_events', 'coming_events', 'passed_events', 'archives']

EVENT_TABS = [
    'tournaments',
    'players',
    'teams',
    'screens',
    'input-screens',
    'check-in-screens',
    'boards-screens',
    'players-screens',
    'results-screens',
    'ranking-screens',
    'image-screens',
    'rotators',
    'families',
    'menus',
    'timers',
    'accounts',
    'display_controllers',
]


@pytest.mark.unit
@pytest.mark.parametrize('tab', ADMIN_TABS)
def test_every_admin_tab_renders(http: TestClient, event: str, tab: str):
    response = http.get(f'/{tab}')
    assert response.status_code == 200
    assert response.text


@pytest.mark.unit
@pytest.mark.parametrize('tab', EVENT_TABS)
def test_every_event_tab_renders(http: TestClient, event: str, tab: str):
    """Each tab of an event with a tournament in it, which is what the
    arbiter opens first."""
    response = http.get(f'/event/{event}/{tab}')
    assert response.status_code == 200
    assert response.text


def create_tournament(http: TestClient, event: str, **fields: str):
    """The tournament modal's save, with the fields a test cares about
    over the defaults a blank form carries."""
    return http.post(
        f'/tournament-create/{event}',
        data={
            'name': 'Second tournament',
            'rounds': '5',
            'pairing_system': 'SWISS',
            'SWISS_pairing_variation': 'SWISS_STANDARD',
        }
        | fields,
    )


def tournament_names(event: str) -> list[str]:
    EventLoader.unload_event(event)
    return list(EventLoader().load_event(event).tournaments_by_name)


@pytest.mark.unit
def test_a_second_tournament_cannot_take_the_first_one_s_name(
    http: TestClient, event: str
):
    response = create_tournament(http, event, name=TOURNAMENT_NAME)
    assert response.status_code == 200
    assert 'This name is already used.' in response.text
    assert tournament_names(event) == [TOURNAMENT_NAME]


@pytest.mark.unit
def test_a_tournament_cannot_have_a_negative_number_of_rounds(
    http: TestClient, event: str
):
    response = create_tournament(http, event, rounds='-1')
    assert response.status_code == 200
    assert 'A positive integer is expected.' in response.text
    assert tournament_names(event) == [TOURNAMENT_NAME]


@pytest.mark.unit
def test_a_draw_cannot_be_worth_more_than_a_win(http: TestClient, event: str):
    """The engine pairs on these points, so an order it cannot read is
    refused at the form."""
    response = create_tournament(http, event, gp_win='0.5', gp_draw='1', gp_loss='0')
    assert response.status_code == 200
    assert 'Game points must satisfy loss ≤ draw ≤ win.' in response.text
    assert tournament_names(event) == [TOURNAMENT_NAME]


@pytest.mark.unit
def test_game_points_cannot_be_negative(http: TestClient, event: str):
    """A negative score has no representation in the TRF the engine
    reads."""
    response = create_tournament(http, event, gp_loss='-1')
    assert response.status_code == 200
    assert 'A positive value is expected.' in response.text
    assert tournament_names(event) == [TOURNAMENT_NAME]


@pytest.mark.unit
def test_a_tournament_the_form_accepts_is_created(http: TestClient, event: str):
    """The same form with nothing wrong with it, so the tests above are
    refusals rather than a form that never saves."""
    response = create_tournament(http, event)
    assert response.status_code == 200
    assert sorted(tournament_names(event)) == sorted(
        [TOURNAMENT_NAME, 'Second tournament']
    )


def tournament_id(event: str) -> int:
    EventLoader.unload_event(event)
    loaded = EventLoader().load_event(event)
    identifier = loaded.tournaments_by_name[TOURNAMENT_NAME].id
    assert identifier is not None
    return identifier


PLAYER_FIELDS = {'federation': 'FRA', 'gender': '', 'title': ''}


def player_count(event: str) -> int:
    EventLoader.unload_event(event)
    return len(EventLoader().load_event(event).players_by_id)


@pytest.mark.unit
def test_a_player_needs_a_last_name(http: TestClient, event: str):
    before = player_count(event)
    response = http.post(
        f'/player-create/{event}',
        data=PLAYER_FIELDS
        | {'tournament_id': str(tournament_id(event)), 'last_name': ''},
    )
    assert response.status_code == 200
    assert 'This field is required.' in response.text
    assert player_count(event) == before


@pytest.mark.unit
def test_a_player_needs_a_tournament_to_play_in(http: TestClient, event: str):
    before = player_count(event)
    response = http.post(
        f'/player-create/{event}',
        data=PLAYER_FIELDS | {'tournament_id': '', 'last_name': 'Nowhere'},
    )
    assert response.status_code == 200
    assert 'Please choose the tournament.' in response.text
    assert player_count(event) == before


@pytest.mark.unit
def test_a_player_cannot_be_entered_twice_under_one_fide_id(
    http: TestClient, event: str
):
    """Two players may share a name, so it is the FIDE ID that says the
    arbiter has entered the same person twice."""
    fields = PLAYER_FIELDS | {
        'tournament_id': str(tournament_id(event)),
        'last_name': 'Doubled',
        'first_name': 'Player',
        'fide_id': '123456',
    }
    before = player_count(event)
    assert http.post(f'/player-create/{event}', data=fields).status_code == 200
    assert player_count(event) == before + 1
    response = http.post(f'/player-create/{event}', data=fields)
    assert response.status_code == 200
    assert 'This player already exists' in response.text
    assert player_count(event) == before + 1


@pytest.mark.unit
def test_two_players_may_share_a_name(http: TestClient, event: str):
    """A namesake with nothing else in common is a second person."""
    fields = PLAYER_FIELDS | {
        'tournament_id': str(tournament_id(event)),
        'last_name': 'Namesake',
        'first_name': 'Player',
    }
    before = player_count(event)
    assert http.post(f'/player-create/{event}', data=fields).status_code == 200
    assert http.post(f'/player-create/{event}', data=fields).status_code == 200
    assert player_count(event) == before + 2


@pytest.mark.unit
@pytest.mark.parametrize('action', ['update', 'clone', 'delete'])
def test_the_tournament_modal_opens_for_every_action(
    http: TestClient, event: str, action: str
):
    response = http.get(f'/tournament-modal/{action}/{event}/{tournament_id(event)}')
    assert response.status_code == 200


UPDATE_FIELDS = {
    'rounds': '5',
    'rating': '1',
    'pairing_system': 'SWISS',
    'SWISS_pairing_variation': 'SWISS_STANDARD',
}


@pytest.mark.unit
def test_a_tournament_is_renamed(http: TestClient, event: str):
    response = http.patch(
        f'/tournament-update/{event}/{tournament_id(event)}',
        data=UPDATE_FIELDS | {'name': 'Renamed tournament'},
    )
    assert response.status_code == 200
    assert tournament_names(event) == ['Renamed tournament']


@pytest.mark.unit
def test_a_started_tournament_keeps_the_rating_it_was_played_on(
    http: TestClient, event: str
):
    """Ratings, pairing system and round count are settled once a round
    has been played; the name is not."""
    response = http.patch(
        f'/tournament-update/{event}/{tournament_id(event)}',
        data=UPDATE_FIELDS | {'name': TOURNAMENT_NAME, 'rating': '2'},
    )
    assert response.status_code == 200
    assert "This field can't be updated once the tournament has started." in (
        response.text.replace('&#39;', "'")
    )
    assert tournament_names(event) == [TOURNAMENT_NAME]


@pytest.mark.unit
def test_a_cloned_tournament_stands_beside_the_first(http: TestClient, event: str):
    response = http.post(
        f'/tournament-clone/{event}/{tournament_id(event)}',
        data={
            'name': 'A copy',
            'rounds': '5',
            'pairing_system': 'SWISS',
            'SWISS_pairing_variation': 'SWISS_STANDARD',
        },
    )
    assert response.status_code == 200
    assert sorted(tournament_names(event)) == sorted([TOURNAMENT_NAME, 'A copy'])


@pytest.mark.unit
def test_a_deleted_tournament_is_gone(http: TestClient, event: str):
    response = http.delete(f'/tournament-delete/{event}/{tournament_id(event)}')
    assert response.status_code == 200
    assert tournament_names(event) == []


@pytest.mark.unit
def test_the_rounds_field_is_rebuilt_for_the_chosen_system(
    http: TestClient, event: str
):
    """A round-robin works its round count out from the entry list, so
    the field is replaced rather than typed in."""
    response = http.get(
        f'/tournament-rounds-field/{event}',
        params={'pairing_system': 'ROUND_ROBIN', 'rounds': '5'},
    )
    assert response.status_code == 200
