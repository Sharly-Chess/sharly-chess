"""Deterministic expansion helpers for packed Molter recipes.

This module deliberately has no public table generator. It only expands the
compact schedule primitives stored in ``molter_recipes.mrec`` into uncoloured
matches and renders coloured rounds as fixed-table rows.
"""

from __future__ import annotations

from functools import lru_cache

from data.pairings.fixed_table import TablePairing

_Player = tuple[int, int]
_Match = tuple[_Player, _Player]
_Round = list[_Match]
_TEAM_LETTERS = tuple(chr(ord('A') + index) for index in range(26))


@lru_cache(maxsize=None)
def _letter(team_index: int) -> str:
    if team_index < len(_TEAM_LETTERS):
        return _TEAM_LETTERS[team_index]
    return chr(ord('A') + team_index)


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

    def choice[T](self, values: list[T]) -> T:
        return values[self.randrange(len(values))]

    def shuffle[T](self, values: list[T]) -> None:
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
    """Edges each 2-factor must contain for the affine floater grid."""
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


@lru_cache(maxsize=None)
def _one_factorization(team_count: int) -> tuple[tuple[tuple[int, int], ...], ...]:
    pivot = team_count - 1
    ring = team_count - 1
    factors: list[tuple[tuple[int, int], ...]] = []
    for b in range(ring):
        matching: list[tuple[int, int]] = [_team_edge(pivot, b)]
        for i in range(1, team_count // 2):
            matching.append(_team_edge((b + i) % ring, (b - i) % ring))
        factors.append(tuple(sorted(matching)))
    return tuple(factors)


def _even_matches_from_factor_rows(
    team_count: int, factor_rows: tuple[tuple[int, ...], ...]
) -> list[list[_Match]]:
    factors = _one_factorization(team_count)
    out: list[list[_Match]] = []
    for factor_row in factor_rows:
        rnd: list[_Match] = []
        for slot, factor_index in enumerate(factor_row):
            for i, j in factors[factor_index]:
                rnd.append(((i, slot), (j, slot)))
        out.append(rnd)
    return out


def _emit(rnd: _Round) -> tuple[TablePairing, ...]:
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
        TablePairing(
            _letter(white[0]),
            white[1] + 1,
            _letter(black[0]),
            black[1] + 1,
        )
        for white, black in ordered
    )
