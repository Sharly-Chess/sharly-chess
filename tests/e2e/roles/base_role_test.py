from enum import IntEnum
import re
from database.sqlite.event.event_store import StoredScreen
import pytest
from playwright.sync_api import Browser, Page, expect, APIRequestContext
from database.sqlite.event.event_database import EventDatabase
from data.auth.roles import Role
from common.sharly_chess_config import SharlyChessConfig
from tests.e2e.roles.conftest import (
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


class BaseRoleTest:
    @pytest.fixture(scope='class', autouse=True)
    def auth_page(
        self,
        api_request_context: APIRequestContext,
        request,
        login_page: Page,
        browser: Browser,
    ):
        cls = request.cls  # the actual test class instance

        if not cls.get_roles(cls) and not cls.get_tournament_ids(cls):
            # Don't logon for anonymous tests
            yield None
            return

        stored_account = cls.create_user(
            cls, api_request_context, cls.get_roles(cls), cls.get_tournament_ids(cls)
        )
        cls.do_login(cls, login_page)

        # Store the auth state a tmp file
        storage = f'auth-{cls.__class__.__name__.lower()}.json'
        login_page.context.storage_state(path=storage)

        config = SharlyChessConfig()
        config.web_port = 9000
        auth_context = browser.new_context(
            base_url=config.lan_url,
            storage_state=storage,
        )
        auth_page = auth_context.new_page()
        auth_page.set_default_timeout(15000)
        auth_page.set_default_navigation_timeout(10000)

        cls.auth_context = auth_context
        cls.auth_page = auth_page

        yield cls.auth_page

        auth_page.close()
        auth_context.close()
        cls.delete_user(cls, api_request_context, stored_account.id)

    def create_user(
        self,
        api_request_context: APIRequestContext,
        role_types: list[type[Role]],
        tournament_ids: list[int] | None = None,
    ):
        username = 'test-account'
        data = {
            'username': username,
            'password': 'test-password',
            'active': True,
            'roles': [type_.static_id() for type_ in role_types],
            'tournament_ids': tournament_ids,
        }

        form_data = TestUtils.prepare_form_data(data)

        res = api_request_context.post(
            f'/admin/account-create/{PUBLIC_EVENT_ID}',
            headers={'Content-Type': 'application/x-www-form-urlencoded'},
            data=form_data,
        )
        TestUtils.check_api_response(res)
        with EventDatabase(PUBLIC_EVENT_ID) as event_database:
            accounts = event_database.load_stored_accounts()
            stored_account = next(a for a in accounts if a.username == username)
        return stored_account

    def delete_user(self, api_request_context: APIRequestContext, account_id: int):
        res = api_request_context.delete(
            f'/admin/account-delete/{PUBLIC_EVENT_ID}/{account_id}',
            headers={'Content-Type': 'application/x-www-form-urlencoded'},
        )
        TestUtils.check_api_response(res)

    def do_login(self, login_page: Page):
        login_page.goto(f'/admin/event/{PUBLIC_EVENT_ID}')
        login_page.get_by_test_id('profile-button').click()
        login_page.locator('#username').fill('test-account')
        login_page.locator('#password').fill('test-password')
        button = login_page.locator('#modal-form button[type=submit]')
        button.click()
        expect(login_page.get_by_text('Account: test-account')).to_be_visible()

    def get_roles(self) -> list[type[Role]]:
        """Override this in subclasses to specify the roles to test."""
        raise NotImplementedError

    def get_tournament_ids(self) -> list[int] | None:
        """Override this in subclasses to specify the tournaments to restrict the account to."""
        return None

    @pytest.fixture(autouse=True)
    def role_test_tournament(
        self, api_request_context: APIRequestContext, role_test_events
    ):
        tournament = TestUtils.create_tournament(
            api_request_context,
            PUBLIC_EVENT_ID,
            TOURNAMENT_ID,
            papi_file='test-screens',
        )
        yield tournament
        TestUtils.delete_tournament(api_request_context, PUBLIC_EVENT_ID, tournament)

    @pytest.fixture(autouse=True)
    def role_test_unpaired_tournament(
        self, api_request_context: APIRequestContext, role_test_events
    ):
        tournament = TestUtils.create_tournament(
            api_request_context,
            PUBLIC_EVENT_ID,
            TOURNAMENT_UNPAIRED_ID,
            papi_file='test-screens-unpaired',
        )
        yield tournament
        TestUtils.delete_tournament(api_request_context, PUBLIC_EVENT_ID, tournament)

    @pytest.fixture()
    def public_input_screen(
        self, api_request_context: APIRequestContext, role_test_tournament
    ):
        stored_screen = TestUtils.create_screen(
            api_request_context,
            PUBLIC_EVENT_ID,
            'public-input',
            ScreenType.INPUT,
            {
                'init_set_tournament_id': role_test_tournament.id,
                'public': True,
                'name': 'PairedInput Screen',
            },
        )
        yield stored_screen
        TestUtils.delete_screen(api_request_context, PUBLIC_EVENT_ID, stored_screen.id)

    @pytest.fixture()
    def public_input_unpaired_screen(
        self, api_request_context: APIRequestContext, role_test_unpaired_tournament
    ):
        stored_screen = TestUtils.create_screen(
            api_request_context,
            PUBLIC_EVENT_ID,
            'public-input-unpaired',
            ScreenType.INPUT,
            {
                'init_set_tournament_id': role_test_unpaired_tournament.id,
                'public': True,
                'name': 'Unpaired Input Screen',
            },
        )
        yield stored_screen
        TestUtils.delete_screen(api_request_context, PUBLIC_EVENT_ID, stored_screen.id)

    @pytest.fixture()
    def private_input_screen(
        self, api_request_context: APIRequestContext, role_test_tournament
    ):
        stored_screen = TestUtils.create_screen(
            api_request_context,
            PUBLIC_EVENT_ID,
            'private-input',
            ScreenType.INPUT,
            {'init_set_tournament_id': role_test_tournament.id, 'public': False},
        )
        yield stored_screen
        TestUtils.delete_screen(api_request_context, PUBLIC_EVENT_ID, stored_screen.id)

    def assert_access_to_visible_events(self, event_id: str, auth_page: Page):
        auth_page.goto('/admin/current_events')
        expect(auth_page.locator('.card')).to_have_count(1)
        expect(auth_page.locator(f"div.card:has-text('{event_id}')")).to_be_visible()

    def assert_access_to_input_screen(
        self,
        can_access: bool,
        mode: DisplayMode,
        event_id: str,
        page: Page,
        screen: StoredScreen,
    ):
        match mode:
            case DisplayMode.SCREENS_NOT_IN_MENU:
                # There's no button in the menu, but we test direct access
                page.goto(f'/admin/event/{event_id}/input-screens')

            case DisplayMode.SCREENS_IN_SUBMENU:
                page.goto(f'/admin/event/{event_id}')
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
                page.goto(f'/admin/event/{event_id}')
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
            page.goto(f'/user/screen/{event_id}/{screen.uniq_id}')
            rows = page.locator('table tbody tr')
            expect(rows).to_have_count(8)
        else:
            # Test no access to the input screen, should redirect to the 403 page
            page.goto(f'/user/screen/{event_id}/{screen.uniq_id}')
            page.wait_for_url('/error/403')

    def assert_can_checkin_via_screen(
        self,
        can_access: bool,
        event_id: str,
        tournament_id: int,
        page: Page,
        screen: StoredScreen,
        api_request_context: APIRequestContext,
    ):
        # Open check-in
        api_request_context.patch(
            f'/admin/tournament-open-check-in/{event_id}/{tournament_id}'
        )

        page.goto(f'/user/screen/{event_id}/{screen.uniq_id}')
        rows = page.locator('table tbody tr')

        expect(rows).to_have_count(16)
        row = rows.filter(has_text='AMOS')

        if can_access:
            # Try to open the modal
            expect(row.locator('td:nth-child(1)')).to_have_attribute(
                'hx-get', re.compile(r'.*checkin-modal.*')
            )
            row.click()
            modal = page.locator('.modal-dialog')

            expect(modal).to_be_visible()
            button = TestUtils.button_by_text(modal, 'CHECK-IN')
            expect(button).to_contain_text('AMOS')
            button.click()

            # Test that the page is updated
            expect(row.locator('i.bi-check-square-fill')).to_be_visible()
        else:
            expect(row.locator('td:nth-child(1)')).not_to_have_attribute(
                'hx-get', re.compile(r'.*checkin-modal.*')
            )

    def assert_can_access_players_tab(
        self,
        can_access: bool,
        event_id: str,
        page: Page,
    ):
        page.goto(f'/admin/event/{event_id}')
        players_button = page.get_by_test_id('nav-admin-event-players-tab-tab')
        if can_access:
            expect(players_button).to_be_visible()
            players_button.click()
            page.wait_for_url(f'/admin/event/{event_id}/players')
        else:
            expect(players_button).not_to_be_visible()
            page.goto(f'/admin/event/{event_id}/players')
            page.wait_for_url('/error/403')

    def assert_can_access_pairings_tab(
        self,
        can_access: bool,
        event_id: str,
        page: Page,
    ):
        page.goto(f'/admin/event/{event_id}')
        pairings_button = page.get_by_test_id('nav-admin-event-pairings-tab-tab')

        if can_access:
            expect(pairings_button).to_be_visible()
            pairings_button.click()
            page.wait_for_url(f'/admin/event/{event_id}/pairings')
        else:
            expect(pairings_button).not_to_be_visible()
            page.goto(f'/admin/event/{event_id}/pairings')
            page.wait_for_url('/error/403')

    def assert_can_checkin_via_players_tab(
        self,
        can_access: bool,
        event_id: str,
        tournament_id: int,
        page: Page,
        api_request_context: APIRequestContext,
    ):
        # Open check-in
        api_request_context.patch(
            f'/admin/tournament-open-check-in/{event_id}/{tournament_id}'
        )

        page.goto(f'/admin/event/{event_id}/players')
        rows = page.locator('table#players-table tbody tr')
        row = rows.filter(has_text='AMOS')
        check_in_button = row.get_by_test_id('check-in-cell')

        if can_access:
            TestUtils.poll_expect_with_reload(
                page,
                lambda: expect(check_in_button).to_have_class(
                    re.compile(r'\bbi-circle-fill\b'), timeout=1
                ),
            )

            expect(check_in_button).to_have_attribute(
                'hx-patch', re.compile(r'.*player-check-in.*')
            )
            check_in_button.click()
            expect(check_in_button).to_have_class(
                re.compile(r'\bbi-check-circle-fill\b')
            )
            check_in_button.click()
            expect(check_in_button).to_have_class(re.compile(r'\bbi-circle-fill\b'))
        else:
            expect(check_in_button).not_to_have_attribute(
                'hx-patch', re.compile(r'.*player-check-in.*')
            )

    def assert_can_checkin_via_pairings_tab(
        self,
        can_access: bool,
        event_id: str,
        tournament_id: int,
        page: Page,
        api_request_context: APIRequestContext,
    ):
        # Open check-in
        api_request_context.patch(
            f'/admin/tournament-open-check-in/{event_id}/{tournament_id}'
        )

        page.goto(f'/admin/event/{event_id}/pairings?tournament_id={tournament_id}')
        rows = page.locator('table#unpaired-players-table tbody tr')
        row = rows.filter(has_text='AMOS')
        check_in_button = row.get_by_test_id('check-in-cell')

        if can_access:
            TestUtils.poll_expect_with_reload(
                page,
                lambda: expect(check_in_button).to_have_class(
                    re.compile(r'\bbi-circle-fill\b'), timeout=1
                ),
            )

            expect(check_in_button).to_have_attribute(
                'hx-post', re.compile(r'.*pairings-check-in-out.*')
            )
            check_in_button.click()
            expect(check_in_button).to_have_class(
                re.compile(r'\bbi-check-circle-fill\b')
            )
            check_in_button.click()
            expect(check_in_button).to_have_class(re.compile(r'\bbi-circle-fill\b'))
        else:
            expect(check_in_button).not_to_have_attribute(
                'hx-post', re.compile(r'.*pairings-check-in-out.*')
            )
