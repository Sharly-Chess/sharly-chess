import pytest
from playwright.sync_api import APIRequestContext, Browser

from common.sharly_chess_config import SharlyChessConfig
from tests.test_config import TestUtils


PUBLIC_EVENT_ID = 'event-test-roles-public'
PRIVATE_EVENT_ID = 'event-test-roles-private'
TOURNAMENT_ID = 'tournament-test-roles'
TOURNAMENT_UNPAIRED_ID = 'tournament-test-roles-unpaired'


@pytest.fixture(scope='module', autouse=True)
def role_test_events(api_request_context: APIRequestContext):
    # Create a public and private event
    TestUtils.create_event(
        api_request_context,
        PUBLIC_EVENT_ID,
        {'custom_exec_mode': True, 'public': True},
    )
    TestUtils.create_event(
        api_request_context,
        PRIVATE_EVENT_ID,
        {'custom_exec_mode': True, 'public': False},
    )

    yield

    TestUtils.delete_event(api_request_context, PUBLIC_EVENT_ID)
    TestUtils.delete_event(api_request_context, PRIVATE_EVENT_ID)


@pytest.fixture(scope='module')
def login_page(browser: Browser):
    config = SharlyChessConfig()
    config.web_port = 9000
    context = browser.new_context(base_url=config.lan_url)
    page = context.new_page()
    yield page
    context.close()
