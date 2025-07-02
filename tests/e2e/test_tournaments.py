"""End-to-end tests for events."""

import pytest
from playwright.sync_api import Page, expect
from tests.test_config import TestUtils


@pytest.mark.e2e
class TestTournamentFunctionality:
    def test_create_and_delete_tournament(self, page: Page):
        TestUtils.create_event('tournament-test-event')
        page.goto('/admin/event/tournament-test-event/tournaments')
        TestUtils.button_by_text(page, 'Create a tournament').click()
        modal = page.locator('.modal-dialog')
        expect(modal).to_be_visible()
        modal.get_by_role('textbox', name='ID (unique):').fill('test-tournament')
        modal.get_by_role('textbox', name='Name:').fill('Test Tournament')
        modal.get_by_role('button', name='Create', exact=True).click()

        card = page.locator("div.card:has-text('Test Tournament')")
        expect(card).to_be_visible()

        button = card.locator('button[hx-get*="delete"]')
        button.click()

        modal = page.locator('.modal-dialog')
        expect(modal).to_be_visible()
        modal.locator('#uniq-id').fill('test-tournament')
        TestUtils.button_by_text(modal, 'Delete').click()
        expect(
            page.get_by_text('Tournament [test-tournament] has been deleted.')
        ).to_be_visible()
        expect(page.locator('.card')).to_have_count(0)
