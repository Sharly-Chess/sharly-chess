"""Tests for the Molter recipe-builder generator and verifier.

The generator is deterministic: ``(team_count, players_per_team, rounds)``
defines a single canonical table. These tests pin the output and check every
hard Molter invariant (no team-mates, no repeated opponent team, colour balance,
floaters S6a/S6b/S6c) plus the ideals the construction claims for complete
layers and partial-layer prefixes.
"""

import sys
from collections import Counter
from itertools import combinations
from pathlib import Path

import pytest

from data.pairings.fixed_table import FixedPairingTable, TablePairing

MOLTER_APPENDIX_DIR = (
    Path(__file__).resolve().parents[2] / 'docs' / 'technical-appendices' / 'molter'
)
sys.path.insert(0, str(MOLTER_APPENDIX_DIR))


def _serialise(table: FixedPairingTable):
    return [
        [(p.white_team, p.white_index, p.black_team, p.black_index) for p in r]
        for r in table.rounds
    ]


# Frozen output of generate_molter_table(3, 4). Pins the algorithm: any
# change to the base construction, the expansion shift, the board ordering
# or the iteration order would change this and break the test — which is the
# point, since the table must be byte-reproducible (incl. by
# re-implementations in other languages, see molter_recipe_generator).
_GOLDEN_3x4 = [
    [
        ('B', 1, 'A', 1),
        ('C', 1, 'B', 2),
        ('A', 2, 'C', 2),
        ('B', 3, 'C', 3),
        ('C', 4, 'A', 3),
        ('A', 4, 'B', 4),
    ],
    [
        ('A', 1, 'C', 1),
        ('C', 2, 'B', 1),
        ('B', 2, 'A', 2),
        ('A', 3, 'B', 3),
        ('C', 3, 'A', 4),
        ('B', 4, 'C', 4),
    ],
]


def test_generator_reference_is_stable() -> None:
    from molter_recipe_generator import generate_molter_table

    assert _serialise(generate_molter_table(3, 4)) == _GOLDEN_3x4


def test_standard_generator_rejects_three_team_three_round_compromise() -> None:
    from molter_recipe_generator import MolterGenerationError
    from molter_recipe_generator import generate_molter_table

    with pytest.raises(MolterGenerationError):
        generate_molter_table(3, 4, rounds=3)


def test_ffe_three_team_three_round_override_is_best_compromise() -> None:
    from data.pairings.molter_verifier import verify_molter_table
    from plugins.ffe.ffe_rule_sets import _FFE_CUP_3T_4P_TABLE

    table = _FFE_CUP_3T_4P_TABLE
    report = verify_molter_table(table)
    assert table.is_compromise
    assert report.ok, report.errors
    assert len(table.rounds) == 3

    opponents: dict[tuple[str, int], list[tuple[str, int]]] = {}
    opponent_teams: dict[tuple[str, int], Counter[str]] = {}
    team_edges_by_round = []
    for round_ in table.rounds:
        team_edges_by_round.append(_team_edges(round_))
        for pairing in round_:
            white = (pairing.white_team, pairing.white_index)
            black = (pairing.black_team, pairing.black_index)
            opponents.setdefault(white, []).append(black)
            opponents.setdefault(black, []).append(white)
            opponent_teams.setdefault(white, Counter())[pairing.black_team] += 1
            opponent_teams.setdefault(black, Counter())[pairing.white_team] += 1

    assert all(len(seen) == len(set(seen)) for seen in opponents.values())
    assert all(sorted(counts.values()) == [1, 2] for counts in opponent_teams.values())
    assert all(
        edges == {('A', 'B'): 2, ('A', 'C'): 2, ('B', 'C'): 2}
        for edges in team_edges_by_round
    )


@pytest.mark.parametrize(
    'team_count, players_per_team',
    [(3, 4), (4, 6), (5, 10), (8, 12), (9, 8), (13, 12)],
)
def test_generated_table_is_valid(team_count: int, players_per_team: int) -> None:
    from molter_recipe_generator import generate_molter_table
    from data.pairings.molter_verifier import verify_molter_table

    table = generate_molter_table(team_count, players_per_team)
    report = verify_molter_table(table)
    assert report.ok, report.errors


def test_large_even_team_count_is_valid() -> None:
    """Team letters may extend beyond Z; generation should still be valid."""
    from molter_recipe_generator import generate_molter_table
    from data.pairings.molter_verifier import verify_molter_table

    report = verify_molter_table(generate_molter_table(50, 2))
    assert report.ok, report.errors


@pytest.mark.parametrize(
    'team_count, players_per_team, rounds, prefix, expected_distinct',
    [
        (9, 4, 8, 2, 8),
        (9, 4, 6, 2, 8),
        (11, 4, 4, 3, 10),
        (11, 6, 4, 2, 10),
        (13, 6, 4, 2, 12),
        (9, 6, 3, 2, 8),
        (13, 4, 2, 2, 8),
        (17, 14, 12, 2, 14),
        (21, 8, 16, 3, 16),
        (31, 10, 3, 3, 30),
        (51, 6, 50, 5, 18),
    ],
)
def test_odd_partial_team_count_is_valid_and_keeps_colour_safe_prefix_spread(
    team_count: int,
    players_per_team: int,
    rounds: int,
    prefix: int,
    expected_distinct: int,
) -> None:
    """Partial odd layers keep hard colour validity ahead of prefix spread.

    The prefix expectation is exact for these regression cases. It documents the
    current hard-rule priority: when maximum prefix spread conflicts with C1/C2,
    the generator keeps the strongest colour-safe spread it can prove.
    """
    from molter_recipe_generator import generate_molter_table
    from data.pairings.molter_verifier import verify_molter_table

    table = generate_molter_table(team_count, players_per_team, rounds)
    report = verify_molter_table(table)
    assert report.ok, report.errors
    _assert_uniform_prefix_opponent_spread(table, prefix, expected_distinct)


@pytest.mark.parametrize(
    'team_count, players_per_team, rounds',
    [
        (19, 14, 17),
        (23, 14, 22),
    ],
)
def test_near_complete_odd_partial_layers_use_final_colour_fallback(
    team_count: int, players_per_team: int, rounds: int
) -> None:
    """Near-complete odd partial layers can need final round-pair colouring.

    Construction-order colour probes reject these shapes, but the final colourer
    can legally reorder and colour them while preserving the hard Molter rules.
    """
    from molter_recipe_generator import generate_molter_table
    from data.pairings.molter_verifier import verify_molter_table

    table = generate_molter_table(team_count, players_per_team, rounds)
    report = verify_molter_table(table)
    assert report.ok, report.errors


@pytest.mark.parametrize(
    'team_count, players_per_team, rounds, expected_i1',
    [
        (5, 14, 2, 0),
        (7, 10, 4, 1),
        (9, 10, 2, 1),
        (9, 10, 4, 0),
        (9, 12, 6, 0),
        (9, 14, 4, 0),
        (13, 8, 4, 1),
        (15, 6, 6, 1),
        (11, 12, 4, 1),
        (11, 14, 4, 1),
    ],
)
def test_odd_full_plus_partial_layers_optimize_i1_before_i3(
    team_count: int,
    players_per_team: int,
    rounds: int,
    expected_i1: int,
) -> None:
    from molter_recipe_generator import generate_molter_table
    from data.pairings.molter_verifier import verify_molter_table

    table = generate_molter_table(team_count, players_per_team, rounds)
    report = verify_molter_table(table)
    assert report.ok, report.errors
    assert _opponent_multiplicity_spread(table) == expected_i1


@pytest.mark.parametrize('team_count', [3, 7])
def test_small_odd_prefixes_are_valid_and_spread_opponents(team_count: int) -> None:
    """Small fixed-factor odd tables keep the same prefix-spread guarantee."""
    from molter_recipe_generator import generate_molter_table
    from data.pairings.molter_verifier import verify_molter_table

    for players_per_team in range(2, 18, 2):
        for rounds in range(1, team_count):
            table = generate_molter_table(team_count, players_per_team, rounds)
            report = verify_molter_table(table)
            assert report.ok, report.errors
            for prefix in range(1, rounds + 1):
                expected = min(
                    table.team_count - 1,
                    table.players_per_team * ((prefix + 1) // 2),
                )
                _assert_prefix_opponent_spread_at_least(table, prefix, expected)


@pytest.mark.parametrize('team_count', [17, 21, 49, 51, 69])
def test_large_odd_full_team_count_is_valid_and_balanced(team_count: int) -> None:
    """Large full odd layers are valid and keep optimal I3 balance."""
    from molter_recipe_generator import generate_molter_table
    from data.pairings.molter_verifier import verify_molter_table

    table = generate_molter_table(team_count, team_count - 1, team_count - 1)
    report = verify_molter_table(table)
    assert report.ok, report.errors

    down: Counter[str] = Counter()
    for round_ in table.rounds:
        for pairing in round_:
            if pairing.white_index < pairing.black_index:
                down[pairing.white_team] += 1
            elif pairing.black_index < pairing.white_index:
                down[pairing.black_team] += 1

    counts = [down[chr(ord('A') + team)] for team in range(team_count)]
    assert max(counts) - min(counts) <= 1


def _team_edges(round_: tuple[TablePairing, ...]) -> Counter[tuple[str, str]]:
    out: Counter[tuple[str, str]] = Counter()
    for pairing in round_:
        teams = sorted((pairing.white_team, pairing.black_team))
        out[(teams[0], teams[1])] += 1
    return out


def _prefix_opponent_counts(table: FixedPairingTable, prefix: int) -> dict[str, int]:
    opponents: dict[str, set[str]] = {}
    for round_ in table.rounds[:prefix]:
        for pairing in round_:
            opponents.setdefault(pairing.white_team, set()).add(pairing.black_team)
            opponents.setdefault(pairing.black_team, set()).add(pairing.white_team)
    return {team: len(seen) for team, seen in opponents.items()}


def _assert_uniform_prefix_opponent_spread(
    table: FixedPairingTable, prefix: int, expected: int
) -> None:
    counts = _prefix_opponent_counts(table, prefix)
    assert len(counts) == table.team_count
    assert set(counts.values()) == {expected}, (prefix, counts)


def _assert_prefix_opponent_spread_at_least(
    table: FixedPairingTable, prefix: int, expected: int
) -> None:
    counts = _prefix_opponent_counts(table, prefix)
    assert len(counts) == table.team_count
    assert min(counts.values()) >= expected, (prefix, counts, expected)


def _opponent_multiplicity_spread(table: FixedPairingTable) -> int:
    teams = tuple(chr(ord('A') + index) for index in range(table.team_count))
    counts: dict[str, Counter[str]] = {team: Counter() for team in teams}
    for round_ in table.rounds:
        for pairing in round_:
            counts[pairing.white_team][pairing.black_team] += 1
            counts[pairing.black_team][pairing.white_team] += 1
    return max(
        max(counts[team][opponent] for opponent in teams if opponent != team)
        - min(counts[team][opponent] for opponent in teams if opponent != team)
        for team in teams
    )


def _floater_i2_l1(table: FixedPairingTable) -> int:
    down: Counter[str] = Counter()
    up: Counter[str] = Counter()
    for round_ in table.rounds:
        for pairing in round_:
            if pairing.white_index < pairing.black_index:
                down[pairing.white_team] += 1
                up[pairing.black_team] += 1
            elif pairing.black_index < pairing.white_index:
                down[pairing.black_team] += 1
                up[pairing.white_team] += 1
    return sum(
        abs(down[chr(ord('A') + team)] - up[chr(ord('A') + team)])
        for team in range(table.team_count)
    )


@pytest.mark.parametrize(
    'team_count, players_per_team, rounds, expected_i2_l1, expected_prefix',
    [
        (9, 4, 4, 0, 8),
        (9, 6, 3, 0, 8),
    ],
)
def test_odd_partial_generator_optimizes_i2_l1_after_hard_validity(
    team_count: int,
    players_per_team: int,
    rounds: int,
    expected_i2_l1: int,
    expected_prefix: int,
) -> None:
    from molter_recipe_generator import generate_molter_table
    from data.pairings.molter_verifier import verify_molter_table

    table = generate_molter_table(team_count, players_per_team, rounds)
    report = verify_molter_table(table)
    assert report.ok, report.errors
    _assert_uniform_prefix_opponent_spread(table, min(rounds, 2), expected_prefix)
    assert _floater_i2_l1(table) == expected_i2_l1


@pytest.mark.parametrize('team_count', [5, 7, 9, 11, 13, 15])
def test_odd_complete_generator_is_valid_at_max_rounds(team_count: int) -> None:
    from molter_recipe_generator import generate_molter_table
    from data.pairings.molter_verifier import verify_molter_table

    table = generate_molter_table(team_count, team_count - 1, team_count - 1)
    report = verify_molter_table(table)
    assert report.ok, report.errors


@pytest.mark.parametrize('team_count', [5, 7, 9, 11, 13, 15])
def test_odd_complete_generator_balances_descending_floaters(
    team_count: int,
) -> None:
    from molter_recipe_generator import generate_molter_table

    table = generate_molter_table(team_count, team_count - 1, team_count - 1)
    down: Counter[str] = Counter()
    for round_ in table.rounds:
        for pairing in round_:
            if pairing.white_index < pairing.black_index:
                down[pairing.white_team] += 1
            elif pairing.black_index < pairing.white_index:
                down[pairing.black_team] += 1

    counts = [down[chr(ord('A') + team)] for team in range(team_count)]
    # Single-layer complete tables balance descending floaters to spread ≤ 1,
    # except N = 5: there S6c and a perfect I3 are mutually exclusive (proven by
    # exhaustive search), so the spread is 2 — S6c, the hard rule, wins.
    assert max(counts) - min(counts) <= (2 if team_count == 5 else 1)


@pytest.mark.parametrize('team_count', [5, 7, 9, 11, 13, 15])
def test_odd_complete_generator_floaters_once_per_round_pair(team_count: int) -> None:
    """On a complete table (P = N − 1) each team floats at most once down and
    once up per round-pair (ideal I4). Only achievable on the single-layer
    complete tables."""
    from molter_recipe_generator import generate_molter_table

    table = generate_molter_table(team_count, team_count - 1, team_count - 1)
    rounds = table.rounds
    for start in range(0, len(rounds), 2):
        down: Counter = Counter()
        up: Counter = Counter()
        for r_index in range(start, min(start + 2, len(rounds))):
            for p in rounds[r_index]:
                if p.white_index == p.black_index:
                    continue
                lo = p.white_team if p.white_index < p.black_index else p.black_team
                hi = p.black_team if p.white_index < p.black_index else p.white_team
                down[lo] += 1
                up[hi] += 1
        assert not down or max(down.values()) <= 1, (start, dict(down))
        assert not up or max(up.values()) <= 1, (start, dict(up))


@pytest.mark.parametrize('team_count', [5, 7, 9, 11, 13, 15])
def test_odd_complete_no_repeated_floater_role(team_count: int) -> None:
    """S6c (hard): over the regular rounds no player is a descending floater
    more than once, nor an ascending floater more than once."""
    from molter_recipe_generator import generate_molter_table

    table = generate_molter_table(team_count, team_count - 1, team_count - 1)
    down: Counter = Counter()
    up: Counter = Counter()
    for round_ in table.rounds:
        for p in round_:
            if p.white_index == p.black_index:
                continue
            lo = (
                (p.white_team, p.white_index)
                if p.white_index < p.black_index
                else (p.black_team, p.black_index)
            )
            hi = (
                (p.white_team, p.white_index)
                if p.white_index > p.black_index
                else (p.black_team, p.black_index)
            )
            down[lo] += 1
            up[hi] += 1
    assert not down or max(down.values()) <= 1, dict(down)
    assert not up or max(up.values()) <= 1, dict(up)


def test_one_round_request_uses_regular_round() -> None:
    from molter_recipe_generator import generate_molter_table

    table = generate_molter_table(5, 4, rounds=1)
    assert table.round_pairings(1, 1) == table.rounds[0]


@pytest.mark.parametrize('team_count', [5, 7, 9, 11, 13, 15])
@pytest.mark.parametrize('rounds', [1, 2, 4])
def test_odd_complete_generator_prefixes_are_valid(
    team_count: int, rounds: int
) -> None:
    from molter_recipe_generator import generate_molter_table
    from data.pairings.molter_verifier import verify_molter_table

    if rounds > team_count - 1:
        pytest.skip('round prefix exceeds the complete schedule')
    table = generate_molter_table(team_count, team_count - 1, rounds)
    report = verify_molter_table(table)
    assert report.ok, report.errors


@pytest.mark.parametrize('team_count', [5, 7, 9, 11, 13, 15])
@pytest.mark.parametrize('rounds', [2, 4])
def test_odd_complete_generator_has_per_round_i1(team_count: int, rounds: int) -> None:
    from molter_recipe_generator import generate_molter_table

    if rounds > team_count - 1:
        pytest.skip('round prefix exceeds the complete schedule')
    table = generate_molter_table(team_count, team_count - 1, rounds)
    expected = {
        tuple(chr(ord('A') + i) for i in pair)
        for pair in combinations(range(team_count), 2)
    }
    for round_ in table.rounds:
        edges = _team_edges(round_)
        assert set(edges) == expected
        assert all(count == 1 for count in edges.values())


@pytest.mark.parametrize(
    'team_count, players_per_team, rounds',
    [(4, 6, 1), (4, 6, 2), (4, 6, 3), (4, 12, 2), (6, 10, 3), (6, 10, 5), (8, 14, 2)],
)
def test_even_complete_generator_has_per_round_i1(
    team_count: int, players_per_team: int, rounds: int
) -> None:
    """Even team counts with ``P = k × (N − 1)`` also reach per-round I1 (each
    team faces every other ``k`` times each round), via a 1-factorisation,
    valid for any round count."""
    from molter_recipe_generator import generate_molter_table
    from data.pairings.molter_verifier import verify_molter_table

    table = generate_molter_table(team_count, players_per_team, rounds)
    assert verify_molter_table(table).ok
    expected = {
        tuple(chr(ord('A') + i) for i in pair)
        for pair in combinations(range(team_count), 2)
    }
    expected_count = players_per_team // (team_count - 1)
    for round_ in table.rounds:
        edges = _team_edges(round_)
        assert set(edges) == expected
        assert all(count == expected_count for count in edges.values())


@pytest.mark.parametrize(
    'team_count, players_per_team, horizons',
    [
        (4, 4, (1, 2, 3)),
        (8, 10, (1, 3, 7)),
        (16, 24, (1, 5, 15)),
    ],
)
def test_even_short_tables_are_valid_for_exact_horizon(
    team_count: int, players_per_team: int, horizons: tuple[int, ...]
) -> None:
    from molter_recipe_generator import generate_molter_table
    from data.pairings.molter_verifier import verify_molter_table

    for rounds in horizons:
        short = generate_molter_table(team_count, players_per_team, rounds)
        report = verify_molter_table(short)
        assert report.ok, report.errors


@pytest.mark.parametrize(
    'team_count, players_per_team, rounds, prefix, expected_distinct',
    [
        (8, 4, 7, 2, 7),
        (10, 6, 4, 2, 9),
        (16, 6, 5, 3, 15),
        (50, 24, 10, 3, 48),
    ],
)
def test_even_partial_team_count_keeps_colour_safe_prefix_spread(
    team_count: int,
    players_per_team: int,
    rounds: int,
    prefix: int,
    expected_distinct: int,
) -> None:
    from molter_recipe_generator import generate_molter_table
    from data.pairings.molter_verifier import verify_molter_table

    table = generate_molter_table(team_count, players_per_team, rounds)
    report = verify_molter_table(table)
    assert report.ok, report.errors
    _assert_uniform_prefix_opponent_spread(table, prefix, expected_distinct)


@pytest.mark.parametrize(
    'team_count, players_per_team, rounds, expected_i1',
    [
        (14, 8, 7, 1),
        (18, 8, 7, 2),
        (30, 14, 7, 2),
    ],
)
def test_even_partial_team_count_prefers_pair_balanced_i1_candidate(
    team_count: int,
    players_per_team: int,
    rounds: int,
    expected_i1: int,
) -> None:
    from molter_recipe_generator import generate_molter_table
    from data.pairings.molter_verifier import verify_molter_table

    table = generate_molter_table(team_count, players_per_team, rounds)
    report = verify_molter_table(table)
    assert report.ok, report.errors
    assert _opponent_multiplicity_spread(table) == expected_i1


@pytest.mark.parametrize(
    'team_count, players_per_team, rounds',
    [
        (12, 8, 6),
        (18, 10, 4),
        (18, 12, 4),
        (18, 14, 4),
        (24, 14, 5),
    ],
)
def test_even_short_tables_try_i1_first_balanced_rows(
    team_count: int,
    players_per_team: int,
    rounds: int,
) -> None:
    from molter_recipe_generator import generate_molter_table
    from data.pairings.molter_verifier import verify_molter_table

    table = generate_molter_table(team_count, players_per_team, rounds)
    report = verify_molter_table(table)
    assert report.ok, report.errors
    assert _opponent_multiplicity_spread(table) <= 1


@pytest.mark.parametrize(
    'team_count, players_per_team',
    [(5, 8), (5, 12), (7, 12), (9, 16), (13, 24)],
)
def test_odd_complete_generator_stacks_i1_layers(
    team_count: int, players_per_team: int
) -> None:
    from molter_recipe_generator import generate_molter_table
    from data.pairings.molter_verifier import verify_molter_table

    table = generate_molter_table(team_count, players_per_team, team_count - 1)
    report = verify_molter_table(table)
    assert report.ok, report.errors

    expected = {
        tuple(chr(ord('A') + i) for i in pair)
        for pair in combinations(range(team_count), 2)
    }
    expected_count = players_per_team // (team_count - 1)
    for round_ in table.rounds:
        edges = _team_edges(round_)
        assert set(edges) == expected
        assert all(count == expected_count for count in edges.values())

    # Descending-floater balance (I3) is a best-effort ideal on multi-layer
    # tables: honouring S6c (the hard rule, already verified above via
    # ``report.ok``) can push the descending spread above 1. I3 ≤ 1 is only
    # guaranteed on the single-layer complete tables — see
    # ``test_odd_complete_generator_balances_descending_floaters``.


def test_generator_is_deterministic() -> None:
    # Bypass the lru_cache so we exercise a real second build, not the
    # cached object — the two builds must be byte-identical.
    from molter_recipe_generator import generate_molter_table

    build = generate_molter_table.__wrapped__
    assert _serialise(build(8, 12)) == _serialise(build(8, 12))


@pytest.mark.parametrize('team_count', [4, 6, 8, 10, 12])
@pytest.mark.parametrize('players_per_team', [4, 8, 12])
def test_even_team_count_has_no_floaters(
    team_count: int, players_per_team: int
) -> None:
    """S6a — an even team count never floats: every board pairs the same
    board number."""
    from molter_recipe_generator import generate_molter_table

    table = generate_molter_table(team_count, players_per_team)
    for ri, round_ in enumerate(table.rounds, start=1):
        for p in round_:
            assert p.white_index == p.black_index, (
                f'{team_count}×{players_per_team} round {ri}: floater {p} on an '
                f'even team count (S6a).'
            )


@pytest.mark.parametrize(
    'team_count, players_per_team',
    [(3, 4), (4, 6), (5, 12), (6, 8), (7, 6), (7, 12), (8, 10), (13, 12)],
)
def test_generated_team_colours_obey_relaxed_s5(
    team_count: int, players_per_team: int
) -> None:
    """S5 — exact per-round balance is preferred; bounded two-round drift is hard."""
    from molter_recipe_generator import generate_molter_table

    table = generate_molter_table(team_count, players_per_team)
    teams = tuple(chr(ord('A') + index) for index in range(team_count))
    drift = Counter({team: 0 for team in teams})
    for r_index, round_ in enumerate(table.rounds, start=1):
        white = Counter(pairing.white_team for pairing in round_)
        black = Counter(pairing.black_team for pairing in round_)
        for team in teams:
            drift[team] += white[team] - black[team]
            assert abs(drift[team]) <= 2, (
                f'{team_count}×{players_per_team} round {r_index}: '
                f'team {team} has cumulative colour drift {drift[team]}.'
            )
            if r_index % 2 == 0 or r_index == len(table.rounds):
                assert drift[team] == 0, (
                    f'{team_count}×{players_per_team} round {r_index}: '
                    f'team {team} did not return to colour balance.'
                )


@pytest.mark.parametrize('team_count', [3, 5, 7, 9, 11, 13])
@pytest.mark.parametrize('players_per_team', [4, 8, 12])
def test_odd_floaters_are_consecutive_odd_descending(
    team_count: int, players_per_team: int
) -> None:
    """S6b — for an odd team count, a floater only joins consecutive
    boards with the odd board descending, and at most one descending
    floater per odd board level per round."""
    from molter_recipe_generator import generate_molter_table

    table = generate_molter_table(team_count, players_per_team)
    for ri, round_ in enumerate(table.rounds, start=1):
        descending_at: Counter[int] = Counter()
        for p in round_:
            if p.white_index == p.black_index:
                continue
            lo, hi = sorted((p.white_index, p.black_index))
            assert hi - lo == 1 and lo % 2 == 1, (
                f'{team_count}×{players_per_team} round {ri}: illegal floater '
                f'{p} (S6b).'
            )
            descending_at[lo] += 1
        assert all(c <= 1 for c in descending_at.values()), (
            f'{team_count}×{players_per_team} round {ri}: more than one '
            f'descending floater at a board level ({dict(descending_at)}).'
        )
