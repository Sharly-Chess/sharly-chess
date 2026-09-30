"""FIDE mode, the warning levels it drives, and the log of the pairing
integrity breaching events (PIBEs) it keeps in the TRF."""

from unittest import TestCase

import pytest

from data.event import Event
from data.input_output.trf.trf_export import TrfExport
from data.input_output.trf.trf_serializer import TrfSerializer
from data.loader import EventLoader
from data.pairings.systems import RoundRobinPairingSystem, SwissPairingSystem
from data.permissions import (
    PairingAction,
    RoundStatus,
    WarningLevel,
    starts_manual_pairing,
)
from data.pibes import (
    Pibe,
    PibeType,
    describe_round_changes,
    fide_mode_exit_trf_comment,
    round_snapshot,
)
from database.sqlite.event.event_database import EventDatabase
from tests.test_config import TestUtils
from utils.enum import Result

EVENT_ID = 'test-fide-mode-event'
TOURNAMENT_ID = 'test-fide-mode-tournament'


@pytest.mark.unit
class WarningLevelTestCase(TestCase):
    def test_a_fide_prohibited_action_asks_for_confirmation_outside_fide_mode(self):
        level = WarningLevel.FIDE_PROHIBITED

        self.assertEqual(level.effective(fide_mode=True), WarningLevel.FIDE_PROHIBITED)
        self.assertEqual(level.effective(fide_mode=False), WarningLevel.CONFIRMATION)

    def test_other_levels_do_not_depend_on_fide_mode(self):
        for level in WarningLevel:
            if level != WarningLevel.FIDE_PROHIBITED:
                self.assertEqual(level.effective(fide_mode=False), level)

    def test_an_information_runs_without_asking(self):
        self.assertFalse(WarningLevel.NONE.asks_user)
        self.assertFalse(WarningLevel.INFORMATION.asks_user)
        self.assertTrue(WarningLevel.CONFIRMATION.asks_user)
        self.assertTrue(WarningLevel.DOUBLE_CONFIRMATION.asks_user)

    def test_a_past_round_cannot_be_unlocked_in_fide_mode(self):
        handler = SwissPairingSystem().permission_handler

        self.assertNotIn(
            PairingAction.RESULT_UPDATE,
            handler.allowed_actions(
                RoundStatus.PAST, WarningLevel.CONFIRMATION, fide_mode=True
            ),
        )
        self.assertIn(
            PairingAction.RESULT_UPDATE,
            handler.allowed_actions(
                RoundStatus.PAST, WarningLevel.CONFIRMATION, fide_mode=False
            ),
        )

    def test_the_current_round_is_unlocked_by_a_manual_pairing_in_fide_mode(self):
        handler = SwissPairingSystem().permission_handler

        self.assertNotIn(
            PairingAction.COLOR_PERMUTE,
            handler.allowed_actions(RoundStatus.CURRENT, WarningLevel.NONE, True),
        )
        self.assertIn(
            PairingAction.COLOR_PERMUTE,
            handler.allowed_actions(
                RoundStatus.CURRENT, WarningLevel.CONFIRMATION, True
            ),
        )
        self.assertFalse(handler.confirmation_unlocks_round(RoundStatus.CURRENT, True))
        self.assertTrue(handler.confirmation_unlocks_round(RoundStatus.CURRENT, False))
        for status in (RoundStatus.CURRENT, RoundStatus.NEXT):
            self.assertTrue(
                starts_manual_pairing(PairingAction.MANUAL_PAIRING, status, True)
            )
        self.assertFalse(
            starts_manual_pairing(
                PairingAction.MANUAL_PAIRING, RoundStatus.CURRENT, False
            )
        )
        self.assertFalse(
            starts_manual_pairing(
                PairingAction.RESULT_UPDATE, RoundStatus.CURRENT, True
            )
        )

    def test_each_correction_of_the_previous_round_is_confirmed_in_fide_mode(self):
        handler = SwissPairingSystem().permission_handler

        self.assertFalse(handler.confirmation_unlocks_round(RoundStatus.PREVIOUS, True))
        self.assertTrue(handler.confirmation_unlocks_round(RoundStatus.PREVIOUS, False))

    def test_unpairing_the_current_round_is_allowed_in_fide_mode(self):
        handler = SwissPairingSystem().permission_handler

        self.assertEqual(
            handler.required_level(RoundStatus.CURRENT, PairingAction.FULL_UNPAIRING),
            WarningLevel.CONFIRMATION,
        )

    def test_only_swiss_systems_support_fide_mode(self):
        self.assertTrue(SwissPairingSystem().supports_fide_mode)
        self.assertFalse(RoundRobinPairingSystem().supports_fide_mode)


@pytest.mark.unit
class PibeTestCase(TestCase):
    def test_trf_comments(self):
        self.assertEqual(
            Pibe(PibeType.CORRECTION, 4, '6-17: 1-0 => 0-1').trf_comment,
            'Correction @ Round 4: result of 6-17 changed from 1-0 to 0-1',
        )
        self.assertEqual(
            Pibe(PibeType.CORRECTION, 4, '6-17: --- => *').trf_comment,
            'Correction @ Round 4: result of 6-17 cleared (was 0F-0F)',
        )
        self.assertEqual(
            Pibe(PibeType.CORRECTION, 4, '6-17 => 17-6').trf_comment,
            'Correction @ Round 4: colours of 17-6 swapped',
        )
        self.assertEqual(
            Pibe(PibeType.MPA, 5, '12-3 9-4 => 12-4 9-3').trf_comment,
            "MPA @ Round 5: 12-4, 9-3 instead of the engine's 12-3, 9-4",
        )
        self.assertEqual(fide_mode_exit_trf_comment(3), 'FIDE mode exited @ Round 3')

    def test_a_result_change(self):
        self.assertEqual(
            describe_round_changes({'6-17': '1-0'}, {'6-17': '0-1'}),
            '6-17: 1-0 => 0-1',
        )

    def test_a_pairing_change(self):
        self.assertEqual(
            describe_round_changes(
                {'19-7': '', '21-33': '', '44=PAB': ''},
                {'19-33': '', '21-44': '', '7=FPB': ''},
            ),
            '19-7 21-33 44=PAB => 19-33 21-44 7=FPB',
        )

    def test_nothing_changed(self):
        self.assertEqual(describe_round_changes({'1-2': '1-0'}, {'1-2': '1-0'}), '')


@pytest.mark.unit
class TournamentFideModeTestCase(TestCase):
    def setUp(self) -> None:
        TestUtils.create_event(EVENT_ID)
        TestUtils.create_tournament(EVENT_ID, TOURNAMENT_ID, json_file='tec-swiss')

    def tearDown(self) -> None:
        TestUtils.delete_event(EVENT_ID)

    @property
    def tournament(self):
        # The tournament keeps only a weak reference to its event.
        self._event: Event = EventLoader().load_event(EVENT_ID)
        return self._event.tournaments_by_name[TOURNAMENT_ID]

    def test_a_swiss_tournament_starts_in_fide_mode(self):
        tournament = self.tournament

        self.assertTrue(tournament.fide_mode)
        self.assertFalse(tournament.left_fide_mode)
        self.assertIsNone(tournament.fide_mode_exit_round)

    def test_leaving_fide_mode_is_recorded_at_the_current_round(self):
        tournament = self.tournament
        current_round = tournament.current_round
        tournament.leave_fide_mode()

        tournament = self.tournament
        self.assertFalse(tournament.fide_mode)
        self.assertTrue(tournament.left_fide_mode)
        self.assertTrue(tournament.leaving_fide_mode_is_final)
        self.assertEqual(tournament.fide_mode_exit_round, current_round)

    def test_the_trf_logs_the_pibes_and_the_exit_from_fide_mode(self):
        tournament = self.tournament
        tournament.log_pibe(Pibe(PibeType.CORRECTION, 2, '1-2: 1-0 => 0-1'))
        tournament.leave_fide_mode()
        exit_round = tournament.fide_mode_exit_round
        assert exit_round is not None

        trf = TrfSerializer.dumps(TrfExport(self.tournament).build())

        self.assertIn(
            '### Correction @ Round 2: result of 1-2 changed from 1-0 to 0-1\n', trf
        )
        self.assertIn(f'### {fide_mode_exit_trf_comment(exit_round)}\n', trf)

    def test_a_result_correction_is_described_by_pairing_numbers(self):
        tournament = self.tournament
        board = next(
            board
            for board in tournament.get_round_boards(1)
            if board.black_tournament_player is not None and board.result == Result.WIN
        )
        white = board.white_tournament_player.pairing_number
        black = board.black_tournament_player.pairing_number
        before = round_snapshot(tournament, 1)

        tournament.add_result(board, Result.DRAW)

        description = describe_round_changes(before, round_snapshot(self.tournament, 1))
        self.assertEqual(description, f'{white}-{black}: 1-0 => =-=')
        self.assertTrue(description.isascii())


@pytest.mark.unit
class PibeSummaryTestCase(TestCase):
    def setUp(self) -> None:
        TestUtils.create_event(EVENT_ID)
        TestUtils.create_tournament(EVENT_ID, TOURNAMENT_ID, json_file='tec-swiss')
        self._event: Event = EventLoader().load_event(EVENT_ID)
        self.tournament = self._event.tournaments_by_name[TOURNAMENT_ID]

    def tearDown(self) -> None:
        TestUtils.delete_event(EVENT_ID)

    def summary(self, type_: PibeType, description: str) -> str:
        return Pibe(type_, 3, description).summary(self.tournament, 'en')

    def name(self, number: int) -> str:
        return self.tournament.tournament_players_by_pairing_number[number].full_name

    def test_a_result_correction_names_the_players(self):
        self.assertEqual(
            self.summary(PibeType.CORRECTION, '6-7: 1-0 => =-='),
            f'Result of {self.name(6)} – {self.name(7)} changed from 1-0 to ½-½.',
        )

    def test_forfeits_read_as_on_the_result_buttons(self):
        self.assertEqual(
            self.summary(PibeType.CORRECTION, '6-7: 0-1 => ---'),
            f'Result of {self.name(6)} – {self.name(7)} changed from 0-1 to F-F.',
        )
        self.assertEqual(
            self.summary(PibeType.CORRECTION, '6-7: 1-0 => +--'),
            f'Result of {self.name(6)} – {self.name(7)} changed from 1-0 to 1-F.',
        )

    def test_a_cleared_result_gives_the_former_one(self):
        self.assertEqual(
            self.summary(PibeType.CORRECTION, '6-7: --- => *'),
            f'Result of {self.name(6)} – {self.name(7)} cleared (previously F-F).',
        )

    def test_an_entered_result_is_given(self):
        self.assertEqual(
            self.summary(PibeType.CORRECTION, '6-7: * => =-='),
            f'Result of {self.name(6)} – {self.name(7)} entered: ½-½.',
        )

    def test_swapped_colours_are_named_as_such(self):
        self.assertEqual(
            self.summary(PibeType.CORRECTION, '6-7 => 7-6'),
            f'Colours of {self.name(7)} – {self.name(6)} swapped.',
        )

    def test_a_few_pairings_are_named(self):
        self.assertEqual(
            self.summary(PibeType.MPA, '1-2 3=PAB => 1-3 2=PAB'),
            'Pairings edited by hand and validated although they differ from '
            f'those of the pairing engine: {self.name(1)} – {self.name(3)}, '
            f'{self.name(2)} (PAB) instead of {self.name(1)} – {self.name(2)}, '
            f'{self.name(3)} (PAB).',
        )

    def test_many_pairings_are_counted(self):
        self.assertTrue(
            self.summary(
                PibeType.IMPORT, '1-2 3-4 5-6 7-8 => 1-3 2-4 5-7 6-8'
            ).endswith(': 4 boards differ.')
        )

    def test_settings_changes(self):
        self.assertEqual(
            self.summary(PibeType.ROUNDS, '9 => 10'),
            'Number of rounds changed from 9 to 10.',
        )
        self.assertEqual(
            self.summary(PibeType.TIE_BREAKS, 'PTS OTHER_PAPI_BUCHHOLZ => PTS BH'),
            'Tie-breaks changed from Points, PAPI_BUCHHOLZ to Points, Buchholz.',
        )

    def test_the_log_follows_the_players_when_the_numbers_change(self):
        players = self.tournament.tournament_players_by_pairing_number
        sixth, seventh = players[6], players[7]
        self.tournament.log_pibe(Pibe(PibeType.CORRECTION, 3, '6-7: 1-0 => 0-1'))
        with EventDatabase(EVENT_ID, write=True) as database:
            for player, number in ((sixth, 7), (seventh, 6)):
                player.stored_tournament_player.pairing_number = number
                database.set_tournament_player_pairing_number(
                    player.stored_tournament_player
                )

        self._event = EventLoader().load_event(EVENT_ID)
        tournament = self._event.tournaments_by_name[TOURNAMENT_ID]
        pibe = tournament.pibes[-1]

        self.assertEqual(
            pibe.summary(tournament, 'en'),
            f'Result of {sixth.full_name} – {seventh.full_name} '
            'changed from 1-0 to 0-1.',
        )
        self.assertEqual(
            pibe.trf_comment_for(tournament),
            'Correction @ Round 3: result of 7-6 changed from 1-0 to 0-1',
        )
