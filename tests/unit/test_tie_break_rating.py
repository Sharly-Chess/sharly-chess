"""Which rating a rating-based tie-break reads in a split tournament.

A player may hold a different rating in each slice, so FIDE C.07:10
leaves the choice to the arbiter and takes the first rating by default.
The others are the rating of each game's own slice, and the rating of a
slice the arbiter names.
"""

import contextlib
from datetime import datetime, timedelta

import pytest

from data.loader import EventLoader
from data.tournament_period import TIE_BREAK_RATING_BY_ROUND
from database.sqlite.event.event_database import EventDatabase
from database.sqlite.event.event_store import (
    StoredPlayer,
    StoredPlayerPeriod,
    StoredTournamentPlayer,
)
from tests.test_config import TestUtils
from utils.enum import TournamentRating

EVENT_ID = 'test-tie-break-rating'
TOURNAMENT_NAME = 'tournament'
# The opponent's rating in each of the three slices.
SLICE_RATINGS = [1500, 1600, 1700]


@pytest.mark.unit
class TestTieBreakRating:
    def teardown_method(self):
        TestUtils.delete_event(EVENT_ID)

    def _setup(self, multi_period: bool = True):
        """Four rounds a fortnight apart, cut at rounds 2 and 4, so each
        slice holds one or two rounds and the opponent a rating of its
        own."""
        TestUtils.create_event(EVENT_ID)
        TestUtils.create_tournament(
            EVENT_ID,
            TOURNAMENT_NAME,
            overrides={
                'rounds': 4,
                'multi_period': multi_period,
                'round_datetimes': {
                    round_nb: datetime.now() + timedelta(days=14 * (round_nb - 4))
                    for round_nb in range(1, 5)
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
            player_ids = []
            for name in ('PLAYER', 'OPPONENT'):
                player_id = database.add_stored_player(
                    StoredPlayer(
                        id=None,
                        last_name=name,
                        ratings={
                            TournamentRating.STANDARD.value: {'fide': SLICE_RATINGS[0]}
                        },
                    )
                )
                database.add_stored_tournament_player(
                    StoredTournamentPlayer(
                        tournament_id=tournament_id, player_id=player_id
                    )
                )
                player_ids.append(player_id)
            database.set_tournament_periods(tournament_id, [2, 4])
            periods = database.load_tournament_stored_periods(tournament_id)
            for stored_period, rating in zip(
                periods[1:], SLICE_RATINGS[1:], strict=True
            ):
                assert stored_period.id is not None
                database.set_player_period(
                    player_ids[1],
                    stored_period.id,
                    StoredPlayerPeriod(
                        ratings={TournamentRating.STANDARD.value: {'fide': rating}}
                    ),
                )
        return self._load()

    def _load(self):
        with contextlib.suppress(KeyError):
            EventLoader.unload_event(EVENT_ID)
        self._event = EventLoader().load_event(EVENT_ID)
        self._tournament = self._event.tournaments_by_name[TOURNAMENT_NAME]
        return self._tournament

    def _opponent(self):
        return next(
            tournament_player
            for tournament_player in self._tournament.tournament_players
            if tournament_player.last_name == 'OPPONENT'
        )

    def _ratings_read(self) -> list[int]:
        opponent = self._opponent()
        return [opponent.tie_break_rating(round_nb) for round_nb in range(1, 5)]

    def test_the_first_rating_is_read_by_default(self):
        """C.07:10's default: one rating for the whole tournament."""
        self._setup()
        assert self._tournament.tie_break_rating == ''
        assert self._ratings_read() == [1500, 1500, 1500, 1500]

    def test_each_game_can_be_read_at_its_own_slice(self):
        tournament = self._setup()
        tournament.set_tie_break_rating(TIE_BREAK_RATING_BY_ROUND)
        assert self._ratings_read() == [1500, 1600, 1600, 1700]

    def test_a_named_slice_is_read_for_every_game(self):
        tournament = self._setup()
        period = tournament.periods[2]
        tournament.set_tie_break_rating(str(period.id))
        assert self._ratings_read() == [1700, 1700, 1700, 1700]

    def test_a_round_reads_the_rating_it_was_played_at(self):
        """What a pairing sheet and a result screen show for a round is
        the rating that round was played at, whatever slice the
        tournament has since reached."""
        self._setup()
        opponent = self._opponent()
        assert [opponent.rating_in_round(round_nb) for round_nb in range(1, 5)] == [
            1500,
            1600,
            1600,
            1700,
        ]
        assert opponent.rating_str_in_round(1).startswith('1500')

    def test_a_tournament_rated_in_one_go_reads_one_rating_throughout(self):
        tournament = self._setup(multi_period=False)
        opponent = self._opponent()
        assert tournament.tie_break_period(2) is None
        assert [opponent.rating_in_round(round_nb) for round_nb in range(1, 5)] == [
            1500,
            1500,
            1500,
            1500,
        ]

    def test_a_tournament_rated_in_one_go_offers_no_choice(self):
        """One slice, one rating: there is nothing for C.07:10 to leave to
        the arbiter, whatever the setting says."""
        tournament = self._setup(multi_period=False)
        tournament.set_tie_break_rating(TIE_BREAK_RATING_BY_ROUND)
        assert tournament.tie_break_period(2) is None
        assert self._ratings_read() == [1500, 1500, 1500, 1500]
