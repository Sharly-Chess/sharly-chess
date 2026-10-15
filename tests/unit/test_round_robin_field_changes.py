"""Players and teams joining or leaving a round-robin.

A Berger round-robin is paired whole from the tables, so players join it
before it is paired; the round count then follows the field. A custom
round-robin takes players until its first result: its pairings are then
removed and its schedule goes back to its editing, keeping what still
fits. A team round-robin takes teams until a round is paired."""

import contextlib
from unittest import TestCase

import pytest

from data.event import Event
from data.loader import EventLoader
from data.pairings.engines import RoundRobinPairingEngine
from data.pairings.round_robin_editor import RoundRobinScheduleEditor
from data.pairings.round_robin_schedule import REST
from data.pairings.variations import (
    BergerRoundRobinVariation,
    BergerTeamRoundRobinVariation,
    CustomRoundRobinVariation,
    CustomTeamRoundRobinVariation,
)
from data.tournament import Tournament
from database.sqlite.event.event_database import EventDatabase
from database.sqlite.event.event_store import (
    StoredPlayer,
    StoredTeam,
    StoredTournamentPlayer,
)
from tests.test_config import TestUtils
from utils.enum import EventType, Result

EVENT_ID = 'test-rr-field-changes-event'
TOURNAMENT_NAME = 'test-rr-field-changes-tournament'


class RoundRobinTestCase(TestCase):
    variation_id: str

    def setUp(self) -> None:
        TestUtils.create_event(EVENT_ID)
        TestUtils.create_tournament(
            EVENT_ID, TOURNAMENT_NAME, overrides={'pairing': self.variation_id}
        )
        for index in range(self.player_count):
            self._add_player(f'Player{index + 1}')

    def tearDown(self) -> None:
        TestUtils.delete_event(EVENT_ID)

    player_count = 4

    def _add_player(self, last_name: str) -> None:
        event = EventLoader().load_event(EVENT_ID)
        event.add_player(
            StoredPlayer(id=None, last_name=last_name),
            [event.tournaments_by_name[TOURNAMENT_NAME]],
        )

    @property
    def tournament(self) -> Tournament:
        # The tournament keeps only a weak reference to its event.
        self._event: Event = EventLoader().load_event(EVENT_ID)
        return self._event.tournaments_by_name[TOURNAMENT_NAME]

    @property
    def editor(self) -> RoundRobinScheduleEditor:
        return RoundRobinScheduleEditor(self.tournament)

    @staticmethod
    def _engine(tournament: Tournament) -> RoundRobinPairingEngine:
        engine = tournament.pairing_variation.engine
        assert isinstance(engine, RoundRobinPairingEngine)
        return engine

    def _enter_a_result(self) -> None:
        tournament = self.tournament
        board = next(
            board
            for board in tournament.get_round_boards(1)
            if board.stored_board.black_player_id is not None
        )
        tournament.add_result(board, Result.DRAW)


@pytest.mark.unit
class BergerFieldChangesTestCase(RoundRobinTestCase):
    variation_id = BergerRoundRobinVariation.static_id()

    def _pair(self) -> None:
        tournament = self.tournament
        for round_ in range(1, tournament.rounds + 1):
            self.assertEqual(tournament.generate_round_pairings(round_), '')

    def test_players_join_before_the_pairing_and_the_rounds_follow(self) -> None:
        self.assertTrue(self.tournament.can_add_players)
        self._add_player('Newcomer')
        tournament = self.tournament
        self.assertEqual(tournament.player_count, 5)
        self.assertEqual(tournament.rounds, 5)
        self._pair()
        tournament = self.tournament
        engine = self._engine(tournament)
        self.assertIsNone(engine.invalid_player_count_message(tournament))
        self.assertEqual(
            engine.paired_schedule(tournament), engine.berger_schedule(tournament)
        )

    def test_no_player_joins_once_paired(self) -> None:
        self._pair()
        self.assertFalse(self.tournament.can_add_players)

    def test_no_player_joins_once_a_result_is_in(self) -> None:
        self._pair()
        self._enter_a_result()
        self.assertFalse(self.tournament.can_add_players)

    def test_the_schedule_is_never_edited_unasked(self) -> None:
        self._add_player('Newcomer')
        self.assertFalse(self.editor.must_edit)
        self._pair()
        self.assertFalse(self.editor.must_edit)


@pytest.mark.unit
class CustomFieldChangesTestCase(RoundRobinTestCase):
    variation_id = CustomRoundRobinVariation.static_id()
    player_count = 5

    def _save_berger_schedule(self) -> None:
        self.editor.start()
        self.assertIsNone(self.editor.fill_from_berger_tables())
        self.assertIsNone(self.editor.save())
        self.assertTrue(self.tournament.has_pairings)

    @staticmethod
    def _newcomer_id(tournament: Tournament) -> int:
        return next(
            player.id
            for player in tournament.tournament_players
            if player.last_name == 'Newcomer'
        )

    def test_players_join_before_any_schedule(self) -> None:
        self.assertTrue(self.tournament.can_add_players)
        self._add_player('Newcomer')
        editor = self.editor
        self.assertTrue(editor.must_edit)
        self.assertEqual(len(editor.draft.rounds), 5)
        self.assertEqual(len(editor.draft.rounds[1].tables), 3)

    def test_a_player_joining_an_odd_field_is_seated_at_the_rests(self) -> None:
        self._save_berger_schedule()
        saved = self.tournament.round_robin_schedule
        assert saved is not None
        self.assertTrue(self.tournament.can_add_players)
        self._add_player('Newcomer')

        tournament = self.tournament
        self.assertFalse(tournament.has_pairings)
        self.assertEqual(tournament.current_round, 0)
        self.assertEqual(tournament.rounds, 5)
        self.assertEqual(tournament.round_robin_schedule, saved)
        self.assertIsNotNone(
            self._engine(tournament).invalid_player_count_message(tournament)
        )
        editor = RoundRobinScheduleEditor(tournament)
        self.assertTrue(editor.must_edit)
        newcomer = self._newcomer_id(tournament)
        draft = editor.draft
        for round_, saved_round in saved.rounds.items():
            self.assertIsNone(draft.rounds[round_].rest)
            self.assertIn(
                {newcomer, saved_round.rest},
                [set(t) for t in draft.rounds[round_].tables],
            )
        self.assertEqual(editor.violations(), [])
        self.assertIsNone(editor.save())
        tournament = self.tournament
        self.assertTrue(tournament.has_pairings)
        self.assertFalse(self.editor.must_edit)

    def test_a_player_joining_an_even_field_adds_rounds_to_fill(self) -> None:
        self._save_berger_schedule()
        self._add_player('Newcomer1')
        saved = self.tournament.round_robin_schedule
        assert saved is not None
        self._add_player('Newcomer2')

        tournament = self.tournament
        self.assertEqual(tournament.rounds, 7)
        self.assertFalse(tournament.has_pairings)
        editor = self.editor
        self.assertTrue(editor.must_edit)
        draft = editor.draft
        self.assertEqual(len(draft.rounds), 7)
        for round_, saved_round in saved.rounds.items():
            self.assertEqual(draft.rounds[round_].tables[:2], saved_round.tables)
            self.assertEqual(draft.rounds[round_].rest, saved_round.rest)
        for round_ in (6, 7):
            self.assertEqual(draft.rounds[round_].tables, [(None, None)] * 3)
        self.assertTrue(editor.violations())
        self.assertIsNotNone(editor.save())

    def test_a_draft_being_edited_follows_the_field(self) -> None:
        editor = self.editor
        self.assertIsNone(editor.fill_from_berger_tables())
        self._add_player('Newcomer')
        tournament = self.tournament
        draft = RoundRobinScheduleEditor(tournament).draft
        self.assertEqual(len(draft.rounds), 5)
        newcomer = self._newcomer_id(tournament)
        self.assertTrue(
            all(newcomer in draft.seated(round_) for round_ in draft.rounds)
        )

    def test_no_player_joins_once_a_result_is_in(self) -> None:
        self._save_berger_schedule()
        self._enter_a_result()
        self.assertFalse(self.tournament.can_add_players)

    def test_the_rest_seat_of_the_newcomer_can_be_changed(self) -> None:
        self._save_berger_schedule()
        self._add_player('Newcomer')
        tournament = self.tournament
        editor = RoundRobinScheduleEditor(tournament)
        self.assertIsNone(editor.place(1, (REST, 0), self._newcomer_id(tournament)))
        self.assertTrue(self.editor.violations())


TEAM_EVENT_ID = 'test-team-rr-field-changes-event'
TEAM_TOURNAMENT_NAME = 'test-team-rr-field-changes-tournament'
TEAM_SIZE = 2


class TeamRoundRobinTestCase(TestCase):
    variation_id: str
    team_count = 4

    def setUp(self) -> None:
        TestUtils.create_event(TEAM_EVENT_ID, overrides={'event_type': EventType.TEAM})
        TestUtils.create_tournament(
            TEAM_EVENT_ID,
            TEAM_TOURNAMENT_NAME,
            overrides={'team_player_count': TEAM_SIZE, 'pairing': self.variation_id},
        )
        for seed in range(1, self.team_count + 1):
            self._add_team(f'Team{seed}')

    def tearDown(self) -> None:
        TestUtils.delete_event(TEAM_EVENT_ID)

    def _add_team(self, name: str) -> None:
        with EventDatabase(TEAM_EVENT_ID, write=True) as database:
            tournament_id = next(
                stored_tournament.id
                for stored_tournament in database.load_stored_tournaments()
                if stored_tournament.name == TEAM_TOURNAMENT_NAME
            )
            assert tournament_id is not None
            team_id = database.add_stored_team(
                StoredTeam(
                    id=None,
                    name=name,
                    tournament_id=tournament_id,
                    pairing_number=None,
                    check_in=True,
                )
            )
            for index in range(TEAM_SIZE):
                player_id = database.add_stored_player(
                    StoredPlayer(
                        id=None,
                        last_name=f'{name}P{index}',
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

    @property
    def tournament(self) -> Tournament:
        with contextlib.suppress(KeyError):
            EventLoader.unload_event(TEAM_EVENT_ID)
        # The tournament keeps only a weak reference to its event.
        self._event: Event = EventLoader().load_event(TEAM_EVENT_ID)
        return self._event.tournaments_by_name[TEAM_TOURNAMENT_NAME]

    @property
    def editor(self) -> RoundRobinScheduleEditor:
        return RoundRobinScheduleEditor(self.tournament)


@pytest.mark.unit
class BergerTeamFieldChangesTestCase(TeamRoundRobinTestCase):
    variation_id = BergerTeamRoundRobinVariation.static_id()

    def test_teams_join_until_a_round_is_paired(self) -> None:
        self.assertTrue(self.tournament.can_add_teams)
        self._add_team('Newcomer')
        tournament = self.tournament
        self.assertEqual(tournament.rounds, 5)
        self.assertEqual(tournament.generate_round_pairings(1), '')
        self.assertFalse(self.tournament.can_add_teams)
        self.assertFalse(self.editor.must_edit)


@pytest.mark.unit
class CustomTeamFieldChangesTestCase(TeamRoundRobinTestCase):
    variation_id = CustomTeamRoundRobinVariation.static_id()

    def _save_berger_schedule(self) -> None:
        editor = self.editor
        self.assertIsNone(editor.fill_from_berger_tables())
        self.assertIsNone(editor.save())
        self.assertFalse(self.editor.must_edit)

    def test_a_team_joining_sends_the_schedule_back_to_its_editing(self) -> None:
        self._save_berger_schedule()
        self.assertTrue(self.tournament.can_add_teams)
        self._add_team('Newcomer')
        tournament = self.tournament
        engine = tournament.pairing_variation.engine
        self.assertEqual(
            engine.invalid_player_count_message(tournament),
            'The participants have changed since the schedule was saved: '
            'it has to be edited.',
        )
        editor = self.editor
        self.assertTrue(editor.must_edit)
        self.assertEqual(len(editor.draft.rounds), 5)

    def test_a_team_leaving_an_even_field_leaves_its_opponents_resting(self) -> None:
        self._save_berger_schedule()
        tournament = self.tournament
        leaving = next(team for team in tournament.teams if team.name == 'Team4')
        tournament.event.delete_team(leaving)
        editor = self.editor
        self.assertTrue(editor.must_edit)
        draft = editor.draft
        self.assertEqual(len(draft.rounds), 3)
        self.assertTrue(
            all(round_.rest is not None for round_ in draft.rounds.values())
        )
        self.assertEqual(editor.violations(), [])
        self.assertIsNone(editor.save())
        self.assertFalse(self.editor.must_edit)
