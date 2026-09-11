"""Slowing down password guessing.

Guessing used to be limited by having to reach the server, which meant standing
in the venue. Once the screens are reachable over the internet that no longer
holds, so the cost of an attempt is charged explicitly.

Driven through the tunnel client because the log-in form is only offered to
somebody who is not the machine itself.
"""

import re
from collections.abc import Iterator

import pytest
from litestar.testing import TestClient

from data.loader import EventLoader
from tests.test_config import TestUtils
from web.login_throttle import ACCOUNT_FREE_ATTEMPTS, LoginThrottle

EVENT_ID = 'test-login-throttle'
FIRST_NAME = 'throttle'
LAST_NAME = 'TEST'
FULL_NAME = f'{FIRST_NAME} {LAST_NAME}'
PASSWORD = 'test-password'


@pytest.fixture
def event(http: TestClient) -> Iterator[str]:
    TestUtils.create_event(EVENT_ID)
    created = http.post(
        f'/account-create/{EVENT_ID}',
        data={
            'first_name': FIRST_NAME,
            'last_name': LAST_NAME,
            'password': PASSWORD,
            'active': 'on',
        },
    )
    assert created.status_code == 200

    LoginThrottle.reset()
    yield EVENT_ID
    LoginThrottle.reset()

    EventLoader.unload_event(EVENT_ID)
    TestUtils.delete_event(EVENT_ID)


def account_id(client: TestClient) -> str:
    """The id the log-in form offers for the account, read from the form."""
    response = client.get(f'/profile-modal/{EVENT_ID}')
    assert response.status_code == 200
    match = re.search(
        rf'<option value="(\d+)"[^>]*>\s*{FULL_NAME}', response.text, re.MULTILINE
    )
    assert match is not None, f'[{FULL_NAME}] is not offered by the log-in form'
    return match.group(1)


def attempt_login(client: TestClient, password: str) -> str:
    response = client.post(
        f'/profile-login/{EVENT_ID}',
        data={'account_id': account_id(client), 'password': password},
    )
    return response.text


@pytest.mark.unit
def test_a_run_of_wrong_passwords_stops_being_answered(
    remote: TestClient, event: str
) -> None:
    for __ in range(ACCOUNT_FREE_ATTEMPTS + 1):
        assert 'Invalid password.' in attempt_login(remote, 'wrong-password')

    assert 'Too many failed attempts' in attempt_login(remote, 'wrong-password')


@pytest.mark.unit
def test_the_right_password_is_still_refused_while_locked_out(
    remote: TestClient, event: str
) -> None:
    """Otherwise the lockout would be no more than a delay on the last guess."""
    for __ in range(ACCOUNT_FREE_ATTEMPTS + 1):
        attempt_login(remote, 'wrong-password')

    assert 'Too many failed attempts' in attempt_login(remote, PASSWORD)


@pytest.mark.unit
def test_the_right_password_is_taken_while_nothing_is_locked_out(
    remote: TestClient, event: str
) -> None:
    assert 'Invalid password.' not in attempt_login(remote, PASSWORD)
