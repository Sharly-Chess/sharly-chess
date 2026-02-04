from pathlib import Path
from typing import Iterator

import pytest
from litestar import Litestar
from litestar.contrib.jinja import JinjaTemplateEngine
from litestar.middleware.session.server_side import ServerSideSessionConfig
from litestar.template import TemplateConfig
from litestar.testing import TestClient
from requests import Response

from common import BASE_DIR
from common.i18n import gettext, ngettext
from data.account import Account
from data.event import Event
from data.loader import EventLoader
from data.tournament import Tournament
from tests.test_config import TestUtils
from web.controllers.admin.event_admin_controller import EventAdminController
from web.controllers.admin.event_documents_controller import EventDocumentsController

session_config = ServerSideSessionConfig()

EVENT_ID = 'test-documents-event'
TOURNAMENT_NAME = 'test-documents-tournament'


@pytest.fixture(scope='function')
def event() -> Iterator[Event]:
    TestUtils.create_event(EVENT_ID)
    TestUtils.create_tournament(EVENT_ID, TOURNAMENT_NAME, json_file='tec-swiss')
    yield EventLoader().load_event(EVENT_ID)
    TestUtils.delete_event(EVENT_ID)


@pytest.fixture(scope='function')
def tournament(event: Event) -> Iterator[Tournament]:
    yield event.tournaments_by_name[TOURNAMENT_NAME]


@pytest.fixture(scope='function')
def account(event: Event, tournament: Tournament) -> Iterator[Account]:
    yield TestUtils.create_account(
        EVENT_ID, tournament.id, 'admin', overrides={'id': 3}
    )


@pytest.fixture(scope='function')
def test_client(account: Account) -> Iterator[TestClient[Litestar]]:
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
        route_handlers=[EventDocumentsController, EventAdminController],
        middleware=[session_config.middleware],
        template_config=template_config,
        debug=True,
    )
    with TestClient(app=app, session_config=session_config) as client:
        client.set_session_data({'account_id': {EVENT_ID: account.id}})
        yield client


PLAYER_HISTORY_HTML_PATTERN = 'class="player-history"'


@pytest.mark.unit
class TestEventDocumentsController:
    def test_crosstable_document_view_includes_player_histories_when_option_is_on(
        self, test_client: TestClient, event: Event, tournament: Tournament
    ):
        html_response: Response = test_client.get(
            f'/document-view/{EVENT_ID}/crosstable?options=player-history-popover%3Don'
        )

        assert html_response.text.count(PLAYER_HISTORY_HTML_PATTERN) == len(
            tournament.tournament_players
        )

    def test_crosstable_document_view_does_not_include_player_histories_when_option_is_absent(
        self, test_client: TestClient, event: Event, tournament: Tournament
    ):
        html_response: Response = test_client.get(
            f'/document-view/{EVENT_ID}/crosstable'
        )

        assert PLAYER_HISTORY_HTML_PATTERN not in html_response.text
