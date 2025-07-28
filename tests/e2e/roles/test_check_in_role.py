from database.sqlite.event.event_store import StoredScreen
import pytest
from playwright.sync_api import Page, APIRequestContext
from data.auth.roles import CheckInRole
from tests.e2e.roles.base_role_test import BaseRoleTest, DisplayMode
from tests.e2e.roles.conftest import PUBLIC_EVENT_ID


@pytest.mark.e2e
class TestCheckInRole(BaseRoleTest):
    def get_roles(self):
        return [CheckInRole]

    def test_access(
        self,
        auth_page: Page,
        public_input_screen: StoredScreen,
        private_input_screen: StoredScreen,
        api_request_context: APIRequestContext,
    ):
        # Admin tabs

        super().assert_can_access_players_tab(False, auth_page)
        super().assert_can_access_pairings_tab(False, auth_page)

        # Screens

        super().assert_access_to_visible_events(PUBLIC_EVENT_ID, auth_page)
        super().assert_access_to_input_screen(
            True,
            DisplayMode.SCREENS_IN_MENU,
            auth_page,
            public_input_screen,
        )
        super().assert_access_to_input_screen(
            False,
            DisplayMode.SCREENS_IN_MENU,
            auth_page,
            private_input_screen,
        )
        super().assert_can_checkin_via_screen(True, api_request_context)
        super().assert_can_enter_results_via_screen(False, False, False)
