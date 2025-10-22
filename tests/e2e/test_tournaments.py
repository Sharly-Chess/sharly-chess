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
        TestUtils.create_event(EVENT_ID, via_api_request_context=api_request_context)
        page.goto(f'/event/{EVENT_ID}/tournaments')
        TestUtils.button_by_text(page, 'Create a tournament').click()
        modal = page.locator('.modal-dialog')
        expect(modal).to_be_visible()
        name = 'Test Tournament'
        modal.get_by_role('textbox', name='Name:').fill(name)
        modal.get_by_role('button', name='Create', exact=True).click()

        # Redirection to Tie-breaks
        success_alert = modal.locator(f"div.alert:has-text('{name}')")
        expect(success_alert).to_be_visible()
        TestUtils.button_by_text(modal, 'Use the recommended tie-breaks').click()
        expect(modal.locator('.tie-break-row')).to_have_count(5)
        TestUtils.button_by_text(modal, 'Close').click()

        card = page.locator(f"div.card:has-text('{name}')")
        expect(card).to_be_visible()

        button = card.locator('button[hx-get*="delete"]')
        button.click()

        modal = page.locator('.modal-dialog')
        expect(modal).to_be_visible()
        modal.locator('#confirm-checkbox').click()
        delete_button = TestUtils.button_by_text(modal, 'Delete')
        expect(delete_button).to_be_enabled()
        delete_button.click()
        expect(
            page.get_by_text(f'Tournament [{name}] has been deleted.')
        ).to_be_visible()
        expect(page.locator('.card')).to_have_count(0)
