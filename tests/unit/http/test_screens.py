"""The screens a venue shows, rendered in this process.

A multi-screen splits a tournament over several screens, either into a
given number of parts or into screens of a given number of rows, and
each part is fetched under its own number. What lands on each one is
decided on the server and read back from the HTML here, where the
browser suite was starting a browser per part to do the same.
"""

import json
import time
from collections.abc import Iterator

import pytest
from AdvancedHTMLParser import AdvancedHTMLParser
from litestar.testing import TestClient

from data.loader import EventLoader
from database.sqlite.event.event_store import StoredTournament
from tests.test_config import ScreenType, TestUtils
from tests.unit.http.client import ApiClient
from tests.unit.http.conftest import TEAM_EVENT_ID

EVENT_ID = 'test-screens-http'
TOURNAMENT_NAME = 'test-screens-http-tournament'
FAMILY_ID = 'test-screens-http-family'
ONE_PIXEL_PNG = (
    'data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR4'
    '2mP8z8DwHwAFBQIAX8jx0gAAAABJRU5ErkJggg=='
)


@pytest.fixture
def tournament(api: ApiClient) -> Iterator[StoredTournament]:
    TestUtils.create_event(EVENT_ID)
    stored = TestUtils.create_tournament(
        EVENT_ID, TOURNAMENT_NAME, json_file='test-screens'
    )
    yield stored
    EventLoader.unload_event(EVENT_ID)
    TestUtils.delete_event(EVENT_ID)


def rows(http: TestClient, part: str, row_class: str) -> list[str]:
    """The rows of one part of the multi-screen, in the order they are
    shown."""
    response = http.get(f'/view/screen/{EVENT_ID}/{FAMILY_ID}:{part}')
    assert response.status_code == 200
    parser = AdvancedHTMLParser()
    parser.parseStr(response.text)
    return [
        ' '.join(element.textContent.split())
        for element in parser.getElementsByTagName('div')
        # The class attribute is written over several lines in the
        # template, which getElementsByClassName does not see through.
        if row_class in (element.getAttribute('class') or '').split()
    ]


@pytest.mark.unit
@pytest.mark.parametrize(
    ('screen_type', 'row_class'),
    [(ScreenType.BOARDS, 'board-row')],
)
def test_a_multi_screen_splits_the_boards_into_parts(
    http: TestClient,
    api: ApiClient,
    tournament: StoredTournament,
    screen_type: ScreenType,
    row_class: str,
):
    """Eight boards over two parts: four each, in board order."""
    TestUtils.create_family(
        api, EVENT_ID, tournament, FAMILY_ID, screen_type, {'parts': 2}
    )
    first = rows(http, '001', row_class)
    assert len(first) == 4
    assert 'ALYX' in first[0]
    assert 'DAVID' in first[-1]

    second = rows(http, '002', row_class)
    assert len(second) == 4
    assert 'HELEN' in second[0]
    assert 'IRINA' in second[-1]


@pytest.mark.unit
def test_a_multi_screen_splits_the_boards_into_screens_of_two(
    http: TestClient, api: ApiClient, tournament: StoredTournament
):
    """Two rows to a screen makes four of them, and the fourth carries
    the last two boards."""
    TestUtils.create_family(
        api, EVENT_ID, tournament, FAMILY_ID, ScreenType.BOARDS, {'number': 2}
    )
    first = rows(http, '001', 'board-row')
    assert len(first) == 2
    assert 'ALYX' in first[0]
    assert 'BRUNO' in first[-1]

    last = rows(http, '004', 'board-row')
    assert len(last) == 2
    assert 'GENEVIEVE' in last[0]
    assert 'IRINA' in last[-1]


@pytest.mark.unit
def test_a_multi_screen_splits_the_players_into_parts(
    http: TestClient, api: ApiClient, tournament: StoredTournament
):
    """A players screen lists everyone entered, not only those paired, so
    its parts are longer than the boards'."""
    TestUtils.create_family(
        api, EVENT_ID, tournament, FAMILY_ID, ScreenType.PLAYERS, {'parts': 2}
    )
    first = rows(http, '001', 'player-row')
    assert len(first) == 8
    assert 'ALYX' in first[0]
    assert 'IRINA' in first[-1]

    second = rows(http, '002', 'player-row')
    assert len(second) == 8
    assert 'JESSICA' in second[0]
    assert 'STEPHAN' in second[-1]


@pytest.mark.unit
def test_a_multi_screen_splits_the_players_into_screens_of_two(
    http: TestClient, api: ApiClient, tournament: StoredTournament
):
    TestUtils.create_family(
        api, EVENT_ID, tournament, FAMILY_ID, ScreenType.PLAYERS, {'number': 2}
    )
    first = rows(http, '001', 'player-row')
    assert len(first) == 2
    assert 'ALYX' in first[0]
    assert 'BRUNO' in first[-1]

    last = rows(http, '008', 'player-row')
    assert len(last) == 2
    assert 'REINE' in last[0]
    assert 'STEPHAN' in last[-1]


@pytest.mark.unit
def test_a_multi_screen_is_created_and_deleted(
    http: TestClient, api: ApiClient, tournament: StoredTournament
):
    stored_family = TestUtils.create_family(
        api,
        EVENT_ID,
        tournament,
        FAMILY_ID,
        ScreenType.BOARDS,
        {'accepts_input': True, 'parts': 2},
    )
    listed = http.get(f'/event/{EVENT_ID}/families')
    assert listed.status_code == 200
    assert FAMILY_ID in listed.text

    TestUtils.delete_family(api, EVENT_ID, stored_family.id)
    emptied = http.get(f'/event/{EVENT_ID}/families')
    assert emptied.status_code == 200
    assert FAMILY_ID not in emptied.text


@pytest.mark.unit
def test_a_screen_is_created_listed_and_deleted(
    http: TestClient, api: ApiClient, tournament: StoredTournament
):
    stored_screen = TestUtils.create_screen(
        api,
        EVENT_ID,
        'A boards screen',
        ScreenType.BOARDS,
        {'init_set_tournament_ids': [tournament.id]},
    )
    listed = http.get(f'/event/{EVENT_ID}/boards-screens')
    assert listed.status_code == 200
    assert 'A boards screen' in listed.text

    TestUtils.delete_screen(api, EVENT_ID, stored_screen.id)
    emptied = http.get(f'/event/{EVENT_ID}/boards-screens')
    assert emptied.status_code == 200
    assert 'A boards screen' not in emptied.text


@pytest.mark.unit
def test_the_link_to_a_screen_follows_its_renaming(
    http: TestClient, api: ApiClient, tournament: StoredTournament
):
    """The screens tab links to each screen by its unique id, and the
    venue is given that link: renaming has to carry it with it."""
    stored_screen = TestUtils.create_screen(
        api,
        EVENT_ID,
        'Renamed screen',
        ScreenType.BOARDS,
        {'accepts_input': True, 'init_set_tournament_ids': [tournament.id]},
    )
    old_uniq_id = stored_screen.uniq_id
    listed = http.get(f'/event/{EVENT_ID}/screens')
    assert f'/view/screen/{EVENT_ID}/{old_uniq_id}' in listed.text

    response = http.patch(
        f'/screen-uniq-id-update/{EVENT_ID}/{stored_screen.id}',
        data={'uniq_id': f'{old_uniq_id}-renamed'},
    )
    assert response.status_code == 200
    # The renamed ID replaces the subtitle only, leaving the title in place.
    assert response.headers['HX-Retarget'] == '.sc-modal-subtitle'
    assert 'modal-title' not in response.text

    renamed = http.get(f'/event/{EVENT_ID}/screens')
    assert f'/view/screen/{EVENT_ID}/{old_uniq_id}-renamed' in renamed.text
    assert http.get(f'/view/screen/{EVENT_ID}/{old_uniq_id}-renamed').status_code == 200


@pytest.mark.unit
@pytest.mark.parametrize(
    ('screen_type', 'row_class', 'expected', 'first', 'last'),
    [
        (ScreenType.BOARDS, 'board-row', 8, 'ALYX', 'IRINA'),
        (ScreenType.PLAYERS, 'player-row', 16, 'ALYX', 'STEPHAN'),
    ],
)
def test_a_screen_of_its_own_shows_the_whole_tournament(
    http: TestClient,
    api: ApiClient,
    tournament: StoredTournament,
    screen_type: ScreenType,
    row_class: str,
    expected: int,
    first: str,
    last: str,
):
    """What a multi-screen splits, a single screen shows in one."""
    stored_screen = TestUtils.create_screen(
        api,
        EVENT_ID,
        'Whole tournament',
        screen_type,
        {'init_set_tournament_ids': [tournament.id]},
    )
    response = http.get(f'/view/screen/{EVENT_ID}/{stored_screen.uniq_id}')
    assert response.status_code == 200
    parser = AdvancedHTMLParser()
    parser.parseStr(response.text)
    shown = [
        ' '.join(element.textContent.split())
        for element in parser.getElementsByTagName('div')
        if row_class in (element.getAttribute('class') or '').split()
    ]
    assert len(shown) == expected
    assert first in shown[0]
    assert last in shown[-1]


@pytest.mark.unit
@pytest.mark.parametrize(
    'screen_type',
    [ScreenType.BOARDS, ScreenType.PLAYERS, ScreenType.CHECK_IN],
)
def test_the_create_modal_opens_for_every_screen_type(
    http: TestClient, tournament: StoredTournament, screen_type: ScreenType
):
    """Each type asks for its own fields, so each has its own form to
    open."""
    response = http.get(f'/screen-modal/create/{EVENT_ID}/{screen_type.value}')
    assert response.status_code == 200


@pytest.mark.unit
@pytest.mark.parametrize('action', ['update', 'clone', 'delete'])
def test_the_screen_modal_opens_for_every_action(
    http: TestClient, api: ApiClient, tournament: StoredTournament, action: str
):
    stored_screen = TestUtils.create_screen(
        api,
        EVENT_ID,
        'Modal screen',
        ScreenType.BOARDS,
        {'init_set_tournament_ids': [tournament.id]},
    )
    response = http.get(f'/screen-modal/{action}/{EVENT_ID}/{stored_screen.id}')
    assert response.status_code == 200


@pytest.mark.unit
def test_the_sets_of_a_screen_are_added_and_removed(
    http: TestClient, api: ApiClient, tournament: StoredTournament
):
    """A screen shows one or more sets — a period of a tournament each —
    and the second one is what makes a screen worth splitting."""
    stored_screen = TestUtils.create_screen(
        api,
        EVENT_ID,
        'Two sets',
        ScreenType.BOARDS,
        {'init_set_tournament_ids': [tournament.id]},
    )
    assert (
        http.get(f'/screen-sets-modal/{EVENT_ID}/{stored_screen.id}').status_code == 200
    )
    added = http.post(f'/screen-set-create/{EVENT_ID}/{stored_screen.id}')
    assert added.status_code == 200

    EventLoader.unload_event(EVENT_ID)
    event = EventLoader().load_event(EVENT_ID)
    screen = event.basic_screens_by_id[stored_screen.id]
    assert len(screen.screen_sets) == 2
    set_id = list(screen.screen_sets)[-1].id

    removed = http.delete(f'/screen-set-delete/{EVENT_ID}/{stored_screen.id}/{set_id}')
    assert removed.status_code == 200
    EventLoader.unload_event(EVENT_ID)
    reloaded = EventLoader().load_event(EVENT_ID)
    assert len(reloaded.basic_screens_by_id[stored_screen.id].screen_sets) == 1


@pytest.mark.unit
@pytest.mark.parametrize('family_type', [ScreenType.BOARDS, ScreenType.PLAYERS])
def test_the_create_modal_opens_for_every_family_type(
    http: TestClient, tournament: StoredTournament, family_type: ScreenType
):
    response = http.get(f'/family-modal/create/{EVENT_ID}/{family_type.value}')
    assert response.status_code == 200


@pytest.mark.unit
@pytest.mark.parametrize('action', ['update', 'delete'])
def test_the_family_modal_opens_for_every_action(
    http: TestClient, api: ApiClient, tournament: StoredTournament, action: str
):
    stored_family = TestUtils.create_family(
        api, EVENT_ID, tournament, FAMILY_ID, ScreenType.BOARDS, {'parts': 2}
    )
    response = http.get(f'/family-modal/{action}/{EVENT_ID}/{stored_family.id}')
    assert response.status_code == 200


@pytest.mark.unit
def test_the_link_to_a_multi_screen_follows_its_renaming(
    http: TestClient, api: ApiClient, tournament: StoredTournament
):
    stored_family = TestUtils.create_family(
        api, EVENT_ID, tournament, FAMILY_ID, ScreenType.BOARDS, {'parts': 2}
    )
    response = http.patch(
        f'/family-uniq-id-update/{EVENT_ID}/{stored_family.id}',
        data={'uniq_id': f'{FAMILY_ID}-renamed'},
    )
    assert response.status_code == 200
    assert response.headers['HX-Retarget'] == '.sc-modal-subtitle'
    assert 'modal-title' not in response.text
    assert (
        http.get(f'/view/screen/{EVENT_ID}/{FAMILY_ID}-renamed:001').status_code == 200
    )


@pytest.mark.unit
@pytest.mark.parametrize(
    ('screen_type', 'shown'), [(ScreenType.IMAGE, False), (ScreenType.BOARDS, True)]
)
@pytest.mark.parametrize('headers', [{}, {'HX-Request': 'true'}])
def test_the_footer_is_left_out_of_image_screens(
    http: TestClient,
    api: ApiClient,
    tournament: StoredTournament,
    screen_type: ScreenType,
    shown: bool,
    headers: dict[str, str],
):
    """The footer is left out of an image screen when it is opened and
    when it is refreshed."""
    stored_screen = TestUtils.create_screen(
        api,
        EVENT_ID,
        'Footer screen',
        screen_type,
        {'background_image_upload': ONE_PIXEL_PNG}
        if screen_type == ScreenType.IMAGE
        else {'init_set_tournament_ids': [tournament.id]},
    )
    response = http.get(
        f'/view/screen/{EVENT_ID}/{stored_screen.uniq_id}', headers=headers
    )
    assert response.status_code == 200
    assert ('id="copyright"' in response.text) == shown


@pytest.mark.unit
@pytest.mark.parametrize(
    ('screen_type', 'row_class'),
    [(ScreenType.BOARDS, 'board-row'), (ScreenType.PLAYERS, 'player-row')],
)
def test_a_pairings_screen_waits_for_the_tournament_to_start(
    http: TestClient,
    api: ApiClient,
    tournament: StoredTournament,
    screen_type: ScreenType,
    row_class: str,
):
    waiting = TestUtils.create_tournament(EVENT_ID, 'Not started yet')
    stored_screen = TestUtils.create_screen(
        api,
        EVENT_ID,
        'Waiting',
        screen_type,
        {'init_set_tournament_ids': [waiting.id]},
    )
    response = http.get(f'/view/screen/{EVENT_ID}/{stored_screen.uniq_id}')
    assert response.status_code == 200
    assert 'The tournament has not yet started.' in response.text
    assert row_class not in response.text
    assert 'check-in-mark' not in response.text


def set_tournaments(screen_id: int | None) -> list[tuple[str, int, int]]:
    """The tournament, first and last of each set of a screen, in order."""
    event = EventLoader().load_event(EVENT_ID)
    screen = event.basic_screens_by_id[screen_id or 0]
    return [
        (screen_set.tournament.name, screen_set.first, screen_set.last)
        for screen_set in screen.sorted_screen_sets
    ]


@pytest.mark.unit
def test_a_duplicate_offers_the_tournaments_of_the_original(
    http: TestClient, api: ApiClient, tournament: StoredTournament
):
    screen = TestUtils.create_screen(
        api,
        EVENT_ID,
        'Pairings',
        ScreenType.BOARDS,
        {'init_set_tournament_ids': [tournament.id]},
    )
    response = http.get(f'/screen-modal/clone/{EVENT_ID}/{screen.id}')
    assert response.status_code == 200
    parser = AdvancedHTMLParser()
    parser.parseStr(response.text)
    selected = [
        option.getAttribute('value')
        for option in parser.getElementsByTagName('option')
        if option.hasAttribute('selected')
        and option.parentNode.getAttribute('name') == 'init_set_tournament_ids'
    ]
    assert selected == [str(tournament.id)]


@pytest.mark.unit
@pytest.mark.parametrize(('name', 'duplicate_named'), [('Pairings', True), ('', False)])
def test_a_duplicate_is_named_only_after_a_screen_with_a_name_of_its_own(
    http: TestClient,
    api: ApiClient,
    tournament: StoredTournament,
    name: str,
    duplicate_named: bool,
):
    screen = TestUtils.create_screen(
        api,
        EVENT_ID,
        name,
        ScreenType.BOARDS,
        {'init_set_tournament_ids': [tournament.id]},
    )
    response = http.get(f'/screen-modal/clone/{EVENT_ID}/{screen.id}')
    parser = AdvancedHTMLParser()
    parser.parseStr(response.text)
    value = next(
        field.getAttribute('value') or ''
        for field in parser.getElementsByTagName('input')
        if field.getAttribute('name') == 'name'
    )
    assert bool(value) == duplicate_named
    if duplicate_named:
        assert value != name


@pytest.mark.unit
def test_a_duplicate_keeps_the_sets_of_the_tournaments_kept_and_adds_the_others(
    http: TestClient, api: ApiClient, tournament: StoredTournament
):
    other = TestUtils.create_tournament(EVENT_ID, 'Other', json_file='test-screens')
    screen = TestUtils.create_screen(
        api,
        EVENT_ID,
        'Pairings',
        ScreenType.BOARDS,
        {'init_set_tournament_ids': [tournament.id]},
    )
    EventLoader.unload_event(EVENT_ID)
    event = EventLoader().load_event(EVENT_ID)
    original_sets = set_tournaments(screen.id)
    before = set(event.basic_screens_by_id)

    response = http.post(
        f'/screen-clone/{EVENT_ID}/{screen.id}',
        data={
            'name': 'Both',
            'init_set_tournament_ids': [str(tournament.id), str(other.id)],
        },
    )
    assert response.status_code == 200
    EventLoader.unload_event(EVENT_ID)
    event = EventLoader().load_event(EVENT_ID)
    (duplicate_id,) = set(event.basic_screens_by_id) - before
    assert set_tournaments(duplicate_id) == [*original_sets, ('Other', 0, 0)]


@pytest.mark.unit
@pytest.mark.parametrize('show_members', [True, False])
def test_a_team_check_in_screen_can_list_the_members_of_each_team(
    http: TestClient, api: ApiClient, team_round_robin: int, show_members: bool
):
    stored_screen = TestUtils.create_screen(
        api,
        TEAM_EVENT_ID,
        'Check-in',
        ScreenType.CHECK_IN,
        {
            'init_set_tournament_ids': [team_round_robin],
            'check_in_show_members': show_members,
        },
    )
    response = http.get(f'/view/screen/{TEAM_EVENT_ID}/{stored_screen.uniq_id}')
    assert response.status_code == 200
    assert ('T1P0' in response.text) is show_members


def live_update(
    http: TestClient,
    screen_uniq_id: str,
    board_ids: list[int] | None = None,
    player_ids: list[int] | None = None,
) -> str:
    response = http.get(
        f'/view/screen/{EVENT_ID}/{screen_uniq_id}',
        headers={
            'X-Sharly-Chess-Live-Update': json.dumps(
                {'board_ids': board_ids or [], 'player_ids': player_ids or []}
            )
        },
    )
    assert response.status_code == 200
    return response.text


def live_keys(text: str) -> list[str]:
    parser = AdvancedHTMLParser()
    parser.parseStr(text)
    return [
        element.getAttribute('data-live-key')
        for element in parser.getAllNodes()
        if element.getAttribute('data-live-key')
    ]


def current_board_ids() -> list[int]:
    EventLoader.unload_event(EVENT_ID)
    event = EventLoader().load_event(EVENT_ID)
    tournament = event.tournaments_by_name[TOURNAMENT_NAME]
    return [
        board.identifier
        for board in tournament.get_round_boards(tournament.current_round)
    ]


@pytest.mark.unit
@pytest.mark.parametrize(('accepts_input', 'per_board'), [(False, 1), (True, 2)])
def test_a_live_update_of_a_boards_screen_renders_only_the_boards_named(
    http: TestClient,
    api: ApiClient,
    tournament: StoredTournament,
    accepts_input: bool,
    per_board: int,
):
    """The boards named come back with the title of their set: their row, and
    their card on a screen taking results."""
    stored_screen = TestUtils.create_screen(
        api,
        EVENT_ID,
        'Boards',
        ScreenType.BOARDS,
        {'init_set_tournament_ids': [tournament.id], 'accepts_input': accepts_input},
    )
    board_ids = current_board_ids()
    page = http.get(f'/view/screen/{EVENT_ID}/{stored_screen.uniq_id}').text
    assert 'data-url="' in page
    named = board_ids[2]
    text = live_update(http, stored_screen.uniq_id, [named])
    assert f'data-screen="{stored_screen.uniq_id}"' in text
    assert sorted(live_keys(text)) == sorted(
        ['set-1-title', f'board-{named}-row']
        + ([f'board-{named}-card'] if accepts_input else [])
    )
    assert len(live_keys(text)) == 1 + per_board
    page_keys = live_keys(page)
    assert all(key in page_keys for key in live_keys(text))


def refresh_status(http: TestClient, screen_uniq_id: str, drawn_at: float) -> int:
    return http.get(
        f'/view/screen/{EVENT_ID}/{screen_uniq_id}',
        headers={'X-Sharly-Chess-If-Modified-Since': str(drawn_at)},
    ).status_code


def first_player_id(tournament_name: str) -> int:
    EventLoader.unload_event(EVENT_ID)
    event = EventLoader().load_event(EVENT_ID)
    tournament = event.tournaments_by_name[tournament_name]
    return min(player.id for player in tournament.tournament_players)


@pytest.mark.unit
def test_a_screen_is_drawn_again_only_for_a_change_it_shows(
    http: TestClient, api: ApiClient, tournament: StoredTournament
):
    TestUtils.create_tournament(EVENT_ID, 'Other', json_file='test-screens')
    stored_screen = TestUtils.create_screen(
        api,
        EVENT_ID,
        'Boards',
        ScreenType.BOARDS,
        {'init_set_tournament_ids': [tournament.id]},
    )
    drawn_at = time.time()
    time.sleep(0.05)
    assert refresh_status(http, stored_screen.uniq_id, drawn_at) == 304

    http.patch(f'/records/withdraw-player/{EVENT_ID}/{first_player_id("Other")}')
    assert refresh_status(http, stored_screen.uniq_id, drawn_at) == 304

    http.patch(
        f'/records/withdraw-player/{EVENT_ID}/{first_player_id(TOURNAMENT_NAME)}'
    )
    assert refresh_status(http, stored_screen.uniq_id, drawn_at) == 200

    drawn_at = time.time()
    time.sleep(0.05)
    TestUtils.create_screen(
        api,
        EVENT_ID,
        'Other boards',
        ScreenType.BOARDS,
        {'init_set_tournament_ids': [tournament.id]},
    )
    assert refresh_status(http, stored_screen.uniq_id, drawn_at) == 200


@pytest.mark.unit
def test_a_rotator_draws_its_page_again_only_when_it_changed(
    http: TestClient, api: ApiClient, tournament: StoredTournament
):
    """Turning to a page always draws it; drawing the page shown again is
    answered with "not modified" until something it shows changes."""
    screen = TestUtils.create_screen(
        api,
        EVENT_ID,
        'Boards',
        ScreenType.BOARDS,
        {'init_set_tournament_ids': [tournament.id]},
    )
    rotator_id = TestUtils.create_rotator(
        api, EVENT_ID, 'Rotator', screen_ids=[screen.id]
    )
    url = f'/view/rotator/{EVENT_ID}/{rotator_id}/0'
    drawn_at = time.time()
    time.sleep(0.05)
    turning = {'X-Sharly-Chess-If-Modified-Since': str(drawn_at)}
    redrawing = turning | {'X-Sharly-Chess-Redraw': 'true'}
    assert http.get(url, headers=turning).status_code == 200
    assert http.get(url, headers=redrawing).status_code == 304
    TestUtils.create_screen(
        api,
        EVENT_ID,
        'Other boards',
        ScreenType.BOARDS,
        {'init_set_tournament_ids': [tournament.id]},
    )
    assert http.get(url, headers=redrawing).status_code == 200


def current_player_ids() -> list[int]:
    EventLoader.unload_event(EVENT_ID)
    event = EventLoader().load_event(EVENT_ID)
    tournament = event.tournaments_by_name[TOURNAMENT_NAME]
    return sorted(player.id for player in tournament.tournament_players)


@pytest.mark.unit
@pytest.mark.parametrize('screen_type', [ScreenType.CHECK_IN, ScreenType.PLAYERS])
def test_a_live_update_of_a_players_screen_renders_only_the_players_named(
    http: TestClient,
    api: ApiClient,
    tournament: StoredTournament,
    screen_type: ScreenType,
):
    stored_screen = TestUtils.create_screen(
        api,
        EVENT_ID,
        'Players',
        screen_type,
        {'init_set_tournament_ids': [tournament.id]},
    )
    page = http.get(f'/view/screen/{EVENT_ID}/{stored_screen.uniq_id}').text
    named = current_player_ids()[:2]
    text = live_update(http, stored_screen.uniq_id, player_ids=named)
    assert sorted(live_keys(text)) == sorted(
        f'player-{player_id}' for player_id in named
    )
    assert all(key in live_keys(page) for key in live_keys(text))
