from typing import Iterator

import pytest
from litestar.middleware.session.server_side import ServerSideSessionConfig
from litestar.status_codes import HTTP_200_OK
from litestar.testing import TestClient
from requests import Response

from data.account import Account
from data.event import Event
from data.loader import EventLoader
from data.tournament import Tournament
from tests.test_config import TestUtils

session_config = ServerSideSessionConfig()

EVENT_ID = 'test-event-documents-event'
TOURNAMENT_NAME = 'test-event-documents-tournament'


@pytest.fixture(scope='function')
def event() -> Iterator[Event]:
    TestUtils.create_event(EVENT_ID)
    TestUtils.create_tournament(EVENT_ID, TOURNAMENT_NAME, json_file='tec-swiss')
    yield EventLoader().load_event(EVENT_ID)
    TestUtils.delete_event(EVENT_ID)


@pytest.fixture(scope='function')
def tournament(event: Event) -> Iterator[Tournament]:
    yield event.tournaments_by_name[TOURNAMENT_NAME]


@pytest.fixture(scope='function', autouse=True)
def account(
    event: Event, tournament: Tournament, test_client: TestClient
) -> Iterator[Account]:
    user_account = TestUtils.create_account(event.uniq_id, 'admin', overrides={'id': 3})
    TestUtils.create_permission(
        event.uniq_id, tournament.id, user_account.id, 'ADMINISTRATION'
    )
    test_client.set_session_data({'account_id': {EVENT_ID: user_account.id}})
    yield user_account


PLAYER_HISTORY_HTML_PATTERN = 'class="player-history"'


@pytest.mark.integration
class TestEventDocumentsController:
    def test_crosstable_document_view_includes_player_histories_when_option_is_on(
        self, test_client: TestClient, tournament: Tournament
    ):
        html_response: Response = test_client.get(
            f'/document-view/{EVENT_ID}/crosstable?options=player-history-popover%3Don'
        )

        assert html_response.status_code == HTTP_200_OK
        assert html_response.text.count(PLAYER_HISTORY_HTML_PATTERN) == len(
            tournament.tournament_players
        )

    def test_crosstable_document_view_does_not_include_player_histories_when_option_is_absent(
        self, test_client: TestClient, tournament: Tournament
    ):
        html_response: Response = test_client.get(
            f'/document-view/{EVENT_ID}/crosstable'
        )

        assert html_response.status_code == HTTP_200_OK
        assert PLAYER_HISTORY_HTML_PATTERN not in html_response.text
