import pytest
from playwright.sync_api import APIRequestContext, Page, expect

from tests.test_config import TestUtils

EVENT_ID = 'test-event-federation-plugins-e2e'


@pytest.fixture(scope='module')
def ffe_event(api_request_context: APIRequestContext):
    TestUtils.create_event(EVENT_ID, via_api_request_context=api_request_context)
    yield EVENT_ID
    TestUtils.delete_event(EVENT_ID, via_api_request_context=api_request_context)


def _wait_for_federation_handler(page: Page) -> None:
    # The change handlers are bound once the swapped-in modal has run
    # its scripts; a change fired before would be lost.
    page.wait_for_function(
        "() => window.jQuery && $('#federation').length"
        " && ($._data($('#federation')[0], 'events') || {}).change"
    )


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
        _wait_for_federation_handler(page)
        ffe = page.locator('#plugin_ffe-plugin-container')

        _set_federation(page, 'FRA')
        expect(ffe).to_be_visible()
        expect(page.locator('#rating-preference')).to_be_disabled()

        _set_federation(page, 'ENG')
        expect(ffe).to_be_hidden()
        expect(page.locator('#rating-preference')).to_be_enabled()

    def test_a_field_the_federation_set_is_sent_once_when_the_federation_changes(
        self, page: Page, ffe_event: str
    ):
        """The rating of unrated players that the FFE prescribes becomes the
        event's own once the event leaves the federation, and the form sends
        it once."""
        page.goto(f'/event/{ffe_event}')
        page.get_by_test_id('nav-admin-event-config-tab-tab').click()
        expect(page.locator('#unrated-rating')).to_be_disabled()
        _wait_for_federation_handler(page)

        _set_federation(page, 'ENG')
        expect(page.locator('#unrated-rating')).to_be_enabled()
        assert (
            page.evaluate(
                "new FormData(document.getElementById('modal-form'))"
                ".getAll('unrated_rating').length"
            )
            == 1
        )
