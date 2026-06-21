"""Generator for Molter pairing tables.

Produces a :class:`FixedPairingTable` for a given ``(team_count,
players_per_team, rounds)`` satisfying the Molter invariants (see
:mod:`data.pairings.molter_verifier`): floaters (S6a/S6b/S6c),
and colours (each player colour-balanced over the regular rounds, never the
same colour three rounds running, a colour repeating only across an
even→odd round boundary).

**Layered construction (every shape).** The board list is built in layers of
``N − 1`` boards, each realising one full ``K_N`` — odd ``N`` by repaired
one-odd 2-factors (with a legal descending floater), even ``N`` by a
1-factorisation (no floaters). When ``N − 1`` divides ``P`` the ``k`` full layers
give I1 on every regular round (each pair of teams appears exactly ``k`` times).
Otherwise a final partial layer covers the remaining boards: every player still
meets a distinct opposing team each round (S4), with legal floaters for odd
``N``. Odd partial blocks and even partial board slots both use prefix-balanced
factor plans, so a prefix of ``r`` rounds gives each team
``min(N − 1, P × r)`` distinct opposing teams. That protects the main I1 intent
for truncated schedules; I2/I5 become verifier notes when they conflict with
that spread.

**Odd floaters use one-odd factors.** For supported odd sizes, full layers use
the affine dropped-edge construction. Partial layers use the same one-odd
factors with deterministic spread offsets and stable dropped edges per
block/factor cell. ``N = 3`` and ``N = 5`` use fixed small one-odd factors;
``N = 5`` has I2 spread 2 because S6c and perfect I2 conflict. Unsupported odd
sizes fail explicitly instead of falling back to a slower search.

**Colours need no search.** A colour repeat is only allowed on an even→odd
round boundary, so odd→even boundaries *must* alternate. Round-pairs are coloured
together by a bipartition of the two-round player graph, balancing each player
(hence each team); for an odd round count the lone final round is coloured
Eulerian so it is per-team balanced on its own. No-tripling and the
even→odd-only repeat rule then hold by construction.

**Deterministic and language-portable.** There is no external solver. The
complete odd-layer path uses fixed recolouring and switching passes; partial odd
layers are arithmetic once the one-odd factors exist. So
``(team_count, players_per_team, rounds)`` defines a single canonical table a
faithful re-implementation in any language can reproduce exactly.
"""

from __future__ import annotations

from functools import lru_cache
from itertools import product

from data.pairings.fixed_table import FixedPairingTable, TablePairing
from data.pairings.molter_verifier import verify_molter_table

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


def _pair_flip_colour(
    first_round: list[_Match], second_round: list[_Match]
) -> tuple[_Round, _Round]:
    """Colour a two-round block so every player flips colour.

    The union of the two uncoloured rounds is a graph on players. If it is
    bipartite, orient round 1 by one side of the bipartition and round 2 by the
    other; each player then gets one White and one Black. This supports partial
    odd layers whose second round is not a mirror of the first.
    """
    adjacent: dict[_Player, list[_Player]] = {}
    for rnd in (first_round, second_round):
        for first, second in rnd:
            adjacent.setdefault(first, []).append(second)
            adjacent.setdefault(second, []).append(first)

    colour: dict[_Player, int] = {}
    for start in sorted(adjacent):
        if start in colour:
            continue
        colour[start] = 0
        stack = [start]
        while stack:
            player = stack.pop()
            for other in adjacent[player]:
                other_colour = 1 - colour[player]
                if other in colour:
                    if colour[other] != other_colour:
                        raise MolterGenerationError(
                            'Could not colour odd Molter round-pair.'
                        )
                else:
                    colour[other] = other_colour
                    stack.append(other)

    first_coloured = [
        (first, second) if colour[first] == 1 else (second, first)
        for first, second in first_round
    ]
    second_coloured = [
        (first, second) if colour[first] == 0 else (second, first)
        for first, second in second_round
    ]
    return first_coloured, second_coloured


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


def _one_odd_spread_partial_blocks(
    team_count: int,
    rounds: int,
    block_offset: int,
    block_count: int,
    factors: tuple[tuple[tuple[int, int], ...], ...],
) -> list[list[_Match]]:
    """Partial odd layer optimized for early opponent spread.

    Each two-board block cycles through every one-odd factor, but the blocks are
    offset across the factor list. In `N=9, P=4`, for example, the two blocks use
    factors `{0, 2}` in round 1 and `{1, 3}` in round 2, so every team has met
    all eight opposing teams after two rounds. When a block later reuses a
    factor, it keeps the same dropped edge and flips the materialization phase;
    that gives the two board-slot players the other incident team edge.
    """
    half = (team_count - 1) // 2
    offsets = _one_odd_partial_offsets(team_count, block_count)
    seen: dict[tuple[int, int], int] = {}
    dropped_by_cell: dict[tuple[int, int], tuple[int, int]] = {}
    out: list[list[_Match]] = []

    def fallback_dropped(factor: tuple[tuple[int, int], ...]) -> tuple[int, int]:
        incident = sorted(edge for edge in factor if 0 in edge)
        edge = incident[0]
        return edge if edge[0] == 0 else (edge[1], edge[0])

    for r_index in range(rounds):
        rnd: list[_Match] = []
        for block, offset in enumerate(offsets):
            factor_index = (r_index + offset) % half
            key = (block, factor_index)
            if key not in dropped_by_cell:
                first_round = (factor_index - offset) % half
                dropped = _affine_floater_edge(team_count, first_round, offset)
                if dropped not in factors[factor_index]:
                    dropped = fallback_dropped(factors[factor_index])
                dropped_by_cell[key] = dropped
            phase = seen.get(key, 0)
            seen[key] = phase + 1
            odd_slot = 2 * (block_offset + block)
            even_slot = odd_slot + 1
            rnd.extend(
                _one_odd_cell_matches(
                    team_count,
                    factors[factor_index],
                    dropped_by_cell[key],
                    odd_slot,
                    even_slot,
                    phase % 2 == 1,
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
    Full layers use its affine dropped edges directly. Partial layers rotate
    spread offsets by round to maximize distinct opponent teams in every prefix.
    Unsupported odd sizes fail explicitly instead of running a slower alternate
    search."""
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
            layer_matches = _one_odd_spread_partial_blocks(
                team_count,
                rounds,
                block_offset,
                count,
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
    """Colour odd-team rounds with the Molter parity scheme.

    Round-pairs are coloured together so every player flips colour from the odd
    round to the even round. A lone final odd round is coloured Eulerian per
    layer-sized chunk, giving exact team colour balance on that round.
    """
    layer_size = team_count * (team_count - 1) // 2
    rounds: list[_Round] = []
    r_index = 0
    while r_index < len(matches):
        if r_index + 1 < len(matches):
            first, second = _pair_flip_colour(matches[r_index], matches[r_index + 1])
            rounds.append(first)
            rounds.append(second)
            r_index += 2
        else:
            rnd: _Round = []
            match = matches[r_index]
            for start in range(0, len(match), layer_size):
                rnd.extend(_eulerian_colour(match[start : start + layer_size]))
            rounds.append(rnd)
            r_index += 1
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


@lru_cache(maxsize=None)
def _even_partial_factor_plan(
    factor_count: int, slot_count: int, rounds: int
) -> tuple[tuple[int, ...], ...]:
    """Prefix-balanced factor rows for the leftover even-team boards.

    The row sets are the first ``slot_count`` entries of a cyclic factor stream,
    so every round prefix uses each factor either floor or ceil times. Those
    factor occurrences are then edge-coloured into physical slots: each row gets
    every slot once, and each factor appears at most once in a slot, so a player
    never repeats an opposing team.
    """
    if slot_count == 0:
        return tuple(() for _round in range(rounds))

    adjacency: list[set[int]] = [
        {
            (round_index * slot_count + offset) % factor_count
            for offset in range(slot_count)
        }
        for round_index in range(rounds)
    ]
    degrees = [0] * factor_count
    for row_factors in adjacency:
        for factor in row_factors:
            degrees[factor] += 1

    deficits = [slot_count - degree for degree in degrees]
    for _dummy in range(factor_count - rounds):
        dummy_row: set[int] = set()
        while len(dummy_row) < slot_count:
            candidates = [
                factor
                for factor in range(factor_count)
                if deficits[factor] > 0 and factor not in dummy_row
            ]
            if not candidates:
                raise MolterGenerationError('Could not regularize even factor plan.')
            factor = max(candidates, key=lambda item: (deficits[item], -item))
            dummy_row.add(factor)
            deficits[factor] -= 1
        adjacency.append(dummy_row)
    if any(deficits):
        raise MolterGenerationError('Incomplete even factor-plan regularization.')

    rows = [[-1] * slot_count for _round in range(rounds)]
    for slot in range(slot_count):
        factor_to_row: dict[int, int] = {}

        def visit(row: int, seen: set[int]) -> bool:
            for factor in sorted(adjacency[row]):
                if factor in seen:
                    continue
                seen.add(factor)
                previous = factor_to_row.get(factor)
                if previous is None or visit(previous, seen):
                    factor_to_row[factor] = row
                    return True
            return False

        for row in range(factor_count):
            if not visit(row, set()):
                raise MolterGenerationError('Could not edge-colour even factor plan.')

        row_to_factor = [-1] * factor_count
        for factor, matched_row in factor_to_row.items():
            row_to_factor[matched_row] = factor
        for matched_row, factor in enumerate(row_to_factor):
            if factor < 0:
                raise MolterGenerationError('Incomplete even factor-plan matching.')
            adjacency[matched_row].remove(factor)
            if matched_row < rounds:
                rows[matched_row][slot] = factor

    return tuple(tuple(row) for row in rows)


def _complete_i1_even_matches(
    team_count: int, players_per_team: int, rounds: int
) -> list[list[_Match]]:
    """Construct even-team rounds for any even ``P``.

    Full layers use every 1-factor once per round, giving exact per-round I1.
    A final partial layer uses a prefix-balanced factor plan, so truncated even
    tables spread opponents as quickly as arithmetic permits while each fixed
    slot still meets a distinct team every round (S4).
    """
    factors = _one_factorization(team_count)
    factor_count = team_count - 1
    full_layers, partial_slots = divmod(players_per_team, factor_count)
    partial_plan = _even_partial_factor_plan(factor_count, partial_slots, rounds)
    out: list[list[_Match]] = []
    for r_index in range(rounds):
        rnd: list[_Match] = []
        for layer in range(full_layers):
            slot_offset = layer * factor_count
            for slot in range(factor_count):
                for i, j in factors[(slot + r_index) % factor_count]:
                    rnd.append(((i, slot_offset + slot), (j, slot_offset + slot)))
        slot_offset = full_layers * factor_count
        for slot, factor_index in enumerate(partial_plan[r_index]):
            for i, j in factors[factor_index]:
                rnd.append(((i, slot_offset + slot), (j, slot_offset + slot)))
        out.append(rnd)
    return out


def _colour_complete_i1_even_matches(
    matches: list[list[_Match]], team_count: int, players_per_team: int
) -> list[_Round]:
    """Colour even-team rounds with the same round-pair flip used by odd teams."""
    rounds: list[_Round] = []
    r_index = 0
    while r_index < len(matches):
        if r_index + 1 < len(matches):
            first, second = _pair_flip_colour(matches[r_index], matches[r_index + 1])
            rounds.append(first)
            rounds.append(second)
            r_index += 2
        else:
            rounds.append(_eulerian_colour(matches[r_index]))
            r_index += 1
    return rounds


# ---------- rendering ----------


def _emit(rnd: _Round) -> tuple[TablePairing, ...]:
    """Render a coloured round as `TablePairing`s, ordered by board number
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
        TablePairing(
            _letter(white[0]),
            white[1] + 1,
            _letter(black[0]),
            black[1] + 1,
        )
        for white, black in ordered
    )


def _emit_even(rnd: _Round, team_count: int) -> tuple[TablePairing, ...]:
    """Render an even-team round.

    Even tables have no floaters, so every game in a slot chunk has the same
    board number. Sorting each chunk by oriented teams is equivalent to the
    generic board sort and avoids repeatedly comparing board numbers.
    """
    chunk_size = team_count // 2
    letters = tuple(_letter(team) for team in range(team_count))
    out: list[TablePairing] = []
    for start in range(0, len(rnd), chunk_size):
        chunk = sorted(
            rnd[start : start + chunk_size],
            key=lambda board: (board[0][0], board[1][0]),
        )
        for white, black in chunk:
            out.append(
                TablePairing(
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
) -> FixedPairingTable:
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

    table = FixedPairingTable(
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
