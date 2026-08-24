"""pytest configuration with Playwright setup and backend server management."""

import os
import signal
import socket
import subprocess
import sys
import time
from io import TextIOWrapper
from pathlib import Path
from typing import Generator

import pytest
import requests
from playwright.sync_api import Browser, Playwright, APIRequestContext

from common import DATA_DIR
from common.sharly_chess_config import SharlyChessConfig
from tests.test_config import TestConfig

# Note: Keeping default event loop policy for Windows (ProactorEventLoop)
# The WindowsSelectorEventLoop doesn't support subprocess operations

# Set up environment variables here to make TEST_ENV available in common.i18n
env = os.environ.copy()
env.update(TestConfig.get_test_env_vars())


def pytest_configure(config):
    """Register custom markers."""
    config.addinivalue_line(
        'markers',
        'e2e: mark test as end-to-end test requiring server (runs on commit, pull request and release)',
    )
    config.addinivalue_line(
        'markers',
        'unit: mark test as unit test (runs on commit, pull request and release)',
    )
    config.addinivalue_line(
        'markers', 'release_only: mark test as release only test (runs on release only)'
    )


def pytest_collection_modifyitems(config, items):
    """Modify test collection to add markers and optimize fixture usage."""
    # Check if we have any e2e tests in the current run
    has_e2e_tests = any(item.get_closest_marker('e2e') for item in items)

    # Store this information for fixtures to use
    config._has_e2e_tests = has_e2e_tests


class BackendServer:
    """Manages the backend server for testing."""

    def __init__(self, host: str | None = None, port: int | None = None):
        self.host = host or TestConfig.TEST_HOST
        self.port = port or TestConfig.TEST_PORT
        self.process: subprocess.Popen | None = None
        self.log_file_handle: TextIOWrapper | None = None
        # Construct base URL with explicit port
        if self.port == 80:
            self.base_url = f'http://{self.host}'
        else:
            self.base_url = f'http://{self.host}:{self.port}'
        self.test_db_dir = None

    def start(self):
        """Start the backend server."""

        # Add src directory to PYTHONPATH for server to find modules
        current_pythonpath = env.get('PYTHONPATH', '')
        project_root = Path(__file__).parent
        src_path = str((project_root / 'src').resolve())
        env['PYTHONPATH'] = (
            f'{src_path}{os.pathsep}{current_pythonpath}'
            if current_pythonpath
            else src_path
        )

        # Start your backend server process
        # Adjust this command based on how your server is started
        cmd = [
            sys.executable,
            str((project_root / 'src/sharly_chess.py').resolve()),
            '--path',
            # The worker's own data directory, not the shared root: the
            # server has to read and write the same tree as the tests
            # driving it.
            str(DATA_DIR),
        ]

        # Create log file for server output - use unique name to avoid conflicts
        import time

        log_file = DATA_DIR / f'server_{int(time.time())}.log'

        # Keep reference to log file handle so we can close it later
        self.log_file_handle = open(log_file, 'w')

        self.process = subprocess.Popen(
            cmd,
            stdout=self.log_file_handle,  # Log to file instead of pipe
            stderr=subprocess.STDOUT,  # Combine stderr with stdout
            text=True,
            env=env,
            cwd=Path(__file__).parent,  # Ensure we're in the right directory
            # Its own process group, so stop() can signal the server and
            # everything it forked in one go.
            start_new_session=True,
        )

        # Wait for server to be ready
        self._wait_for_server()

    #: How long to let the server shut down cleanly before killing it. It
    #: holds the screens' event streams open and never exits on the
    #: signal, so this elapses in full every time — but the graceful
    #: shutdown releases the listening socket while it does, which is what
    #: lets the next run bind the port.
    STOP_TIMEOUT = 2
    #: How long to keep waiting for the port after the server is gone.
    PORT_RELEASE_TIMEOUT = 10

    def stop(self):
        """Stop the backend server and everything it forked."""
        if self.process:
            self._signal_group(signal.SIGTERM)
            try:
                self.process.wait(timeout=self.STOP_TIMEOUT)
            except subprocess.TimeoutExpired:
                pass
            # Unconditionally, not only when the parent outstays its
            # welcome: the parent exiting says nothing about the child it
            # forked, which is left holding open handles on a data
            # directory the next run deletes underneath it.
            self._signal_group(signal.SIGKILL)
            self.process.wait()
            self._wait_for_port_release()

        # Close log file handle if it exists
        if self.log_file_handle:
            self.log_file_handle.close()

    def _signal_group(self, signal_number: int):
        """Signal the server's whole process group.

        The server forks, and it is the child that holds the listening
        socket: signalling the parent alone leaves the child bound to the
        port, and the next run cannot start at all ('All the candidate
        ports are already in use').
        """
        assert self.process is not None
        try:
            os.killpg(os.getpgid(self.process.pid), signal_number)
        except (ProcessLookupError, PermissionError):
            # Already gone, or not ours to signal as a group.
            self.process.send_signal(signal_number)

    def _wait_for_port_release(self):
        """Block until the port can be bound again.

        Waiting on the process is not enough: the socket outlives it
        briefly, and a suite that starts a server per run would race its
        own predecessor for the port.
        """
        deadline = time.time() + self.PORT_RELEASE_TIMEOUT
        while time.time() < deadline:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
                probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                try:
                    probe.bind((self.host, self.port))
                    return
                except OSError:
                    time.sleep(0.1)
        print(f'Warning: port {self.port} still in use after stopping the server')

    def _wait_for_server(self, timeout: int | None = None):
        """Wait for the server to be ready to accept connections."""
        timeout = timeout or TestConfig.TEST_TIMEOUT
        start_time = time.time()

        while time.time() - start_time < timeout:
            try:
                response = requests.get(f'{self.base_url}/', timeout=5)
                if response.status_code in [
                    200,
                    404,
                ]:  # 404 is fine, means server is up
                    return
            except requests.exceptions.RequestException:
                pass
            time.sleep(0.5)

        error_message = f'Server did not start within {timeout} seconds'

        # If server didn't start, capture the output for debugging
        if self.process and self.process.poll() is not None:
            stdout, stderr = self.process.communicate()
            error_message += f'\n\nServer stdout: {stdout}'
            error_message += f'\n\nServer stderr: {stderr}'

        raise RuntimeError(error_message)


@pytest.fixture(scope='session')
def backend_server(request):
    """Fixture to start and stop the backend server for e2e tests only."""
    # Check if any of the selected tests have the 'e2e' marker
    if not any(item.get_closest_marker('e2e') for item in request.session.items):
        # No e2e tests selected, skip server startup
        yield None
        return

    server = BackendServer()
    print(f'Starting server on {server.host}:{server.port}')
    server.start()
    yield server
    print(f'Stopping server on {server.host}:{server.port}')
    server.stop()


@pytest.fixture(autouse=True)
def setup_page(request, backend_server):
    """Give every e2e test's page the same timeouts.

    The page is asked for through ``request`` rather than taken as an
    argument: this fixture runs for every test, and naming ``page`` would
    have each of them open a browser context.
    """
    if not backend_server:
        return None

    page = request.getfixturevalue('page')
    page.set_default_timeout(15000)
    page.set_default_navigation_timeout(10000)
    return page


@pytest.fixture(scope='session')
def lan_context(browser: Browser):
    config = SharlyChessConfig()
    config.web_port = 9000
    context = browser.new_context(base_url=config.lan_urls[0])
    yield context
    context.close()


@pytest.fixture(scope='function')
def lan_page(lan_context):
    page = lan_context.new_page()
    page.set_default_timeout(15000)
    page.set_default_navigation_timeout(10000)
    yield page
    # Spawned tabs must not keep polling after the test.
    for open_page in list(lan_context.pages):
        if not open_page.is_closed():
            open_page.close()


@pytest.fixture(scope='session')
def api_request_context(
    playwright: Playwright,
) -> Generator[APIRequestContext, None, None]:
    request_context = playwright.request.new_context(base_url='http://127.0.0.1:9000')
    yield request_context
    request_context.dispose()
