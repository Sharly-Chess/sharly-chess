"""Result entry on an input screen shown through a display controller, over
HTTP, when the database ids of the round's boards overlap their table
numbers, as they do once other boards have been created in the event."""

import re
from collections.abc import Iterator

import pytest
from litestar.testing import TestClient

from data.tournament import Tournament
from database.sqlite.event.event_database import EventDatabase
from tests.test_config import ScreenType, TestUtils
from tests.unit.http.client import ApiClient
from tests.unit.http.events import EventUnderTest

EVENT_ID = 'test-display-controller-result-entry-http'
TOURNAMENT_NAME = 'test-display-controller-result-entry-http-tournament'
SCREEN_ID = 'test-display-controller-result-entry-http-screen'
CONTROLLER_NAME = 'test-display-controller-result-entry-http-controller'
BOARDS_CREATED_BEFORE = 3

EVENT = EventUnderTest(EVENT_ID, TOURNAMENT_NAME)


@pytest.fixture
def tournament(api: ApiClient, http: TestClient) -> Iterator[Tournament]:
    EVENT.create(json_file='tec-swiss-unpaired')
    tournament = EVENT.tournament()
    TestUtils.create_screen(
        api,
        EVENT_ID,
        SCREEN_ID,
        ScreenType.INPUT,
        {'init_set_tournament_id': tournament.id},
    )
    with EventDatabase(EVENT_ID, write=True) as event_database:
        event_database.execute("DELETE FROM `sqlite_sequence` WHERE `name` = 'board'")
        event_database.execute(
            "INSERT INTO `sqlite_sequence` (`name`, `seq`) VALUES ('board', ?)",
            (BOARDS_CREATED_BEFORE,),
        )
    http.post(f'/pairings/generate/{EVENT_ID}/{tournament.id}/1')
    http.put(f'/pairings/publish/{EVENT_ID}/{tournament.id}/1')
    yield EVENT.tournament()
    EVENT.delete()


@pytest.mark.unit
def test_each_board_of_a_display_controller_opens_its_own_result_window(
    api: ApiClient, http: TestClient, tournament: Tournament
):
    controller = TestUtils.create_display_controller(
        api, EVENT_ID, CONTROLLER_NAME, screen_uniq_id=SCREEN_ID
    )
    boards = tournament.get_round_boards(1)
    assert any(board.identifier != board.id for board in boards)
    assert any(
        board.id in {other.identifier for other in boards if other is not board}
        for board in boards
    )

    markup = http.get(f'/view/display-controller/{EVENT_ID}/{controller.id}').text
    for board in boards:
        if not board.black_tournament_player:
            continue
        row = re.search(
            rf'id="tournament-{tournament.id}-board-{board.id}-row".*?hx-get="([^"]+)"',
            markup,
            re.DOTALL,
        )
        assert row is not None, f'Board {board.id} has no result link.'
        window = http.get(row.group(1))
        assert window.status_code == 200
        assert board.white_tournament_player.last_name in window.text
        assert board.black_tournament_player.last_name in window.text
