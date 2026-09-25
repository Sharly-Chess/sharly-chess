"""An opponent is counted as the round they were played in knew them.

FIDE B.01 1.1.4: in tournaments lasting more than 30 days, the
opponents' ratings and titles used are those applying when the games
were played — the exception 1.4.6.1 names to the rule that a norm uses
the list in force at the start.
"""

import contextlib
from datetime import datetime, timedelta

import pytest

from data.loader import EventLoader
from data.norms import NormInputs, NormOpponent, TitleNormEvaluator
from database.sqlite.event.event_database import EventDatabase
from database.sqlite.event.event_store import (
    StoredPlayer,
    StoredPlayerPeriod,
    StoredTournamentPlayer,
)
from tests.test_config import TestUtils
from utils import Utils
from utils.enum import PlayerTitle, TitleNorm, TournamentRating

EVENT_ID = 'test-norm-period-opponents'
TOURNAMENT_NAME = 'tournament'
FIRST_RATING = 2380
LATER_RATING = 2415


@pytest.mark.unit
class TestOpponentInRound:
    def teardown_method(self):
        TestUtils.delete_event(EVENT_ID)

    def _opponent(self):
        """A four-round tournament cut at round 3, whose opponent gains a
        grandmaster title and 35 rating points at the cut."""
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
            },
        )
        with EventDatabase(EVENT_ID, write=True) as database:
            tournament_id = next(
                stored.id
                for stored in database.load_stored_tournaments()
                if stored.name == TOURNAMENT_NAME
            )
            assert tournament_id is not None
            player_id = database.add_stored_player(
                StoredPlayer(
                    id=None,
                    last_name='OPPONENT',
                    title=PlayerTitle.INTERNATIONAL_MASTER.value,
                    ratings={TournamentRating.STANDARD.value: {'fide': FIRST_RATING}},
                )
            )
            database.add_stored_tournament_player(
                StoredTournamentPlayer(tournament_id=tournament_id, player_id=player_id)
            )
            database.set_tournament_periods(tournament_id, [3])
            second_period = database.load_tournament_stored_periods(tournament_id)[1]
            assert second_period.id is not None
            database.set_player_period(
                player_id,
                second_period.id,
                StoredPlayerPeriod(
                    ratings={TournamentRating.STANDARD.value: {'fide': LATER_RATING}},
                    title=PlayerTitle.GRANDMASTER.value,
                ),
            )
        with contextlib.suppress(KeyError):
            EventLoader.unload_event(EVENT_ID)
        self._event = EventLoader().load_event(EVENT_ID)
        tournament = self._event.tournaments_by_name[TOURNAMENT_NAME]
        return next(iter(tournament.tournament_players))

    def test_a_game_in_the_first_slice_counts_the_earlier_rating_and_title(self):
        opponent = NormOpponent.in_round(self._opponent(), 1)
        assert opponent.rating == FIRST_RATING
        assert opponent.held_titles == frozenset({PlayerTitle.INTERNATIONAL_MASTER})
        assert opponent.display_title == 'IM'

    def test_a_game_in_the_later_slice_counts_what_was_held_then(self):
        opponent = NormOpponent.in_round(self._opponent(), 4)
        assert opponent.rating == LATER_RATING
        assert opponent.held_titles == frozenset({PlayerTitle.GRANDMASTER})
        assert opponent.display_title == 'GM'

    def test_the_average_rating_counts_each_game_at_its_own_slice(self):
        """1.4.6 averages the opponents of the games counted, and 1.1.4
        fixes each of those at the slice its game was played in — so
        meeting one opponent on either side of a cut averages the two
        ratings they held."""
        tournament_player = self._opponent()
        inputs = NormInputs(
            played_games=2,
            opponents=[
                NormOpponent.in_round(tournament_player, 1),
                NormOpponent.in_round(tournament_player, 4),
            ],
            included_rounds=[1, 4],
        )
        evaluator = TitleNormEvaluator(tournament_player)
        average, adjusted, adjusted_rating = (
            evaluator.opponent_rating_floor_and_average(inputs, TitleNorm.GM)
        )
        assert average == Utils.round_ranking((FIRST_RATING + LATER_RATING) / 2)
        # Both are well above the GM floor of 2200, so nothing is raised.
        assert adjusted is None and adjusted_rating is None

    def test_everything_else_is_read_from_the_player(self):
        """Federation, identity and the opponent's own schedule do not
        belong to a slice: 1.1.4 names ratings and titles alone."""
        tournament_player = self._opponent()
        opponent = NormOpponent.in_round(tournament_player, 1)
        assert opponent.id == tournament_player.id
        assert opponent.federation == tournament_player.federation
        assert opponent.full_name == tournament_player.full_name
        assert opponent.pairings_by_round is tournament_player.pairings_by_round
