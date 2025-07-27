from database.sqlite.event.event_store import StoredScreen, StoredTournament
import pytest
from playwright.sync_api import Page, APIRequestContext
from data.auth.roles import DeputyChiefArbitrationRole
from tests.e2e.roles.base_role_test import BaseRoleTest, DisplayMode
from tests.e2e.roles.conftest import PUBLIC_EVENT_ID


@pytest.mark.e2e
class TestDeputyChiefArbitrationRole(BaseRoleTest):
    def get_roles(self):
        return [DeputyChiefArbitrationRole]

    def test_access(
        self,
        auth_page: Page,
        public_input_screen: StoredScreen,
        public_input_unpaired_screen: StoredScreen,
        private_input_screen: StoredScreen,
        role_test_unpaired_tournament: StoredTournament,
        api_request_context: APIRequestContext,
    ):
        # Admin

        super().assert_can_access_players_tab(True, PUBLIC_EVENT_ID, auth_page)
        super().assert_can_access_pairings_tab(True, PUBLIC_EVENT_ID, auth_page)

        # Screens

        super().assert_access_to_visible_events(PUBLIC_EVENT_ID, auth_page)
        super().assert_access_to_input_screen(
            True,
            DisplayMode.SCREENS_IN_SUBMENU,
            PUBLIC_EVENT_ID,
            auth_page,
            public_input_screen,
        )
        super().assert_access_to_input_screen(
            True,
            DisplayMode.SCREENS_IN_SUBMENU,
            PUBLIC_EVENT_ID,
            auth_page,
            private_input_screen,
        )
        super().assert_can_checkin_via_screen(
            True,
            PUBLIC_EVENT_ID,
            role_test_unpaired_tournament.id,
            auth_page,
            public_input_unpaired_screen,
            api_request_context,
        )
