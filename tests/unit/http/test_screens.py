"""The screens a venue shows, rendered in this process.

A multi-screen splits a tournament over several screens, either into a
given number of parts or into screens of a given number of rows, and
each part is fetched under its own number. What lands on each one is
decided on the server and read back from the HTML here, where the
browser suite was starting a browser per part to do the same.
"""

from collections.abc import Iterator

import pytest
from AdvancedHTMLParser import AdvancedHTMLParser
from litestar.testing import TestClient

from data.loader import EventLoader
from database.sqlite.event.event_store import StoredTournament
from tests.test_config import ScreenType, TestUtils
from tests.unit.http.client import ApiClient

EVENT_ID = 'test-screens-http'
TOURNAMENT_NAME = 'test-screens-http-tournament'
FAMILY_ID = 'test-screens-http-family'


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
    [(ScreenType.INPUT, 'board-row'), (ScreenType.BOARDS, 'board-row')],
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
        api, EVENT_ID, tournament, FAMILY_ID, ScreenType.INPUT, {'parts': 2}
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
        {'init_set_tournament_id': tournament.id},
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
        ScreenType.INPUT,
        {'init_set_tournament_id': tournament.id},
    )
    old_uniq_id = stored_screen.uniq_id
    listed = http.get(f'/event/{EVENT_ID}/input-screens')
    assert f'/view/screen/{EVENT_ID}/{old_uniq_id}' in listed.text

    response = http.patch(
        f'/screen-uniq-id-update/{EVENT_ID}/{stored_screen.id}',
        data={'uniq_id': f'{old_uniq_id}-renamed'},
    )
    assert response.status_code == 200

    renamed = http.get(f'/event/{EVENT_ID}/input-screens')
    assert f'/view/screen/{EVENT_ID}/{old_uniq_id}-renamed' in renamed.text
    assert http.get(f'/view/screen/{EVENT_ID}/{old_uniq_id}-renamed').status_code == 200


@pytest.mark.unit
@pytest.mark.parametrize(
    ('screen_type', 'row_class', 'expected', 'first', 'last'),
    [
        (ScreenType.BOARDS, 'board-row', 8, 'ALYX', 'IRINA'),
        (ScreenType.INPUT, 'board-row', 8, 'ALYX', 'IRINA'),
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
        {'init_set_tournament_id': tournament.id},
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
    [ScreenType.BOARDS, ScreenType.INPUT, ScreenType.PLAYERS, ScreenType.CHECK_IN],
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
        {'init_set_tournament_id': tournament.id},
    )
    response = http.get(f'/screen-modal/{action}/{EVENT_ID}/{stored_screen.id}')
    assert response.status_code == 200


@pytest.mark.unit
def test_the_sets_of_a_screen_are_added_and_removed(
    http: TestClient, api: ApiClient, tournament: StoredTournament
):
    """A screen shows one or more sets — a slice of a tournament each —
    and the second one is what makes a screen worth splitting."""
    stored_screen = TestUtils.create_screen(
        api,
        EVENT_ID,
        'Two sets',
        ScreenType.BOARDS,
        {'init_set_tournament_id': tournament.id},
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
@pytest.mark.parametrize('family_type', [ScreenType.BOARDS, ScreenType.INPUT])
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
    assert (
        http.get(f'/view/screen/{EVENT_ID}/{FAMILY_ID}-renamed:001').status_code == 200
    )
