import pytest
from playwright.sync_api import APIRequestContext

from data.auth.exec_mode import ExecMode
from tests.test_config import TestUtils


PUBLIC_EVENT_ID = 'event-test-roles-public'
PRIVATE_EVENT_ID = 'event-test-roles-private'


@pytest.fixture(scope='module', autouse=True)
def event_database(api_request_context: APIRequestContext):
    TestUtils.create_event(
        api_request_context,
        PUBLIC_EVENT_ID,
        {'exec_mode': ExecMode.CUSTOM, 'public': True},
    )
    TestUtils.create_event(api_request_context, PRIVATE_EVENT_ID, {'public': False})
    TestUtils.create_tournament(
        api_request_context, PUBLIC_EVENT_ID, 'tournament-test-roles-public'
    )
    TestUtils.create_tournament(
        api_request_context, PUBLIC_EVENT_ID, 'tournament-test-roles-private'
    )
    yield
    TestUtils.delete_event(api_request_context, PUBLIC_EVENT_ID)
    TestUtils.delete_event(api_request_context, PRIVATE_EVENT_ID)
