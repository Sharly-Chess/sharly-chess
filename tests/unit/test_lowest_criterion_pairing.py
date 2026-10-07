"""Prohibited pairings avoided as bbpPairings' lowest-priority criterion,
through the real engine."""

from unittest import TestCase

import pytest

from data.event import Event
from data.loader import EventLoader
from data.tournament import Tournament
from database.sqlite.event.event_database import EventDatabase
from tests.test_config import TestUtils
from utils.enum import ProhibitedPairingConstraint

EVENT_ID = 'test-lowest-criterion-pairing-event'
TOURNAMENT_ID = 'test-lowest-criterion-pairing-tournament'


@pytest.mark.unit
class LowestCriterionTestCase(TestCase):
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

    def test_the_round_is_paired_and_exported_with_scs_records(self):
        tournament = self.tournament
        round_ = tournament.last_paired_round
        board = tournament.get_round_boards(round_)[0]
        white = board.white_tournament_player
        black = board.black_tournament_player
        assert black is not None
        assert white.pairing_number is not None
        assert black.pairing_number is not None
        tournament.board_operations.unpair(tournament.get_round_boards(round_))

        tournament = self.tournament
        with EventDatabase(tournament.event.uniq_id, True) as database:
            tournament.prohibited_pairings.set_manual_groups(
                [
                    (
                        ProhibitedPairingConstraint.LOWEST_CRITERION,
                        [white.id, black.id],
                    )
                ],
                database,
            )
        tournament = self.tournament
        error = tournament.pairing_variation.engine.generate_pairings(
            tournament, round_
        )

        self.assertEqual(error, '')
        tournament = self.tournament
        self.assertEqual(
            [
                group.constraint
                for group in tournament.prohibited_pairings.snapshot(round_)
            ],
            [ProhibitedPairingConstraint.LOWEST_CRITERION],
        )
        trf = tournament.to_trf()
        self.assertEqual(
            [
                (line.first_round, sorted(line.pairing_numbers))
                for line in trf.soft_prohibited_pairings
            ],
            [(round_, sorted([white.pairing_number, black.pairing_number]))],
        )
        self.assertEqual(trf.prohibited_pairings, [])
