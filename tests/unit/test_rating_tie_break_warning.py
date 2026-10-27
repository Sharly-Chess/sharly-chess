"""The warning a tie-break that rests on a rating carries.

FIDE C.07:10 does not recommend such a tie-break in a tournament where a
player may hold more than one rating, and a tie-break says so on its own
row — whichever class it is built on, a plugin's re-implementation of a
FIDE one included.
"""

from datetime import datetime, timedelta

import pytest

from data.loader import EventLoader
from data.tie_breaks.tie_breaks import (
    AverageRatingOpponentsTieBreak,
    WinsTieBreak,
)
from plugins.ffe.ffe_tie_breaks import (
    LowestOwnAverageRatingTieBreak,
    PapiKashdanTieBreak,
    PapiPerformanceTieBreak,
)
from tests.test_config import TestUtils

EVENT_ID = 'test-rating-tie-break-warning'
TOURNAMENT_NAME = 'tournament'
WARNING = 'lasting over multiple FIDE periods'


def _build(days: int):
    """A tournament whose rounds span *days*, so that one over 30 holds
    more than one rating per player. The event comes back with it — it is
    held weakly and goes if nothing keeps it."""
    TestUtils.create_event(EVENT_ID)
    TestUtils.create_tournament(
        EVENT_ID,
        TOURNAMENT_NAME,
        overrides={
            'rounds': 2,
            'start_date': datetime.now().date(),
            'stop_date': (datetime.now() + timedelta(days=days)).date(),
            'round_datetimes': {
                1: datetime.now(),
                2: datetime.now() + timedelta(days=days),
            },
        },
    )
    EventLoader.unload_event(EVENT_ID)
    event = EventLoader().load_event(EVENT_ID)
    return event, event.tournaments_by_name[TOURNAMENT_NAME]


@pytest.mark.unit
class TestRatingTieBreakWarning:
    def _tournament(self, days: int):
        self._event, tournament = _build(days)
        return tournament

    def teardown_method(self):
        EventLoader.unload_event(EVENT_ID)
        TestUtils.delete_event(EVENT_ID)

    def test_a_fide_rating_tie_break_is_warned_about(self):
        tournament = self._tournament(days=45)
        warning = AverageRatingOpponentsTieBreak().get_warning_for_tournament(
            tournament
        )
        assert warning is not None and WARNING in warning

    def test_a_plugin_rating_tie_break_is_warned_about(self):
        """The Papi performance is a re-implementation of the FIDE one and
        rests on ratings just as much."""
        tournament = self._tournament(days=45)
        warning = PapiPerformanceTieBreak().get_warning_for_tournament(tournament)
        assert warning is not None and WARNING in warning

    def test_a_rating_tie_break_grouped_elsewhere_is_warned_about(self):
        tournament = self._tournament(days=45)
        warning = LowestOwnAverageRatingTieBreak().get_warning_for_tournament(
            tournament
        )
        assert warning is not None and WARNING in warning

    def test_tie_breaks_that_read_no_rating_are_left_alone(self):
        tournament = self._tournament(days=45)
        assert WinsTieBreak().get_warning_for_tournament(tournament) is None
        assert PapiKashdanTieBreak().get_warning_for_tournament(tournament) is None

    def test_a_short_tournament_is_left_alone(self):
        tournament = self._tournament(days=7)
        assert (
            AverageRatingOpponentsTieBreak().get_warning_for_tournament(tournament)
            is None
        )
