from database.sqlite.event.event_store import StoredScreen
import pytest
from playwright.sync_api import Page, APIRequestContext
from data.access_levels.access_levels import SectorArbitrationAccessLevel
from tests.e2e.access_levels.base_access_level_test import (
    BaseAccessLevelTest,
    DisplayMode,
)
from tests.e2e.access_levels.conftest import PUBLIC_EVENT_ID


@pytest.mark.e2e
class TestSectorArbitrationAccessLevel(BaseAccessLevelTest):
    def get_access_levels(self):
        return [SectorArbitrationAccessLevel]

    def test_access(
        self,
        auth_page: Page,
        public_input_screen: StoredScreen,
        private_input_screen: StoredScreen,
        api_request_context: APIRequestContext,
    ):
        # Players tab

        super().assert_can_access_players_tab(True, auth_page)
        super().assert_can_checkin_via_players_tab(
            True,
            api_request_context,
        )

        # Pairings tab

        super().assert_can_access_pairings_tab(True, auth_page)

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
        super().assert_can_enter_results_via_screen(True, True, False)
        super().assert_can_set_illegal_moves_via_screen(True, api_request_context)
