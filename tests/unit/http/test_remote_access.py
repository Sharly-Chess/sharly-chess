"""What the server says to a visitor who arrived through the tunnel.

The tunnel client runs on the machine it exposes, so its requests reach the
server from the loopback address exactly as the local browser's do. Everything
here turns on the one thing that tells them apart — the listener they landed on
— which is why it can be asserted without a browser, a socket or a relay.
"""

from collections.abc import Iterator

import pytest
from litestar.testing import TestClient

from data.loader import EventLoader
from tests.test_config import TestUtils
from web.tunnel import REMOTE_SESSION_MAX_AGE

PRIVATE_EVENT_ID = 'test-remote-access-private'


@pytest.fixture
def private_event() -> Iterator[str]:
    TestUtils.create_event(PRIVATE_EVENT_ID, overrides={'public': False})
    yield PRIVATE_EVENT_ID
    EventLoader.unload_event(PRIVATE_EVENT_ID)
    TestUtils.delete_event(PRIVATE_EVENT_ID)


@pytest.mark.unit
class TestWhoTheVisitorIs:
    def test_the_machine_itself_is_granted_the_administrator_account(
        self, http: TestClient, private_event: str
    ):
        response = http.get(f'/event/{private_event}', follow_redirects=False)

        assert response.status_code == 302
        assert private_event in response.headers['location']

    def test_the_same_request_through_the_tunnel_is_not(
        self, remote: TestClient, private_event: str
    ):
        """Granting the administrator's rights to whoever reaches the loopback
        address is right for the person sitting at the machine and wrong for
        everyone the tunnel carries."""
        response = remote.get(f'/event/{private_event}', follow_redirects=False)

        assert response.status_code == 302
        assert private_event not in response.headers['location']


@pytest.mark.unit
class TestSessionTerms:
    def test_a_session_opened_from_the_internet_is_secure_and_short_lived(
        self, remote: TestClient
    ):
        response = remote.get('/', follow_redirects=False)

        set_cookie = response.headers['set-cookie']

        assert 'Secure' in set_cookie
        assert f'Max-Age={REMOTE_SESSION_MAX_AGE}' in set_cookie

    def test_a_session_opened_on_the_local_network_keeps_its_own_terms(
        self, lan: TestClient
    ):
        response = lan.get('/', follow_redirects=False)

        set_cookie = response.headers['set-cookie']

        assert 'Secure' not in set_cookie
        assert f'Max-Age={REMOTE_SESSION_MAX_AGE}' not in set_cookie


@pytest.mark.unit
class TestInstanceIdentity:
    def test_a_hostname_nothing_is_live_on_says_so(self, remote: TestClient):
        """Answered rather than raised: the control plane reads this, not a
        person, so it must not be turned into a page."""
        response = remote.get(
            '/.well-known/sharly-chess-instance',
            headers={'Host': 'nobody.live.example.com'},
            follow_redirects=False,
        )

        assert response.status_code == 404


@pytest.mark.unit
class TestSignIn:
    """The sign-in is reached by ordinary navigation from the application
    window, so it has to answer with something a browser will follow."""

    def test_signing_in_sends_the_browser_somewhere(self, http: TestClient):
        response = http.get('/remote-access/sign-in', follow_redirects=False)

        assert response.status_code == 302
        assert response.headers['location']

    def test_signing_out_sends_the_browser_somewhere(self, http: TestClient):
        response = http.get('/remote-access/sign-out', follow_redirects=False)

        assert response.status_code == 302
        assert response.headers['location']

    def test_a_code_nobody_is_waiting_for_is_refused_rather_than_honoured(
        self, http: TestClient
    ):
        response = http.get(
            '/remote-access/callback',
            params={'code': 'invented', 'state': 'nobody-is-waiting'},
            follow_redirects=False,
        )

        assert response.status_code == 302


@pytest.mark.unit
class TestCrawlers:
    """What is said to whoever is reading the server rather than using it."""

    def test_crawlers_are_asked_to_leave_the_event_alone(self, http: TestClient):
        response = http.get('/robots.txt')

        assert response.status_code == 200
        assert 'Disallow: /' in response.text

    def test_every_page_says_it_too(self, http: TestClient):
        """A crawler arriving by a link elsewhere has not read the file."""
        response = http.get('/robots.txt')

        assert 'noindex' in response.headers.get('X-Robots-Tag', '')


@pytest.mark.unit
class TestProbes:
    """What a stranger guessing at filenames is answered with.

    Anything reachable from the internet is guessed at continuously. A refusal
    is the right answer; a server error is an invitation to keep going, and it
    fills the log of a laptop that is running a tournament.
    """

    @pytest.mark.parametrize(
        'path',
        ['/config.json', '/.env', '/app.css', '/settings.json', '/static/nothing.json'],
    )
    def test_a_guess_at_a_filename_is_refused_rather_than_failing(
        self, http: TestClient, path: str
    ):
        response = http.get(path, follow_redirects=False)

        assert response.status_code < 500

    def test_a_method_the_server_does_not_answer_is_refused(self, http: TestClient):
        response = http.post('/graphql', follow_redirects=False)

        assert response.status_code < 500
