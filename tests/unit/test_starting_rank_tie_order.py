"""The order of the players with the same rating and title in the starting
rank: alphabetical, or by drawing of lots."""

import pytest

from data.loader import EventLoader
from database.sqlite.event.event_database import EventDatabase
from database.sqlite.event.event_store import StoredPlayer, StoredTournamentPlayer
from tests.test_config import TestUtils
from utils.enum import StartingRankTieOrder

EVENT_ID = 'test-starting-rank-tie-order'
TOURNAMENT_NAME = 'tournament'
# Registered in reverse alphabetical order.
LAST_NAMES = ['HOTEL', 'GOLF', 'FOXTROT', 'ECHO', 'DELTA', 'CHARLIE', 'BRAVO', 'ALPHA']


def _starting_rank(
    order: StartingRankTieOrder,
    seed: int | None = None,
    pairing: str = 'SWISS_STANDARD',
) -> list[str]:
    TestUtils.create_event(EVENT_ID)
    try:
        TestUtils.create_tournament(
            EVENT_ID,
            TOURNAMENT_NAME,
            overrides={
                'rounds': 5,
                'pairing': pairing,
                'starting_rank_tie_order': order.value,
                'starting_rank_lot_seed': seed,
            },
        )
        with EventDatabase(EVENT_ID, write=True) as database:
            tournament_id = next(
                stored.id
                for stored in database.load_stored_tournaments()
                if stored.name == TOURNAMENT_NAME
            )
            assert tournament_id is not None
            for last_name in LAST_NAMES:
                player_id = database.add_stored_player(
                    StoredPlayer(
                        id=None,
                        last_name=last_name,
                        first_name='Test',
                        ratings={1: {'standard': 2000}},
                    )
                )
                database.add_stored_tournament_player(
                    StoredTournamentPlayer(
                        tournament_id=tournament_id, player_id=player_id
                    )
                )
        event = EventLoader().load_event(EVENT_ID)
        tournament = event.tournaments_by_name[TOURNAMENT_NAME]
        return [
            player.stored_player.last_name
            for player in tournament.tournament_players_by_pairing_number.values()
        ]
    finally:
        TestUtils.delete_event(EVENT_ID)


@pytest.mark.unit
class TestStartingRankTieOrder:
    def test_alphabetical(self):
        assert _starting_rank(StartingRankTieOrder.ALPHABETICAL) == sorted(LAST_NAMES)

    def test_lots_hold_for_a_seed(self):
        assert _starting_rank(StartingRankTieOrder.LOTS, 1) == _starting_rank(
            StartingRankTieOrder.LOTS, 1
        )

    def test_lots_change_with_the_seed(self):
        draws = {
            tuple(_starting_rank(StartingRankTieOrder.LOTS, seed))
            for seed in range(1, 5)
        }
        assert len(draws) > 1
        assert all(sorted(draw) == sorted(LAST_NAMES) for draw in draws)

    def test_alphabetical_outside_the_swiss(self):
        assert _starting_rank(
            StartingRankTieOrder.LOTS, 1, pairing='ROUND_ROBIN_BERGER'
        ) == sorted(LAST_NAMES)
