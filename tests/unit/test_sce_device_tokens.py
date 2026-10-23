"""Sharly-Chess.com tokens belong to the computer they were issued to.

A copied event file carries the refresh token of another computer. Refreshing
it would have Sharly-Chess.com see the same token used twice and revoke it on
both computers, so the copy asks to be connected on its own instead.
"""

from datetime import datetime, timedelta
from unittest import TestCase
from unittest.mock import MagicMock, patch

import pytest

from common.computer_identity import computer_identity
from common.exception import SharlyChessException
from data.loader import EventLoader
from database.sqlite.event.event_database import EventDatabase
from plugins.sce import PLUGIN_NAME
from plugins.sce.sce_data import SCEEventPluginData, SCETokens
from plugins.sce.sce_session import SCESession
from plugins.sce.utils import SCEUtils
from tests.test_config import TestUtils

EVENT_UNIQ_ID = 'test-sce-device-tokens'
OTHER_DEVICE_ID = 'f' * 32


def tokens(device_id: str | None, expired: bool = False) -> SCETokens:
    return SCETokens(
        access_token='ACCESS',
        refresh_token='REFRESH',
        expires_at=datetime.now() + timedelta(hours=-1 if expired else 1),
        device_id=device_id,
    )


def token_response() -> MagicMock:
    response = MagicMock()
    response.status_code = 200
    response.json.return_value = {
        'access_token': 'NEW-ACCESS',
        'refresh_token': 'NEW-REFRESH',
        'expires_in': 3600,
    }
    return response


def ok_response() -> MagicMock:
    response = MagicMock()
    response.status_code = 200
    return response


@pytest.mark.unit
class TestTokensStorage(TestCase):
    def test_device_id_round_trips(self) -> None:
        plugin_data = SCEEventPluginData(id='E', tokens=tokens('abc'))

        loaded = SCEEventPluginData.from_stored_value(plugin_data.to_stored_value())

        assert loaded.tokens is not None
        assert loaded.tokens.device_id == 'abc'

    def test_tokens_stored_before_devices_have_none(self) -> None:
        stored = SCEEventPluginData(id='E', tokens=tokens('abc')).to_stored_value()
        del stored['tokens']['device_id']

        loaded = SCEEventPluginData.from_stored_value(stored)

        assert loaded.tokens is not None
        assert loaded.tokens.device_id is None


@pytest.mark.unit
class TestTokensOfDevice(TestCase):
    def setUp(self) -> None:
        super().setUp()
        TestUtils.create_event(EVENT_UNIQ_ID)

    def tearDown(self) -> None:
        TestUtils.delete_event(EVENT_UNIQ_ID)
        super().tearDown()

    @staticmethod
    def install_tokens(event_tokens: SCETokens | None) -> SCESession:
        plugin_data = SCEEventPluginData(id='SCE-EVT', tokens=event_tokens)
        with EventDatabase(EVENT_UNIQ_ID, write=True) as database:
            stored_event = database.load_stored_event()
            stored_event.plugin_data[PLUGIN_NAME] = plugin_data.to_stored_value()
            database.update_stored_event(stored_event)
        return SCESession(EventLoader().load_event(EVENT_UNIQ_ID))

    @staticmethod
    def stored_tokens() -> SCETokens | None:
        event = EventLoader().load_event(EVENT_UNIQ_ID)
        return SCEUtils.get_event_plugin_data(event).tokens

    def test_tokens_of_this_device_are_used(self) -> None:
        session = self.install_tokens(tokens(computer_identity().device_id))
        request = MagicMock(return_value=ok_response())

        session._run_with_token_validation(request)

        request.assert_called_once()
        stored = self.stored_tokens()
        assert stored is not None
        assert stored.refresh_token == 'REFRESH'
        assert stored.device_id == computer_identity().device_id

    def test_tokens_without_device_are_adopted(self) -> None:
        session = self.install_tokens(tokens(None))
        request = MagicMock(return_value=ok_response())

        session._run_with_token_validation(request)

        request.assert_called_once()
        stored = self.stored_tokens()
        assert stored is not None
        assert stored.device_id == computer_identity().device_id
        assert stored.refresh_token == 'REFRESH'

    def test_tokens_of_another_device_are_discarded(self) -> None:
        session = self.install_tokens(tokens(OTHER_DEVICE_ID))
        request = MagicMock(return_value=ok_response())

        with pytest.raises(SharlyChessException):
            session._run_with_token_validation(request)

        request.assert_not_called()
        assert self.stored_tokens() is None

    def test_expired_tokens_of_another_device_are_never_refreshed(self) -> None:
        session = self.install_tokens(tokens(OTHER_DEVICE_ID, expired=True))
        request = MagicMock(return_value=ok_response())

        with (
            patch('plugins.sce.sce_session.requests.post') as post,
            pytest.raises(SharlyChessException),
        ):
            session._run_with_token_validation(request)

        post.assert_not_called()
        request.assert_not_called()
        assert self.stored_tokens() is None

    def test_expired_tokens_of_this_device_are_refreshed_for_it(self) -> None:
        session = self.install_tokens(tokens(computer_identity().device_id, True))
        request = MagicMock(return_value=ok_response())

        with patch(
            'plugins.sce.sce_session.requests.post', return_value=token_response()
        ) as post:
            session._run_with_token_validation(request)

        post.assert_called_once()
        request.assert_called_once()
        stored = self.stored_tokens()
        assert stored is not None
        assert stored.refresh_token == 'NEW-REFRESH'
        assert stored.device_id == computer_identity().device_id

    def test_refreshed_tokens_belong_to_this_device(self) -> None:
        session = self.install_tokens(tokens(None, expired=True))

        with patch(
            'plugins.sce.sce_session.requests.post', return_value=token_response()
        ):
            session.refresh_tokens(force=True)

        stored = self.stored_tokens()
        assert stored is not None
        assert stored.device_id == computer_identity().device_id

    def test_tokens_from_authorisation_belong_to_this_device(self) -> None:
        with patch(
            'plugins.sce.sce_session.requests.post', return_value=token_response()
        ):
            new_tokens = SCESession.get_tokens_from_code('CODE', 'VERIFIER', 'URI')

        assert new_tokens.device_id == computer_identity().device_id

    def test_sync_of_a_copied_event_asks_for_authorisation(self) -> None:
        from plugins.sce import sce_background_synchronizer
        from plugins.sce.sce_sync_status import AuthFailureSCESyncStatus

        self.install_tokens(tokens(OTHER_DEVICE_ID))

        with (
            patch(
                'plugins.sce.sce_background_synchronizer.NetworkMonitor.connected',
                return_value=True,
            ),
            patch('plugins.sce.sce_background_synchronizer.time.sleep'),
            patch.object(sce_background_synchronizer, '_publish_upload_event'),
            patch('plugins.sce.sce_session.requests.post') as post,
            patch('plugins.sce.sce_session.requests.get') as get,
        ):
            sce_background_synchronizer.sync_event(EVENT_UNIQ_ID)

        post.assert_not_called()
        get.assert_not_called()
        event = EventLoader().load_event(EVENT_UNIQ_ID)
        plugin_data = SCEUtils.get_event_plugin_data(event)
        assert plugin_data.tokens is None
        assert plugin_data.last_sync_attempt_status == AuthFailureSCESyncStatus().id
