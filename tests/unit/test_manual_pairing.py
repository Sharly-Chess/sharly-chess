"""Manual pairing in FIDE mode: the absolute criteria a pairing is checked
against, the comparison of a round with the pairing engine's, and the manual
pairing that runs from the first change to the validation."""

from unittest import TestCase

import pytest

from data.event import Event
from data.loader import EventLoader
from data.pairings.manual_pairing import (
    both_against_preference,
    bye_eligibility_violations,
    bye_violations,
    changed_pairs,
    RoundPairs,
    differing_pairs,
    moved_member_seats,
    colour_preference,
    colour_violations,
    describe_pairs,
    pairing_violations,
    played_colours,
    round_pairs,
)
from data.pibes import Pibe, PibeType
from data.player import TournamentPlayer
from data.tournament import Tournament
from tests.test_config import TestUtils
from utils.enum import BoardColor, Result

EVENT_ID = 'test-manual-pairing-event'
TOURNAMENT_ID = 'test-manual-pairing-tournament'


@pytest.mark.unit
class ManualPairingTestCase(TestCase):
    def setUp(self) -> None:
        TestUtils.create_event(EVENT_ID)
        TestUtils.create_tournament(EVENT_ID, TOURNAMENT_ID, json_file='tec-swiss')

    def tearDown(self) -> None:
        TestUtils.delete_event(EVENT_ID)

    @property
    def tournament(self) -> Tournament:
        # The tournament keeps only a weak reference to its event.
        self._event: Event = EventLoader().load_event(EVENT_ID)
        return self._event.tournaments_by_name[TOURNAMENT_ID]

    def _repair_last_round(self) -> int:
        """Pair the last round again with the engine, and return it."""
        tournament = self.tournament
        round_ = tournament.last_paired_round
        tournament.board_operations.unpair(tournament.get_round_boards(round_))
        tournament = self.tournament
        error = tournament.pairing_variation.engine.generate_pairings(
            tournament, round_
        )
        self.assertEqual(error, '')
        return round_

    def test_the_engine_pairings_match_the_engine(self):
        round_ = self._repair_last_round()
        tournament = self.tournament

        expected = tournament.pairing_variation.engine.expected_round_pairs(
            tournament, round_
        )

        self.assertEqual(expected, round_pairs(self.tournament, round_))

    def test_a_colour_swap_differs_from_the_engine(self):
        round_ = self._repair_last_round()
        tournament = self.tournament
        board = next(
            board
            for board in tournament.get_round_boards(round_)
            if board.black_tournament_player is not None
        )
        black = board.black_tournament_player
        assert black is not None
        white_id, black_id = board.white_tournament_player.id, black.id
        board.permute_colors()

        tournament = self.tournament
        actual = round_pairs(tournament, round_)
        expected = tournament.pairing_variation.engine.expected_round_pairs(
            tournament, round_
        )

        self.assertEqual(expected - actual, {(white_id, black_id)})
        self.assertEqual(actual - expected, {(black_id, white_id)})
        white_number = tournament.tournament_players_by_id[white_id].pairing_number
        black_number = tournament.tournament_players_by_id[black_id].pairing_number
        self.assertEqual(
            describe_pairs(tournament, expected - actual),
            f'{white_number}-{black_number}',
        )

    def test_players_who_met_cannot_meet_again(self):
        tournament = self.tournament
        board = next(
            board
            for board in tournament.get_round_boards(1)
            if board.black_tournament_player is not None and board.result.is_win
        )
        white = board.white_tournament_player
        black = board.black_tournament_player
        assert black is not None

        violations = pairing_violations(tournament, 2, black, white)

        self.assertTrue(any('already played' in violation for violation in violations))

    def test_a_third_colour_in_a_row_breaks_the_colour_rules(self):
        tournament = self.tournament
        player_id = next(
            player.id
            for player in tournament.tournament_players
            if all(
                player.pairings_by_round[round_].board is not None
                and player.pairings_by_round[round_].opponent is not None
                for round_ in (2, 3)
            )
        )
        for round_ in (2, 3):
            tournament = self.tournament
            player = tournament.tournament_players_by_id[player_id]
            pairing = player.pairings_by_round[round_]
            if pairing.color == BoardColor.BLACK:
                assert pairing.board is not None
                pairing.board.permute_colors()
        tournament = self.tournament
        player = tournament.tournament_players_by_id[player_id]
        opponent = next(
            other for other in tournament.tournament_players if other.id != player_id
        )

        self.assertEqual(played_colours(player, 4)[-2:], [BoardColor.WHITE] * 2)
        self.assertTrue(colour_violations(tournament, 4, player, opponent))
        self.assertFalse(
            [
                violation
                for violation in colour_violations(tournament, 4, opponent, player)
                if player.full_name in violation
            ]
        )

    def test_the_bye_goes_once(self):
        tournament = self.tournament
        round_ = tournament.last_paired_round
        player = next(
            player
            for player in tournament.tournament_players
            if any(
                pairing.result
                in (
                    Result.PAIRING_ALLOCATED_BYE,
                    Result.FORFEIT_WIN,
                    Result.FULL_POINT_BYE,
                )
                for round_before, pairing in player.pairings_by_round.items()
                if round_before < round_
            )
        )

        self.assertTrue(bye_violations(tournament, round_, player))

    def test_the_bye_goes_to_the_lowest_score_that_can_have_it(self):
        tournament = self.tournament
        round_ = tournament.last_paired_round

        def score(player: TournamentPlayer) -> float:
            return sum(
                player.pairings_by_round[before].points for before in range(1, round_)
            )

        def lower_score_violations(player: TournamentPlayer) -> list[str]:
            return [
                violation
                for violation in bye_violations(tournament, round_, player)
                if 'lower score' in violation
            ]

        eligible = sorted(
            (
                player
                for player in tournament.tournament_players
                if not any(
                    'already had' in violation
                    for violation in bye_violations(tournament, round_, player)
                )
            ),
            key=score,
        )

        self.assertFalse(lower_score_violations(eligible[0]))
        self.assertGreater(score(eligible[-1]), score(eligible[0]))
        self.assertTrue(lower_score_violations(eligible[-1]))

    def test_a_player_who_had_the_bye_cannot_have_it_again(self):
        tournament = self.tournament
        round_ = tournament.last_paired_round
        had_it = [
            player
            for player in tournament.tournament_players
            if bye_eligibility_violations(player, round_)
        ]

        self.assertTrue(had_it)
        for player in had_it:
            self.assertTrue(
                any(
                    player.pairings_by_round[before].result
                    in (
                        Result.PAIRING_ALLOCATED_BYE,
                        Result.FORFEIT_WIN,
                        Result.FULL_POINT_BYE,
                    )
                    for before in range(1, round_)
                )
            )

    def test_both_players_against_their_colour(self):
        tournament = self.tournament
        round_ = 2
        board = next(
            board
            for board in tournament.get_round_boards(round_)
            if board.black_tournament_player is not None
            and colour_preference(board.white_tournament_player, round_)
            == BoardColor.WHITE
            and colour_preference(board.black_tournament_player, round_)
            == BoardColor.BLACK
        )
        white, black = board.white_tournament_player, board.black_tournament_player
        assert black is not None

        self.assertFalse(both_against_preference(round_, white, black))
        self.assertTrue(both_against_preference(round_, black, white))

    def test_a_manual_pairing_runs_until_validated(self):
        tournament = self.tournament
        round_ = tournament.last_paired_round
        tournament.log_pibe(Pibe(PibeType.MPA, round_, '1-2 => 2-1'))

        tournament.start_manual_pairing(round_)

        tournament = self.tournament
        self.assertEqual(tournament.manual_pairing_round, round_)
        self.assertEqual(tournament.pibes, [])
        tournament.end_manual_pairing(Pibe(PibeType.MPA, round_, '3-4 => 4-3'))
        tournament = self.tournament
        self.assertIsNone(tournament.manual_pairing_round)
        self.assertEqual(tournament.pibes, [Pibe(PibeType.MPA, round_, '3-4 => 4-3')])

    def test_unpairing_the_round_cancels_its_manual_pairing(self):
        tournament = self.tournament
        round_ = tournament.last_paired_round
        tournament.start_manual_pairing(round_)
        tournament.log_pibe(Pibe(PibeType.MPA, round_, '1-2 => 2-1'))

        self.tournament.cancel_manual_pairing(round_)

        tournament = self.tournament
        self.assertIsNone(tournament.manual_pairing_round)
        self.assertEqual(tournament.pibes, [])

    def test_there_is_no_manual_pairing_outside_fide_mode(self):
        tournament = self.tournament
        tournament.start_manual_pairing(1)
        tournament.leave_fide_mode()

        self.assertIsNone(self.tournament.manual_pairing_round)


@pytest.mark.unit
def test_only_the_pairs_of_the_players_moved_count():
    start = {(1, 2), (3, 4), (5, None)}
    actual = {(1, 2), (4, 3), (5, None)}

    self_check = changed_pairs(start, actual, {(1, 3), (2, 4), (4, 3), (5, 6)})

    assert self_check == {(1, 3), (2, 4), (4, 3)}
    assert changed_pairs(None, actual, {(1, 2)}) == {(1, 2)}


@pytest.mark.unit
def test_each_player_moved_is_compared_with_the_engine():
    expected: RoundPairs = {(1, 3), (7, 15), (8, 5), (10, 2)}
    start: RoundPairs = {(1, 3), (8, 10), (7, 2), (15, 5)}
    actual: RoundPairs = {(1, 8), (3, 10), (7, 2), (15, 5)}

    assert moved_member_seats(start, actual, expected) == [
        (1, (3, True), (8, True)),
        (3, (1, False), (10, True)),
        (8, (5, True), (1, False)),
        (10, (2, True), (3, False)),
    ]


@pytest.mark.unit
def test_byes_do_not_link_the_players_given_them():
    expected = {(1, 2), (3, 4), (5, None)}
    start = {(1, 2), (3, 4), (6, None)}
    actual = {(2, 1), (3, 4), (6, None)}

    missing, extra = differing_pairs(start, actual, expected)

    assert missing == {(1, 2)}
    assert extra == {(2, 1)}
