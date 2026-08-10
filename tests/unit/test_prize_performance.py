"""Tests for the per-round performance ranking bases of prize categories.

These use the real ``tec-swiss`` tournament fixture (players with actual
opponents and results) so the per-round performance indicator can be computed,
unlike the synthetic players of ``test_prizes.py`` which have no opponents."""

import pytest
from unittest import TestCase

from data.event import Event
from data.loader import EventLoader
from data.prize.prize_group import PrizeGroup
from data.prize.prize_sharing import NoPrizeSharing
from data.prize.prize_type import MonetaryPrizeType
from data.tournament import Tournament
from database.sqlite.event.event_store import (
    StoredPrize,
    StoredPrizeCategory,
    StoredPrizeGroup,
)
from tests.test_config import TestUtils
from utils.enum import PrizeCategoryRankingBasis

EVENT_ID = 'test-prize-performance-event'
TOURNAMENT_ID = 'test-prize-performance-tournament'


@pytest.mark.unit
class PrizePerformanceTestCase(TestCase):
    event: Event

    def setUp(self):
        super().setUp()
        TestUtils.create_event(EVENT_ID)
        TestUtils.create_tournament(EVENT_ID, TOURNAMENT_ID, json_file='tec-swiss')
        self.event = EventLoader().load_event(EVENT_ID)

    def tearDown(self):
        TestUtils.delete_event(EVENT_ID)
        super().tearDown()

    @property
    def tournament(self) -> Tournament:
        return self.event.tournaments_by_name[TOURNAMENT_ID]

    def test_round_performance_matches_expected_formula(self):
        """Each round performance is the K=20 Elo delta against the opponent."""
        tournament = self.tournament
        found_a_game = False
        for player in tournament.tournament_players:
            for round_index, pairing in player.pairings.items():
                performance = player.round_performance(round_index)
                if not pairing.opponent_id or not pairing.played:
                    self.assertIsNone(performance)
                    continue
                found_a_game = True
                opponent = tournament.tournament_players_by_id[pairing.opponent_id]
                expected_score = 1 / (
                    1 + 10 ** ((opponent.rating - player.rating) / 400)
                )
                expected = 20 * (pairing.result.points() - expected_score)
                assert performance is not None
                self.assertAlmostEqual(performance, expected)
        self.assertTrue(found_a_game)

    def test_aggregates(self):
        """Average and best aggregate the per-round performances."""
        for player in self.tournament.tournament_players:
            performances = player.round_performances
            if not performances:
                self.assertIsNone(player.average_round_performance)
                self.assertIsNone(player.best_round_performance)
                continue
            average = player.average_round_performance
            best = player.best_round_performance
            assert average is not None and best is not None
            self.assertAlmostEqual(average, sum(performances) / len(performances))
            self.assertAlmostEqual(best, max(performances))

    @staticmethod
    def _prize(prize_id: int, category_id: int, value: float) -> StoredPrize:
        return StoredPrize(
            id=prize_id,
            prize_category_id=category_id,
            type=MonetaryPrizeType.static_id(),
            value=value,
            description='',
        )

    def test_mixed_ranking_bases_coexist(self):
        """A group mixing a final-standing main category with a performance
        category ranks each category by its own basis and de-duplicates prizes
        by value across categories."""
        main_category = StoredPrizeCategory(
            id=1,
            prize_group_id=1,
            name='main',
            prize_sharing=NoPrizeSharing.static_id(),
            sharing_threshold=None,
            is_main=True,
            index=0,
            ranking_basis=PrizeCategoryRankingBasis.FINAL_STANDING.value,
            stored_prizes=[self._prize(1, 1, 300), self._prize(2, 1, 200)],
        )
        performance_category = StoredPrizeCategory(
            id=2,
            prize_group_id=1,
            name='performance',
            prize_sharing=NoPrizeSharing.static_id(),
            sharing_threshold=None,
            is_main=False,
            index=1,
            ranking_basis=PrizeCategoryRankingBasis.AVERAGE_PERFORMANCE.value,
            stored_prizes=[self._prize(3, 2, 100), self._prize(4, 2, 50)],
        )
        stored_group = StoredPrizeGroup(
            id=1,
            tournament_id=1,
            name='group',
            stored_prize_categories=[main_category, performance_category],
        )
        assigned_prizes = PrizeGroup(self.tournament, stored_group).assign_prizes()
        prize_by_player_id = {
            assigned.assigned_to.id: assigned.value
            for assigned in assigned_prizes
            if assigned.assigned_to
        }

        # The main category (higher prizes) follows the final standing.
        self.tournament.compute_tournament_player_ranks()
        by_rank = list(self.tournament.tournament_players_by_rank.values())
        self.assertEqual(prize_by_player_id.get(by_rank[0].id), 300)
        self.assertEqual(prize_by_player_id.get(by_rank[1].id), 200)

        # The performance category follows the average performance, skipping the
        # two players who already hold the larger main prizes.
        main_winner_ids = {by_rank[0].id, by_rank[1].id}
        performance_ranked = sorted(
            (
                player
                for player in self.tournament.tournament_players
                if player.average_round_performance is not None
                and player.id not in main_winner_ids
            ),
            key=lambda player: (
                -(player.average_round_performance or 0.0),
                player.rank,
            ),
        )
        self.assertEqual(prize_by_player_id.get(performance_ranked[0].id), 100)
        self.assertEqual(prize_by_player_id.get(performance_ranked[1].id), 50)

    def _prize_group(self, ranking_basis: PrizeCategoryRankingBasis) -> PrizeGroup:
        category = StoredPrizeCategory(
            id=1,
            prize_group_id=1,
            name='performance',
            prize_sharing='',
            sharing_threshold=None,
            is_main=False,
            index=0,
            ranking_basis=ranking_basis.value,
            stored_prizes=[
                StoredPrize(
                    id=1,
                    prize_category_id=1,
                    type=MonetaryPrizeType.static_id(),
                    value=100,
                    description='',
                ),
                StoredPrize(
                    id=2,
                    prize_category_id=1,
                    type=MonetaryPrizeType.static_id(),
                    value=50,
                    description='',
                ),
            ],
        )
        stored_group = StoredPrizeGroup(
            id=1,
            tournament_id=1,
            name='group',
            stored_prize_categories=[category],
        )
        return PrizeGroup(self.tournament, stored_group)

    def _assert_top_two_ordered_by(self, metric_name: str, ranking_basis):
        prize_group = self._prize_group(ranking_basis)
        assigned_prizes = prize_group.assign_prizes()

        ranked = sorted(
            (
                player
                for player in self.tournament.tournament_players
                if getattr(player, metric_name) is not None
            ),
            key=lambda player: (-getattr(player, metric_name), player.rank),
        )
        prize_by_player_id = {
            assigned.assigned_to.id: assigned.value
            for assigned in assigned_prizes
            if assigned.assigned_to
        }
        self.assertEqual(prize_by_player_id.get(ranked[0].id), 100)
        self.assertEqual(prize_by_player_id.get(ranked[1].id), 50)

    def test_assign_average_performance(self):
        self._assert_top_two_ordered_by(
            'average_round_performance',
            PrizeCategoryRankingBasis.AVERAGE_PERFORMANCE,
        )

    def test_assign_best_round_performance(self):
        self._assert_top_two_ordered_by(
            'best_round_performance',
            PrizeCategoryRankingBasis.BEST_ROUND_PERFORMANCE,
        )
