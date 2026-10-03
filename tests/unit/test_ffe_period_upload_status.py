"""A slice answers for its own submission.

Each tranche is submitted under its own registration, so what is known
of one — whether it has been sent, and how it went — is the slice's own
and never the tournament's.
"""

import contextlib
from datetime import datetime, timedelta

import pytest

from data.loader import EventLoader
from database.sqlite.event.event_database import EventDatabase
from plugins.ffe.ffe_background_uploader import FfeBackgroundUploader
from plugins.ffe.utils import FFEUtils
from tests.test_config import TestUtils

EVENT_ID = 'test-ffe-period-status'
TOURNAMENT_NAME = 'tournament'


@pytest.mark.unit
class TestPeriodUploadStatus:
    def teardown_method(self):
        FfeBackgroundUploader.ongoing_period_result_ids.clear()
        FfeBackgroundUploader.pending_period_result_ids.clear()
        FfeBackgroundUploader.group_upload_wait_queue.clear()
        TestUtils.delete_event(EVENT_ID)

    def _setup(self, second_period_plugin_data: dict | None = None):
        TestUtils.create_event(EVENT_ID)
        TestUtils.create_tournament(
            EVENT_ID,
            TOURNAMENT_NAME,
            overrides={
                'rounds': 4,
                'multi_period': True,
                'round_datetimes': {
                    round_nb: datetime.now() + timedelta(days=14 * (round_nb - 4))
                    for round_nb in range(1, 5)
                },
                # The tournament has been uploaded; its slices have not.
                'plugin_data': {
                    'ffe': {
                        'ffe_id': 49943,
                        'password': 'AAAAAAAAAA',
                        'last_upload': datetime.now().isoformat(),
                    }
                },
            },
        )
        with EventDatabase(EVENT_ID, write=True) as database:
            tournament_id = next(
                stored.id
                for stored in database.load_stored_tournaments()
                if stored.name == TOURNAMENT_NAME
            )
            assert tournament_id is not None
            database.set_tournament_periods(tournament_id, [3])
            if second_period_plugin_data is not None:
                second = database.load_tournament_stored_periods(tournament_id)[1]
                assert second.id is not None
                database.set_tournament_period_plugin_data(
                    second.id, {'ffe': second_period_plugin_data}
                )
        with contextlib.suppress(KeyError):
            EventLoader.unload_event(EVENT_ID)
        self._event = EventLoader().load_event(EVENT_ID)
        return self._event.tournaments_by_name[TOURNAMENT_NAME]

    def test_a_slice_with_no_registration_is_not_reported_as_uploaded(self):
        """It borrows the tournament's registration to upload with, but
        never its upload: the tournament's file is not this slice's."""
        tournament = self._setup()
        statuses = FFEUtils.resolve_period_upload_statuses(tournament.periods[1])
        assert [status.id for status in statuses] == ['NOT_CONFIGURED']

    def test_a_slice_never_sent_says_so(self):
        tournament = self._setup({'ffe_id': 49944, 'password': 'BBBBBBBBBB'})
        statuses = FFEUtils.resolve_period_upload_statuses(tournament.periods[1])
        assert 'NEVER' in [status.id for status in statuses]

    def test_a_slice_that_was_sent_says_when(self):
        tournament = self._setup(
            {
                'ffe_id': 49944,
                'password': 'BBBBBBBBBB',
                'last_upload': datetime.now().isoformat(),
            }
        )
        statuses = FFEUtils.resolve_period_upload_statuses(tournament.periods[1])
        assert 'NEVER' not in [status.id for status in statuses]

    def _registered(self):
        return self._setup({'ffe_id': 49944, 'password': 'BBBBBBBBBB'})

    def test_the_slice_being_sent_says_so(self):
        tournament = self._registered()
        period = tournament.periods[1]
        FfeBackgroundUploader.ongoing_period_result_ids.add(
            FfeBackgroundUploader.period_result_id(period)
        )
        statuses = FFEUtils.resolve_period_upload_statuses(period)
        assert 'ONGOING' in [status.id for status in statuses]

    def test_a_slice_waiting_for_its_turn_says_so(self):
        """The whole tournament is published first, and the slice being
        played follows it in the same run."""
        tournament = self._registered()
        period = tournament.periods[1]
        FfeBackgroundUploader.pending_period_result_ids.add(
            FfeBackgroundUploader.period_result_id(period)
        )
        statuses = [
            status.id for status in FFEUtils.resolve_period_upload_statuses(period)
        ]
        assert 'PENDING' in statuses
        assert 'ONGOING' not in statuses

    def test_the_slice_being_played_waits_on_a_queued_upload(self):
        tournament = self._registered()
        FfeBackgroundUploader.group_upload_wait_queue.add(
            FfeBackgroundUploader.tournament_result_id(tournament)
        )
        statuses = FFEUtils.resolve_period_upload_statuses(tournament.periods[1])
        assert 'PENDING' in [status.id for status in statuses]
