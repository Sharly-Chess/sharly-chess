"""Rating periods cut a long tournament into the slices FIDE rates.

A tournament of more than 30 days is reported one slice at a time, each
slice starting at a round the arbiter marks. A tournament that is not
marked as long has the single period covering every round, so the read
paths have one shape whatever the length of the tournament.
"""

import contextlib
from datetime import datetime, timedelta

import pytest

from data.loader import EventLoader
from data.tournament_period import period_first_rounds, period_spans
from database.sqlite.event.event_database import EventDatabase
from tests.test_config import TestUtils

EVENT_ID = 'test-tournament-periods'
TOURNAMENT_NAME = 'tournament'


@pytest.mark.unit
class TestPeriodBoundaries:
    """The boundary helpers the form and the stored periods share."""

    def test_round_one_always_starts_a_period(self):
        assert period_first_rounds([], rounds=7) == [1]

    def test_marked_rounds_become_boundaries(self):
        assert period_first_rounds([3, 6], rounds=7) == [1, 3, 6]

    def test_a_mark_past_the_last_round_is_dropped(self):
        assert period_first_rounds([3, 9], rounds=7) == [1, 3]

    def test_periods_run_to_the_round_before_the_next(self):
        spans = period_spans([1, 3, 6], rounds=7, round_datetimes={})
        assert [(span.first_round, span.last_round) for span in spans] == [
            (1, 2),
            (3, 5),
            (6, 7),
        ]

    def test_a_period_takes_its_dates_from_its_rounds(self):
        spans = period_spans(
            [1, 3],
            rounds=4,
            round_datetimes={
                1: datetime(2026, 11, 14, 14),
                2: datetime(2026, 11, 28, 14),
                3: datetime(2027, 1, 9, 14),
                4: datetime(2027, 1, 23, 14),
            },
        )
        assert (spans[0].start_date, spans[0].stop_date) == (
            datetime(2026, 11, 14).date(),
            datetime(2026, 11, 28).date(),
        )
        assert spans[0].days == 15
        assert not spans[0].too_long
        assert spans[1].days == 15

    def test_a_period_of_more_than_thirty_days_is_flagged(self):
        spans = period_spans(
            [1],
            rounds=2,
            round_datetimes={
                1: datetime(2026, 11, 14, 14),
                2: datetime(2026, 12, 20, 14),
            },
        )
        assert spans[0].days == 37
        assert spans[0].too_long

    def test_a_too_long_period_names_the_round_to_split_before(self):
        """The round that takes the period past 30 days, not the one it
        starts at — that is where the arbiter has to cut."""
        spans = period_spans(
            [1],
            rounds=4,
            round_datetimes={
                1: datetime(2026, 11, 14, 14),
                2: datetime(2026, 11, 28, 14),
                3: datetime(2026, 12, 20, 14),
                4: datetime(2027, 1, 9, 14),
            },
        )
        assert spans[0].overflow_round == 3

    def test_a_period_within_the_limit_has_no_such_round(self):
        spans = period_spans(
            [1],
            rounds=2,
            round_datetimes={
                1: datetime(2026, 11, 14, 14),
                2: datetime(2026, 11, 28, 14),
            },
        )
        assert spans[0].overflow_round is None

    def test_a_period_without_dates_has_no_span(self):
        spans = period_spans([1], rounds=2, round_datetimes={})
        assert spans[0].days is None
        assert not spans[0].too_long


@pytest.mark.unit
class TestTournamentPeriods:
    def teardown_method(self):
        TestUtils.delete_event(EVENT_ID)

    def _tournament(self, multi_period: bool, first_rounds: list[int]):
        TestUtils.create_event(EVENT_ID)
        TestUtils.create_tournament(
            EVENT_ID,
            TOURNAMENT_NAME,
            overrides={
                'rounds': 7,
                'multi_period': multi_period,
                'round_datetimes': {
                    round_nb: datetime(2026, 11, 1, 14)
                    + timedelta(days=7 * (round_nb - 1))
                    for round_nb in range(1, 8)
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
            database.set_tournament_periods(tournament_id, first_rounds)
        with contextlib.suppress(KeyError):
            EventLoader.unload_event(EVENT_ID)
        # Held on to: a tournament keeps only a weak reference to its event.
        self._event = EventLoader().load_event(EVENT_ID)
        return self._event.tournaments_by_name[TOURNAMENT_NAME]

    def test_a_short_tournament_has_one_period_over_every_round(self):
        tournament = self._tournament(multi_period=False, first_rounds=[])
        assert len(tournament.periods) == 1
        period = tournament.periods[0]
        assert period.first_round == 1
        assert period.last_round == tournament.rounds
        assert tournament.period_by_round[4] is period

    def test_boundaries_are_ignored_until_the_tournament_is_marked_long(self):
        """The rows survive the switch being turned off, so turning it
        back on restores the cut the arbiter had made."""
        tournament = self._tournament(multi_period=False, first_rounds=[3, 6])
        assert len(tournament.periods) == 1

    def test_a_long_tournament_is_cut_at_the_marked_rounds(self):
        tournament = self._tournament(multi_period=True, first_rounds=[3, 6])
        assert [
            (period.first_round, period.last_round) for period in tournament.periods
        ] == [(1, 2), (3, 5), (6, 7)]
        assert tournament.period_by_round[5] is tournament.periods[1]

    def test_only_a_round_opening_a_period_calls_for_a_rating_update(self):
        """The ratings of a slice are set when it opens, so that is the
        one round at which the arbiter is reminded of it — not every
        round of a long tournament."""
        tournament = self._tournament(multi_period=True, first_rounds=[3, 6])
        assert [
            round_nb
            for round_nb in range(1, tournament.rounds + 1)
            if tournament.round_starts_period(round_nb)
        ] == [1, 3, 6]

    def test_a_tournament_rated_in_one_go_never_calls_for_one(self):
        tournament = self._tournament(multi_period=False, first_rounds=[])
        assert not any(
            tournament.round_starts_period(round_nb)
            for round_nb in range(1, tournament.rounds + 1)
        )

    def test_a_period_knows_the_month_of_the_list_it_is_played_on(self):
        """A slice is rated on the list in force when it starts, whatever
        month it ends in."""
        tournament = self._tournament(multi_period=True, first_rounds=[5])
        second = tournament.periods[1]
        assert second.start_date == datetime(2026, 11, 29).date()
        assert second.stop_date == datetime(2026, 12, 13).date()
        assert second.rating_month == datetime(2026, 11, 1).date()

    def test_a_slice_keeps_its_ratings_when_its_boundary_moves(self):
        """Moving a cut re-bounds the slice rather than replacing it, so
        what its players were prepared with — and what a report of it was
        built from — survives the edit."""
        tournament = self._tournament(multi_period=True, first_rounds=[3, 6])
        assert tournament.id is not None
        period_ids = [period.id for period in tournament.periods]
        with EventDatabase(EVENT_ID, write=True) as database:
            database.set_tournament_periods(tournament.id, [4, 6])
            kept = database.load_tournament_stored_periods(tournament.id)
        assert [stored.first_round for stored in kept] == [1, 4, 6]
        assert [stored.id for stored in kept] == period_ids

    def test_boundaries_that_cross_do_not_collide(self):
        """A slice moved onto the round another is leaving passes it on
        the way; the rows are rewritten so neither is lost."""
        tournament = self._tournament(multi_period=True, first_rounds=[3, 4])
        assert tournament.id is not None
        with EventDatabase(EVENT_ID, write=True) as database:
            database.set_tournament_periods(tournament.id, [4, 5])
            kept = database.load_tournament_stored_periods(tournament.id)
        assert [stored.first_round for stored in kept] == [1, 4, 5]

    def test_an_earlier_boundary_can_be_removed(self):
        """Merging the second slice into the first leaves the later ones
        where they are."""
        tournament = self._tournament(multi_period=True, first_rounds=[3, 6])
        assert tournament.id is not None
        with EventDatabase(EVENT_ID, write=True) as database:
            database.set_tournament_periods(tournament.id, [6])
            kept = database.load_tournament_stored_periods(tournament.id)
        assert [stored.first_round for stored in kept] == [1, 6]

    def test_a_merged_slice_loses_its_row(self):
        tournament = self._tournament(multi_period=True, first_rounds=[3, 6])
        assert tournament.id is not None
        with EventDatabase(EVENT_ID, write=True) as database:
            database.set_tournament_periods(tournament.id, [3])
            kept = database.load_tournament_stored_periods(tournament.id)
        assert [stored.first_round for stored in kept] == [1, 3]

    def test_periods_are_seeded_for_a_new_tournament(self):
        TestUtils.create_event(EVENT_ID)
        TestUtils.create_tournament(EVENT_ID, TOURNAMENT_NAME)
        with EventDatabase(EVENT_ID) as database:
            tournament_id = next(
                stored.id
                for stored in database.load_stored_tournaments()
                if stored.name == TOURNAMENT_NAME
            )
            assert tournament_id is not None
            stored_periods = database.load_tournament_stored_periods(tournament_id)
        assert [stored.first_round for stored in stored_periods] == [1]
