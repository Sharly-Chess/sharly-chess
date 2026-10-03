"""Pairing numbers follow the ratings the tournament is played on.

FIDE C.04.2.B.3 lets the numbering follow the field until the fourth
round is paired and holds it from there. In a tournament reported in
slices, the ratings it follows are those of the slice being played — a
refresh before a later slice reorders the field exactly as a correction
would, and stops doing so once round 4 is paired.
"""

import contextlib
from datetime import datetime, timedelta

import pytest

from data.loader import EventLoader
from database.sqlite.event.event_database import EventDatabase
from database.sqlite.event.event_store import (
    StoredPlayer,
    StoredPlayerPeriod,
    StoredTournamentPlayer,
)
from tests.test_config import TestUtils
from utils.enum import TournamentRating

EVENT_ID = 'test-period-pairing-numbers'
TOURNAMENT_NAME = 'tournament'
# Two players, the second the stronger of the two in the first slice and
# the weaker of the two in the second.
FIRST_SLICE = {'ALPHA': 1500, 'BETA': 1700}
SECOND_SLICE = {'ALPHA': 1750, 'BETA': 1650}


@pytest.mark.unit
class TestPairingNumbersAcrossSlices:
    def teardown_method(self):
        TestUtils.delete_event(EVENT_ID)

    def _setup(self):
        TestUtils.create_event(EVENT_ID)
        TestUtils.create_tournament(
            EVENT_ID,
            TOURNAMENT_NAME,
            overrides={
                'rounds': 6,
                'multi_period': True,
                'round_datetimes': {
                    round_nb: datetime.now() + timedelta(days=14 * (round_nb - 6))
                    for round_nb in range(1, 7)
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
            database.set_tournament_periods(tournament_id, [4])
            second_period = database.load_tournament_stored_periods(tournament_id)[1]
            assert second_period.id is not None
            for name, rating in FIRST_SLICE.items():
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
                                'fide': SECOND_SLICE[name]
                            }
                        }
                    ),
                )
        return self._load()

    def _load(self):
        with contextlib.suppress(KeyError):
            EventLoader.unload_event(EVENT_ID)
        self._event = EventLoader().load_event(EVENT_ID)
        return self._event.tournaments_by_name[TOURNAMENT_NAME]

    def _numbers(self, tournament) -> dict[str, int | None]:
        tournament.set_tournament_players_pairing_numbers()
        return {
            player.last_name: player.pairing_number
            for player in tournament.tournament_players
        }

    def test_the_numbering_follows_the_slice_being_played(self):
        """The current slice makes ALPHA the higher rated of the two, so
        the numbering puts them first — as it would after any rating
        correction before the fourth round."""
        tournament = self._setup()
        assert tournament.current_period is tournament.periods[1]
        assert self._numbers(tournament) == {'ALPHA': 1, 'BETA': 2}

    def test_the_numbering_holds_once_the_fourth_round_is_paired(self):
        """C.04.2.B.3: no modification of a pairing number after the
        fourth round is paired, whatever a later slice does to the
        ratings."""
        tournament = self._setup()
        numbers = self._numbers(tournament)
        tournament.stored_tournament.current_round = 4
        reloaded = self._load()
        assert reloaded.pairing_system.pairing_numbers_are_frozen(reloaded) is (
            reloaded.current_round >= 4
        )
        assert numbers == {'ALPHA': 1, 'BETA': 2}
