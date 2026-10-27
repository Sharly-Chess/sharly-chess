from unittest import TestCase

import pytest

from data.pairings.engines import BergerPairingEngine, DoubleBergerPairingEngine
from data.pairings.systems import RoundRobinPairingSystem, TeamRoundRobinPairingSystem
from data.tie_breaks.tie_breaks import (
    AverageOfBuchholzTieBreak,
    ForeBuchholzTieBreak,
    StandardBuchholzTieBreak,
    SumOfBuchholzTieBreak,
)


def _colour_sequences(player_count: int, reverse_last_rounds: bool) -> dict[int, str]:
    single_rounds = BergerPairingEngine.get_single_encounter_round_count(player_count)
    table = BergerPairingEngine.get_berger_table(player_count)
    sequences = dict.fromkeys(range(1, player_count + 1), '')
    for round_ in range(1, 2 * single_rounds + 1):
        source_round, invert = DoubleBergerPairingEngine.source_round(
            round_, single_rounds, reverse_last_rounds
        )
        for white, black in table[source_round]:
            if invert:
                white, black = black, white
            sequences[white] += 'W'
            sequences[black] += 'B'
    return sequences


def _has_colour_triple(sequences: dict[int, str]) -> bool:
    return any(
        'WWW' in sequence or 'BBB' in sequence for sequence in sequences.values()
    )


@pytest.mark.unit
class DoubleBergerTestCase(TestCase):
    def test_reversed_last_rounds_of_first_cycle(self):
        # 6 players: 5 rounds per cycle.
        self.assertEqual(
            [DoubleBergerPairingEngine.source_round(r, 5, True) for r in range(1, 11)],
            [
                (1, False),
                (2, False),
                (3, False),
                (5, False),
                (4, False),
                (1, True),
                (2, True),
                (3, True),
                (4, True),
                (5, True),
            ],
        )

    def test_unreversed_last_rounds_of_first_cycle(self):
        self.assertEqual(
            [DoubleBergerPairingEngine.source_round(r, 5, False) for r in range(1, 11)],
            [(r, False) for r in range(1, 6)] + [(r, True) for r in range(1, 6)],
        )

    def test_no_reversal_under_three_rounds_per_cycle(self):
        for reverse in (True, False):
            self.assertEqual(
                [DoubleBergerPairingEngine.source_round(r, 1, reverse) for r in (1, 2)],
                [(1, False), (1, True)],
            )

    def test_reversal_prevents_colour_triples(self):
        for player_count in (4, 6, 8, 10):
            with self.subTest(player_count=player_count):
                self.assertFalse(
                    _has_colour_triple(_colour_sequences(player_count, True))
                )
                self.assertTrue(
                    _has_colour_triple(_colour_sequences(player_count, False))
                )


@pytest.mark.unit
class RoundRobinBuchholzTestCase(TestCase):
    def test_buchholz_family_incompatible_with_round_robins(self):
        for tie_break_class in (
            StandardBuchholzTieBreak,
            ForeBuchholzTieBreak,
            SumOfBuchholzTieBreak,
            AverageOfBuchholzTieBreak,
        ):
            tie_break = tie_break_class()
            for system in (RoundRobinPairingSystem(), TeamRoundRobinPairingSystem()):
                with self.subTest(tie_break=tie_break.id, system=system.id):
                    self.assertFalse(tie_break.is_compatible_with(system))
