import pytest
from playwright.sync_api import APIRequestContext

from tests.test_config import TestUtils


PUBLIC_EVENT_ID = 'event-test-roles-public'
PRIVATE_EVENT_ID = 'event-test-roles-private'
TOURNAMENT_ID = 'tournament-test-roles'
TOURNAMENT_UNPAIRED_ID = 'tournament-test-roles-unpaired'


@pytest.fixture(scope='module', autouse=True)
def role_test_events(api_request_context: APIRequestContext):
    # Create a public and private event
    TestUtils.create_event(
        PUBLIC_EVENT_ID,
        api_request_context,
        {'custom_exec_mode': True, 'public': True},
    )
    TestUtils.create_event(
        PRIVATE_EVENT_ID,
        api_request_context,
        {'custom_exec_mode': True, 'public': False},
    )

    yield

    TestUtils.delete_event(PUBLIC_EVENT_ID, api_request_context)
    TestUtils.delete_event(PRIVATE_EVENT_ID, api_request_context)
