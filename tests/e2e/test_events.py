import pytest
from playwright.sync_api import Page, expect, APIRequestContext
from tests.test_config import TestUtils


EVENT_ID = 'test-event-e2e'


@pytest.mark.e2e
class TestEventFunctionality:
    def test_create_and_delete_event(self, page: Page):
        page.goto('/admin/config')
        TestUtils.button_by_text(page, 'Create an event').click()
        modal = page.locator('.modal-dialog')
        expect(modal).to_be_visible()
        modal.get_by_label('Federation:').select_option('FRA')
        modal.get_by_role('textbox', name='Name:').fill(EVENT_ID)
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
        modal.locator('#uniq-id').fill(EVENT_ID)
        modal.locator('button[type=submit]').click()
        expect(page.get_by_text(f'Event [{EVENT_ID}] has been deleted')).to_be_visible()

    def test_rename_event(self, page: Page, api_request_context: APIRequestContext):
        new_uniq_id = EVENT_ID + '-2'
        TestUtils.create_event(EVENT_ID, via_api_request_context=api_request_context)
        page.goto(f'/admin/event/{EVENT_ID}/config')
        page.get_by_test_id('uniq-id-update-button').click()
        page.get_by_test_id('uniq-id-update-input').fill(new_uniq_id)
        page.get_by_test_id('uniq-id-update-submit-button').click()
        expect(page.locator("tr:has(th:text-is('Unique ID')) td")).to_have_text(
            new_uniq_id
        )
