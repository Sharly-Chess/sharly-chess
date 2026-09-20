"""What the Molter verifier refuses.

Every recipe table passes it; these tables do not, each breaking one
principle, so that each check is seen to fire on what it is there for.
"""

from dataclasses import replace

import pytest

from data.pairings.fixed_table import FixedPairingTable, TablePairing
from data.pairings.molter_recipes import get_molter_recipe_table
from data.pairings.molter_verifier import verify_molter_table

Round = tuple[TablePairing, ...]


def _table(team_count: int, players_per_team: int, rounds: int) -> FixedPairingTable:
    table = get_molter_recipe_table(team_count, players_per_team, rounds)
    assert table is not None
    return table


def _with_rounds(table: FixedPairingTable, rounds: list[Round]) -> FixedPairingTable:
    return replace(table, rounds=tuple(rounds))


def _swap(pairing: TablePairing) -> TablePairing:
    """The same game with the colours reversed."""
    return TablePairing(
        pairing.black_team, pairing.black_index, pairing.white_team, pairing.white_index
    )


def _errors(table: FixedPairingTable) -> str:
    return '\n'.join(verify_molter_table(table).errors)


@pytest.mark.unit
class TestShape:
    def test_a_recipe_table_is_valid(self):
        report = verify_molter_table(_table(4, 2, 3))
        assert report.ok
        assert report.errors == []

    def test_players_per_team_must_be_even(self):
        table = replace(_table(4, 2, 3), players_per_team=3)
        assert 'players-per-team must be even (got 3)' in _errors(table)

    def test_rounds_must_be_fewer_than_teams(self):
        table = _table(4, 2, 3)
        table = _with_rounds(table, [*table.rounds, table.rounds[0]])
        assert 'a player would meet a team twice' in _errors(table)
        # Unless the table is a declared compromise.
        assert 'a player would meet a team twice' not in _errors(
            replace(table, is_compromise=True)
        )

    def test_every_round_has_a_board_per_pair_of_players(self):
        table = _table(4, 2, 3)
        short = table.rounds[0][:-1]
        table = _with_rounds(table, [short, *table.rounds[1:]])
        assert 'round 1: 3 boards, expected 4 (= 4 × 2/2)' in _errors(table)

    def test_team_letters_and_player_indexes_are_checked(self):
        table = _table(4, 2, 3)
        first = table.rounds[0]
        bad_letter = (TablePairing('Z', 1, 'C', 1), *first[1:])
        assert "round 1: unknown team letter 'Z'" in _errors(
            _with_rounds(table, [bad_letter, *table.rounds[1:]])
        )
        bad_index = (TablePairing('B', 3, 'C', 1), *first[1:])
        assert 'round 1: player index 3 out of range 1..2' in _errors(
            _with_rounds(table, [bad_index, *table.rounds[1:]])
        )


@pytest.mark.unit
class TestGames:
    def test_team_mates_are_never_paired(self):
        table = _table(4, 2, 3)
        # Round 1: B1-C1, D1-A1, C2-A2, D2-B2 → B1-B2 and D2-C1 instead.
        first = (
            TablePairing('B', 1, 'B', 2),
            table.rounds[0][1],
            table.rounds[0][2],
            TablePairing('D', 2, 'C', 1),
        )
        assert 'round 1: team-mates paired' in _errors(
            _with_rounds(table, [first, *table.rounds[1:]])
        )

    def test_a_player_plays_once_a_round(self):
        table = _table(4, 2, 3)
        # B1 on two boards: B1-C1 and D1-B1 (A1 dropped).
        first = (
            table.rounds[0][0],
            TablePairing('D', 1, 'B', 1),
            table.rounds[0][2],
            table.rounds[0][3],
        )
        errors = _errors(_with_rounds(table, [first, *table.rounds[1:]]))
        assert 'round 1: B1 appears on more than one board' in errors
        assert 'players do not all play the same number of games' in errors

    def test_a_player_meets_a_team_once(self):
        table = _table(5, 2, 4)
        # Round 2 replayed as round 3: every player meets the same teams
        # again, within the round budget rounds < teams.
        rounds = [table.rounds[0], table.rounds[1], table.rounds[1], table.rounds[3]]
        assert 'meets the same team twice' in _errors(_with_rounds(table, rounds))

    def test_a_multi_board_team_faces_more_than_one_team(self):
        table = _table(4, 2, 3)
        # Round 1 with both of A's boards against D: D1-A1 and D2-A2, so
        # B and C meet each other on both boards too.
        first = (
            TablePairing('B', 1, 'C', 1),
            TablePairing('D', 1, 'A', 1),
            TablePairing('C', 2, 'B', 2),
            TablePairing('D', 2, 'A', 2),
        )
        assert 'faces only one other team' in _errors(
            _with_rounds(table, [first, *table.rounds[1:]])
        )


@pytest.mark.unit
class TestColours:
    def test_a_team_s_colour_drift_is_bounded(self):
        table = _table(4, 2, 3)
        # Every game of A's with White, round after round.
        rounds = [
            tuple(_swap(p) if p.black_team == 'A' else p for p in rnd)
            for rnd in table.rounds
        ]
        errors = _errors(_with_rounds(table, rounds))
        assert 'team A cumulative colour drift' in errors

    def test_a_team_returns_to_balance_after_two_rounds(self):
        table = _table(6, 2, 5)
        # A's first two rounds both with White, the rest untouched: drift 2
        # is within bounds, but not restored at the end of the block.
        rounds = [
            tuple(_swap(p) if p.black_team == 'A' else p for p in rnd)
            if index < 2
            else rnd
            for index, rnd in enumerate(table.rounds)
        ]
        errors = _errors(_with_rounds(table, rounds))
        assert (
            'teams must return to colour balance after each two-round block' in errors
        )


@pytest.mark.unit
class TestFloaters:
    def test_an_even_team_count_has_no_floaters(self):
        table = _table(4, 2, 3)
        # Round 1: B1-C1, D1-A1, C2-A2, D2-B2 → B1 plays C2 and C1 plays
        # B2: two floaters across the board levels.
        first = (
            TablePairing('B', 1, 'C', 2),
            table.rounds[0][1],
            TablePairing('C', 1, 'B', 2),
            table.rounds[0][3],
        )
        assert 'on an even team count — none allowed (S6a)' in _errors(
            _with_rounds(table, [first, *table.rounds[1:]])
        )
