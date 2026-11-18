"""The uploads of a tournament to the FFE website run one at a time, what
changes while one is running is sent by the next one, and a failed upload
is tried again."""

import contextlib
import time
from datetime import datetime, timedelta
from threading import Lock, Thread, current_thread

import pytest

from common.network import NetworkMonitor
from data.loader import EventLoader
from database.sqlite.event.event_database import EventDatabase
from plugins.ffe.ffe_background_uploader import FfeBackgroundUploader
from plugins.ffe.ffe_session import FFE_REQUEST_TIMEOUT, FFESession
from plugins.ffe.ffe_upload_status import (
    AuthFailureFFEUploadStatus,
    NotReachableFFEUploadStatus,
)
from plugins.ffe.utils import FFEUtils
from tests.test_config import TestUtils

EVENT_ID = 'test-ffe-upload-concurrency'
TOURNAMENT_NAME = 'tournament'


@pytest.mark.unit
class TestUploadConcurrency:
    @pytest.fixture(autouse=True)
    def _no_channels(self, monkeypatch):
        monkeypatch.setattr(
            FfeBackgroundUploader,
            'publish_upload_event',
            classmethod(lambda cls, start=False: None),
        )

    def teardown_method(self):
        FfeBackgroundUploader.ongoing_result_ids.clear()
        FfeBackgroundUploader.group_upload_wait_queue.clear()
        FfeBackgroundUploader.sending_threads.clear()
        for timer in FfeBackgroundUploader.timeout_threads.values():
            cancel = getattr(timer, 'cancel', None)
            if cancel:
                cancel()
        FfeBackgroundUploader.timeout_threads.clear()
        with contextlib.suppress(FileNotFoundError):
            TestUtils.delete_event(EVENT_ID)

    def _setup(self) -> int:
        TestUtils.create_event(EVENT_ID)
        TestUtils.create_tournament(
            EVENT_ID,
            TOURNAMENT_NAME,
            overrides={
                'plugin_data': {
                    'ffe': {
                        'ffe_id': 49943,
                        'password': 'AAAAAAAAAA',
                        'last_upload': (
                            datetime.now() - timedelta(hours=1)
                        ).isoformat(),
                    }
                },
            },
        )
        with contextlib.suppress(KeyError):
            EventLoader.unload_event(EVENT_ID)
        tournament = (
            EventLoader().load_event(EVENT_ID).tournaments_by_name[TOURNAMENT_NAME]
        )
        return tournament.id

    @staticmethod
    def _stored_tournament(tournament_id: int):
        with EventDatabase(EVENT_ID) as database:
            stored_tournament = database.get_stored_tournament(tournament_id)
        assert stored_tournament is not None
        return stored_tournament

    @staticmethod
    def _touch_tournament(tournament_id: int) -> None:
        with EventDatabase(EVENT_ID, write=True) as database:
            database.execute(
                'UPDATE `tournament` SET `last_update` = ? WHERE `id` = ?',
                (EventDatabase.now_as_database_timestamp(), tournament_id),
            )

    def _upload_with(self, monkeypatch, upload) -> None:
        monkeypatch.setattr(
            NetworkMonitor, 'connected', classmethod(lambda cls, use_cached=True: True)
        )
        monkeypatch.setattr(
            FFEUtils,
            'ffe_actions_unavailable_message',
            classmethod(lambda cls, tournament: None),
        )
        monkeypatch.setattr(FFESession, 'upload', upload)

    def test_uploads_of_a_tournament_run_one_after_the_other(self, monkeypatch):
        running = 0
        most_running = 0
        calls = 0
        counter_lock = Lock()

        def fake_upload(*_args) -> None:
            nonlocal running, most_running, calls
            with counter_lock:
                running += 1
                calls += 1
                most_running = max(most_running, running)
            time.sleep(0.2)
            with counter_lock:
                running -= 1

        monkeypatch.setattr(FfeBackgroundUploader, '_upload_tournament', fake_upload)
        threads = [
            Thread(target=FfeBackgroundUploader.upload_tournament, args=(EVENT_ID, 1))
            for _ in range(3)
        ]
        for thread in threads:
            thread.start()
        time.sleep(0.1)
        assert (
            FfeBackgroundUploader.result_id(EVENT_ID, 1)
            in FfeBackgroundUploader.group_upload_wait_queue
        )
        for thread in threads:
            thread.join()
        assert calls == 3
        assert most_running == 1

    def test_a_change_during_an_upload_is_still_to_be_sent(self, monkeypatch):
        tournament_id = self._setup()

        def upload_during_a_change(_session, _set_visible):
            time.sleep(0.01)
            self._touch_tournament(tournament_id)

        self._upload_with(monkeypatch, upload_during_a_change)
        FfeBackgroundUploader.upload_tournament(EVENT_ID, tournament_id)
        assert FfeBackgroundUploader.ffe_upload_needed(
            self._stored_tournament(tournament_id)
        )

    def test_an_upload_without_change_leaves_the_tournament_up_to_date(
        self, monkeypatch
    ):
        tournament_id = self._setup()
        self._upload_with(monkeypatch, lambda _session, _set_visible: None)
        FfeBackgroundUploader.upload_tournament(EVENT_ID, tournament_id)
        assert not FfeBackgroundUploader.ffe_upload_needed(
            self._stored_tournament(tournament_id)
        )

    def test_a_change_during_an_automatic_upload_schedules_the_next_one(self):
        tournament_id = self._setup()
        with EventDatabase(EVENT_ID) as database:
            stored_event = database.load_stored_event()
        stored_tournament = self._stored_tournament(tournament_id)
        result_id = FfeBackgroundUploader.result_id(EVENT_ID, tournament_id)
        FfeBackgroundUploader.timeout_threads[result_id] = current_thread()  # type: ignore[assignment]
        assert not FfeBackgroundUploader.should_schedule_tournament_upload(
            stored_event, stored_tournament
        )
        FfeBackgroundUploader.sending_threads[result_id] = current_thread()
        assert FfeBackgroundUploader.should_schedule_tournament_upload(
            stored_event, stored_tournament
        )

    def _retry(self, tournament_id: int):
        return FfeBackgroundUploader.timeout_threads.get(
            FfeBackgroundUploader.result_id(EVENT_ID, tournament_id)
        )

    def test_a_failed_upload_is_tried_again(self, monkeypatch):
        tournament_id = self._setup()
        self._upload_with(
            monkeypatch, lambda _session, _set_visible: NotReachableFFEUploadStatus()
        )
        FfeBackgroundUploader.upload_tournament(EVENT_ID, tournament_id)
        retry = self._retry(tournament_id)
        assert retry is not None
        assert retry.interval == 60
        assert retry.kwargs['attempt'] == 1

    def test_the_attempts_end_after_the_last_retry(self, monkeypatch):
        tournament_id = self._setup()
        self._upload_with(
            monkeypatch, lambda _session, _set_visible: NotReachableFFEUploadStatus()
        )
        FfeBackgroundUploader.upload_tournament(EVENT_ID, tournament_id, attempt=3)
        assert self._retry(tournament_id) is None

    def test_a_refused_login_is_not_tried_again(self, monkeypatch):
        tournament_id = self._setup()
        self._upload_with(
            monkeypatch, lambda _session, _set_visible: AuthFailureFFEUploadStatus()
        )
        FfeBackgroundUploader.upload_tournament(EVENT_ID, tournament_id)
        assert self._retry(tournament_id) is None

    def test_requests_to_the_ffe_website_time_out(self, monkeypatch):
        timeouts = []

        class Response:
            content = b''

        def fake_request(_session, _url, **kwargs):
            timeouts.append(kwargs.get('timeout'))
            return Response()

        monkeypatch.setattr(FFESession, 'get', fake_request)
        monkeypatch.setattr(FFESession, 'post', fake_request)
        session = FFESession(None)
        session._read_url('http://example.invalid', None, None)
        session._read_url('http://example.invalid', {'field': 'value'}, None)
        assert timeouts == [FFE_REQUEST_TIMEOUT, FFE_REQUEST_TIMEOUT]

    def test_an_upload_asked_for_while_one_waits_its_turn_is_not_added(
        self, monkeypatch
    ):
        monkeypatch.setattr(
            FfeBackgroundUploader,
            'upload_tournament',
            classmethod(lambda cls, *args, **kwargs: None),
        )
        tournament_id = self._setup()
        event = EventLoader().load_event(EVENT_ID)
        tournament = event.tournaments_by_id[tournament_id]
        result_id = FfeBackgroundUploader.result_id(EVENT_ID, tournament_id)
        FfeBackgroundUploader.group_upload_wait_queue.add(result_id)
        FfeBackgroundUploader.schedule_upload(tournament, force=True)
        assert self._retry(tournament_id) is None
        FfeBackgroundUploader.group_upload_wait_queue.discard(result_id)
        FfeBackgroundUploader.schedule_upload(tournament, force=True)
        assert self._retry(tournament_id) is not None
