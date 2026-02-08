import pytest
from playwright.sync_api import APIRequestContext, expect, Page, BrowserContext

from database.sqlite.event.event_store import StoredTournament
from tests.test_config import TestUtils

EVENT_ID = 'event-test-crosstable-document'
TOURNAMENT_ID = 'tournament-test-document'


@pytest.fixture(scope='module', autouse=True)
def setup(api_request_context: APIRequestContext):
    TestUtils.create_event(EVENT_ID, via_api_request_context=api_request_context)
    yield
    TestUtils.delete_event(EVENT_ID, via_api_request_context=api_request_context)


@pytest.fixture(scope='module', autouse=True)
def tournament(api_request_context: APIRequestContext):
    tournament = TestUtils.create_tournament(
        EVENT_ID,
        TOURNAMENT_ID,
        json_file='tec-swiss',
        via_api_request_context=api_request_context,
    )
    yield tournament
    TestUtils.delete_tournament(api_request_context, EVENT_ID, tournament)


TEST_PLAYER_NAME = 'ALYX'


@pytest.mark.e2e
class TestCrosstableDocument:
    def test_generate_crosstable_document_without_player_history_option(
        self, page: Page, context: BrowserContext, tournament: StoredTournament
    ):
        page.goto(f'/event/{EVENT_ID}/')
        page.locator('#print-button').click()

        self.select_document_type(page, 'Crosstable')

        with context.expect_page() as new_page_info:
            TestUtils.button_by_text(page, 'Generate').click()
        crosstable_document_page = new_page_info.value

        crosstable_document_page.get_by_text(TEST_PLAYER_NAME).filter(
            visible=True
        ).hover()

        expect(
            crosstable_document_page.locator('.player-history table').filter(
                visible=True
            )
        ).to_have_count(0)

    def test_generate_crosstable_document_with_player_history_option(
        self, page: Page, context: BrowserContext, tournament: StoredTournament
    ):
        page.goto(f'/event/{EVENT_ID}/')
        page.locator('#print-button').click()

        self.select_document_type(page, 'Crosstable')

        page.get_by_test_id('player-history').click()

        with context.expect_page() as new_page_info:
            TestUtils.button_by_text(page, 'Generate').click()
        crosstable_document_page = new_page_info.value

        crosstable_document_page.get_by_text(TEST_PLAYER_NAME).filter(
            visible=True
        ).hover()

        expect(
            crosstable_document_page.locator('.player-history table').filter(
                visible=True
            )
        ).not_to_be_empty()

    @staticmethod
    def select_document_type(page: Page, document_type: str):
        page.locator('#document-input-container').click()
        document_name_input = page.locator('#modal-wrapper input[type=search]').filter(
            visible=True
        )
        document_name_input.fill(document_type)
        document_name_input.press('Enter')
