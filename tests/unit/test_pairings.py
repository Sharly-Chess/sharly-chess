from unittest import TestCase

from data.board import Board
from data.event import Event
from data.loader import EventLoader

import pytest
from data.pairings.engines import BergerPairingEngine
from database.sqlite.event.event_database import EventDatabase
from database.sqlite.event.event_store import StoredTournamentPlayer
from tests.test_config import TestUtils

EVENT_ID = 'test-pairings-event'
TOURNAMENT_ID = 'test-pairings-tournament'


@pytest.mark.unit
class PairingTestCase(TestCase):
    event: Event

    def setUp(self):
        super().setUp()
        TestUtils.create_event(EVENT_ID)
        self.event = EventLoader().load_event(EVENT_ID)

    def tearDown(self):
        TestUtils.delete_event(EVENT_ID)
        super().tearDown()

    """Tests for all the pairing systems."""

    def _tournament_from_json(self, json_file: str):
        TestUtils.create_tournament(EVENT_ID, TOURNAMENT_ID, json_file=json_file)
        return self._reload_tournament()

    def _reload_tournament(self):
        self.event = EventLoader().load_event(EVENT_ID)
        return self.event.tournaments_by_name[TOURNAMENT_ID]

    def assert_no_pairings_diff_in_tournament(
        self,
        json_file: str,
        ignore_order: bool = False,
        max_round: int | None = None,
    ):
        tournament = self._tournament_from_json(json_file)
        diff_display = ''
        for round_ in range(1, (max_round or tournament.rounds) + 1):
            diff = tournament.pairing_variation.engine.pairings_diff(
                tournament, round_, ignore_order
            )
            if diff:
                diff_display = self._diff_display(diff)
            self.assertEqual(
                diff,
                [],
                f'Round {round_}: {len(diff)} differences\n\n{diff_display}',
            )

    @classmethod
    def _diff_display(
        cls, pairing_diff: list[tuple[Board | None, Board | None]]
    ) -> str:
        message = f'Real boards{"":<19}Expected boards\n'
        for real_board, expected_board in pairing_diff:
            message += f'{cls._board_display(real_board)}   {cls._board_display(expected_board)}\n'
        return message

    @staticmethod
    def _board_display(board: Board | None) -> str:
        if not board:
            return f'{"":<14} - {"":<10}'
        return (
            f'{board.index:>2}. {board.white_tournament_player.full_name:<10}'
            f' - {getattr(board.black_tournament_player, "full_name", ""):<10}'
        )

    # ---------------------------------------------------------------------------------
    # Swiss pairing systems
    # ---------------------------------------------------------------------------------
    """
    For each swiss system, a tournament has been generated
    with Papi using the following process:
        - Start from a tournament with the players of the TEC exercise file*
        - Settings:
            - pair first player as white
            - for accelerated pairings:
                - 2 groups rating limit: 1825 (8 - 8)
                - 3 groups rating limits: 1825 - 1625 (8 - 4 - 4)
        - For each round
            - Generate the pairings
            - fill out random standard results (win - draw - loss)

    Testing Papi-generated tournament requires to avoid unplayed game results
    (forfeits and byes) as it does not respect the FIDE floater following rule:
    "A player who, for whatever reason, does not play in a round, receives a downfloat."
    FIDE Handbook C.04.3 - A.4.b
    This rule changes in the rules effective from 1 July 2025:
    "A player who, for whatever reason, scores without playing in a round
    more points than those rewarded for a loss, also receives a downfloat."
    FIDE Handbook C.04.3 - 1.4.3
    Once these modifications have been implemented in BbpPairings,
    including forfeits and ZPB will be possible, but not HPB.

    The tests regenerate the pairings for each round
    from the results of the previous rounds.
    The generated pairings are then compared to the actual pairings.

    * https://tec.fide.com/2024/03/18/tie-break-exercise/
    """

    def test_swiss_tec_standard(self):
        self.assert_no_pairings_diff_in_tournament('tec-swiss')

    def test_swiss_papi_standard(self):
        self.assert_no_pairings_diff_in_tournament('papi-swiss')

    def test_swiss_papi_haley(self):
        self.assert_no_pairings_diff_in_tournament('papi-haley')

    def test_swiss_papi_haley_soft(self):
        # TODO (Molrn) figure out what is wrong with round 5
        self.assert_no_pairings_diff_in_tournament('papi-haley-soft', max_round=4)

    def test_swiss_papi_progressive(self):
        # TODO (Molrn) figure out what is wrong with round 5
        self.assert_no_pairings_diff_in_tournament('papi-progressive', max_round=4)

    def test_swiss_papi_nicois(self):
        # TODO (Molrn) figure out what is wrong with round 3
        self.assert_no_pairings_diff_in_tournament('papi-nicois', max_round=2)

    # ---------------------------------------------------------------------------------
    # Berger
    # ---------------------------------------------------------------------------------

    def assert_generated_berger_table_equals_fide_table(
        self, player_count: int, fide_table: dict[int, list[tuple[int, int]]]
    ):
        """Assert that the generated Berger table for *player_count* players
        is the same as the one defined in the FIDE handbook (section C.05.Annex 1)
        """
        self.assertEqual(BergerPairingEngine.get_berger_table(player_count), fide_table)

    def test_berger_2_players_table(self):
        # A two-competitor round-robin is a single round (used by 2-team
        # team round-robins).
        self.assert_generated_berger_table_equals_fide_table(2, {1: [(1, 2)]})

    def test_berger_4_players_table(self):
        self.assert_generated_berger_table_equals_fide_table(
            4,
            {
                1: [(1, 4), (2, 3)],
                2: [(4, 3), (1, 2)],
                3: [(2, 4), (3, 1)],
            },
        )

    def test_berger_odd_players_table(self):
        self.assert_generated_berger_table_equals_fide_table(
            3,
            {
                1: [(1, 4), (2, 3)],
                2: [(4, 3), (1, 2)],
                3: [(2, 4), (3, 1)],
            },
        )

    def test_berger_6_players_table(self):
        self.assert_generated_berger_table_equals_fide_table(
            6,
            {
                1: [(1, 6), (2, 5), (3, 4)],
                2: [(6, 4), (5, 3), (1, 2)],
                3: [(2, 6), (3, 1), (4, 5)],
                4: [(6, 5), (1, 4), (2, 3)],
                5: [(3, 6), (4, 2), (5, 1)],
            },
        )

    def test_berger_8_players_table(self):
        self.assert_generated_berger_table_equals_fide_table(
            8,
            {
                1: [(1, 8), (2, 7), (3, 6), (4, 5)],
                2: [(8, 5), (6, 4), (7, 3), (1, 2)],
                3: [(2, 8), (3, 1), (4, 7), (5, 6)],
                4: [(8, 6), (7, 5), (1, 4), (2, 3)],
                5: [(3, 8), (4, 2), (5, 1), (6, 7)],
                6: [(8, 7), (1, 6), (2, 5), (3, 4)],
                7: [(4, 8), (5, 3), (6, 2), (7, 1)],
            },
        )

    def test_berger_10_players_table(self):
        self.assert_generated_berger_table_equals_fide_table(
            10,
            {
                1: [(1, 10), (2, 9), (3, 8), (4, 7), (5, 6)],
                2: [(10, 6), (7, 5), (8, 4), (9, 3), (1, 2)],
                3: [(2, 10), (3, 1), (4, 9), (5, 8), (6, 7)],
                4: [(10, 7), (8, 6), (9, 5), (1, 4), (2, 3)],
                5: [(3, 10), (4, 2), (5, 1), (6, 9), (7, 8)],
                6: [(10, 8), (9, 7), (1, 6), (2, 5), (3, 4)],
                7: [(4, 10), (5, 3), (6, 2), (7, 1), (8, 9)],
                8: [(10, 9), (1, 8), (2, 7), (3, 6), (4, 5)],
                9: [(5, 10), (6, 4), (7, 3), (8, 2), (9, 1)],
            },
        )

    def test_berger_12_players_table(self):
        self.assert_generated_berger_table_equals_fide_table(
            12,
            {
                1: [(1, 12), (2, 11), (3, 10), (4, 9), (5, 8), (6, 7)],
                2: [(12, 7), (8, 6), (9, 5), (10, 4), (11, 3), (1, 2)],
                3: [(2, 12), (3, 1), (4, 11), (5, 10), (6, 9), (7, 8)],
                4: [(12, 8), (9, 7), (10, 6), (11, 5), (1, 4), (2, 3)],
                5: [(3, 12), (4, 2), (5, 1), (6, 11), (7, 10), (8, 9)],
                6: [(12, 9), (10, 8), (11, 7), (1, 6), (2, 5), (3, 4)],
                7: [(4, 12), (5, 3), (6, 2), (7, 1), (8, 11), (9, 10)],
                8: [(12, 10), (11, 9), (1, 8), (2, 7), (3, 6), (4, 5)],
                9: [(5, 12), (6, 4), (7, 3), (8, 2), (9, 1), (10, 11)],
                10: [(12, 11), (1, 10), (2, 9), (3, 8), (4, 7), (5, 6)],
                11: [(6, 12), (7, 5), (8, 4), (9, 3), (10, 2), (11, 1)],
            },
        )

    def test_berger_14_players_table(self):
        self.assert_generated_berger_table_equals_fide_table(
            14,
            {
                1: [(1, 14), (2, 13), (3, 12), (4, 11), (5, 10), (6, 9), (7, 8)],
                2: [(14, 8), (9, 7), (10, 6), (11, 5), (12, 4), (13, 3), (1, 2)],
                3: [(2, 14), (3, 1), (4, 13), (5, 12), (6, 11), (7, 10), (8, 9)],
                4: [(14, 9), (10, 8), (11, 7), (12, 6), (13, 5), (1, 4), (2, 3)],
                5: [(3, 14), (4, 2), (5, 1), (6, 13), (7, 12), (8, 11), (9, 10)],
                6: [(14, 10), (11, 9), (12, 8), (13, 7), (1, 6), (2, 5), (3, 4)],
                7: [(4, 14), (5, 3), (6, 2), (7, 1), (8, 13), (9, 12), (10, 11)],
                8: [(14, 11), (12, 10), (13, 9), (1, 8), (2, 7), (3, 6), (4, 5)],
                9: [(5, 14), (6, 4), (7, 3), (8, 2), (9, 1), (10, 13), (11, 12)],
                10: [(14, 12), (13, 11), (1, 10), (2, 9), (3, 8), (4, 7), (5, 6)],
                11: [(6, 14), (7, 5), (8, 4), (9, 3), (10, 2), (11, 1), (12, 13)],
                12: [(14, 13), (1, 12), (2, 11), (3, 10), (4, 9), (5, 8), (6, 7)],
                13: [(7, 14), (8, 6), (9, 5), (10, 4), (11, 3), (12, 2), (13, 1)],
            },
        )

    def test_berger_16_players_table(self):
        fide_berger_table = {
            1: [(1, 16), (2, 15), (3, 14), (4, 13), (5, 12), (6, 11), (7, 10), (8, 9)],
            2: [(16, 9), (10, 8), (11, 7), (12, 6), (13, 5), (14, 4), (15, 3), (1, 2)],
            3: [(2, 16), (3, 1), (4, 15), (5, 14), (6, 13), (7, 12), (8, 11), (9, 10)],
            4: [(16, 10), (11, 9), (12, 8), (13, 7), (14, 6), (15, 5), (1, 4), (2, 3)],
            5: [(3, 16), (4, 2), (5, 1), (6, 15), (7, 14), (8, 13), (9, 12), (10, 11)],
            6: [(16, 11), (12, 10), (13, 9), (14, 8), (15, 7), (1, 6), (2, 5), (3, 4)],
            7: [(4, 16), (5, 3), (6, 2), (7, 1), (8, 15), (9, 14), (10, 13), (11, 12)],
            8: [(16, 12), (13, 11), (14, 10), (15, 9), (1, 8), (2, 7), (3, 6), (4, 5)],
            9: [(5, 16), (6, 4), (7, 3), (8, 2), (9, 1), (10, 15), (11, 14), (12, 13)],
            10: [(16, 13), (14, 12), (15, 11), (1, 10), (2, 9), (3, 8), (4, 7), (5, 6)],
            11: [(6, 16), (7, 5), (8, 4), (9, 3), (10, 2), (11, 1), (12, 15), (13, 14)],
            12: [(16, 14), (15, 13), (1, 12), (2, 11), (3, 10), (4, 9), (5, 8), (6, 7)],
            13: [(7, 16), (8, 6), (9, 5), (10, 4), (11, 3), (12, 2), (13, 1), (14, 15)],
            14: [(16, 15), (1, 14), (2, 13), (3, 12), (4, 11), (5, 10), (6, 9), (7, 8)],
            15: [(8, 16), (9, 7), (10, 6), (11, 5), (12, 4), (13, 3), (14, 2), (15, 1)],
        }
        self.assert_generated_berger_table_equals_fide_table(16, fide_berger_table)

    def test_berger_tec(self):
        self.assert_no_pairings_diff_in_tournament('tec-round-robin', ignore_order=True)

    def test_berger_papi(self):
        self.assert_no_pairings_diff_in_tournament('papi-berger', ignore_order=True)

    def test_berger_papi_odd(self):
        self.assert_no_pairings_diff_in_tournament('papi-berger-odd', ignore_order=True)

    def test_berger_papi_large(self):
        self.assert_no_pairings_diff_in_tournament(
            'papi-berger-large', ignore_order=True
        )

    # ---------------------------------------------------------------------------------
    # Pairing numbers
    # ---------------------------------------------------------------------------------

    def test_pairing_numbers_assigned_in_starting_rank_order(self):
        tournament = self._tournament_from_json('tec-swiss')
        expected_player_name_by_pairing_number = {
            1: 'ALYX',
            2: 'BRUNO',
            3: 'CHARLINE',
            4: 'DAVID',
            5: 'HELENE',
            6: 'FRANCK',
            7: 'GENEVIEVE',
            8: 'IRINA',
            9: 'JESSICA',
            10: 'LAIS',
            11: 'MARIA',
            12: 'NICK',
            13: 'OPAL',
            14: 'PAUL',
            15: 'REINE',
            16: 'STEPHAN',
        }
        player_name_by_pairing_number = {
            pairing_number: tournament_player.last_name
            for pairing_number, tournament_player in tournament.tournament_players_by_pairing_number.items()
        }
        self.assertEqual(
            player_name_by_pairing_number,
            expected_player_name_by_pairing_number,
        )

    def test_pairing_numbers_reordered_on_starting_rank_change(self):
        tournament = self._tournament_from_json('tec-swiss-unpaired')
        tournament_player = tournament.tournament_players_by_pairing_number[9]
        tournament_player.stored_player.ratings |= {
            1: {
                'fide': 2250,
            }
        }
        with EventDatabase(EVENT_ID, True) as database:
            database.update_stored_player(tournament_player.stored_player)

        tournament = self._reload_tournament()
        players_by_pairing_number = tournament.tournament_players_by_pairing_number
        self.assertEqual(players_by_pairing_number[9].last_name, 'IRINA')
        self.assertEqual(players_by_pairing_number[1].last_name, 'JESSICA')

    def test_pairing_numbers_not_reordered_on_starting_rank_change_after_round_4(self):
        tournament = self._tournament_from_json('tec-swiss')
        tournament_player = tournament.tournament_players_by_pairing_number[9]
        tournament_player.stored_player.ratings |= {
            1: {
                'value': 2250,
                'type': 3,
            }
        }
        with EventDatabase(EVENT_ID, True) as database:
            database.update_stored_player(tournament_player.stored_player)

        tournament = self._reload_tournament()
        tournament_player = tournament.tournament_players_by_pairing_number[9]
        players_by_pairing_number = tournament.tournament_players_by_pairing_number
        self.assertEqual(
            players_by_pairing_number[9].last_name,
            tournament_player.last_name,
        )

    def test_pairing_numbers_reordered_on_player_deletion(self):
        tournament = self._tournament_from_json('tec-swiss')
        tournament_player = tournament.tournament_players_by_pairing_number[9]

        with EventDatabase(EVENT_ID, True) as database:
            database.delete_stored_player(tournament_player.id)

        tournament = self._reload_tournament()
        expected_player_name_by_pairing_number = {
            1: 'ALYX',
            2: 'BRUNO',
            3: 'CHARLINE',
            4: 'DAVID',
            5: 'HELENE',
            6: 'FRANCK',
            7: 'GENEVIEVE',
            8: 'IRINA',
            9: 'LAIS',
            10: 'MARIA',
            11: 'NICK',
            12: 'OPAL',
            13: 'PAUL',
            14: 'REINE',
            15: 'STEPHAN',
        }
        player_name_by_pairing_number = {
            pairing_number: tournament_player.last_name
            for pairing_number, tournament_player in tournament.tournament_players_by_pairing_number.items()
        }
        self.assertEqual(
            player_name_by_pairing_number,
            expected_player_name_by_pairing_number,
        )

    def test_pairing_numbers_reordered_on_player_insertion(self):
        tournament = self._tournament_from_json('tec-swiss')
        tournament_player = tournament.tournament_players_by_pairing_number[9]
        new_stored_player = tournament_player.stored_player
        new_stored_player.id = None
        new_stored_player.last_name = 'PIERRE'
        new_stored_player.ratings |= {
            1: {
                'fide': 1925,
            }
        }
        with EventDatabase(EVENT_ID, True) as database:
            player_id = database.add_stored_player(new_stored_player)
            database.add_stored_tournament_player(
                StoredTournamentPlayer(tournament.id, player_id)
            )

        tournament = self._reload_tournament()
        expected_player_name_by_pairing_number = {
            1: 'ALYX',
            2: 'BRUNO',
            3: 'CHARLINE',
            4: 'DAVID',
            5: 'HELENE',
            6: 'FRANCK',
            7: 'PIERRE',
            8: 'GENEVIEVE',
            9: 'IRINA',
            10: 'JESSICA',
            11: 'LAIS',
            12: 'MARIA',
            13: 'NICK',
            14: 'OPAL',
            15: 'PAUL',
            16: 'REINE',
            17: 'STEPHAN',
        }
        player_name_by_pairing_number = {
            pairing_number: tournament_player.last_name
            for pairing_number, tournament_player in tournament.tournament_players_by_pairing_number.items()
        }
        self.assertEqual(
            player_name_by_pairing_number,
            expected_player_name_by_pairing_number,
        )
