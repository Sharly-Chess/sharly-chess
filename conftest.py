"""pytest configuration with Playwright setup and backend server management."""

import os
import subprocess
import sys
import time
from io import TextIOWrapper
from pathlib import Path
from typing import Generator

import pytest
import requests
from playwright.sync_api import Browser, Playwright, APIRequestContext

from common import TEST_DATA_DIR
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
            str(TEST_DATA_DIR),
        ]

        # Create log file for server output - use unique name to avoid conflicts
        import time

        log_file = TEST_DATA_DIR / f'server_{int(time.time())}.log'

        # Keep reference to log file handle so we can close it later
        self.log_file_handle = open(log_file, 'w')

        self.process = subprocess.Popen(
            cmd,
            stdout=self.log_file_handle,  # Log to file instead of pipe
            stderr=subprocess.STDOUT,  # Combine stderr with stdout
            text=True,
            env=env,
            cwd=Path(__file__).parent,  # Ensure we're in the right directory
        )

        # Wait for server to be ready
        self._wait_for_server()

    def stop(self):
        """Stop the backend server."""
        if self.process:
            self.process.terminate()
            try:
                self.process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait()

        # Close log file handle if it exists
        if self.log_file_handle:
            self.log_file_handle.close()

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
def setup_page(page, backend_server):
    if not backend_server:
        return None

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
    # Close this page and any tabs it spawned (e.g. target="_blank" screen
    # views). The context is session-scoped, so a page left open keeps
    # auto-refreshing its screen and hits the event the next test tears down,
    # causing flaky 500 / SQLite errors.
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
