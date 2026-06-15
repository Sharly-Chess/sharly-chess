from enum import IntEnum
import re

from data.event import Event
from database.sqlite.event.event_store import StoredScreen
import pytest
from playwright.sync_api import Browser, Page, expect, APIRequestContext
from database.sqlite.event.event_database import EventDatabase
from data.access_levels.access_levels import AccessLevel
from common.sharly_chess_config import SharlyChessConfig
from tests.e2e.access_levels.conftest import (
    PUBLIC_EVENT_ID,
    TOURNAMENT_ID,
    TOURNAMENT_UNPAIRED_ID,
)
from tests.test_config import TestUtils
from utils.enum import ScreenType


class DisplayMode(IntEnum):
    SCREENS_IN_MENU = 0
    SCREENS_IN_SUBMENU = 1
    SCREENS_NOT_IN_MENU = 2


class BaseAccessLevelTest:
    @pytest.fixture(scope='class', autouse=True)
    def auth_page(
        self,
        api_request_context: APIRequestContext,
        request,
        browser: Browser,
    ):
        """A fixture that logs in the user and returns the authenticated page"""
        cls = request.cls  # the actual test class instance

        if not cls.get_access_levels(cls) and not cls.get_tournament_ids(cls):
            # Don't logon for anonymous tests
            yield None
            return

        stored_account = self.create_user(
            api_request_context, self.get_access_levels(), self.get_tournament_ids()
        )

        config = SharlyChessConfig()
        config.web_port = 9000
        auth_context = browser.new_context(
            base_url=config.lan_urls[0],
            viewport={'width': 1600, 'height': 1000},
        )
        auth_page = auth_context.new_page()
        auth_page.set_default_timeout(15000)
        auth_page.set_default_navigation_timeout(10000)

        auth_page.goto(f'/event/{PUBLIC_EVENT_ID}')
        auth_page.wait_for_load_state('domcontentloaded')
        auth_page.get_by_test_id('profile-button').click()
        auth_page.locator('#password').fill('test-password')

        auth_page.locator('#modal-form button[type=submit]').click()

        expect(
            auth_page.get_by_text(
                f'Account: {stored_account.first_name} {stored_account.last_name}'
            )
        ).to_be_visible()

        cls.auth_context = auth_context
        cls.auth_page = auth_page
        cls.api_request_context = api_request_context

        yield cls.auth_page

        cls.auth_page.close()
        cls.auth_context.close()
        self.delete_user(api_request_context, stored_account.id)

    def create_user(
        self,
        api_request_context: APIRequestContext,
        access_levels: list[type[AccessLevel]],
        tournament_ids: list[int] | None = None,
    ):
        """Creates a user with the specified access levels and tournaments"""
        first_name = 'test'
        last_name = self.__class__.__name__.upper()
        data = {
            'first_name': first_name,
            'last_name': last_name,
            'password': 'test-password',
            'active': True,
        }

        form_data = TestUtils.prepare_form_data(data)

        res = api_request_context.post(
            f'/account-create/{PUBLIC_EVENT_ID}',
            headers={'Content-Type': 'application/x-www-form-urlencoded'},
            data=form_data,
        )
        TestUtils.check_api_response(res)
        with EventDatabase(PUBLIC_EVENT_ID) as event_database:
            stored_accounts = event_database.load_stored_accounts()
            stored_account = next(
                a
                for a in stored_accounts
                if a.first_name == first_name and a.last_name == last_name
            )
        # For the tests, delete all existing permissions of the new account
        # (new accounts inherit the anonymous account's permissions)
        with EventDatabase(PUBLIC_EVENT_ID, write=True) as event_database:
            for stored_permission in stored_account.stored_permissions:
                event_database.delete_stored_permission(stored_permission)
            stored_account.stored_permissions = []
        for access_level in access_levels:
            form_data = TestUtils.prepare_form_data(
                {
                    'access_level': access_level.static_id(),
                    'tournament_ids': tournament_ids,
                }
            )
            res = api_request_context.post(
                f'/account-permission-create/{PUBLIC_EVENT_ID}/{stored_account.id}',
                headers={'Content-Type': 'application/x-www-form-urlencoded'},
                data=form_data,
            )
            TestUtils.check_api_response(res)
        return stored_account

    def delete_user(self, api_request_context: APIRequestContext, account_id: int):
        res = api_request_context.delete(
            f'/account-delete/{PUBLIC_EVENT_ID}/{account_id}',
            headers={'Content-Type': 'application/x-www-form-urlencoded'},
        )
        TestUtils.check_api_response(res)

    def get_access_levels(self) -> list[type[AccessLevel]]:
        """Override this in subclasses to specify the access levels to test."""
        raise NotImplementedError

    def get_tournament_ids(self) -> list[int] | None:
        """Override this in subclasses to specify the tournaments to restrict the account to."""
        return None

    @pytest.fixture(autouse=True)
    def access_level_test_tournament(
        self, api_request_context: APIRequestContext, access_level_test_events
    ):
        """A fixture to create a paired tournament"""
        tournament = TestUtils.create_tournament(
            PUBLIC_EVENT_ID,
            TOURNAMENT_ID,
            api_request_context,
            json_file='test-screens',
            overrides={'record_illegal_moves': 1},
        )
        self.paired_tournament = tournament
        yield tournament
        self.paired_tournament = None
        TestUtils.delete_tournament(api_request_context, PUBLIC_EVENT_ID, tournament)

    @pytest.fixture(autouse=True)
    def access_level_test_unpaired_tournament(
        self, api_request_context: APIRequestContext, access_level_test_events
    ):
        """A fixture to create an unpaired tournament"""
        tournament = TestUtils.create_tournament(
            PUBLIC_EVENT_ID,
            TOURNAMENT_UNPAIRED_ID,
            api_request_context,
            json_file='test-screens-unpaired',
        )
        self.unpaired_tournament = tournament
        yield tournament
        self.unpaired_tournament = None
        TestUtils.delete_tournament(api_request_context, PUBLIC_EVENT_ID, tournament)

    @pytest.fixture(autouse=True)
    def public_input_screen(
        self, api_request_context: APIRequestContext, access_level_test_tournament
    ):
        """A fixture to create a public input screen for the paired tournament"""
        stored_screen = TestUtils.create_screen(
            api_request_context,
            PUBLIC_EVENT_ID,
            'Input Screen with pairings',
            ScreenType.INPUT,
            {
                'init_set_tournament_id': access_level_test_tournament.id,
                'public': True,
            },
        )
        self.paired_screen = stored_screen
        yield stored_screen
        self.paired_screen = None
        TestUtils.delete_screen(api_request_context, PUBLIC_EVENT_ID, stored_screen.id)

    @pytest.fixture(autouse=True)
    def public_check_in_screen(
        self,
        api_request_context: APIRequestContext,
        access_level_test_unpaired_tournament,
    ):
        """A fixture to create a public input screen for the unpaired tournament"""
        stored_screen = TestUtils.create_screen(
            api_request_context,
            PUBLIC_EVENT_ID,
            'Check-in Screen',
            ScreenType.CHECK_IN,
            {
                'init_set_tournament_id': access_level_test_unpaired_tournament.id,
                'public': True,
            },
        )
        self.check_in_screen = stored_screen
        yield stored_screen
        self.check_in_screen = None

        TestUtils.delete_screen(api_request_context, PUBLIC_EVENT_ID, stored_screen.id)

    @pytest.fixture(autouse=True)
    def private_input_screen(
        self, api_request_context: APIRequestContext, access_level_test_tournament
    ):
        """A fixture to create a private input screen for the paired tournament"""
        stored_screen = TestUtils.create_screen(
            api_request_context,
            PUBLIC_EVENT_ID,
            'private-input',
            ScreenType.INPUT,
            {
                'init_set_tournament_id': access_level_test_tournament.id,
                'public': False,
            },
        )
        self.private_input_screen = stored_screen
        yield stored_screen
        self.private_input_screen = None
        TestUtils.delete_screen(api_request_context, PUBLIC_EVENT_ID, stored_screen.id)

    def assert_access_to_visible_events(self, event_id: str, auth_page: Page):
        """Asserts that the user can access the public event only"""
        auth_page.goto('/home')
        expect(auth_page.locator('.card')).to_have_count(1)
        expect(auth_page.locator(f"div.card:has-text('{event_id}')")).to_be_visible()

    # --------------------------------------------------------------------------
    # Input Screens
    # --------------------------------------------------------------------------

    def assert_access_to_input_screen(
        self,
        can_access: bool,
        mode: DisplayMode,
        page: Page,
        screen: StoredScreen,
    ):
        match mode:
            case DisplayMode.SCREENS_NOT_IN_MENU:
                # There's no button in the menu, but we test direct access
                page.goto(f'/event/{PUBLIC_EVENT_ID}/input-screens')

            case DisplayMode.SCREENS_IN_SUBMENU:
                page.goto(f'/event/{PUBLIC_EVENT_ID}')
                screens_button = page.get_by_test_id('nav-admin-event-views-tab')
                expect(screens_button).to_be_visible()
                screens_button.click()

                single_screens_button = page.get_by_test_id(
                    'nav-admin-event-screens-tab-tab'
                )
                expect(single_screens_button).to_be_visible()
                single_screens_button.click()

                accordion_button = page.get_by_test_id('accordion-screen-type-input')
                expect(accordion_button).to_be_visible()
                accordion_button.click()

            case DisplayMode.SCREENS_IN_MENU:
                page.goto(f'/event/{PUBLIC_EVENT_ID}')
                screens_button = page.get_by_test_id('nav-admin-event-views-tab')
                expect(screens_button).not_to_be_visible()
                input_screens_button = page.get_by_test_id(
                    'nav-admin-event-input-screens-tab-tab'
                )
                expect(input_screens_button).to_be_visible()
                input_screens_button.click()

        card = page.locator(f"div.card:has-text('{screen.name}')")

        if can_access:
            expect(card).to_be_visible()
        else:
            expect(card).not_to_be_visible()

        if can_access:
            # Test access to the input screen
            page.goto(f'/view/screen/{PUBLIC_EVENT_ID}/{screen.uniq_id}')
            rows = page.locator('div.board-row')
            expect(rows).to_have_count(8)
        else:
            # Test no access to the input screen, should redirect to the 403 page
            page.goto(f'/view/screen/{PUBLIC_EVENT_ID}/{screen.uniq_id}')
            page.wait_for_url('/error/403')

    def assert_can_checkin_via_screen(
        self,
        can_access: bool,
        api_request_context: APIRequestContext,
    ):
        self.auth_page.goto(
            f'/view/screen/{PUBLIC_EVENT_ID}/{self.check_in_screen.uniq_id}'
        )
        rows = self.auth_page.locator('div.player-row')

        expect(rows).to_have_count(16)
        row = rows.filter(has_text='AMOS')

        if can_access:
            # Try to open the modal
            expect(row.locator('div:nth-child(1)')).to_have_attribute(
                'hx-get', re.compile(r'.*checkin-modal.*')
            )
            row.click()
            modal = self.auth_page.locator('.modal-dialog')

            expect(modal).to_be_visible()
            button = TestUtils.button_by_text(modal, 'CHECK-IN')
            expect(button).to_contain_text('AMOS')
            button.click()

            # Test that the page is updated
            expect(row.locator('i.bi-check-square-fill')).to_be_visible()
        else:
            expect(row.locator('div:nth-child(1)')).not_to_have_attribute(
                'hx-get', re.compile(r'.*checkin-modal.*')
            )

    def assert_can_enter_results_via_screen(
        self,
        can_enter: bool,
        can_update: bool,
        can_set_special_results: bool,
    ):
        self.auth_page.goto(
            f'/view/screen/{PUBLIC_EVENT_ID}/{self.paired_screen.uniq_id}'
        )
        rows = self.auth_page.locator('div.board-row')

        expect(rows).to_have_count(8)
        row = rows.filter(has_text='ALYX')
        result_cell = row.locator('div.score')
        if not can_enter:
            expect(result_cell).not_to_have_attribute(
                'hx-get', re.compile(r'.*result-modal.*')
            )
            return

        # Try to open the modal
        expect(result_cell).to_have_attribute('hx-get', re.compile(r'.*result-modal.*'))
        row.click()
        modal = self.auth_page.locator('.modal-dialog')

        expect(modal).to_be_visible()
        button = TestUtils.button_by_text(modal, 'ALYX')
        button.click()

        if not can_set_special_results:
            expect(
                modal.get_by_test_id('white-wins-by-forfeit-button')
            ).not_to_be_visible()
            expect(modal.get_by_test_id('double-forfeit-button')).not_to_be_visible()
            expect(
                modal.get_by_test_id('black-wins-by-forfeit-button')
            ).not_to_be_visible()

        if not can_update:
            expect(modal.get_by_test_id('clear-result-button')).not_to_be_visible()

        # Test that the page is updated
        expect(result_cell).to_have_text('1-0')

        if can_set_special_results:
            result_cell.click()
            expect(modal).to_be_visible()
            clear_button = modal.get_by_test_id('white-wins-by-forfeit-button')
            clear_button.click()
            expect(result_cell).to_have_text('1-F')

        if can_update:
            result_cell.click()
            expect(modal).to_be_visible()
            clear_button = modal.get_by_test_id('clear-result-button')
            clear_button.click()
            expect(result_cell).to_have_text('#1')
        else:
            expect(result_cell).not_to_have_attribute(
                'hx-get', re.compile(r'.*result-modal.*')
            )

    def assert_can_set_illegal_moves_via_screen(
        self,
        can_access: bool,
        api_request_context: APIRequestContext,
    ):
        self.auth_page.goto(
            f'/view/screen/{PUBLIC_EVENT_ID}/{self.paired_screen.uniq_id}'
        )
        rows = self.auth_page.locator('div.board-row')

        row = rows.filter(has_text='ALYX')
        illegal_move_button = row.get_by_test_id('add-illegal-move-button-W')
        illegal_move_icon = row.get_by_test_id('illegal-move-icon-W')
        if not can_access:
            expect(illegal_move_button).not_to_be_visible()
            expect(illegal_move_icon).not_to_be_visible()

            # Check that the illegal moves are display (but can't be deleted)
            with EventDatabase(PUBLIC_EVENT_ID) as database:
                event = Event(database.load_stored_event())
                alyx = next(
                    p for p in event.players_by_id.values() if p.last_name == 'ALYX'
                )

            api_request_context.put(
                f'/view/add-illegal-move/1/{PUBLIC_EVENT_ID}/{self.paired_screen.uniq_id}/{self.paired_tournament.id}/{alyx.id}'
            )
            expect(illegal_move_icon).to_be_visible()
            expect(illegal_move_icon).not_to_have_attribute(
                'hx-delete', re.compile(r'.*delete-illegal-move.*')
            )

            return

        illegal_move_button.click()
        illegal_move_icon = row.get_by_test_id('illegal-move-icon-W')
        expect(illegal_move_icon).to_have_attribute(
            'hx-delete', re.compile(r'.*delete-illegal-move.*')
        )

        expect(illegal_move_button).not_to_be_visible()
        illegal_move_icon.click()
        expect(illegal_move_button).not_to_be_visible()
        expect(illegal_move_icon).not_to_be_visible()

    # --------------------------------------------------------------------------
    # Players tab
    # --------------------------------------------------------------------------

    def assert_can_access_players_tab(
        self,
        can_access: bool,
        page: Page,
    ):
        page.goto(f'/event/{PUBLIC_EVENT_ID}')
        players_button = page.get_by_test_id('nav-admin-event-players-tab-tab')
        if can_access:
            expect(players_button).to_be_visible()
            players_button.click()
            page.wait_for_url(f'/event/{PUBLIC_EVENT_ID}/players')
        else:
            expect(players_button).not_to_be_visible()
            page.goto(f'/event/{PUBLIC_EVENT_ID}/players')
            page.wait_for_url('/error/403')

    def assert_can_checkin_via_players_tab(
        self,
        can_access: bool,
        api_request_context: APIRequestContext,
    ):
        self.auth_page.goto(f'/event/{PUBLIC_EVENT_ID}/players')
        rows = self.auth_page.locator('table#players-table tbody tr')
        row = rows.filter(has_text='AMOS')
        check_in_button = row.get_by_test_id('check-in-cell')

        if can_access:
            TestUtils.poll_expect_with_reload(
                self.auth_page,
                lambda: expect(check_in_button).to_have_class(
                    re.compile(r'\bbi-x-circle-fill\b'), timeout=1
                ),
            )

            expect(check_in_button).to_have_attribute(
                'hx-patch', re.compile(r'.*player-table/check-in-player.*')
            )
            check_in_button.click()
            expect(check_in_button).to_have_class(
                re.compile(r'\bbi-check-circle-fill\b')
            )
            check_in_button.click()
            expect(check_in_button).to_have_class(re.compile(r'\bbi-x-circle-fill\b'))
        else:
            expect(check_in_button).not_to_have_attribute(
                'hx-patch', re.compile(r'.*player-table/check-in-player.*')
            )

    # --------------------------------------------------------------------------
    # Pairings tab
    # --------------------------------------------------------------------------

    def assert_can_access_pairings_tab(
        self,
        can_access: bool,
        page: Page,
    ):
        page.goto(f'/event/{PUBLIC_EVENT_ID}')
        pairings_button = page.get_by_test_id('nav-admin-event-pairings-tab-tab')

        if can_access:
            expect(pairings_button).to_be_visible()
            pairings_button.click()
            page.wait_for_url(f'/event/{PUBLIC_EVENT_ID}/pairings')
        else:
            expect(pairings_button).not_to_be_visible()
            page.goto(f'/event/{PUBLIC_EVENT_ID}/pairings')
            page.wait_for_url('/error/403')
