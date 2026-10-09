"""The rating the rating-based tie-breaks give to players without a FIDE
or national rating: their estimated rating by default, or a fixed value
the arbiter chooses."""

import contextlib

import pytest

from common.exception import OptionError
from data.loader import EventLoader
from data.tie_breaks.configuration import TieBreakConfiguration
from data.tie_breaks.options import (
    EstimatedRatingsTieBreakOption,
    UnratedRatingTieBreakOption,
)
from data.tie_breaks.tie_breaks import (
    AverageRatingOpponentsTieBreak,
    AveragePerformanceRatingOpponentsTieBreak,
    PlayerRatingTieBreak,
    TournamentPerformanceRatingTieBreak,
)
from database.sqlite.event.event_database import EventDatabase
from database.sqlite.event.event_store import StoredPlayer, StoredTournamentPlayer
from tests.test_config import TestUtils
from utils.enum import PlayerRatingType, TournamentRating

EVENT_ID = 'test-unrated-rating-option'
TOURNAMENT_NAME = 'tournament'
PLAYERS: dict[str, dict[str, int | None]] = {
    'RATED': {'fide': 1800},
    'ESTIMATED': {'estimated': 1200},
    'UNRATED': {},
}


@pytest.mark.unit
class TestUnratedRatingOption:
    def teardown_method(self):
        TestUtils.delete_event(EVENT_ID)

    def _setup(self, players: dict[str, dict[str, int | None]]):
        TestUtils.create_event(EVENT_ID)
        TestUtils.create_tournament(EVENT_ID, TOURNAMENT_NAME)
        with EventDatabase(EVENT_ID, write=True) as database:
            tournament_id = next(
                stored.id
                for stored in database.load_stored_tournaments()
                if stored.name == TOURNAMENT_NAME
            )
            assert tournament_id is not None
            for name, ratings in players.items():
                player_id = database.add_stored_player(
                    StoredPlayer(
                        id=None,
                        last_name=name,
                        ratings={TournamentRating.STANDARD.value: ratings},
                    )
                )
                database.add_stored_tournament_player(
                    StoredTournamentPlayer(
                        tournament_id=tournament_id, player_id=player_id
                    )
                )
        with contextlib.suppress(KeyError):
            EventLoader.unload_event(EVENT_ID)
        self._event = EventLoader().load_event(EVENT_ID)
        self._tournament = self._event.tournaments_by_name[TOURNAMENT_NAME]

    def _player(self, name: str):
        return next(
            tournament_player
            for tournament_player in self._tournament.tournament_players
            if tournament_player.last_name == name
        )

    def _rtng_values(self, tie_break: PlayerRatingTieBreak) -> dict[str, int]:
        return {
            name: tie_break.compute_player_value(self._player(name), after_round=0)
            for name in PLAYERS
        }

    def test_the_estimated_rating_is_read_by_default(self):
        self._setup(PLAYERS)
        assert self._rtng_values(PlayerRatingTieBreak()) == {
            'RATED': 1800,
            'ESTIMATED': 1200,
            'UNRATED': self._player('UNRATED').rating,
        }

    def test_a_fixed_value_replaces_every_rating_but_a_real_one(self):
        self._setup(PLAYERS)
        tie_break = PlayerRatingTieBreak([UnratedRatingTieBreakOption(1400)])
        assert self._rtng_values(tie_break) == {
            'RATED': 1800,
            'ESTIMATED': 1400,
            'UNRATED': 1400,
        }

    def test_a_fixed_value_is_read_for_opponents(self):
        self._setup(PLAYERS)
        tie_break = AverageRatingOpponentsTieBreak([UnratedRatingTieBreakOption(1400)])
        assert tie_break._tie_break_rating(self._player('ESTIMATED'), 1) == 1400
        assert tie_break._tie_break_rating(self._player('RATED'), 1) == 1800

    def test_unrated_players_disable_the_tie_break_by_default(self):
        self._setup(PLAYERS)
        configuration = TieBreakConfiguration(self._tournament)
        assert configuration.invalid_message(PlayerRatingTieBreak()) is not None

    def test_estimated_players_need_the_rules_to_explain_the_estimation(self):
        self._setup({'RATED': PLAYERS['RATED'], 'ESTIMATED': PLAYERS['ESTIMATED']})
        configuration = TieBreakConfiguration(self._tournament)
        assert configuration.invalid_message(PlayerRatingTieBreak()) is not None
        assert (
            configuration.invalid_message(
                PlayerRatingTieBreak([EstimatedRatingsTieBreakOption(True)])
            )
            is None
        )

    def test_a_fixed_value_also_needs_the_rules_to_state_it(self):
        self._setup(PLAYERS)
        configuration = TieBreakConfiguration(self._tournament)
        tie_break = PlayerRatingTieBreak([UnratedRatingTieBreakOption(1400)])
        message = configuration.invalid_message(tie_break)
        assert message is not None
        assert '1400' in message

    def test_a_fixed_value_stated_in_the_rules_enables_the_tie_break(self):
        self._setup(PLAYERS)
        configuration = TieBreakConfiguration(self._tournament)
        tie_break = PlayerRatingTieBreak(
            [
                UnratedRatingTieBreakOption(1400),
                EstimatedRatingsTieBreakOption(True),
            ]
        )
        assert configuration.invalid_message(tie_break) is None

    @pytest.mark.parametrize('fixed_value', [None, 1400])
    def test_unrated_players_are_warned_about_whatever_rating_they_get(
        self, fixed_value: int | None
    ):
        self._setup(PLAYERS)
        tie_break = PlayerRatingTieBreak([UnratedRatingTieBreakOption(fixed_value)])
        assert tie_break.get_warning_for_tournament(self._tournament) is not None


@pytest.mark.unit
class TestUnratedRatingOptionValue:
    def test_a_fixed_value_replaces_a_rating_of_zero_of_any_type(self):
        """Without an estimate, an unrated player has no rating of the
        tournament's type, which reads as 0 of that type."""
        tie_break = PlayerRatingTieBreak([UnratedRatingTieBreakOption(1400)])
        assert tie_break._rating_value(0, PlayerRatingType.FIDE) == 1400
        assert tie_break._rating_value(1800, PlayerRatingType.FIDE) == 1800

    def test_the_fixed_value_reaches_the_opponents_performances(self):
        tie_break = AveragePerformanceRatingOpponentsTieBreak(
            [UnratedRatingTieBreakOption(1400)]
        )
        inner = tie_break._with_same_unrated_rating(TournamentPerformanceRatingTieBreak)
        assert inner.fixed_unrated_rating == 1400

    @pytest.mark.parametrize(
        'value', [0, -1, UnratedRatingTieBreakOption.MAX_VALUE + 1]
    )
    def test_a_fixed_value_must_be_a_plausible_rating(self, value: int):
        with pytest.raises(OptionError):
            UnratedRatingTieBreakOption(value).validate()

    def test_the_fixed_value_is_named_in_the_full_name(self):
        tie_break = PlayerRatingTieBreak([UnratedRatingTieBreakOption(1400)])
        assert '1400' in tie_break.full_name
        assert tie_break.acronym == PlayerRatingTieBreak().acronym
