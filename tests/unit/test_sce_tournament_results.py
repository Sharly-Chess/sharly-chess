"""The tournament results payload uploaded to the SCE platform."""

from contextlib import suppress
from itertools import pairwise
from unittest import TestCase

import pytest

from data.event import Event
from data.loader import EventLoader
from data.tournament import Tournament
from database.sqlite.event.event_database import EventDatabase
from database.sqlite.event.event_store import StoredPlayer, StoredTournamentPlayer
from plugins.sce.sce_tournament_results_builder import build_tournament_results
from tests.test_config import TestUtils
from utils.enum import Result

EVENT_ID = 'test-sce-tournament-results-event'
TOURNAMENT_ID = 'test-sce-tournament-results-tournament'


@pytest.mark.unit
class SCETournamentResultsTestCase(TestCase):
    def setUp(self) -> None:
        TestUtils.create_event(EVENT_ID)
        TestUtils.create_tournament(
            EVENT_ID, TOURNAMENT_ID, json_file='median-buchholz-byes'
        )

    def tearDown(self) -> None:
        TestUtils.delete_event(EVENT_ID)

    def test_requested_byes_are_sent_as_unpaired_rows(self) -> None:
        self._event: Event = EventLoader().load_event(EVENT_ID)
        tournament = self._event.tournaments_by_name[TOURNAMENT_ID]
        payload = build_tournament_results(tournament, 'sce-event', 'sce-tournament')

        expected = {
            (round_, player.pairing_number, pairing.result.value)
            for player in tournament.tournament_players
            for round_, pairing in player.pairings.items()
            if pairing.board is None and pairing.result != Result.NO_RESULT
        }
        self.assertTrue(expected)
        self.assertEqual(
            expected,
            {
                (
                    pairing['round'],
                    pairing['whitePairingNumber'],
                    pairing['whiteResult'],
                )
                for pairing in payload['pairings']
                if pairing['blackPairingNumber'] == -2
            },
        )

    def test_standings_show_the_ranking_criteria_with_the_first_in_bold(self) -> None:
        self._event = EventLoader().load_event(EVENT_ID)
        tournament = self._event.tournaments_by_name[TOURNAMENT_ID]
        payload = build_tournament_results(tournament, 'sce-event', 'sce-tournament')

        columns = payload['tournament']['displayConfig']['rankingColumns']
        keys = [column['key'] for column in columns]
        self.assertNotIn('points', keys)
        tie_break_columns = [
            column for column in columns if column['key'].startswith('tb:')
        ]
        self.assertEqual(
            [f'tb:{i}' for i in range(len(tournament.tie_breaks))],
            [column['key'] for column in tie_break_columns],
        )
        self.assertEqual(
            [True] + [False] * (len(tie_break_columns) - 1),
            [column.get('bold', False) for column in tie_break_columns],
        )

    def test_tied_players_share_a_rank(self) -> None:
        self._event = EventLoader().load_event(EVENT_ID)
        tournament_id = self._event.tournaments_by_name[TOURNAMENT_ID].id
        # Ranked on the points alone, players on the same score are tied.
        with EventDatabase(EVENT_ID, write=True) as database:
            database.delete_all_tournament_stored_tie_breaks(tournament_id)
        EventLoader.unload_event(EVENT_ID)
        self._event = EventLoader().load_event(EVENT_ID)
        tournament = self._event.tournaments_by_name[TOURNAMENT_ID]
        payload = build_tournament_results(tournament, 'sce-event', 'sce-tournament')

        standings = payload['rankings'][0]['standings']
        self.assertEqual(1, standings[0]['rank'])
        for position, (previous, standing) in enumerate(pairwise(standings), start=2):
            if standing['points'] == previous['points']:
                self.assertEqual(previous['rank'], standing['rank'])
            else:
                self.assertEqual(position, standing['rank'])
        self.assertLess(len({s['rank'] for s in standings}), len(standings))


KEIZER_EVENT_ID = 'test-sce-keizer-results-event'
KEIZER_TOURNAMENT_NAME = 'keizer'
KEIZER_PLAYERS = ['P0', 'P1', 'P2', 'P3', 'P4']


@pytest.mark.unit
class SCEKeizerResultsTestCase(TestCase):
    def setUp(self) -> None:
        TestUtils.create_event(KEIZER_EVENT_ID)
        TestUtils.create_tournament(
            KEIZER_EVENT_ID,
            KEIZER_TOURNAMENT_NAME,
            overrides={'rounds': 5, 'current_round': 1, 'pairing': 'KEIZER_STANDARD'},
        )
        with EventDatabase(KEIZER_EVENT_ID, write=True) as database:
            tournament_id = next(
                stored.id
                for stored in database.load_stored_tournaments()
                if stored.name == KEIZER_TOURNAMENT_NAME
            )
            assert tournament_id is not None
            for index, name in enumerate(KEIZER_PLAYERS):
                player_id = database.add_stored_player(
                    StoredPlayer(
                        id=None,
                        last_name=name,
                        ratings={1: {'standard': 2000 - index * 100}},
                        check_in=True,
                    )
                )
                database.add_stored_tournament_player(
                    StoredTournamentPlayer(
                        tournament_id=tournament_id, player_id=player_id
                    )
                )

    def tearDown(self) -> None:
        TestUtils.delete_event(KEIZER_EVENT_ID)

    def _load(self) -> Tournament:
        with suppress(KeyError):
            EventLoader.unload_event(KEIZER_EVENT_ID)
        self._event = EventLoader().load_event(KEIZER_EVENT_ID)
        return self._event.tournaments_by_name[KEIZER_TOURNAMENT_NAME]

    def _play_two_rounds(self) -> Tournament:
        for round_ in (1, 2):
            tournament = self._load()
            self.assertEqual('', tournament.generate_round_pairings(round_))
            tournament = self._load()
            for board in tournament.get_round_boards(round_):
                if board.black_tournament_player is not None:
                    tournament.add_result(board, Result.WIN)
        return self._load()

    def test_keizer_tournaments_are_sent_as_keizer(self) -> None:
        tournament = self._play_two_rounds()
        payload = build_tournament_results(tournament, 'sce-event', 'sce-tournament')
        self.assertEqual('keizer', payload['tournament']['type'])

    def test_each_board_carries_the_keizer_scores_before_the_round(self) -> None:
        tournament = self._play_two_rounds()
        payload = build_tournament_results(tournament, 'sce-event', 'sce-tournament')
        players_by_pairing_number = tournament.tournament_players_by_pairing_number

        boards = [pairing for pairing in payload['pairings'] if pairing['board'] > 0]
        self.assertTrue(boards)
        for pairing in boards:
            totals = tournament.keizer_scorer.totals_after(pairing['round'] - 1)
            white = players_by_pairing_number[pairing['whitePairingNumber']]
            self.assertEqual(totals[white.id], pairing['whitePoints'])
            if pairing['blackPairingNumber'] > 0:
                black = players_by_pairing_number[pairing['blackPairingNumber']]
                self.assertEqual(totals[black.id], pairing['blackPoints'])
            else:
                self.assertNotIn('blackPoints', pairing)

    def test_standings_points_are_the_keizer_totals(self) -> None:
        tournament = self._play_two_rounds()
        payload = build_tournament_results(tournament, 'sce-event', 'sce-tournament')
        players_by_pairing_number = tournament.tournament_players_by_pairing_number
        totals = tournament.keizer_scorer.totals_after(2)

        standings = payload['rankings'][0]['standings']
        self.assertEqual(len(KEIZER_PLAYERS), len(standings))
        for standing in standings:
            player = players_by_pairing_number[standing['pairingNumber']]
            self.assertEqual(totals[player.id], standing['points'])
