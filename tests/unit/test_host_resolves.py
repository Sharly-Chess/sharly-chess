"""A host that does not resolve in a few seconds counts as unreachable, so that
a request to Sharly-Chess.com fails fast instead of waiting for the system
DNS resolver to give up."""

import socket
import time
from datetime import datetime, timedelta
from typing import Any
from unittest import TestCase
from unittest.mock import MagicMock, patch

import pytest

from common.computer_identity import computer_identity
from common.exception import SharlyChessException
from common.network import host_resolves
from data.loader import EventLoader
from database.sqlite.event.event_database import EventDatabase
from plugins.sce import PLUGIN_NAME
from plugins.sce.sce_data import SCEEventPluginData, SCETokens
from plugins.sce.sce_event_status import NotReachableSCEEventStatus
from plugins.sce.sce_session import SCESession
from plugins.sce.utils import SCEUtils
from tests.test_config import TestUtils

EVENT_UNIQ_ID = 'test-host-resolves'


def hanging_lookup(*_args: Any, **_kwargs: Any) -> Any:
    time.sleep(2)
    raise socket.gaierror('timed out')


@pytest.mark.unit
class TestHostResolves(TestCase):
    def test_resolving_host(self) -> None:
        assert host_resolves('http://localhost:8080/path')

    def test_failing_lookup(self) -> None:
        with patch(
            'common.network.socket.getaddrinfo', side_effect=socket.gaierror('no')
        ):
            assert not host_resolves('https://example.invalid')

    def test_hanging_lookup_gives_up_at_timeout(self) -> None:
        with patch('common.network.socket.getaddrinfo', side_effect=hanging_lookup):
            start = time.monotonic()
            assert not host_resolves('https://example.invalid', timeout=0.2)
            assert time.monotonic() - start < 1

    def test_url_without_host(self) -> None:
        assert not host_resolves('not a url')


@pytest.mark.unit
class TestSCEUnresolvedHost(TestCase):
    def setUp(self) -> None:
        super().setUp()
        TestUtils.create_event(EVENT_UNIQ_ID)
        plugin_data = SCEEventPluginData(
            id='SCE-EVT',
            tokens=SCETokens(
                access_token='ACCESS',
                refresh_token='REFRESH',
                expires_at=datetime.now() - timedelta(hours=1),
                device_id=computer_identity().device_id,
            ),
        )
        with EventDatabase(EVENT_UNIQ_ID, write=True) as database:
            stored_event = database.load_stored_event()
            stored_event.plugin_data[PLUGIN_NAME] = plugin_data.to_stored_value()
            database.update_stored_event(stored_event)

    def tearDown(self) -> None:
        TestUtils.delete_event(EVENT_UNIQ_ID)
        super().tearDown()

    def test_request_fails_without_contacting_the_server(self) -> None:
        session = SCESession(EventLoader().load_event(EVENT_UNIQ_ID))
        request = MagicMock()
        with (
            patch('plugins.sce.sce_session.host_resolves', return_value=False),
            patch('plugins.sce.sce_session.requests.post') as post,
            pytest.raises(SharlyChessException),
        ):
            session._run_with_token_validation(request)

        post.assert_not_called()
        request.assert_not_called()
        event = EventLoader().load_event(EVENT_UNIQ_ID)
        assert (
            SCEUtils.get_event_plugin_data(event).status
            == NotReachableSCEEventStatus().id
        )

    def test_authorization_fails_without_contacting_the_server(self) -> None:
        with (
            patch('plugins.sce.sce_session.host_resolves', return_value=False),
            patch('plugins.sce.sce_session.requests.post') as post,
            pytest.raises(SharlyChessException),
        ):
            SCESession.get_tokens_from_code('CODE', 'VERIFIER', 'http://localhost')

        post.assert_not_called()
