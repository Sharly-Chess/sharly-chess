"""Acceleration rules across the first attribution of pairing numbers.

A custom acceleration rule addresses players by pairing number, and the
numbers are only handed out when they are first needed — at the first
pairing. Everyone is unnumbered until then, so the arbiter writes the
rule against a numbering that does not exist yet. This checks the rule
survives that moment: it used to be shifted once per player, marching a
rule for numbers 1-2 clear off the end of the field.
"""

import pytest

from data.loader import EventLoader
from database.sqlite.event.event_database import EventDatabase
from database.sqlite.event.event_store import StoredPlayer, StoredTournamentPlayer
from plugins.pairing_acceleration.pairing_settings import (
    AccelerationRule,
    CustomAccelerationSetting,
)
from tests.test_config import TestUtils

EVENT_ID = 'test-acceleration-pairing-numbers'
TOURNAMENT_NAME = 'tournament'
PLAYER_COUNT = 8


@pytest.mark.unit
class TestRuleAcrossFirstNumbering:
    @pytest.fixture
    def tournament(self):
        TestUtils.create_event(EVENT_ID)
        TestUtils.create_tournament(
            EVENT_ID,
            TOURNAMENT_NAME,
            overrides={'rounds': 5, 'pairing': 'pairing_acceleration-SWISS_CUSTOM'},
        )
        with EventDatabase(EVENT_ID, write=True) as database:
            tournament_id = next(
                stored.id
                for stored in database.load_stored_tournaments()
                if stored.name == TOURNAMENT_NAME
            )
            assert tournament_id is not None
            for index in range(PLAYER_COUNT):
                player_id = database.add_stored_player(
                    StoredPlayer(
                        id=None,
                        last_name=f'PLAYER{index:02d}',
                        first_name='Test',
                        # Descending rating, so the starting rank is
                        # the order they were added.
                        ratings={1: {'standard': 2000 - index * 10}},
                    )
                )
                database.add_stored_tournament_player(
                    StoredTournamentPlayer(
                        tournament_id=tournament_id,
                        player_id=player_id,
                    )
                )
        event = EventLoader().load_event(EVENT_ID)
        yield event.tournaments_by_name[TOURNAMENT_NAME]
        TestUtils.delete_event(EVENT_ID)

    @pytest.mark.parametrize('number_range', [(1, 2), (None, 2)])
    def test_the_rule_still_addresses_the_players_it_named(
        self, tournament, number_range
    ):
        """Both spellings of "the top two": the explicit range, and the
        one that leaves the start open."""
        rule = AccelerationRule(
            vpoints=1.0, first_round=1, last_round=3, number_range=number_range
        )
        tournament.stored_tournament.pairing_settings[
            CustomAccelerationSetting.static_id()
        ] = CustomAccelerationSetting.to_stored_value([rule])

        # Reading this is what hands out the pairing numbers.
        by_number = tournament.tournament_players_by_pairing_number
        assert sorted(by_number) == list(range(1, PLAYER_COUNT + 1))

        stored = CustomAccelerationSetting.get_value(tournament)
        assert stored[0].number_range == number_range, 'the rule was shifted'

        variation = tournament.pairing_variation
        accelerated = [
            number
            for number in range(1, PLAYER_COUNT + 1)
            if variation.compute_virtual_points(
                tournament, by_number[number], at_round=1
            )
        ]
        assert accelerated == [1, 2]
