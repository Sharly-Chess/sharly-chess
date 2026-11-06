import re
from collections.abc import Iterator

import pytest
from playwright.sync_api import BrowserContext, Locator, Page, expect

PLUGIN_ID = 'custom_upload'
ACTIVE = re.compile(r'\bactive\b')


def _item(page: Page) -> Locator:
    return page.get_by_test_id(f'plugin-list-item-{PLUGIN_ID}')


def _wait_for_websocket(page: Page) -> None:
    page.wait_for_function(
        "() => document.querySelector('[ws-connect]')"
        "?.['htmx-internal-data']?.webSocket?.socket?.readyState === 1"
    )


def _toggle(page: Page) -> None:
    _item(page).click()
    page.locator(
        f'[data-testid="plugin-install-{PLUGIN_ID}"],'
        f'[data-testid="plugin-uninstall-{PLUGIN_ID}"]'
    ).click()


@pytest.fixture
def other_window(context: BrowserContext) -> Iterator[Page]:
    other_page = context.new_page()
    other_page.goto('/plugins')
    yield other_page
    other_page.close()


@pytest.mark.e2e
class TestPluginsLiveUpdates:
    @pytest.mark.parametrize('url', ['/plugins', '/plugins?embedded=1'])
    def test_the_list_follows_a_change_made_in_another_window(
        self, page: Page, other_window: Page, url: str
    ):
        """A plugin enabled or disabled elsewhere is displayed as such without
        reloading the page, which keeps the plugin selected and the search."""
        page.goto(url)
        _wait_for_websocket(page)
        page.locator('#plugin-search-input').fill('upload')
        _item(page).click()
        expect(_item(page)).to_have_class(ACTIVE)
        mark = _item(page).locator('.bi-check-circle-fill')
        was_enabled = mark.count() == 1

        _toggle(other_window)
        expect(mark).to_have_count(0 if was_enabled else 1)
        expect(_item(page)).to_have_class(ACTIVE)
        expect(page.locator('#plugin-search-input')).to_have_value('upload')

        _toggle(other_window)
        expect(mark).to_have_count(1 if was_enabled else 0)

    def test_a_local_admin_page_follows_the_theme_of_the_application(self, page: Page):
        page.goto('/home')
        page.evaluate(
            """() => document.body.dispatchEvent(new CustomEvent(
                'ws:admin-theme-updated', {detail: {theme: 'light'}}
            ))"""
        )
        expect(page.locator('body')).to_have_attribute('data-bs-theme', 'light')
        page.evaluate(
            """() => document.body.dispatchEvent(new CustomEvent(
                'ws:admin-theme-updated', {detail: {theme: 'dark'}}
            ))"""
        )
        expect(page.locator('body')).to_have_attribute('data-bs-theme', 'dark')

    def test_the_page_of_the_application_window_keeps_its_own_theme(self, page: Page):
        page.goto('/plugins?embedded=1')
        page.evaluate(
            """() => document.body.dispatchEvent(new CustomEvent(
                'ws:admin-theme-updated', {detail: {theme: 'dark'}}
            ))"""
        )
        expect(page.locator('body')).to_have_attribute('data-bs-theme', 'light')
