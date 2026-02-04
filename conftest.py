"""pytest configuration with Playwright setup and backend server management."""

import os
import shutil
import subprocess
import sys
import time
from io import TextIOWrapper
from pathlib import Path
from typing import Generator, Iterator

import pytest
import requests
from litestar import Litestar
from litestar.contrib.jinja import JinjaTemplateEngine
from litestar.template import TemplateConfig
from litestar.testing import TestClient
from playwright.sync_api import Browser, Playwright, APIRequestContext

from common import BASE_DIR
from common.i18n import gettext, ngettext
from common.sharly_chess_config import SharlyChessConfig
from tests.integration.test_event_documents_controller import session_config
from tests.test_config import TestConfig
from utils.file import shutil_delete_onerror
from web.controllers.admin.account_admin_controller import AccountAdminController
from web.controllers.admin.display_controller_admin_controller import (
    DisplayControllerAdminController,
)
from web.controllers.admin.event_admin_controller import EventAdminController
from web.controllers.admin.event_documents_controller import EventDocumentsController
from web.controllers.admin.family_admin_controller import FamilyAdminController
from web.controllers.admin.index_admin_controller import IndexAdminController
from web.controllers.admin.pairings_admin_controller import PairingsAdminController
from web.controllers.admin.player_admin_controller import PlayerAdminController
from web.controllers.admin.prize_admin_controller import PrizeAdminController
from web.controllers.admin.prize_config_admin_controller import (
    PrizeConfigAdminController,
)
from web.controllers.admin.rotator_admin_controller import RotatorAdminController
from web.controllers.admin.screen_admin_controller import ScreenAdminController
from web.controllers.admin.screen_config_admin_controller import (
    ScreenConfigAdminController,
)
from web.controllers.admin.timer_admin_controller import TimerAdminController
from web.controllers.admin.tournament_admin_controller import TournamentAdminController
from web.controllers.background_controller import BackgroundController
from web.controllers.index_controller import IndexController
from web.controllers.profile_controller import ProfileController
from web.controllers.qrcode_controller import QRCodeController
from web.controllers.user.screen_user_controller import ScreenUserController
from web.controllers.user.tournament_user_controller import (
    ResultUserController,
    CheckInUserController,
    IllegalMoveUserController,
)

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
        'integration: mark test as integration test requiring Litestar app with basic config '
        '(runs on commit, pull request and release)',
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
            str(TestConfig.TEST_DATA_DIR.resolve()),
        ]

        # Create log file for server output - use unique name to avoid conflicts
        import time

        data_dir = TestConfig.TEST_DATA_DIR.resolve()
        log_file = data_dir / f'server_{int(time.time())}.log'

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


@pytest.fixture(autouse=True, scope='session')
def set_working_dir(request):
    """Set the working directory and prepare the data directory."""
    data_dir = TestConfig.TEST_DATA_DIR.resolve()
    data_dir.mkdir(parents=True, exist_ok=True)

    # Remove contents
    for item in data_dir.iterdir():
        if item.is_file() or item.is_symlink():
            item.unlink()
        elif item.is_dir():
            shutil.rmtree(item, onerror=shutil_delete_onerror)

    os.chdir(TestConfig.TEST_DATA_DIR.resolve())
    return


@pytest.fixture(scope='session')
def backend_server(request, set_working_dir):
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
    return page


@pytest.fixture(scope='session')
def api_request_context(
    playwright: Playwright,
) -> Generator[APIRequestContext, None, None]:
    request_context = playwright.request.new_context(base_url='http://127.0.0.1:9000')
    yield request_context
    request_context.dispose()


# Integration tests fixtures


@pytest.fixture(scope='session')
def test_client() -> Iterator[TestClient[Litestar]]:
    template_dirs: list[Path] = [
        BASE_DIR / 'src/web/templates',
        BASE_DIR / 'src/web/templates/admin/print',
        BASE_DIR / 'src/web/static',
    ]

    jinja_template_engine = JinjaTemplateEngine(template_dirs)
    jinja_template_engine.engine.add_extension('jinja2.ext.i18n')
    jinja_template_engine.engine.install_gettext_callables(
        gettext=gettext, ngettext=ngettext, newstyle=True
    )
    jinja_template_engine.engine.add_extension('jinja2.ext.do')
    template_config: TemplateConfig = TemplateConfig(engine=jinja_template_engine)
    app = Litestar(
        route_handlers=[
            IndexController,
            BackgroundController,
            ScreenUserController,
            ResultUserController,
            CheckInUserController,
            IllegalMoveUserController,
            IndexAdminController,
            EventAdminController,
            EventDocumentsController,
            TournamentAdminController,
            PairingsAdminController,
            PrizeConfigAdminController,
            PrizeAdminController,
            ScreenConfigAdminController,
            ScreenAdminController,
            TimerAdminController,
            FamilyAdminController,
            RotatorAdminController,
            PlayerAdminController,
            DisplayControllerAdminController,
            QRCodeController,
            AccountAdminController,
            ProfileController,
        ],
        middleware=[session_config.middleware],
        template_config=template_config,
        debug=True,
    )
    with TestClient(app=app, session_config=session_config) as client:
        yield client
