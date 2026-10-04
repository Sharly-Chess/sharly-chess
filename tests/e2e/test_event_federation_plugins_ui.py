import pytest
from playwright.sync_api import Page, expect


def _set_federation(page: Page, federation: str) -> None:
    page.evaluate(
        "federation => $('#federation').val(federation).trigger('change')",
        federation,
    )


@pytest.mark.e2e
class TestEventFederationPlugins:
    def test_a_federation_plugin_follows_the_federation_chosen(self, page: Page):
        """The plugins of a federation are only offered while the event is
        of that federation."""
        page.goto('/')
        page.get_by_role('button', name='Create an event').first.click()
        # The change handlers are bound once the swapped-in modal has run
        # its scripts; a change fired before would be lost.
        page.wait_for_function(
            "() => window.jQuery && $('#federation').length"
            " && ($._data($('#federation')[0], 'events') || {}).change"
        )
        ffe = page.locator('#plugin_ffe-plugin-container')

        _set_federation(page, 'FRA')
        expect(ffe).to_be_visible()
        expect(page.locator('#rating-preference')).to_be_disabled()

        _set_federation(page, 'ENG')
        expect(ffe).to_be_hidden()
        expect(page.locator('#rating-preference')).to_be_enabled()
