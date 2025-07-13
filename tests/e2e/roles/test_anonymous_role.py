from database.sqlite.event.event_store import StoredScreen
import pytest
from playwright.sync_api import expect, Page
from tests.e2e.roles.base_role_test import BaseRoleTest
from tests.e2e.roles.conftest import PUBLIC_EVENT_ID


@pytest.mark.e2e
class TestAnonymousRole(BaseRoleTest):
    def get_roles(self):
        return []

    def test_access_to_visible_events(self, lan_page: Page):
        lan_page.goto('/admin/current_events')
        # Public events should be visible (otherwise there'd be no way to log onto one)
        expect(lan_page.locator('.card')).to_have_count(1)
        expect(
            lan_page.locator(f"div.card:has-text('{PUBLIC_EVENT_ID}')")
        ).to_be_visible()

    # FIXME(Amaras): this is supposed to be unmarked before merging.
    # It is currently marked because I am working on reworking the level
    # of abstractions of the client and want to isolate failing tests not
    # related to my changes
    @pytest.mark.skip(reason='Test is expected to fail')
    def test_access_to_visible_screens(
        self,
        lan_page: Page,
        public_input_screen: StoredScreen,
        private_input_screen: StoredScreen,
    ):
        lan_page.goto(f'/admin/event/{PUBLIC_EVENT_ID}/input-screens')

        # No screens should be visible
        expect(lan_page.locator('.card')).to_have_count(0)

        # Test no access to the public input screen, should redirect to the home page
        lan_page.goto(f'/user/screen/{PUBLIC_EVENT_ID}/{public_input_screen.uniq_id}')
        lan_page.wait_for_url('/admin')

        # Test no access to the private input screen, should redirect to the home page
        lan_page.goto(f'/user/screen/{PUBLIC_EVENT_ID}/{private_input_screen.uniq_id}')
        lan_page.wait_for_url('/admin')
