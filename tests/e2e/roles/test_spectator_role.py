from database.sqlite.event.event_store import StoredScreen
import pytest
from playwright.sync_api import expect, Page
from data.auth.roles import SpectatorRole
from tests.e2e.roles.base_role_test import BaseRoleTest
from tests.e2e.roles.conftest import PUBLIC_EVENT_ID


@pytest.mark.e2e
class TestSpectatorRole(BaseRoleTest):
    def get_roles(self):
        return [SpectatorRole]

    def test_access_to_visible_events(self, auth_page):
        self.auth_page.goto('/admin/current_events')
        expect(auth_page.locator('.card')).to_have_count(1)
        expect(
            auth_page.locator(f"div.card:has-text('{PUBLIC_EVENT_ID}')")
        ).to_be_visible()

    def test_access_to_visible_screens(
        self,
        auth_page: Page,
        public_input_screen: StoredScreen,
        private_input_screen: StoredScreen,
    ):
        self.auth_page.goto(f'/admin/event/{PUBLIC_EVENT_ID}/input-screens')

        # Only the public input screen should be visible
        expect(auth_page.locator('.card')).to_have_count(1)
        expect(
            auth_page.locator(f"div.card:has-text('{public_input_screen.name}')")
        ).to_be_visible()

        # Test access to the public input screen
        auth_page.goto(f'/user/screen/{PUBLIC_EVENT_ID}/{public_input_screen.uniq_id}')
        rows = auth_page.locator('table tbody tr')
        expect(rows).to_have_count(8)

        # We should NOT see the modal
        row = rows.filter(has_text='ALYX')
        row.click()
        modal = auth_page.locator('.modal-dialog')
        auth_page.wait_for_timeout(200)
        expect(modal).not_to_be_visible()

        # Test no access to the private input screen, should redirect to the home page
        auth_page.goto(f'/user/screen/{PUBLIC_EVENT_ID}/{private_input_screen.uniq_id}')
        auth_page.wait_for_url('/admin')
