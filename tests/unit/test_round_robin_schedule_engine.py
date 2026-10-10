"""Round-robin engines pair every round from the tournament's schedule: the
saved one or, for the Berger variations, the Berger tables.

Built on the TEC round-robin fixture (6 players, 5 rounds)."""

from unittest import TestCase

import pytest

from data.event import Event
from data.input_output.trf.trf_data import TrfPlayer, TrfTeam, TrfTournament
from data.input_output.trf.trf_importer import TrfTournamentImporter
from data.loader import EventLoader
from data.pairings.engines import RoundRobinPairingEngine
from data.pairings.round_robin_schedule import RoundRobinSchedule
from data.pairings.variations import (
    BergerRoundRobinVariation,
    CustomRoundRobinVariation,
    CustomTeamRoundRobinVariation,
    DoubleCustomRoundRobinVariation,
    DoubleCustomTeamRoundRobinVariation,
)
from database.sqlite.event.event_database import EventDatabase
from tests.test_config import TestUtils

EVENT_ID = 'test-rr-schedule-engine-event'
TOURNAMENT_ID = 'test-rr-schedule-engine-tournament'


@pytest.mark.unit
class RoundRobinScheduleEngineTestCase(TestCase):
    def setUp(self) -> None:
        TestUtils.create_event(EVENT_ID)
        TestUtils.create_tournament(
            EVENT_ID, TOURNAMENT_ID, json_file='tec-round-robin'
        )

    def tearDown(self) -> None:
        TestUtils.delete_event(EVENT_ID)

    @property
    def tournament(self):
        # The tournament keeps only a weak reference to its event.
        self._event: Event = EventLoader().load_event(EVENT_ID)
        return self._event.tournaments_by_name[TOURNAMENT_ID]

    def _set_variation(self, variation_id: str) -> None:
        stored_tournament = self.tournament.stored_tournament
        stored_tournament.pairing = variation_id
        with EventDatabase(EVENT_ID, True) as database:
            database.update_stored_tournament(stored_tournament)

    def _engine(self, tournament) -> RoundRobinPairingEngine:
        engine = tournament.pairing_variation.engine
        assert isinstance(engine, RoundRobinPairingEngine)
        return engine

    def _custom_schedule(self, tournament) -> RoundRobinSchedule:
        """The Berger schedule with its rounds in reverse order."""
        berger = self._engine(tournament).berger_schedule(tournament)
        last = len(berger.rounds)
        return RoundRobinSchedule(
            {round_: berger.rounds[last + 1 - round_] for round_ in berger.rounds}
        )

    def test_berger_tournament_follows_the_berger_tables(self) -> None:
        self._set_variation(BergerRoundRobinVariation.static_id())
        tournament = self.tournament
        engine = self._engine(tournament)
        self.assertEqual(
            engine.schedule(tournament), engine.berger_schedule(tournament)
        )
        self.assertIsNone(engine.schedule_message(tournament))

    def test_custom_tournament_without_schedule_follows_its_pairings(self) -> None:
        """As a tournament imported with its games has none saved."""
        self._set_variation(CustomRoundRobinVariation.static_id())
        tournament = self.tournament
        engine = self._engine(tournament)
        schedule = engine.schedule(tournament)
        assert schedule is not None
        self.assertEqual(schedule, engine.paired_schedule(tournament))
        self.assertEqual(
            set(schedule.rounds[3].tables),
            {
                (board.stored_board.white_player_id, board.stored_board.black_player_id)
                for board in tournament.get_round_boards(3)
            },
        )
        self.assertIsNone(engine.invalid_player_count_message(tournament))

    def test_custom_tournament_is_paired_from_its_schedule(self) -> None:
        self._set_variation(CustomRoundRobinVariation.static_id())
        tournament = self.tournament
        schedule = self._custom_schedule(tournament)
        tournament.set_round_robin_schedule(schedule, None)
        tournament = self.tournament
        engine = self._engine(tournament)
        self.assertEqual(engine.schedule(tournament), schedule)
        self.assertIsNone(engine.invalid_player_count_message(tournament))
        for round_, schedule_round in schedule.rounds.items():
            boards = engine._generate_stored_boards(tournament, round_)
            self.assertEqual(
                [(board.white_player_id, board.black_player_id) for board in boards],
                [
                    *schedule_round.tables,
                    *([(schedule_round.rest, None)] if schedule_round.rest else []),
                ],
            )

    def test_schedule_breaking_the_rules_is_not_paired(self) -> None:
        self._set_variation(CustomRoundRobinVariation.static_id())
        tournament = self.tournament
        schedule = self._custom_schedule(tournament)
        schedule.rounds[2] = schedule.rounds[1]
        tournament.set_round_robin_schedule(schedule, None)
        tournament = self.tournament
        self.assertEqual(
            self._engine(tournament).invalid_player_count_message(tournament),
            'The schedule of the tournament breaks the round-robin rules.',
        )


@pytest.mark.unit
class CustomRoundRobinImportTestCase(TestCase):
    """CUSTOM_ROUNDROBIN and CUSTOM_TEAM_ROUNDROBIN cover single and double
    round-robins alike: the number of rounds tells them apart."""

    @staticmethod
    def _variation_id(encoded_type: str, rounds: int) -> str:
        trf_tournament = TrfTournament(encoded_type=encoded_type, num_rounds=rounds)
        if 'TEAM' in encoded_type:
            trf_tournament.teams = [TrfTeam(id=id_) for id_ in range(1, 6)]
        else:
            trf_tournament.players = [TrfPlayer(id=id_) for id_ in range(1, 6)]
        return TrfTournamentImporter._pairing_variation_id(trf_tournament)

    def test_single_and_double_custom_round_robins(self) -> None:
        self.assertEqual(
            self._variation_id('CUSTOM_ROUNDROBIN', 5),
            CustomRoundRobinVariation.static_id(),
        )
        self.assertEqual(
            self._variation_id('CUSTOM_ROUNDROBIN', 10),
            DoubleCustomRoundRobinVariation.static_id(),
        )
        self.assertEqual(
            self._variation_id('CUSTOM_TEAM_ROUNDROBIN', 5),
            CustomTeamRoundRobinVariation.static_id(),
        )
        self.assertEqual(
            self._variation_id('CUSTOM_TEAM_ROUNDROBIN', 10),
            DoubleCustomTeamRoundRobinVariation.static_id(),
        )

    def test_custom_round_robins_export_their_code(self) -> None:
        for variation, code in (
            (CustomRoundRobinVariation(), 'CUSTOM_ROUNDROBIN'),
            (DoubleCustomRoundRobinVariation(), 'CUSTOM_ROUNDROBIN'),
            (CustomTeamRoundRobinVariation(), 'CUSTOM_TEAM_ROUNDROBIN'),
            (DoubleCustomTeamRoundRobinVariation(), 'CUSTOM_TEAM_ROUNDROBIN'),
        ):
            self.assertEqual(variation.trf_encoded_type, code)
