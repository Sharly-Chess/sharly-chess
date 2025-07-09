import pytest
from playwright.sync_api import Browser, Page, expect, APIRequestContext
from database.sqlite.event.event_database import EventDatabase
from data.auth.roles import Role
from common.sharly_chess_config import SharlyChessConfig
from tests.e2e.roles.conftest import PUBLIC_EVENT_ID
from tests.test_config import TestUtils


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
