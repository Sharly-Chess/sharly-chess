import pytest
from playwright.sync_api import expect
from data.auth.roles import DeputyChiefArbitrationRole
from tests.e2e.roles.base_role_test import BaseRoleTest
from tests.e2e.roles.conftest import PUBLIC_EVENT_ID


@pytest.mark.e2e
class TestDeputyChiefArbitrationRole(BaseRoleTest):
    def get_roles(self):
        return [DeputyChiefArbitrationRole]

    def test_access_to_visible_events(self, auth_page):
        self.auth_page.goto('/admin/current_events')
        expect(auth_page.locator('.card')).to_have_count(1)
        expect(
            auth_page.locator(f"div.card:has-text('{PUBLIC_EVENT_ID}')")
        ).to_be_visible()
