"""Editing a round-robin's schedule: a draft changed seat by seat, saved
only when it keeps the round-robin rules, then paired; the games already
played cannot change, and a player joining before the first result is
paired in."""

import contextlib
from unittest import TestCase

import pytest

from data.event import Event
from data.loader import EventLoader
from data.pairings.engines import RoundRobinPairingEngine
from data.pairings.round_robin_editor import RoundRobinScheduleEditor
from data.pairings.round_robin_schedule import REST
from data.pairings.settings import BergerNumbersSetting
from data.pairings.variations import (
    BergerRoundRobinVariation,
    CustomRoundRobinVariation,
    CustomTeamRoundRobinVariation,
)
from database.sqlite.event.event_database import EventDatabase
from database.sqlite.event.event_store import (
    StoredPlayer,
    StoredTeam,
    StoredTournamentPlayer,
)
from tests.test_config import TestUtils
from utils.enum import EventType, Result

EVENT_ID = 'test-rr-schedule-editor-event'
TOURNAMENT_ID = 'test-rr-schedule-editor-tournament'


@pytest.mark.unit
class RoundRobinScheduleEditorTestCase(TestCase):
    def setUp(self) -> None:
        TestUtils.create_event(EVENT_ID)
        TestUtils.create_tournament(
            EVENT_ID,
            TOURNAMENT_ID,
            overrides={'pairing': CustomRoundRobinVariation.static_id()},
        )
        for index in range(5):
            self._add_player(f'Player{index + 1}')

    def tearDown(self) -> None:
        TestUtils.delete_event(EVENT_ID)

    def _add_player(self, last_name: str) -> None:
        event = EventLoader().load_event(EVENT_ID)
        event.add_player(
            StoredPlayer(id=None, last_name=last_name),
            [event.tournaments_by_name[TOURNAMENT_ID]],
        )

    @property
    def tournament(self):
        # The tournament keeps only a weak reference to its event.
        self._event: Event = EventLoader().load_event(EVENT_ID)
        return self._event.tournaments_by_name[TOURNAMENT_ID]

    @property
    def editor(self) -> RoundRobinScheduleEditor:
        return RoundRobinScheduleEditor(self.tournament)

    def _save_berger_schedule(self) -> None:
        self.editor.start()
        self.assertIsNone(self.editor.fill_from_berger_tables())
        self.assertIsNone(self.editor.save())

    def _pairs(self, round_: int) -> set[tuple[int | None, int | None]]:
        return {
            (board.stored_board.white_player_id, board.stored_board.black_player_id)
            for board in self.tournament.get_round_boards(round_)
        }

    def test_a_custom_schedule_starts_empty_and_cannot_be_saved_so(self) -> None:
        editor = self.editor
        self.assertTrue(editor.must_edit)
        self.assertTrue(editor.editing)
        draft = editor.draft
        self.assertEqual(len(draft.rounds), 5)
        self.assertTrue(
            all(
                table == (None, None)
                for schedule_round in draft.rounds.values()
                for table in schedule_round.tables
            )
        )
        self.assertIsNotNone(self.editor.save())
        self.assertFalse(self.tournament.has_pairings)

    def test_saving_pairs_every_round_from_the_schedule(self) -> None:
        self._save_berger_schedule()
        tournament = self.tournament
        schedule = tournament.round_robin_schedule
        assert schedule is not None
        self.assertIsNone(tournament.round_robin_schedule_draft)
        self.assertEqual(tournament.current_round, 1)
        self.assertTrue(tournament.has_pairings)
        for round_, schedule_round in schedule.rounds.items():
            self.assertEqual(
                self._pairs(round_),
                {*schedule_round.tables, (schedule_round.rest, None)},
            )

    def test_editing_changes_the_unplayed_games(self) -> None:
        self._save_berger_schedule()
        self.editor.start()
        draft = self.editor.draft
        first, second = draft.rounds[1].tables[0]
        third, fourth = draft.rounds[2].tables[0]
        # Swapping round 1 and round 2 keeps the round-robin rules.
        for table, (white, black) in enumerate(draft.rounds[2].tables):
            self.assertIsNone(self.editor.place(1, (table, 0), white))
            self.assertIsNone(self.editor.place(1, (table, 1), black))
        self.assertIsNone(self.editor.place(1, (REST, 0), draft.rounds[2].rest))
        for table, (white, black) in enumerate(draft.rounds[1].tables):
            self.assertIsNone(self.editor.place(2, (table, 0), white))
            self.assertIsNone(self.editor.place(2, (table, 1), black))
        self.assertIsNone(self.editor.place(2, (REST, 0), draft.rounds[1].rest))
        self.assertIsNone(self.editor.save())
        self.assertIn((third, fourth), self._pairs(1))
        self.assertIn((first, second), self._pairs(2))

    def test_played_games_cannot_be_changed(self) -> None:
        self._save_berger_schedule()
        tournament = self.tournament
        board = tournament.get_round_boards(1)[0]
        tournament.add_result(board, Result.WIN)
        editor = self.editor
        editor.start()
        white = board.stored_board.white_player_id
        assert white is not None
        self.assertEqual(editor.locked_tables(1), {0})
        self.assertIsNotNone(editor.place(1, (1, 0), white))
        self.assertIsNotNone(editor.place(1, (0, 0), None))
        self.assertIsNotNone(editor.swap_colours(1, 0))
        self.assertIsNotNone(editor.fill_from_berger_tables())
        editor.clear()
        self.assertEqual(
            self.editor.draft.rounds[1].tables[0],
            (white, board.stored_board.black_player_id),
        )
        self.assertIsNone(self.editor.place(2, (0, 0), white))

    def test_an_unpaired_custom_tournament_is_edited_again(self) -> None:
        self._save_berger_schedule()
        self.assertFalse(self.editor.must_edit)
        tournament = self.tournament
        tournament.board_operations.unpair(list(tournament.boards_by_id.values()))
        editor = self.editor
        self.assertTrue(editor.must_edit)
        self.assertEqual(editor.draft, self.tournament.round_robin_schedule)

    def _enter_round_1_results(self, *results: Result) -> list[tuple[int, int]]:
        """Enter *results* on the games of round 1, in board order; returns
        their pairs."""
        tournament = self.tournament
        games = [
            board
            for board in tournament.get_round_boards(1)
            if board.stored_board.black_player_id is not None
        ]
        pairs: list[tuple[int, int]] = []
        for board, result in zip(games, results, strict=True):
            tournament.add_result(board, result)
            white = board.stored_board.white_player_id
            black = board.stored_board.black_player_id
            assert white is not None and black is not None
            pairs.append((white, black))
        return pairs

    def test_a_schedule_breaking_the_rules_is_forced_only_once_results_exist(
        self,
    ) -> None:
        self._save_berger_schedule()
        editor = self.editor
        editor.start()
        editor.swap_colours(2, 0)
        editor.swap_colours(3, 0)
        violations = self.editor.violations()
        self.assertTrue(violations)
        self.assertFalse(self.editor.can_force(violations))
        self.assertIsNotNone(self.editor.save(force=True))

        self._enter_round_1_results(Result.DRAW, Result.DRAW)
        editor = self.editor
        violations = editor.violations()
        self.assertTrue(editor.can_force(violations))
        self.assertIsNotNone(editor.save())
        self.assertIsNone(editor.save(force=True))

        # The log lists each rule the saved schedule breaks, and the TRF has
        # a comment for each.
        tournament = self.tournament
        breaches = tournament.schedule_breaches
        self.assertEqual(
            [breach.summary(tournament) for breach in breaches],
            [violation.message for violation in violations],
        )
        self.assertEqual(tournament.pibes, [])
        self.assertTrue(set(breaches) <= set(tournament.log_entries))
        self.assertTrue(
            all(
                breach.trf_comment_for(tournament).startswith(
                    f'Schedule @ Round {breach.round_}: '
                )
                for breach in breaches
            )
        )

        # Saved anyway again, the same rules are listed once.
        editor = self.editor
        editor.start()
        self.assertIsNone(self.editor.save(force=True))
        self.assertEqual(self.tournament.schedule_breaches, breaches)

        # Saved keeping the rules, nothing is listed any more.
        editor = self.editor
        editor.start()
        editor.swap_colours(2, 0)
        editor.swap_colours(3, 0)
        self.assertEqual(self.editor.violations(), [])
        self.assertIsNone(self.editor.save())
        tournament = self.tournament
        self.assertEqual(tournament.schedule_breaches, [])
        self.assertEqual(tournament.log_entries, [])

    def test_an_empty_seat_cannot_be_forced(self) -> None:
        self._save_berger_schedule()
        self._enter_round_1_results(Result.DRAW, Result.DRAW)
        editor = self.editor
        editor.start()
        editor.place(2, (0, 0), None)
        violations = self.editor.violations()
        self.assertFalse(self.editor.can_force(violations))
        self.assertIsNotNone(self.editor.save(force=True))

    def test_games_played_at_the_wrong_boards_are_corrected(self) -> None:
        self._save_berger_schedule()
        (first, second), (third, fourth) = self._enter_round_1_results(
            Result.WIN, Result.WIN
        )
        tournament = self.tournament
        editor = RoundRobinScheduleEditor(tournament)
        editor.start()
        self.assertEqual(editor.locked_tables(1), {0, 1})
        self.assertIsNotNone(editor.place(1, (0, 1), fourth))

        editor = RoundRobinScheduleEditor(tournament, played_games_unlocked=True)
        self.assertEqual(editor.locked_tables(1), set())
        # The first player really played the fourth, and the third the
        # second: their results agree, so they are kept.
        self.assertIsNone(editor.place(1, (0, 1), fourth))
        self.assertIsNone(editor.place(1, (1, 1), second))
        self.assertIsNone(editor.save(force=True))
        self.assertEqual(editor.results_to_enter, [])

        results = {
            (board.stored_board.white_player_id, board.stored_board.black_player_id): (
                board.result
            )
            for board in self.tournament.get_round_boards(1)
        }
        self.assertEqual(results[first, fourth], Result.WIN)
        self.assertEqual(results[third, second], Result.WIN)

    def test_disagreeing_results_of_corrected_games_are_entered_again(self) -> None:
        self._save_berger_schedule()
        (_first, second), (_third, fourth) = self._enter_round_1_results(
            Result.WIN, Result.DRAW
        )
        editor = RoundRobinScheduleEditor(self.tournament, played_games_unlocked=True)
        editor.start()
        self.assertIsNone(editor.place(1, (0, 1), fourth))
        self.assertIsNone(editor.place(1, (1, 1), second))
        self.assertIsNone(editor.save(force=True))
        self.assertEqual(editor.results_to_enter, [1])


BERGER_EVENT_ID = 'test-berger-rr-schedule-editor-event'
BERGER_TOURNAMENT_ID = 'test-berger-rr-schedule-editor-tournament'


@pytest.mark.unit
class BergerRoundRobinScheduleEditorTestCase(TestCase):
    """A Berger tournament is paired from the tables; its schedule can be
    edited once paired, and turns custom when it no longer follows them."""

    def setUp(self) -> None:
        TestUtils.create_event(BERGER_EVENT_ID)
        TestUtils.create_tournament(
            BERGER_EVENT_ID,
            BERGER_TOURNAMENT_ID,
            overrides={'pairing': BergerRoundRobinVariation.static_id()},
        )
        event = EventLoader().load_event(BERGER_EVENT_ID)
        for index in range(4):
            event.add_player(
                StoredPlayer(id=None, last_name=f'Player{index + 1}'),
                [event.tournaments_by_name[BERGER_TOURNAMENT_ID]],
            )

    def tearDown(self) -> None:
        TestUtils.delete_event(BERGER_EVENT_ID)

    @property
    def tournament(self):
        # The tournament keeps only a weak reference to its event.
        self._event: Event = EventLoader().load_event(BERGER_EVENT_ID)
        return self._event.tournaments_by_name[BERGER_TOURNAMENT_ID]

    def _pair(self) -> None:
        tournament = self.tournament
        for round_ in range(1, tournament.rounds + 1):
            self.assertEqual(tournament.generate_round_pairings(round_), '')

    def test_the_schedule_is_edited_once_paired(self) -> None:
        editor = RoundRobinScheduleEditor(self.tournament)
        self.assertFalse(editor.must_edit)
        self.assertFalse(editor.can_start)
        self._pair()
        self.assertTrue(RoundRobinScheduleEditor(self.tournament).can_start)

    def test_saving_the_berger_tables_keeps_the_variation(self) -> None:
        self._pair()
        editor = RoundRobinScheduleEditor(self.tournament)
        editor.start()
        self.assertIsNone(editor.save())
        self.assertEqual(
            self.tournament.pairing_variation.id, BergerRoundRobinVariation.static_id()
        )

    def test_another_schedule_turns_the_tournament_custom(self) -> None:
        self._pair()
        editor = RoundRobinScheduleEditor(self.tournament)
        editor.start()
        draft = editor.draft
        # Round 1 and 3 swapped keep the round-robin rules.
        for round_, source in ((1, 3), (3, 1)):
            for table, (white, black) in enumerate(draft.rounds[source].tables):
                self.assertIsNone(editor.place(round_, (table, 0), white))
                self.assertIsNone(editor.place(round_, (table, 1), black))
        self.assertEqual(editor.violations(), [])
        self.assertIsNone(editor.save())
        tournament = self.tournament
        self.assertEqual(
            tournament.pairing_variation.id, CustomRoundRobinVariation.static_id()
        )
        self.assertFalse(RoundRobinScheduleEditor(tournament).must_edit)

    def test_the_berger_numbers_of_players_who_left_are_dropped(self) -> None:
        tournament = self.tournament
        player_ids = sorted(player.id for player in tournament.tournament_players)
        # The player numbered 3 has left the tournament.
        numbers = dict(
            zip([*player_ids[:2], 999, *player_ids[2:]], range(1, 6), strict=True)
        )
        tournament.update_pairing_settings(
            tournament.stored_pairing_settings
            | {
                BergerNumbersSetting.static_id(): BergerNumbersSetting.to_stored_value(
                    numbers
                )
            }
        )
        tournament = self.tournament
        engine = tournament.pairing_variation.engine
        assert isinstance(engine, RoundRobinPairingEngine)
        self.assertEqual(
            engine.berger_numbered_members(tournament),
            dict(enumerate(player_ids, 1)),
        )
        self.assertEqual(len(RoundRobinScheduleEditor(tournament).member_options), 4)


TEAM_EVENT_ID = 'test-team-rr-schedule-editor-event'
TEAM_TOURNAMENT_ID = 'test-team-rr-schedule-editor-tournament'
TEAMS = 4
TEAM_SIZE = 2


@pytest.mark.unit
class TeamRoundRobinScheduleEditorTestCase(TestCase):
    """A team round-robin keeps pairing its members round by round, each
    round's matches read from the saved schedule; a round once paired
    cannot be changed in the schedule."""

    def setUp(self) -> None:
        TestUtils.create_event(TEAM_EVENT_ID, overrides={'event_type': EventType.TEAM})
        TestUtils.create_tournament(
            TEAM_EVENT_ID,
            TEAM_TOURNAMENT_ID,
            overrides={
                'team_player_count': TEAM_SIZE,
                'pairing': CustomTeamRoundRobinVariation.static_id(),
            },
        )
        with EventDatabase(TEAM_EVENT_ID, write=True) as database:
            tournament_id = next(
                stored_tournament.id
                for stored_tournament in database.load_stored_tournaments()
                if stored_tournament.name == TEAM_TOURNAMENT_ID
            )
            assert tournament_id is not None
            for seed in range(1, TEAMS + 1):
                team_id = database.add_stored_team(
                    StoredTeam(
                        id=None,
                        name=f'Team{seed}',
                        tournament_id=tournament_id,
                        pairing_number=seed,
                        check_in=True,
                    )
                )
                for index in range(TEAM_SIZE):
                    player_id = database.add_stored_player(
                        StoredPlayer(
                            id=None,
                            last_name=f'T{seed}P{index}',
                            team_id=team_id,
                            team_index=index,
                            check_in=True,
                        )
                    )
                    database.add_stored_tournament_player(
                        StoredTournamentPlayer(
                            tournament_id=tournament_id,
                            player_id=player_id,
                            pairing_number=index,
                        )
                    )

    def tearDown(self) -> None:
        TestUtils.delete_event(TEAM_EVENT_ID)

    @property
    def tournament(self):
        with contextlib.suppress(KeyError):
            EventLoader.unload_event(TEAM_EVENT_ID)
        # The tournament keeps only a weak reference to its event.
        self._event: Event = EventLoader().load_event(TEAM_EVENT_ID)
        return self._event.tournaments_by_name[TEAM_TOURNAMENT_ID]

    def test_rounds_are_paired_from_the_saved_schedule(self) -> None:
        tournament = self.tournament
        self.assertIsNotNone(
            tournament.pairing_variation.engine.invalid_player_count_message(tournament)
        )
        editor = RoundRobinScheduleEditor(tournament)
        editor.start()
        self.assertIsNone(editor.fill_from_berger_tables())
        # Reverse the rounds so that the schedule is not the Berger one.
        draft = editor.draft
        last = len(draft.rounds)
        for round_ in range(1, last + 1):
            for table, (first, second) in enumerate(
                draft.rounds[last + 1 - round_].tables
            ):
                self.assertIsNone(editor.place(round_, (table, 0), first))
                self.assertIsNone(editor.place(round_, (table, 1), second))
        self.assertIsNone(editor.save())

        tournament = self.tournament
        schedule = tournament.round_robin_schedule
        assert schedule is not None
        self.assertFalse(tournament.has_pairings)
        self.assertEqual(tournament.generate_round_pairings(1), '')

        tournament = self.tournament
        self.assertEqual(
            {
                (
                    team_board.stored_team_board.team_a_id,
                    team_board.stored_team_board.team_b_id,
                )
                for team_board in tournament.get_round_team_boards(1)
            },
            set(schedule.rounds[1].tables),
        )
        editor = RoundRobinScheduleEditor(tournament)
        editor.start()
        self.assertTrue(editor.round_locked(1))
        first = schedule.rounds[2].tables[0][0]
        assert first is not None
        self.assertIsNotNone(editor.place(1, (0, 0), first))
        self.assertIsNone(editor.swap_colours(2, 0))
