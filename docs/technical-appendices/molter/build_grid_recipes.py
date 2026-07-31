#!/usr/bin/env python3
"""Build Molter recipes from factor grids with decoupled colouring.

The builder treats schedule quality and colour legality as independent
problems, which they are:

* **Schedule.** For even team counts a round is one 1-factor of ``K_N`` per
  board; for odd team counts a round is one one-odd 2-factor per board pair.
  In both cases S4 only requires that a factor never repeats in the same
  column (board or board pair), so the whole opponent structure reduces to a
  symbol grid: symbols are factor indices, columns are boards/cells, rows are
  rounds. Balanced symbol loads give ``I1 <= 1`` (exact when the arithmetic
  divides), fresh symbols in early rows give a prefix deficit of ``0``, and
  distinct symbols per row give ``I5 <= 1``.

* **Colour.** Any Molter schedule is hard-rule colourable. Taking rounds in
  two-round blocks, the union of the two matchings is a disjoint set of even
  cycles, so alternating colours around each cycle makes every player flip
  colour inside the block: C1, C2 and C3 hold by construction and every team
  returns to balance at the block boundary (S5). Choosing which cycles to
  flip controls the odd-round team drift; when no flip choice keeps it within
  the S5 bound, a CP-SAT model per block lets a few players take a same-colour
  block (a colour debt) that the next block is forced to repay. The last two
  blocks are solved together so the final block's needs are planned for.

Recipes are emitted in the existing artifact formats (``even_factor_rows``
and ``odd_cell_occurrences``), so the runtime replay path is unchanged. The
output JSON merges into a recipe state with::

    python3 build_solver_recipes.py --merge-only --ignore-existing-output \
      --merge-input src/data/pairings/resources/molter_recipes.mrec \
      --merge-input grid_recipes.json --output merged.json

The merge keeps a new recipe only when it strictly improves the metric
priority, and every candidate must pass the hard verifier.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SRC_DIR = ROOT / 'src'
THIS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SRC_DIR))
sys.path.insert(0, str(THIS_DIR))

import build_solver_recipes as recipes  # noqa: E402
import molter_recipe_generator as mg  # noqa: E402
from data.pairings.molter_verifier import verify_molter_table  # noqa: E402

Match = tuple[tuple[int, int], tuple[int, int]]


# ---------- symbol grid ----------


def build_grid(
    symbol_count: int, columns: int, rounds: int, salt: int, column_cap: int = 1
) -> tuple[tuple[int, ...], ...] | None:
    """Prefix-first, load-balanced grid; a symbol repeats at most
    ``column_cap`` times per column and at most ``ceil(columns/symbols)``
    times per row."""
    row_cap = -(-columns // symbol_count)
    loads = [0] * symbol_count
    seen = [False] * symbol_count
    column_used: list[dict[int, int]] = [{} for _ in range(columns)]
    out: list[tuple[int, ...]] = []

    for row_index in range(rounds):
        order = sorted(
            range(symbol_count),
            key=lambda s: (
                seen[s],
                loads[s],
                (s + 7 * salt + 3 * row_index) % symbol_count,
            ),
        )
        row_counts = [0] * symbol_count
        assignment: dict[int, int] = {}

        def augment(symbol: int, visited: set[int]) -> bool:
            for column in range(columns):
                if column in visited:
                    continue
                if column_used[column].get(symbol, 0) >= column_cap:
                    continue
                visited.add(column)
                holder = assignment.get(column)
                if holder is None or augment(holder, visited):
                    assignment[column] = symbol
                    return True
            return False

        chosen = 0
        cursor = 0
        while chosen < columns and cursor < 4 * symbol_count:
            symbol = order[cursor % len(order)]
            cursor += 1
            if row_counts[symbol] >= row_cap:
                continue
            snapshot = dict(assignment)
            if augment(symbol, set()):
                chosen += 1
                row_counts[symbol] += 1
            else:
                assignment.clear()
                assignment.update(snapshot)
        if chosen < columns:
            return None
        row = tuple(assignment[column] for column in range(columns))
        for column, symbol in enumerate(row):
            column_used[column][symbol] = column_used[column].get(symbol, 0) + 1
            loads[symbol] += 1
            seen[symbol] = True
        out.append(row)
    return tuple(out)


def grid_score(
    rows: tuple[tuple[int, ...], ...], symbol_count: int, columns: int
) -> tuple[int, int]:
    """(load spread, worst prefix deficit) of a grid, both lower better."""
    loads = [0] * symbol_count
    seen: set[int] = set()
    worst_prefix = 0
    for row_index, row in enumerate(rows):
        for symbol in row:
            loads[symbol] += 1
            seen.add(symbol)
        expected = min(symbol_count, columns * (row_index + 1))
        worst_prefix = max(worst_prefix, expected - len(seen))
    used = [load for load in loads if load]
    spread = max(used) - min(used) if used else 0
    return (spread, worst_prefix)


# ---------- colouring ----------


def _pair_cycles(first_round: list[Match], second_round: list[Match]):
    """Alternating cycles of the union of two rounds' matchings.

    Each cycle is a list of ``(round_offset, match_index, oriented)``;
    ``oriented`` keeps the stored (first, second) order as (white, black).
    """
    partners = ({}, {})
    for offset, matches in ((0, first_round), (1, second_round)):
        for index, (a, b) in enumerate(matches):
            partners[offset][a] = (b, index)
            partners[offset][b] = (a, index)
    seen = (set(), set())
    cycles = []
    for start in partners[0]:
        _, first_index = partners[0][start]
        if first_index in seen[0]:
            continue
        cycle = []
        vertex = start
        offset = 0
        while True:
            other, match_index = partners[offset][vertex]
            seen[offset].add(match_index)
            match = (first_round if offset == 0 else second_round)[match_index]
            cycle.append((offset, match_index, match[0] == vertex))
            offset = 1 - offset
            vertex = other
            if vertex == start and offset == 0:
                break
        cycles.append(cycle)
    return cycles


def _cycle_drift(cycle, first_round, team_count):
    vector = [0] * team_count
    for offset, match_index, oriented in cycle:
        if offset != 0:
            continue
        a, b = first_round[match_index]
        white, black = (a, b) if oriented else (b, a)
        vector[white[0]] += 1
        vector[black[0]] -= 1
    return vector


def _choose_flips(vectors: list[list[int]], team_count: int) -> tuple[list[int], int]:
    order = sorted(range(len(vectors)), key=lambda i: -sum(abs(x) for x in vectors[i]))
    totals = [0] * team_count
    signs = [1] * len(vectors)
    for i in order:
        plus = max(abs(totals[t] + vectors[i][t]) for t in range(team_count))
        minus = max(abs(totals[t] - vectors[i][t]) for t in range(team_count))
        sign = 1 if plus <= minus else -1
        signs[i] = sign
        for t in range(team_count):
            totals[t] += sign * vectors[i][t]
    best = max(abs(x) for x in totals)
    if best == 0 or not vectors:
        return signs, best
    try:
        from ortools.sat.python import cp_model
    except ImportError:
        return signs, best
    model = cp_model.CpModel()
    flips = [model.new_bool_var(f'f{i}') for i in range(len(vectors))]
    bound = sum(sum(abs(x) for x in v) for v in vectors) or 1
    peak = model.new_int_var(0, bound, 'peak')
    for t in range(team_count):
        expression = sum(
            (1 - 2 * flips[i]) * vectors[i][t] for i in range(len(vectors))
        )
        model.add(expression <= peak)
        model.add(-expression <= peak)
    model.minimize(peak)
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = 2.0
    solver.parameters.num_search_workers = 4
    status = solver.solve(model)
    if status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        value = solver.value(peak)
        if value < best:
            return [1 - 2 * solver.value(f) for f in flips], value
    return signs, best


def _eulerian_colour(matches: list[Match], team_count: int) -> list[Match] | None:
    adjacency: dict[int, list[int]] = {t: [] for t in range(team_count)}
    for index, (a, b) in enumerate(matches):
        adjacency[a[0]].append(index)
        adjacency[b[0]].append(index)
    used = [False] * len(matches)
    orient = [True] * len(matches)
    for start in range(team_count):
        while True:
            unused = [i for i in adjacency[start] if not used[i]]
            if not unused:
                break
            vertex = start
            while True:
                edge = next((i for i in adjacency[vertex] if not used[i]), None)
                if edge is None:
                    return None
                used[edge] = True
                a, b = matches[edge]
                if a[0] == vertex:
                    orient[edge] = True
                    vertex = b[0]
                else:
                    orient[edge] = False
                    vertex = a[0]
                if vertex == start:
                    break
    return [
        matches[i] if orient[i] else (matches[i][1], matches[i][0])
        for i in range(len(matches))
    ]


def colour_by_alternation(
    matches: list[list[Match]], team_count: int
) -> tuple[list[list[Match]], int] | None:
    """Alternation colouring; returns (rounds, worst odd-round team drift)."""
    coloured: list[list[Match] | None] = [None] * len(matches)
    worst = 0
    r = 0
    while r + 1 < len(matches):
        first_round, second_round = matches[r], matches[r + 1]
        cycles = _pair_cycles(first_round, second_round)
        vectors = [_cycle_drift(c, first_round, team_count) for c in cycles]
        signs, peak = _choose_flips(vectors, team_count)
        worst = max(worst, peak)
        out = ([None] * len(first_round), [None] * len(second_round))
        for cycle, sign in zip(cycles, signs):
            for offset, match_index, oriented in cycle:
                keep = oriented if sign == 1 else not oriented
                source = (first_round if offset == 0 else second_round)[match_index]
                out[offset][match_index] = source if keep else (source[1], source[0])
        coloured[r], coloured[r + 1] = out
        r += 2
    if r < len(matches):
        last = _eulerian_colour(matches[r], team_count)
        if last is None:
            return None
        coloured[r] = last
    return coloured, worst  # type: ignore[return-value]


def _colour_span(
    span: list[list[Match]],
    team_count: int,
    players_per_team: int,
    drift: list[int],
    history: list[tuple[int, int]],
    *,
    is_final: bool,
    force_clean: bool,
    timeout_seconds: float,
) -> list[list[Match]] | None:
    """Colour a span (one block, or the final two blocks) with CP-SAT.

    Hard rules: bounded team drift restored at block boundaries and at the
    final round; per-player prefix drift bounds and no colour triples, using
    the carried per-seat drift and last two colours. A seat entering with
    non-zero drift must leave the span balanced, so colour debts live exactly
    one block. New debts are allowed unless ``force_clean``; the objective
    minimises them first, then the distance from exact per-round balance.
    """
    from ortools.sat.python import cp_model

    seat_count = team_count * players_per_team
    span_length = len(span)

    def seat(player):
        return player[0] * players_per_team + player[1]

    model = cp_model.CpModel()
    seat_colours: list[list] = [[] for _ in range(seat_count)]
    team_drift = []
    variables = []
    for round_offset, round_matches in enumerate(span):
        round_vars = {}
        team_whites = [[] for _ in range(team_count)]
        for match_index, (first, second) in enumerate(round_matches):
            var = model.new_bool_var(f'w{round_offset}_{match_index}')
            round_vars[match_index] = var
            seat_colours[seat(first)].append(var)
            seat_colours[seat(second)].append(1 - var)
            team_whites[first[0]].append(var)
            team_whites[second[0]].append(1 - var)
        variables.append(round_vars)
        team_drift.append(
            [2 * sum(team_whites[t]) - players_per_team for t in range(team_count)]
        )

    exact_terms = []
    for t in range(team_count):
        cumulative = 0
        for index in range(span_length):
            cumulative = cumulative + team_drift[index][t]
            closes_block = index % 2 == 1
            final_round = is_final and index == span_length - 1
            if closes_block or final_round:
                model.add(cumulative == 0)
            else:
                model.add(cumulative <= 2)
                model.add(cumulative >= -2)
                excess = model.new_int_var(0, players_per_team, f'ex{t}_{index}')
                model.add(cumulative <= excess)
                model.add(-cumulative <= excess)
                exact_terms.append(excess)

    debt_terms = []
    for s in range(seat_count):
        colours = seat_colours[s]
        h1, h2 = history[s]
        sequence = ([h1] if h1 >= 0 else []) + ([h2] if h2 >= 0 else [])
        known = len(sequence)
        sequence = sequence + colours
        for i in range(len(sequence) - 2):
            if i + 2 < known:
                continue
            window = sequence[i] + sequence[i + 1] + sequence[i + 2]
            model.add(window >= 1)
            model.add(window <= 2)
        after = drift[s]
        for index in range(span_length):
            after = after + 2 * colours[index] - 1
            final_round = is_final and index == span_length - 1
            limit = 1 if final_round else 2
            model.add(after <= limit)
            model.add(after >= -limit)
        if is_final:
            continue
        if drift[s] != 0 or force_clean:
            model.add(after == 0)
        else:
            debt = model.new_int_var(0, 2, f'debt{s}')
            model.add(after <= debt)
            model.add(-after <= debt)
            debt_terms.append(debt)

    if exact_terms or debt_terms:
        model.minimize(1000 * sum(debt_terms) + sum(exact_terms))

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = timeout_seconds
    solver.parameters.num_search_workers = 8
    status = solver.solve(model)
    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return None

    out = []
    for round_offset, round_matches in enumerate(span):
        coloured_round = []
        for match_index, (first, second) in enumerate(round_matches):
            white_first = bool(solver.value(variables[round_offset][match_index]))
            coloured_round.append((first, second) if white_first else (second, first))
        out.append(coloured_round)
    return out


def _apply_span(span_coloured, drift, history, players_per_team) -> None:
    for round_matches in span_coloured:
        for first, second in round_matches:
            white_seat = first[0] * players_per_team + first[1]
            black_seat = second[0] * players_per_team + second[1]
            drift[white_seat] += 1
            drift[black_seat] -= 1
            history[white_seat] = (history[white_seat][1], 1)
            history[black_seat] = (history[black_seat][1], 0)


def colour_case(
    matches: list[list[Match]],
    team_count: int,
    players_per_team: int,
    cp_timeout: float = 5.0,
) -> list[list[Match]] | None:
    alternation = colour_by_alternation(matches, team_count)
    if alternation is not None and alternation[1] == 0:
        return alternation[0]

    seat_count = team_count * players_per_team
    blocks = [matches[r : r + 2] for r in range(0, len(matches), 2)]
    spans: list[tuple[list[list[Match]], bool]] = []
    for index in range(len(blocks)):
        if index == len(blocks) - 2:
            spans.append((blocks[index] + blocks[index + 1], True))
            break
        spans.append((blocks[index], index == len(blocks) - 1))

    drift = [0] * seat_count
    history = [(-1, -1)] * seat_count
    coloured: list[list[Match]] = []
    saved: list[tuple[list[int], list[tuple[int, int]]]] = []
    forced = [False] * len(spans)
    index = 0
    backtracks = 0
    while index < len(spans):
        span, is_final = spans[index]
        state = (list(drift), list(history))
        span_coloured = _colour_span(
            span,
            team_count,
            players_per_team,
            drift,
            history,
            is_final=is_final,
            force_clean=forced[index],
            timeout_seconds=cp_timeout * (2 if is_final else 1),
        )
        if span_coloured is None:
            if index == 0 or backtracks >= 4 or forced[index - 1]:
                return None
            backtracks += 1
            index -= 1
            drift, history = (list(part) for part in saved[index])
            del coloured[index * 2 :]
            del saved[index:]
            forced[index] = True
            continue
        saved.append(state)
        _apply_span(span_coloured, drift, history, players_per_team)
        coloured.extend(span_coloured)
        index += 1
    return coloured


# ---------- even team counts ----------


def _even_i1_bound(team_count: int, players_per_team: int, rounds: int) -> int:
    load = players_per_team * rounds
    opponents = team_count - 1
    if load <= opponents or load % opponents == 0:
        return 0
    return 1


def build_even_case(team_count: int, players_per_team: int, rounds: int):
    bound = _even_i1_bound(team_count, players_per_team, rounds)
    factor_count = team_count - 1
    candidates = []
    seen_rows = set()
    for salt in range(12):
        rows = build_grid(factor_count, players_per_team, rounds, salt)
        if rows is None or rows in seen_rows:
            continue
        seen_rows.add(rows)
        candidates.append((grid_score(rows, factor_count, players_per_team), rows))
        if candidates[-1][0] == (bound, 0):
            break
    candidates.sort(key=lambda item: item[0])
    for _score, rows in candidates[:6]:
        matches = mg._even_matches_from_factor_rows(team_count, rows)
        coloured = colour_case(matches, team_count, players_per_team)
        if coloured is None:
            continue
        bits = recipes._colour_bits(matches, coloured)
        case = {
            'team_count': team_count,
            'players_per_team': players_per_team,
            'rounds': rounds,
            'candidate_label': 'grid_alternation_even',
            'schedule': {
                'kind': 'even_factor_rows',
                'rows': [list(row) for row in rows],
            },
            'colour_bit_count': len(bits),
            'colour_bits': recipes._pack_bits(bits),
        }
        table = recipes.materialize_recipe(case)
        if verify_molter_table(table).ok:
            return case
    return None


# ---------- odd team counts ----------


def _odd_factorization(team_count: int):
    return mg._one_odd_factorization(team_count) or mg._small_one_odd_factorization(
        team_count
    )


def _occurrence_options(team_count: int, factors, factor_index: int):
    """(dropped, reverse, descender, ascender) choices for one factor."""
    factor = factors[factor_index]
    odd_edges = mg._one_odd_factor_odd_edges(team_count, factors)[factor_index]
    options = []
    for edge in odd_edges:
        for dropped in (edge, (edge[1], edge[0])):
            for reverse in (False, True):
                cell = mg._one_odd_cell_matches(
                    team_count, factor, dropped, 0, 1, reverse
                )
                floater = next((m for m in cell if m[0][1] != m[1][1]), None)
                if floater is None:
                    continue
                if floater[0][1] == 0:
                    descender, ascender = floater[0][0], floater[1][0]
                else:
                    descender, ascender = floater[1][0], floater[0][0]
                options.append((dropped, reverse, descender, ascender))
    return options


class _RoleAssigner:
    """Choose per-occurrence dropped edges cell by cell.

    Hard rules are per cell: floater roles never repeat (S6c), and a factor
    used twice replays with the same dropped edge and the opposite reverse
    phase, which swaps the floater roles, so both endpoints stay reserved.
    Round-pair role repeats (I4) and per-team role balance (I2/I3) are greedy
    preferences, with backtracking over dropped-edge choices inside a cell.
    """

    def __init__(self, team_count: int, cells: int, rounds: int, salt: int):
        self.team_count = team_count
        self.cells = cells
        self.rounds = rounds
        self.salt = salt
        self.descents = [0] * team_count
        self.ascents = [0] * team_count
        self.nodes = 0

    def assign(self, grid, options_by_factor):
        entries: list[list[dict | None]] = [
            [None] * self.cells for _ in range(self.rounds)
        ]
        for cell in range(self.cells):
            if not self._assign_cell(cell, grid, options_by_factor, entries):
                return None
            for r in range(self.rounds):
                entry = entries[r][cell]
                self.descents[entry['_descender']] += 1
                self.ascents[entry['_ascender']] += 1
        out = []
        for r in range(self.rounds):
            out.extend(entries[r])
        return out

    def _assign_cell(self, cell, grid, options_by_factor, entries) -> bool:
        column = [grid[r][cell] for r in range(self.rounds)]
        counts: dict[int, int] = {}
        for factor in column:
            counts[factor] = counts.get(factor, 0) + 1
        used_descents: set[int] = set()
        used_ascents: set[int] = set()
        first_use: dict[int, tuple] = {}
        self.nodes = 0

        def role_pressure(r, descender, ascender):
            pair_start = r - (r % 2)
            pressure = 0
            for rr in (pair_start, pair_start + 1):
                if rr >= self.rounds or rr == r:
                    continue
                for other_cell in range(cell):
                    entry = entries[rr][other_cell]
                    if entry is not None:
                        pressure += entry['_descender'] == descender
                        pressure += entry['_ascender'] == ascender
                mine = entries[rr][cell]
                if mine is not None:
                    pressure += mine['_descender'] == descender
                    pressure += mine['_ascender'] == ascender
            return pressure

        def restore_roles():
            used_descents.clear()
            used_ascents.clear()
            for rr in range(self.rounds):
                entry = entries[rr][cell]
                if entry is not None:
                    used_descents.add(entry['_descender'])
                    used_ascents.add(entry['_ascender'])
                    if counts[entry['factor']] > 1:
                        used_descents.add(entry['_ascender'])
                        used_ascents.add(entry['_descender'])

        def fill(r) -> bool:
            if r == self.rounds:
                return True
            self.nodes += 1
            if self.nodes > 20000:
                return False
            factor = column[r]
            previous = first_use.get(factor)
            if previous is not None:
                dropped, reverse = previous
                for d, rev, descender, ascender in options_by_factor[factor]:
                    if d == dropped and rev == (not reverse):
                        entries[r][cell] = {
                            'factor': factor,
                            'dropped': [d[0], d[1]],
                            'reverse': bool(rev),
                            '_descender': descender,
                            '_ascender': ascender,
                        }
                        if fill(r + 1):
                            return True
                        entries[r][cell] = None
                return False
            is_reused = counts[factor] > 1
            scored = []
            for dropped, reverse, descender, ascender in options_by_factor[factor]:
                if descender in used_descents or ascender in used_ascents:
                    continue
                if is_reused and (
                    ascender in used_descents or descender in used_ascents
                ):
                    continue
                scored.append(
                    (
                        (
                            role_pressure(r, descender, ascender),
                            self.descents[descender],
                            self.ascents[ascender],
                            abs(self.descents[descender] - self.ascents[descender])
                            + abs(self.descents[ascender] - self.ascents[ascender]),
                            (descender * 7 + ascender * 3 + r + self.salt * 11)
                            % self.team_count,
                        ),
                        dropped,
                        reverse,
                        descender,
                        ascender,
                    )
                )
            scored.sort()
            for _cost, dropped, reverse, descender, ascender in scored[:8]:
                first_use[factor] = (dropped, reverse)
                used_descents.add(descender)
                used_ascents.add(ascender)
                if is_reused:
                    used_descents.add(ascender)
                    used_ascents.add(descender)
                entries[r][cell] = {
                    'factor': factor,
                    'dropped': [dropped[0], dropped[1]],
                    'reverse': bool(reverse),
                    '_descender': descender,
                    '_ascender': ascender,
                }
                if fill(r + 1):
                    return True
                entries[r][cell] = None
                del first_use[factor]
                restore_roles()
            return False

        return fill(0)


def build_odd_case(team_count: int, players_per_team: int, rounds: int):
    factors = _odd_factorization(team_count)
    if factors is None:
        return None
    half = (team_count - 1) // 2
    cells = players_per_team // 2
    if rounds > 2 * half:
        return None
    options_by_factor = {
        i: _occurrence_options(team_count, factors, i) for i in range(half)
    }
    column_cap = 1 if rounds <= half else 2
    load = cells * rounds
    bound = 0 if load % half == 0 else 1
    best = None
    for salt in range(8):
        grid = build_grid(half, cells, rounds, salt, column_cap=column_cap)
        if grid is None:
            continue
        assigner = _RoleAssigner(team_count, cells, rounds, salt)
        occurrences = assigner.assign(grid, options_by_factor)
        if occurrences is None:
            continue
        schedule = {
            'kind': 'odd_cell_occurrences',
            'cells': [
                {key: value for key, value in entry.items() if not key.startswith('_')}
                for entry in occurrences
            ],
        }
        try:
            matches = recipes._materialize_matches(
                team_count, players_per_team, rounds, schedule
            )
        except Exception:
            continue
        coloured = colour_case(matches, team_count, players_per_team)
        if coloured is None:
            continue
        bits = recipes._colour_bits(matches, coloured)
        case = {
            'team_count': team_count,
            'players_per_team': players_per_team,
            'rounds': rounds,
            'candidate_label': 'grid_alternation_odd',
            'schedule': schedule,
            'colour_bit_count': len(bits),
            'colour_bits': recipes._pack_bits(bits),
        }
        try:
            table = recipes.materialize_recipe(case)
        except Exception:
            continue
        if not verify_molter_table(table).ok:
            continue
        metrics = recipes._metrics(table)
        priority = recipes._metric_priority(metrics)
        if best is None or priority < best[0]:
            best = (priority, case)
        if metrics.i1 <= bound and metrics.i1_prefix_deficit == 0 and metrics.i3 <= 1:
            break
    return best[1] if best else None


def build_case(team_count: int, players_per_team: int, rounds: int):
    if team_count % 2 == 0:
        return build_even_case(team_count, players_per_team, rounds)
    return build_odd_case(team_count, players_per_team, rounds)


# ---------- CLI ----------


def _grid_cases(args) -> list[tuple[int, int, int]]:
    cases = []
    for team_count in range(args.min_team_count, args.max_team_count + 1):
        for players in range(2, args.max_players + 1, 2):
            max_rounds = min(args.max_short_rounds, team_count - 1)
            rounds_list = list(range(1, max_rounds + 1))
            if args.include_full_tables and team_count - 1 > args.max_short_rounds:
                rounds_list.append(team_count - 1)
            for rounds in rounds_list:
                cases.append((team_count, players, rounds))
    return cases


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--case', action='append', default=[])
    parser.add_argument('--min-team-count', type=int, default=3)
    parser.add_argument('--max-team-count', type=int, default=25)
    parser.add_argument('--max-players', type=int, default=12)
    parser.add_argument('--max-short-rounds', type=int, default=13)
    parser.add_argument('--include-full-tables', action='store_true')
    parser.add_argument('--progress-every', type=int, default=25)
    args = parser.parse_args()

    if args.case:
        cases = [tuple(int(x) for x in spec.split(',')) for spec in args.case]
    else:
        cases = _grid_cases(args)

    built = []
    failed = []
    for index, (team_count, players, rounds) in enumerate(cases):
        case = build_case(team_count, players, rounds)
        if case is None:
            failed.append((team_count, players, rounds))
        else:
            built.append(case)
        if args.progress_every and index % args.progress_every == 0:
            print(f'... {index}/{len(cases)}', flush=True)

    payload = {
        'version': 1,
        'description': 'grid + alternation colouring recipe candidates',
        'cases': built,
    }
    args.output.write_text(json.dumps(payload))
    print(f'built {len(built)}/{len(cases)} cases -> {args.output}')
    if failed:
        print('failed:', failed)


if __name__ == '__main__':
    main()
