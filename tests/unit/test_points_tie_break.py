"""The points as a ranking criterion of their own.

TRF26 record 212 lists the criteria that define the standings and accepts
``PTS`` among them, so where the points sit decides the ranking:
``212 PTS,<rest>`` is the classic "points, then tie-breaks" — the spec
notes it is the same as ``202 <rest>`` — while ranking ``PTS`` lower lets
another criterion outrank the score.
"""

from unittest import TestCase

import pytest

from data.loader import EventLoader
from data.tie_breaks.tie_breaks import (
    PointsTieBreak,
    StandardBuchholzTieBreak,
    WinsTieBreak,
)
from plugins.ffe.papi_converter import PapiConverter
from tests.test_config import TestUtils

EVENT_ID = 'test-points-tie-break'
TOURNAMENT_NAME = 'tournament'


@pytest.mark.unit
class PointsTieBreakTestCase(TestCase):
    def setUp(self) -> None:
        TestUtils.create_event(EVENT_ID)
        TestUtils.create_tournament(EVENT_ID, TOURNAMENT_NAME, json_file='tec-swiss')
        self.event = EventLoader().load_event(EVENT_ID)
        # A TieBreakValue keeps only a weak reference to its tie-break,
        # so the instances have to outlive the assignment.
        self._held: list = []

    def tearDown(self) -> None:
        TestUtils.delete_event(EVENT_ID)

    @property
    def tournament(self):
        return self.event.tournaments_by_name[TOURNAMENT_NAME]

    def _rank(self, tie_breaks: list) -> list[tuple[str, float]]:
        """Rank the field on *tie_breaks* and return (name, points) in
        ranking order."""
        self._held.append(tie_breaks)
        tournament = self.tournament
        tournament.tie_breaks_by_id = {
            index + 1: tie_break for index, tie_break in enumerate(tie_breaks)
        }
        tournament.compute_tournament_player_ranks()
        return [
            (player.last_name, player.points)
            for player in sorted(tournament.tournament_players, key=lambda p: p.rank)
        ]

    def test_nothing_configured_ranks_on_the_points(self):
        # An empty list would otherwise rank nobody, the score being one
        # of the criteria rather than an implicit first key.
        tournament = self.tournament
        tournament.tie_breaks_by_id = {}
        self.assertEqual([tb.id for tb in tournament.tie_breaks], ['POINTS'])
        ranked = self._rank([])
        self.assertEqual(ranked[0][1], max(points for __, points in ranked))

    def test_points_first_ranks_by_score(self):
        ranked = self._rank([PointsTieBreak(), WinsTieBreak()])
        points = [player_points for __, player_points in ranked]
        self.assertEqual(points, sorted(points, reverse=True))

    def test_a_criterion_before_the_points_outranks_them(self):
        # The capability TRF26 allows: whoever leads on wins ranks first,
        # even on a lower score.
        by_wins = self._rank([WinsTieBreak(), PointsTieBreak()])
        by_points = self._rank([PointsTieBreak(), WinsTieBreak()])
        self.assertNotEqual(
            [name for name, __ in by_wins], [name for name, __ in by_points]
        )
        points = [player_points for __, player_points in by_wins]
        self.assertNotEqual(points, sorted(points, reverse=True))

    def test_the_points_can_be_left_out_entirely(self):
        ranked = self._rank([WinsTieBreak()])
        self.assertEqual([tb.id for tb in self.tournament.tie_breaks], ['WINS'])
        self.assertEqual(len(ranked), len(self.tournament.tournament_players))

    def test_papi_export_is_blocked_when_the_points_do_not_lead(self):
        # Papi ranks on the points and then on up to three tie-breaks;
        # it cannot express a criterion that outranks the score, so the
        # export is refused rather than silently reordered.
        self._rank([PointsTieBreak(), WinsTieBreak()])
        self.assertIsNone(
            PapiConverter.papi_export_unavailable_message(self.tournament)
        )
        self._rank([WinsTieBreak(), PointsTieBreak()])
        message = PapiConverter.papi_export_unavailable_message(self.tournament)
        self.assertIsNotNone(message)
        assert message is not None
        self.assertIn('points', message.lower())

    def test_the_trf_carries_the_order(self):
        self._rank([WinsTieBreak(), PointsTieBreak(), StandardBuchholzTieBreak()])
        trf = self.tournament.to_trf(after_round=self.tournament.rounds)
        self.assertEqual(trf.standings_tie_breaks[:3], ['WIN', 'PTS', 'BH'])
