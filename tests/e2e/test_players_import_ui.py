import html

import pytest
from playwright.sync_api import APIRequestContext
from tests.test_config import TestUtils


EVENT_ID = 'test-players-import-e2e'
TOURNAMENT_NAME = 'started-tournament'
CSV_CONTENT = 'last_name,first_name\nDOE,John\n'
FORBIDDEN_MESSAGE = "Players can't be overwritten once the tournament has started."


@pytest.fixture(scope='module', autouse=True)
def setup(api_request_context: APIRequestContext):
    TestUtils.create_event(EVENT_ID, via_api_request_context=api_request_context)
    yield
    TestUtils.delete_event(EVENT_ID, via_api_request_context=api_request_context)


@pytest.mark.e2e
class TestPlayersImportOverwrite:
    @pytest.fixture(scope='class')
    def started_tournament(self, api_request_context: APIRequestContext):
        tournament = TestUtils.create_tournament(
            EVENT_ID,
            TOURNAMENT_NAME,
            json_file='test-screens',
            via_api_request_context=api_request_context,
        )
        yield tournament
        TestUtils.delete_tournament(api_request_context, EVENT_ID, tournament)

    def test_diff_modal_rejects_overwrite_of_started_tournament(
        self, api_request_context: APIRequestContext, started_tournament
    ):
        """Asking to overwrite the players of a started tournament brings the
        import form back with the error on the overwrite switch."""
        response = api_request_context.post(
            f'/players-import-diff-modal/{EVENT_ID}',
            multipart={
                'tournament_id': str(started_tournament.id),
                'overwrite_players': 'on',
                'file': {
                    'name': 'players.csv',
                    'mimeType': 'text/csv',
                    'buffer': CSV_CONTENT.encode(),
                },
            },
        )
        assert response.ok
        body = html.unescape(response.body().decode('utf-8'))
        assert 'overwrite_players' in body
        assert FORBIDDEN_MESSAGE in body
        assert 'row-index-checkbox' not in body

    def test_import_rejects_overwrite_of_started_tournament(
        self, api_request_context: APIRequestContext, started_tournament, tmp_path
    ):
        """A stale confirmation still asking to overwrite a started tournament
        gets an error message, not a request failure."""
        csv_file = tmp_path / 'players.csv'
        csv_file.write_text(CSV_CONTENT)
        response = api_request_context.post(
            f'/import-players/{EVENT_ID}/{started_tournament.id}',
            headers={'Content-Type': 'application/x-www-form-urlencoded'},
            data=TestUtils.prepare_form_data(
                {
                    'file_path': str(csv_file),
                    'overwrite_players': True,
                    'row_indexes': [0],
                }
            ),
        )
        assert response.ok
        assert FORBIDDEN_MESSAGE in html.unescape(response.body().decode('utf-8'))
