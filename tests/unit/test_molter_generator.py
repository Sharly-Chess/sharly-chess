"""Tests for the core Molter pairing-table generator and verifier
(``data.pairings.molter_generator`` / ``data.pairings.molter_verifier``).

The generator is deterministic: ``(team_count, players_per_team, rounds)``
defines a single canonical table (the only search is a small, bounded,
deterministic backtracking for the floater edges). These tests pin the output
and check every hard Molter invariant (no team-mates, no repeated opponent team,
colour balance, floaters S6a/S6b/S6c) and the ideals (per-round I1,
descending-floater balance I2, the per-round-pair I5).
"""

from collections import Counter
from itertools import combinations

import pytest

from data.pairings.fixed_table import FixedPairingTable, TablePairing


def _serialise(table: FixedPairingTable):
    return [
        [(p.white_team, p.white_index, p.black_team, p.black_index) for p in r]
        for r in table.rounds
    ]


# Frozen output of generate_molter_table(3, 4). Pins the algorithm: any
# change to the base construction, the expansion shift, the board ordering
# or the iteration order would change this and break the test — which is the
# point, since the table must be byte-reproducible (incl. by
# re-implementations in other languages, see data.pairings.molter_generator).
_GOLDEN_3x4 = [
    [
        ('A', 1, 'B', 1),
        ('B', 2, 'C', 1),
        ('C', 2, 'A', 2),
        ('C', 3, 'B', 3),
        ('A', 3, 'C', 4),
        ('B', 4, 'A', 4),
    ],
    [
        ('C', 1, 'A', 1),
        ('B', 1, 'C', 2),
        ('A', 2, 'B', 2),
        ('B', 3, 'A', 3),
        ('A', 4, 'C', 3),
        ('C', 4, 'B', 4),
    ],
]


def test_generator_reference_is_stable() -> None:
    from data.pairings.molter_generator import generate_molter_table

    assert _serialise(generate_molter_table(3, 4)) == _GOLDEN_3x4


def test_standard_generator_rejects_three_team_three_round_compromise() -> None:
    from data.pairings.molter_generator import MolterGenerationError
    from data.pairings.molter_generator import generate_molter_table

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
    from data.pairings.molter_generator import generate_molter_table
    from data.pairings.molter_verifier import verify_molter_table

    table = generate_molter_table(team_count, players_per_team)
    report = verify_molter_table(table)
    assert report.ok, report.errors


def test_large_even_team_count_is_valid() -> None:
    """Team letters may extend beyond Z; generation should still be valid."""
    from data.pairings.molter_generator import generate_molter_table
    from data.pairings.molter_verifier import verify_molter_table

    report = verify_molter_table(generate_molter_table(50, 2))
    assert report.ok, report.errors


@pytest.mark.parametrize(
    'team_count, players_per_team, rounds, max_spread',
    [
        (9, 6, 3, 0),
        (17, 14, 12, 1),
        (21, 8, 16, 1),
        (17, 14, 14, 2),
        (51, 6, 50, 1),
        (51, 48, 50, 1),
        (69, 68, 2, 1),
    ],
)
def test_odd_partial_team_count_is_valid_and_balanced(
    team_count: int, players_per_team: int, rounds: int, max_spread: int
) -> None:
    """Partial odd layers use one-odd plans instead of a full floater grid."""
    from data.pairings.molter_generator import generate_molter_table
    from data.pairings.molter_verifier import verify_molter_table

    table = generate_molter_table(team_count, players_per_team, rounds)
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
    assert max(counts) - min(counts) <= max_spread


@pytest.mark.parametrize('team_count', [3, 7])
def test_small_odd_layer_rotations_reach_i2_lower_bound(team_count: int) -> None:
    """Repeated odd layers rotate team labels so I2 does not accumulate on the
    same teams. N=5 remains exceptional and is covered separately."""
    from data.pairings.molter_generator import generate_molter_table
    from data.pairings.molter_verifier import verify_molter_table

    for players_per_team in range(2, 18, 2):
        for rounds in range(1, team_count):
            table = generate_molter_table(team_count, players_per_team, rounds)
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
            total = (players_per_team // 2) * rounds
            lower_bound = 0 if total % team_count == 0 else 1
            assert max(counts) - min(counts) == lower_bound, (
                team_count,
                players_per_team,
                rounds,
                counts,
            )


@pytest.mark.parametrize('team_count', [17, 21, 49, 51, 69])
def test_large_odd_full_team_count_is_valid_and_balanced(team_count: int) -> None:
    """Large full odd layers are valid and keep optimal I2 balance."""
    from data.pairings.molter_generator import generate_molter_table
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


@pytest.mark.parametrize('team_count', [5, 7, 9, 11, 13, 15])
def test_odd_complete_generator_is_valid_at_max_rounds(team_count: int) -> None:
    from data.pairings.molter_generator import generate_molter_table
    from data.pairings.molter_verifier import verify_molter_table

    table = generate_molter_table(team_count, team_count - 1, team_count - 1)
    report = verify_molter_table(table)
    assert report.ok, report.errors


@pytest.mark.parametrize('team_count', [5, 7, 9, 11, 13, 15])
def test_odd_complete_generator_balances_descending_floaters(
    team_count: int,
) -> None:
    from data.pairings.molter_generator import generate_molter_table

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
    # except N = 5: there S6c and a perfect I2 are mutually exclusive (proven by
    # exhaustive search), so the spread is 2 — S6c, the hard rule, wins.
    assert max(counts) - min(counts) <= (2 if team_count == 5 else 1)


@pytest.mark.parametrize('team_count', [5, 7, 9, 11, 13, 15])
def test_odd_complete_generator_floaters_once_per_round_pair(team_count: int) -> None:
    """On a complete table (P = N − 1) each team floats at most once down and
    once up per round-pair (ideal I5). Only achievable on the single-layer
    complete tables."""
    from data.pairings.molter_generator import generate_molter_table

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
    from data.pairings.molter_generator import generate_molter_table

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
    from data.pairings.molter_generator import generate_molter_table

    table = generate_molter_table(5, 4, rounds=1)
    assert table.round_pairings(1, 1) == table.rounds[0]


@pytest.mark.parametrize('team_count', [5, 7, 9, 11, 13, 15])
@pytest.mark.parametrize('rounds', [1, 2, 4])
def test_odd_complete_generator_prefixes_are_valid(
    team_count: int, rounds: int
) -> None:
    from data.pairings.molter_generator import generate_molter_table
    from data.pairings.molter_verifier import verify_molter_table

    if rounds > team_count - 1:
        pytest.skip('round prefix exceeds the complete schedule')
    table = generate_molter_table(team_count, team_count - 1, rounds)
    report = verify_molter_table(table)
    assert report.ok, report.errors


@pytest.mark.parametrize('team_count', [5, 7, 9, 11, 13, 15])
@pytest.mark.parametrize('rounds', [2, 4])
def test_odd_complete_generator_has_per_round_i1(team_count: int, rounds: int) -> None:
    from data.pairings.molter_generator import generate_molter_table

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
    from data.pairings.molter_generator import generate_molter_table
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
    'team_count, players_per_team',
    [(5, 8), (5, 12), (7, 12), (9, 16), (13, 24)],
)
def test_odd_complete_generator_stacks_i1_layers(
    team_count: int, players_per_team: int
) -> None:
    from data.pairings.molter_generator import generate_molter_table
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

    # Descending-floater balance (I2) is a best-effort ideal on multi-layer
    # tables: honouring S6c (the hard rule, already verified above via
    # ``report.ok``) can push the descending spread above 1. I2 ≤ 1 is only
    # guaranteed on the single-layer complete tables — see
    # ``test_odd_complete_generator_balances_descending_floaters``.


def test_generator_is_deterministic() -> None:
    # Bypass the lru_cache so we exercise a real second build, not the
    # cached object — the two builds must be byte-identical.
    from data.pairings.molter_generator import generate_molter_table

    build = generate_molter_table.__wrapped__
    assert _serialise(build(8, 12)) == _serialise(build(8, 12))


@pytest.mark.parametrize('team_count', [4, 6, 8, 10, 12])
@pytest.mark.parametrize('players_per_team', [4, 8, 12])
def test_even_team_count_has_no_floaters(
    team_count: int, players_per_team: int
) -> None:
    """S6a — an even team count never floats: every board pairs the same
    board number."""
    from data.pairings.molter_generator import generate_molter_table

    table = generate_molter_table(team_count, players_per_team)
    for ri, round_ in enumerate(table.rounds, start=1):
        for p in round_:
            assert p.white_index == p.black_index, (
                f'{team_count}×{players_per_team} round {ri}: floater {p} on an '
                f'even team count (S6a).'
            )


def _colour_sequences(table: FixedPairingTable) -> dict[tuple[str, int], list[bool]]:
    """player → list of True(white)/False(black) over the regular rounds."""
    R = len(table.rounds)
    seq: dict[tuple[str, int], list[bool]] = {}
    for ri, round_ in enumerate(table.rounds):
        for p in round_:
            seq.setdefault((p.white_team, p.white_index), [False] * R)[ri] = True
            seq.setdefault((p.black_team, p.black_index), [False] * R)[ri] = False
    return seq


@pytest.mark.parametrize(
    'team_count, players_per_team',
    [(3, 4), (4, 6), (5, 12), (6, 8), (7, 6), (7, 12), (8, 10), (13, 12)],
)
def test_generated_colours_follow_the_convention(
    team_count: int, players_per_team: int
) -> None:
    """Each player is colour-balanced over the regular rounds, never plays
    one colour three rounds running, and only repeats a colour across an
    even→odd round boundary."""
    from data.pairings.molter_generator import generate_molter_table

    table = generate_molter_table(team_count, players_per_team)
    R = len(table.rounds)
    for player, seq in _colour_sequences(table).items():
        whites = sum(seq)
        assert abs(whites - (R - whites)) <= R % 2, (
            f'{team_count}×{players_per_team} {player}: colour imbalance '
            f'{whites}W/{R - whites}B.'
        )
        run = 1
        for i in range(1, R):
            run = run + 1 if seq[i] == seq[i - 1] else 1
            assert run <= 2, f'{player} tripled colour around round {i + 1}.'
            if seq[i] == seq[i - 1]:
                assert i % 2 == 0, (
                    f'{player} repeats colour on an odd→even boundary '
                    f'(round {i}→{i + 1}).'
                )


@pytest.mark.parametrize('team_count', [3, 5, 7, 9, 11, 13])
@pytest.mark.parametrize('players_per_team', [4, 8, 12])
def test_odd_floaters_are_consecutive_odd_descending(
    team_count: int, players_per_team: int
) -> None:
    """S6b — for an odd team count, a floater only joins consecutive
    boards with the odd board descending, and at most one descending
    floater per odd board level per round."""
    from data.pairings.molter_generator import generate_molter_table

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
