"""The rounds of a team round-robin not paired yet are sent to
Chess-Results as team pairings only, from the Berger tables."""

import contextlib
import os
from unittest import TestCase
from unittest.mock import patch
from xml.etree import ElementTree

import pytest

from data.loader import EventLoader
from data.pairings.engines import TeamRoundRobinPairingEngine
from data.tournament import Tournament
from database.sqlite.event.event_database import EventDatabase
from database.sqlite.event.event_store import (
    StoredPlayer,
    StoredTeam,
    StoredTournamentPlayer,
)
from plugins.chess_results.chess_results_session import ChessResultsSession
from tests.test_config import TestUtils
from utils.enum import EventType

EVENT_ID = 'test-chess-results-team-rr'
TOURNAMENT_NAME = 'rr'
PLAYERS_PER_TEAM = 2
TEAMS = 5  # an odd count: one team has a bye each round


@pytest.mark.unit
class ChessResultsTeamRoundRobinTestCase(TestCase):
    def setUp(self) -> None:
        TestUtils.create_event(EVENT_ID, overrides={'event_type': EventType.TEAM})
        TestUtils.create_tournament(
            EVENT_ID,
            TOURNAMENT_NAME,
            overrides={
                'rounds': TEAMS,
                'team_player_count': PLAYERS_PER_TEAM,
                'pairing': 'TEAM_ROUND_ROBIN_BERGER',
            },
        )
        with EventDatabase(EVENT_ID, write=True) as database:
            tournament_id = next(
                stored_tournament.id
                for stored_tournament in database.load_stored_tournaments()
                if stored_tournament.name == TOURNAMENT_NAME
            )
            assert tournament_id is not None
            for seed in range(1, TEAMS + 1):
                team_id = database.add_stored_team(
                    StoredTeam(
                        id=None,
                        name=f'Team{seed}',
                        tournament_id=tournament_id,
                        pairing_number=seed,
                        check_in=True,
                    )
                )
                for index in range(PLAYERS_PER_TEAM):
                    player_id = database.add_stored_player(
                        StoredPlayer(
                            id=None,
                            last_name=f'T{seed}P{index}',
                            team_id=team_id,
                            team_index=index,
                            check_in=True,
                        )
                    )
                    database.add_stored_tournament_player(
                        StoredTournamentPlayer(
                            tournament_id=tournament_id,
                            player_id=player_id,
                            pairing_number=index,
                        )
                    )

    def tearDown(self) -> None:
        TestUtils.delete_event(EVENT_ID)

    def _load(self, public_view: bool = False) -> Tournament:
        with contextlib.suppress(KeyError):
            EventLoader.unload_event(EVENT_ID)
        self._event = EventLoader().load_event(EVENT_ID, public_view=public_view)
        return self._event.tournaments_by_name[TOURNAMENT_NAME]

    @staticmethod
    def _xml(tournament: Tournament) -> ElementTree.Element:
        # The upload signs its session ids with the AES credentials, which are
        # a deployment secret: any well-formed key and IV will do here.
        credentials = {
            'CHESS_RESULTS_AES_KEY': '00' * 32,
            'CHESS_RESULTS_AES_IV': '00' * 16,
        }
        with patch.dict(os.environ, credentials):
            xml = ChessResultsSession(tournament).build_tournament_xml(
                tournament, 'sid', '1', 'creator', None
            )
        return ElementTree.fromstring(xml)

    def test_the_rounds_not_paired_are_sent_as_team_pairings_only(self) -> None:
        tournament = self._load()
        engine = tournament.pairing_variation.engine
        self.assertEqual(engine.generate_pairings(tournament, 1), '')
        tournament = self._load(public_view=True)
        engine = tournament.pairing_variation.engine
        assert isinstance(engine, TeamRoundRobinPairingEngine)
        schedule = engine.full_schedule(tournament)
        root = self._xml(tournament)

        team_pairings = list(root.iter('teampairing'))
        self.assertEqual(
            {int(pairing.attrib['round']) for pairing in team_pairings},
            set(range(1, TEAMS + 1)),
        )
        for round_ in range(2, TEAMS + 1):
            pairings = [
                pairing
                for pairing in team_pairings
                if pairing.attrib['round'] == str(round_)
            ]
            self.assertEqual(len(pairings), len(schedule[round_]))
            self.assertEqual(
                [pairing.attrib['pairing'] for pairing in pairings],
                [str(number) for number in range(1, len(pairings) + 1)],
            )
            self.assertEqual(pairings[-1].attrib['no2'], '-1')
            self.assertTrue(
                all(
                    pairing.attrib['res1'] == pairing.attrib['res2'] == ''
                    for pairing in pairings
                )
            )
        self.assertEqual(
            {int(pairing.attrib['round']) for pairing in root.iter('playerpairing')},
            {1},
        )
