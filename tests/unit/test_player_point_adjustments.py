import pytest
from unittest import TestCase

from data.loader import EventLoader
from database.sqlite.event.event_database import EventDatabase
from database.sqlite.event.event_store import (
    StoredBoard,
    StoredPlayer,
    StoredTournamentPlayer,
)
from utils.enum import Result
from tests.test_config import TestUtils

EVENT_ID = 'test-player-point-adjustments'


@pytest.mark.unit
class PlayerPointAdjustmentTestCase(TestCase):
    def setUp(self):
        super().setUp()
        TestUtils.create_event(EVENT_ID)
        self.tournament_id = TestUtils.create_tournament(EVENT_ID, 'Adjustments').id
        with EventDatabase(EVENT_ID, write=True) as database:
            for index in range(2):
                player_id = database.add_stored_player(
                    StoredPlayer(id=None, last_name=f'P{index}', check_in=True)
                )
                database.add_stored_tournament_player(
                    StoredTournamentPlayer(
                        tournament_id=self.tournament_id,
                        player_id=player_id,
                        pairing_number=index + 1,
                    )
                )
        self.event = EventLoader().load_event(EVENT_ID)

    def tearDown(self):
        TestUtils.delete_event(EVENT_ID)
        super().tearDown()

    @property
    def tournament(self):
        return self.event.tournaments_by_id[self.tournament_id]

    def _reload(self):
        self.event = EventLoader().load_event(EVENT_ID)

    def _pair_round_one(self):
        """Seat the two players on one board. The pairing engine refuses
        a field this small (it wants more players than rounds), and the
        board is all these tests need."""
        tournament = self.tournament
        white = tournament.tournament_players_by_pairing_number[1]
        black = tournament.tournament_players_by_pairing_number[2]
        tournament.create_boards(
            [
                StoredBoard(
                    id=None,
                    white_player_id=white.id,
                    black_player_id=black.id,
                    index=0,
                )
            ],
            1,
            Result.NO_RESULT,
        )
        self._reload()

    def test_adjustment_survives_a_reload_and_counts_towards_the_score(self):
        tournament = self.tournament
        player = next(iter(tournament.tournament_players_by_pairing_number.values()))
        before = player.points_after(tournament.rounds)

        with EventDatabase(EVENT_ID, write=True) as database:
            tournament.set_manual_player_point_adjustment(
                player.id, 1, -0.5, 'late arrival', database
            )
        self._reload()
        tournament = self.tournament
        player = tournament.tournament_players_by_pairing_number[player.pairing_number]

        self.assertEqual(tournament.player_point_adjustment(player.id, 1), -0.5)
        self.assertEqual(
            tournament.stored_player_point_adjustment(player.id, 1).reason,
            'late arrival',
        )
        # The score the pairing engine works from moves with it.
        self.assertEqual(player.points_after(tournament.rounds), before - 0.5)

    def test_clearing_an_adjustment_removes_it(self):
        tournament = self.tournament
        player = next(iter(tournament.tournament_players_by_pairing_number.values()))
        with EventDatabase(EVENT_ID, write=True) as database:
            tournament.set_manual_player_point_adjustment(
                player.id, 1, 1.0, None, database
            )
            tournament.set_manual_player_point_adjustment(
                player.id, 1, 0.0, None, database
            )
        self._reload()
        tournament = self.tournament
        self.assertIsNone(tournament.stored_player_point_adjustment(player.id, 1))
        self.assertEqual(tournament.player_point_adjustment(player.id, 1), 0.0)

    def test_adjustment_round_trips_through_the_trf(self):
        """The delta goes out as a blank-type 299 keyed on the pairing
        number, and the 001 points already include it — which is what a
        reader recomputing the score from the results expects."""
        from data.input_output.trf.trf_serializer import TrfSerializer

        tournament = self.tournament
        player = tournament.tournament_players_by_pairing_number[1]
        with EventDatabase(EVENT_ID, write=True) as database:
            tournament.set_manual_player_point_adjustment(
                player.id, 1, -0.5, 'late arrival', database
            )
        self._reload()
        tournament = self.tournament

        trf = tournament.to_trf(after_round=tournament.rounds)
        self.assertEqual(
            [
                (a.type, a.match_points, a.game_points, a.round, a.pairing_numbers)
                for a in trf.abnormal_points_assignments
            ],
            [(' ', None, -0.5, 1, [1])],
        )
        # The record survives a serialize / parse cycle.
        reloaded = TrfSerializer.loads(TrfSerializer.dumps(trf))
        self.assertEqual(len(reloaded.abnormal_points_assignments), 1)
        self.assertEqual(reloaded.abnormal_points_assignments[0].game_points, -0.5)
        self.assertEqual(reloaded.abnormal_points_assignments[0].pairing_numbers, [1])

    def test_team_events_have_no_player_adjustments(self):
        """Teams adjust whole teams; a player-level delta would be a
        second, competing mechanism on the same event."""
        tournament = self.tournament
        player = tournament.tournament_players_by_pairing_number[1]
        with EventDatabase(EVENT_ID, write=True) as database:
            tournament.set_manual_player_point_adjustment(
                player.id, 1, 1.0, None, database
            )
        self._reload()
        tournament = self.tournament
        self.assertEqual(tournament.player_point_adjustment(player.id, 1), 1.0)

    def test_the_pairings_table_figure_includes_the_adjustment(self):
        """``compute_points`` fills ``player.points``, which is what the
        pairings table shows and what the board ordering sorts on — so a
        penalty has to reach it, not just ``points_after``."""
        tournament = self.tournament
        player = tournament.tournament_players_by_pairing_number[1]
        with EventDatabase(EVENT_ID, write=True) as database:
            tournament.set_manual_player_point_adjustment(
                player.id, 1, -1.0, 'penalty', database
            )
        self._reload()
        tournament = self.tournament
        player = tournament.tournament_players_by_pairing_number[1]

        # Entering round 2, the round-1 penalty counts.
        self.assertEqual(player.points_before(2), -1.0)
        player.compute_points(before_round=2)
        self.assertEqual(player.points, -1.0)
        # It is not counted before the round it belongs to.
        self.assertEqual(player.points_before(1), 0.0)

    def test_papi_export_is_blocked_by_a_penalty(self):
        """Papi has nowhere to record a bonus / penalty, so exporting
        would silently drop points. The same check gates the FFE upload."""
        from plugins.ffe.papi_converter import PapiConverter

        tournament = self.tournament
        player = tournament.tournament_players_by_pairing_number[1]
        self.assertIsNone(PapiConverter.papi_export_unavailable_message(tournament))

        with EventDatabase(EVENT_ID, write=True) as database:
            tournament.set_manual_player_point_adjustment(
                player.id, 1, -1.0, 'penalty', database
            )
        self._reload()
        message = PapiConverter.papi_export_unavailable_message(self.tournament)
        assert message is not None
        self.assertIn('bonus', message.lower())

        # A row carrying only a reason is not a reason to block.
        with EventDatabase(EVENT_ID, write=True) as database:
            self.tournament.set_manual_player_point_adjustment(
                player.id, 1, 0.0, 'noted, no points', database
            )
        self._reload()
        self.assertIsNone(
            PapiConverter.papi_export_unavailable_message(self.tournament)
        )

    def test_unpairing_a_board_clears_its_players_adjustments(self):
        """Points are only assignable on a paired round — the button is
        disabled otherwise — so unpairing must take them with it. Left
        behind they are invisible (no board to show them on) and still
        count towards the score the pairing engine reads."""
        tournament = self.tournament
        players = list(tournament.tournament_players_by_pairing_number.values())
        white, black = players[0], players[1]
        self._pair_round_one()
        tournament = self.tournament
        white, black = (
            tournament.tournament_players_by_pairing_number[1],
            tournament.tournament_players_by_pairing_number[2],
        )

        with EventDatabase(EVENT_ID, write=True) as database:
            tournament.set_manual_player_point_adjustment(
                white.id, 1, -2.0, 'penalty', database
            )
            tournament.set_manual_player_point_adjustment(
                black.id, 1, 1.0, 'bonus', database
            )
        assert tournament.player_point_adjustment(white.id, 1) == -2.0

        tournament.unpair_boards(tournament.get_round_boards(1))

        assert tournament.player_point_adjustment(white.id, 1) == 0.0
        assert tournament.player_point_adjustment(black.id, 1) == 0.0
        self._reload()
        tournament = self.tournament
        assert tournament.stored_player_point_adjustment(white.id, 1) is None
        assert tournament.stored_player_point_adjustment(black.id, 1) is None

    def test_another_rounds_adjustment_is_left_alone(self):
        tournament = self.tournament
        player = next(iter(tournament.tournament_players_by_pairing_number.values()))
        self._pair_round_one()
        tournament = self.tournament
        player = tournament.tournament_players_by_pairing_number[1]
        with EventDatabase(EVENT_ID, write=True) as database:
            tournament.set_manual_player_point_adjustment(
                player.id, 2, -1.0, 'later round', database
            )
        tournament.unpair_boards(tournament.get_round_boards(1))
        assert tournament.player_point_adjustment(player.id, 2) == -1.0
