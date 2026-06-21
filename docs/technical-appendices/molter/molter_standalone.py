#!/usr/bin/env python3
"""Standalone Molter table reference generator and verifier.

This script is intentionally self-contained: it uses only the Python standard
library, builds a Molter pairing table for a requested shape, verifies it against
the Molter principles, and prints it.

Verified hard invariants for strict generated tables:
  S1  P (players per team) is even; boards per round = N × P / 2.
  S2  each player plays once per round, and the same number of total games.
  S3  team-mates are never paired.
  S4  no player meets two opponents from the same team, so rounds < teams.
  S5  each team has exactly as many Whites as Blacks, possible because P is even.
  S6a for an even team count there are no floaters: every board pairs players
      with the same board number.
  S6b for an odd team count a floater only joins consecutive boards, the odd
      board descends, and at most one descending floater is allowed per odd board
      level and round.
  S6c the floater role rotates: over the regular rounds no player is a
      descending floater, or ascending floater, more than once.
  C1/C2/C3 colour rules over the regular rounds: each player is colour-balanced,
      no player has the same colour three times running, and a colour repeat is
      allowed only across an even-to-odd round boundary.

Rule-set override tables may be marked as compromises; those are checked against
explicit best-compromise repeat/colour rules instead of strict S4 and the strict
colour-boundary convention. The standalone generator itself remains strict.

Ideals, such as uniform team encounters and floater balance, are reached only by
complete tables. Reduced tables report unmet ideals as notes, never as errors.

The construction is deterministic and portable. Odd team counts use one-odd
factors: each full layer covers K_N in every round, so I1 is exact. Partial
layers reuse the same factors and choose deterministic floater edges. Every
traversal is sorted and deterministic, so a given (N, P, rounds) defines one
reference table that can be reproduced exactly in another language.

Examples:
    python3 molter_standalone.py 5 10
    python3 molter_standalone.py 9 8 --rounds 2
    python3 molter_standalone.py --grid --csv tables.csv
"""

from __future__ import annotations

import argparse
import csv
import sys
from dataclasses import dataclass, field
from functools import lru_cache
from itertools import product

# --------------------------------------------------------------------------
# Representation
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class Pairing:
    """One board: White (team letter, board number) against Black."""

    white_team: str
    white_index: int
    black_team: str
    black_index: int

    def __str__(self) -> str:
        return (
            f'{self.white_team}{self.white_index} - {self.black_team}{self.black_index}'
        )


@dataclass(frozen=True)
class MolterTable:
    team_count: int
    players_per_team: int
    rounds: tuple[tuple[Pairing, ...], ...]
    is_compromise: bool = False

    @property
    def regular_round_count(self) -> int:
        return len(self.rounds)


@dataclass
class Report:
    errors: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors


Player = tuple[int, int]  # (team 0..N-1, slot 0..P-1)


@lru_cache(maxsize=None)
def _letter(team_index: int) -> str:
    if team_index < len(_TEAM_LETTERS):
        return _TEAM_LETTERS[team_index]
    return chr(ord('A') + team_index)


# --------------------------------------------------------------------------
# Construction and verification core
# --------------------------------------------------------------------------

_Player = tuple[int, int]  # (team_index 0-based, slot 0-based; board = slot + 1)
_Match = tuple[_Player, _Player]  # an uncoloured board (unordered pair)
_Board = tuple[_Player, _Player]  # a coloured board (white, black)
_Round = list[_Board]
_OneOddPlanCell = tuple[int, tuple[int, int]]
_OneOddPlan = tuple[tuple[_OneOddPlanCell, ...], ...]
_VERIFY_GENERATED_TABLES = False
_TEAM_LETTERS = tuple(chr(ord('A') + index) for index in range(26))


class MolterGenerationError(Exception):
    """Raised when no valid Molter table could be generated for the
    requested shape."""


@lru_cache(maxsize=None)
def _letter(team_index: int) -> str:
    if team_index < len(_TEAM_LETTERS):
        return _TEAM_LETTERS[team_index]
    return chr(ord('A') + team_index)


def _colours(rnd: _Round) -> dict[_Player, bool]:
    """Map each player in a coloured round to True if it had White."""
    out: dict[_Player, bool] = {}
    for white, black in rnd:
        out[white] = True
        out[black] = False
    return out


# ---------- colouring a matched round (deterministic, no search) ----------


def _eulerian_colour(boards: list[_Match]) -> _Round:
    """A "free" round: orient each board so every team gets one White / one
    Black (S5). Each team plays an even number of boards, so the team graph
    decomposes into cycles; orienting each cycle is an Eulerian orientation.
    Deterministic — cycles start at the lowest team, follow the lowest edge."""
    edge_teams = [(a[0], b[0]) for a, b in boards]
    incident: dict[int, set[int]] = {}
    for e, (ta, tb) in enumerate(edge_teams):
        incident.setdefault(ta, set()).add(e)
        incident.setdefault(tb, set()).add(e)
    white_team_of: list[int] = [-1] * len(boards)
    unused = set(range(len(boards)))
    while unused:
        start = min(t for t, es in incident.items() if es)
        cur = start
        while True:
            e = min(incident[cur])
            ta, tb = edge_teams[e]
            nxt = tb if ta == cur else ta
            incident[cur].discard(e)
            incident[nxt].discard(e)
            unused.discard(e)
            white_team_of[e] = cur
            cur = nxt
            if cur == start:
                break
    return [
        (a, b) if a[0] == white_team_of[e] else (b, a)
        for e, (a, b) in enumerate(boards)
    ]


def _flip_colour(boards: list[_Match], prev: dict[_Player, bool]) -> _Round:
    """An "alternating" round: each player takes the opposite of its previous
    colour. The matching paired opposite previous colours, so the player that
    was Black becomes White."""
    return [(a, b) if prev[a] is False else (b, a) for a, b in boards]


# ---------- complete odd tables (P = k × (N - 1), per-round I1) ----------


def _team_edge(first: int, second: int) -> tuple[int, int]:
    return (first, second) if first < second else (second, first)


class _DeterministicRng:
    """Small stable pseudo-random stream for deterministic repair tie-breaks."""

    def __init__(self, seed: int) -> None:
        self._state = seed & ((1 << 64) - 1)

    def _next(self) -> int:
        self._state = (6364136223846793005 * self._state + 1442695040888963407) & (
            (1 << 64) - 1
        )
        return self._state

    def randrange(self, stop: int) -> int:
        return (self._next() >> 32) % stop

    def choice(self, values):
        return values[self.randrange(len(values))]

    def shuffle(self, values: list) -> None:
        for index in range(len(values) - 1, 0, -1):
            other = self.randrange(index + 1)
            values[index], values[other] = values[other], values[index]


def _affine_floater_edge(
    team_count: int, round_pair: int, block: int
) -> tuple[int, int]:
    half = (team_count - 1) // 2
    start = round_pair + block
    return _team_edge(start % team_count, (start + half + 1) % team_count)


def _one_odd_prescribed_edges(
    team_count: int,
) -> tuple[tuple[tuple[int, int], ...], ...]:
    """Edges each 2-factor must contain for the affine floater grid.

    Factor ``h`` is used on cells where ``h = (round_pair + block) mod half``.
    Across the full schedule this requires two adjacent affine floater edges,
    except the final factor, which only receives the wrap edge.
    """
    half = (team_count - 1) // 2
    out: list[list[tuple[int, int]]] = [[] for _ in range(half)]
    for round_pair in range(half):
        for block in range(half):
            factor = (round_pair + block) % half
            edge = _affine_floater_edge(team_count, round_pair, block)
            if edge not in out[factor]:
                out[factor].append(edge)
    return tuple(tuple(edges) for edges in out)


def _one_odd_components(
    team_count: int, factor: set[tuple[int, int]]
) -> list[set[int]]:
    adj: list[list[int]] = [[] for _team in range(team_count)]
    for first, second in factor:
        adj[first].append(second)
        adj[second].append(first)
    unseen = set(range(team_count))
    components = []
    while unseen:
        start = min(unseen)
        component = {start}
        unseen.remove(start)
        stack = [start]
        while stack:
            team = stack.pop()
            for other in adj[team]:
                if other in unseen:
                    unseen.remove(other)
                    component.add(other)
                    stack.append(other)
        components.append(component)
    return components


def _one_odd_factor_score(
    team_count: int,
    factor: set[tuple[int, int]],
    prescribed: set[tuple[int, int]],
) -> tuple[int, int, int, int, int]:
    components = _one_odd_components(team_count, factor)
    prescribed_teams = {team for edge in prescribed for team in edge}
    prescribed_components = [
        component for component in components if component & prescribed_teams
    ]
    odd_components = [component for component in components if len(component) % 2 == 1]
    split_prescribed = max(0, len(prescribed_components) - 1)
    prescribed_even = 0
    if len(prescribed_components) == 1 and prescribed_teams <= prescribed_components[0]:
        prescribed_even = 1 - (len(prescribed_components[0]) % 2)
    extra_odd = sum(
        1 for component in odd_components if not (prescribed_teams <= component)
    )
    valid = split_prescribed == 0 and prescribed_even == 0 and extra_odd == 0
    return (
        0 if valid else 1,
        split_prescribed,
        prescribed_even,
        extra_odd,
        len(components),
    )


def _one_odd_total_score(
    team_count: int,
    factors: list[set[tuple[int, int]]],
    prescribed: tuple[set[tuple[int, int]], ...],
) -> tuple[int, int, int, int, int]:
    scores = [
        _one_odd_factor_score(team_count, factor, prescribed[factor_index])
        for factor_index, factor in enumerate(factors)
    ]
    return tuple(sum(score[index] for score in scores) for index in range(5))  # type: ignore[return-value]


def _one_odd_length_factor(team_count: int, edge: tuple[int, int]) -> int:
    first, second = edge
    distance = (second - first) % team_count
    return min(distance, team_count - distance) - 1


def _one_odd_degree_score(degrees: list[list[int]]) -> int:
    return sum(abs(degree - 2) for factor in degrees for degree in factor)


def _one_odd_recolour_delta(
    degrees: list[list[int]],
    edge: tuple[int, int],
    source: int,
    target: int,
) -> int:
    first, second = edge
    old = (
        abs(degrees[source][first] - 2)
        + abs(degrees[source][second] - 2)
        + abs(degrees[target][first] - 2)
        + abs(degrees[target][second] - 2)
    )
    new = (
        abs(degrees[source][first] - 3)
        + abs(degrees[source][second] - 3)
        + abs(degrees[target][first] - 1)
        + abs(degrees[target][second] - 1)
    )
    return new - old


def _one_odd_initial_factors(
    team_count: int, attempt: int
) -> tuple[tuple[tuple[int, int], ...], ...] | None:
    """Dependency-free degree model for a prescribed 2-factorisation.

    Start from the cyclic length-class 2-factorisation, force the affine
    prescribed edges into their required factors, then recolour non-prescribed
    edges until every factor has degree 2 at every team. This is the narrow
    degree subproblem; component shape is still handled by the deterministic
    4-edge repair pass.
    """
    half = (team_count - 1) // 2
    rng = _DeterministicRng(attempt + 1)
    edges = [
        (first, second)
        for first in range(team_count)
        for second in range(first + 1, team_count)
    ]
    prescribed = {
        edge: factor
        for factor, factor_edges in enumerate(_one_odd_prescribed_edges(team_count))
        for edge in factor_edges
    }

    if attempt % 2 == 0:
        permutation = list(range(half))
    else:
        permutation = list(range(half))
        rng.shuffle(permutation)

    edge_factor = {
        edge: permutation[_one_odd_length_factor(team_count, edge)] for edge in edges
    }
    for edge, factor in prescribed.items():
        edge_factor[edge] = factor

    degrees = [[0] * team_count for _factor in range(half)]
    for (first, second), factor in edge_factor.items():
        degrees[factor][first] += 1
        degrees[factor][second] += 1

    fixed = set(prescribed)
    free_edges = [edge for edge in edges if edge not in fixed]
    incident_edges: list[list[tuple[int, int]]] = [[] for _team in range(team_count)]
    for edge in free_edges:
        first, second = edge
        incident_edges[first].append(edge)
        incident_edges[second].append(edge)

    score = _one_odd_degree_score(degrees)
    plateau_steps = 0
    max_steps = max(5000, team_count * team_count * team_count)
    for _step in range(max_steps):
        if score == 0:
            factors: list[list[tuple[int, int]]] = [[] for _factor in range(half)]
            for edge, factor in edge_factor.items():
                factors[factor].append(edge)
            return tuple(tuple(sorted(factor)) for factor in factors)

        excess = [
            (degrees[factor][team] - 2, factor, team)
            for factor in range(half)
            for team in range(team_count)
            if degrees[factor][team] > 2
        ]
        if not excess:
            return None
        excess.sort(reverse=True)
        deficit_by_team = [
            [factor for factor in range(half) if degrees[factor][team] < 2]
            for team in range(team_count)
        ]

        moves: list[tuple[int, tuple[int, int], int, int]] = []
        for _excess, source, team in excess[:30]:
            candidates = list(incident_edges[team])
            rng.shuffle(candidates)
            for edge in candidates[:80]:
                if edge_factor[edge] != source:
                    continue
                first, second = edge
                targets = list(
                    set(deficit_by_team[first]) | set(deficit_by_team[second])
                )
                if not targets:
                    targets = list(range(half))
                rng.shuffle(targets)
                for target in targets:
                    if target == source:
                        continue
                    delta = _one_odd_recolour_delta(degrees, edge, source, target)
                    if delta <= 0:
                        moves.append((delta, edge, source, target))
                if len(moves) > 200:
                    break
            if len(moves) > 200:
                break

        if not moves:
            _excess, source, team = rng.choice(excess)
            source_edges = [
                edge for edge in incident_edges[team] if edge_factor[edge] == source
            ]
            if not source_edges:
                return None
            edge = rng.choice(source_edges)
            target = rng.randrange(half)
            if target == source:
                target = (target + 1) % half
            moves = [
                (
                    _one_odd_recolour_delta(degrees, edge, source, target),
                    edge,
                    source,
                    target,
                )
            ]

        improving = [move for move in moves if move[0] < 0]
        neutral = [move for move in moves if move[0] == 0]
        if improving:
            rng.shuffle(improving)
            delta, edge, source, target = min(improving, key=lambda move: move[0])
            plateau_steps = 0
        elif neutral and plateau_steps < 2000:
            delta, edge, source, target = rng.choice(neutral)
            plateau_steps += 1
        else:
            moves.sort(key=lambda move: move[0])
            delta, edge, source, target = rng.choice(moves[: min(20, len(moves))])
            plateau_steps = 0

        first, second = edge
        edge_factor[edge] = target
        degrees[source][first] -= 1
        degrees[source][second] -= 1
        degrees[target][first] += 1
        degrees[target][second] += 1
        score += delta
    return None


def _one_odd_repair_factors(
    team_count: int,
    factors_in: tuple[tuple[tuple[int, int], ...], ...],
) -> tuple[tuple[tuple[int, int], ...], ...] | None:
    """Repair degree-valid factors into Molter-materialisable one-odd factors."""
    factors = [set(factor) for factor in factors_in]
    edge_factor = {
        edge: factor_i for factor_i, factor in enumerate(factors) for edge in factor
    }
    prescribed = tuple(set(edges) for edges in _one_odd_prescribed_edges(team_count))
    rng = _DeterministicRng(1)

    def can_remove(factor_i: int, edge: tuple[int, int]) -> bool:
        return edge not in prescribed[factor_i]

    def swap(
        first_factor: int,
        second_factor: int,
        first_edges: tuple[tuple[int, int], tuple[int, int]],
        second_edges: tuple[tuple[int, int], tuple[int, int]],
    ) -> None:
        for edge in first_edges:
            factors[first_factor].remove(edge)
            del edge_factor[edge]
        for edge in second_edges:
            factors[second_factor].remove(edge)
            del edge_factor[edge]
        for edge in second_edges:
            factors[first_factor].add(edge)
            edge_factor[edge] = first_factor
        for edge in first_edges:
            factors[second_factor].add(edge)
            edge_factor[edge] = second_factor

    def component_edges(
        factor: set[tuple[int, int]], component: set[int]
    ) -> list[tuple[int, int]]:
        return [
            edge for edge in factor if edge[0] in component and edge[1] in component
        ]

    def candidate_swaps(factor_i: int, limit: int):
        components = _one_odd_components(team_count, factors[factor_i])
        prescribed_teams = {team for edge in prescribed[factor_i] for team in edge}
        infos = []
        for component in components:
            has_prescribed = bool(component & prescribed_teams)
            has_all_prescribed = prescribed_teams <= component
            bad = (len(component) % 2 == 1 and not has_all_prescribed) or (
                len(component) % 2 == 0 and has_prescribed
            )
            infos.append((bad, component))
        bad_infos = [info for info in infos if info[0]]
        if not bad_infos:
            return
        targets = bad_infos + infos
        rng.shuffle(targets)
        yielded = 0
        for _bad, first_component in bad_infos:
            first_edges = component_edges(factors[factor_i], first_component)
            rng.shuffle(first_edges)
            for _target_bad, second_component in targets:
                if first_component is second_component:
                    continue
                second_edges = component_edges(factors[factor_i], second_component)
                rng.shuffle(second_edges)
                for first_edge in first_edges[:8]:
                    if not can_remove(factor_i, first_edge):
                        continue
                    first_a, first_b = first_edge
                    for second_edge in second_edges[:8]:
                        if not can_remove(factor_i, second_edge):
                            continue
                        second_a, second_b = second_edge
                        for other_edges in (
                            (
                                _team_edge(first_a, second_a),
                                _team_edge(first_b, second_b),
                            ),
                            (
                                _team_edge(first_a, second_b),
                                _team_edge(first_b, second_a),
                            ),
                        ):
                            if (
                                other_edges[0] == other_edges[1]
                                or other_edges[0] in factors[factor_i]
                                or other_edges[1] in factors[factor_i]
                            ):
                                continue
                            other_factor = edge_factor[other_edges[0]]
                            if (
                                other_factor == factor_i
                                or edge_factor[other_edges[1]] != other_factor
                                or not can_remove(other_factor, other_edges[0])
                                or not can_remove(other_factor, other_edges[1])
                            ):
                                continue
                            yield other_factor, (first_edge, second_edge), other_edges
                            yielded += 1
                            if yielded >= limit:
                                return

    factor_scores = [
        _one_odd_factor_score(team_count, factor, prescribed[factor_i])
        for factor_i, factor in enumerate(factors)
    ]
    current = tuple(sum(score[index] for score in factor_scores) for index in range(5))
    for _step in range(team_count):
        if current[0] == 0:
            return tuple(tuple(sorted(factor)) for factor in factors)
        factor_order = list(range(len(factors)))
        factor_order.sort(key=lambda factor_i: factor_scores[factor_i], reverse=True)
        moved = False
        for factor_i in factor_order:
            factor_score = factor_scores[factor_i]
            if factor_score[0] == 0:
                continue
            best_move = None
            for other_factor, factor_edges, other_edges in candidate_swaps(
                factor_i, 2000
            ):
                swap(factor_i, other_factor, factor_edges, other_edges)
                next_factor_score = _one_odd_factor_score(
                    team_count, factors[factor_i], prescribed[factor_i]
                )
                next_other_score = _one_odd_factor_score(
                    team_count, factors[other_factor], prescribed[other_factor]
                )
                next_score = tuple(
                    current[index]
                    - factor_scores[factor_i][index]
                    - factor_scores[other_factor][index]
                    + next_factor_score[index]
                    + next_other_score[index]
                    for index in range(5)
                )
                swap(factor_i, other_factor, other_edges, factor_edges)
                if next_score < current and (
                    best_move is None or next_score < best_move[0]
                ):
                    best_move = (
                        next_score,
                        other_factor,
                        factor_edges,
                        other_edges,
                        next_factor_score,
                        next_other_score,
                    )
                    if next_score[0] < current[0]:
                        break
            if best_move is not None:
                (
                    current,
                    other_factor,
                    factor_edges,
                    other_edges,
                    next_factor_score,
                    next_other_score,
                ) = best_move
                swap(factor_i, other_factor, factor_edges, other_edges)
                factor_scores[factor_i] = next_factor_score
                factor_scores[other_factor] = next_other_score
                moved = True
                break
        if not moved:
            return None
    return None


@lru_cache(maxsize=None)
def _one_odd_factorization(
    team_count: int,
) -> tuple[tuple[tuple[int, int], ...], ...] | None:
    """Fast full-layer construction target for odd complete-I1 layers.

    A narrow recolouring pass first finds a degree-valid prescribed
    2-factorisation; a small deterministic 4-edge switching pass then makes every
    factor materialisable by Molter's two-board layout.
    """
    if team_count < 7 or team_count > 99:
        return None
    for attempt in range(12):
        initial = _one_odd_initial_factors(team_count, attempt)
        if initial is None:
            continue
        repaired = _one_odd_repair_factors(team_count, initial)
        if repaired is not None:
            return repaired
    return None


def _small_one_odd_factorization(
    team_count: int,
) -> tuple[tuple[tuple[int, int], ...], ...] | None:
    """Tiny exceptional one-odd factors.

    ``N=3`` is below the general factor search range. ``N=5`` cannot use the
    affine-perfect target built into ``_one_odd_factorization``: S6c and
    lower-bound I2 conflict, and the best full-table spread is 2. These fixed
    factors still fit the one-odd materializer.
    """
    if team_count == 3:
        return (((0, 1), (0, 2), (1, 2)),)
    if team_count == 5:
        return (
            ((0, 3), (0, 4), (1, 2), (1, 3), (2, 4)),
            ((0, 1), (0, 2), (1, 4), (2, 3), (3, 4)),
        )
    return None


def _one_odd_cycle_order(
    component: set[int], factor: set[tuple[int, int]]
) -> list[int]:
    adj: dict[int, list[int]] = {team: [] for team in component}
    for first, second in factor:
        if first in component and second in component:
            adj[first].append(second)
            adj[second].append(first)
    start = min(component)
    order = [start]
    previous = -1
    current = start
    while True:
        choices = [team for team in sorted(adj[current]) if team != previous]
        next_team = choices[0]
        if next_team == start:
            return order
        order.append(next_team)
        previous, current = current, next_team


def _one_odd_path_after_dropping(
    component: set[int],
    factor: set[tuple[int, int]],
    dropped: tuple[int, int],
) -> list[int]:
    adj: dict[int, list[int]] = {team: [] for team in component}
    dropped_edge = _team_edge(dropped[0], dropped[1])
    for first, second in factor:
        if _team_edge(first, second) == dropped_edge:
            continue
        if first in component and second in component:
            adj[first].append(second)
            adj[second].append(first)
    start, end = dropped
    path = [start]
    previous = -1
    current = start
    while current != end:
        choices = [team for team in sorted(adj[current]) if team != previous]
        next_team = choices[0]
        path.append(next_team)
        previous, current = current, next_team
    return path


def _one_odd_cell_matches(
    team_count: int,
    factor: tuple[tuple[int, int], ...],
    dropped: tuple[int, int],
    odd_slot: int,
    even_slot: int,
    reverse: bool,
) -> list[_Match]:
    factor_set = set(factor)
    components = _one_odd_components(team_count, factor_set)
    dropped_component = next(
        component for component in components if dropped[0] in component
    )
    path = _one_odd_path_after_dropping(dropped_component, factor_set, dropped)
    if reverse:
        path = list(reversed(path))

    out: list[_Match] = [((path[-1], odd_slot), (path[0], even_slot))]
    for index in range(0, len(path) - 1, 2):
        out.append(((path[index], odd_slot), (path[index + 1], odd_slot)))
    for index in range(1, len(path) - 1, 2):
        out.append(((path[index], even_slot), (path[index + 1], even_slot)))

    for component in components:
        if component == dropped_component:
            continue
        cycle = _one_odd_cycle_order(component, factor_set)
        if reverse:
            # Shift parity so round two uses the alternate matching on each
            # adjacent board; reversing alone preserves parity on even cycles.
            cycle = cycle[1:] + cycle[:1]
        for index in range(0, len(cycle), 2):
            out.append(
                ((cycle[index], odd_slot), (cycle[(index + 1) % len(cycle)], odd_slot))
            )
        for index in range(1, len(cycle), 2):
            out.append(
                (
                    (cycle[index], even_slot),
                    (cycle[(index + 1) % len(cycle)], even_slot),
                )
            )
    return out


def _one_odd_factor_odd_edges(
    team_count: int,
    factors: tuple[tuple[tuple[int, int], ...], ...],
) -> tuple[tuple[tuple[int, int], ...], ...]:
    prescribed = tuple(set(edges) for edges in _one_odd_prescribed_edges(team_count))
    out = []
    for factor_index, factor in enumerate(factors):
        factor_set = set(factor)
        components = _one_odd_components(team_count, factor_set)
        prescribed_teams = {team for edge in prescribed[factor_index] for team in edge}
        odd_component = next(
            component
            for component in components
            if len(component) % 2 == 1 and prescribed_teams <= component
        )
        out.append(
            tuple(
                sorted(
                    edge
                    for edge in factor
                    if edge[0] in odd_component and edge[1] in odd_component
                )
            )
        )
    return tuple(out)


def _one_odd_partial_offsets(team_count: int, block_count: int) -> tuple[int, ...]:
    half = (team_count - 1) // 2
    return tuple((index * half) // block_count for index in range(block_count))


def _one_odd_partial_score(
    counts: list[int] | tuple[int, ...],
) -> tuple[int, int, int, tuple[int, ...]]:
    return (
        max(counts) - min(counts),
        max(counts),
        sum(count * count for count in counts),
        tuple(counts),
    )


def _one_odd_affine_partial_contribution(
    team_count: int, rounds: int, offset: int
) -> tuple[int, ...]:
    counts = [0] * team_count
    full_round_pairs = rounds // 2
    for round_pair in range(full_round_pairs):
        first, second = _affine_floater_edge(team_count, round_pair, offset)
        counts[first] += 1
        counts[second] += 1
    if rounds % 2 == 1:
        _first, second = _affine_floater_edge(team_count, full_round_pairs, offset)
        counts[second] += 1
    return tuple(counts)


def _one_odd_select_affine_partial_offsets(
    team_count: int,
    rounds: int,
    block_count: int,
    initial_counts: tuple[int, ...],
) -> tuple[tuple[int, ...], tuple[int, ...]]:
    half = (team_count - 1) // 2
    contributions = [
        _one_odd_affine_partial_contribution(team_count, rounds, offset)
        for offset in range(half)
    ]
    counts = list(initial_counts)
    chosen: list[int] = []
    remaining = set(range(half))

    for _block in range(block_count):
        best: tuple[tuple[int, int, int, tuple[int, ...]], int, list[int]] | None = None
        for offset in sorted(remaining):
            candidate = [
                counts[team] + contributions[offset][team] for team in range(team_count)
            ]
            score = _one_odd_partial_score(candidate)
            if best is None or score < best[0]:
                best = score, offset, candidate
        assert best is not None
        _score, offset, counts = best
        chosen.append(offset)
        remaining.remove(offset)

    improved = True
    while improved:
        improved = False
        base_score = _one_odd_partial_score(counts)
        best_swap = None
        for index, old_offset in enumerate(chosen):
            for new_offset in sorted(remaining):
                candidate = [
                    counts[team]
                    - contributions[old_offset][team]
                    + contributions[new_offset][team]
                    for team in range(team_count)
                ]
                score = _one_odd_partial_score(candidate)
                if score < base_score and (best_swap is None or score < best_swap[0]):
                    best_swap = score, index, old_offset, new_offset, candidate
        if best_swap is not None:
            _score, index, old_offset, new_offset, counts = best_swap
            chosen[index] = new_offset
            remaining.remove(new_offset)
            remaining.add(old_offset)
            improved = True

    return tuple(sorted(chosen)), tuple(counts)


def _one_odd_affine_partial_plan(
    team_count: int,
    rounds: int,
    block_count: int,
    initial_counts: tuple[int, ...],
    require_optimal: bool = True,
) -> tuple[_OneOddPlan, tuple[int, ...]] | None:
    """Fast affine-offset partial plan when it already reaches optimal I2."""
    half = (team_count - 1) // 2
    num_round_pairs = (rounds + 1) // 2
    offsets, counts = _one_odd_select_affine_partial_offsets(
        team_count, rounds, block_count, initial_counts
    )
    total = sum(initial_counts) + block_count * rounds
    lower_bound = 0 if total % team_count == 0 else 1
    if require_optimal and _one_odd_partial_score(counts)[0] != lower_bound:
        return None

    row_used = [0] * num_round_pairs
    block_used = [0] * block_count
    plan: list[tuple[_OneOddPlanCell, ...]] = []
    for round_pair in range(num_round_pairs):
        row = []
        for block, offset in enumerate(offsets):
            dropped = _affine_floater_edge(team_count, round_pair, offset)
            mask = (1 << dropped[0]) | (1 << dropped[1])
            if row_used[round_pair] & mask or block_used[block] & mask:
                return None
            row_used[round_pair] |= mask
            block_used[block] |= mask
            row.append(((round_pair + offset) % half, dropped))
        plan.append(tuple(row))
    incidence = tuple(counts[team] - initial_counts[team] for team in range(team_count))
    return tuple(plan), incidence


def _one_odd_partial_plan(
    team_count: int,
    rounds: int,
    block_count: int,
    initial_counts: tuple[int, ...],
    factors: tuple[tuple[tuple[int, int], ...], ...],
    offsets: tuple[int, ...] | None = None,
    salt_start: int = 0,
    max_salts: int = 8,
    max_spread: int | None = None,
) -> tuple[_OneOddPlan, tuple[int, ...]] | None:
    """Choose partial-layer one-odd cells with optimal descending-floater spread."""
    half = (team_count - 1) // 2
    num_round_pairs = (rounds + 1) // 2
    full_round_pairs = rounds // 2
    factor_edges = _one_odd_factor_odd_edges(team_count, factors)
    if offsets is None:
        offsets = _one_odd_partial_offsets(team_count, block_count)
    variables = [
        (block, round_pair)
        for block in range(block_count)
        for round_pair in range(num_round_pairs)
    ]
    variable_index = {variable: index for index, variable in enumerate(variables)}
    variable_units = [
        2 if round_pair < full_round_pairs else 1 for _, round_pair in variables
    ]
    total = sum(initial_counts) + block_count * rounds
    average_floor = total // team_count
    max_initial = max(initial_counts, default=0)
    best_possible_spread = 0 if total % team_count == 0 else 1
    node_budget = 20_000

    options_by_variable: list[
        list[tuple[int, tuple[int, int], int, int, int, int]]
    ] = []
    for block, round_pair in variables:
        factor = (round_pair + offsets[block]) % half
        options = []
        for edge in factor_edges[factor]:
            first, second = edge
            mask = (1 << first) | (1 << second)
            if round_pair < full_round_pairs:
                options.append((factor, (first, second), first, second, 2, mask))
            else:
                options.append((factor, (first, second), second, -1, 1, mask))
                options.append((factor, (second, first), first, -1, 1, mask))
        options_by_variable.append(options)

    def option_tie_break(
        block: int, round_pair: int, dropped: tuple[int, int], salt: int
    ) -> int:
        value = (
            dropped[0] * 1_000_003
            + dropped[1] * 9_176
            + block * 131
            + round_pair * 8_191
            + salt * 2_654_435_761
        ) & 0xFFFFFFFF
        value ^= value >> 16
        value = (value * 0x7FEB_352D) & 0xFFFFFFFF
        value ^= value >> 15
        return value

    last_spread = total if max_spread is None else max_spread
    for spread in range(best_possible_spread, last_spread + 1):
        min_low = max(0, (total - team_count * spread + team_count - 1) // team_count)
        for low_bound in range(average_floor, min_low - 1, -1):
            high = low_bound + spread
            if high < max_initial:
                continue
            for salt in range(salt_start, salt_start + max_salts):
                row_used = [0] * num_round_pairs
                block_used = [0] * block_count
                counts = list(initial_counts)
                chosen: list[tuple[int, tuple[int, int]] | None] = [None] * len(
                    variables
                )
                nodes = 0

                def place(done: int, remaining_units: int) -> bool:
                    nonlocal nodes
                    nodes += 1
                    if nodes > node_budget:
                        return False

                    needed = sum(max(0, low_bound - count) for count in counts)
                    if needed > remaining_units:
                        return False
                    capacity = sum(max(0, high - count) for count in counts)
                    if capacity < remaining_units:
                        return False
                    if done == len(chosen):
                        return min(counts) >= low_bound and max(counts) <= high

                    if low_bound and done * 2 >= len(chosen):
                        possible = [0] * team_count
                        for var_index, (block, round_pair) in enumerate(variables):
                            if chosen[var_index] is not None:
                                continue
                            blocked = row_used[round_pair] | block_used[block]
                            possible_teams = 0
                            for option in options_by_variable[var_index]:
                                if not (option[5] & blocked):
                                    possible_teams |= option[5]
                            while possible_teams:
                                bit = possible_teams & -possible_teams
                                team = bit.bit_length() - 1
                                possible[team] += 1
                                possible_teams ^= bit
                        for team, count in enumerate(counts):
                            if count + possible[team] < low_bound:
                                return False

                    best_var_index = -1
                    best_options: (
                        list[
                            tuple[
                                int,
                                tuple[int, int],
                                int,
                                int,
                                int,
                                int,
                            ]
                        ]
                        | None
                    ) = None
                    for var_index, (block, round_pair) in enumerate(variables):
                        if chosen[var_index] is not None:
                            continue
                        blocked = row_used[round_pair] | block_used[block]
                        options = []
                        for option in options_by_variable[var_index]:
                            factor, dropped, first, second, unit_count, mask = option
                            if mask & blocked:
                                continue
                            if unit_count == 2:
                                if counts[first] < high and counts[second] < high:
                                    options.append(option)
                            elif counts[first] < high:
                                options.append(option)
                        if best_options is None or len(options) < len(best_options):
                            best_var_index = var_index
                            best_options = options
                            if not options:
                                break
                    if not best_options or best_var_index < 0:
                        return False

                    block, round_pair = variables[best_var_index]
                    best_options.sort(
                        key=lambda option: (
                            counts[option[2]]
                            if option[4] == 1
                            else counts[option[2]] + counts[option[3]],
                            counts[option[2]]
                            if option[4] == 1
                            else max(counts[option[2]], counts[option[3]]),
                            option_tie_break(block, round_pair, option[1], salt),
                        )
                    )
                    for (
                        factor,
                        dropped,
                        first,
                        second,
                        unit_count,
                        mask,
                    ) in best_options:
                        chosen[best_var_index] = (factor, dropped)
                        row_used[round_pair] |= mask
                        block_used[block] |= mask
                        counts[first] += 1
                        if unit_count == 2:
                            counts[second] += 1
                        if place(
                            done + 1,
                            remaining_units - variable_units[best_var_index],
                        ):
                            return True
                        if unit_count == 2:
                            counts[second] -= 1
                        counts[first] -= 1
                        block_used[block] ^= mask
                        row_used[round_pair] ^= mask
                        chosen[best_var_index] = None
                    return False

                if place(0, sum(variable_units)):
                    plan: list[tuple[_OneOddPlanCell, ...]] = []
                    for round_pair in range(num_round_pairs):
                        row: list[_OneOddPlanCell] = []
                        for block in range(block_count):
                            cell = chosen[variable_index[(block, round_pair)]]
                            assert cell is not None
                            row.append(cell)
                        plan.append(tuple(row))
                    incidence = tuple(
                        counts[team] - initial_counts[team]
                        for team in range(team_count)
                    )
                    return tuple(plan), incidence
    return None


def _complete_i1_one_odd_plan_blocks(
    team_count: int,
    rounds: int,
    block_offset: int,
    plan: _OneOddPlan,
    factors: tuple[tuple[tuple[int, int], ...], ...],
) -> list[list[_Match]]:
    out: list[list[_Match]] = []
    for r_index in range(rounds):
        round_pair = r_index // 2
        reverse = r_index % 2 == 1
        rnd: list[_Match] = []
        for block, (factor_index, dropped) in enumerate(plan[round_pair]):
            odd_slot = 2 * (block_offset + block)
            even_slot = odd_slot + 1
            rnd.extend(
                _one_odd_cell_matches(
                    team_count,
                    factors[factor_index],
                    dropped,
                    odd_slot,
                    even_slot,
                    reverse,
                )
            )
        out.append(rnd)
    return out


def _shift_layer_teams(
    matches: list[list[_Match]], team_count: int, shift: int
) -> list[list[_Match]]:
    shift %= team_count
    if shift == 0:
        return matches
    return [
        [
            (
                (((first[0] + shift) % team_count), first[1]),
                (((second[0] + shift) % team_count), second[1]),
            )
            for first, second in rnd
        ]
        for rnd in matches
    ]


def _shift_team_counts(counts: tuple[int, ...], shift: int) -> tuple[int, ...]:
    shifted = [0] * len(counts)
    for team, count in enumerate(counts):
        shifted[(team + shift) % len(counts)] = count
    return tuple(shifted)


def _layer_descending_incidence(
    matches: list[list[_Match]], team_count: int
) -> tuple[int, ...]:
    counts = [0] * team_count
    for rnd in matches:
        for first, second in rnd:
            if first[1] < second[1]:
                counts[first[0]] += 1
            elif second[1] < first[1]:
                counts[second[0]] += 1
    return tuple(counts)


def _best_layer_shift(
    initial_counts: tuple[int, ...], incidence: tuple[int, ...]
) -> tuple[int, tuple[int, ...]]:
    """Rotate a complete or partial odd layer's team labels to balance I2.

    Team-label rotation is a graph automorphism of the layer: it preserves the
    pairings, floater legality, S6c, colours-to-be-assigned, and per-round I1
    shape. It only changes which real teams receive the layer's descending
    floater incidences.
    """
    best = None
    for shift in range(len(incidence)):
        shifted = _shift_team_counts(incidence, shift)
        final_counts = [
            initial_counts[team] + shifted[team] for team in range(len(incidence))
        ]
        score = _one_odd_partial_score(final_counts) + (shift,)
        if best is None or score < best[0]:
            best = score, shift, shifted
    assert best is not None
    return best[1], best[2]


def _optimise_layer_shifts(incidences: list[tuple[int, ...]]) -> tuple[int, ...]:
    """Choose final team-label rotations for all odd layers to minimize I2.

    For small layer counts we can check every rotation tuple exactly. For larger
    stacks, start from greedy per-layer shifts and run deterministic coordinate
    improvement. The shifts are applied only after all layer matches are built.
    """
    if not incidences:
        return ()
    team_count = len(incidences[0])
    exact_search_limit = 200_000
    combinations = 1
    for _ in incidences:
        combinations *= team_count
        if combinations > exact_search_limit:
            break

    def score(shifts: tuple[int, ...]) -> tuple[int, int, int, tuple[int, ...]]:
        counts = [0] * team_count
        for incidence, shift in zip(incidences, shifts):
            shifted = _shift_team_counts(incidence, shift)
            for team, count in enumerate(shifted):
                counts[team] += count
        return _one_odd_partial_score(counts)

    if combinations <= exact_search_limit:
        best_score: tuple[int, int, int, tuple[int, ...]] | None = None
        best_shifts: tuple[int, ...] | None = None
        for shift_tuple in product(range(team_count), repeat=len(incidences)):
            candidate_score = score(shift_tuple)
            if best_score is None or candidate_score < best_score:
                best_score = candidate_score
                best_shifts = shift_tuple
        assert best_shifts is not None
        return best_shifts

    shifts: list[int] = []
    counts = [0] * team_count
    for incidence in incidences:
        shift, shifted = _best_layer_shift(tuple(counts), incidence)
        shifts.append(shift)
        for team, count in enumerate(shifted):
            counts[team] += count

    improved = True
    while improved:
        improved = False
        base_score = score(tuple(shifts))
        for layer, old_shift in enumerate(shifts):
            best = (base_score, old_shift)
            for new_shift in range(team_count):
                if new_shift == old_shift:
                    continue
                candidate_shifts = list(shifts)
                candidate_shifts[layer] = new_shift
                candidate_score = score(tuple(candidate_shifts))
                if candidate_score < best[0]:
                    best = (candidate_score, new_shift)
            if best[1] != old_shift:
                shifts[layer] = best[1]
                improved = True
                break
    return tuple(shifts)


def _complete_i1_one_odd_blocks(
    team_count: int,
    rounds: int,
    block_offset: int,
    block_count: int,
    factors: tuple[tuple[tuple[int, int], ...], ...],
) -> list[list[_Match]]:
    half = (team_count - 1) // 2
    out: list[list[_Match]] = []
    for r_index in range(rounds):
        round_pair = r_index // 2
        reverse = r_index % 2 == 1
        rnd: list[_Match] = []
        for block in range(block_count):
            factor_index = (round_pair + block) % half
            dropped = _affine_floater_edge(team_count, round_pair, block)
            odd_slot = 2 * (block_offset + block)
            even_slot = odd_slot + 1
            rnd.extend(
                _one_odd_cell_matches(
                    team_count,
                    factors[factor_index],
                    dropped,
                    odd_slot,
                    even_slot,
                    reverse,
                )
            )
        out.append(rnd)
    return out


def _complete_i1_matches(
    team_count: int, players_per_team: int, rounds: int
) -> list[list[_Match]]:
    """Construct odd-team rounds for any even ``P``. Full layers of ``half``
    blocks give per-round I1; a final partial layer (when ``N − 1`` does not
    divide ``P``) keeps every player on a distinct opposing team each round
    (S4) and a legal floater per block, with best-effort team spread.

    Supported odd sizes first try the prescribed one-odd 2-factor construction.
    Full layers use its affine dropped edges directly. Partial layers use a
    legal affine offset subset when that already reaches the arithmetic I2 lower
    bound; otherwise a bounded one-odd repair search tries to reach that lower
    bound before falling back to the same fast legal affine subset. Unsupported
    odd sizes fail explicitly instead of running a slower alternate search."""
    half = (team_count - 1) // 2
    blocks = players_per_team // 2
    num_round_pairs = (rounds + 1) // 2
    layers: list[tuple[list[list[_Match]], tuple[int, ...]]] = []
    # Planning counts guide later layer construction. Final I2 is optimized after
    # all layers exist by rotating whole layers in _optimise_layer_shifts.
    planning_floater_count = [0] * team_count
    block_offset = 0
    one_odd_factors = _one_odd_factorization(team_count)
    use_affine_full_layers = one_odd_factors is not None
    if one_odd_factors is None:
        one_odd_factors = _small_one_odd_factorization(team_count)
    if one_odd_factors is None:
        raise MolterGenerationError(
            f'No checked one-odd factorization for {team_count} teams.'
        )
    while block_offset < blocks:
        count = min(half, blocks - block_offset)
        if count == half:
            if use_affine_full_layers:
                layer_matches = _complete_i1_one_odd_blocks(
                    team_count, rounds, block_offset, count, one_odd_factors
                )
            else:
                result = _one_odd_partial_plan(
                    team_count,
                    rounds,
                    count,
                    tuple(planning_floater_count),
                    one_odd_factors,
                    max_spread=2,
                )
                if result is None:
                    raise MolterGenerationError(
                        f'No valid small one-odd plan for {team_count} teams, '
                        f'{count} blocks, over {num_round_pairs} round-pairs.'
                    )
                plan, _ = result
                layer_matches = _complete_i1_one_odd_plan_blocks(
                    team_count,
                    rounds,
                    block_offset,
                    plan,
                    one_odd_factors,
                )
        else:
            if use_affine_full_layers:
                result = _one_odd_affine_partial_plan(
                    team_count,
                    rounds,
                    count,
                    tuple(planning_floater_count),
                )
            else:
                result = None
            if result is None and use_affine_full_layers:
                affine_offsets, _counts = _one_odd_select_affine_partial_offsets(
                    team_count,
                    rounds,
                    count,
                    tuple(planning_floater_count),
                )
                floor_offsets = _one_odd_partial_offsets(team_count, count)
                offset_candidates = [floor_offsets]
                if affine_offsets != floor_offsets:
                    offset_candidates.append(affine_offsets)
                target_spread = (
                    0
                    if (sum(planning_floater_count) + count * rounds) % team_count == 0
                    else 1
                )
                if rounds <= 12 or count * num_round_pairs <= 36:
                    for salt in range(4):
                        for offsets in offset_candidates:
                            result = _one_odd_partial_plan(
                                team_count,
                                rounds,
                                count,
                                tuple(planning_floater_count),
                                one_odd_factors,
                                offsets,
                                salt,
                                1,
                                target_spread,
                            )
                            if result is not None:
                                break
                        if result is not None:
                            break
                if result is None:
                    result = _one_odd_affine_partial_plan(
                        team_count,
                        rounds,
                        count,
                        tuple(planning_floater_count),
                        require_optimal=False,
                    )
            elif result is None:
                result = _one_odd_partial_plan(
                    team_count,
                    rounds,
                    count,
                    tuple(planning_floater_count),
                    one_odd_factors,
                    max_spread=2,
                )
            if result is None:
                raise MolterGenerationError(
                    f'No valid one-odd partial plan for {team_count} teams, '
                    f'{count} blocks, over {num_round_pairs} round-pairs.'
                )
            plan, _ = result
            layer_matches = _complete_i1_one_odd_plan_blocks(
                team_count,
                rounds,
                block_offset,
                plan,
                one_odd_factors,
            )
        incidence = _layer_descending_incidence(layer_matches, team_count)
        layers.append((layer_matches, incidence))
        shift, incidence = _best_layer_shift(tuple(planning_floater_count), incidence)
        for team, added in enumerate(incidence):
            planning_floater_count[team] += added
        block_offset += count

    out: list[list[_Match]] = [[] for _ in range(rounds)]
    shifts = _optimise_layer_shifts([incidence for _matches, incidence in layers])
    for (layer_matches, _incidence), shift in zip(layers, shifts):
        shifted_matches = _shift_layer_teams(layer_matches, team_count, shift)
        for r_index, rnd in enumerate(shifted_matches):
            out[r_index].extend(rnd)
    return out


def _colour_complete_i1_matches(
    matches: list[list[_Match]], team_count: int
) -> list[_Round]:
    """Colour odd-team complete-I1 rounds with the Molter parity scheme:
    even-numbered (free) rounds are coloured Eulerian per layer-sized chunk
    (each team has even degree there, so each gets one White / one Black —
    per-team balance even on a lone final round); odd-numbered rounds are the
    forced flip. A final partial layer is the smaller last chunk."""
    layer_size = team_count * (team_count - 1) // 2
    rounds: list[_Round] = []
    for r_index, match in enumerate(matches):
        if r_index % 2 == 0:
            rnd: _Round = []
            for start in range(0, len(match), layer_size):
                rnd.extend(_eulerian_colour(match[start : start + layer_size]))
            rounds.append(rnd)
        else:
            rounds.append(_flip_colour(match, _colours(rounds[-1])))
    return rounds


# ---------- complete even tables (P = k × (N - 1), per-round I1) ----------


@lru_cache(maxsize=None)
def _one_factorization(team_count: int) -> tuple[tuple[tuple[int, int], ...], ...]:
    """1-factorization of ``K_N`` for even ``N`` (circle method): ``N - 1``
    perfect matchings whose edge sets partition every team pair. Team
    ``N - 1`` is the pivot; the others rotate around it. Deterministic."""
    pivot = team_count - 1
    ring = team_count - 1  # rotating positions 0..N-2
    factors: list[tuple[tuple[int, int], ...]] = []
    for b in range(ring):
        matching: list[tuple[int, int]] = [_team_edge(pivot, b)]
        for i in range(1, team_count // 2):
            matching.append(_team_edge((b + i) % ring, (b - i) % ring))
        factors.append(tuple(sorted(matching)))
    return tuple(factors)


def _complete_i1_even_matches(
    team_count: int, players_per_team: int, rounds: int
) -> list[list[_Match]]:
    """Construct even-team rounds for any even ``P``. Slot ``b`` in round ``r``
    plays the perfect matching ``M_(b + r)`` of the 1-factorisation — so a
    fixed slot meets a distinct team each round (S4), no floaters (S6a), and
    when ``N − 1`` divides ``P`` every team-pair appears equally each round
    (I1); otherwise the per-round spread is best-effort."""
    factors = _one_factorization(team_count)
    ring = team_count - 1
    out: list[list[_Match]] = []
    for r_index in range(rounds):
        rnd: list[_Match] = []
        for b in range(players_per_team):
            for i, j in factors[(b + r_index) % ring]:
                rnd.append(((i, b), (j, b)))
        out.append(rnd)
    return out


@lru_cache(maxsize=None)
def _two_colour(
    team_count: int,
    matching_a: tuple[tuple[int, int], ...],
    matching_b: tuple[tuple[int, int], ...],
) -> tuple[int, ...]:
    """Proper 2-colouring of the union of two disjoint perfect matchings (a
    2-regular graph whose every cycle is even). Class 0 is assigned to the
    lowest team of each component, so the result is deterministic."""
    adj: list[list[int]] = [[] for _ in range(team_count)]
    for i, j in matching_a + matching_b:
        adj[i].append(j)
        adj[j].append(i)
    colour = [-1] * team_count
    for start in range(team_count):
        if colour[start] != -1:
            continue
        colour[start] = 0
        stack = [start]
        while stack:
            u = stack.pop()
            for v in adj[u]:
                if colour[v] == -1:
                    colour[v] = 1 - colour[u]
                    stack.append(v)
    return tuple(colour)


def _colour_complete_i1_even_matches(
    matches: list[list[_Match]], team_count: int, players_per_team: int
) -> list[_Round]:
    """Colour even-team complete-I1 rounds.

    A free round orients slot ``b``'s matching ``M_a`` by a proper 2-colouring
    of ``M_a ∪ M_(a+1)``; because that colouring also properly splits
    ``M_(a+1)``, the next round's forced flip lands one White and one Black on
    every board. The flip pairs each player off across the round-pair, so every
    player — hence every team — is colour-balanced over an even number of
    rounds; no-tripling and the even→odd-only repeat rule hold likewise.

    For an odd round count the last (free) round has no flip partner; it is
    coloured Eulerian instead (each team plays an even ``P`` games there, so it
    is per-team balanced on its own) — giving team balance for any round
    count."""
    factors = _one_factorization(team_count)
    ring = team_count - 1
    last = len(matches) - 1
    rounds: list[_Round] = []
    for r_index, match in enumerate(matches):
        if r_index % 2 == 1:
            rounds.append(_flip_colour(match, _colours(rounds[-1])))
            continue
        if r_index == last:
            # Lone final (odd-round-count) free round: balance per team.
            rounds.append(_eulerian_colour(match))
            continue
        rnd: _Round = []
        for b in range(players_per_team):
            a = (b + r_index) % ring
            colour = _two_colour(team_count, factors[a], factors[(a + 1) % ring])
            for i, j in factors[a]:
                if colour[i] == 0:
                    rnd.append(((i, b), (j, b)))
                else:
                    rnd.append(((j, b), (i, b)))
        rounds.append(rnd)
    return rounds


# ---------- rendering ----------


def _emit(rnd: _Round) -> tuple[Pairing, ...]:
    """Render a coloured round as `Pairing`s, ordered by board number
    (all board-1 games first, then board-2 …; a block's floater grouped with
    its lower board)."""
    ordered = sorted(
        rnd,
        key=lambda board: (
            min(board[0][1], board[1][1]),
            max(board[0][1], board[1][1]),
            board[0][0],
            board[1][0],
        ),
    )
    return tuple(
        Pairing(
            _letter(white[0]),
            white[1] + 1,
            _letter(black[0]),
            black[1] + 1,
        )
        for white, black in ordered
    )


def _emit_even(rnd: _Round, team_count: int) -> tuple[Pairing, ...]:
    """Render an even-team round.

    Even tables have no floaters, so every game in a slot chunk has the same
    board number. Sorting each chunk by oriented teams is equivalent to the
    generic board sort and avoids repeatedly comparing board numbers.
    """
    chunk_size = team_count // 2
    letters = tuple(_letter(team) for team in range(team_count))
    out: list[Pairing] = []
    for start in range(0, len(rnd), chunk_size):
        chunk = sorted(
            rnd[start : start + chunk_size],
            key=lambda board: (board[0][0], board[1][0]),
        )
        for white, black in chunk:
            out.append(
                Pairing(
                    letters[white[0]],
                    white[1] + 1,
                    letters[black[0]],
                    black[1] + 1,
                )
            )
    return tuple(out)


# ---------- public API ----------


def default_molter_rounds(team_count: int) -> int:
    """Default regular-round count by convention: odd team counts up to 7
    are "complete" (all rounds ⇒ team_count − 1 rounds); others use 2. The
    arbiter can override."""
    if team_count in (5, 7):
        return team_count - 1
    return min(2, team_count - 1)


@lru_cache(maxsize=None)
def generate_molter_table(
    team_count: int,
    players_per_team: int,
    rounds: int | None = None,
) -> MolterTable:
    """Generate a Molter table. ``rounds`` defaults by convention
    (see :func:`default_molter_rounds`); it may range up to ``team_count − 1``.

    Deterministic: ``(team_count, players_per_team, rounds)`` defines a single
    table using fixed search/tie-break order. Raises
    :class:`MolterGenerationError` on invalid input. Results are cached."""
    if players_per_team % 2 != 0:
        raise MolterGenerationError(
            f'players_per_team must be even (got {players_per_team}).'
        )
    if team_count < 3:
        raise MolterGenerationError(
            f'Molter needs at least 3 teams (got {team_count}).'
        )
    rounds = default_molter_rounds(team_count) if rounds is None else rounds
    if not 1 <= rounds <= team_count - 1:
        raise MolterGenerationError(
            f'rounds must be between 1 and team_count-1 '
            f'({team_count - 1}); got {rounds}.'
        )

    # Layered construction for every shape: each layer of N−1 boards realises a
    # full K_N (one-odd factors for odd N, a 1-factorisation for even N), giving
    # per-round I1 when N−1 divides P; a final partial layer otherwise keeps
    # every player on a distinct opposing team each round, best-effort spread.
    if team_count % 2 == 1:
        regular_matches = _complete_i1_matches(team_count, players_per_team, rounds)
        regular = _colour_complete_i1_matches(regular_matches, team_count)
        emitted_rounds = tuple(_emit(rnd) for rnd in regular)
    else:
        regular_matches = _complete_i1_even_matches(
            team_count, players_per_team, rounds
        )
        regular = _colour_complete_i1_even_matches(
            regular_matches, team_count, players_per_team
        )
        emitted_rounds = tuple(_emit_even(rnd, team_count) for rnd in regular)

    table = MolterTable(
        team_count=team_count,
        players_per_team=players_per_team,
        rounds=emitted_rounds,
    )
    if _VERIFY_GENERATED_TABLES:
        report = verify_molter_table(table)
        if not report.ok:
            raise MolterGenerationError(
                f'Generated table for {team_count}×{players_per_team} over '
                f'{rounds} rounds failed verification: {report.errors[0]}'
            )
    return table


# --------------------------------------------------------------------------
# Verification
# --------------------------------------------------------------------------


def _check_rounds(
    rounds: tuple[tuple['Pairing', ...], ...],
    team_count: int,
    players_per_team: int,
    label: str,
    report: Report,
    is_compromise: bool = False,
) -> None:
    err = report.errors.append
    note = report.notes.append
    letters = tuple(chr(ord('A') + i) for i in range(team_count))
    team_by_letter = {letter: index for index, letter in enumerate(letters)}
    expected_boards = team_count * players_per_team // 2

    # The verifier may scan tens of thousands of generated boards in tests and
    # diagnostics. Keep this hot path flat-array and bitmask based: a more
    # idiomatic Counter/list-heavy version made large verification measurably slow.
    seat_count = team_count * players_per_team
    games = [0] * seat_count
    white_count = [0] * seat_count
    prev_colour = [-1] * seat_count
    prev_prev_colour = [-1] * seat_count
    opp_mask = [0] * seat_count
    repeated_opp: set[int] = set()
    opp_team_counts = (
        [[0] * team_count for _seat in range(seat_count)] if is_compromise else []
    )
    seen_opp_seats: set[tuple[int, int]] = set()
    repeated_opp_seats: set[tuple[int, int]] = set()
    seen_stamp = [0] * seat_count
    team_white = [0] * team_count
    team_black = [0] * team_count
    up = [0] * team_count
    down = [0] * team_count
    seat_down = [0] * seat_count
    seat_up = [0] * seat_count
    pair_count = [[0] * team_count for _ in range(team_count)]
    round_pairs = (len(rounds) + 1) // 2
    rp_down = [[0] * team_count for _ in range(round_pairs)]
    rp_up = [[0] * team_count for _ in range(round_pairs)]
    i5_violated = False
    spread_note: tuple[int, str, dict[str, int]] | None = None
    relaxed_colour_boundary = False
    n_rounds = len(rounds)

    def seat_name(seat: int) -> str:
        return f'{letters[seat // players_per_team]}{seat % players_per_team + 1}'

    for r_zero, rnd in enumerate(rounds):
        r_index = r_zero + 1
        if len(rnd) != expected_boards:
            err(
                f'{label} round {r_index}: {len(rnd)} boards, '
                f'expected {expected_boards} (= {team_count} × {players_per_team}/2).'
            )
        opp_this = [[0] * team_count for _ in range(team_count)]
        floater_levels = [0] * (players_per_team + 1)
        round_pair = r_zero // 2
        for p in rnd:
            white_team = team_by_letter.get(p.white_team)
            black_team = team_by_letter.get(p.black_team)
            if white_team is None:
                err(f'{label} round {r_index}: unknown team letter {p.white_team!r}.')
            if black_team is None:
                err(f'{label} round {r_index}: unknown team letter {p.black_team!r}.')
            white_index_ok = 1 <= p.white_index <= players_per_team
            black_index_ok = 1 <= p.black_index <= players_per_team
            if not white_index_ok:
                err(
                    f'{label} round {r_index}: player index {p.white_index} out '
                    f'of range 1..{players_per_team}.'
                )
            if not black_index_ok:
                err(
                    f'{label} round {r_index}: player index {p.black_index} out '
                    f'of range 1..{players_per_team}.'
                )
            if white_team is not None and black_team is not None:
                if white_team == black_team:
                    err(f'{label} round {r_index}: team-mates paired ({p}).')

                team_white[white_team] += 1
                team_black[black_team] += 1
                opp_this[white_team][black_team] += 1
                opp_this[black_team][white_team] += 1
                pair_count[white_team][black_team] += 1
                pair_count[black_team][white_team] += 1

            white_seat = (
                white_team * players_per_team + p.white_index - 1
                if white_team is not None and white_index_ok
                else -1
            )
            black_seat = (
                black_team * players_per_team + p.black_index - 1
                if black_team is not None and black_index_ok
                else -1
            )
            for seat in (white_seat, black_seat):
                if seat < 0:
                    continue
                if seen_stamp[seat] == r_index:
                    err(
                        f'{label} round {r_index}: {seat_name(seat)} appears '
                        f'on more than one board.'
                    )
                seen_stamp[seat] = r_index
                games[seat] += 1

            if white_seat >= 0:
                white_count[white_seat] += 1
                if n_rounds >= 2:
                    prev = prev_colour[white_seat]
                    if prev == 1:
                        name = None
                        if r_zero % 2 == 1:
                            if is_compromise:
                                relaxed_colour_boundary = True
                            else:
                                name = seat_name(white_seat)
                                err(
                                    f'{label}: {name} repeats colour from round '
                                    f'{r_zero} to {r_zero + 1} — only an even→odd '
                                    f'boundary may repeat.'
                                )
                        if prev_prev_colour[white_seat] == prev:
                            if name is None:
                                name = seat_name(white_seat)
                            err(
                                f'{label}: {name} plays the same colour three '
                                f'rounds running (rounds {r_zero - 1}–'
                                f'{r_zero + 1}).'
                            )
                    prev_prev_colour[white_seat] = prev
                prev_colour[white_seat] = 1
                if black_team is not None:
                    mask = 1 << black_team
                    if opp_mask[white_seat] & mask:
                        repeated_opp.add(white_seat)
                    opp_mask[white_seat] |= mask
                    if is_compromise:
                        opp_team_counts[white_seat][black_team] += 1
            if black_seat >= 0:
                if n_rounds >= 2:
                    prev = prev_colour[black_seat]
                    if prev == 0:
                        name = None
                        if r_zero % 2 == 1:
                            if is_compromise:
                                relaxed_colour_boundary = True
                            else:
                                name = seat_name(black_seat)
                                err(
                                    f'{label}: {name} repeats colour from round '
                                    f'{r_zero} to {r_zero + 1} — only an even→odd '
                                    f'boundary may repeat.'
                                )
                        if prev_prev_colour[black_seat] == prev:
                            if name is None:
                                name = seat_name(black_seat)
                            err(
                                f'{label}: {name} plays the same colour three '
                                f'rounds running (rounds {r_zero - 1}–'
                                f'{r_zero + 1}).'
                            )
                    prev_prev_colour[black_seat] = prev
                prev_colour[black_seat] = 0
                if white_team is not None:
                    mask = 1 << white_team
                    if opp_mask[black_seat] & mask:
                        repeated_opp.add(black_seat)
                    opp_mask[black_seat] |= mask
                    if is_compromise:
                        opp_team_counts[black_seat][white_team] += 1
            if is_compromise and white_seat >= 0 and black_seat >= 0:
                exact_pair = (
                    (white_seat, black_seat)
                    if white_seat < black_seat
                    else (black_seat, white_seat)
                )
                if exact_pair in seen_opp_seats:
                    repeated_opp_seats.add(exact_pair)
                seen_opp_seats.add(exact_pair)

            if p.white_index < p.black_index:
                if white_team is not None:
                    down[white_team] += 1
                    if white_seat >= 0:
                        seat_down[white_seat] += 1
                    rp_down[round_pair][white_team] += 1
                    if rp_down[round_pair][white_team] > 1:
                        i5_violated = True
                if black_team is not None:
                    up[black_team] += 1
                    if black_seat >= 0:
                        seat_up[black_seat] += 1
                    rp_up[round_pair][black_team] += 1
                    if rp_up[round_pair][black_team] > 1:
                        i5_violated = True
            elif p.white_index > p.black_index:
                if white_team is not None:
                    up[white_team] += 1
                    if white_seat >= 0:
                        seat_up[white_seat] += 1
                    rp_up[round_pair][white_team] += 1
                    if rp_up[round_pair][white_team] > 1:
                        i5_violated = True
                if black_team is not None:
                    down[black_team] += 1
                    if black_seat >= 0:
                        seat_down[black_seat] += 1
                    rp_down[round_pair][black_team] += 1
                    if rp_down[round_pair][black_team] > 1:
                        i5_violated = True

            # S6a/S6b — floater rules (hard).
            if p.white_index != p.black_index:
                lo = min(p.white_index, p.black_index)
                hi = max(p.white_index, p.black_index)
                if team_count % 2 == 0:
                    err(
                        f'{label} round {r_index}: floater {p} on an even team '
                        f'count — none allowed (S6a).'
                    )
                elif not (white_index_ok and black_index_ok):
                    pass
                elif hi - lo != 1 or lo % 2 == 0:
                    err(
                        f'{label} round {r_index}: illegal floater {p} — a '
                        f'descending floater may only join consecutive boards '
                        f'with the odd board descending (S6b).'
                    )
                else:
                    floater_levels[lo] += 1

        for level, count in enumerate(floater_levels):
            if count > 1:
                err(
                    f'{label} round {r_index}: {count} descending floaters at '
                    f'board {level} — at most one is allowed per round (S6b).'
                )

        for team, counts in enumerate(opp_this):
            spread_values = [count for count in counts if count]
            if team_count > 2 and len(spread_values) == 1 and spread_values[0] > 1:
                err(
                    f'{label} round {r_index}: team {letters[team]} faces only '
                    f'one other team.'
                )
            elif (
                spread_values
                and max(spread_values) - min(spread_values) > 1
                and spread_note is None
            ):
                spread_note = (
                    r_index,
                    letters[team],
                    {letters[opp]: count for opp, count in enumerate(counts) if count},
                )

    if games and max(games) != min(games):
        err(f'{label}: players do not all play the same number of games.')
    if repeated_opp and is_compromise:
        for seat, counts in enumerate(opp_team_counts):
            values = [
                count
                for team, count in enumerate(counts)
                if team != seat // players_per_team
            ]
            if values and max(values) - min(values) > 1:
                err(
                    f'{label}: {seat_name(seat)} repeats opponent teams unevenly '
                    f'({values}) in a compromise table.'
                )
        if repeated_opp_seats:
            first, second = min(repeated_opp_seats)
            err(
                f'{label}: {seat_name(first)} and {seat_name(second)} meet more '
                f'than once in a compromise table.'
            )
        note(
            f'{label}: opponent-team repeats are unavoidable for this round '
            f'count; the table is checked as a best compromise.'
        )
    else:
        for seat in sorted(repeated_opp):
            err(
                f'{label}: {seat_name(seat)} meets the same team twice — rounds '
                f'must be < team count.'
            )

    # Per-player colour rules (read off the official tables). Checked over a
    # multi-round set only — a single round has nothing to alternate.
    if n_rounds >= 2:
        for seat, whites in enumerate(white_count):
            if abs(whites - (n_rounds - whites)) > n_rounds % 2:
                err(
                    f'{label}: {seat_name(seat)} colour imbalance '
                    f'({whites} white / {n_rounds - whites} black).'
                )
        # S6c — over the regular rounds no player is a descending floater
        # more than once (nor an ascending floater more than once).
        for seat, count in enumerate(seat_down):
            if count > 1:
                err(
                    f'{label}: {seat_name(seat)} is a descending floater '
                    f'{count} times — at most once is allowed (S6c).'
                )
        for seat, count in enumerate(seat_up):
            if count > 1:
                err(
                    f'{label}: {seat_name(seat)} is an ascending floater '
                    f'{count} times — at most once is allowed (S6c).'
                )
    for team, letter in enumerate(letters):
        if team_white[team] != team_black[team]:
            err(
                f'{label}: team {letter} colour imbalance '
                f'(white {team_white[team]} / black {team_black[team]}).'
            )
    if relaxed_colour_boundary:
        note(
            f'{label}: colour repeats occur outside the usual even→odd boundary; '
            f'the compromise table still forbids three identical colours in a row.'
        )

    for team, counts in enumerate(pair_count):
        non_zero_counts = [count for count in counts if count]
        if len(set(non_zero_counts)) > 1:
            note(
                f'{label}: team {letters[team]} faces an uneven number of members per '
                f'team — only the complete tables equalise this (I1).'
            )
            break
    # I3 (equal ascending/descending floaters per team) is a whole-schedule
    # ideal — meaningless for a single round (the autonomous one), where a team
    # floats at most one way. Only assess it over a multi-round set.
    unbalanced = [
        letter for team, letter in enumerate(letters) if up[team] != down[team]
    ]
    if unbalanced and n_rounds >= 2:
        note(
            f'{label}: floaters not balanced for team(s) '
            f'{", ".join(unbalanced)} — each team should have as many ascending as '
            f'descending floaters; only the complete tables equalise this (I3).'
        )
    down_counts = list(down)
    if down_counts and max(down_counts) - min(down_counts) > 1:
        note(
            f'{label}: descending floaters unequal across teams '
            f'(range {min(down_counts)}–{max(down_counts)}) — descending '
            f'floaters should be as equal as possible (spread at most 1) (I2).'
        )
    # I5 — a single-layer table (P ≤ N − 1) should float each team at most once
    # up and once down per round-pair. (For more than one layer this is
    # arithmetically impossible, so it is only checked for a single layer.)
    if team_count % 2 == 1 and 0 < players_per_team <= team_count - 1:
        if i5_violated:
            note(
                f'{label}: a team floats more than once within a round-pair — a '
                f'single-layer table should float each team at most once up and '
                f'once down per round-pair (I5).'
            )
    if spread_note is not None:
        r_index, team_name, spread = spread_note
        note(
            f'{label} round {r_index}: team {team_name} opponent spread {spread} '
            f'is uneven — a team should be spread evenly across opponents each '
            f'round; only the smaller tables equalise this (I4).'
        )


def verify_molter_table(table: MolterTable) -> Report:
    """Verify ``table`` against the Molter principles."""
    report = Report()
    if table.players_per_team % 2 != 0:
        report.errors.append(
            f'players-per-team must be even (got {table.players_per_team}).'
        )
    if table.regular_round_count >= table.team_count and not table.is_compromise:
        report.errors.append(
            f'{table.regular_round_count} regular rounds with only '
            f'{table.team_count} teams — a player would meet a team twice '
            f'(principle 2 requires rounds < teams).'
        )
    _check_rounds(
        table.rounds,
        table.team_count,
        table.players_per_team,
        'regular',
        report,
        table.is_compromise,
    )
    return report


# --------------------------------------------------------------------------
# Display / CSV / CLI
# --------------------------------------------------------------------------


def format_table(table: MolterTable) -> str:
    boards = table.team_count * table.players_per_team // 2
    names = [f'Round {i}' for i in range(1, table.regular_round_count + 1)]
    all_rounds = list(table.rounds)
    width = 14
    header = 'Board | ' + ' | '.join(n.ljust(width) for n in names)
    lines = [
        f'{table.team_count} teams x {table.players_per_team} players '
        f'- {boards} boards - {table.regular_round_count} regular round(s) '
        f'(first named = White)',
        header,
        '-' * len(header),
    ]
    for b in range(boards):
        cells = [str(rnd[b]).ljust(width) for rnd in all_rounds]
        lines.append(f'{b + 1:>4} | ' + ' | '.join(cells))
    return '\n'.join(lines)


def write_csv(tables: list[MolterTable], path: str) -> None:
    with open(path, 'w', newline='', encoding='utf-8') as fh:
        w = csv.writer(fh)
        for table in tables:
            boards = table.team_count * table.players_per_team // 2
            names = [f'Round {i}' for i in range(1, table.regular_round_count + 1)]
            all_rounds = list(table.rounds)
            w.writerow([f'{table.team_count} teams x {table.players_per_team} players'])
            w.writerow(['Board'] + names)
            for b in range(boards):
                w.writerow([b + 1] + [str(rnd[b]) for rnd in all_rounds])
            w.writerow([])


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description='Standalone Molter table generator and verifier.'
    )
    parser.add_argument('teams', type=int, nargs='?', help='number of teams')
    parser.add_argument('players', type=int, nargs='?', help='players per team (even)')
    parser.add_argument(
        '--rounds',
        type=int,
        default=None,
        help='number of regular rounds (default by convention)',
    )
    parser.add_argument(
        '--grid',
        action='store_true',
        help='generate the 3-13 teams x 4,6,8,10,12 players sample grid',
    )
    parser.add_argument(
        '--csv', metavar='FILE', default=None, help='write the result as CSV'
    )
    args = parser.parse_args(argv)

    tables: list[MolterTable] = []
    if args.grid:
        for n in range(3, 14):
            for p in (4, 6, 8, 10, 12):
                try:
                    tables.append(generate_molter_table(n, p))
                except MolterGenerationError as exc:
                    print(f'  {n}×{p} : {exc}', file=sys.stderr)
    else:
        if args.teams is None or args.players is None:
            parser.error('provide <teams> <players>, or use --grid.')
        try:
            tables.append(
                generate_molter_table(args.teams, args.players, rounds=args.rounds)
            )
        except MolterGenerationError as exc:
            print(f'Error: {exc}', file=sys.stderr)
            return 1

    for table in tables:
        report = verify_molter_table(table)
        print(format_table(table))
        print('Verification:', 'OK' if report.ok else 'FAILED')
        for e in report.errors:
            print('  ERROR:', e)
        for note in report.notes:
            print('  (ideal):', note)
        print()

    if args.csv:
        write_csv(tables, args.csv)
        print(f'CSV written: {args.csv}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
