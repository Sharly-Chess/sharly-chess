import pytest
from playwright.sync_api import Page, expect, APIRequestContext
from tests.test_config import TestUtils


EVENT_ID = 'tournament-test-event'
TOURNAMENT_ID = 'test-tournament'


@pytest.mark.e2e
class TestTournamentFunctionality:
    def test_create_and_delete_tournament(
        self, page: Page, api_request_context: APIRequestContext
    ):
        TestUtils.create_event(api_request_context, EVENT_ID)
        page.goto(f'/admin/event/{EVENT_ID}/tournaments')
        TestUtils.button_by_text(page, 'Create a tournament').click()
        modal = page.locator('.modal-dialog')
        expect(modal).to_be_visible()
        modal.get_by_role('textbox', name='ID (unique):').fill(TOURNAMENT_ID)
        modal.get_by_role('textbox', name='Name:').fill('Test Tournament')
        modal.get_by_role('button', name='Create', exact=True).click()

        card = page.locator("div.card:has-text('Test Tournament')")
        expect(card).to_be_visible()

        button = card.locator('button[hx-get*="delete"]')
        button.click()

        modal = page.locator('.modal-dialog')
        expect(modal).to_be_visible()
        modal.locator('#uniq-id').fill(TOURNAMENT_ID)
        TestUtils.button_by_text(modal, 'Delete').click()
        expect(
            page.get_by_text(f'Tournament [{TOURNAMENT_ID}] has been deleted.')
        ).to_be_visible()
        expect(page.locator('.card')).to_have_count(0)
