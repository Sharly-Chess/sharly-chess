from database.sqlite.event.event_store import StoredScreen
import pytest
from playwright.sync_api import Page
from tests.e2e.roles.base_role_test import BaseRoleTest, DisplayMode
from tests.e2e.roles.conftest import PUBLIC_EVENT_ID


@pytest.mark.e2e
class TestAnonymousRole(BaseRoleTest):
    def get_roles(self):
        return []

    def test_access(
        self,
        lan_page: Page,
        public_input_screen: StoredScreen,
        private_input_screen: StoredScreen,
    ):
        # Admin tabs

        super().assert_can_access_players_tab(False, lan_page)
        super().assert_can_access_pairings_tab(False, lan_page)

        # Screens

        super().assert_access_to_visible_events(PUBLIC_EVENT_ID, lan_page)
        super().assert_access_to_input_screen(
            False,
            DisplayMode.SCREENS_NOT_IN_MENU,
            lan_page,
            public_input_screen,
        )
        super().assert_access_to_input_screen(
            False,
            DisplayMode.SCREENS_NOT_IN_MENU,
            lan_page,
            private_input_screen,
        )
