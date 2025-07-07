from argon2 import PasswordHasher
from data.loader import EventLoader
import pytest
from playwright.sync_api import Browser, Page, expect
from database.sqlite.event.event_database import EventDatabase
from database.sqlite.event.event_store import StoredAccount
from data.auth.roles import Role
from common.sharly_chess_config import SharlyChessConfig
from tests.e2e.roles.conftest import PUBLIC_EVENT_ID


class BaseRoleTest:
    @pytest.fixture(scope='class', autouse=True)
    def auth_page(self, request, lan_page: Page, browser: Browser):
        cls = request.cls  # the actual test class instance
        cls.create_user(cls, cls.get_roles(cls), cls.get_tournament_ids(cls))
        cls.do_login(cls, lan_page)

        # Store the auth state a tmp file
        storage = f'auth-{cls.__class__.__name__.lower()}.json'
        lan_page.context.storage_state(path=storage)
        lan_page.context.close()

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
        cls.delete_user(cls)

    def create_user(
        self, role_types: list[type[Role]], tournament_ids: list[int] | None = None
    ):
        ph = PasswordHasher()
        password_hash = ph.hash('test-password')
        with EventDatabase(PUBLIC_EVENT_ID, write=True) as db:
            db.create_custom_exec_mode_objects()
            db.commit()
            self.account = db.add_stored_account(
                StoredAccount(
                    id=None,
                    active=True,
                    username='test-account',
                    password_hash=password_hash,
                    roles=[type_.static_id() for type_ in role_types],
                    tournament_ids=tournament_ids,
                )
            )
            db.commit()
        EventLoader.get(request=None).unload_event(PUBLIC_EVENT_ID)

    def delete_user(self):
        with EventDatabase(PUBLIC_EVENT_ID, write=True) as db:
            db.delete_stored_account(self.account.id)
            db.commit()
        EventLoader.get(request=None).unload_event(PUBLIC_EVENT_ID)

    def do_login(self, lan_page: Page):
        lan_page.goto(f'/admin/event/{PUBLIC_EVENT_ID}')
        lan_page.get_by_test_id('profile-button').click()
        lan_page.locator('#username').fill('test-account')
        lan_page.locator('#password').fill('test-password')
        button = lan_page.locator('#modal-form button[type=submit]')
        button.click()
        expect(lan_page.get_by_text('Account: test-account')).to_be_visible()

    def get_roles(self) -> list[type[Role]]:
        """Override this in subclasses to specify the roles to test."""
        raise NotImplementedError

    def get_tournament_ids(self) -> list[int] | None:
        """Override this in subclasses to specify the tournaments to restrict the account to."""
        return None
