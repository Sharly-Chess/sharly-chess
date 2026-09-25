"""The TRF of one slice of a tournament reported in slices.

A slice's file is a tournament of its own: its rounds numbered from 1,
the players who played them, ranked and rated as they were then, and
points counted from those games alone — as in the submissions FIDE has
accepted (codes 286873 / 286875).
"""

import contextlib
from datetime import datetime, timedelta

import pytest

from data.loader import EventLoader
from database.sqlite.event.event_database import EventDatabase
from database.sqlite.event.event_store import (
    StoredBoard,
    StoredPairing,
    StoredPlayer,
    StoredPlayerPeriod,
    StoredTournamentPlayer,
)
from tests.test_config import TestUtils
from utils.enum import Result, TournamentRating

EVENT_ID = 'test-trf-period-export'
TOURNAMENT_NAME = 'tournament'
PLAYERS = {'ALPHA': 2000, 'BETA': 1900, 'GAMMA': 1800, 'DELTA': 1700}
# BETA overtakes ALPHA between the slices.
LATER_RATINGS = {'ALPHA': 1890, 'BETA': 1950, 'GAMMA': 1810, 'DELTA': 1690}


@pytest.mark.unit
class TestPeriodTrf:
    def teardown_method(self):
        TestUtils.delete_event(EVENT_ID)

    def _setup(self):
        """Four players over four rounds, cut after round 2. Every round
        pairs 1-2 and 3-4, with the higher number winning in the second
        slice so the standings differ from the first."""
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
            database.set_tournament_periods(tournament_id, [3])
            second_period = database.load_tournament_stored_periods(tournament_id)[1]
            assert second_period.id is not None
            player_ids: dict[str, int] = {}
            for name, rating in PLAYERS.items():
                player_id = database.add_stored_player(
                    StoredPlayer(
                        id=None,
                        last_name=name,
                        ratings={TournamentRating.STANDARD.value: {'fide': rating}},
                    )
                )
                database.add_stored_tournament_player(
                    StoredTournamentPlayer(
                        tournament_id=tournament_id, player_id=player_id
                    )
                )
                database.set_player_period(
                    player_id,
                    second_period.id,
                    StoredPlayerPeriod(
                        ratings={
                            TournamentRating.STANDARD.value: {
                                'fide': LATER_RATINGS[name]
                            }
                        }
                    ),
                )
                player_ids[name] = player_id
            for round_nb in range(1, 5):
                for white, black in (('ALPHA', 'BETA'), ('GAMMA', 'DELTA')):
                    board_id = database.add_stored_board(
                        StoredBoard(
                            id=None,
                            white_player_id=player_ids[white],
                            black_player_id=player_ids[black],
                            index=0 if white == 'ALPHA' else 1,
                        )
                    )
                    for name, result in (
                        (white, Result.LOSS),
                        (black, Result.WIN),
                    ):
                        database.add_stored_pairing(
                            StoredPairing(
                                tournament_id=tournament_id,
                                player_id=player_ids[name],
                                round_=round_nb,
                                result=result.value,
                                board_id=board_id,
                            )
                        )
        return self._load()

    def _load(self):
        with contextlib.suppress(KeyError):
            EventLoader.unload_event(EVENT_ID)
        self._event = EventLoader().load_event(EVENT_ID)
        return self._event.tournaments_by_name[TOURNAMENT_NAME]

    def test_the_file_holds_the_slice_s_rounds_numbered_from_one(self):
        tournament = self._setup()
        trf = tournament.to_trf(period=tournament.periods[1])
        assert trf.num_rounds == 2
        assert len(trf.round_dates) == 2
        for player in trf.players:
            assert [game.round for game in player.games] == [1, 2]

    def test_the_points_are_the_slice_s_own(self):
        """Two rounds of two games: whoever won both has 2.0, not the 4.0
        they hold over the whole tournament."""
        tournament = self._setup()
        trf = tournament.to_trf(period=tournament.periods[1])
        assert sorted(player.points for player in trf.players) == [0.0, 0.0, 2.0, 2.0]

    def test_the_ratings_are_those_the_slice_was_played_on(self):
        tournament = self._setup()
        trf = tournament.to_trf(period=tournament.periods[1])
        assert sorted(player.rating for player in trf.players) == sorted(
            LATER_RATINGS.values()
        )

    def test_the_players_are_renumbered_on_the_slice_s_ratings(self):
        """The file is ranked on the ratings it was played on, so BETA
        overtaking ALPHA between the slices reverses their numbers."""
        tournament = self._setup()
        first = tournament.to_trf(period=tournament.periods[0])
        later = tournament.to_trf(period=tournament.periods[1])
        assert [player.name for player in first.players][:2] == ['ALPHA', 'BETA']
        assert [player.name for player in later.players][:2] == ['BETA', 'ALPHA']
        assert [player.id for player in later.players] == [1, 2, 3, 4]

    def test_the_opponents_are_renumbered_with_them(self):
        tournament = self._setup()
        later = tournament.to_trf(period=tournament.periods[1])
        numbers = {player.name: player.id for player in later.players}
        beta = next(player for player in later.players if player.name == 'BETA')
        assert [game.opponent_id for game in beta.games] == [
            numbers['ALPHA'],
            numbers['ALPHA'],
        ]

    def test_the_file_is_named_after_the_rounds_it_holds(self):
        """Two files of one tournament are told apart by their name, as
        the registrations they are submitted under are."""
        tournament = self._setup()
        assert tournament.to_trf(period=tournament.periods[0]).name.endswith(
            'Rounds 1-2'
        )
        assert tournament.to_trf(period=tournament.periods[1]).name.endswith(
            'Rounds 3-4'
        )
        assert tournament.to_trf().name == TOURNAMENT_NAME

    def test_the_whole_tournament_is_still_exported_in_full(self):
        tournament = self._setup()
        trf = tournament.to_trf()
        assert trf.num_rounds == 4
        for player in trf.players:
            assert [game.round for game in player.games] == [1, 2, 3, 4]
