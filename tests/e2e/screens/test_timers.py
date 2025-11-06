import pytest
from playwright.sync_api import Page, expect, APIRequestContext
from tests.test_config import TestUtils


EVENT_ID = 'event-test-timer'


@pytest.fixture(scope='module', autouse=True)
def setup(api_request_context: APIRequestContext):
    TestUtils.create_event(EVENT_ID, via_api_request_context=api_request_context)
    yield
    TestUtils.delete_event(EVENT_ID, via_api_request_context=api_request_context)


@pytest.mark.e2e
class TestTimersFunctionality:
    def test_create_and_delete_timer(self, page: Page):
        page.goto(f'/event/{EVENT_ID}/timers')
        TestUtils.button_by_text(page, 'Create a timer').click()
        modal = page.locator('.modal-dialog')
        expect(modal).to_be_visible()
        name = 'Test Timer'
        modal.get_by_test_id('name').fill(name)
        modal.locator('button[type=submit]').click()

        hours_modal = page.locator('#admin-timer-hours-modal.modal-dialog')
        expect(hours_modal).to_be_visible()
        TestUtils.button_by_text(hours_modal, 'Cancel').click()
        TestUtils.button_by_text(hours_modal, 'Close').click()

        card = page.locator(f"div.card:has-text('{name}')")
        expect(card).to_be_visible()

        button = card.locator('button[hx-get*="delete"]')
        button.click()
        TestUtils.button_by_text(modal, 'Delete').click()
        expect(page.locator(f"div.card:has-text('{name}')")).not_to_be_attached()
