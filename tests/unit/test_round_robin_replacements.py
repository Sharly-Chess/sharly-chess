"""A player who leaves a round-robin replaced by a newcomer, who takes over
their seat: its Berger number, its opponents and its colours, from a round
on. The tournament keeps its seats, its rounds and its schedule; the two
players are kept out of the ranking, their games counting for everyone,
and their seat counts as one opponent in the tie-breaks."""

from unittest import TestCase

import pytest

from data.columns.column import ColumnUsage
from data.columns.player_table import (
    ExAequoRankColumn,
    RankColumn,
)
from data.event import Event
from data.input_output.trf.trf_export import TrfExport
from data.input_output.trf.trf_serializer import TrfSerializer
from data.loader import EventLoader
from data.pairings.engines import RoundRobinPairingEngine
from data.pairings.variations import (
    BergerRoundRobinVariation,
    CustomRoundRobinVariation,
)
from data.pairings.round_robin_editor import RoundRobinScheduleEditor
from data.player import TournamentPlayer
from data.print_documents.documents import PlayerRankingPrintDocument
from data.print_documents.options import TournamentPrintOption
from data.tie_breaks.tie_breaks import TieBreak
from data.tournament import Tournament
from database.sqlite.event.event_store import StoredPlayer
from plugins.ffe.papi_converter import PapiConverter
from plugins.ffe.papi_mappers import PapiRound
from tests.test_config import TestUtils
from utils.enum import Result

EVENT_ID = 'test-rr-replacements-event'
TOURNAMENT_NAME = 'test-rr-replacements-tournament'
PLAYER_COUNT = 6
ROUNDS = 5


class RoundRobinReplacementTestCase(TestCase):
    variation_id = BergerRoundRobinVariation.static_id()

    def setUp(self) -> None:
        TestUtils.create_event(EVENT_ID)
        TestUtils.create_tournament(
            EVENT_ID, TOURNAMENT_NAME, overrides={'pairing': self.variation_id}
        )
        for index in range(PLAYER_COUNT):
            self._add_player(f'Player{index + 1}')
        self._pair()

    def tearDown(self) -> None:
        TestUtils.delete_event(EVENT_ID)

    def _add_player(
        self,
        last_name: str,
        replaced_player_id: int | None = None,
        replaced_from_round: int | None = None,
    ) -> int:
        event = EventLoader().load_event(EVENT_ID)
        return event.add_player(
            StoredPlayer(id=None, last_name=last_name),
            [event.tournaments_by_name[TOURNAMENT_NAME]],
            replaced_player_id=replaced_player_id,
            replaced_from_round=replaced_from_round,
        )

    @property
    def tournament(self) -> Tournament:
        # The tournament keeps only a weak reference to its event.
        self._event: Event = EventLoader().load_event(EVENT_ID)
        return self._event.tournaments_by_name[TOURNAMENT_NAME]

    def _pair(self) -> None:
        tournament = self.tournament
        for round_ in range(1, tournament.rounds + 1):
            self.assertEqual(tournament.generate_round_pairings(round_), '')

    def _play_rounds(self, *rounds: int) -> None:
        for round_ in rounds:
            tournament = self.tournament
            for board in tournament.get_round_boards(round_):
                if board.stored_board.black_player_id is not None:
                    tournament.add_result(board, Result.WIN)

    def _player(self, tournament: Tournament, last_name: str) -> TournamentPlayer:
        return next(
            player
            for player in tournament.tournament_players
            if player.last_name == last_name
        )

    def _opponents(self, tournament: Tournament, player_id: int) -> dict[int, int]:
        """The opponents of *player_id* by round."""
        player = tournament.tournament_players_by_id[player_id]
        return {
            round_: pairing.opponent_id
            for round_, pairing in player.pairings_by_round.items()
            if pairing.opponent_id is not None
        }

    def _replace(self, last_name: str, from_round: int) -> tuple[int, int]:
        leaver_id = self._player(self.tournament, last_name).id
        replacement_id = self._add_player(
            'Replacement', replaced_player_id=leaver_id, replaced_from_round=from_round
        )
        return leaver_id, replacement_id


@pytest.mark.unit
class BergerReplacementTestCase(RoundRobinReplacementTestCase):
    def test_a_paired_round_robin_takes_replacements_only(self) -> None:
        tournament = self.tournament
        self.assertFalse(tournament.can_add_players)
        self.assertTrue(tournament.can_add_replacements)
        self._play_rounds(1, 2)
        tournament = self.tournament
        self.assertTrue(tournament.can_add_replacements)
        leaver = self._player(tournament, 'Player1')
        self.assertEqual(
            tournament.replaceable_rounds_by_player_id[leaver.id], [3, 4, 5]
        )

    def test_the_replacement_plays_the_games_of_the_seat(self) -> None:
        self._play_rounds(1, 2)
        tournament = self.tournament
        leaver_before = self._opponents(
            tournament, self._player(tournament, 'Player1').id
        )
        leaver_id, replacement_id = self._replace('Player1', 3)
        tournament = self.tournament
        self.assertEqual(tournament.rounds, ROUNDS)
        self.assertEqual(tournament.seat_count, PLAYER_COUNT)
        self.assertEqual(tournament.player_count, PLAYER_COUNT + 1)
        engine = tournament.pairing_variation.engine
        assert isinstance(engine, RoundRobinPairingEngine)
        self.assertIsNone(engine.invalid_player_count_message(tournament))
        self.assertEqual(
            self._opponents(tournament, leaver_id),
            {round_: leaver_before[round_] for round_ in (1, 2)},
        )
        self.assertEqual(
            self._opponents(tournament, replacement_id),
            {round_: leaver_before[round_] for round_ in (3, 4, 5)},
        )
        replacement = tournament.tournament_players_by_id[replacement_id]
        self.assertEqual(replacement.seat_id, leaver_id)
        self.assertTrue(replacement.holds_seat_in(3))
        self.assertFalse(replacement.holds_seat_in(2))
        self.assertFalse(
            any(
                pairing.voluntary_unplayed
                for pairing in replacement.pairings_by_round.values()
            )
        )
        self.assertEqual(
            engine.paired_schedule(tournament), engine.schedule(tournament)
        )

    def test_the_seat_holders_are_ranked_and_their_games_count(self) -> None:
        self._play_rounds(1, 2)
        leaver_id, replacement_id = self._replace('Player1', 3)
        self._play_rounds(3, 4, 5)
        tournament = self.tournament
        for player_id in (leaver_id, replacement_id):
            self.assertTrue(tournament.tournament_players_by_id[player_id].shares_seat)
        for player in tournament.tournament_players:
            self.assertFalse(player.is_excluded_from_standings)
            self.assertTrue(
                all(
                    not player.game_is_annulled(pairing)
                    for pairing in player.pairings_by_round.values()
                )
            )
            if not player.shares_seat:
                self.assertEqual(
                    sum(
                        1
                        for pairing in player.pairings_by_round.values()
                        if pairing.played
                    ),
                    ROUNDS,
                )

    def test_the_standings_rank_the_seat_holders_by_their_points(self) -> None:
        self._play_rounds(1, 2)
        self._replace('Player1', 3)
        self._play_rounds(3, 4, 5)
        tournament = self.tournament
        document = PlayerRankingPrintDocument(
            options=[TournamentPrintOption(self._event, tournament.id)]
        )
        document.event = self._event
        listed = document.ordered_tournament_players
        self.assertEqual(len(listed), PLAYER_COUNT + 1)
        points = [player.points or 0 for player in listed]
        self.assertEqual(points, sorted(points, reverse=True))
        for player in listed:
            self.assertIsNone(document.heading_before(player, None))
            self.assertFalse(
                ExAequoRankColumn(ColumnUsage.PRINT).is_cell_blank_for(player)
            )
            self.assertEqual(
                RankColumn(ColumnUsage.PRINT).get_cell_content(player), player.rank
            )

    def test_the_seat_counts_as_one_opponent(self) -> None:
        self._play_rounds(1, 2)
        leaver_id, replacement_id = self._replace('Player1', 3)
        self._play_rounds(3, 4, 5)
        tournament = self.tournament
        leaver = tournament.tournament_players_by_id[leaver_id]
        replacement = tournament.tournament_players_by_id[replacement_id]
        seat_points = leaver.standings_points(ROUNDS) + replacement.standings_points(
            ROUNDS
        )
        for player in (leaver, replacement):
            self.assertEqual(player.seat_points(ROUNDS), seat_points)
            self.assertEqual(
                TieBreak.adjusted_score(player, after_round=ROUNDS), seat_points
            )

    def test_a_replacement_can_be_replaced(self) -> None:
        self._play_rounds(1)
        leaver_id, first_id = self._replace('Player1', 2)
        self._play_rounds(2, 3)
        tournament = self.tournament
        self.assertEqual(tournament.replaceable_rounds_by_player_id[first_id], [4, 5])
        self.assertNotIn(leaver_id, tournament.replaceable_rounds_by_player_id)
        second_id = self._add_player(
            'Second', replaced_player_id=first_id, replaced_from_round=4
        )
        tournament = self.tournament
        self.assertEqual(tournament.seat_count, PLAYER_COUNT)
        self.assertEqual(
            [player.id for player in tournament.seat_players(leaver_id)],
            [leaver_id, first_id, second_id],
        )
        self.assertEqual(sorted(self._opponents(tournament, first_id)), [2, 3])
        self.assertEqual(sorted(self._opponents(tournament, second_id)), [4, 5])

    def test_several_seats_are_replaced_at_once(self) -> None:
        self._play_rounds(1, 2)
        self._replace('Player1', 3)
        self._replace('Player2', 3)
        tournament = self.tournament
        self.assertEqual(tournament.rounds, ROUNDS)
        self.assertEqual(tournament.seat_count, PLAYER_COUNT)
        for round_ in range(3, ROUNDS + 1):
            self.assertEqual(
                len(tournament.get_round_boards(round_)), PLAYER_COUNT // 2
            )

    def test_the_trf_keeps_the_rounds_and_states_the_replacement(self) -> None:
        self._play_rounds(1, 2)
        leaver_id, replacement_id = self._replace('Player1', 3)
        self._play_rounds(3, 4, 5)
        tournament = self.tournament
        tournament.set_tournament_players_pairing_numbers()
        leaver = tournament.tournament_players_by_id[leaver_id]
        replacement = tournament.tournament_players_by_id[replacement_id]
        self.assertEqual(replacement.pairing_number, PLAYER_COUNT + 1)
        trf = TrfExport(tournament).build()
        self.assertEqual(trf.num_rounds, ROUNDS)
        self.assertEqual(trf.encoded_type, 'CUSTOM_ROUNDROBIN')
        text = TrfSerializer.dumps(trf)
        self.assertIn(
            f'### Replacement @ Round 3: player {PLAYER_COUNT + 1} takes over '
            f'the seat of player {leaver.pairing_number}\n',
            text,
        )
        games = {player.id: player.games for player in trf.players}
        self.assertEqual(
            [game.result for game in games[PLAYER_COUNT + 1][:2]], [' ', ' ']
        )
        assert leaver.pairing_number is not None
        self.assertNotIn(
            'Z', [game.result for game in games[leaver.pairing_number][2:]]
        )

    def test_the_papi_gives_the_replacement_as_forfeit_before_joining(
        self,
    ) -> None:
        self._play_rounds(1, 2)
        leaver_id, replacement_id = self._replace('Player1', 3)
        self._play_rounds(3, 4, 5)
        tournament = self.tournament
        players = list(tournament.tournament_players)
        papi_players = PapiConverter().tournament_to_papi_data(tournament).players
        papi_by_id = {
            player.id: papi_player
            for player, papi_player in zip(players, papi_players, strict=True)
        }
        replacement_rounds = papi_by_id[replacement_id].rounds
        for round_ in (1, 2):
            self.assertEqual(replacement_rounds[round_], PapiRound.zero_point_bye())
        for round_ in (3, 4, 5):
            self.assertIsNotNone(replacement_rounds[round_].opponent)
        leaver_rounds = papi_by_id[leaver_id].rounds
        for round_ in (1, 2):
            self.assertIsNotNone(leaver_rounds[round_].opponent)

    def test_a_replacement_yet_to_play_can_be_taken_back(self) -> None:
        self._play_rounds(1, 2)
        tournament = self.tournament
        leaver_id = self._player(tournament, 'Player1').id
        leaver_before = self._opponents(tournament, leaver_id)
        _leaver_id, replacement_id = self._replace('Player1', 3)
        event = EventLoader().load_event(EVENT_ID)
        replacement = event.players_by_id[replacement_id]
        self.assertIsNone(replacement.paired_tournament)
        event.delete_player(replacement)
        tournament = self.tournament
        self.assertNotIn(replacement_id, tournament.tournament_players_by_id)
        self.assertFalse(tournament.has_replacements)
        self.assertEqual(self._opponents(tournament, leaver_id), leaver_before)

    def _assert_every_game_has_both_players(self) -> None:
        tournament = self.tournament
        for round_ in range(1, ROUNDS + 1):
            for board in tournament.get_round_boards(round_):
                for player_id in (
                    board.stored_board.white_player_id,
                    board.stored_board.black_player_id,
                ):
                    assert player_id is not None
                    pairing = tournament.tournament_players_by_id[
                        player_id
                    ].pairings_by_round[round_]
                    self.assertTrue(pairing.exists, (round_, player_id))
                    self.assertEqual(
                        pairing.stored_pairing.board_id,
                        board.stored_board.id,
                        (round_, player_id),
                    )

    def test_taking_a_replacement_back_leaves_every_game_with_both_players(
        self,
    ) -> None:
        self._play_rounds(1, 2)
        _leaver_id, replacement_id = self._replace('Player1', 3)
        event = EventLoader().load_event(EVENT_ID)
        event.delete_player(event.players_by_id[replacement_id])
        EventLoader.unload_event(EVENT_ID)
        self._assert_every_game_has_both_players()

    def test_taking_back_the_last_of_a_chain_of_replacements(self) -> None:
        self._play_rounds(1)
        _leaver_id, first_id = self._replace('Player1', 2)
        self._play_rounds(2)
        second_id = self._add_player(
            'Second', replaced_player_id=first_id, replaced_from_round=3
        )
        event = EventLoader().load_event(EVENT_ID)
        event.delete_player(event.players_by_id[second_id])
        EventLoader.unload_event(EVENT_ID)
        self._assert_every_game_has_both_players()
        tournament = self.tournament
        self.assertEqual(sorted(self._opponents(tournament, first_id)), [2, 3, 4, 5])

    def test_a_replacement_who_played_cannot_be_taken_back(self) -> None:
        self._play_rounds(1, 2)
        _leaver_id, replacement_id = self._replace('Player1', 3)
        self._play_rounds(3)
        event = EventLoader().load_event(EVENT_ID)
        self.assertIsNotNone(event.players_by_id[replacement_id].paired_tournament)

    def test_the_seat_is_named_after_all_its_holders(self) -> None:
        leaver_id, _replacement_id = self._replace('Player1', 3)
        editor = RoundRobinScheduleEditor(self.tournament)
        self.assertEqual(editor.member_name(leaver_id), 'PLAYER1 / REPLACEMENT')


@pytest.mark.unit
class CustomReplacementTestCase(RoundRobinReplacementTestCase):
    variation_id = CustomRoundRobinVariation.static_id()

    def _pair(self) -> None:
        editor = RoundRobinScheduleEditor(self.tournament)
        self.assertIsNone(editor.fill_from_berger_tables())
        self.assertIsNone(editor.save())

    def test_a_custom_round_robin_takes_replacements_once_played(self) -> None:
        self.assertTrue(self.tournament.can_add_players)
        self._play_rounds(1)
        self.assertFalse(self.tournament.can_add_players)
        leaver_id, replacement_id = self._replace('Player1', 2)
        tournament = self.tournament
        engine = tournament.pairing_variation.engine
        assert isinstance(engine, RoundRobinPairingEngine)
        self.assertIsNone(engine.schedule_message(tournament))
        self.assertEqual(sorted(self._opponents(tournament, leaver_id)), [1])
        self.assertEqual(
            sorted(self._opponents(tournament, replacement_id)), [2, 3, 4, 5]
        )
