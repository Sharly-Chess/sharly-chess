"""Fake data on the screens: a made-up first round for the tournaments that
have not started, while the screens are being set up. Nothing is written."""

from collections.abc import Iterator
from dataclasses import dataclass, replace

import pytest
from AdvancedHTMLParser import AdvancedHTMLParser
from litestar.testing import TestClient

from data.loader import EventLoader
from database.sqlite.event.event_database import EventDatabase
from database.sqlite.event.event_store import StoredTournament
from tests.test_config import ScreenType, TestUtils
from tests.unit.http.client import ApiClient

EVENT_ID = 'test-screens-fake-data-http'


@dataclass
class Fixtures:
    waiting: StoredTournament
    started: StoredTournament


@pytest.fixture
def tournaments(api: ApiClient) -> Iterator[Fixtures]:
    TestUtils.create_event(EVENT_ID)
    yield Fixtures(
        waiting=TestUtils.create_tournament(
            EVENT_ID, 'Not started', json_file='test-screens-unpaired'
        ),
        started=TestUtils.create_tournament(
            EVENT_ID, 'Started', json_file='test-screens'
        ),
    )
    EventLoader.unload_event(EVENT_ID)
    TestUtils.delete_event(EVENT_ID)


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


def stored_waiting(tournament: StoredTournament) -> tuple:
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
        [
            (player.player_id, player.pairing_number, list(player.stored_pairings))
            for player in stored.stored_tournament_players
        ],
    )


def set_fake_data(http: TestClient, on: bool) -> None:
    response = http.patch(f'/screens-fake-data/{EVENT_ID}/{int(on)}')
    assert response.status_code == 200


@pytest.mark.unit
@pytest.mark.parametrize(
    ('screen_type', 'row_class'),
    [(ScreenType.BOARDS, 'board-row'), (ScreenType.PLAYERS, 'player-row')],
)
def test_a_tournament_not_started_is_shown_with_a_made_up_round(
    http: TestClient,
    api: ApiClient,
    tournaments: Fixtures,
    screen_type: ScreenType,
    row_class: str,
):
    before = stored_waiting(tournaments.waiting)
    set_fake_data(http, True)
    shown = screen_text(http, api, tournaments.waiting, screen_type)
    assert row_class in shown
    assert 'data-testid="fake-data-notice"' in shown
    assert '/view/result-modal/' not in shown
    assert stored_waiting(tournaments.waiting) == before


@pytest.mark.unit
def test_the_ranking_counts_the_made_up_round(
    http: TestClient, api: ApiClient, tournaments: Fixtures
):
    set_fake_data(http, True)
    shown = screen_text(http, api, tournaments.waiting, ScreenType.RANKING)
    assert 'data-testid="fake-data-notice"' in shown
    assert '½' in shown


@pytest.mark.unit
def test_a_started_tournament_keeps_its_real_data(
    http: TestClient, api: ApiClient, tournaments: Fixtures
):
    set_fake_data(http, True)
    shown = screen_text(http, api, tournaments.started, ScreenType.BOARDS)
    assert 'fake-data-notice' not in shown


@pytest.mark.unit
def test_without_fake_data_a_tournament_not_started_waits(
    http: TestClient, api: ApiClient, tournaments: Fixtures
):
    shown = screen_text(http, api, tournaments.waiting, ScreenType.BOARDS)
    assert 'The tournament has not yet started.' in shown
    assert 'fake-data-notice' not in shown


@pytest.mark.unit
def test_the_display_tabs_say_when_the_screens_show_fake_data(
    http: TestClient, tournaments: Fixtures
):
    assert 'screens-fake-data-banner' not in http.get(f'/event/{EVENT_ID}/screens').text
    set_fake_data(http, True)
    for tab in ('screens', 'display_controllers', 'rotators', 'menus', 'timers'):
        assert 'screens-fake-data-banner' in http.get(f'/event/{EVENT_ID}/{tab}').text
    set_fake_data(http, False)
    assert 'screens-fake-data-banner' not in http.get(f'/event/{EVENT_ID}/screens').text


def board_one(text: str) -> str:
    parser = AdvancedHTMLParser()
    parser.parseStr(text)
    rows = [
        row
        for row in parser.getElementsByTagName('div')
        if (row.getAttribute('id') or '').endswith('-board-1-row')
    ]
    assert rows
    return ' '.join(rows[0].textContent.split())


@pytest.mark.unit
@pytest.mark.parametrize(
    ('variation_id', 'opponent', 'draws'),
    [
        ('SWISS_STANDARD', 'JACK', True),
        ('SWISS_BAKU', 'JACK', True),
        ('ROUND_ROBIN_BERGER', 'SIMON', True),
        ('ROUND_ROBIN_DOUBLE_CUSTOM', 'SIMON', True),
        ('KNOCKOUT_STANDARD', 'SIMON', False),
        ('KNOCKOUT_DOUBLE_ELIMINATION_TWO_GAME', 'SIMON', False),
        ('KEIZER_STANDARD', 'BARBARA', True),
    ],
)
def test_the_made_up_round_is_paired_the_way_its_system_pairs(
    http: TestClient,
    api: ApiClient,
    tournaments: Fixtures,
    variation_id: str,
    opponent: str,
    draws: bool,
):
    """The top player, AMOS, meets the middle of the field in a Swiss, the
    last player in a round robin or a knock-out, and the next one in a
    Keizer. A knock-out game has a winner."""
    with EventDatabase(EVENT_ID, True) as database:
        stored = database.get_stored_tournament(tournaments.waiting.id or 0)
        assert stored is not None
        database.update_stored_tournament(replace(stored, pairing=variation_id))
    EventLoader.unload_event(EVENT_ID)
    set_fake_data(http, True)
    shown = screen_text(http, api, tournaments.waiting, ScreenType.BOARDS)
    first = board_one(shown)
    assert 'AMOS' in first
    assert opponent in first
    assert ('½-½' in shown) is draws


@pytest.mark.unit
def test_the_button_shows_only_when_a_tournament_can_take_fake_data(
    http: TestClient, api: ApiClient
):
    TestUtils.create_event(EVENT_ID)
    try:
        TestUtils.create_tournament(EVENT_ID, 'Started', json_file='test-screens')
        toggle = 'data-testid="screens-fake-data-toggle"'
        assert toggle not in http.get(f'/event/{EVENT_ID}/screens').text
        TestUtils.create_tournament(
            EVENT_ID, 'Not started', json_file='test-screens-unpaired'
        )
        EventLoader.unload_event(EVENT_ID)
        assert toggle in http.get(f'/event/{EVENT_ID}/screens').text
    finally:
        EventLoader.unload_event(EVENT_ID)
        TestUtils.delete_event(EVENT_ID)
