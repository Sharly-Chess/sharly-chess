import pytest
from playwright.sync_api import Page, expect, APIRequestContext

from database.sqlite.event.event_database import EventDatabase
from tests.test_config import TestUtils


EVENT_ID = 'test-event-e2e'
RENAMED_EVENT_ID = EVENT_ID + '-2'


@pytest.fixture(scope='module', autouse=True)
def setup(api_request_context: APIRequestContext):
    yield

    # The tests create, delete and rename the event themselves, so which of
    # the two ids is left behind depends on how far each one got.
    for uniq_id in (EVENT_ID, RENAMED_EVENT_ID):
        if EventDatabase(uniq_id).file.exists():
            TestUtils.delete_event(uniq_id, via_api_request_context=api_request_context)


@pytest.mark.e2e
class TestEventFunctionality:
    def test_sce_oauth_callback_accepts_standard_query_parameter_names(
        self, api_request_context: APIRequestContext
    ):
        response = api_request_context.get(
            '/sce/oauth/callback/import-event',
            params={
                'code': 'test-code',
                'state': 'unknown-state',
                'event_id': 'test-event-id',
            },
            max_redirects=0,
        )

        assert response.status == 302
        assert response.headers['location'] == '/'

    def test_create_and_delete_event(self, page: Page):
        page.goto('/')
        # The home page shows the main button plus a sidebar quick-create "+"
        # (same accessible name); either opens the create-event modal.
        TestUtils.button_by_text(page, 'Create an event').first.click()
        modal = page.locator('.modal-dialog')
        expect(modal).to_be_visible()
        modal.get_by_test_id('federation').select_option('FRA', force=True)
        TestUtils.fill_and_confirm(modal.get_by_test_id('name'), EVENT_ID)
        TestUtils.submit_modal(page, modal.get_by_test_id('event-form-submit-button'))
        expect(page).to_have_url(f'/event/{EVENT_ID}/tournaments')

        page.goto('/current_events')
        item = page.get_by_test_id('events-item').filter(has_text=EVENT_ID)
        expect(item).to_be_visible()
        button = item.locator('button[hx-get*="delete"]')
        button.click()

        modal = page.locator('.modal-dialog')
        expect(modal).to_be_visible()
        modal.locator('#archive').check()
        TestUtils.submit_modal(page, modal.locator('button[type=submit]'))
        page.goto('/event/current_events')
        item = page.get_by_test_id('events-item').filter(has_text=EVENT_ID)
        expect(item).not_to_be_attached()

    def test_rename_event(self, page: Page, api_request_context: APIRequestContext):
        new_uniq_id = RENAMED_EVENT_ID
        TestUtils.create_event(EVENT_ID, via_api_request_context=api_request_context)
        page.goto(f'/event/{EVENT_ID}')
        page.get_by_test_id('nav-admin-event-config-tab-tab').click()
        modal = page.locator('.modal-dialog')
        expect(modal).to_be_visible()
        page.get_by_test_id('uniq-id-update-button').click()
        update_input = page.get_by_test_id('uniq-id-update-input')
        expect(update_input).to_be_visible()
        TestUtils.fill_and_confirm(update_input, new_uniq_id)
        TestUtils.submit_modal(
            page,
            page.get_by_test_id('uniq-id-update-submit-button'),
            '#uniq-id-update-form',
        )
        expect(page).to_have_url(f'/event/{new_uniq_id}/tournaments')
