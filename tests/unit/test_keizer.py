"""The Keizer scorer and pairing matcher.

These tests pin the two pieces of Keizer that carry the real logic — the
iterative whole-table scorer and the minimum-cost matcher — against
worked examples, using lightweight fakes rather than a full tournament so
the arithmetic is checked directly.
"""

from typing import cast
from unittest import TestCase

from data.pairings.keizer import KeizerPairingEngine, KeizerScorer
from data.player import TournamentPlayer
from data.tournament import Tournament
from utils.enum import BoardColor, Result


class FakePairing:
    def __init__(
        self,
        result: Result,
        opponent_id: int | None,
        color: BoardColor | None = None,
    ):
        self.result = result
        self.opponent_id = opponent_id
        self.color = color

    @property
    def played(self) -> bool:
        return not self.result.is_unplayed


class FakePlayer:
    def __init__(self, player_id: int):
        self.id = player_id
        self.pairings: dict[int, FakePairing] = {}


class FakeTournament:
    def __init__(self, players: list[FakePlayer], rounds: int = 10):
        # ``players`` is given in rating order (best first).
        self._players = players
        self.rounds = rounds
        self.stored_pairing_settings: dict = {}

    @property
    def player_count(self) -> int:
        return len(self._players)

    @property
    def tournament_players(self) -> list[FakePlayer]:
        return self._players

    @property
    def tournament_players_by_starting_rank(self) -> dict[int, FakePlayer]:
        return {rank: player for rank, player in enumerate(self._players, start=1)}


def _play(
    a: FakePlayer, b: FakePlayer, round_: int, a_result: Result, b_result: Result
):
    a.pairings[round_] = FakePairing(a_result, b.id)
    b.pairings[round_] = FakePairing(b_result, a.id)


class KeizerScorerTest(TestCase):
    def setUp(self):
        # Four players A, B, C, D in rating order (ids 1..4).
        self.a, self.b, self.c, self.d = (FakePlayer(i) for i in range(1, 5))
        self.tournament = FakeTournament([self.a, self.b, self.c, self.d])
        self.scorer = KeizerScorer(cast(Tournament, self.tournament))

    def test_start_values_run_from_the_top_down_by_rank(self):
        # N = 4: lowest = (4-1)//2 = 1, top = 1 + 3 = 4, then -1 per rank.
        starts = self.scorer.totals_after(0)
        self.assertEqual(starts[self.a.id], 4)
        self.assertEqual(starts[self.b.id], 3)
        self.assertEqual(starts[self.c.id], 2)
        self.assertEqual(starts[self.d.id], 1)

    def test_win_earns_opponent_value_draw_earns_half(self):
        _play(self.a, self.b, 1, Result.WIN, Result.LOSS)
        _play(self.c, self.d, 1, Result.DRAW, Result.DRAW)
        totals = self.scorer.totals_after(1)
        # A: start 4 + B's start value 3.
        self.assertEqual(totals[self.a.id], 7)
        self.assertEqual(totals[self.b.id], 3)
        # C: start 2 + half of D's start value 1; D: start 1 + half of C's 2.
        self.assertEqual(totals[self.c.id], 2 + 0.5)
        self.assertEqual(totals[self.d.id], 1 + 1.0)

    def test_past_results_are_rescored_with_current_values(self):
        # Round 1: A beats D, C beats B (an upset).
        _play(self.a, self.d, 1, Result.WIN, Result.LOSS)
        _play(self.c, self.b, 1, Result.WIN, Result.LOSS)
        # Round 2: A beats C, B beats D.
        _play(self.a, self.c, 2, Result.WIN, Result.LOSS)
        _play(self.b, self.d, 2, Result.WIN, Result.LOSS)

        # After round 1: A 5, C 5, B 3, D 1 -> order A, C, B, D, so the
        # round-2 ranking values are A 4, C 3, B 2, D 1. B has dropped to
        # rank 3, from its start rank 2.
        self.assertEqual(
            self.scorer.totals_after(1),
            {self.a.id: 5, self.b.id: 3, self.c.id: 5, self.d.id: 1},
        )
        totals = self.scorer.totals_after(2)
        # Each total is the player's *current* own value (the own-value
        # bonus, from the round-2 values A 4, C 3, B 2, D 1) plus results
        # scored with those same current values. Two recorrections show:
        # B's own-value bonus is now 2, not its start value 3 (it slipped to
        # rank 3); and C's round-1 win over B is now worth B's current 2.
        self.assertEqual(totals[self.a.id], 4 + 1 + 3)  # 8
        self.assertEqual(totals[self.c.id], 3 + 2 + 0)  # 5
        self.assertEqual(totals[self.b.id], 2 + 0 + 1)  # 3
        self.assertEqual(totals[self.d.id], 1)

    def test_excused_absence_earns_a_fraction_of_own_value(self):
        # A takes a half-point bye in round 1; default fraction is 1/3.
        self.a.pairings[1] = FakePairing(Result.HALF_POINT_BYE, None)
        total = self.scorer.totals_after(1)[self.a.id]
        # Own start value 4 * 1/3.
        self.assertAlmostEqual(total, 4 + 4 / 3)

    def test_late_entrant_only_scores_rounds_it_played(self):
        # D joins in round 2 (no round-1 pairing) and beats C.
        _play(self.a, self.b, 1, Result.WIN, Result.LOSS)
        _play(self.c, self.d, 2, Result.LOSS, Result.WIN)
        totals = self.scorer.totals_after(2)
        # D scores only its round-2 win; no phantom round-1 contribution.
        # values_after(1): A 4, B 3, C 2, D 1. D beats C -> +2.
        self.assertEqual(totals[self.d.id], 1 + 2)


class KeizerMatcherTest(TestCase):
    def setUp(self):
        self.engine = KeizerPairingEngine()

    def _ids(self, pairs):
        return {frozenset((a.id, b.id)) for a, b in pairs}

    def test_adjacent_players_are_paired_first(self):
        players = [FakePlayer(i) for i in range(1, 5)]
        pairs = self.engine._match(
            cast(list[TournamentPlayer], players), round_=1, gap=99
        )
        self.assertEqual(self._ids(pairs), {frozenset((1, 2)), frozenset((3, 4))})

    def test_a_rematch_inside_the_gap_is_avoided(self):
        players = [FakePlayer(i) for i in range(1, 5)]
        p0, p1 = players[0], players[1]
        # p0 and p1 met in round 1; gap is large, so they must not repeat.
        p0.pairings[1] = FakePairing(Result.WIN, p1.id)
        p1.pairings[1] = FakePairing(Result.LOSS, p0.id)
        pairs = self.engine._match(
            cast(list[TournamentPlayer], players), round_=2, gap=99
        )
        # Cheapest rematch-free matching pairs neighbours-once-removed.
        self.assertEqual(self._ids(pairs), {frozenset((1, 3)), frozenset((2, 4))})
