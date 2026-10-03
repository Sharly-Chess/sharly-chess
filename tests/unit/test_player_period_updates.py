"""Refreshing ratings prepares the slice being played.

A tournament reported in slices is rated slice by slice, so an update
taken from a player database records what the current slice will be
reported with — the earlier ones keep what they were reported with,
whatever day the database is from.
"""

import contextlib
from datetime import datetime, timedelta

import pytest

from data.input_output.data_source import PlayerComparator
from data.input_output.player_updater_fields import StandardRatingUpdaterField
from data.loader import EventLoader
from database.sqlite.event.event_database import EventDatabase
from database.sqlite.event.event_store import (
    StoredPlayer,
    StoredPlayerPeriod,
    StoredTournamentPlayer,
)
from tests.test_config import TestUtils
from utils.enum import TournamentRating

EVENT_ID = 'test-player-period-updates'
TOURNAMENT_NAME = 'tournament'
PLAYER_NAME = 'PLAYER'
FIRST_RATING = 1500
PERIOD_RATING = 1540
DATABASE_RATING = 1585


@pytest.mark.unit
class TestRatingUpdates:
    def teardown_method(self):
        TestUtils.delete_event(EVENT_ID)

    def _setup(self, multi_period: bool):
        """Six rounds a fortnight apart, the last one played today, cut
        at rounds 3 and 5 — so the third slice is the current one."""
        TestUtils.create_event(EVENT_ID)
        TestUtils.create_tournament(
            EVENT_ID,
            TOURNAMENT_NAME,
            overrides={
                'rounds': 6,
                'multi_period': multi_period,
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
            player_id = database.add_stored_player(
                StoredPlayer(
                    id=None,
                    last_name=PLAYER_NAME,
                    ratings={TournamentRating.STANDARD.value: {'fide': FIRST_RATING}},
                )
            )
            database.add_stored_tournament_player(
                StoredTournamentPlayer(tournament_id=tournament_id, player_id=player_id)
            )
            database.set_tournament_periods(tournament_id, [3, 5])
            if multi_period:
                second_period = database.load_tournament_stored_periods(tournament_id)[
                    1
                ]
                assert second_period.id is not None
                database.set_player_period(
                    player_id,
                    second_period.id,
                    StoredPlayerPeriod(
                        ratings={
                            TournamentRating.STANDARD.value: {'fide': PERIOD_RATING}
                        }
                    ),
                )
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

    def _update(self, player):
        """What the players-update screen does once the arbiter accepts a
        match from a player database."""
        field = StandardRatingUpdaterField()
        comparator = PlayerComparator(
            [field],
            player,
            StoredPlayer(
                id=None,
                last_name=PLAYER_NAME,
                ratings={TournamentRating.STANDARD.value: {'fide': DATABASE_RATING}},
            ),
        )
        assert comparator.diff_field_ids == [field.id]
        updated = comparator.updated_player_from_match([field])
        with EventDatabase(EVENT_ID, write=True) as database:
            database.update_stored_player(updated.stored_player)
        return self._load()

    def _fide(self, player, period_index: int) -> int | None:
        period = self._tournament.periods[period_index]
        return player.ratings_for(period)[TournamentRating.STANDARD].fide

    def test_the_update_lands_on_the_slice_being_played(self):
        player = self._setup(multi_period=True)
        assert self._tournament.current_period is self._tournament.periods[2]
        player = self._update(player)
        assert self._fide(player, 2) == DATABASE_RATING

    def test_the_earlier_slices_keep_what_they_were_reported_with(self):
        player = self._setup(multi_period=True)
        player = self._update(player)
        assert self._fide(player, 0) == FIRST_RATING
        assert self._fide(player, 1) == PERIOD_RATING

    def test_the_comparison_is_made_against_the_slice_being_played(self):
        """The slice being played inherits the second slice's rating, so
        that — not the player's first rating — is what the database value
        is compared with."""
        player = self._setup(multi_period=True)
        comparator = PlayerComparator(
            [StandardRatingUpdaterField()],
            player,
            StoredPlayer(
                id=None,
                last_name=PLAYER_NAME,
                ratings={TournamentRating.STANDARD.value: {'fide': PERIOD_RATING}},
            ),
        )
        assert comparator.diff_field_ids == []

    def test_a_tournament_rated_in_one_go_updates_the_player(self):
        player = self._setup(multi_period=False)
        player = self._update(player)
        assert player.stored_player.periods == {}
        assert player.ratings[TournamentRating.STANDARD].fide == DATABASE_RATING
