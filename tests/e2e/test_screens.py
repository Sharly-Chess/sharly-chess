import pytest
from playwright.sync_api import Page, expect
from tests.test_config import TestUtils


@pytest.fixture(scope='module', autouse=True)
def setup():
    TestUtils.create_event('event-test-screen')
    TestUtils.create_tournament('event-test-screen', 'tournament-test-screen')
    yield

    TestUtils.delete_event('event-test-screen')


@pytest.mark.e2e
class TestScreensFunctionality:
    def test_create_and_delete_simple_screen(self, page: Page):
        page.goto('/admin/event/event-test-screen/screens')
        TestUtils.button_by_text(page, 'Create a screen').click()
        page.get_by_test_id('create-screen-type-input').click()
        modal = page.locator('.modal-dialog')
        expect(modal).to_be_visible()
        modal.get_by_role('textbox', name='ID (unique):').fill('test-screen')
        modal.get_by_role('textbox', name='Name:').fill('Test Screen')
        modal.locator('button[type=submit]').click()
        page.get_by_test_id('accordion-screen-type-input').click()

        card = page.locator("div.card:has-text('Test Screen')")
        expect(card).to_be_visible()

        button = card.locator('button[hx-get*="delete"]')
        button.click()
        TestUtils.button_by_text(modal, 'Delete').click()

        expect(
            page.get_by_text('Screen [test-screen] has been deleted.')
        ).to_be_visible()
        expect(page.locator('.card')).to_have_count(0)
