"""Generator for Molter pairing tables.

Produces a :class:`FixedPairingTable` for a given ``(team_count,
players_per_team, rounds)`` satisfying the Molter invariants (see
:mod:`data.pairings.molter_verifier`): floaters (S6a/S6b/S6c),
and colours (bounded cumulative team colour drift plus individual C1/C2/C3).

**Layered construction (every shape).** The board list is built in layers of
``N − 1`` boards, each realising one full ``K_N`` — odd ``N`` by repaired
one-odd 2-factors (with a legal descending floater), even ``N`` by a
1-factorisation (no floaters). When ``N − 1`` divides ``P`` the ``k`` full layers
give I1 on every regular round (each pair of teams appears exactly ``k`` times).
Otherwise a final partial layer covers the remaining boards: every player still
meets a distinct opposing team each round (S4), with legal floaters for odd
``N``. Odd partial blocks use prefix-balanced factor plans. Even partial rows
first keep pair-compatible colour-safe rows, then for short horizons try bounded
balanced rows with I1 <= 1 before accepting only candidates that still satisfy
the hard colour rules; fully prefix-balanced rows can still win when colourable.
Odd partial directed floater-edge choices then minimize I3 as an L1 score before
I2/I5 tie-breakers.

**Odd floaters use one-odd factors.** For supported odd sizes, full layers use
the affine dropped-edge construction. Partial layers use the same one-odd
factors with deterministic spread offsets and stable dropped edges per
block/factor cell. ``N = 3`` and ``N = 5`` use fixed small one-odd factors;
``N = 5`` has I2 spread 2 because S6c and perfect I2 conflict. Unsupported odd
sizes fail explicitly instead of falling back to a slower search.

**Colours prefer exact S5 but enforce bounded S5.** Round-pairs are first coloured together by a
bipartition of the two-round player graph. When that also gives every team
``P/2`` Whites in each round, it is kept because it gives excellent individual
colour sequences. Some partial schedules cannot satisfy both that round-pair
flip and exact per-round S5; those rounds are coloured by a min-cost orientation
of each team multigraph or a bounded two-round drift colourer, then improved by
team-balance-preserving directed cycle reversals to reduce individual imbalance
and triples. The verifier enforces the bounded cumulative team drift and reports
missed exact per-round S5 as a quality note.

**Deterministic and language-portable.** There is no external solver. The
complete odd-layer path uses fixed recolouring and switching passes; partial odd
layers are arithmetic once the one-odd factors exist. So
``(team_count, players_per_team, rounds)`` defines a single canonical table a
faithful re-implementation in any language can reproduce exactly.
"""

from __future__ import annotations

from functools import lru_cache
from heapq import heappop, heappush
from itertools import combinations, permutations, product

from data.pairings.fixed_table import FixedPairingTable, TablePairing
from data.pairings.molter_verifier import verify_molter_table

_Player = tuple[int, int]  # (team_index 0-based, slot 0-based; board = slot + 1)
_Match = tuple[_Player, _Player]  # an uncoloured board (unordered pair)
_Board = tuple[_Player, _Player]  # a coloured board (white, black)
_Round = list[_Board]
_PackedCounts = tuple[int, tuple[tuple[int, int], ...]]
_PairFlipData = tuple[
    dict[_Player, int],
    dict[_Player, int],
    list[tuple[list[int], list[int]]],
]
_OneOddPlanCell = tuple[int, tuple[int, int]]
_OneOddPlan = tuple[tuple[_OneOddPlanCell, ...], ...]
_VERIFY_GENERATED_TABLES = False
_TEAM_LETTERS = tuple(chr(ord('A') + index) for index in range(26))
_COLOUR_IMBALANCE_COST = 10_000
_COLOUR_TRIPLE_COST = 1_000
_COLOUR_REPEAT_COST = 1
_RELAXED_S5_STATE_LIMIT = 1_000


class MolterGenerationError(Exception):
    """Raised when no valid Molter table could be generated for the
    requested shape."""


@lru_cache(maxsize=None)
def _letter(team_index: int) -> str:
    if team_index < len(_TEAM_LETTERS):
        return _TEAM_LETTERS[team_index]
    return chr(ord('A') + team_index)


# ---------- colouring a matched round (deterministic, no search) ----------


def _eulerian_colour(boards: list[_Match], phase: int = 0) -> _Round:
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
    cycle_index = 0
    while unused:
        start = min(t for t, es in incident.items() if es)
        cur = start
        cycle_edges: list[tuple[int, int, int]] = []
        while True:
            e = min(incident[cur])
            ta, tb = edge_teams[e]
            nxt = tb if ta == cur else ta
            incident[cur].discard(e)
            incident[nxt].discard(e)
            unused.discard(e)
            cycle_edges.append((e, cur, nxt))
            cur = nxt
            if cur == start:
                break
        reverse = (phase + cycle_index) % 2 == 1
        for e, current, next_team in cycle_edges:
            white_team_of[e] = next_team if reverse else current
        cycle_index += 1
    return [
        (a, b) if a[0] == white_team_of[e] else (b, a)
        for e, (a, b) in enumerate(boards)
    ]


def _pair_flip_data(
    first_round: list[_Match],
    second_round: list[_Match],
    team_count: int,
    _players_per_team: int,
) -> _PairFlipData | None:
    """Return bipartite component choices for a two-round colour flip.

    The union of the two uncoloured rounds is a graph on players. If it is
    bipartite, each player can get one White and one Black across the pair.
    Each connected component can still be flipped independently; callers choose
    the component flips according to their team-colour objective.
    """
    adjacent: dict[_Player, list[_Player]] = {}
    for rnd in (first_round, second_round):
        for first, second in rnd:
            adjacent.setdefault(first, []).append(second)
            adjacent.setdefault(second, []).append(first)

    colour: dict[_Player, int] = {}
    components: list[list[_Player]] = []
    for start in sorted(adjacent):
        if start in colour:
            continue
        colour[start] = 0
        stack = [start]
        component: list[_Player] = []
        while stack:
            player = stack.pop()
            component.append(player)
            for other in adjacent[player]:
                other_colour = 1 - colour[player]
                if other in colour:
                    if colour[other] != other_colour:
                        return None
                else:
                    colour[other] = other_colour
                    stack.append(other)
        components.append(component)

    choices: list[tuple[list[int], list[int]]] = []
    component_index_by_player: dict[_Player, int] = {}
    for component_index, component in enumerate(components):
        component_set = set(component)
        team_players = [0] * team_count
        first_white = [0] * team_count
        for player in component:
            component_index_by_player[player] = component_index
            team_players[player[0]] += 1
        for first, second in first_round:
            if first not in component_set:
                continue
            white = first if colour[first] == 1 else second
            first_white[white[0]] += 1
        choices.append(
            (
                first_white,
                [team_players[team] - first_white[team] for team in range(team_count)],
            )
        )
    return colour, component_index_by_player, choices


def _packed_counts(
    counts: list[int], place_values: list[int]
) -> tuple[int, tuple[tuple[int, int], ...]]:
    sparse = tuple((team, count) for team, count in enumerate(counts) if count != 0)
    return (
        sum(count * place_values[team] for team, count in sparse),
        sparse,
    )


def _emit_pair_flip_rounds(
    first_round: list[_Match],
    second_round: list[_Match],
    colour: dict[_Player, int],
    component_index_by_player: dict[_Player, int],
    flips: list[int],
) -> tuple[_Round, _Round]:
    def effective_colour(player: _Player) -> int:
        return colour[player] ^ flips[component_index_by_player[player]]

    first_coloured = [
        (first, second) if effective_colour(first) == 1 else (second, first)
        for first, second in first_round
    ]
    second_coloured = [
        (first, second) if effective_colour(first) == 0 else (second, first)
        for first, second in second_round
    ]
    return first_coloured, second_coloured


def _pair_flip_colour(
    first_round: list[_Match],
    second_round: list[_Match],
    team_count: int,
    players_per_team: int,
) -> tuple[_Round, _Round] | None:
    """Colour a two-round block so every player flips colour and S5 holds.

    Component flips are chosen exactly to give every team ``P/2`` Whites in
    round 1. Round 2 is then balanced too.
    """
    data = _pair_flip_data(first_round, second_round, team_count, players_per_team)
    if data is None:
        return None
    colour, component_index_by_player, raw_choices = data

    target = players_per_team // 2
    base = target + 1
    place_values = [base**team for team in range(team_count)]
    target_state = sum(target * place_values[team] for team in range(team_count))
    choices = [
        (
            _packed_counts(normal, place_values),
            _packed_counts(flipped, place_values),
        )
        for normal, flipped in raw_choices
    ]

    states: tuple[int, ...] = (0,)
    parents: list[dict[int, tuple[int, int]]] = []
    for normal, flipped in choices:
        next_states: dict[int, tuple[int, int]] = {}
        for state in states:
            for flip, (packed, sparse) in enumerate((normal, flipped)):
                if any(
                    (state // place_values[team]) % base + count > target
                    for team, count in sparse
                ):
                    continue
                next_state = state + packed
                if next_state not in next_states:
                    next_states[next_state] = (state, flip)
        parents.append(next_states)
        states = tuple(next_states)
        if not states:
            return None

    if target_state not in states:
        return None
    flips = [0] * len(choices)
    state = target_state
    for component_index in range(len(choices) - 1, -1, -1):
        previous_state, flip = parents[component_index][state]
        flips[component_index] = flip
        state = previous_state

    return _emit_pair_flip_rounds(
        first_round, second_round, colour, component_index_by_player, flips
    )


def _pair_flip_colour_relaxed_s5(
    first_round: list[_Match],
    second_round: list[_Match],
    team_count: int,
    players_per_team: int,
) -> tuple[_Round, _Round] | None:
    """Colour a pair with per-player colour flips and bounded S5 drift.

    Round 1 may give a team one more or one fewer White than ``P/2``; round 2 is
    the exact compensation, so every team returns to cumulative colour balance
    after two rounds and no cumulative team drift exceeds 2.
    """
    data = _pair_flip_data(first_round, second_round, team_count, players_per_team)
    if data is None:
        return None
    colour, component_index_by_player, choices = data

    target = players_per_team // 2
    low = target - 1
    high = target + 1
    base = players_per_team + 1
    place_values = [base**team for team in range(team_count)]
    best_state: int | None = None
    best_score: tuple[int, int, int] | None = None
    states: tuple[int, ...] = (0,)
    parents: list[dict[int, tuple[int, int]]] = []
    ordered_choices = sorted(
        enumerate(choices),
        key=lambda item: (
            -sum(
                abs(item[1][0][team] - item[1][1][team]) for team in range(team_count)
            ),
            item[0],
        ),
    )
    remaining_min = [[0] * team_count for _index in range(len(ordered_choices) + 1)]
    remaining_max = [[0] * team_count for _index in range(len(ordered_choices) + 1)]
    for index in range(len(ordered_choices) - 1, -1, -1):
        _original_index, (normal, flipped) = ordered_choices[index]
        for team in range(team_count):
            remaining_min[index][team] = remaining_min[index + 1][team] + min(
                normal[team], flipped[team]
            )
            remaining_max[index][team] = remaining_max[index + 1][team] + max(
                normal[team], flipped[team]
            )

    for component_index, (_original_index, (normal, flipped)) in enumerate(
        ordered_choices
    ):
        packed_choices = (
            _packed_counts(normal, place_values),
            _packed_counts(flipped, place_values),
        )
        next_states: dict[int, tuple[int, int]] = {}
        for state in states:
            for flip, (packed, sparse) in enumerate(packed_choices):
                next_state = state + packed
                feasible = True
                for team in range(team_count):
                    count = (next_state // place_values[team]) % base
                    if (
                        count + remaining_min[component_index + 1][team] > high
                        or count + remaining_max[component_index + 1][team] < low
                    ):
                        feasible = False
                        break
                if not feasible:
                    continue
                if next_state not in next_states:
                    next_states[next_state] = (state, flip)
        if len(next_states) > _RELAXED_S5_STATE_LIMIT:

            def state_key(state: int) -> tuple[int, int, int]:
                max_distance = 0
                total_distance = 0
                for team in range(team_count):
                    count = (state // place_values[team]) % base
                    reachable_low = count + remaining_min[component_index + 1][team]
                    reachable_high = count + remaining_max[component_index + 1][team]
                    nearest = min(max(target, reachable_low), reachable_high)
                    distance = abs(nearest - target)
                    max_distance = max(max_distance, distance)
                    total_distance += distance
                return max_distance, total_distance, state

            kept_states = sorted(next_states, key=state_key)[:_RELAXED_S5_STATE_LIMIT]
            next_states = {state: next_states[state] for state in kept_states}
        parents.append(next_states)
        states = tuple(next_states)
        if not states:
            return None

    for state in states:
        counts = [(state // place_values[team]) % base for team in range(team_count)]
        if any(count < low or count > high for count in counts):
            continue
        drifts = [abs(2 * count - players_per_team) for count in counts]
        score = (max(drifts), sum(drifts), sum(1 for drift in drifts if drift))
        if best_score is None or score < best_score:
            best_score = score
            best_state = state
    if best_state is None or best_score is None or best_score[0] > 2:
        return None

    flips = [0] * len(choices)
    state = best_state
    for component_index in range(len(ordered_choices) - 1, -1, -1):
        previous_state, flip = parents[component_index][state]
        original_index = ordered_choices[component_index][0]
        flips[original_index] = flip
        state = previous_state

    return _emit_pair_flip_rounds(
        first_round, second_round, colour, component_index_by_player, flips
    )


class _MinCostFlow:
    def __init__(self, node_count: int) -> None:
        self.graph: list[list[list[int]]] = [[] for _node in range(node_count)]

    def add_edge(self, source: int, target: int, capacity: int, cost: int) -> int:
        forward_index = len(self.graph[source])
        reverse_index = len(self.graph[target])
        self.graph[source].append([target, capacity, cost, reverse_index])
        self.graph[target].append([source, 0, -cost, forward_index])
        return forward_index

    def send(self, source: int, target: int, amount: int) -> None:
        node_count = len(self.graph)
        potential = [0] * node_count
        sent = 0
        while sent < amount:
            distance = [10**18] * node_count
            previous_node = [-1] * node_count
            previous_edge = [-1] * node_count
            distance[source] = 0
            queue: list[tuple[int, int]] = [(0, source)]
            while queue:
                current_distance, node = heappop(queue)
                if current_distance != distance[node]:
                    continue
                for edge_index, edge in enumerate(self.graph[node]):
                    if edge[1] <= 0:
                        continue
                    next_node = edge[0]
                    next_distance = (
                        current_distance
                        + edge[2]
                        + potential[node]
                        - potential[next_node]
                    )
                    if next_distance < distance[next_node]:
                        distance[next_node] = next_distance
                        previous_node[next_node] = node
                        previous_edge[next_node] = edge_index
                        heappush(queue, (next_distance, next_node))
            if distance[target] == 10**18:
                raise MolterGenerationError('Could not colour Molter round.')
            for node, node_distance in enumerate(distance):
                if node_distance < 10**18:
                    potential[node] += node_distance
            path_amount = amount - sent
            node = target
            while node != source:
                edge = self.graph[previous_node[node]][previous_edge[node]]
                path_amount = min(path_amount, edge[1])
                node = previous_node[node]
            node = target
            while node != source:
                edge = self.graph[previous_node[node]][previous_edge[node]]
                edge[1] -= path_amount
                self.graph[node][edge[3]][1] += path_amount
                node = previous_node[node]
            sent += path_amount


def _seat(player: _Player, players_per_team: int) -> int:
    return player[0] * players_per_team + player[1]


def _colour_prefix_limit(round_index: int, total_rounds: int) -> int:
    return 1 if round_index == total_rounds - 1 else 2


@lru_cache(maxsize=200_000)
def _player_colour_penalty_tuple(sequence: tuple[int, ...]) -> int:
    rounds = len(sequence)
    whites = sum(sequence)
    penalty = (
        max(0, abs(whites - (rounds - whites)) - rounds % 2) * _COLOUR_IMBALANCE_COST
    )
    for index in range(rounds - 2):
        if sequence[index] == sequence[index + 1] == sequence[index + 2]:
            penalty += _COLOUR_TRIPLE_COST
    prefix_whites = 0
    for index, colour in enumerate(sequence):
        prefix_whites += colour
        played = index + 1
        drift = abs(prefix_whites - (played - prefix_whites))
        penalty += (
            max(0, drift - _colour_prefix_limit(index, rounds)) * _COLOUR_IMBALANCE_COST
        )
    for index in range(rounds - 1):
        if sequence[index] == sequence[index + 1] and index % 2 == 0:
            penalty += _COLOUR_REPEAT_COST
    return penalty


def _sequence_with_colour(
    sequence: tuple[int, ...], round_index: int, colour: int
) -> tuple[int, ...]:
    if sequence[round_index] == colour:
        return sequence
    return sequence[:round_index] + (colour,) + sequence[round_index + 1 :]


def _colour_choice_cost(
    seat: int,
    colour: int,
    total_rounds: int,
    round_index: int,
    white_counts: list[int],
    sequences: list[list[int]],
) -> int:
    sequence = sequences[seat]
    cost = 0
    if len(sequence) >= 2 and sequence[-1] == colour and sequence[-2] == colour:
        cost += 100_000
    if sequence and sequence[-1] == colour:
        cost += 3 if round_index % 2 == 0 else 20

    low = total_rounds // 2
    high = (total_rounds + 1) // 2
    remaining = total_rounds - round_index - 1
    new_whites = white_counts[seat] + colour
    if new_whites > high:
        cost += 50_000 * (new_whites - high)
    if new_whites + remaining < low:
        cost += 50_000 * (low - new_whites - remaining)
    played = round_index + 1
    drift = abs(new_whites - (played - new_whites))
    if drift > _colour_prefix_limit(round_index, total_rounds):
        cost += 100_000 * (drift - _colour_prefix_limit(round_index, total_rounds))
    cost += int(abs(new_whites - (round_index + 1) / 2) * 10)
    return cost


def _colour_round_min_cost(
    matches: list[_Match],
    team_count: int,
    players_per_team: int,
    total_rounds: int,
    round_index: int,
    white_counts: list[int],
    sequences: list[list[int]],
) -> _Round:
    match_count = len(matches)
    source = 0
    match_base = 1
    team_base = match_base + match_count
    sink = team_base + team_count
    flow = _MinCostFlow(sink + 1)
    orientation_edges: list[tuple[int, int]] = []
    for match_index, (first, second) in enumerate(matches):
        match_node = match_base + match_index
        flow.add_edge(source, match_node, 1, 0)
        first_seat = _seat(first, players_per_team)
        second_seat = _seat(second, players_per_team)
        first_white_cost = _colour_choice_cost(
            first_seat, 1, total_rounds, round_index, white_counts, sequences
        ) + _colour_choice_cost(
            second_seat, 0, total_rounds, round_index, white_counts, sequences
        )
        second_white_cost = _colour_choice_cost(
            second_seat, 1, total_rounds, round_index, white_counts, sequences
        ) + _colour_choice_cost(
            first_seat, 0, total_rounds, round_index, white_counts, sequences
        )
        first_edge = flow.add_edge(
            match_node, team_base + first[0], 1, first_white_cost
        )
        second_edge = flow.add_edge(
            match_node, team_base + second[0], 1, second_white_cost
        )
        orientation_edges.append((first_edge, second_edge))
    for team in range(team_count):
        flow.add_edge(team_base + team, sink, players_per_team // 2, 0)
    flow.send(source, sink, match_count)

    round_: _Round = []
    for match_index, (first, second) in enumerate(matches):
        first_edge, _second_edge = orientation_edges[match_index]
        first_edge_state = flow.graph[match_base + match_index][first_edge]
        round_.append((first, second) if first_edge_state[1] == 0 else (second, first))
    return round_


def _colour_sequences(
    rounds: list[_Round], team_count: int, players_per_team: int
) -> list[list[int]]:
    sequences = [[] for _seat_index in range(team_count * players_per_team)]
    for round_ in rounds:
        for white_player, black_player in round_:
            sequences[_seat(white_player, players_per_team)].append(1)
            sequences[_seat(black_player, players_per_team)].append(0)
    return sequences


def _colour_reversal_delta(
    sequences: list[list[int]],
    round_index: int,
    white_player: _Player,
    black_player: _Player,
    players_per_team: int,
) -> int:
    white_seat = _seat(white_player, players_per_team)
    black_seat = _seat(black_player, players_per_team)
    white_sequence = tuple(sequences[white_seat])
    black_sequence = tuple(sequences[black_seat])
    before = _player_colour_penalty_tuple(
        white_sequence
    ) + _player_colour_penalty_tuple(black_sequence)
    return (
        _player_colour_penalty_tuple(
            _sequence_with_colour(white_sequence, round_index, 0)
        )
        + _player_colour_penalty_tuple(
            _sequence_with_colour(black_sequence, round_index, 1)
        )
        - before
    )


def _negative_colour_cycle(
    round_: _Round,
    sequences: list[list[int]],
    team_count: int,
    players_per_team: int,
    round_index: int,
) -> tuple[list[int], int] | None:
    edge_costs = [0] * len(round_)
    edges = []
    for edge_index, (white_player, black_player) in enumerate(round_):
        cost = _colour_reversal_delta(
            sequences,
            round_index,
            white_player,
            black_player,
            players_per_team,
        )
        edge_costs[edge_index] = cost
        edges.append(
            (
                white_player[0],
                black_player[0],
                cost,
                edge_index,
            )
        )
    distance = [0] * team_count
    parent: list[tuple[int, int] | None] = [None] * team_count
    changed: int | None = None
    for _iteration in range(team_count):
        changed = None
        for source, target, cost, edge_index in edges:
            if distance[target] > distance[source] + cost:
                distance[target] = distance[source] + cost
                parent[target] = (source, edge_index)
                changed = target
    if changed is None:
        return None

    cycle_vertex = changed
    for _step in range(team_count):
        previous = parent[cycle_vertex]
        if previous is None:
            return None
        cycle_vertex = previous[0]

    cycle: list[int] = []
    current = cycle_vertex
    while True:
        previous = parent[current]
        if previous is None:
            return None
        previous_vertex, edge_index = previous
        cycle.append(edge_index)
        current = previous_vertex
        if current == cycle_vertex:
            break
    cycle.reverse()
    delta = sum(edge_costs[edge_index] for edge_index in cycle)
    if delta >= 0:
        return None
    return cycle, delta


def _reverse_colour_cycle(
    round_: _Round,
    sequences: list[list[int]],
    round_index: int,
    cycle: list[int],
    players_per_team: int,
) -> None:
    for edge_index in cycle:
        white_player, black_player = round_[edge_index]
        round_[edge_index] = (black_player, white_player)
        sequences[_seat(white_player, players_per_team)][round_index] = 0
        sequences[_seat(black_player, players_per_team)][round_index] = 1


def _improve_colour_sequences(
    rounds: list[_Round], team_count: int, players_per_team: int
) -> list[_Round]:
    sequences = _colour_sequences(rounds, team_count, players_per_team)
    max_iterations = min(2_000, max(50, len(rounds) * players_per_team))
    for _iteration in range(max_iterations):
        best: tuple[int, int, list[int]] | None = None
        for round_index, round_ in enumerate(rounds):
            candidate = _negative_colour_cycle(
                round_, sequences, team_count, players_per_team, round_index
            )
            if candidate is None:
                continue
            cycle, delta = candidate
            if best is None or delta < best[0]:
                best = (delta, round_index, cycle)
        if best is None:
            break
        _delta, round_index, cycle = best
        _reverse_colour_cycle(
            rounds[round_index], sequences, round_index, cycle, players_per_team
        )
    return rounds


def _team_balanced_colour(
    matches: list[list[_Match]], team_count: int, players_per_team: int
) -> list[_Round]:
    total_rounds = len(matches)
    white_counts = [0] * (team_count * players_per_team)
    sequences = [[] for _seat_index in range(team_count * players_per_team)]
    rounds: list[_Round] = []
    for round_index, round_matches in enumerate(matches):
        round_ = _colour_round_min_cost(
            round_matches,
            team_count,
            players_per_team,
            total_rounds,
            round_index,
            white_counts,
            sequences,
        )
        rounds.append(round_)
        for white_player, black_player in round_:
            white_seat = _seat(white_player, players_per_team)
            black_seat = _seat(black_player, players_per_team)
            white_counts[white_seat] += 1
            sequences[white_seat].append(1)
            sequences[black_seat].append(0)
    return _improve_colour_sequences(rounds, team_count, players_per_team)


def _exact_colour_balance_no_triples(
    matches: list[list[_Match]],
    team_count: int,
    players_per_team: int,
    *,
    node_limit: int = 2_000_000,
) -> list[_Round] | None:
    """Small exact S5+C1+C2 colourer for short colour-sensitive schedules."""
    round_count = len(matches)
    seat_count = team_count * players_per_team
    if round_count % 2 != 0 or round_count > 8 or seat_count > 80:
        return None

    target_whites = round_count // 2
    target_team_whites = players_per_team // 2
    match_seats = [
        [
            (
                _seat(first, players_per_team),
                _seat(second, players_per_team),
                first,
                second,
            )
            for first, second in round_
        ]
        for round_ in matches
    ]
    whites_needed = [target_whites] * seat_count
    previous = [-1] * seat_count
    previous_previous = [-1] * seat_count
    coloured_rounds: list[_Round] = []
    visited_nodes = 0

    def colour_round(round_index: int) -> bool:
        nonlocal visited_nodes
        if round_index == round_count:
            return all(needed == 0 for needed in whites_needed)

        remaining_after = round_count - round_index - 1
        round_matches = match_seats[round_index]
        team_whites = [0] * team_count
        choices = [False] * len(round_matches)
        order = sorted(
            range(len(round_matches)),
            key=lambda index: (
                round_matches[index][0] // players_per_team,
                round_matches[index][1] // players_per_team,
            ),
        )
        remaining_team_boards = [[0] * team_count for _index in range(len(order) + 1)]
        for index in range(len(order) - 1, -1, -1):
            remaining_team_boards[index] = remaining_team_boards[index + 1][:]
            first_seat, second_seat, _first, _second = round_matches[order[index]]
            remaining_team_boards[index][first_seat // players_per_team] += 1
            remaining_team_boards[index][second_seat // players_per_team] += 1

        def choose_match(position: int) -> bool:
            nonlocal visited_nodes
            visited_nodes += 1
            if visited_nodes > node_limit:
                return False
            if position == len(order):
                if team_whites != [target_team_whites] * team_count:
                    return False
                changed: list[tuple[int, int, tuple[int, int, int, int]]] = []
                round_: _Round = []
                for match_index, first_white in enumerate(choices):
                    first_seat, second_seat, first, second = round_matches[match_index]
                    white_seat, black_seat = (
                        (first_seat, second_seat)
                        if first_white
                        else (second_seat, first_seat)
                    )
                    whites_needed[white_seat] -= 1
                    old_state = (
                        previous[white_seat],
                        previous_previous[white_seat],
                        previous[black_seat],
                        previous_previous[black_seat],
                    )
                    previous_previous[white_seat] = previous[white_seat]
                    previous[white_seat] = 1
                    previous_previous[black_seat] = previous[black_seat]
                    previous[black_seat] = 0
                    changed.append((white_seat, black_seat, old_state))
                    round_.append((first, second) if first_white else (second, first))

                played = round_index + 1
                prefix_limit = _colour_prefix_limit(round_index, round_count)
                for white_seat, black_seat, _old_state in changed:
                    for seat in (white_seat, black_seat):
                        whites_so_far = target_whites - whites_needed[seat]
                        if abs(whites_so_far - (played - whites_so_far)) > prefix_limit:
                            for undo_white, undo_black, old_state in reversed(changed):
                                whites_needed[undo_white] += 1
                                (
                                    previous[undo_white],
                                    previous_previous[undo_white],
                                    previous[undo_black],
                                    previous_previous[undo_black],
                                ) = old_state
                            return False

                coloured_rounds.append(round_)
                if colour_round(round_index + 1):
                    return True
                coloured_rounds.pop()

                for white_seat, black_seat, old_state in reversed(changed):
                    whites_needed[white_seat] += 1
                    (
                        previous[white_seat],
                        previous_previous[white_seat],
                        previous[black_seat],
                        previous_previous[black_seat],
                    ) = old_state
                return False

            match_index = order[position]
            first_seat, second_seat, _first, _second = round_matches[match_index]
            alternatives = (
                (True, first_seat, second_seat),
                (False, second_seat, first_seat),
            )
            for first_white, white_seat, black_seat in alternatives:
                white_team = white_seat // players_per_team
                if team_whites[white_team] >= target_team_whites:
                    continue
                if whites_needed[white_seat] <= 0:
                    continue
                if whites_needed[white_seat] > remaining_after + 1:
                    continue
                if whites_needed[black_seat] > remaining_after:
                    continue
                if previous[white_seat] == previous_previous[white_seat] == 1:
                    continue
                if previous[black_seat] == previous_previous[black_seat] == 0:
                    continue

                team_whites[white_team] += 1
                choices[match_index] = first_white
                feasible = True
                for team in range(team_count):
                    if (
                        team_whites[team] > target_team_whites
                        or team_whites[team] + remaining_team_boards[position + 1][team]
                        < target_team_whites
                    ):
                        feasible = False
                        break
                if feasible and choose_match(position + 1):
                    return True
                team_whites[white_team] -= 1
            return False

        return choose_match(0)

    return coloured_rounds if colour_round(0) else None


def _pair_flip_round_order(
    matches: list[list[_Match]], team_count: int, players_per_team: int
) -> list[int] | None:
    """Order rounds so each odd→even pair can use balanced colouring."""
    round_count = len(matches)
    if round_count < 2:
        return list(range(round_count))

    coloured_cache: dict[tuple[int, int], tuple[_Round, _Round] | None] = {}

    def coloured_pair(first: int, second: int) -> tuple[_Round, _Round] | None:
        key = (first, second)
        if key not in coloured_cache:
            coloured_cache[key] = _pair_flip_colour(
                matches[first], matches[second], team_count, players_per_team
            )
        return coloured_cache[key]

    adjacent_order = list(range(round_count))
    if all(
        coloured_pair(index, index + 1) is not None
        for index in range(0, round_count - 1, 2)
    ):
        return adjacent_order

    def greedy_order() -> list[int] | None:
        remaining = list(range(round_count))
        ordered: list[int] = []
        lone: int | None = None
        while len(remaining) >= 2:
            first = remaining.pop(0)
            match_index = next(
                (
                    index
                    for index, candidate in enumerate(remaining)
                    if coloured_pair(first, candidate) is not None
                ),
                -1,
            )
            if match_index < 0:
                if round_count % 2 == 1 and lone is None:
                    lone = first
                    continue
                return None
            ordered.append(first)
            ordered.append(remaining.pop(match_index))
        if remaining:
            if lone is not None:
                return None
            lone = remaining.pop()
        if lone is not None:
            ordered.append(lone)
        return ordered

    if round_count > 16:
        return greedy_order()

    @lru_cache(maxsize=None)
    def search(remaining: tuple[int, ...]) -> tuple[int, ...] | None:
        if len(remaining) <= 1:
            return remaining
        if len(remaining) % 2 == 1:
            for lone in remaining:
                rest = tuple(item for item in remaining if item != lone)
                ordered_rest = search(rest)
                if ordered_rest is not None:
                    return (*ordered_rest, lone)
        first = remaining[0]
        for candidate in remaining[1:]:
            if coloured_pair(first, candidate) is None:
                continue
            rest = tuple(item for item in remaining if item not in (first, candidate))
            ordered_rest = search(rest)
            if ordered_rest is not None:
                return (first, candidate, *ordered_rest)
        return None

    order = search(tuple(range(round_count)))
    return list(order) if order is not None else None


def _round_has_team_colour_balance(
    rnd: _Round, team_count: int, players_per_team: int
) -> bool:
    target = players_per_team // 2
    white = [0] * team_count
    black = [0] * team_count
    for white_player, black_player in rnd:
        white[white_player[0]] += 1
        black[black_player[0]] += 1
    return all(
        white[team] == target and black[team] == target for team in range(team_count)
    )


def _rounds_have_team_colour_balance(
    rounds: list[_Round], team_count: int, players_per_team: int
) -> bool:
    return all(
        _round_has_team_colour_balance(rnd, team_count, players_per_team)
        for rnd in rounds
    )


def _rounds_have_hard_colour_rules(
    rounds: list[_Round], team_count: int, players_per_team: int
) -> bool:
    if not _rounds_have_team_colour_balance(rounds, team_count, players_per_team):
        return False
    round_count = len(rounds)
    seat_count = team_count * players_per_team
    sequences = [[] for _seat_index in range(seat_count)]
    for round_ in rounds:
        for white_player, black_player in round_:
            sequences[_seat(white_player, players_per_team)].append(1)
            sequences[_seat(black_player, players_per_team)].append(0)
    for sequence in sequences:
        if len(sequence) != round_count:
            return False
        prefix_whites = 0
        for index, colour in enumerate(sequence):
            prefix_whites += colour
            played = index + 1
            if abs(prefix_whites - (played - prefix_whites)) > _colour_prefix_limit(
                index, round_count
            ):
                return False
        for index in range(round_count - 2):
            if sequence[index] == sequence[index + 1] == sequence[index + 2]:
                return False
    return True


def _rounds_have_relaxed_team_colour_rules(
    rounds: list[_Round], team_count: int, players_per_team: int
) -> bool:
    """C1/C2/C3* plus bounded team S5 drift.

    Per-round S5 is preferred by generation, but this relaxed rule allows a
    team to be ``P/2 ± 1`` on the first round of a two-round block if the next
    round compensates it. Cumulative team colour drift may never exceed 2 and
    must be zero after every even prefix and at the final round.
    """
    round_count = len(rounds)
    seat_count = team_count * players_per_team
    sequences = [[] for _seat_index in range(seat_count)]
    team_drift = [0] * team_count
    for round_index, round_ in enumerate(rounds):
        round_white = [0] * team_count
        round_black = [0] * team_count
        for white_player, black_player in round_:
            round_white[white_player[0]] += 1
            round_black[black_player[0]] += 1
            sequences[_seat(white_player, players_per_team)].append(1)
            sequences[_seat(black_player, players_per_team)].append(0)
        must_return_to_zero = (
            round_index + 1
        ) % 2 == 0 or round_index == round_count - 1
        for team in range(team_count):
            team_drift[team] += round_white[team] - round_black[team]
            if abs(team_drift[team]) > 2:
                return False
            if must_return_to_zero and team_drift[team] != 0:
                return False

    for sequence in sequences:
        if len(sequence) != round_count:
            return False
        prefix_whites = 0
        for index, colour in enumerate(sequence):
            prefix_whites += colour
            played = index + 1
            if abs(prefix_whites - (played - prefix_whites)) > _colour_prefix_limit(
                index, round_count
            ):
                return False
        for index in range(round_count - 2):
            if sequence[index] == sequence[index + 1] == sequence[index + 2]:
                return False
    return True


def _colour_with_team_balance_in_order(
    matches: list[list[_Match]],
    team_count: int,
    players_per_team: int,
    *,
    exact_node_limit: int = 2_000_000,
    allow_exact: bool = True,
) -> list[_Round]:
    """Colour the supplied rounds without changing their order."""
    pair_flip_rounds: list[_Round] = []
    r_index = 0
    pair_flip_possible = True
    while r_index < len(matches):
        if r_index + 1 < len(matches):
            coloured_pair = _pair_flip_colour(
                matches[r_index], matches[r_index + 1], team_count, players_per_team
            )
            if coloured_pair is None:
                pair_flip_possible = False
                break
            first, second = coloured_pair
            pair_flip_rounds.append(first)
            pair_flip_rounds.append(second)
            r_index += 2
        else:
            pair_flip_rounds.append(_eulerian_colour(matches[r_index], r_index))
            r_index += 1
    if pair_flip_possible and _rounds_have_hard_colour_rules(
        pair_flip_rounds, team_count, players_per_team
    ):
        return pair_flip_rounds
    if allow_exact:
        exact_rounds = _exact_colour_balance_no_triples(
            matches, team_count, players_per_team, node_limit=exact_node_limit
        )
        if exact_rounds is not None:
            return exact_rounds
    return _team_balanced_colour(matches, team_count, players_per_team)


def _colour_with_team_balance(
    matches: list[list[_Match]],
    team_count: int,
    players_per_team: int,
    *,
    exact_node_limit: int = 2_000_000,
    preserve_round_order: bool = False,
) -> list[_Round]:
    """Colour rounds while preserving the construction's prefix order first.

    Per-round S5 is preferred when it is compatible with the constructed order.
    If the order can only satisfy the hard colour rules with bounded S5 drift,
    keep it: prefix opponent spread is a first-class objective for partial
    tables. Reordering is reserved as a fallback for otherwise uncolourable
    shapes.
    """
    in_order_rounds = _colour_with_team_balance_in_order(
        matches,
        team_count,
        players_per_team,
        exact_node_limit=exact_node_limit,
        allow_exact=False,
    )
    if _rounds_have_relaxed_team_colour_rules(
        in_order_rounds, team_count, players_per_team
    ):
        return in_order_rounds

    relaxed_rounds = _colour_with_relaxed_team_balance(
        matches, team_count, players_per_team
    )
    if relaxed_rounds is not None:
        return relaxed_rounds

    exact_in_order_rounds = _colour_with_team_balance_in_order(
        matches,
        team_count,
        players_per_team,
        exact_node_limit=exact_node_limit,
    )
    if preserve_round_order or _rounds_have_relaxed_team_colour_rules(
        exact_in_order_rounds, team_count, players_per_team
    ):
        return exact_in_order_rounds

    round_order = _pair_flip_round_order(matches, team_count, players_per_team)
    if round_order is not None and round_order != list(range(len(matches))):
        reordered_matches = [matches[index] for index in round_order]
        reordered_rounds = _colour_with_team_balance_in_order(
            reordered_matches,
            team_count,
            players_per_team,
            exact_node_limit=exact_node_limit,
        )
        if _rounds_have_relaxed_team_colour_rules(
            reordered_rounds, team_count, players_per_team
        ):
            return reordered_rounds
        reordered_relaxed = _colour_with_relaxed_team_balance(
            reordered_matches, team_count, players_per_team
        )
        if reordered_relaxed is not None:
            return reordered_relaxed

    return exact_in_order_rounds


def _colour_with_relaxed_team_balance(
    matches: list[list[_Match]], team_count: int, players_per_team: int
) -> list[_Round] | None:
    """Colour using strict S5 when possible, otherwise bounded two-round drift."""
    rounds: list[_Round] = []
    r_index = 0
    while r_index < len(matches):
        if r_index + 1 < len(matches):
            coloured_pair = _pair_flip_colour_relaxed_s5(
                matches[r_index],
                matches[r_index + 1],
                team_count,
                players_per_team,
            )
            if coloured_pair is None:
                return None
            rounds.append(coloured_pair[0])
            rounds.append(coloured_pair[1])
            r_index += 2
        else:
            rounds.append(_eulerian_colour(matches[r_index], r_index))
            r_index += 1
    if _rounds_have_relaxed_team_colour_rules(rounds, team_count, players_per_team):
        return rounds
    return None


def _team_bipartition(
    first_matching: list[_Match],
    second_matching: list[_Match],
    team_count: int,
) -> list[int] | None:
    """Bipartition the union of two team matchings, if possible."""
    adjacent: list[list[int]] = [[] for _team in range(team_count)]
    for matching in (first_matching, second_matching):
        for first, second in matching:
            first_team = first[0]
            second_team = second[0]
            adjacent[first_team].append(second_team)
            adjacent[second_team].append(first_team)

    colour = [-1] * team_count
    for start in range(team_count):
        if colour[start] >= 0:
            continue
        colour[start] = 0
        stack = [start]
        while stack:
            team = stack.pop()
            other_colour = 1 - colour[team]
            for other in adjacent[team]:
                if colour[other] < 0:
                    colour[other] = other_colour
                    stack.append(other)
                elif colour[other] != other_colour:
                    return None
    return colour


def _append_oriented_by_team_colour(
    out: _Round, matches: list[_Match], team_colour: list[int]
) -> bool:
    for first, second in matches:
        first_colour = team_colour[first[0]]
        if first_colour == team_colour[second[0]]:
            return False
        out.append((first, second) if first_colour == 1 else (second, first))
    return True


def _colour_even_round_pair(
    first_round: list[_Match],
    second_round: list[_Match],
    team_count: int,
    players_per_team: int,
) -> tuple[_Round, _Round] | None:
    """Direct colour for the even-team rows produced by `_even_factor_rows`.

    Adjacent board slots in the first round contain two distinct 1-factors, and
    the second round swaps those slots. The union of two 1-factors is bipartite;
    use one side as White on the first slot and the opposite side on the second.
    Every team then gets one White in each slot pair, and every player flips
    colour in the second round.
    """
    chunk_size = team_count // 2
    first_coloured: _Round = []
    second_coloured: _Round = []
    for slot in range(0, players_per_team, 2):
        first_start = slot * chunk_size
        first_next = first_start + chunk_size
        next_end = first_next + chunk_size
        first_slot = first_round[first_start:first_next]
        next_slot = first_round[first_next:next_end]
        team_colour = _team_bipartition(first_slot, next_slot, team_count)
        if team_colour is None:
            return None
        opposite_colour = [1 - colour for colour in team_colour]
        second_slot = second_round[first_start:first_next]
        second_next_slot = second_round[first_next:next_end]
        if not _append_oriented_by_team_colour(first_coloured, first_slot, team_colour):
            return None
        if not _append_oriented_by_team_colour(
            first_coloured, next_slot, opposite_colour
        ):
            return None
        if not _append_oriented_by_team_colour(
            second_coloured, second_slot, opposite_colour
        ):
            return None
        if not _append_oriented_by_team_colour(
            second_coloured, second_next_slot, team_colour
        ):
            return None
    return first_coloured, second_coloured


def _colour_even_matches(
    matches: list[list[_Match]], team_count: int, players_per_team: int
) -> list[_Round]:
    """Colour the even-team construction without the generic pair-flip search."""
    rounds: list[_Round] = []
    r_index = 0
    while r_index < len(matches):
        if r_index + 1 < len(matches):
            coloured_pair = _colour_even_round_pair(
                matches[r_index], matches[r_index + 1], team_count, players_per_team
            )
            if coloured_pair is None:
                raise MolterGenerationError('Could not colour even Molter round-pair.')
            rounds.extend(coloured_pair)
            r_index += 2
        else:
            rounds.append(_eulerian_colour(matches[r_index], r_index))
            r_index += 1
    if not _rounds_have_hard_colour_rules(rounds, team_count, players_per_team):
        raise MolterGenerationError('Even Molter colour rules failed.')
    return rounds


def _partial_spread_probe_exact_node_limit(
    team_count: int, players_per_team: int, rounds: int
) -> int:
    """Keep partial-spread feasibility probes bounded for bulk generation."""
    if team_count * players_per_team <= 36 and rounds <= 4:
        return 500_000
    if team_count * players_per_team <= 120 and rounds <= 7:
        return 100_000
    return 20_000


def _should_probe_spread_partial(
    team_count: int, block_count: int, rounds: int
) -> bool:
    """Use extra spread candidates when the partial-layer budget allows it."""
    if _one_odd_spread_offset_candidate_limit(team_count, block_count, rounds) > 1:
        return True
    return team_count * (2 * block_count) * max(1, rounds) <= 1_200


def _one_odd_spread_offset_candidate_limit(
    team_count: int, block_count: int, rounds: int
) -> int:
    """Adaptive prefix-search budget for odd partial-layer offset patterns."""
    if block_count > 3:
        return 1
    work = team_count * (2 * block_count) * max(1, rounds)
    if work <= 360:
        return 24
    if work <= 720:
        return 12
    if work <= 1_200:
        return 6
    return 1


def _one_odd_spread_offset_candidates(
    team_count: int, block_count: int, rounds: int
) -> tuple[tuple[int, ...], ...]:
    """Bounded offset patterns for odd partial-layer spread probes."""
    primary = _one_odd_partial_offsets(team_count, block_count)
    candidate_limit = _one_odd_spread_offset_candidate_limit(
        team_count, block_count, rounds
    )
    if candidate_limit <= 1:
        return (primary,)

    half = (team_count - 1) // 2

    def factor_prefix_score(
        offsets: tuple[int, ...],
    ) -> tuple[int, int, tuple[int, ...]]:
        seen_factors: set[int] = set()
        deficits: list[int] = []
        for round_index in range(rounds):
            for offset in offsets:
                seen_factors.add((round_index + offset) % half)
            expected = min(half, block_count * (round_index + 1))
            deficits.append(expected - len(seen_factors))
        return max(deficits), sum(deficits), tuple(deficits)

    scored = [
        (factor_prefix_score(offsets), offsets)
        for offsets in permutations(range(half), block_count)
    ]
    scored.sort(key=lambda item: (item[0], item[1] != primary, item[1]))
    candidates = [primary]
    seen = {primary}
    for _score, offsets in scored:
        if offsets in seen:
            continue
        candidates.append(offsets)
        seen.add(offsets)
        if len(candidates) >= candidate_limit:
            break
    return tuple(candidates)


def _match_prefix_spread_score(
    matches: list[list[_Match]], team_count: int, layer_players_per_team: int
) -> tuple[int, int, int, int, int, int, int, int, tuple[int, ...]]:
    counts = [[0] * team_count for _team in range(team_count)]
    seen_masks = [0] * team_count
    prefix_deficits: list[int] = []
    for round_index, rnd in enumerate(matches, start=1):
        for first, second in rnd:
            first_team = first[0]
            second_team = second[0]
            counts[first_team][second_team] += 1
            counts[second_team][first_team] += 1
            seen_masks[first_team] |= 1 << second_team
            seen_masks[second_team] |= 1 << first_team
        expected_distinct = min(team_count - 1, layer_players_per_team * round_index)
        prefix_deficits.append(
            max(expected_distinct - mask.bit_count() for mask in seen_masks)
        )

    i1 = max(
        max(row[:team] + row[team + 1 :]) - min(row[:team] + row[team + 1 :])
        for team, row in enumerate(counts)
    )
    down, up = _layer_floater_incidence(matches, team_count)
    i2_l1, i2_max_abs, i3_spread, i3_max_down, i3_square_sum, _diffs, _down = (
        _floater_balance_score(down, up)
    )
    return (
        max(0, i1 - 1),
        max(prefix_deficits, default=0),
        i1,
        i2_l1,
        i2_max_abs,
        i3_spread,
        i3_max_down,
        i3_square_sum,
        tuple(prefix_deficits),
    )


def _matches_have_final_colour(
    matches: list[list[_Match]],
    team_count: int,
    players_per_team: int,
    *,
    exact_node_limit: int = 2_000_000,
) -> bool:
    rounds = _colour_with_team_balance(
        matches,
        team_count,
        players_per_team,
        exact_node_limit=exact_node_limit,
    )
    return _rounds_have_relaxed_team_colour_rules(rounds, team_count, players_per_team)


def _colour_safe_spread_partial_blocks(
    team_count: int,
    players_per_team: int,
    rounds: int,
    block_offset: int,
    block_count: int,
    factors: tuple[tuple[tuple[int, int], ...], ...],
) -> list[list[_Match]] | None:
    exact_node_limit = _partial_spread_probe_exact_node_limit(
        team_count, players_per_team, rounds
    )
    work = team_count * (2 * block_count) * max(1, rounds)
    spread_options = _one_odd_spread_partial_block_options(
        team_count,
        rounds,
        block_offset,
        block_count,
        factors,
        limit=32 if work <= 720 else 8,
    )
    for spread_matches in spread_options:
        if _floater_role_excess(spread_matches):
            continue
        if (
            _colour_with_relaxed_team_balance(
                spread_matches, team_count, players_per_team
            )
            is not None
        ):
            return spread_matches

    final_colour_tests = 0
    final_colour_limit = 16 if work <= 720 else 4
    best_final: (
        tuple[
            tuple[int, int, int, int, int, int, int, int, tuple[int, ...]],
            list[list[_Match]],
        ]
        | None
    ) = None
    for spread_matches in spread_options:
        if _floater_role_excess(spread_matches):
            continue
        if final_colour_tests >= final_colour_limit:
            continue
        final_colour_tests += 1
        coloured_rounds = _colour_with_team_balance(
            spread_matches,
            team_count,
            players_per_team,
            exact_node_limit=exact_node_limit,
        )
        if not _rounds_have_relaxed_team_colour_rules(
            coloured_rounds, team_count, players_per_team
        ):
            continue
        actual_matches = [
            [(white, black) for white, black in rnd] for rnd in coloured_rounds
        ]
        score = _match_prefix_spread_score(actual_matches, team_count, block_count * 2)
        if best_final is None or score < best_final[0]:
            best_final = score, spread_matches
    return best_final[1] if best_final is not None else None


def _one_odd_partial_layer_matches(
    team_count: int,
    players_per_team: int,
    rounds: int,
    block_offset: int,
    block_count: int,
    planning_down_count: tuple[int, ...],
    planning_up_count: tuple[int, ...],
    factors: tuple[tuple[tuple[int, int], ...], ...],
) -> list[list[_Match]]:
    if (block_offset == 0 or rounds <= 7) and _should_probe_spread_partial(
        team_count, block_count, rounds
    ):
        spread_matches = _colour_safe_spread_partial_blocks(
            team_count,
            players_per_team,
            rounds,
            block_offset,
            block_count,
            factors,
        )
        if spread_matches is not None:
            return spread_matches

    result = _one_odd_fast_partial_plan(
        team_count,
        rounds,
        block_count,
        planning_down_count,
        factors,
        initial_up_counts=planning_up_count,
    )
    if result is not None:
        plan, _ = result
        return _complete_i1_one_odd_plan_blocks(
            team_count,
            rounds,
            block_offset,
            plan,
            factors,
        )

    spread_matches = _colour_safe_spread_partial_blocks(
        team_count,
        players_per_team,
        rounds,
        block_offset,
        block_count,
        factors,
    )
    if spread_matches is not None:
        return spread_matches

    # The final colourer is allowed to reorder round-pairs, while the
    # construction-time probes above preserve the prefix order. Near-complete
    # partial odd layers can be valid only after that final colouring step.
    fallback_matches = _one_odd_spread_partial_blocks(
        team_count,
        rounds,
        block_offset,
        block_count,
        factors,
    )
    if _matches_have_final_colour(fallback_matches, team_count, players_per_team):
        return fallback_matches

    raise MolterGenerationError(
        f'No colour-safe one-odd partial layer for {team_count} teams, '
        f'{players_per_team} players per team, over {rounds} rounds.'
    )


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


def _floater_balance_score(
    down_counts: list[int] | tuple[int, ...],
    up_counts: list[int] | tuple[int, ...],
) -> tuple[int, int, int, int, int, tuple[int, ...], tuple[int, ...]]:
    diffs = [down - up for down, up in zip(down_counts, up_counts, strict=True)]
    return (
        sum(abs(diff) for diff in diffs),
        max((abs(diff) for diff in diffs), default=0),
        max(down_counts) - min(down_counts),
        max(down_counts),
        sum(count * count for count in down_counts),
        tuple(diffs),
        tuple(down_counts),
    )


def _one_odd_fast_partial_plan(
    team_count: int,
    rounds: int,
    block_count: int,
    initial_counts: tuple[int, ...],
    factors: tuple[tuple[tuple[int, int], ...], ...],
    offsets: tuple[int, ...] | None = None,
    initial_up_counts: tuple[int, ...] | None = None,
    max_salts: int = 4,
    node_budget: int = 5_000,
) -> tuple[_OneOddPlan, tuple[int, ...]] | None:
    """Find a hard-valid partial one-odd plan without proving optimal spread."""
    half = (team_count - 1) // 2
    num_round_pairs = (rounds + 1) // 2
    full_round_pairs = rounds // 2
    factor_edges = _one_odd_factor_odd_edges(team_count, factors)
    if offsets is None:
        offsets = _one_odd_partial_offsets(team_count, block_count)

    variables = [
        (block, round_pair)
        for round_pair in range(num_round_pairs)
        for block in range(block_count)
    ]
    variable_index = {variable: index for index, variable in enumerate(variables)}
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

    best: (
        tuple[
            tuple[int, int, int, int, int, tuple[int, ...], tuple[int, ...], int],
            _OneOddPlan,
            tuple[int, ...],
        ]
        | None
    ) = None
    for salt in range(max_salts):
        row_used = [0] * num_round_pairs
        block_used = [0] * block_count
        counts = list(initial_counts)
        up_counts = (
            [0] * team_count if initial_up_counts is None else list(initial_up_counts)
        )
        chosen: list[tuple[int, tuple[int, int]] | None] = [None] * len(variables)
        nodes = 0

        def option_score(
            option: tuple[int, tuple[int, int], int, int, int, int],
            block: int,
            round_pair: int,
        ) -> tuple[int, int, int, int]:
            _factor, dropped, first, second, unit_count, _mask = option
            if unit_count == 2:
                next_first = counts[first] + 1
                next_second = counts[second] + 1
                return (
                    max(next_first, next_second),
                    next_first + next_second,
                    next_first * next_first + next_second * next_second,
                    option_tie_break(block, round_pair, dropped, salt),
                )
            next_first = counts[first] + 1
            up = dropped[0]
            affected = {first, up}
            before_i3 = sum(abs(counts[team] - up_counts[team]) for team in affected)
            after_i3 = sum(
                abs(
                    (counts[team] + (1 if team == first else 0))
                    - (up_counts[team] + (1 if team == up else 0))
                )
                for team in affected
            )
            return (
                after_i3 - before_i3,
                next_first,
                next_first * next_first,
                option_tie_break(block, round_pair, dropped, salt),
            )

        def place(done: int) -> bool:
            nonlocal nodes
            nodes += 1
            if nodes > node_budget:
                return False
            if done == len(chosen):
                return True

            best_var_index = -1
            best_options: (
                list[tuple[int, tuple[int, int], int, int, int, int]] | None
            ) = None
            best_key: tuple[int, int, int] | None = None
            for var_index, (block, round_pair) in enumerate(variables):
                if chosen[var_index] is not None:
                    continue
                blocked = row_used[round_pair] | block_used[block]
                options = [
                    option
                    for option in options_by_variable[var_index]
                    if not (option[5] & blocked)
                ]
                if not options:
                    return False
                key = (len(options), -round_pair, block)
                if best_key is None or key < best_key:
                    best_key = key
                    best_var_index = var_index
                    best_options = options

            assert best_options is not None
            block, round_pair = variables[best_var_index]
            best_options.sort(
                key=lambda option: option_score(option, block, round_pair)
            )
            for factor, dropped, first, second, unit_count, mask in best_options:
                chosen[best_var_index] = (factor, dropped)
                row_used[round_pair] |= mask
                block_used[block] |= mask
                counts[first] += 1
                if unit_count == 2:
                    counts[second] += 1
                    up_counts[first] += 1
                    up_counts[second] += 1
                else:
                    up_counts[dropped[0]] += 1
                if place(done + 1):
                    return True
                if unit_count == 2:
                    up_counts[second] -= 1
                    up_counts[first] -= 1
                    counts[second] -= 1
                else:
                    up_counts[dropped[0]] -= 1
                counts[first] -= 1
                block_used[block] ^= mask
                row_used[round_pair] ^= mask
                chosen[best_var_index] = None
            return False

        if not place(0):
            continue

        plan: list[tuple[_OneOddPlanCell, ...]] = []
        for round_pair in range(num_round_pairs):
            row: list[_OneOddPlanCell] = []
            for block in range(block_count):
                cell = chosen[variable_index[(block, round_pair)]]
                assert cell is not None
                row.append(cell)
            plan.append(tuple(row))
        incidence = tuple(
            counts[team] - initial_counts[team] for team in range(team_count)
        )
        floater_score = _floater_balance_score(counts, up_counts)
        score = (
            floater_score[0],
            floater_score[1],
            floater_score[2],
            floater_score[3],
            floater_score[4],
            floater_score[5],
            floater_score[6],
            salt,
        )
        if best is None or score < best[0]:
            best = (score, tuple(plan), incidence)

    if best is None:
        return None
    return best[1], best[2]


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
    *,
    offsets: tuple[int, ...] | None = None,
    optimise_floaters: bool = True,
    salt: int = 0,
    search_passes: int | None = None,
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
    if offsets is None:
        offsets = _one_odd_partial_offsets(team_count, block_count)
    factor_edges = _one_odd_factor_odd_edges(team_count, factors)

    def fallback_dropped(factor: tuple[tuple[int, int], ...]) -> tuple[int, int]:
        incident = sorted(edge for edge in factor if 0 in edge)
        edge = incident[0]
        return edge if edge[0] == 0 else (edge[1], edge[0])

    cell_keys: list[tuple[int, int]] = []
    cell_key_index: dict[tuple[int, int], int] = {}
    occurrences_by_round: list[list[tuple[int, int]]] = [[] for _round in range(rounds)]
    options_by_cell: list[tuple[tuple[int, int], ...]] = []
    choices: list[int] = []
    for r_index in range(rounds):
        for block, offset in enumerate(offsets):
            factor_index = (r_index + offset) % half
            key = (block, factor_index)
            if key not in cell_key_index:
                cell_key_index[key] = len(cell_keys)
                cell_keys.append(key)
                first_round = (factor_index - offset) % half
                dropped = _affine_floater_edge(team_count, first_round, offset)
                if dropped not in factors[factor_index]:
                    dropped = fallback_dropped(factors[factor_index])
                options = tuple(
                    directed
                    for edge in factor_edges[factor_index]
                    for directed in (edge, (edge[1], edge[0]))
                )
                options_by_cell.append(options)
                affine_choice = options.index(dropped) if dropped in options else 0
                if salt == 0:
                    choice = affine_choice
                elif salt == 1:
                    reversed_dropped = (dropped[1], dropped[0])
                    choice = (
                        options.index(reversed_dropped)
                        if reversed_dropped in options
                        else affine_choice
                    )
                elif salt == 2:
                    choice = 0
                else:
                    rng = _DeterministicRng(
                        team_count * 1_000_003
                        + rounds * 8_191
                        + block_count * 131
                        + len(options_by_cell) * 65_537
                        + salt * 2_654_435_761
                    )
                    choice = rng.randrange(len(options))
                choices.append(choice)
            occurrences_by_round[r_index].append((cell_key_index[key], block))

    option_count = sum(len(options) for options in options_by_cell)
    local_search_budget = option_count * max(1, len(cell_keys)) * max(1, rounds)
    full_edge_search_limit = 100_000
    if local_search_budget > full_edge_search_limit:
        for cell_index, options in enumerate(options_by_cell):
            dropped = options[choices[cell_index]]
            reversed_dropped = (dropped[1], dropped[0])
            options_by_cell[cell_index] = (dropped, reversed_dropped)
            choices[cell_index] = 0

    def oriented_floater(cell_index: int, phase: int) -> tuple[int, int]:
        first, second = options_by_cell[cell_index][choices[cell_index]]
        if phase % 2 == 1:
            return first, second
        return second, first

    def edge_selection_score() -> tuple[
        int,
        int,
        int,
        int,
        int,
        int,
        int,
        int,
        int,
        tuple[int, ...],
        tuple[int, ...],
    ]:
        down_counts = [0] * team_count
        up_counts = [0] * team_count
        seen_phases = [0] * len(cell_keys)
        prefix_i2_l1_sum = 0
        prefix_i2_l1_peak = 0
        prefix_i3_peak = 0
        seat_down = [[0] * team_count for _block in range(block_count)]
        seat_up = [[0] * team_count for _block in range(block_count)]
        s6c_excess = 0
        round_pair_down = [[0] * team_count for _rp in range((rounds + 1) // 2)]
        round_pair_up = [[0] * team_count for _rp in range((rounds + 1) // 2)]
        i4_excess = 0
        for r_index, row in enumerate(occurrences_by_round):
            round_pair = r_index // 2
            for cell_index, _block in row:
                phase = seen_phases[cell_index]
                seen_phases[cell_index] = phase + 1
                down, up = oriented_floater(cell_index, phase)
                down_counts[down] += 1
                up_counts[up] += 1
                seat_down[_block][down] += 1
                seat_up[_block][up] += 1
                s6c_excess += max(0, seat_down[_block][down] - 1)
                s6c_excess += max(0, seat_up[_block][up] - 1)
                round_pair_down[round_pair][down] += 1
                round_pair_up[round_pair][up] += 1
                i4_excess += max(0, round_pair_down[round_pair][down] - 1)
                i4_excess += max(0, round_pair_up[round_pair][up] - 1)
            prefix_i2_l1 = sum(
                abs(down - up) for down, up in zip(down_counts, up_counts, strict=True)
            )
            prefix_i2_l1_sum += prefix_i2_l1
            prefix_i2_l1_peak = max(prefix_i2_l1_peak, prefix_i2_l1)
            prefix_i3_peak = max(prefix_i3_peak, max(down_counts) - min(down_counts))
        final_i2_l1, final_i2_max_abs, i3_spread, i3_max_down, _i3_sum, diffs, down = (
            _floater_balance_score(down_counts, up_counts)
        )
        return (
            s6c_excess,
            final_i2_l1,
            final_i2_max_abs,
            prefix_i2_l1_peak,
            prefix_i2_l1_sum,
            i3_spread,
            i3_max_down,
            prefix_i3_peak,
            i4_excess,
            diffs,
            down,
        )

    best_score = edge_selection_score()
    if optimise_floaters:
        max_passes = (
            search_passes
            if search_passes is not None
            else 3
            if local_search_budget <= full_edge_search_limit
            else 1
        )
        for _pass in range(max_passes):
            improved = False
            for cell_index, options in enumerate(options_by_cell):
                old_choice = choices[cell_index]
                cell_best_score = best_score
                cell_best_choice = old_choice
                for option_index in range(len(options)):
                    if option_index == old_choice:
                        continue
                    choices[cell_index] = option_index
                    score = edge_selection_score()
                    if score < cell_best_score:
                        cell_best_score = score
                        cell_best_choice = option_index
                choices[cell_index] = cell_best_choice
                if cell_best_score < best_score:
                    best_score = cell_best_score
                    improved = True
            if not improved:
                break

    seen: dict[int, int] = {}
    out: list[list[_Match]] = []

    for r_index in range(rounds):
        rnd: list[_Match] = []
        for (cell_index, block), _offset in zip(
            occurrences_by_round[r_index], offsets, strict=True
        ):
            _cell_block, factor_index = cell_keys[cell_index]
            phase = seen.get(cell_index, 0)
            seen[cell_index] = phase + 1
            odd_slot = 2 * (block_offset + block)
            even_slot = odd_slot + 1
            rnd.extend(
                _one_odd_cell_matches(
                    team_count,
                    factors[factor_index],
                    options_by_cell[cell_index][choices[cell_index]],
                    odd_slot,
                    even_slot,
                    phase % 2 == 1,
                )
            )
        out.append(rnd)
    return out


def _floater_role_excess(matches: list[list[_Match]]) -> int:
    down: dict[_Player, int] = {}
    up: dict[_Player, int] = {}
    excess = 0
    for rnd in matches:
        for first, second in rnd:
            if first[1] == second[1]:
                continue
            if first[1] < second[1]:
                descending, ascending = first, second
            else:
                descending, ascending = second, first
            down[descending] = down.get(descending, 0) + 1
            up[ascending] = up.get(ascending, 0) + 1
            excess += max(0, down[descending] - 1)
            excess += max(0, up[ascending] - 1)
    return excess


def _one_odd_spread_partial_block_options(
    team_count: int,
    rounds: int,
    block_offset: int,
    block_count: int,
    factors: tuple[tuple[tuple[int, int], ...], ...],
    *,
    limit: int,
) -> tuple[list[list[_Match]], ...]:
    layer_players_per_team = block_count * 2
    work = team_count * layer_players_per_team * max(1, rounds)
    salt_count = 1
    if work <= 720:
        salt_count = 8
    elif work <= 1_200:
        salt_count = 4

    scored: list[
        tuple[
            tuple[
                int,
                int,
                int,
                int,
                int,
                int,
                int,
                int,
                int,
                tuple[int, ...],
                tuple[int, ...],
                tuple[int, ...],
                int,
            ],
            list[list[_Match]],
        ]
    ] = []
    for offsets in _one_odd_spread_offset_candidates(team_count, block_count, rounds):
        for salt in range(salt_count):
            matches = _one_odd_spread_partial_blocks(
                team_count,
                rounds,
                block_offset,
                block_count,
                factors,
                offsets=offsets,
                salt=salt,
                search_passes=2,
            )
            score = (
                (_floater_role_excess(matches),)
                + _match_prefix_spread_score(
                    matches, team_count, layer_players_per_team
                )
                + (offsets, salt)
            )
            scored.append((score, matches))
    scored.sort(key=lambda item: item[0])

    out: list[list[list[_Match]]] = []
    seen: set[tuple[tuple[_Match, ...], ...]] = set()
    for _score, matches in scored:
        key = tuple(tuple(rnd) for rnd in matches)
        if key in seen:
            continue
        seen.add(key)
        out.append(matches)
        if len(out) >= limit:
            break
    return tuple(out)


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


def _combine_shifted_layers(
    layer_matches: tuple[list[list[_Match]], ...],
    shifts: tuple[int, ...],
    team_count: int,
    rounds: int,
) -> list[list[_Match]]:
    out: list[list[_Match]] = [[] for _round in range(rounds)]
    for matches, shift in zip(layer_matches, shifts):
        shifted_matches = _shift_layer_teams(matches, team_count, shift)
        for round_index, rnd in enumerate(shifted_matches):
            out[round_index].extend(rnd)
    return out


def _layer_floater_incidence(
    matches: list[list[_Match]], team_count: int
) -> tuple[tuple[int, ...], tuple[int, ...]]:
    down = [0] * team_count
    up = [0] * team_count
    for rnd in matches:
        for first, second in rnd:
            if first[1] < second[1]:
                down[first[0]] += 1
                up[second[0]] += 1
            elif second[1] < first[1]:
                down[second[0]] += 1
                up[first[0]] += 1
    return tuple(down), tuple(up)


def _best_layer_shift(
    initial_down: tuple[int, ...],
    initial_up: tuple[int, ...],
    incidence: tuple[tuple[int, ...], tuple[int, ...]],
) -> tuple[int, tuple[int, ...], tuple[int, ...]]:
    """Rotate a complete or partial odd layer's team labels to balance I2, then I3.

    Team-label rotation is a graph automorphism of the layer: it preserves the
    pairings, floater legality, S6c, colours-to-be-assigned, and per-round I1
    shape. It only changes which real teams receive the layer's descending
    and ascending floater incidences.
    """
    down_incidence, up_incidence = incidence
    best = None
    for shift in range(len(down_incidence)):
        shifted_down = _shift_team_counts(down_incidence, shift)
        shifted_up = _shift_team_counts(up_incidence, shift)
        final_down = [
            initial_down[team] + shifted_down[team]
            for team in range(len(down_incidence))
        ]
        final_up = [
            initial_up[team] + shifted_up[team] for team in range(len(down_incidence))
        ]
        score = _floater_balance_score(final_down, final_up) + (shift,)
        if best is None or score < best[0]:
            best = score, shift, shifted_down, shifted_up
    assert best is not None
    return best[1], best[2], best[3]


def _optimise_layer_shifts(
    incidences: list[tuple[tuple[int, ...], tuple[int, ...]]],
) -> tuple[int, ...]:
    """Choose final team-label rotations for all odd layers to minimize I2, then I3.

    For small layer counts we can check every rotation tuple exactly. For larger
    stacks, start from greedy per-layer shifts and run deterministic coordinate
    improvement. The shifts are applied only after all layer matches are built.
    """
    if not incidences:
        return ()
    team_count = len(incidences[0][0])
    exact_search_limit = 200_000
    combinations = 1
    for _ in incidences:
        combinations *= team_count
        if combinations > exact_search_limit:
            break

    def score(
        shifts: tuple[int, ...],
    ) -> tuple[int, int, int, int, int, tuple[int, ...], tuple[int, ...]]:
        down_counts = [0] * team_count
        up_counts = [0] * team_count
        for incidence, shift in zip(incidences, shifts):
            down_incidence, up_incidence = incidence
            shifted_down = _shift_team_counts(down_incidence, shift)
            shifted_up = _shift_team_counts(up_incidence, shift)
            for team, count in enumerate(shifted_down):
                down_counts[team] += count
            for team, count in enumerate(shifted_up):
                up_counts[team] += count
        return _floater_balance_score(down_counts, up_counts)

    if combinations <= exact_search_limit:
        best_score: (
            tuple[int, int, int, int, int, tuple[int, ...], tuple[int, ...]] | None
        ) = None
        best_shifts: tuple[int, ...] | None = None
        for shift_tuple in product(range(team_count), repeat=len(incidences)):
            candidate_score = score(shift_tuple)
            if best_score is None or candidate_score < best_score:
                best_score = candidate_score
                best_shifts = shift_tuple
        assert best_shifts is not None
        return best_shifts

    shifts: list[int] = []
    down_counts = [0] * team_count
    up_counts = [0] * team_count
    for incidence in incidences:
        shift, shifted_down, shifted_up = _best_layer_shift(
            tuple(down_counts), tuple(up_counts), incidence
        )
        shifts.append(shift)
        for team, count in enumerate(shifted_down):
            down_counts[team] += count
        for team, count in enumerate(shifted_up):
            up_counts[team] += count

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


def _default_odd_layer_shifts(
    layers: list[tuple[list[list[_Match]], tuple[tuple[int, ...], tuple[int, ...]]]],
    has_partial_layer: bool,
    rounds: int,
) -> tuple[int, ...]:
    return (
        (0,) * len(layers)
        if has_partial_layer and rounds <= 3
        else _optimise_layer_shifts([incidence for _matches, incidence in layers])
    )


def _should_try_combined_spread_layer(
    team_count: int,
    players_per_team: int,
    rounds: int,
    layer_count: int,
    block_count: int,
) -> bool:
    """Budget combined full+partial alternatives by rotation complexity."""
    if block_count > 3:
        return False
    shift_combinations = team_count**layer_count
    return (
        shift_combinations <= 2_000
        and shift_combinations * players_per_team * max(1, rounds) <= 75_000
    )


def _select_odd_layer_matches(
    layers: list[tuple[list[list[_Match]], tuple[tuple[int, ...], tuple[int, ...]]]],
    layer_options: list[list[list[list[_Match]]]],
    team_count: int,
    players_per_team: int,
    rounds: int,
    has_partial_layer: bool,
) -> list[list[_Match]]:
    """Choose layer rotations with I1/prefix spread before I2, then I3.

    The usual construction picks a single layer shape, then rotates layers for
    floater balance. For full+partial odd tables, a spread-oriented final layer
    can improve I1 once combined with the full layers, even if that partial
    layer is not colour-safe on its own. Try those bounded alternatives and keep
    only candidates whose final colouring satisfies the relaxed colour rules.
    """
    default_shifts = _default_odd_layer_shifts(layers, has_partial_layer, rounds)
    default_matches = _combine_shifted_layers(
        tuple(matches for matches, _incidence in layers),
        default_shifts,
        team_count,
        rounds,
    )
    default_score = _match_prefix_spread_score(
        default_matches, team_count, players_per_team
    )
    if all(len(options) == 1 for options in layer_options):
        return default_matches

    exact_shift_limit = 200_000
    combinations = 1
    for _layer in layer_options:
        combinations *= team_count
        if combinations > exact_shift_limit:
            return default_matches

    scored: list[
        tuple[
            tuple[
                int, int, int, int, int, int, int, int, tuple[int, ...], tuple[int, ...]
            ],
            list[list[_Match]],
            tuple[int, ...],
        ]
    ] = []
    candidate_limit = 12
    option_ranges = tuple(range(len(options)) for options in layer_options)
    for option_indices in product(*option_ranges):
        option_choice = tuple(
            layer_options[layer_index][option_index]
            for layer_index, option_index in enumerate(option_indices)
        )
        for shifts in product(range(team_count), repeat=len(option_choice)):
            matches = _combine_shifted_layers(
                tuple(option_choice), shifts, team_count, rounds
            )
            if _floater_role_excess(matches):
                continue
            score = _match_prefix_spread_score(
                matches, team_count, players_per_team
            ) + (shifts,)
            scored.append((score, matches, option_indices))
    scored.sort(key=lambda item: item[0])

    for _score, matches, _option_indices in scored[:candidate_limit]:
        if (
            _colour_with_relaxed_team_balance(matches, team_count, players_per_team)
            is not None
        ):
            return matches
    final_colour_limit = 12 if rounds <= 7 else 4
    best_by_option: dict[
        tuple[int, ...],
        tuple[
            tuple[
                int, int, int, int, int, int, int, int, tuple[int, ...], tuple[int, ...]
            ],
            list[list[_Match]],
        ],
    ] = {}
    for score, matches, option_indices in scored:
        if score[:-1] >= default_score:
            break
        best_by_option.setdefault(option_indices, (score, matches))
    for _score, matches in sorted(best_by_option.values(), key=lambda item: item[0])[
        :final_colour_limit
    ]:
        if _matches_have_final_colour(
            matches,
            team_count,
            players_per_team,
            exact_node_limit=100_000,
        ):
            return matches
    return default_matches


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
    layers: list[
        tuple[list[list[_Match]], tuple[tuple[int, ...], tuple[int, ...]]]
    ] = []
    layer_options: list[list[list[list[_Match]]]] = []
    # Planning counts guide later layer construction. Final I2, then I3 is optimized after
    # all layers exist by rotating whole layers in _optimise_layer_shifts.
    planning_down_count = [0] * team_count
    planning_up_count = [0] * team_count
    block_offset = 0
    has_partial_layer = False
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
                    tuple(planning_down_count),
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
            has_partial_layer = True
            layer_matches = _one_odd_partial_layer_matches(
                team_count,
                players_per_team,
                rounds,
                block_offset,
                count,
                tuple(planning_down_count),
                tuple(planning_up_count),
                one_odd_factors,
            )
            options = [layer_matches]
            if layers and _should_try_combined_spread_layer(
                team_count,
                players_per_team,
                rounds,
                len(layers) + 1,
                count,
            ):
                if rounds <= 7:
                    for spread_matches in _one_odd_spread_partial_block_options(
                        team_count,
                        rounds,
                        block_offset,
                        count,
                        one_odd_factors,
                        limit=24,
                    ):
                        if spread_matches not in options:
                            options.append(spread_matches)
                else:
                    spread_matches = _one_odd_spread_partial_blocks(
                        team_count,
                        rounds,
                        block_offset,
                        count,
                        one_odd_factors,
                    )
                    if spread_matches != layer_matches:
                        options.append(spread_matches)
                affine_matches = _one_odd_spread_partial_blocks(
                    team_count,
                    rounds,
                    block_offset,
                    count,
                    one_odd_factors,
                    optimise_floaters=False,
                )
                if affine_matches not in options:
                    options.append(affine_matches)
            layer_options.append(options)
        if count == half:
            layer_options.append([layer_matches])
        incidence = _layer_floater_incidence(layer_matches, team_count)
        layers.append((layer_matches, incidence))
        _shift, shifted_down, shifted_up = _best_layer_shift(
            tuple(planning_down_count), tuple(planning_up_count), incidence
        )
        for team, added in enumerate(shifted_down):
            planning_down_count[team] += added
        for team, added in enumerate(shifted_up):
            planning_up_count[team] += added
        block_offset += count

    return _select_odd_layer_matches(
        layers,
        layer_options,
        team_count,
        players_per_team,
        rounds,
        has_partial_layer,
    )


def _colour_complete_i1_matches(
    matches: list[list[_Match]], team_count: int, players_per_team: int
) -> list[_Round]:
    """Colour odd-team rounds, preserving pair-flip colour when it satisfies S5."""
    rounds = _colour_with_team_balance(matches, team_count, players_per_team)
    if _rounds_have_relaxed_team_colour_rules(rounds, team_count, players_per_team):
        return rounds
    raise MolterGenerationError(
        f'Could not colour odd Molter table for {team_count} teams, '
        f'{players_per_team} players per team, over {len(matches)} rounds.'
    )


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
def _even_factor_rows(
    factor_count: int, players_per_team: int, rounds: int
) -> tuple[tuple[int, ...], ...]:
    """Factor row assigned to each board slot of each even-team round.

    Odd→even round-pairs use the same factor multiset in both rounds, with
    adjacent board slots swapped in the second round. That gives each player two
    distinct opponent teams in the pair and makes the pair exactly colourable by
    `_pair_flip_colour` while keeping per-round factor counts as even as
    arithmetic permits. A lone final round uses each slot's next unused factor.
    """
    rows: list[tuple[int, ...]] = []
    for round_index in range(0, rounds, 2):
        if round_index + 1 < rounds:
            first = [
                (slot + round_index) % factor_count for slot in range(players_per_team)
            ]
            second = first[:]
            for slot in range(0, players_per_team, 2):
                second[slot], second[slot + 1] = second[slot + 1], second[slot]
            rows.append(tuple(first))
            rows.append(tuple(second))
        else:
            if round_index == 0:
                rows.append(
                    tuple(slot % factor_count for slot in range(players_per_team))
                )
            else:
                rows.append(
                    tuple(
                        (slot + round_index - (slot % 2)) % factor_count
                        for slot in range(players_per_team)
                    )
                )
    return tuple(rows)


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


@lru_cache(maxsize=None)
def _even_prefix_balanced_factor_rows(
    factor_count: int, players_per_team: int, rounds: int
) -> tuple[tuple[int, ...], ...]:
    """Factor rows that prioritize I1/prefix spread before colour shape."""
    full_layers, partial_slots = divmod(players_per_team, factor_count)
    partial_plan = _even_partial_factor_plan(factor_count, partial_slots, rounds)
    rows: list[tuple[int, ...]] = []
    for round_index in range(rounds):
        row: list[int] = []
        for _layer in range(full_layers):
            row.extend(
                (slot + round_index) % factor_count for slot in range(factor_count)
            )
        row.extend(partial_plan[round_index])
        rows.append(tuple(row))
    return tuple(rows)


@lru_cache(maxsize=None)
def _even_pair_balanced_factor_rows(
    factor_count: int, players_per_team: int, rounds: int
) -> tuple[tuple[int, ...], ...]:
    """I1-oriented rows that keep every two-round block pair-colourable.

    A pair-colourable even block uses the same two slot factors in both rounds,
    swapped across the adjacent physical slots. That is less flexible than the
    fully prefix-balanced rows, but it preserves the exact pair-flip colourer and
    still lets us spread factor counts far better than a fixed cyclic shift.
    """
    block_count = players_per_team // 2
    counts = [0] * factor_count
    used_by_slot: list[set[int]] = [set() for _slot in range(players_per_team)]
    prefix_mask = 0
    rows: list[tuple[int, ...]] = []

    for round_pair in range(rounds // 2):
        first = [-1] * players_per_team
        row_counts = [0] * factor_count
        for block in range(block_count):
            first_slot = 2 * block
            second_slot = first_slot + 1
            allowed = sorted(
                set(range(factor_count))
                - used_by_slot[first_slot]
                - used_by_slot[second_slot]
            )
            if len(allowed) < 2:
                raise MolterGenerationError('Could not build even paired factor rows.')

            best: tuple[tuple[int, int, int, int, int, int, int], int, int] | None = (
                None
            )
            for first_factor, second_factor in combinations(allowed, 2):
                next_counts = counts[:]
                next_counts[first_factor] += 2
                next_counts[second_factor] += 2
                next_mask = prefix_mask | (1 << first_factor) | (1 << second_factor)
                expected_distinct = min(
                    factor_count, players_per_team * (2 * round_pair + 1)
                )
                prefix_deficit = expected_distinct - next_mask.bit_count()
                score = (
                    max(next_counts) - min(next_counts),
                    prefix_deficit,
                    sum(count * count for count in next_counts),
                    row_counts[first_factor] + row_counts[second_factor],
                    counts[first_factor] + counts[second_factor],
                    first_factor + second_factor,
                    first_factor,
                )
                candidate = (score, first_factor, second_factor)
                if best is None or candidate < best:
                    best = candidate
            assert best is not None
            _score, first_factor, second_factor = best

            first[first_slot] = first_factor
            first[second_slot] = second_factor
            for slot in (first_slot, second_slot):
                used_by_slot[slot].add(first_factor)
                used_by_slot[slot].add(second_factor)
            counts[first_factor] += 2
            counts[second_factor] += 2
            row_counts[first_factor] += 1
            row_counts[second_factor] += 1
            prefix_mask |= (1 << first_factor) | (1 << second_factor)

        second = first[:]
        for slot in range(0, players_per_team, 2):
            second[slot], second[slot + 1] = second[slot + 1], second[slot]
        rows.append(tuple(first))
        rows.append(tuple(second))

    if rounds % 2 == 1:
        row: list[int] = []
        row_counts = [0] * factor_count
        for slot in range(players_per_team):
            allowed = sorted(set(range(factor_count)) - used_by_slot[slot])
            if not allowed:
                raise MolterGenerationError('Could not build even lone factor row.')

            best_factor = min(
                allowed,
                key=lambda factor: (
                    max(
                        counts[other] + (1 if other == factor else 0)
                        for other in range(factor_count)
                    )
                    - min(
                        counts[other] + (1 if other == factor else 0)
                        for other in range(factor_count)
                    ),
                    min(factor_count, players_per_team * rounds)
                    - (prefix_mask | (1 << factor)).bit_count(),
                    row_counts[factor],
                    counts[factor],
                    factor,
                ),
            )
            row.append(best_factor)
            used_by_slot[slot].add(best_factor)
            counts[best_factor] += 1
            row_counts[best_factor] += 1
            prefix_mask |= 1 << best_factor
        rows.append(tuple(row))

    return tuple(rows)


def _even_i1_first_work_budget(
    factor_count: int, players_per_team: int, rounds: int
) -> int:
    """Bound short even-row I1 search so bulk generation stays predictable."""
    if rounds > 7:
        return 0
    if factor_count * players_per_team * rounds > 3_000:
        return 0
    return 128


def _even_i1_first_rows_from_salt(
    factor_count: int, players_per_team: int, rounds: int, salt: int
) -> tuple[tuple[int, ...], ...] | None:
    total = players_per_team * rounds
    used_factor_count = min(factor_count, total)
    low, extra = divmod(total, used_factor_count)
    factors = list(range(factor_count))
    rotation = salt % factor_count
    factors = factors[rotation:] + factors[:rotation]
    remaining = {
        factor: low + (1 if index < extra else 0)
        for index, factor in enumerate(factors[:used_factor_count])
    }

    rows = [[-1] * players_per_team for _round in range(rounds)]
    used_by_slot: list[set[int]] = [set() for _slot in range(players_per_team)]
    for round_index in range(rounds):
        row_counts = [0] * factor_count
        slots = list(range(players_per_team))
        if salt & 1:
            slots.reverse()
        elif salt % 3 == 0:
            slots = slots[::2] + slots[1::2]
        elif salt % 3 == 1:
            slots = slots[1::2] + slots[::2]

        for slot in slots:
            candidates = [
                factor
                for factor, count in remaining.items()
                if count > 0 and factor not in used_by_slot[slot]
            ]
            if not candidates:
                return None

            def candidate_key(factor: int) -> tuple[int, int, int, int]:
                future_slots = sum(
                    1
                    for other_slot in range(players_per_team)
                    if factor not in used_by_slot[other_slot]
                    and rows[round_index][other_slot] < 0
                )
                return (
                    -remaining[factor],
                    row_counts[factor],
                    -future_slots,
                    (factor + salt * 7 + round_index * 3 + slot) % factor_count,
                )

            factor = min(candidates, key=candidate_key)
            rows[round_index][slot] = factor
            remaining[factor] -= 1
            used_by_slot[slot].add(factor)
            row_counts[factor] += 1

    if any(remaining.values()):
        return None
    return tuple(tuple(row) for row in rows)


@lru_cache(maxsize=None)
def _even_i1_first_factor_row_candidates(
    factor_count: int, players_per_team: int, rounds: int
) -> tuple[tuple[tuple[int, ...], ...], ...]:
    """Balanced even rows for short horizons, before colour filtering.

    These rows are deliberately generic: they first make the cumulative factor
    counts as even as arithmetic permits, while preserving S4 by never repeating
    a factor in the same physical slot. The caller then keeps only candidates
    that the existing hard colour checker accepts.
    """
    limit = _even_i1_first_work_budget(factor_count, players_per_team, rounds)
    if limit == 0:
        return ()

    seen: set[tuple[tuple[int, ...], ...]] = set()
    scored: list[tuple[tuple[int, int, int], int, tuple[tuple[int, ...], ...]]] = []
    for salt in range(limit):
        rows = _even_i1_first_rows_from_salt(
            factor_count, players_per_team, rounds, salt
        )
        if rows is None or rows in seen:
            continue
        seen.add(rows)
        score = _even_factor_row_score(rows, factor_count)
        priority = _even_candidate_priority(score)
        if priority[0] > 0:
            continue
        scored.append((priority, salt, rows))
    scored.sort()
    return tuple(rows for _priority, _salt, rows in scored)


def _even_factor_row_score(
    rows: tuple[tuple[int, ...], ...], factor_count: int
) -> tuple[int, int]:
    """Return ``(I1, prefix_deficit)`` for even-team factor rows."""
    if not rows:
        return 0, 0
    counts = [0] * factor_count
    prefix_mask = 0
    prefix_deficit = 0
    slots = len(rows[0])
    for round_index, row in enumerate(rows, start=1):
        for factor in row:
            counts[factor] += 1
            prefix_mask |= 1 << factor
        expected_distinct = min(factor_count, slots * round_index)
        prefix_deficit = max(
            prefix_deficit, expected_distinct - prefix_mask.bit_count()
        )
    used_counts = [count for count in counts if count]
    i1 = max(used_counts) - min(used_counts) if used_counts else 0
    return i1, prefix_deficit


def _even_candidate_priority(score: tuple[int, int]) -> tuple[int, int, int]:
    """Rank even candidates for short-prefix spread.

    I1 values 0 and 1 are both acceptable for the current Molter ideal; once
    that threshold is met, prefer full prefix opponent coverage.
    """
    i1, prefix_deficit = score
    return max(0, i1 - 1), prefix_deficit, i1


def _even_prefix_round_orders(rounds: int) -> tuple[tuple[int, ...], ...]:
    if rounds <= 3:
        return tuple(permutations(range(rounds)))
    out = [tuple(range(rounds))]
    rest = tuple(range(3, rounds))
    for prefix in permutations(range(3)):
        order = (*prefix, *rest)
        if order not in out:
            out.append(order)
    return tuple(out)


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


def _generate_even_rounds(
    team_count: int, players_per_team: int, rounds: int
) -> list[_Round]:
    """Generate even-team rounds, relaxing S5 only when it improves I1."""
    factor_count = team_count - 1
    strict_rows = _even_factor_rows(factor_count, players_per_team, rounds)
    best_score = _even_factor_row_score(strict_rows, factor_count)
    best_priority = _even_candidate_priority(best_score)
    best_rounds = _colour_even_matches(
        _even_matches_from_factor_rows(team_count, strict_rows),
        team_count,
        players_per_team,
    )

    pair_rows = _even_pair_balanced_factor_rows(factor_count, players_per_team, rounds)
    pair_score = _even_factor_row_score(pair_rows, factor_count)
    pair_priority = _even_candidate_priority(pair_score)
    if pair_priority < best_priority:
        pair_rounds = _colour_even_matches(
            _even_matches_from_factor_rows(team_count, pair_rows),
            team_count,
            players_per_team,
        )
        best_priority = pair_priority
        best_rounds = pair_rounds

    if best_priority[0] > 0:
        for search_rows in _even_i1_first_factor_row_candidates(
            factor_count, players_per_team, rounds
        ):
            search_score = _even_factor_row_score(search_rows, factor_count)
            search_priority = _even_candidate_priority(search_score)
            if search_priority >= best_priority:
                continue
            relaxed_rounds = _colour_with_relaxed_team_balance(
                _even_matches_from_factor_rows(team_count, search_rows),
                team_count,
                players_per_team,
            )
            if relaxed_rounds is not None:
                best_priority = search_priority
                best_rounds = relaxed_rounds

    prefix_rows = _even_prefix_balanced_factor_rows(
        factor_count, players_per_team, rounds
    )
    for order in _even_prefix_round_orders(rounds):
        ordered_rows = tuple(prefix_rows[index] for index in order)
        prefix_score = _even_factor_row_score(ordered_rows, factor_count)
        prefix_priority = _even_candidate_priority(prefix_score)
        if prefix_priority >= best_priority:
            continue
        relaxed_rounds = _colour_with_relaxed_team_balance(
            _even_matches_from_factor_rows(team_count, ordered_rows),
            team_count,
            players_per_team,
        )
        if relaxed_rounds is not None:
            best_priority = prefix_priority
            best_rounds = relaxed_rounds
    return best_rounds


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
        regular = _colour_complete_i1_matches(
            regular_matches, team_count, players_per_team
        )
        emitted_rounds = tuple(_emit(rnd) for rnd in regular)
    else:
        regular = _generate_even_rounds(team_count, players_per_team, rounds)
        emitted_rounds = tuple(_emit_even(rnd, team_count) for rnd in regular)

    table = FixedPairingTable(
        team_count=team_count,
        players_per_team=players_per_team,
        rounds=emitted_rounds,
    )
    # P=2 has very little slack: reject edge-case horizons that the fast even
    # construction cannot realize without breaching hard verifier rules.
    if _VERIFY_GENERATED_TABLES or players_per_team == 2:
        report = verify_molter_table(table)
        if not report.ok:
            raise MolterGenerationError(
                f'Generated table for {team_count}×{players_per_team} over '
                f'{rounds} rounds failed verification: {report.errors[0]}'
            )
    return table
