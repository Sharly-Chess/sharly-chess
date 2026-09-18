"""What each access level may reach, asked of the application directly.

An account is given one access level, signs in from the network the way
a visitor does, and the pages it is offered are read back: the tabs it
may open, the screens it may see, and whether the rows of those screens
carry the links that enter a result or check a player in.

Every expectation below is stated once, in ``EXPECTATIONS``, so a level
that gains or loses a right is a line of the table rather than a file.
"""

from collections.abc import Iterator
from dataclasses import dataclass

import pytest
from AdvancedHTMLParser import AdvancedHTMLParser, AdvancedTag
from httpx import Response
from litestar.testing import TestClient

from data.access_levels.access_levels import (
    AccessLevel,
    CheckInAccessLevel,
    ChiefArbitrationAccessLevel,
    DeputyChiefArbitrationAccessLevel,
    OrganizationAccessLevel,
    PairingAccessLevel,
    ResultsEntryAccessLevel,
    ScreenManagementAccessLevel,
    SectorArbitrationAccessLevel,
    SpectatorAccessLevel,
)
from data.loader import EventLoader
from data.tournament import Tournament
from database.sqlite.event.event_database import EventDatabase
from database.sqlite.event.event_store import StoredScreen
from utils.enum import Result
from tests.test_config import ScreenType, TestUtils
from tests.unit.http.client import ApiClient

PUBLIC_EVENT_ID = 'test-access-levels-public'
PRIVATE_EVENT_ID = 'test-access-levels-private'
TOURNAMENT_NAME = 'test-access-levels-tournament'
UNPAIRED_TOURNAMENT_NAME = 'test-access-levels-unpaired'
PASSWORD = 'test-password'


@dataclass(frozen=True)
class Rights:
    """What one access level is expected to reach."""

    players_tab: bool
    pairings_tab: bool
    private_screen: bool
    check_in_via_screen: bool
    enter_results: bool
    update_results: bool
    #: Whether the result form offers the forfeit buttons, and whether a
    #: forfeit sent without them is recorded. The two answer alike: the
    #: form's own right is what the handler asks for.
    forfeit_offered: bool
    forfeit_accepted: bool
    illegal_moves: bool


EXPECTATIONS: dict[str, tuple[list[type[AccessLevel]], Rights]] = {
    # Not a level but the absence of one: what a visitor who has not
    # signed in is given by the event's own anonymous account, which a
    # public event leaves able to enter results and check players in.
    'anonymous': (
        [],
        Rights(False, False, False, True, True, False, False, False, False),
    ),
    'spectator': (
        [SpectatorAccessLevel],
        Rights(False, False, False, False, False, False, False, False, False),
    ),
    'check-in': (
        [CheckInAccessLevel],
        Rights(False, False, False, True, False, False, False, False, False),
    ),
    'results-entry': (
        [ResultsEntryAccessLevel],
        Rights(False, False, False, False, True, False, False, False, False),
    ),
    'screen-management': (
        [ScreenManagementAccessLevel],
        Rights(False, False, True, False, False, False, False, False, False),
    ),
    'organization': (
        [OrganizationAccessLevel],
        Rights(False, False, True, False, False, False, False, False, False),
    ),
    'sector-arbitration': (
        [SectorArbitrationAccessLevel],
        Rights(True, True, False, True, True, True, False, False, True),
    ),
    'pairing': (
        [PairingAccessLevel],
        Rights(True, True, False, True, True, True, False, False, True),
    ),
    'deputy-chief-arbitration': (
        [DeputyChiefArbitrationAccessLevel],
        Rights(True, True, True, True, True, True, True, True, True),
    ),
    'chief-arbitration': (
        [ChiefArbitrationAccessLevel],
        Rights(True, True, True, True, True, True, True, True, True),
    ),
}


@dataclass
class Fixtures:
    public_screen: StoredScreen
    private_screen: StoredScreen
    check_in_screen: StoredScreen
    tournament_id: int
    unpaired_tournament_id: int


@pytest.fixture(scope='module')
def events(api: ApiClient) -> Iterator[Fixtures]:
    """A public event with a paired tournament and three screens, and a
    private event nobody outside the organisers may see."""
    TestUtils.create_event(PUBLIC_EVENT_ID, overrides={'public': True})
    TestUtils.create_event(PRIVATE_EVENT_ID, overrides={'public': False})
    tournament = TestUtils.create_tournament(
        PUBLIC_EVENT_ID,
        TOURNAMENT_NAME,
        json_file='test-screens',
        overrides={'record_illegal_moves': 1},
    )
    unpaired = TestUtils.create_tournament(
        PUBLIC_EVENT_ID,
        UNPAIRED_TOURNAMENT_NAME,
        json_file='test-screens-unpaired',
    )
    assert tournament.id is not None
    assert unpaired.id is not None
    yield Fixtures(
        tournament_id=tournament.id,
        unpaired_tournament_id=unpaired.id,
        public_screen=TestUtils.create_screen(
            api,
            PUBLIC_EVENT_ID,
            'Public input screen',
            ScreenType.INPUT,
            {'init_set_tournament_id': tournament.id, 'public': True},
        ),
        private_screen=TestUtils.create_screen(
            api,
            PUBLIC_EVENT_ID,
            'Private input screen',
            ScreenType.INPUT,
            {'init_set_tournament_id': tournament.id, 'public': False},
        ),
        check_in_screen=TestUtils.create_screen(
            api,
            PUBLIC_EVENT_ID,
            'Check-in screen',
            ScreenType.CHECK_IN,
            {'init_set_tournament_id': unpaired.id, 'public': True},
        ),
    )
    TestUtils.delete_event(PUBLIC_EVENT_ID)
    TestUtils.delete_event(PRIVATE_EVENT_ID)


def sign_in(
    http: TestClient, lan: TestClient, access_levels: list[type[AccessLevel]]
) -> None:
    """Create an account holding these access levels and sign the network
    client in as it. An account with none of them is left signed out, the
    way a visitor arrives."""
    if not access_levels:
        return
    name = access_levels[0].static_id()
    created = http.post(
        f'/account-create/{PUBLIC_EVENT_ID}',
        data={
            'first_name': 'Test',
            'last_name': name,
            'password': PASSWORD,
            'active': 'on',
        },
    )
    assert created.status_code == 200
    with EventDatabase(PUBLIC_EVENT_ID) as database:
        account = next(
            stored
            for stored in database.load_stored_accounts()
            if stored.last_name == name
        )
    # A new account inherits the anonymous account's permissions, which
    # would answer for the level under test.
    with EventDatabase(PUBLIC_EVENT_ID, write=True) as database:
        for permission in account.stored_permissions:
            database.delete_stored_permission(permission)
    for access_level in access_levels:
        granted = http.post(
            f'/account-permission-create/{PUBLIC_EVENT_ID}/{account.id}',
            data={'access_level': access_level.static_id()},
        )
        assert granted.status_code == 200

    signed_in = lan.post(
        f'/profile-login/{PUBLIC_EVENT_ID}',
        data={'account_id': str(account.id), 'password': PASSWORD},
    )
    assert signed_in.is_success, signed_in.text


def rows(client: TestClient, url: str, row_class: str) -> list[AdvancedTag]:
    response = client.get(url)
    assert response.status_code == 200, url
    parser = AdvancedHTMLParser()
    parser.parseStr(response.text)
    return [
        element
        for element in parser.getElementsByTagName('div')
        if row_class in (element.getAttribute('class') or '').split()
    ]


def row_for(rows_: list[AdvancedTag], name: str) -> AdvancedTag:
    return next(row for row in rows_ if name in row.textContent)


def markup_of(row: AdvancedTag) -> str:
    return row.getHTML()


def assert_reaches(client: TestClient, url: str, allowed: bool) -> None:
    response = client.get(url, follow_redirects=False)
    if allowed:
        assert response.status_code == 200, url
    else:
        assert response.status_code == 302, url
        assert response.headers['location'].endswith('/error/403'), url


@pytest.fixture(params=sorted(EXPECTATIONS), ids=sorted(EXPECTATIONS))
def level(
    request: pytest.FixtureRequest, http: TestClient, lan: TestClient, events: Fixtures
) -> Rights:
    access_levels, rights = EXPECTATIONS[request.param]
    sign_in(http, lan, access_levels)
    return rights


@pytest.mark.unit
def test_the_admin_tabs_it_may_open(lan: TestClient, level: Rights):
    assert_reaches(lan, f'/event/{PUBLIC_EVENT_ID}/players', level.players_tab)
    assert_reaches(lan, f'/event/{PUBLIC_EVENT_ID}/pairings', level.pairings_tab)


@pytest.mark.unit
def test_only_the_public_event_is_listed(lan: TestClient, level: Rights):
    """A private event is the organisers' own until they publish it."""
    response = lan.get('/home')
    assert response.status_code == 200
    assert PUBLIC_EVENT_ID in response.text
    assert PRIVATE_EVENT_ID not in response.text


@pytest.mark.unit
def test_the_screens_it_may_watch(lan: TestClient, level: Rights, events: Fixtures):
    """The public screen is for anyone at the venue; the private one is
    for those the organisers have given a level that reaches it."""
    public = f'/view/screen/{PUBLIC_EVENT_ID}/{events.public_screen.uniq_id}'
    assert len(rows(lan, public, 'board-row')) == 8
    assert_reaches(
        lan,
        f'/view/screen/{PUBLIC_EVENT_ID}/{events.private_screen.uniq_id}',
        level.private_screen,
    )


@pytest.mark.unit
def test_whether_a_row_offers_the_result_form(
    lan: TestClient, level: Rights, events: Fixtures
):
    """The row carries the link that opens the result form, and carries
    it only for a level allowed to enter one."""
    board_rows = rows(
        lan,
        f'/view/screen/{PUBLIC_EVENT_ID}/{events.public_screen.uniq_id}',
        'board-row',
    )
    markup = markup_of(row_for(board_rows, 'ALYX'))
    assert ('result-modal' in markup) is level.enter_results


@pytest.mark.unit
def test_whether_an_illegal_move_can_be_recorded_from_a_screen(
    lan: TestClient, level: Rights, events: Fixtures
):
    board_rows = rows(
        lan,
        f'/view/screen/{PUBLIC_EVENT_ID}/{events.public_screen.uniq_id}',
        'board-row',
    )
    markup = markup_of(row_for(board_rows, 'ALYX'))
    assert ('add-illegal-move-button' in markup) is level.illegal_moves


@pytest.mark.unit
def test_whether_a_player_can_be_checked_in_from_a_screen(
    lan: TestClient, level: Rights, events: Fixtures
):
    player_rows = rows(
        lan,
        f'/view/screen/{PUBLIC_EVENT_ID}/{events.check_in_screen.uniq_id}',
        'player-row',
    )
    assert len(player_rows) == 16
    markup = markup_of(row_for(player_rows, 'AMOS'))
    assert ('checkin-modal' in markup) is level.check_in_via_screen


@pytest.mark.unit
@pytest.mark.parametrize(
    'name',
    sorted(name for name, (_, rights) in EXPECTATIONS.items() if rights.players_tab),
)
def test_whoever_reaches_the_players_tab_may_check_players_in_from_it(
    http: TestClient, lan: TestClient, events: Fixtures, name: str
):
    sign_in(http, lan, EXPECTATIONS[name][0])
    response = lan.get(f'/event/{PUBLIC_EVENT_ID}/players')
    assert response.status_code == 200
    assert 'player-table/check-in-player' in response.text


def first_board_and_players(event_id: str, tournament_id: int) -> tuple[int, int]:
    """The first board of the paired round, and the player sitting White
    on it."""
    EventLoader.unload_event(event_id)
    event = EventLoader().load_event(event_id)
    tournament: Tournament = event.tournaments_by_id[tournament_id]
    board = sorted(tournament.get_round_boards(1), key=lambda one: one.id)[0]
    assert board.white_player_id is not None
    return board.id, board.white_player_id


def first_player(event_id: str, tournament_id: int) -> int:
    EventLoader.unload_event(event_id)
    event = EventLoader().load_event(event_id)
    tournament: Tournament = event.tournaments_by_id[tournament_id]
    return sorted(player.id for player in tournament.tournament_players)[0]


def assert_acts(response: Response, allowed: bool) -> None:
    """A refusal is answered the way the rest of the application answers
    one: a redirect to the page that says so."""
    if allowed:
        assert response.status_code == 200, response.status_code
    else:
        assert response.status_code == 302, response.status_code
        assert response.headers['location'].endswith('/error/403')


def set_result_as_admin(
    http: TestClient, events: Fixtures, board_id: int, result: Result
) -> None:
    """The board is left in a known state before each level tries it, so
    one level's entry is not the next one's update."""
    response = http.put(
        f'/pairing/set-result/{PUBLIC_EVENT_ID}/{events.tournament_id}'
        f'/1/{board_id}/{result.value}'
    )
    assert response.status_code == 200


def send_result(
    lan: TestClient, events: Fixtures, board_id: int, result: Result
) -> Response:
    return lan.put(
        f'/view/update-result/1/{PUBLIC_EVENT_ID}/{events.public_screen.uniq_id}'
        f'/{events.tournament_id}/1/{board_id}/{result.value}',
        follow_redirects=False,
    )


@pytest.mark.unit
def test_whether_a_result_can_be_entered_from_a_screen(
    http: TestClient, lan: TestClient, level: Rights, events: Fixtures
):
    """A row carrying no link is one thing; a request sent anyway is what
    the guard is there for."""
    board_id, _white = first_board_and_players(PUBLIC_EVENT_ID, events.tournament_id)
    set_result_as_admin(http, events, board_id, Result.NO_RESULT)
    assert_acts(send_result(lan, events, board_id, Result.WIN), level.enter_results)


@pytest.mark.unit
def test_whether_a_result_already_entered_can_be_changed(
    http: TestClient, lan: TestClient, level: Rights, events: Fixtures
):
    """Entering the result of a game that has just finished and changing
    one already recorded are different rights: the second is the one that
    rewrites the standings."""
    board_id, _white = first_board_and_players(PUBLIC_EVENT_ID, events.tournament_id)
    set_result_as_admin(http, events, board_id, Result.WIN)
    assert_acts(send_result(lan, events, board_id, Result.LOSS), level.update_results)


@pytest.mark.unit
def test_whether_a_forfeit_can_be_recorded_from_a_screen(
    http: TestClient, lan: TestClient, level: Rights, events: Fixtures
):
    """A forfeit is the arbiter's to record: a level the form keeps the
    buttons from does not get one in by sending the request itself."""
    board_id, _white = first_board_and_players(PUBLIC_EVENT_ID, events.tournament_id)
    set_result_as_admin(http, events, board_id, Result.NO_RESULT)
    assert_acts(
        send_result(lan, events, board_id, Result.FORFEIT_WIN),
        level.forfeit_accepted,
    )


@pytest.mark.unit
def test_whether_an_illegal_move_sent_from_a_screen_is_recorded(
    lan: TestClient, level: Rights, events: Fixtures
):
    _board_id, white = first_board_and_players(PUBLIC_EVENT_ID, events.tournament_id)
    response = lan.put(
        f'/view/add-illegal-move/1/{PUBLIC_EVENT_ID}/{events.public_screen.uniq_id}'
        f'/{events.tournament_id}/{white}',
        follow_redirects=False,
    )
    assert_acts(response, level.illegal_moves)


@pytest.mark.unit
def test_whether_a_check_in_sent_from_a_screen_is_taken(
    lan: TestClient, level: Rights, events: Fixtures
):
    player_id = first_player(PUBLIC_EVENT_ID, events.unpaired_tournament_id)
    response = lan.patch(
        f'/view/toggle-check-in/1/{PUBLIC_EVENT_ID}/{events.check_in_screen.uniq_id}'
        f'/{events.unpaired_tournament_id}/{player_id}',
        follow_redirects=False,
    )
    assert_acts(response, level.check_in_via_screen)


@pytest.mark.unit
def test_which_levels_are_offered_the_forfeit_buttons(
    lan: TestClient, level: Rights, events: Fixtures
):
    """The form is where a forfeit is normally reached, and it offers the
    buttons to the two arbitration levels alone."""
    board_id, _white = first_board_and_players(PUBLIC_EVENT_ID, events.tournament_id)
    response = lan.get(
        f'/view/result-modal/1/{PUBLIC_EVENT_ID}/{events.public_screen.uniq_id}'
        f'/{events.tournament_id}/{board_id}',
        follow_redirects=False,
    )
    if not level.enter_results:
        assert response.status_code in (200, 302)
        return
    assert response.status_code == 200
    assert ('wins-by-forfeit-button' in response.text) is level.forfeit_offered
