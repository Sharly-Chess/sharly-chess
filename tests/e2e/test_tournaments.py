"""End-to-end tests for events."""

import pytest
from playwright.sync_api import Page, expect
from tests.test_config import TestUtils


@pytest.mark.e2e
class TestTournamentFunctionality:
    def test_create_and_delete_tournament(self, page: Page):
        TestUtils.create_event('tournament-test-event')
        page.goto(f'{page.base_url}/admin/event/tournament-test-event/tournaments')
        TestUtils.button_by_text(page, 'Create a tournament').click()
        page.get_by_role('textbox', name='ID (unique):').fill('test-tournament')
        page.get_by_role('textbox', name='Name:').fill('Test Tournament')
        page.get_by_role('button', name='Create', exact=True).click()
        locator = page.locator("div.card:has-text('Test Tournament')")
        expect(locator).to_be_visible()

        button = page.locator('button[hx-get*="delete"]')
        button.click()

        page.locator('#uniq-id').fill('test-tournament')
        TestUtils.button_by_text(page, 'Delete').click()
        expect(
            page.get_by_text('Tournament [test-tournament] has been deleted.')
        ).to_be_visible()
        expect(page.locator('.card')).to_have_count(0)
