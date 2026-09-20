"""Keizer pairing over a real tournament: who is paired with whom, who
sits out, and who has White, round after round.

Five players, so every round gives one of them a bye. The engine pairs
neighbours in the current Keizer standings, avoids a rematch inside the
configured gap, hands the bye down the table to a player who has not had
one, and gives White to the lower-ranked player in round one, then to
whoever has had it less.
"""

from contextlib import suppress

import pytest

from data.loader import EventLoader
from data.pairings.settings import KeizerRematchGapSetting
from data.tournament import Tournament
from database.sqlite.event.event_database import EventDatabase
from database.sqlite.event.event_store import StoredPlayer, StoredTournamentPlayer
from tests.test_config import TestUtils
from utils.enum import Result

EVENT_ID = 'test-keizer-engine'
TOURNAMENT_NAME = 'keizer'
# Rating order is P0 > P1 > P2 > P3 > P4, and so the initial standing.
PLAYERS = ['P0', 'P1', 'P2', 'P3', 'P4']


@pytest.mark.unit
class TestKeizerEngine:
    @pytest.fixture(autouse=True)
    def tournament_name(self):
        TestUtils.create_event(EVENT_ID)
        TestUtils.create_tournament(
            EVENT_ID,
            TOURNAMENT_NAME,
            overrides={'rounds': 5, 'current_round': 1, 'pairing': 'KEIZER_STANDARD'},
        )
        with EventDatabase(EVENT_ID, write=True) as database:
            tournament_id = next(
                stored.id
                for stored in database.load_stored_tournaments()
                if stored.name == TOURNAMENT_NAME
            )
            assert tournament_id is not None
            for index, name in enumerate(PLAYERS):
                player_id = database.add_stored_player(
                    StoredPlayer(
                        id=None,
                        last_name=name,
                        ratings={1: {'standard': 2000 - index * 100}},
                        check_in=True,
                    )
                )
                database.add_stored_tournament_player(
                    StoredTournamentPlayer(
                        tournament_id=tournament_id, player_id=player_id
                    )
                )
        yield TOURNAMENT_NAME
        TestUtils.delete_event(EVENT_ID)

    def _load(self) -> Tournament:
        with suppress(KeyError):
            EventLoader.unload_event(EVENT_ID)
        self._event = EventLoader().load_event(EVENT_ID)
        return self._event.tournaments_by_name[TOURNAMENT_NAME]

    @staticmethod
    def _boards(tournament: Tournament, round_: int) -> list[tuple[str, str | None]]:
        """``(white, black)`` names per board, in board order; a bye has no
        black."""
        return [
            (
                board.white_tournament_player.last_name,
                board.black_tournament_player.last_name
                if board.black_tournament_player
                else None,
            )
            for board in tournament.get_round_boards(round_)
        ]

    @staticmethod
    def _play(tournament: Tournament, round_: int, winners: set[str]) -> None:
        """Enter every board's result: the named players win, the other
        games are drawn."""
        for board in tournament.get_round_boards(round_):
            black = board.black_tournament_player
            if black is None:
                continue
            white = board.white_tournament_player
            if white.last_name in winners:
                tournament.add_result(board, Result.WIN)
            elif black.last_name in winners:
                tournament.add_result(board, Result.LOSS)
            else:
                tournament.add_result(board, Result.DRAW)

    def _pair(self, round_: int) -> Tournament:
        tournament = self._load()
        assert tournament.generate_round_pairings(round_) == ''
        return self._load()

    def test_round_one_pairs_neighbours_and_byes_the_last(self):
        tournament = self._pair(1)
        # Adjacent in the standings, the lower-ranked with White, and the
        # bye at the bottom of the table.
        assert self._boards(tournament, 1) == [
            ('P1', 'P0'),
            ('P3', 'P2'),
            ('P4', None),
        ]
        bye = tournament.tournament_players_by_id[
            tournament.get_round_boards(1)[-1].white_tournament_player.id
        ]
        assert bye.pairings[1].result == Result.PAIRING_ALLOCATED_BYE

    def test_round_two_follows_the_keizer_standings(self):
        tournament = self._pair(1)
        # P0 and P2 win: with start values 6, 5, 4, 3, 2 (lowest is
        # (5 - 1) // 2 = 2), P0 has 6 + 5, P2 has 4 + 3, P4 its bye share,
        # P1 and P3 their own value only.
        self._play(tournament, 1, winners={'P0', 'P2'})
        tournament = self._load()
        totals = tournament.keizer_scorer.totals_after(1)
        by_name = {p.last_name: p.id for p in tournament.tournament_players}
        assert totals[by_name['P0']] > totals[by_name['P2']] > totals[by_name['P1']]

        tournament = self._pair(2)
        boards = self._boards(tournament, 2)
        # The bye goes to the lowest-ranked player who has not had one yet;
        # P4 has, so P3 (last but one, at the bottom on 3 points) sits out.
        assert boards[-1] == ('P3', None)
        # The leaders meet — P0 v P2 — and the rematch P0 v P1 is avoided
        # while the gap covers it. Round-one Whites (P1, P3) do not get it
        # again when their opponent has had it less.
        paired = {frozenset(board) for board in boards[:-1]}
        assert paired == {frozenset(('P0', 'P2')), frozenset(('P1', 'P4'))}
        assert ('P2', 'P0') in boards
        assert ('P4', 'P1') in boards

    def _draw_round_one(self, gap: str) -> list[tuple[str, str | None]]:
        """Round one all drawn, then round two paired with the given
        rematch gap. Drawn, the standings keep their order (P0 8.5, P1 8,
        P2 5.5, P3 5, P4 on its bye share), so with P3 sitting out the
        neighbours to pair are P0 v P1 again and P2 v P4."""
        tournament = self._load()
        tournament.update_pairing_settings({KeizerRematchGapSetting.static_id(): gap})
        tournament = self._pair(1)
        self._play(tournament, 1, winners=set())
        return self._boards(self._pair(2), 2)

    def test_a_rematch_inside_the_gap_is_avoided(self):
        boards = self._draw_round_one(gap='3')
        paired = {frozenset(board) for board in boards[:-1]}
        assert paired == {frozenset(('P0', 'P2')), frozenset(('P1', 'P4'))}

    def test_a_rematch_is_allowed_once_the_gap_has_passed(self):
        boards = self._draw_round_one(gap='0')
        paired = {frozenset(board) for board in boards[:-1]}
        assert paired == {frozenset(('P0', 'P1')), frozenset(('P2', 'P4'))}

    def test_every_round_pairs_the_whole_field(self):
        for round_ in range(1, 6):
            tournament = self._pair(round_)
            boards = tournament.get_round_boards(round_)
            seated = [
                player
                for board in boards
                for player in (
                    board.optional_white_tournament_player,
                    board.black_tournament_player,
                )
                if player is not None
            ]
            assert len(seated) == len(PLAYERS)
            assert len({player.id for player in seated}) == len(PLAYERS)
            assert sum(board.black_tournament_player is None for board in boards) == 1
            self._play(tournament, round_, winners=set())
        # Five rounds, five byes: everyone sat out exactly once.
        tournament = self._load()
        byes = {
            player.last_name: sum(
                pairing.result == Result.PAIRING_ALLOCATED_BYE
                for pairing in player.pairings.values()
            )
            for player in tournament.tournament_players
        }
        assert byes == dict.fromkeys(PLAYERS, 1)
