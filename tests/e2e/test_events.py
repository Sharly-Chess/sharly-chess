"""End-to-end tests for events."""

import pytest
from playwright.sync_api import Page, expect
from tests.test_config import TestUtils


@pytest.mark.e2e
class TestEventFunctionality:
    def test_create_and_delete_event(self, page: Page):
        page.goto(f'{page.base_url}/admin/config')
        TestUtils.button_by_text(page, 'Create an event').click()
        page.get_by_label('Federation:').select_option('FRA')
        page.get_by_role('textbox', name='ID (unique):').fill('test-event')
        page.get_by_role('textbox', name='Name:').fill('Test Event')
        page.locator('button[type=submit]').click()
        expect(page.locator("tr:has(th:text-is('Unique ID')) td")).to_have_text(
            'test-event'
        )

        page.goto(f'{page.base_url}/admin')
        locator = page.locator("div.card:has-text('Unique ID: test-event')")
        expect(locator).to_be_visible()

        locator.click()
        TestUtils.button_by_text(page, 'Delete').click()
        page.locator('#uniq-id').fill('test-event')
        page.locator('button[type=submit]').click()
        expect(page.get_by_text('Event [test-event] has been deleted')).to_be_visible()
