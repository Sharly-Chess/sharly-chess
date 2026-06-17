"""Invariant tests for the FFE Molter pairing tables.

These tests enforce the four core rules from the FFE DNA reference
("Tableaux Molter", October 2025):

  1. Within a round, no two players from the same team face each other.
  2. Across the tournament, no player faces two opponents from the same
     team. (Equivalent: number of rounds < number of teams.)
  3. Each team faces the same number of members of each other team.
  4. Each team has white and black equally distributed across the tournament.

They also enforce structural invariants:

  - Every player from every team is paired exactly once per round.
  - The autonomous round (when present) is itself a valid single-round
     pairing — every player paired, no teammate-vs-teammate.

Typos in the encoded tables are flagged by these tests.
"""

from collections import Counter

import pytest

from data.pairings.fixed_table import FixedPairingTable, TablePairing
from plugins.ffe.ffe_molter_tables import FFE_MOLTER_TABLES


def _all_players(team_count: int, players_per_team: int) -> set[tuple[str, int]]:
    """The set (team_letter, player_index) of every player in the tournament."""
    return {
        (chr(ord('A') + t), p + 1)
        for t in range(team_count)
        for p in range(players_per_team)
    }


def _round_player_set(round_: tuple[TablePairing, ...]) -> list[tuple[str, int]]:
    """Flat list of every (team_letter, player_index) appearing in a round."""
    flat: list[tuple[str, int]] = []
    for p in round_:
        flat.append((p.white_team, p.white_index))
        flat.append((p.black_team, p.black_index))
    return flat


@pytest.mark.parametrize('key,table', FFE_MOLTER_TABLES.items())
def test_no_teammate_pairing(key: tuple[int, int], table: FixedPairingTable) -> None:
    """Rule 1 — no player ever faces a teammate."""
    rounds_to_check = list(table.rounds)
    if table.autonomous_round is not None:
        rounds_to_check.append(table.autonomous_round)
    for ri, round_ in enumerate(rounds_to_check):
        for board, pairing in enumerate(round_, start=1):
            assert pairing.white_team != pairing.black_team, (
                f'Table {key} round {ri + 1} board {board}: '
                f'teammates paired ({pairing}).'
            )


@pytest.mark.parametrize('key,table', FFE_MOLTER_TABLES.items())
def test_every_player_paired_each_round(
    key: tuple[int, int], table: FixedPairingTable
) -> None:
    """Structural — every player from every team appears exactly once per round."""
    expected = _all_players(*key)
    rounds_to_check = list(table.rounds)
    if table.autonomous_round is not None:
        rounds_to_check.append(table.autonomous_round)
    for ri, round_ in enumerate(rounds_to_check):
        flat = _round_player_set(round_)
        # Each player appears exactly once.
        counts = Counter(flat)
        dupes = {p: c for p, c in counts.items() if c > 1}
        missing = expected - set(flat)
        extras = set(flat) - expected
        assert not dupes, f'Table {key} round {ri + 1}: duplicate players {dupes}.'
        assert not missing, (
            f'Table {key} round {ri + 1}: missing players {sorted(missing)}.'
        )
        assert not extras, (
            f'Table {key} round {ri + 1}: unknown players {sorted(extras)}.'
        )


@pytest.mark.parametrize('key,table', FFE_MOLTER_TABLES.items())
def test_no_repeat_team_across_rounds(
    key: tuple[int, int], table: FixedPairingTable
) -> None:
    """Rule 2 — a player never faces two opponents from the same opposing team.
    Checked across the regular rounds only (the autonomous round may
    duplicate when used as a terminal odd-round extra)."""
    team_count, players_per_team = key
    # opponents_by_player[(team, idx)] = list of opponent team letters
    opponents: dict[tuple[str, int], list[str]] = {
        player: [] for player in _all_players(team_count, players_per_team)
    }
    for round_ in table.rounds:
        for pairing in round_:
            opponents[(pairing.white_team, pairing.white_index)].append(
                pairing.black_team
            )
            opponents[(pairing.black_team, pairing.black_index)].append(
                pairing.white_team
            )
    for player, faced_teams in opponents.items():
        dupes = [t for t, c in Counter(faced_teams).items() if c > 1]
        assert not dupes, (
            f'Table {key}: player {player[0]}{player[1]} faces '
            f'players from team(s) {dupes} more than once.'
        )


@pytest.mark.parametrize('key,table', FFE_MOLTER_TABLES.items())
def test_team_vs_team_distribution_balanced(
    key: tuple[int, int], table: FixedPairingTable
) -> None:
    """Rule 3 — for each team, the number of games played against each
    other opposing team is the same to within 1 (perfect equality is
    impossible when total_games / opposing_teams is not a whole number,
    e.g. 4 teams × 4 players × 2 rounds = 8 games / 3 opponents)."""
    team_count, _players_per_team = key
    for tournament_team_idx in range(team_count):
        team_letter = chr(ord('A') + tournament_team_idx)
        opp_counter: Counter[str] = Counter()
        for round_ in table.rounds:
            for pairing in round_:
                if pairing.white_team == team_letter:
                    opp_counter[pairing.black_team] += 1
                elif pairing.black_team == team_letter:
                    opp_counter[pairing.white_team] += 1
        if not opp_counter:
            continue
        spread = max(opp_counter.values()) - min(opp_counter.values())
        assert spread <= 1, (
            f'Table {key} team {team_letter}: imbalanced opponents '
            f'{dict(opp_counter)} (spread {spread}).'
        )


@pytest.mark.parametrize('key,table', FFE_MOLTER_TABLES.items())
def test_color_balance_per_team(key: tuple[int, int], table: FixedPairingTable) -> None:
    """Rule 4 — across the regular rounds, each team plays as many whites
    as blacks."""
    team_count, _players_per_team = key
    for tournament_team_idx in range(team_count):
        team_letter = chr(ord('A') + tournament_team_idx)
        whites = 0
        blacks = 0
        for round_ in table.rounds:
            for pairing in round_:
                if pairing.white_team == team_letter:
                    whites += 1
                if pairing.black_team == team_letter:
                    blacks += 1
        assert whites == blacks, (
            f'Table {key} team {team_letter}: {whites} whites vs '
            f'{blacks} blacks across regular rounds.'
        )


def test_table_keys_match_data() -> None:
    """The dict keys must match each table's declared (team_count, players_per_team)."""
    for key, table in FFE_MOLTER_TABLES.items():
        assert key == (table.team_count, table.players_per_team), (
            f'Key {key} does not match table.team_count/players_per_team '
            f'({table.team_count}, {table.players_per_team}).'
        )
