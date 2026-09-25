"""A player's rating can change while a long tournament is being played.

A tournament of more than 30 days is reported slice by slice, each rated
on the ratings in force while it was played (FIDE B.01 1.1.4). The
player's stored ratings are the first of them; a slice where they
changed records them against itself.
"""

import contextlib
from datetime import date, datetime, timedelta

import pytest

from data.loader import EventLoader
from database.sqlite.event.event_database import EventDatabase
from database.sqlite.event.event_store import (
    StoredPlayer,
    StoredTournamentPlayer,
)
from tests.test_config import TestUtils
from utils.enum import TournamentRating
from utils.types import PlayerRating

EVENT_ID = 'test-player-period-ratings'
TOURNAMENT_NAME = 'tournament'
PLAYER_NAME = 'PLAYER'


@pytest.mark.unit
class TestMonthRatings:
    def teardown_method(self):
        TestUtils.delete_event(EVENT_ID)

    def _player(self, fide_rating: int = 1500):
        TestUtils.create_event(EVENT_ID)
        TestUtils.create_tournament(
            EVENT_ID,
            TOURNAMENT_NAME,
            overrides={
                'rounds': 6,
                'multi_period': True,
                'start_date': date(2026, 11, 1),
                'stop_date': date(2027, 2, 1),
                'round_datetimes': {
                    round_nb: datetime(2026, 11, 7, 14)
                    + timedelta(days=14 * (round_nb - 1))
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
            player_id = database.add_stored_player(
                StoredPlayer(
                    id=None,
                    last_name=PLAYER_NAME,
                    ratings={
                        TournamentRating.STANDARD.value: {'fide': fide_rating},
                        TournamentRating.RAPID.value: {'fide': 1400},
                        TournamentRating.BLITZ.value: {'national': 1300},
                    },
                )
            )
            database.add_stored_tournament_player(
                StoredTournamentPlayer(tournament_id=tournament_id, player_id=player_id)
            )
            database.set_tournament_periods(tournament_id, [3, 5])
        return self._load()

    def _load(self):
        with contextlib.suppress(KeyError):
            EventLoader.unload_event(EVENT_ID)
        self._event = EventLoader().load_event(EVENT_ID)
        self._tournament = self._event.tournaments_by_name[TOURNAMENT_NAME]
        return next(
            player
            for player in self._event.players_by_id.values()
            if player.last_name == PLAYER_NAME
        )

    def _period(self, index: int):
        return self._tournament.periods[index]

    def _fide(self, player, period) -> int | None:
        return player.ratings_for(period)[TournamentRating.STANDARD].fide

    def test_without_a_recorded_change_every_period_reads_the_same(self):
        player = self._player(fide_rating=1500)
        assert self._fide(player, None) == 1500
        assert self._fide(player, self._period(0)) == 1500
        assert self._fide(player, self._period(2)) == 1500

    def test_a_later_period_takes_the_rating_recorded_for_it(self):
        player = self._player(fide_rating=1500)
        player.update_ratings(
            {TournamentRating.STANDARD: PlayerRating(fide=1560)},
            period=self._period(1),
        )
        assert self._fide(player, self._period(0)) == 1500
        assert self._fide(player, self._period(1)) == 1560

    def test_a_period_keeps_the_last_rating_recorded_before_it(self):
        player = self._player(fide_rating=1500)
        player.update_ratings(
            {TournamentRating.STANDARD: PlayerRating(fide=1560)},
            period=self._period(1),
        )
        assert self._fide(player, self._period(2)) == 1560

    def test_the_first_period_holds_the_player_s_first_rating(self):
        """Updating during the first slice is an ordinary rating update:
        it belongs on the player, not on a slice of its own."""
        player = self._player(fide_rating=1500)
        player.update_ratings(
            {TournamentRating.STANDARD: PlayerRating(fide=1520)},
            period=self._period(0),
        )
        assert player.stored_player.periods == {}
        assert self._fide(player, None) == 1520

    def test_a_period_records_the_whole_of_the_player_s_ratings(self):
        """A slice has to answer for every rating type and its k-factors,
        not only the ones the update happened to carry."""
        player = self._player(fide_rating=1500)
        player.update_ratings(
            {TournamentRating.STANDARD: PlayerRating(fide=1560, k_factor=20)},
            period=self._period(1),
        )
        ratings = player.ratings_for(self._period(1))
        assert ratings[TournamentRating.STANDARD].fide == 1560
        assert ratings[TournamentRating.STANDARD].k_factor == 20
        assert ratings[TournamentRating.RAPID].fide == 1400
        assert ratings[TournamentRating.BLITZ].national == 1300

    def test_recorded_ratings_survive_a_boundary_moving(self):
        """Re-cutting a tournament re-bounds its slices; a slice must not
        lose what its players were prepared with — and what a report of it
        was built from — because the arbiter moved a round."""
        player = self._player(fide_rating=1500)
        player.update_ratings(
            {TournamentRating.STANDARD: PlayerRating(fide=1560)},
            period=self._period(1),
        )
        with EventDatabase(EVENT_ID, write=True) as database:
            database.update_stored_player(player.stored_player)
            assert self._tournament.id is not None
            database.set_tournament_periods(self._tournament.id, [4, 5])
        reloaded = self._load()
        assert self._tournament.periods[1].first_round == 4
        assert self._fide(reloaded, self._period(1)) == 1560

    def test_recorded_periods_survive_a_save(self):
        player = self._player(fide_rating=1500)
        player.update_ratings(
            {TournamentRating.STANDARD: PlayerRating(fide=1560)},
            period=self._period(1),
        )
        with EventDatabase(EVENT_ID, write=True) as database:
            database.update_stored_player(player.stored_player)
        reloaded = self._load()
        assert self._fide(reloaded, self._period(0)) == 1500
        assert self._fide(reloaded, self._period(1)) == 1560
