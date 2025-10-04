import pytest
from playwright.sync_api import Page, expect, APIRequestContext
from tests.test_config import TestUtils


EVENT_ID = 'test-event-e2e'


@pytest.mark.e2e
class TestEventFunctionality:
    def test_create_and_delete_event(self, page: Page):
        page.goto('/')
        TestUtils.button_by_text(page, 'Create an event').click()
        modal = page.locator('.modal-dialog')
        expect(modal).to_be_visible()
        modal.get_by_label('Federation:').select_option('FRA')
        modal.get_by_role('textbox', name='Name:').fill(EVENT_ID)
        modal.locator('button[type=submit]').click()
        expect(page).to_have_url(f'/event/{EVENT_ID}/tournaments')

        page.goto('/current_events')
        card = page.locator(f"div.card:has-text('Unique ID: {EVENT_ID}')")
        expect(card).to_be_visible()
        button = card.locator('button[hx-get*="delete"]')
        button.click()

        modal = page.locator('.modal-dialog')
        expect(modal).to_be_visible()
        modal.locator('#archive').check()
        modal.locator('button[type=submit]').click()
        page.goto('/event/current_events')
        card = page.locator(f"div.card:has-text('Unique ID: {EVENT_ID}')")
        expect(card).not_to_be_attached()

    def test_rename_event(self, page: Page, api_request_context: APIRequestContext):
        new_uniq_id = EVENT_ID + '-2'
        TestUtils.create_event(EVENT_ID, via_api_request_context=api_request_context)
        page.goto(f'/event/{EVENT_ID}')
        page.get_by_test_id('nav-admin-event-config-tab-tab').click()
        modal = page.locator('.modal-dialog')
        expect(modal).to_be_visible()
        page.get_by_test_id('uniq-id-update-button').click()
        update_input = page.get_by_test_id('uniq-id-update-input')
        expect(update_input).to_be_visible()
        update_input.fill(new_uniq_id)
        page.get_by_test_id('uniq-id-update-submit-button').click()
        expect(page).to_have_url(f'/event/{new_uniq_id}/tournaments')
