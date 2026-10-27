"""Reading an event while it is being written.

An event is read by a series of queries. Without a transaction each of
them sees the file as it stands at that moment, so a write committed in
between is read half way: the event then holds rows pointing at records
it has not read, and building it raises.
"""

import contextlib
import threading
import time
from unittest import TestCase

import pytest

from data.loader import EventLoader
from data.tournament import Tournament
from database.sqlite.event.event_database import EventDatabase
from database.sqlite.event.event_store import StoredPlayer, StoredTournamentPlayer
from tests.test_config import TestUtils

EVENT_ID = 'test-event-load-snapshot'
TOURNAMENT_NAME = 'tournament'
PLAYERS = 3


@pytest.mark.unit
class EventLoadSnapshotTestCase(TestCase):
    def setUp(self) -> None:
        TestUtils.create_event(EVENT_ID)
        stored_tournament = TestUtils.create_tournament(EVENT_ID, TOURNAMENT_NAME)
        self.tournament_id = stored_tournament.id
        assert self.tournament_id is not None
        with EventDatabase(EVENT_ID, write=True) as database:
            for index in range(PLAYERS):
                self._add_player(database, f'Player{index}')

    def tearDown(self) -> None:
        TestUtils.delete_event(EVENT_ID)

    def _add_player(self, database: EventDatabase, name: str) -> int:
        player_id = database.add_stored_player(
            StoredPlayer(id=None, last_name=name, check_in=True)
        )
        database.add_stored_tournament_player(
            StoredTournamentPlayer(
                tournament_id=self.tournament_id, player_id=player_id
            )
        )
        return player_id

    def _load(self) -> Tournament:
        with contextlib.suppress(KeyError):
            EventLoader.unload_event(EVENT_ID)
        # A Tournament holds its event weakly, so the event has to
        # outlive this call.
        self._event = EventLoader().load_event(EVENT_ID)
        return self._event.tournaments_by_name[TOURNAMENT_NAME]

    def test_a_write_committed_during_a_read_is_not_read_half_way(self) -> None:
        """The players and the tournament entries are read by two
        queries: both see the event as it stood when the read began."""
        # The read starts first, so the write can only land between its
        # two queries — the case this guards against.
        reading = threading.Event()

        def add_player() -> None:
            reading.wait(5)
            with EventDatabase(EVENT_ID, write=True) as database:
                self._add_player(database, 'Late')

        writer = threading.Thread(target=add_player)
        writer.start()
        try:
            with EventDatabase(EVENT_ID) as database:
                players = database.load_stored_players()
                reading.set()
                # Long enough for the write to land, were it able to.
                time.sleep(0.5)
                tournaments = database.load_stored_tournaments()
        finally:
            writer.join(10)
        entered = tournaments[0].stored_tournament_players
        self.assertEqual(len(players), PLAYERS)
        self.assertEqual(len(entered), PLAYERS)
        self.assertTrue(
            {entry.player_id for entry in entered} <= {player.id for player in players}
        )
        # The write lands once the read is over.
        with EventDatabase(EVENT_ID) as database:
            self.assertEqual(len(database.load_stored_players()), PLAYERS + 1)

    def test_a_player_entered_but_not_in_the_event_is_left_out(self) -> None:
        """Belt and braces: an entry pointing at a player the event does
        not hold is dropped rather than raised on."""
        tournament = self._load()
        stored_players = tournament.event.stored_event.stored_players
        missing = stored_players.pop().id
        self.assertEqual(len(tournament.tournament_players), PLAYERS - 1)
        self.assertNotIn(missing, {player.id for player in tournament.players})
