import pytest
from playwright.sync_api import Page, expect
from tests.test_config import TestUtils


@pytest.mark.e2e
class TestEventFunctionality:
    def test_create_and_delete_event(self, page: Page):
        page.goto('/admin/config')
        TestUtils.button_by_text(page, 'Create an event').click()
        modal = page.locator('.modal-dialog')
        expect(modal).to_be_visible()
        modal.get_by_label('Federation:').select_option('FRA')
        modal.get_by_role('textbox', name='ID (unique):').fill('test-event-e2e')
        modal.get_by_role('textbox', name='Name:').fill('Test Event')
        modal.locator('button[type=submit]').click()
        expect(page.locator("tr:has(th:text-is('Unique ID')) td")).to_have_text(
            'test-event-e2e'
        )

        page.goto('/admin/current_events')
        card = page.locator("div.card:has-text('Unique ID: test-event-e2e')")
        expect(card).to_be_visible()
        card.click()
        TestUtils.button_by_text(page, 'Delete').click()

        modal = page.locator('.modal-dialog')
        expect(modal).to_be_visible()
        modal.locator('#uniq-id').fill('test-event-e2e')
        modal.locator('button[type=submit]').click()
        expect(
            page.get_by_text('Event [test-event-e2e] has been deleted')
        ).to_be_visible()
