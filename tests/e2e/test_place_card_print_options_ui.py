import pytest
from playwright.sync_api import Page, expect, APIRequestContext
from tests.test_config import TestUtils


EVENT_ID = 'test-place-card-print-options-e2e'


@pytest.fixture(scope='module', autouse=True)
def setup(api_request_context: APIRequestContext):
    TestUtils.create_event(EVENT_ID, via_api_request_context=api_request_context)
    TestUtils.create_tournament(
        EVENT_ID, 'Open A', via_api_request_context=api_request_context
    )
    TestUtils.create_tournament(
        EVENT_ID, 'Open B', via_api_request_context=api_request_context
    )

    yield

    TestUtils.delete_event(EVENT_ID, via_api_request_context=api_request_context)


@pytest.mark.e2e
class TestPlaceCardPrintOptions:
    @staticmethod
    def _open_documents_modal(page: Page):
        page.goto(f'/event/{EVENT_ID}')
        TestUtils.wait_for_htmx_bound(page, '#print-button button')
        page.locator('#print-button button').click()
        expect(page.locator('.print-modal #document')).to_be_attached()
        TestUtils.wait_for_htmx_idle(page)

    def test_player_cards_hide_round_and_board_options(self, page: Page):
        self._open_documents_modal(page)
        round_container = page.locator('#round_container')
        boards_container = page.locator('#place-card-board-numbers_container')
        players_container = page.locator('#optional-players_container')
        tournament = page.locator('#tournament')
        tournament_ids = [
            value
            for value in tournament.locator('option').evaluate_all(
                'options => options.map(option => option.value)'
            )
            if value
        ]

        TestUtils.select_and_confirm(page.locator('#document'), 'place-card')
        expect(page.locator('#place-card-type')).to_have_value('player')
        expect(players_container).to_be_visible()
        expect(round_container).to_be_hidden()
        expect(boards_container).to_be_hidden()

        TestUtils.select_and_confirm(tournament, tournament_ids[1])
        expect(players_container).to_be_visible()
        expect(round_container).to_be_hidden()
        expect(boards_container).to_be_hidden()

        TestUtils.select_and_confirm(page.locator('#place-card-type'), 'pairing')
        expect(round_container).to_be_visible()
        expect(boards_container).to_be_visible()
        expect(players_container).to_be_hidden()

        TestUtils.select_and_confirm(tournament, tournament_ids[0])
        expect(round_container).to_be_visible()
        expect(boards_container).to_be_visible()
        expect(players_container).to_be_hidden()
