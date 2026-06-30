#!/usr/bin/env python3
"""Build and replay compact solver recipes for Molter tables.

This is a prototype for a different architecture:

* offline: CP-SAT searches for a better colourable schedule;
* stored data: only the schedule recipe plus one colour bit per board;
* runtime/replay: expand the recipe deterministically and emit a
  ``FixedPairingTable`` without running a solver.

The JSON produced here is resumable research/audit state. The adjacent ``.mrec``
file is the compact replay artifact; it is also not a cache of final pairings.
"""

from __future__ import annotations

import argparse
import base64
import json
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import UTC, datetime
from functools import lru_cache
from itertools import permutations
from math import perm
from pathlib import Path
from time import perf_counter
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
SRC_DIR = ROOT / 'src'
sys.path.insert(0, str(SRC_DIR))

from data.pairings.fixed_table import FixedPairingTable  # noqa: E402
from data.pairings.molter_verifier import verify_molter_table  # noqa: E402
from molter_recipe_generator import generate_molter_table  # noqa: E402
import molter_recipe_generator as mg  # noqa: E402

DEFAULT_OUTPUT = Path(__file__).resolve().parent / 'molter_solver_recipes.json'
BINARY_MAGIC_V1 = b'MLTRCP\x01'
BINARY_MAGIC = b'MLTRCP\x02'
SCHEDULE_KIND_IDS = {
    'odd_cell_drops': 1,
    'even_factor_rows': 2,
    'odd_cell_occurrences': 3,
}
SCHEDULE_KINDS_BY_ID = {value: key for key, value in SCHEDULE_KIND_IDS.items()}
DEFAULT_CASES = (
    (15, 4, 10),
    (19, 4, 8),
    (23, 6, 7),
    (29, 4, 6),
    (28, 12, 7),
    (34, 12, 7),
)
DEFAULT_GRID_PLAYERS = tuple(range(2, 13, 2))
DEFAULT_GRID_MIN_TEAM_COUNT = 3
DEFAULT_GRID_MAX_TEAM_COUNT = 25
DEFAULT_GRID_MAX_ROUNDS = 13
DEFAULT_GRID_INCLUDE_FULL_TABLES = False

Player = tuple[int, int]
Match = tuple[Player, Player]
Round = list[tuple[Player, Player]]


@dataclass(frozen=True)
class Metrics:
    i1: int
    i1_prefix_deficit: int
    i1_prefix_deficit_total: int
    i1_prefix_deficit_vector: tuple[int, ...]
    i2_l1: int
    i3: int
    i4: int
    i5: int
    exact_s5: bool


@dataclass(frozen=True)
class Candidate:
    label: str
    schedule: dict[str, Any]
    matches: list[list[Match]]
    coloured: list[Round] | None = None
    colour_status: str = 'integrated-colour:ok'
    colour_seconds: float = 0.0


def _letter(team_index: int) -> str:
    return chr(ord('A') + team_index)


def _seat(player: Player, players_per_team: int) -> int:
    return player[0] * players_per_team + player[1]


def _table_from_rounds(
    rounds: list[Round], team_count: int, players_per_team: int
) -> FixedPairingTable:
    return FixedPairingTable(
        team_count=team_count,
        players_per_team=players_per_team,
        rounds=tuple(mg._emit(rnd) for rnd in rounds),
    )


def _matches_from_table(table: FixedPairingTable) -> list[list[Match]]:
    out: list[list[Match]] = []
    for rnd in table.rounds:
        matches: list[Match] = []
        for pairing in rnd:
            white = (ord(pairing.white_team) - ord('A'), pairing.white_index - 1)
            black = (ord(pairing.black_team) - ord('A'), pairing.black_index - 1)
            matches.append((white, black))
        out.append(matches)
    return out


def _metrics(table: FixedPairingTable) -> Metrics:
    team_count = table.team_count
    players_per_team = table.players_per_team
    rounds = table.rounds
    index = {_letter(team): team for team in range(team_count)}
    round_pairs = (len(rounds) + 1) // 2
    pair = [[0] * team_count for _team in range(team_count)]
    prefix_mask = [0] * team_count
    down = [0] * team_count
    up = [0] * team_count
    rp_down = [[0] * team_count for _round_pair in range(round_pairs)]
    rp_up = [[0] * team_count for _round_pair in range(round_pairs)]
    exact_s5 = True
    prefix_deficit_total = 0
    prefix_deficit_vector: list[int] = []
    i5 = 0

    for r_index, rnd in enumerate(rounds):
        round_pair = r_index // 2
        round_team_white = [0] * team_count
        round_team_black = [0] * team_count
        round_opponents = [[0] * team_count for _team in range(team_count)]
        for pairing in rnd:
            white = index[pairing.white_team]
            black = index[pairing.black_team]
            pair[white][black] += 1
            pair[black][white] += 1
            round_opponents[white][black] += 1
            round_opponents[black][white] += 1
            prefix_mask[white] |= 1 << black
            prefix_mask[black] |= 1 << white
            round_team_white[white] += 1
            round_team_black[black] += 1
            if pairing.white_index != pairing.black_index:
                if pairing.white_index < pairing.black_index:
                    descend, ascend = white, black
                else:
                    descend, ascend = black, white
                down[descend] += 1
                up[ascend] += 1
                rp_down[round_pair][descend] += 1
                rp_up[round_pair][ascend] += 1

        expected_distinct = min(team_count - 1, players_per_team * (r_index + 1))
        round_max_prefix_deficit = 0
        for team in range(team_count):
            prefix_deficit = expected_distinct - prefix_mask[team].bit_count()
            prefix_deficit_total += prefix_deficit
            round_max_prefix_deficit = max(round_max_prefix_deficit, prefix_deficit)
            if r_index == 0 and team == 0:
                max_prefix_deficit = prefix_deficit
            else:
                max_prefix_deficit = max(max_prefix_deficit, prefix_deficit)
        prefix_deficit_vector.append(round_max_prefix_deficit)

        target = players_per_team // 2
        for team in range(team_count):
            counts = [
                round_opponents[team][opponent]
                for opponent in range(team_count)
                if round_opponents[team][opponent]
            ]
            if counts:
                i5 = max(i5, max(counts) - min(counts))
            if round_team_white[team] != target or round_team_black[team] != target:
                exact_s5 = False

    i1 = max(
        max(row[:team] + row[team + 1 :]) - min(row[:team] + row[team + 1 :])
        for team, row in enumerate(pair)
    )
    i2_l1 = sum(abs(up[team] - down[team]) for team in range(team_count))
    i3 = max(down) - min(down)
    i4 = max(
        (
            max(rp_down[round_pair][team], rp_up[round_pair][team])
            for round_pair in range(round_pairs)
            for team in range(team_count)
        ),
        default=0,
    )
    return Metrics(
        i1=i1,
        i1_prefix_deficit=max_prefix_deficit,
        i1_prefix_deficit_total=prefix_deficit_total,
        i1_prefix_deficit_vector=tuple(prefix_deficit_vector),
        i2_l1=i2_l1,
        i3=i3,
        i4=i4,
        i5=i5,
        exact_s5=exact_s5,
    )


def _metric_priority(
    metrics: Metrics,
) -> tuple[int, int, int, tuple[int, ...], int, int, int, int, int]:
    return (
        metrics.i1,
        metrics.i1_prefix_deficit,
        metrics.i1_prefix_deficit_total,
        metrics.i1_prefix_deficit_vector,
        metrics.i2_l1,
        metrics.i3,
        metrics.i4,
        metrics.i5,
        0 if metrics.exact_s5 else 1,
    )


def _metric_mapping_priority(
    metrics: dict[str, Any],
) -> tuple[int, int, int, tuple[int, ...], int, int, int, int, int]:
    return (
        int(metrics['i1']),
        int(metrics['i1_prefix_deficit']),
        int(metrics['i1_prefix_deficit_total']),
        tuple(int(value) for value in metrics['i1_prefix_deficit_vector']),
        int(metrics['i2_l1']),
        int(metrics['i3']),
        int(metrics['i4']),
        int(metrics['i5']),
        0 if bool(metrics.get('exact_s5')) else 1,
    )


def _metric_dict(metrics: Metrics) -> dict[str, Any]:
    return {
        'i1': metrics.i1,
        'i1_prefix_deficit': metrics.i1_prefix_deficit,
        'i1_prefix_deficit_total': metrics.i1_prefix_deficit_total,
        'i1_prefix_deficit_vector': list(metrics.i1_prefix_deficit_vector),
        'i2_l1': metrics.i2_l1,
        'i3': metrics.i3,
        'i4': metrics.i4,
        'i5': metrics.i5,
        'exact_s5': metrics.exact_s5,
    }


def _pack_bits(bits: list[bool]) -> str:
    return base64.b64encode(_pack_bit_bytes(bits)).decode('ascii')


def _pack_bit_bytes(bits: list[bool]) -> bytes:
    out = bytearray((len(bits) + 7) // 8)
    for index, bit in enumerate(bits):
        if bit:
            out[index // 8] |= 1 << (index % 8)
    return bytes(out)


def _unpack_bits(encoded: str, bit_count: int) -> list[bool]:
    raw = base64.b64decode(encoded.encode('ascii'))
    return [bool(raw[index // 8] & (1 << (index % 8))) for index in range(bit_count)]


def _write_varint(out: bytearray, value: int) -> None:
    if value < 0:
        raise ValueError(f'Cannot encode negative varint: {value}')
    while value >= 0x80:
        out.append((value & 0x7F) | 0x80)
        value >>= 7
    out.append(value)


def _read_varint(raw: bytes, offset: int) -> tuple[int, int]:
    shift = 0
    value = 0
    while True:
        if offset >= len(raw):
            raise ValueError('Unexpected end of packed recipe data.')
        byte = raw[offset]
        offset += 1
        value |= (byte & 0x7F) << shift
        if byte < 0x80:
            return value, offset
        shift += 7
        if shift > 63:
            raise ValueError('Packed recipe varint is too large.')


def _write_colour_payload(out: bytearray, case_recipe: dict[str, Any]) -> None:
    bit_count = int(case_recipe['colour_bit_count'])
    colour_bytes = base64.b64decode(case_recipe['colour_bits'].encode('ascii'))
    byte_count = (bit_count + 7) // 8
    if len(colour_bytes) != byte_count:
        raise ValueError(
            f'Colour bit payload has {len(colour_bytes)} bytes, expected {byte_count}.'
        )
    _write_varint(out, bit_count)
    out.extend(colour_bytes)


def _read_colour_payload(raw: bytes, offset: int) -> tuple[int, str, int]:
    bit_count, offset = _read_varint(raw, offset)
    byte_count = (bit_count + 7) // 8
    end = offset + byte_count
    if end > len(raw):
        raise ValueError('Packed recipe colour payload is truncated.')
    colour_bits = base64.b64encode(raw[offset:end]).decode('ascii')
    return bit_count, colour_bits, end


def _write_schedule(out: bytearray, schedule: dict[str, Any]) -> None:
    kind = schedule['kind']
    _write_varint(out, SCHEDULE_KIND_IDS[kind])
    if kind == 'odd_cell_drops':
        offsets = schedule['offsets']
        _write_varint(out, len(offsets))
        for offset in offsets:
            _write_varint(out, int(offset))
        cell_drops = schedule['cell_drops']
        _write_varint(out, len(cell_drops))
        for entry in cell_drops:
            _write_varint(out, int(entry['block']))
            _write_varint(out, int(entry['factor']))
            _write_varint(out, int(entry['dropped'][0]))
            _write_varint(out, int(entry['dropped'][1]))
        return
    if kind == 'odd_cell_occurrences':
        cells = schedule['cells']
        _write_varint(out, len(cells))
        for entry in cells:
            _write_varint(out, int(entry['factor']))
            _write_varint(out, int(entry['dropped'][0]))
            _write_varint(out, int(entry['dropped'][1]))
            _write_varint(out, 1 if entry['reverse'] else 0)
            _write_varint(out, int(entry.get('team_shift', 0)))
        return
    if kind == 'even_factor_rows':
        rows = schedule['rows']
        _write_varint(out, len(rows))
        row_width = len(rows[0]) if rows else 0
        _write_varint(out, row_width)
        for row in rows:
            if len(row) != row_width:
                raise ValueError('Packed even factor rows must be rectangular.')
            for factor_index in row:
                _write_varint(out, int(factor_index))
        return
    raise ValueError(f'Unsupported packed recipe schedule kind: {kind}')


def _read_schedule(
    raw: bytes, offset: int, *, packed_version: int
) -> tuple[dict[str, Any], int]:
    kind_id, offset = _read_varint(raw, offset)
    kind = SCHEDULE_KINDS_BY_ID.get(kind_id)
    if kind == 'odd_cell_drops':
        offset_count, offset = _read_varint(raw, offset)
        offsets: list[int] = []
        for _index in range(offset_count):
            value, offset = _read_varint(raw, offset)
            offsets.append(value)
        drop_count, offset = _read_varint(raw, offset)
        cell_drops: list[dict[str, Any]] = []
        for _index in range(drop_count):
            block, offset = _read_varint(raw, offset)
            factor, offset = _read_varint(raw, offset)
            dropped_first, offset = _read_varint(raw, offset)
            dropped_second, offset = _read_varint(raw, offset)
            cell_drops.append(
                {
                    'block': block,
                    'factor': factor,
                    'dropped': [dropped_first, dropped_second],
                }
            )
        return {'kind': kind, 'offsets': offsets, 'cell_drops': cell_drops}, offset
    if kind == 'odd_cell_occurrences':
        cell_count, offset = _read_varint(raw, offset)
        cells: list[dict[str, Any]] = []
        for _index in range(cell_count):
            factor, offset = _read_varint(raw, offset)
            dropped_first, offset = _read_varint(raw, offset)
            dropped_second, offset = _read_varint(raw, offset)
            reverse, offset = _read_varint(raw, offset)
            if packed_version >= 2:
                team_shift, offset = _read_varint(raw, offset)
            else:
                team_shift = 0
            cells.append(
                {
                    'factor': factor,
                    'dropped': [dropped_first, dropped_second],
                    'reverse': bool(reverse),
                    'team_shift': team_shift,
                }
            )
        return {'kind': kind, 'cells': cells}, offset
    if kind == 'even_factor_rows':
        row_count, offset = _read_varint(raw, offset)
        row_width, offset = _read_varint(raw, offset)
        rows: list[list[int]] = []
        for _row_index in range(row_count):
            row: list[int] = []
            for _slot in range(row_width):
                factor_index, offset = _read_varint(raw, offset)
                row.append(factor_index)
            rows.append(row)
        return {'kind': kind, 'rows': rows}, offset
    raise ValueError(f'Unsupported packed recipe schedule kind id: {kind_id}')


def _pack_recipe_payload(payload: dict[str, Any]) -> bytes:
    out = bytearray(BINARY_MAGIC)
    cases = payload.get('cases', [])
    _write_varint(out, len(cases))
    for case in cases:
        _write_varint(out, int(case['team_count']))
        _write_varint(out, int(case['players_per_team']))
        _write_varint(out, int(case['rounds']))
        _write_schedule(out, case['schedule'])
        _write_colour_payload(out, case)
    return bytes(out)


def _unpack_recipe_payload(raw: bytes) -> dict[str, Any]:
    if raw.startswith(BINARY_MAGIC):
        packed_version = 2
        offset = len(BINARY_MAGIC)
    elif raw.startswith(BINARY_MAGIC_V1):
        packed_version = 1
        offset = len(BINARY_MAGIC_V1)
    else:
        raise ValueError('Not a packed Molter recipe file.')
    case_count, offset = _read_varint(raw, offset)
    cases: list[dict[str, Any]] = []
    for _case_index in range(case_count):
        team_count, offset = _read_varint(raw, offset)
        players_per_team, offset = _read_varint(raw, offset)
        rounds, offset = _read_varint(raw, offset)
        schedule, offset = _read_schedule(raw, offset, packed_version=packed_version)
        colour_bit_count, colour_bits, offset = _read_colour_payload(raw, offset)
        cases.append(
            {
                'team_count': team_count,
                'players_per_team': players_per_team,
                'rounds': rounds,
                'schedule': schedule,
                'colour_bit_count': colour_bit_count,
                'colour_bits': colour_bits,
            }
        )
    if offset != len(raw):
        raise ValueError('Packed Molter recipe file has trailing bytes.')
    return {
        'version': packed_version,
        'description': 'Packed Molter solver recipes.',
        'cases': cases,
        'misses': [],
    }


def _colour_bits(matches: list[list[Match]], rounds: list[Round]) -> list[bool]:
    bits: list[bool] = []
    for match_round, coloured_round in zip(matches, rounds, strict=True):
        oriented = set(coloured_round)
        for first, second in match_round:
            bits.append((first, second) in oriented)
    return bits


def _apply_colour_bits(matches: list[list[Match]], bits: list[bool]) -> list[Round]:
    out: list[Round] = []
    cursor = 0
    for rnd in matches:
        coloured: Round = []
        for first, second in rnd:
            coloured.append((first, second) if bits[cursor] else (second, first))
            cursor += 1
        out.append(coloured)
    return out


def _shift_match(match: Match, team_count: int, shift: int) -> Match:
    if shift % team_count == 0:
        return match
    return (
        ((match[0][0] + shift) % team_count, match[0][1]),
        ((match[1][0] + shift) % team_count, match[1][1]),
    )


def _shift_matches(matches: list[Match], team_count: int, shift: int) -> list[Match]:
    return [_shift_match(match, team_count, shift) for match in matches]


def _normalised_match(match: Match) -> tuple[Player, Player]:
    first, second = match
    return (first, second) if first <= second else (second, first)


def _normalised_match_set(matches: list[Match]) -> frozenset[tuple[Player, Player]]:
    return frozenset(_normalised_match(match) for match in matches)


def _materialize_matches(
    team_count: int, players_per_team: int, rounds: int, schedule: dict[str, Any]
) -> list[list[Match]]:
    kind = schedule['kind']
    if kind == 'odd_cell_drops':
        factors = mg._one_odd_factorization(
            team_count
        ) or mg._small_one_odd_factorization(team_count)
        if factors is None:
            raise ValueError(f'No one-odd factorization for {team_count} teams.')
        offsets = tuple(schedule['offsets'])
        drops = {
            (entry['block'], entry['factor']): tuple(entry['dropped'])
            for entry in schedule['cell_drops']
        }
        seen: dict[tuple[int, int], int] = {}
        out: list[list[Match]] = []
        half = (team_count - 1) // 2
        for round_index in range(rounds):
            rnd: list[Match] = []
            for block, offset in enumerate(offsets):
                factor_index = (round_index + offset) % half
                key = (block, factor_index)
                phase = seen.get(key, 0)
                seen[key] = phase + 1
                odd_slot = 2 * block
                even_slot = odd_slot + 1
                rnd.extend(
                    mg._one_odd_cell_matches(
                        team_count,
                        factors[factor_index],
                        drops[key],
                        odd_slot,
                        even_slot,
                        phase % 2 == 1,
                    )
                )
            out.append(rnd)
        return out
    if kind == 'odd_cell_occurrences':
        factors = mg._one_odd_factorization(
            team_count
        ) or mg._small_one_odd_factorization(team_count)
        if factors is None:
            raise ValueError(f'No one-odd factorization for {team_count} teams.')
        block_count = players_per_team // 2
        cells = schedule['cells']
        expected_cells = rounds * block_count
        if len(cells) != expected_cells:
            raise ValueError(
                f'Odd occurrence recipe has {len(cells)} cells, expected '
                f'{expected_cells}.'
            )
        out: list[list[Match]] = []
        cursor = 0
        for _round_index in range(rounds):
            rnd: list[Match] = []
            for block in range(block_count):
                entry = cells[cursor]
                cursor += 1
                cell_matches = mg._one_odd_cell_matches(
                    team_count,
                    factors[int(entry['factor'])],
                    tuple(entry['dropped']),
                    2 * block,
                    2 * block + 1,
                    bool(entry['reverse']),
                )
                rnd.extend(
                    _shift_matches(
                        cell_matches, team_count, int(entry.get('team_shift', 0))
                    )
                )
            out.append(rnd)
        return out
    if kind == 'even_factor_rows':
        rows = tuple(tuple(row) for row in schedule['rows'])
        return mg._even_matches_from_factor_rows(team_count, rows)
    if kind == 'current_generator':
        return _matches_from_table(
            generate_molter_table(team_count, players_per_team, rounds)
        )
    raise ValueError(f'Unsupported recipe schedule kind: {kind}')


def _infer_even_factor_row_schedule(
    team_count: int, players_per_team: int, matches: list[list[Match]]
) -> dict[str, Any]:
    factors = mg._one_factorization(team_count)
    factor_by_edges = {
        frozenset(mg._team_edge(first, second) for first, second in factor): index
        for index, factor in enumerate(factors)
    }
    rows: list[list[int]] = []
    for round_index, rnd in enumerate(matches):
        row: list[int] = []
        for slot in range(players_per_team):
            edges = frozenset(
                mg._team_edge(first[0], second[0])
                for first, second in rnd
                if first[1] == slot and second[1] == slot
            )
            factor_index = factor_by_edges.get(edges)
            if factor_index is None:
                raise ValueError(
                    f'Cannot infer even factor row for round {round_index + 1}, '
                    f'slot {slot + 1}.'
                )
            row.append(factor_index)
        rows.append(row)
    return {'kind': 'even_factor_rows', 'rows': rows}


@lru_cache(maxsize=None)
def _odd_cell_lookup(
    team_count: int,
    factors: tuple[tuple[tuple[int, int], ...], ...],
    block: int,
) -> dict[frozenset[tuple[Player, Player]], dict[str, Any]]:
    factor_edges = mg._one_odd_factor_odd_edges(team_count, factors)
    odd_slot = 2 * block
    even_slot = odd_slot + 1
    lookup: dict[frozenset[tuple[Player, Player]], dict[str, Any]] = {}
    scored_entries: list[
        tuple[
            tuple[int, int, int, int, int],
            frozenset[tuple[Player, Player]],
            dict[str, Any],
        ]
    ] = []
    for team_shift in range(team_count):
        for factor_index, factor in enumerate(factors):
            directed_edges = [
                directed
                for edge in factor_edges[factor_index]
                for directed in (edge, (edge[1], edge[0]))
            ]
            for dropped in directed_edges:
                for reverse in (False, True):
                    cell_matches = mg._one_odd_cell_matches(
                        team_count,
                        factor,
                        dropped,
                        odd_slot,
                        even_slot,
                        reverse,
                    )
                    shifted = _shift_matches(cell_matches, team_count, team_shift)
                    key = _normalised_match_set(shifted)
                    entry = {
                        'factor': factor_index,
                        'dropped': list(dropped),
                        'reverse': reverse,
                    }
                    if team_shift:
                        entry['team_shift'] = team_shift
                    scored_entries.append(
                        (
                            (
                                team_shift,
                                factor_index,
                                dropped[0],
                                dropped[1],
                                1 if reverse else 0,
                            ),
                            key,
                            entry,
                        )
                    )
    for _score, key, entry in sorted(scored_entries, key=lambda item: item[0]):
        lookup.setdefault(key, entry)
    return lookup


def _infer_odd_occurrence_schedule(
    team_count: int, players_per_team: int, matches: list[list[Match]]
) -> dict[str, Any]:
    factors = mg._one_odd_factorization(team_count) or mg._small_one_odd_factorization(
        team_count
    )
    if factors is None:
        raise ValueError(f'No one-odd factorization for {team_count} teams.')
    block_count = players_per_team // 2
    lookups = [
        _odd_cell_lookup(team_count, factors, block) for block in range(block_count)
    ]
    cells: list[dict[str, Any]] = []
    for round_index, rnd in enumerate(matches):
        for block, lookup in enumerate(lookups):
            slots = {2 * block, 2 * block + 1}
            cell_matches = [
                match for match in rnd if match[0][1] in slots and match[1][1] in slots
            ]
            if len(cell_matches) != team_count:
                raise ValueError(
                    f'Cannot infer odd cell for round {round_index + 1}, '
                    f'block {block + 1}: expected {team_count} matches, '
                    f'got {len(cell_matches)}.'
                )
            entry = lookup.get(_normalised_match_set(cell_matches))
            if entry is None:
                raise ValueError(
                    f'Cannot infer odd cell recipe for round {round_index + 1}, '
                    f'block {block + 1}.'
                )
            cells.append(dict(entry))
    return {'kind': 'odd_cell_occurrences', 'cells': cells}


def _infer_schedule_from_table(table: FixedPairingTable) -> dict[str, Any]:
    matches = _matches_from_table(table)
    if table.team_count % 2 == 0:
        return _infer_even_factor_row_schedule(
            table.team_count, table.players_per_team, matches
        )
    return _infer_odd_occurrence_schedule(
        table.team_count, table.players_per_team, matches
    )


def _baseline_candidate_from_table(table: FixedPairingTable) -> Candidate:
    schedule = _infer_schedule_from_table(table)
    matches = _materialize_matches(
        table.team_count, table.players_per_team, len(table.rounds), schedule
    )
    if [_normalised_match_set(rnd) for rnd in matches] != [
        _normalised_match_set(rnd) for rnd in _matches_from_table(table)
    ]:
        raise ValueError(
            f'Inferred baseline recipe does not replay {table.team_count}x'
            f'{table.players_per_team} R{len(table.rounds)}.'
        )
    return Candidate(
        'baseline_current_generator_inferred',
        schedule,
        matches,
        coloured=_matches_from_table(table),
        colour_status='baseline-current-generator:inferred',
        colour_seconds=0.0,
    )


def materialize_recipe(case_recipe: dict[str, Any]) -> FixedPairingTable:
    team_count = int(case_recipe['team_count'])
    players_per_team = int(case_recipe['players_per_team'])
    rounds = int(case_recipe['rounds'])
    matches = _materialize_matches(
        team_count, players_per_team, rounds, case_recipe['schedule']
    )
    bit_count = sum(len(rnd) for rnd in matches)
    bits = _unpack_bits(case_recipe['colour_bits'], bit_count)
    return _table_from_rounds(
        _apply_colour_bits(matches, bits), team_count, players_per_team
    )


def _match_prefix_deficit_stats(
    matches: list[list[Match]], team_count: int, players_per_team: int
) -> tuple[int, int, tuple[int, ...]]:
    seen_masks = [0] * team_count
    max_deficit = 0
    total_deficit = 0
    vector: list[int] = []
    for round_index, rnd in enumerate(matches, start=1):
        for first, second in rnd:
            seen_masks[first[0]] |= 1 << second[0]
            seen_masks[second[0]] |= 1 << first[0]
        expected_distinct = min(team_count - 1, players_per_team * round_index)
        round_max = 0
        for mask in seen_masks:
            deficit = expected_distinct - mask.bit_count()
            total_deficit += deficit
            round_max = max(round_max, deficit)
        max_deficit = max(max_deficit, round_max)
        vector.append(round_max)
    return max_deficit, total_deficit, tuple(vector)


def _raw_priority(matches: list[list[Match]], team_count: int, players_per_team: int):
    score = mg._match_prefix_spread_score(matches, team_count, players_per_team)
    prefix_deficit, prefix_total, prefix_vector = _match_prefix_deficit_stats(
        matches, team_count, players_per_team
    )
    return score[2], prefix_deficit, prefix_total, prefix_vector, score[3], score[5]


def _one_odd_spread_offset_candidates(
    team_count: int,
    block_count: int,
    rounds: int,
    *,
    limit: int,
    max_permutations: int,
) -> tuple[tuple[int, ...], ...]:
    """Return explicit odd-block offset patterns for recipe search.

    The portable generator keeps this list small. The offline recipe builder can
    afford a wider, deterministic portfolio for large odd partial tables, where
    prefix quality is otherwise the main D-case failure mode.
    """
    if limit <= 0:
        return mg._one_odd_spread_offset_candidates(team_count, block_count, rounds)

    primary = mg._one_odd_partial_offsets(team_count, block_count)
    half = (team_count - 1) // 2
    if block_count <= 0 or block_count > half:
        return (primary,)

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

    out: list[tuple[int, ...]] = [primary]
    seen = {primary}
    permutation_count = perm(half, block_count)
    if permutation_count <= max_permutations:
        scored = [
            (factor_prefix_score(offsets), offsets != primary, offsets)
            for offsets in permutations(range(half), block_count)
        ]
        scored.sort()
        for _score, _not_primary, offsets in scored:
            if offsets in seen:
                continue
            out.append(offsets)
            seen.add(offsets)
            if len(out) >= limit:
                break
        return tuple(out)

    # Fallback for future larger grids: use evenly spaced rotations and strides
    # instead of enumerating a factorial space.
    for stride in range(1, half):
        if len({(index * stride) % half for index in range(half)}) != half:
            continue
        for start in range(half):
            offsets = tuple(
                (start + index * stride) % half for index in range(block_count)
            )
            if offsets in seen:
                continue
            out.append(offsets)
            seen.add(offsets)
            if len(out) >= limit:
                return tuple(
                    sorted(
                        out,
                        key=lambda offsets: (
                            factor_prefix_score(offsets),
                            offsets != primary,
                            offsets,
                        ),
                    )
                )
    return tuple(
        sorted(
            out,
            key=lambda offsets: (
                factor_prefix_score(offsets),
                offsets != primary,
                offsets,
            ),
        )
    )


def _metrics_raw_priority(
    metrics: Metrics,
) -> tuple[int, int, int, tuple[int, ...], int, int]:
    return (
        metrics.i1,
        metrics.i1_prefix_deficit,
        metrics.i1_prefix_deficit_total,
        metrics.i1_prefix_deficit_vector,
        metrics.i2_l1,
        metrics.i3,
    )


def _odd_cp_sat_factor_row_candidates(
    factor_count: int,
    block_count: int,
    rounds: int,
    *,
    timeout_seconds: float,
    workers: int,
    attempts: int,
) -> tuple[tuple[tuple[int, ...], ...], ...]:
    if timeout_seconds <= 0 or attempts <= 0:
        return ()

    from ortools.sat.python import cp_model

    model = cp_model.CpModel()
    variables: dict[tuple[int, int, int], Any] = {}
    for round_index in range(rounds):
        for block in range(block_count):
            for factor in range(factor_count):
                variables[(round_index, block, factor)] = model.NewBoolVar(
                    f'x_{round_index}_{block}_{factor}'
                )

    for round_index in range(rounds):
        for block in range(block_count):
            model.Add(
                sum(
                    variables[(round_index, block, factor)]
                    for factor in range(factor_count)
                )
                == 1
            )
        for factor in range(factor_count):
            model.Add(
                sum(
                    variables[(round_index, block, factor)]
                    for block in range(block_count)
                )
                <= 1
            )

    for block in range(block_count):
        for factor in range(factor_count):
            model.Add(
                sum(
                    variables[(round_index, block, factor)]
                    for round_index in range(rounds)
                )
                <= 2
            )

    total = rounds * block_count
    low = total // factor_count
    high = (total + factor_count - 1) // factor_count
    for factor in range(factor_count):
        count = sum(
            variables[(round_index, block, factor)]
            for round_index in range(rounds)
            for block in range(block_count)
        )
        model.Add(count >= low)
        model.Add(count <= high)

    for prefix in range(1, rounds + 1):
        expected_distinct = min(factor_count, block_count * prefix)
        for factor in range(factor_count):
            count = sum(
                variables[(round_index, block, factor)]
                for round_index in range(prefix)
                for block in range(block_count)
            )
            if expected_distinct == block_count * prefix:
                model.Add(count <= 1)
            if expected_distinct == factor_count:
                model.Add(count >= 1)

    out: list[tuple[tuple[int, ...], ...]] = []
    seen: set[tuple[tuple[int, ...], ...]] = set()
    for attempt in range(attempts):
        solver = cp_model.CpSolver()
        solver.parameters.max_time_in_seconds = timeout_seconds
        solver.parameters.num_search_workers = workers
        solver.parameters.random_seed = attempt + 1
        status = solver.Solve(model)
        if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            break

        rows: list[tuple[int, ...]] = []
        chosen_literals = []
        for round_index in range(rounds):
            row: list[int] = []
            for block in range(block_count):
                for factor in range(factor_count):
                    literal = variables[(round_index, block, factor)]
                    if solver.Value(literal):
                        row.append(factor)
                        chosen_literals.append(literal)
                        break
            rows.append(tuple(row))
        candidate = tuple(rows)
        model.Add(sum(chosen_literals) <= len(chosen_literals) - 1)
        if candidate in seen:
            continue
        seen.add(candidate)
        out.append(candidate)
    return tuple(out)


def _odd_cell_option(
    team_count: int,
    players_per_team: int,
    factors: tuple[tuple[tuple[int, int], ...], ...],
    factor_index: int,
    block: int,
    dropped: tuple[int, int],
    reverse: bool,
) -> tuple[list[Match], int, int]:
    odd_slot = 2 * block
    even_slot = odd_slot + 1
    matches = mg._one_odd_cell_matches(
        team_count,
        factors[factor_index],
        dropped,
        odd_slot,
        even_slot,
        reverse,
    )
    down, up = dropped if reverse else (dropped[1], dropped[0])
    return matches, down, up


def _odd_occurrence_schedule_from_factor_rows(
    team_count: int,
    players_per_team: int,
    factor_rows: tuple[tuple[int, ...], ...],
    factors: tuple[tuple[tuple[int, int], ...], ...],
    *,
    salt: int,
    search_passes: int,
) -> dict[str, Any] | None:
    factor_edges = mg._one_odd_factor_odd_edges(team_count, factors)
    cells = [
        (round_index, block, factor_index)
        for round_index, row in enumerate(factor_rows)
        for block, factor_index in enumerate(row)
    ]
    options_by_cell: list[
        list[tuple[tuple[int, int], bool, list[Match], int, int]]
    ] = []
    for round_index, block, factor_index in cells:
        options = []
        for edge in factor_edges[factor_index]:
            for dropped in (edge, (edge[1], edge[0])):
                for reverse in (False, True):
                    matches, down, up = _odd_cell_option(
                        team_count,
                        players_per_team,
                        factors,
                        factor_index,
                        block,
                        dropped,
                        reverse,
                    )
                    options.append((dropped, reverse, matches, down, up))
        options.sort(
            key=lambda option: (
                (option[0][0] * 1_000_003)
                ^ (option[0][1] * 9_176)
                ^ (round_index * 8_191)
                ^ (block * 131)
                ^ (salt * 2_654_435_761)
                ^ (1 if option[1] else 0)
            )
        )
        options = options[:16]
        options_by_cell.append(options)

    choices = [
        (salt + cell_index) % len(options)
        for cell_index, options in enumerate(options_by_cell)
    ]

    def score_choices() -> tuple[
        int,
        int,
        int,
        int,
        int,
        int,
        tuple[int, ...],
        tuple[int, ...],
    ]:
        seat_count = team_count * players_per_team
        opponent_masks = [0] * seat_count
        seat_down = [0] * seat_count
        seat_up = [0] * seat_count
        down_counts = [0] * team_count
        up_counts = [0] * team_count
        round_pairs = (len(factor_rows) + 1) // 2
        rp_down = [[0] * team_count for _round_pair in range(round_pairs)]
        rp_up = [[0] * team_count for _round_pair in range(round_pairs)]
        opponent_repeat_excess = 0
        for cell_index, choice in enumerate(choices):
            round_index, block, _factor_index = cells[cell_index]
            _dropped, _reverse, matches, down, up = options_by_cell[cell_index][choice]
            for first, second in matches:
                for player, opponent_team in ((first, second[0]), (second, first[0])):
                    seat = _seat(player, players_per_team)
                    bit = 1 << opponent_team
                    if opponent_masks[seat] & bit:
                        opponent_repeat_excess += 1
                    opponent_masks[seat] |= bit
            down_seat = down * players_per_team + 2 * block
            up_seat = up * players_per_team + 2 * block + 1
            seat_down[down_seat] += 1
            seat_up[up_seat] += 1
            down_counts[down] += 1
            up_counts[up] += 1
            round_pair = round_index // 2
            rp_down[round_pair][down] += 1
            rp_up[round_pair][up] += 1

        s6c_excess = sum(max(0, count - 1) for count in seat_down) + sum(
            max(0, count - 1) for count in seat_up
        )
        i4_excess = sum(
            max(0, count - 1) for row in (*rp_down, *rp_up) for count in row
        )
        i2_l1, _i2_max_abs, i3_spread, i3_max_down, i3_square_sum, diffs, down = (
            mg._floater_balance_score(down_counts, up_counts)
        )
        return (
            opponent_repeat_excess,
            s6c_excess,
            i2_l1,
            i3_spread,
            i3_max_down,
            i3_square_sum + i4_excess,
            diffs,
            down,
        )

    best_score = score_choices()
    for _pass in range(search_passes):
        improved = False
        for cell_index, options in enumerate(options_by_cell):
            old_choice = choices[cell_index]
            cell_best_score = best_score
            cell_best_choice = old_choice
            for option_index in range(len(options)):
                if option_index == old_choice:
                    continue
                choices[cell_index] = option_index
                option_score = score_choices()
                if option_score < cell_best_score:
                    cell_best_score = option_score
                    cell_best_choice = option_index
            choices[cell_index] = cell_best_choice
            if cell_best_score < best_score:
                best_score = cell_best_score
                improved = True
        if not improved:
            break

    if best_score[0] or best_score[1]:
        return None

    schedule_cells = []
    for cell_index, choice in enumerate(choices):
        _round_index, _block, factor_index = cells[cell_index]
        dropped, reverse, _matches, _down, _up = options_by_cell[cell_index][choice]
        schedule_cells.append(
            {
                'factor': factor_index,
                'dropped': list(dropped),
                'reverse': reverse,
            }
        )
    return {'kind': 'odd_cell_occurrences', 'cells': schedule_cells}


def _odd_cp_sat_occurrence_schedule_from_factor_rows(
    team_count: int,
    players_per_team: int,
    factor_rows: tuple[tuple[int, ...], ...],
    factors: tuple[tuple[tuple[int, int], ...], ...],
    *,
    timeout_seconds: float,
    workers: int,
    seed: int,
) -> dict[str, Any] | None:
    if timeout_seconds <= 0:
        return None

    from ortools.sat.python import cp_model

    factor_edges = mg._one_odd_factor_odd_edges(team_count, factors)
    cells = [
        (round_index, block, factor_index)
        for round_index, row in enumerate(factor_rows)
        for block, factor_index in enumerate(row)
    ]
    options_by_cell: list[list[dict[str, Any]]] = []
    for round_index, block, factor_index in cells:
        options = []
        for edge in factor_edges[factor_index]:
            for dropped in (edge, (edge[1], edge[0])):
                for reverse in (False, True):
                    matches, down, up = _odd_cell_option(
                        team_count,
                        players_per_team,
                        factors,
                        factor_index,
                        block,
                        dropped,
                        reverse,
                    )
                    opponent_keys = []
                    for first, second in matches:
                        opponent_keys.append(
                            (_seat(first, players_per_team), second[0])
                        )
                        opponent_keys.append(
                            (_seat(second, players_per_team), first[0])
                        )
                    options.append(
                        {
                            'factor': factor_index,
                            'dropped': dropped,
                            'reverse': reverse,
                            'down': down,
                            'up': up,
                            'down_seat': down * players_per_team + 2 * block,
                            'up_seat': up * players_per_team + 2 * block + 1,
                            'opponent_keys': tuple(opponent_keys),
                            'tie': (
                                (dropped[0] * 1_000_003)
                                ^ (dropped[1] * 9_176)
                                ^ (round_index * 8_191)
                                ^ (block * 131)
                                ^ (seed * 2_654_435_761)
                                ^ (1 if reverse else 0)
                            )
                            & 0xFFFFFFFF,
                        }
                    )
        options.sort(key=lambda option: option['tie'])
        options_by_cell.append(options)

    model = cp_model.CpModel()
    variables: dict[tuple[int, int], Any] = {}
    by_opponent: dict[tuple[int, int], list[Any]] = {}
    by_down_seat: dict[int, list[Any]] = {}
    by_up_seat: dict[int, list[Any]] = {}
    down_by_team: list[list[Any]] = [[] for _team in range(team_count)]
    up_by_team: list[list[Any]] = [[] for _team in range(team_count)]
    objective_terms: list[Any] = []
    for cell_index, options in enumerate(options_by_cell):
        cell_variables = []
        for option_index, option in enumerate(options):
            variable = model.NewBoolVar(f'd_{cell_index}_{option_index}')
            variables[(cell_index, option_index)] = variable
            cell_variables.append(variable)
            for key in option['opponent_keys']:
                by_opponent.setdefault(key, []).append(variable)
            by_down_seat.setdefault(option['down_seat'], []).append(variable)
            by_up_seat.setdefault(option['up_seat'], []).append(variable)
            down_by_team[option['down']].append(variable)
            up_by_team[option['up']].append(variable)
            objective_terms.append(option['tie'] % 997 * variable)
        model.Add(sum(cell_variables) == 1)

    for variables_for_key in by_opponent.values():
        model.Add(sum(variables_for_key) <= 1)
    for variables_for_key in by_down_seat.values():
        model.Add(sum(variables_for_key) <= 1)
    for variables_for_key in by_up_seat.values():
        model.Add(sum(variables_for_key) <= 1)

    abs_diffs = []
    for team in range(team_count):
        diff = model.NewIntVar(-len(cells), len(cells), f'i3_{team}')
        model.Add(diff == sum(down_by_team[team]) - sum(up_by_team[team]))
        abs_diff = model.NewIntVar(0, len(cells), f'abs_i3_{team}')
        model.AddAbsEquality(abs_diff, diff)
        abs_diffs.append(abs_diff)
    model.Minimize(sum(abs_diffs) * 1_000_000 + sum(objective_terms))

    block_count = len(factor_rows[0]) if factor_rows else 0
    deadline = perf_counter() + timeout_seconds
    solve_index = 0
    while perf_counter() < deadline and solve_index < 32:
        solver = cp_model.CpSolver()
        solver.parameters.max_time_in_seconds = max(0.1, deadline - perf_counter())
        solver.parameters.num_search_workers = workers
        solver.parameters.random_seed = seed + solve_index + 1
        solver.parameters.randomize_search = True
        status = solver.Solve(model)
        if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            if status == cp_model.MODEL_INVALID:
                raise ValueError(model.Validate())
            return None

        selected: list[int] = []
        schedule_cells = []
        for cell_index, options in enumerate(options_by_cell):
            selected_option = -1
            for option_index, option in enumerate(options):
                if solver.Value(variables[(cell_index, option_index)]):
                    selected_option = option_index
                    schedule_cells.append(
                        {
                            'factor': option['factor'],
                            'dropped': list(option['dropped']),
                            'reverse': option['reverse'],
                        }
                    )
                    break
            if selected_option < 0:
                raise ValueError('Dropped-edge CP returned an incomplete solution.')
            selected.append(selected_option)

        schedule = {'kind': 'odd_cell_occurrences', 'cells': schedule_cells}
        matches = _materialize_matches(
            team_count, players_per_team, len(factor_rows), schedule
        )
        if (
            mg._colour_with_relaxed_team_balance(matches, team_count, players_per_team)
            is not None
        ):
            return schedule

        failed_groups: list[list[int]] = []
        for first_round in range(0, len(matches) - 1, 2):
            if (
                mg._pair_flip_colour_relaxed_s5(
                    matches[first_round],
                    matches[first_round + 1],
                    team_count,
                    players_per_team,
                )
                is not None
            ):
                continue
            start = first_round * block_count
            failed_groups.append(list(range(start, start + 2 * block_count)))
        if not failed_groups:
            failed_groups.append(list(range(len(cells))))
        for group in failed_groups:
            model.Add(
                sum(
                    variables[(cell_index, selected[cell_index])]
                    for cell_index in group
                )
                <= len(group) - 1
            )
        solve_index += 1
    return None


def _odd_integrated_cp_sat_occurrence_schedule(
    team_count: int,
    players_per_team: int,
    rounds: int,
    factors: tuple[tuple[tuple[int, int], ...], ...],
    *,
    timeout_seconds: float,
    workers: int,
    seed: int,
    options_per_factor: int,
) -> dict[str, Any] | None:
    if timeout_seconds <= 0 or options_per_factor <= 0:
        return None

    from ortools.sat.python import cp_model

    factor_count = (team_count - 1) // 2
    block_count = players_per_team // 2
    factor_edges = mg._one_odd_factor_odd_edges(team_count, factors)
    offsets = mg._one_odd_partial_offsets(team_count, block_count)
    fast_plan_result = mg._one_odd_fast_partial_plan(
        team_count,
        rounds,
        block_count,
        tuple(0 for _team in range(team_count)),
        factors,
        initial_up_counts=tuple(0 for _team in range(team_count)),
    )
    fast_plan = fast_plan_result[0] if fast_plan_result is not None else None
    hinted_rounds: list[Round] | None = None
    hinted_white_by_round_pair: list[dict[frozenset[Player], Player]] = [
        {} for _round in range(rounds)
    ]
    if fast_plan is not None:
        hinted_matches = mg._complete_i1_one_odd_plan_blocks(
            team_count, rounds, 0, fast_plan, factors
        )
        hinted_rounds = mg._colour_with_relaxed_team_balance(
            hinted_matches, team_count, players_per_team
        )
        if hinted_rounds is not None:
            for round_index, rnd in enumerate(hinted_rounds):
                for white, black in rnd:
                    hinted_white_by_round_pair[round_index][
                        frozenset((white, black))
                    ] = white

    def preferred_dropped_edges(
        round_index: int, factor_index: int, block: int
    ) -> set[tuple[int, int]]:
        preferred: set[tuple[int, int]] = set()
        if fast_plan is not None:
            planned_factor, planned_dropped = fast_plan[round_index // 2][block]
            if planned_factor == factor_index:
                preferred.add(planned_dropped)
                preferred.add((planned_dropped[1], planned_dropped[0]))
        offset = offsets[block]
        first_round = (factor_index - offset) % factor_count
        dropped = mg._affine_floater_edge(team_count, first_round, offset)
        if dropped not in factors[factor_index]:
            incident = sorted(edge for edge in factors[factor_index] if 0 in edge)
            edge = incident[0]
            dropped = edge if edge[0] == 0 else (edge[1], edge[0])
        preferred.add(dropped)
        preferred.add((dropped[1], dropped[0]))
        return preferred

    cells = [
        (round_index, block)
        for round_index in range(rounds)
        for block in range(block_count)
    ]
    options_by_cell: list[list[dict[str, Any]]] = []
    for round_index, block in cells:
        options = []
        for factor_index in range(factor_count):
            factor_options = []
            for edge in factor_edges[factor_index]:
                for dropped in (edge, (edge[1], edge[0])):
                    for reverse in (False, True):
                        matches, down, up = _odd_cell_option(
                            team_count,
                            players_per_team,
                            factors,
                            factor_index,
                            block,
                            dropped,
                            reverse,
                        )
                        opponent_keys = []
                        team_pair_keys = []
                        for first, second in matches:
                            opponent_keys.append(
                                (_seat(first, players_per_team), second[0])
                            )
                            opponent_keys.append(
                                (_seat(second, players_per_team), first[0])
                            )
                            team_pair_keys.append(tuple(sorted((first[0], second[0]))))
                        tie = (
                            (dropped[0] * 1_000_003)
                            ^ (dropped[1] * 9_176)
                            ^ (factor_index * 65_537)
                            ^ (round_index * 8_191)
                            ^ (block * 131)
                            ^ (seed * 2_654_435_761)
                            ^ (1 if reverse else 0)
                        ) & 0xFFFFFFFF
                        factor_options.append(
                            {
                                'factor': factor_index,
                                'dropped': dropped,
                                'reverse': reverse,
                                'down': down,
                                'up': up,
                                'down_seat': down * players_per_team + 2 * block,
                                'up_seat': up * players_per_team + 2 * block + 1,
                                'opponent_keys': tuple(opponent_keys),
                                'team_pair_keys': tuple(team_pair_keys),
                                'tie': tie,
                            }
                        )
            factor_options.sort(key=lambda option: option['tie'])
            preferred = preferred_dropped_edges(round_index, factor_index, block)
            selected: list[dict[str, Any]] = []
            seen_option_keys: set[tuple[tuple[int, int], bool]] = set()
            for option in factor_options:
                key = (option['dropped'], option['reverse'])
                if option['dropped'] in preferred and key not in seen_option_keys:
                    selected.append(option)
                    seen_option_keys.add(key)
            for option in factor_options:
                key = (option['dropped'], option['reverse'])
                if key in seen_option_keys:
                    continue
                selected.append(option)
                seen_option_keys.add(key)
                if len(selected) >= options_per_factor:
                    break
            options.extend(selected[: max(options_per_factor, len(selected))])
        options_by_cell.append(options)

    model = cp_model.CpModel()
    variables: dict[tuple[int, int], Any] = {}
    by_factor = [list() for _factor in range(factor_count)]
    by_round_factor: dict[tuple[int, int], list[Any]] = {}
    by_block_factor: dict[tuple[int, int], list[Any]] = {}
    by_prefix_factor: dict[tuple[int, int], list[Any]] = {}
    by_opponent: dict[tuple[int, int], list[Any]] = {}
    by_team_pair: dict[tuple[int, int], list[Any]] = {}
    by_prefix_team_pair: dict[tuple[int, tuple[int, int]], list[Any]] = {}
    by_down_seat: dict[int, list[Any]] = {}
    by_up_seat: dict[int, list[Any]] = {}
    down_by_team: list[list[Any]] = [[] for _team in range(team_count)]
    up_by_team: list[list[Any]] = [[] for _team in range(team_count)]
    objective_terms: list[Any] = []

    for cell_index, (round_index, block) in enumerate(cells):
        cell_variables = []
        for option_index, option in enumerate(options_by_cell[cell_index]):
            variable = model.NewBoolVar(f'i_{cell_index}_{option_index}')
            variables[(cell_index, option_index)] = variable
            cell_variables.append(variable)
            factor_index = option['factor']
            by_factor[factor_index].append(variable)
            by_round_factor.setdefault((round_index, factor_index), []).append(variable)
            by_block_factor.setdefault((block, factor_index), []).append(variable)
            for prefix in range(round_index + 1, rounds + 1):
                by_prefix_factor.setdefault((prefix, factor_index), []).append(variable)
            for key in option['opponent_keys']:
                by_opponent.setdefault(key, []).append(variable)
            for key in option['team_pair_keys']:
                by_team_pair.setdefault(key, []).append(variable)
            for prefix in range(round_index + 1, rounds + 1):
                for key in set(option['team_pair_keys']):
                    by_prefix_team_pair.setdefault((prefix, key), []).append(variable)
            by_down_seat.setdefault(option['down_seat'], []).append(variable)
            by_up_seat.setdefault(option['up_seat'], []).append(variable)
            down_by_team[option['down']].append(variable)
            up_by_team[option['up']].append(variable)
            objective_terms.append(option['tie'] % 997 * variable)
        model.Add(sum(cell_variables) == 1)

    for variables_for_key in by_round_factor.values():
        model.Add(sum(variables_for_key) <= 1)
    for variables_for_key in by_block_factor.values():
        model.Add(sum(variables_for_key) <= 2)
    for variables_for_key in by_opponent.values():
        model.Add(sum(variables_for_key) <= 1)
    for variables_for_key in by_down_seat.values():
        model.Add(sum(variables_for_key) <= 1)
    for variables_for_key in by_up_seat.values():
        model.Add(sum(variables_for_key) <= 1)

    total_factor_uses = rounds * block_count
    factor_totals = []
    for factor_index, factor_variables in enumerate(by_factor):
        factor_total = model.NewIntVar(
            0, total_factor_uses, f'int_factor_total_{factor_index}'
        )
        model.Add(factor_total == sum(factor_variables))
        factor_totals.append(factor_total)
    max_factor_total = model.NewIntVar(0, total_factor_uses, 'int_max_factor_total')
    min_factor_total = model.NewIntVar(0, total_factor_uses, 'int_min_factor_total')
    factor_spread = model.NewIntVar(0, total_factor_uses, 'int_factor_spread')
    model.AddMaxEquality(max_factor_total, factor_totals)
    model.AddMinEquality(min_factor_total, factor_totals)
    model.Add(factor_spread == max_factor_total - min_factor_total)

    max_pair_count = players_per_team * rounds
    pair_counts: dict[tuple[int, int], Any] = {}
    for first_team in range(team_count):
        for second_team in range(first_team + 1, team_count):
            key = (first_team, second_team)
            pair_count = model.NewIntVar(
                0, max_pair_count, f'int_pair_{first_team}_{second_team}'
            )
            model.Add(pair_count == sum(by_team_pair.get(key, ())))
            pair_counts[key] = pair_count

    team_i1_spreads = []
    for team in range(team_count):
        opponent_counts = [
            pair_counts[tuple(sorted((team, opponent)))]
            for opponent in range(team_count)
            if opponent != team
        ]
        team_max = model.NewIntVar(0, max_pair_count, f'int_team_i1_max_{team}')
        team_min = model.NewIntVar(0, max_pair_count, f'int_team_i1_min_{team}')
        team_spread = model.NewIntVar(0, max_pair_count, f'int_team_i1_spread_{team}')
        model.AddMaxEquality(team_max, opponent_counts)
        model.AddMinEquality(team_min, opponent_counts)
        model.Add(team_spread == team_max - team_min)
        team_i1_spreads.append(team_spread)
    max_i1_spread = model.NewIntVar(0, max_pair_count, 'int_max_i1_spread')
    model.AddMaxEquality(max_i1_spread, team_i1_spreads)

    prefix_deficits = []
    for prefix in range(1, rounds + 1):
        expected_distinct = min(team_count - 1, players_per_team * prefix)
        present_by_pair: dict[tuple[int, int], Any] = {}
        for first_team in range(team_count):
            for second_team in range(first_team + 1, team_count):
                key = (first_team, second_team)
                prefix_count = sum(by_prefix_team_pair.get((prefix, key), ()))
                present = model.NewBoolVar(
                    f'int_prefix_{prefix}_{first_team}_{second_team}'
                )
                model.Add(prefix_count >= 1).OnlyEnforceIf(present)
                model.Add(prefix_count == 0).OnlyEnforceIf(present.Not())
                present_by_pair[key] = present
        for team in range(team_count):
            present_opponents = [
                present_by_pair[tuple(sorted((team, opponent)))]
                for opponent in range(team_count)
                if opponent != team
            ]
            prefix_deficit = model.NewIntVar(
                0, expected_distinct, f'int_prefix_deficit_{prefix}_{team}'
            )
            model.Add(prefix_deficit == expected_distinct - sum(present_opponents))
            prefix_deficits.append(prefix_deficit)
    max_prefix_deficit = model.NewIntVar(0, team_count - 1, 'int_max_prefix_deficit')
    model.AddMaxEquality(max_prefix_deficit, prefix_deficits)

    abs_diffs = []
    for team in range(team_count):
        diff = model.NewIntVar(-len(cells), len(cells), f'int_i3_{team}')
        model.Add(diff == sum(down_by_team[team]) - sum(up_by_team[team]))
        abs_diff = model.NewIntVar(0, len(cells), f'int_abs_i3_{team}')
        model.AddAbsEquality(abs_diff, diff)
        abs_diffs.append(abs_diff)
    model.Minimize(
        max_i1_spread * 1_000_000_000_000
        + max_prefix_deficit * 10_000_000_000
        + sum(prefix_deficits) * 1_000_000
        + factor_spread * 100_000
        + sum(abs_diffs) * 1_000
        + sum(objective_terms)
    )

    deadline = perf_counter() + timeout_seconds
    solve_index = 0
    while perf_counter() < deadline and solve_index < 64:
        solver = cp_model.CpSolver()
        solver.parameters.max_time_in_seconds = max(0.1, deadline - perf_counter())
        solver.parameters.num_search_workers = workers
        solver.parameters.random_seed = seed + solve_index + 1
        solver.parameters.randomize_search = True
        status = solver.Solve(model)
        if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            if status == cp_model.MODEL_INVALID:
                raise ValueError(model.Validate())
            return None

        selected: list[int] = []
        schedule_cells = []
        for cell_index, options in enumerate(options_by_cell):
            selected_option = -1
            for option_index, option in enumerate(options):
                if solver.Value(variables[(cell_index, option_index)]):
                    selected_option = option_index
                    schedule_cells.append(
                        {
                            'factor': option['factor'],
                            'dropped': list(option['dropped']),
                            'reverse': option['reverse'],
                        }
                    )
                    break
            if selected_option < 0:
                raise ValueError('Integrated odd CP returned an incomplete solution.')
            selected.append(selected_option)

        schedule = {'kind': 'odd_cell_occurrences', 'cells': schedule_cells}
        matches = _materialize_matches(team_count, players_per_team, rounds, schedule)
        if (
            mg._colour_with_relaxed_team_balance(matches, team_count, players_per_team)
            is not None
        ):
            return schedule

        failed_groups: list[list[int]] = []
        for first_round in range(0, rounds - 1, 2):
            if (
                mg._pair_flip_colour_relaxed_s5(
                    matches[first_round],
                    matches[first_round + 1],
                    team_count,
                    players_per_team,
                )
                is not None
            ):
                continue
            start = first_round * block_count
            failed_groups.append(list(range(start, start + 2 * block_count)))
        if not failed_groups:
            failed_groups.append(list(range(len(cells))))
        for group in failed_groups:
            model.Add(
                sum(
                    variables[(cell_index, selected[cell_index])]
                    for cell_index in group
                )
                <= len(group) - 1
            )
        solve_index += 1
    return None


def _odd_colour_integrated_cp_sat_occurrence_schedule(
    team_count: int,
    players_per_team: int,
    rounds: int,
    factors: tuple[tuple[tuple[int, int], ...], ...],
    *,
    timeout_seconds: float,
    workers: int,
    seed: int,
    options_per_factor: int,
) -> tuple[dict[str, Any], list[Round], float] | None:
    if timeout_seconds <= 0 or options_per_factor <= 0:
        return None

    from ortools.sat.python import cp_model

    started = perf_counter()
    factor_count = (team_count - 1) // 2
    block_count = players_per_team // 2
    factor_edges = mg._one_odd_factor_odd_edges(team_count, factors)
    offsets = mg._one_odd_partial_offsets(team_count, block_count)
    fast_plan_result = mg._one_odd_fast_partial_plan(
        team_count,
        rounds,
        block_count,
        tuple(0 for _team in range(team_count)),
        factors,
        initial_up_counts=tuple(0 for _team in range(team_count)),
    )
    fast_plan = fast_plan_result[0] if fast_plan_result is not None else None
    hinted_rounds: list[Round] | None = None
    hinted_white_by_round_pair: list[dict[frozenset[Player], Player]] = [
        {} for _round in range(rounds)
    ]
    if fast_plan is not None:
        hinted_matches = mg._complete_i1_one_odd_plan_blocks(
            team_count, rounds, 0, fast_plan, factors
        )
        hinted_rounds = mg._colour_with_relaxed_team_balance(
            hinted_matches, team_count, players_per_team
        )
        if hinted_rounds is not None:
            for round_index, rnd in enumerate(hinted_rounds):
                for white, black in rnd:
                    hinted_white_by_round_pair[round_index][
                        frozenset((white, black))
                    ] = white

    def preferred_dropped_edges(
        round_index: int, factor_index: int, block: int
    ) -> set[tuple[int, int]]:
        preferred: set[tuple[int, int]] = set()
        if fast_plan is not None:
            planned_factor, planned_dropped = fast_plan[round_index // 2][block]
            if planned_factor == factor_index:
                preferred.add(planned_dropped)
                preferred.add((planned_dropped[1], planned_dropped[0]))
        offset = offsets[block]
        first_round = (factor_index - offset) % factor_count
        dropped = mg._affine_floater_edge(team_count, first_round, offset)
        if dropped not in factors[factor_index]:
            incident = sorted(edge for edge in factors[factor_index] if 0 in edge)
            edge = incident[0]
            dropped = edge if edge[0] == 0 else (edge[1], edge[0])
        preferred.add(dropped)
        preferred.add((dropped[1], dropped[0]))
        return preferred

    cells = [
        (round_index, block)
        for round_index in range(rounds)
        for block in range(block_count)
    ]
    options_by_cell: list[list[dict[str, Any]]] = []
    for round_index, block in cells:
        options = []
        for factor_index in range(factor_count):
            factor_options = []
            for edge in factor_edges[factor_index]:
                for dropped in (edge, (edge[1], edge[0])):
                    for reverse in (False, True):
                        matches, down, up = _odd_cell_option(
                            team_count,
                            players_per_team,
                            factors,
                            factor_index,
                            block,
                            dropped,
                            reverse,
                        )
                        opponent_keys = []
                        team_pair_keys = []
                        for first, second in matches:
                            opponent_keys.append(
                                (_seat(first, players_per_team), second[0])
                            )
                            opponent_keys.append(
                                (_seat(second, players_per_team), first[0])
                            )
                            team_pair_keys.append(tuple(sorted((first[0], second[0]))))
                        tie = (
                            (dropped[0] * 1_000_003)
                            ^ (dropped[1] * 9_176)
                            ^ (factor_index * 65_537)
                            ^ (round_index * 8_191)
                            ^ (block * 131)
                            ^ (seed * 2_654_435_761)
                            ^ (1 if reverse else 0)
                        ) & 0xFFFFFFFF
                        factor_options.append(
                            {
                                'factor': factor_index,
                                'dropped': dropped,
                                'reverse': reverse,
                                'matches': tuple(matches),
                                'down': down,
                                'up': up,
                                'down_seat': down * players_per_team + 2 * block,
                                'up_seat': up * players_per_team + 2 * block + 1,
                                'opponent_keys': tuple(opponent_keys),
                                'team_pair_keys': tuple(team_pair_keys),
                                'tie': tie,
                            }
                        )
            factor_options.sort(key=lambda option: option['tie'])
            preferred = preferred_dropped_edges(round_index, factor_index, block)
            selected: list[dict[str, Any]] = []
            seen_option_keys: set[tuple[tuple[int, int], bool]] = set()
            for option in factor_options:
                key = (option['dropped'], option['reverse'])
                if option['dropped'] in preferred and key not in seen_option_keys:
                    selected.append(option)
                    seen_option_keys.add(key)
            for option in factor_options:
                key = (option['dropped'], option['reverse'])
                if key in seen_option_keys:
                    continue
                selected.append(option)
                seen_option_keys.add(key)
                if len(selected) >= options_per_factor:
                    break
            options.extend(selected[: max(options_per_factor, len(selected))])
        options_by_cell.append(options)

    model = cp_model.CpModel()
    variables: dict[tuple[int, int], Any] = {}
    first_white_variables: dict[tuple[int, int, int], Any] = {}
    second_white_variables: dict[tuple[int, int, int], Any] = {}
    by_factor = [list() for _factor in range(factor_count)]
    by_round_factor: dict[tuple[int, int], list[Any]] = {}
    by_block_factor: dict[tuple[int, int], list[Any]] = {}
    by_opponent: dict[tuple[int, int], list[Any]] = {}
    by_team_pair: dict[tuple[int, int], list[Any]] = {}
    by_prefix_team_pair: dict[tuple[int, tuple[int, int]], list[Any]] = {}
    by_down_seat: dict[int, list[Any]] = {}
    by_up_seat: dict[int, list[Any]] = {}
    down_by_team: list[list[Any]] = [[] for _team in range(team_count)]
    up_by_team: list[list[Any]] = [[] for _team in range(team_count)]
    player_white_by_round = [
        [[] for _seat_index in range(team_count * players_per_team)]
        for _round in range(rounds)
    ]
    team_white_by_round = [
        [[] for _team in range(team_count)] for _round in range(rounds)
    ]
    objective_terms: list[Any] = []

    for cell_index, (round_index, block) in enumerate(cells):
        cell_variables = []
        for option_index, option in enumerate(options_by_cell[cell_index]):
            variable = model.NewBoolVar(f'ci_{cell_index}_{option_index}')
            variables[(cell_index, option_index)] = variable
            cell_variables.append(variable)
            factor_index = option['factor']
            by_factor[factor_index].append(variable)
            by_round_factor.setdefault((round_index, factor_index), []).append(variable)
            by_block_factor.setdefault((block, factor_index), []).append(variable)
            for key in option['opponent_keys']:
                by_opponent.setdefault(key, []).append(variable)
            for key in option['team_pair_keys']:
                by_team_pair.setdefault(key, []).append(variable)
            for prefix in range(round_index + 1, rounds + 1):
                for key in set(option['team_pair_keys']):
                    by_prefix_team_pair.setdefault((prefix, key), []).append(variable)
            by_down_seat.setdefault(option['down_seat'], []).append(variable)
            by_up_seat.setdefault(option['up_seat'], []).append(variable)
            down_by_team[option['down']].append(variable)
            up_by_team[option['up']].append(variable)
            objective_terms.append(option['tie'] % 997 * variable)
            if fast_plan is not None:
                planned_factor, planned_dropped = fast_plan[round_index // 2][block]
                planned_reverse = round_index % 2 == 1
                model.AddHint(
                    variable,
                    int(
                        planned_factor == factor_index
                        and planned_dropped == option['dropped']
                        and planned_reverse == option['reverse']
                    ),
                )

            for match_index, (first, second) in enumerate(option['matches']):
                first_white = model.NewBoolVar(
                    f'cw_{cell_index}_{option_index}_{match_index}_a'
                )
                second_white = model.NewBoolVar(
                    f'cw_{cell_index}_{option_index}_{match_index}_b'
                )
                first_white_variables[(cell_index, option_index, match_index)] = (
                    first_white
                )
                second_white_variables[(cell_index, option_index, match_index)] = (
                    second_white
                )
                model.Add(first_white + second_white == variable)
                first_seat = _seat(first, players_per_team)
                second_seat = _seat(second, players_per_team)
                player_white_by_round[round_index][first_seat].append(first_white)
                player_white_by_round[round_index][second_seat].append(second_white)
                team_white_by_round[round_index][first[0]].append(first_white)
                team_white_by_round[round_index][second[0]].append(second_white)
                if hinted_rounds is not None:
                    hinted_white = hinted_white_by_round_pair[round_index].get(
                        frozenset((first, second))
                    )
                    selected_hint = (
                        fast_plan is not None
                        and fast_plan[round_index // 2][block][0] == factor_index
                        and fast_plan[round_index // 2][block][1] == option['dropped']
                        and (round_index % 2 == 1) == option['reverse']
                    )
                    model.AddHint(
                        first_white,
                        int(selected_hint and hinted_white == first),
                    )
                    model.AddHint(
                        second_white,
                        int(selected_hint and hinted_white == second),
                    )
        model.Add(sum(cell_variables) == 1)

    for variables_for_key in by_round_factor.values():
        model.Add(sum(variables_for_key) <= 1)
    for variables_for_key in by_block_factor.values():
        model.Add(sum(variables_for_key) <= 2)
    for variables_for_key in by_opponent.values():
        model.Add(sum(variables_for_key) <= 1)
    for variables_for_key in by_down_seat.values():
        model.Add(sum(variables_for_key) <= 1)
    for variables_for_key in by_up_seat.values():
        model.Add(sum(variables_for_key) <= 1)

    max_pair_count = players_per_team * rounds
    pair_counts: dict[tuple[int, int], Any] = {}
    for first_team in range(team_count):
        for second_team in range(first_team + 1, team_count):
            key = (first_team, second_team)
            pair_count = model.NewIntVar(
                0, max_pair_count, f'ci_pair_{first_team}_{second_team}'
            )
            model.Add(pair_count == sum(by_team_pair.get(key, ())))
            pair_counts[key] = pair_count

    team_i1_spreads = []
    for team in range(team_count):
        opponent_counts = [
            pair_counts[tuple(sorted((team, opponent)))]
            for opponent in range(team_count)
            if opponent != team
        ]
        team_max = model.NewIntVar(0, max_pair_count, f'ci_team_i1_max_{team}')
        team_min = model.NewIntVar(0, max_pair_count, f'ci_team_i1_min_{team}')
        team_spread = model.NewIntVar(0, max_pair_count, f'ci_team_i1_spread_{team}')
        model.AddMaxEquality(team_max, opponent_counts)
        model.AddMinEquality(team_min, opponent_counts)
        model.Add(team_spread == team_max - team_min)
        team_i1_spreads.append(team_spread)
    max_i1_spread = model.NewIntVar(0, max_pair_count, 'ci_max_i1_spread')
    model.AddMaxEquality(max_i1_spread, team_i1_spreads)

    prefix_deficits = []
    for prefix in range(1, rounds + 1):
        expected_distinct = min(team_count - 1, players_per_team * prefix)
        present_by_pair: dict[tuple[int, int], Any] = {}
        for first_team in range(team_count):
            for second_team in range(first_team + 1, team_count):
                key = (first_team, second_team)
                prefix_count = sum(by_prefix_team_pair.get((prefix, key), ()))
                present = model.NewBoolVar(
                    f'ci_prefix_{prefix}_{first_team}_{second_team}'
                )
                model.Add(prefix_count >= 1).OnlyEnforceIf(present)
                model.Add(prefix_count == 0).OnlyEnforceIf(present.Not())
                present_by_pair[key] = present
        for team in range(team_count):
            present_opponents = [
                present_by_pair[tuple(sorted((team, opponent)))]
                for opponent in range(team_count)
                if opponent != team
            ]
            prefix_deficit = model.NewIntVar(
                0, expected_distinct, f'ci_prefix_deficit_{prefix}_{team}'
            )
            model.Add(prefix_deficit == expected_distinct - sum(present_opponents))
            prefix_deficits.append(prefix_deficit)
    max_prefix_deficit = model.NewIntVar(0, team_count - 1, 'ci_max_prefix_deficit')
    model.AddMaxEquality(max_prefix_deficit, prefix_deficits)

    abs_diffs = []
    for team in range(team_count):
        diff = model.NewIntVar(-len(cells), len(cells), f'ci_i3_{team}')
        model.Add(diff == sum(down_by_team[team]) - sum(up_by_team[team]))
        abs_diff = model.NewIntVar(0, len(cells), f'ci_abs_i3_{team}')
        model.AddAbsEquality(abs_diff, diff)
        abs_diffs.append(abs_diff)

    for seat in range(team_count * players_per_team):
        colours = [
            sum(player_white_by_round[round_index][seat])
            for round_index in range(rounds)
        ]
        for round_index in range(rounds - 2):
            triple = (
                colours[round_index]
                + colours[round_index + 1]
                + colours[round_index + 2]
            )
            model.Add(triple >= 1)
            model.Add(triple <= 2)
        for prefix in range(1, rounds + 1):
            whites = sum(colours[:prefix])
            drift = 2 * whites - prefix
            limit = 1 if prefix == rounds else 2
            model.Add(drift <= limit)
            model.Add(drift >= -limit)

    for team in range(team_count):
        drift = 0
        for round_index in range(rounds):
            whites = sum(team_white_by_round[round_index][team])
            round_drift = 2 * whites - players_per_team
            drift += round_drift
            model.Add(drift <= 2)
            model.Add(drift >= -2)
            if (round_index + 1) % 2 == 0 or round_index + 1 == rounds:
                model.Add(drift == 0)

    model.Minimize(
        max_i1_spread * 1_000_000_000_000
        + max_prefix_deficit * 10_000_000_000
        + sum(prefix_deficits) * 1_000_000
        + sum(abs_diffs) * 1_000
        + sum(objective_terms)
    )

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = timeout_seconds
    solver.parameters.num_search_workers = workers
    solver.parameters.random_seed = seed + 1
    solver.parameters.randomize_search = True
    status = solver.Solve(model)
    elapsed = perf_counter() - started
    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        if status == cp_model.MODEL_INVALID:
            raise ValueError(model.Validate())
        return None

    schedule_cells = []
    coloured: list[Round] = [[] for _round in range(rounds)]
    for cell_index, (round_index, _block) in enumerate(cells):
        selected_option = -1
        for option_index, option in enumerate(options_by_cell[cell_index]):
            if not solver.Value(variables[(cell_index, option_index)]):
                continue
            selected_option = option_index
            schedule_cells.append(
                {
                    'factor': option['factor'],
                    'dropped': list(option['dropped']),
                    'reverse': option['reverse'],
                }
            )
            for match_index, (first, second) in enumerate(option['matches']):
                first_white = first_white_variables[
                    (cell_index, option_index, match_index)
                ]
                coloured[round_index].append(
                    (first, second) if solver.Value(first_white) else (second, first)
                )
            break
        if selected_option < 0:
            raise ValueError(
                'Colour-integrated odd CP returned an incomplete solution.'
            )
    return {'kind': 'odd_cell_occurrences', 'cells': schedule_cells}, coloured, elapsed


def _odd_cell_drop_schedule(
    team_count: int,
    players_per_team: int,
    rounds: int,
    offsets: tuple[int, ...],
    matches: list[list[Match]],
) -> dict[str, Any]:
    half = (team_count - 1) // 2
    block_count = players_per_team // 2
    seen: dict[tuple[int, int], int] = {}
    drops: dict[tuple[int, int], tuple[int, int]] = {}
    for round_index in range(rounds):
        rnd = matches[round_index]
        for block in range(block_count):
            offset = offsets[block]
            factor_index = (round_index + offset) % half
            key = (block, factor_index)
            phase = seen.get(key, 0)
            seen[key] = phase + 1
            odd_slot = 2 * block
            even_slot = odd_slot + 1
            cross_matches = [
                match
                for match in rnd
                if {match[0][1], match[1][1]} == {odd_slot, even_slot}
            ]
            if len(cross_matches) != 1:
                raise ValueError(
                    f'Could not identify odd cell floater for {key} in round '
                    f'{round_index + 1}.'
                )
            first, second = cross_matches[0]
            odd_team = first[0] if first[1] == odd_slot else second[0]
            even_team = first[0] if first[1] == even_slot else second[0]
            dropped = (odd_team, even_team) if phase % 2 == 1 else (even_team, odd_team)
            previous = drops.setdefault(key, dropped)
            if previous != dropped:
                raise ValueError(
                    f'Inconsistent dropped edge for {key}: {previous} vs {dropped}.'
                )
    return {
        'kind': 'odd_cell_drops',
        'offsets': list(offsets),
        'cell_drops': [
            {'block': block, 'factor': factor, 'dropped': list(dropped)}
            for (block, factor), dropped in sorted(drops.items())
        ],
    }


def _odd_phase_reverse(
    policy: str,
    round_index: int,
    block: int,
    factor_index: int,
    block_factor_phase: int,
    factor_phase: int,
) -> bool:
    if policy == 'block_factor':
        return block_factor_phase % 2 == 1
    if policy == 'factor':
        return factor_phase % 2 == 1
    if policy == 'round_block':
        return (round_index + block) % 2 == 1
    if policy == 'round':
        return round_index % 2 == 1
    if policy == 'block':
        return block % 2 == 1
    if policy == 'never':
        return False
    if policy == 'always':
        return True
    raise ValueError(f'Unknown odd phase policy: {policy}')


def _odd_cell_occurrence_schedule(
    team_count: int,
    players_per_team: int,
    rounds: int,
    offsets: tuple[int, ...],
    drop_schedule: dict[str, Any],
    policy: str,
) -> dict[str, Any]:
    half = (team_count - 1) // 2
    drops = {
        (entry['block'], entry['factor']): tuple(entry['dropped'])
        for entry in drop_schedule['cell_drops']
    }
    seen_block_factor: dict[tuple[int, int], int] = {}
    seen_factor: dict[int, int] = {}
    cells: list[dict[str, Any]] = []
    for round_index in range(rounds):
        for block, offset in enumerate(offsets):
            factor_index = (round_index + offset) % half
            block_factor_key = (block, factor_index)
            block_factor_phase = seen_block_factor.get(block_factor_key, 0)
            factor_phase = seen_factor.get(factor_index, 0)
            seen_block_factor[block_factor_key] = block_factor_phase + 1
            seen_factor[factor_index] = factor_phase + 1
            cells.append(
                {
                    'factor': factor_index,
                    'dropped': list(drops[block_factor_key]),
                    'reverse': _odd_phase_reverse(
                        policy,
                        round_index,
                        block,
                        factor_index,
                        block_factor_phase,
                        factor_phase,
                    ),
                }
            )
    return {'kind': 'odd_cell_occurrences', 'cells': cells}


def _odd_direct_offset_occurrence_schedule(
    team_count: int,
    players_per_team: int,
    rounds: int,
    offsets: tuple[int, ...],
    factors: tuple[tuple[tuple[int, int], ...], ...],
    policy: str,
    drop_mode: str,
) -> dict[str, Any]:
    half = (team_count - 1) // 2
    factor_edges = mg._one_odd_factor_odd_edges(team_count, factors)

    def fallback_dropped(factor: tuple[tuple[int, int], ...]) -> tuple[int, int]:
        incident = sorted(edge for edge in factor if 0 in edge)
        edge = incident[0]
        return edge if edge[0] == 0 else (edge[1], edge[0])

    def dropped_edge(factor_index: int, offset: int) -> tuple[int, int]:
        first_round = (factor_index - offset) % half
        dropped = mg._affine_floater_edge(team_count, first_round, offset)
        if dropped not in factors[factor_index]:
            dropped = fallback_dropped(factors[factor_index])
        if drop_mode == 'affine':
            return dropped
        if drop_mode == 'reverse':
            return dropped[1], dropped[0]
        if drop_mode == 'first':
            return factor_edges[factor_index][0]
        if drop_mode == 'first_reverse':
            first, second = factor_edges[factor_index][0]
            return second, first
        raise ValueError(f'Unknown odd direct drop mode: {drop_mode}')

    seen_block_factor: dict[tuple[int, int], int] = {}
    seen_factor: dict[int, int] = {}
    cells: list[dict[str, Any]] = []
    for round_index in range(rounds):
        for block, offset in enumerate(offsets):
            factor_index = (round_index + offset) % half
            block_factor_key = (block, factor_index)
            block_factor_phase = seen_block_factor.get(block_factor_key, 0)
            factor_phase = seen_factor.get(factor_index, 0)
            seen_block_factor[block_factor_key] = block_factor_phase + 1
            seen_factor[factor_index] = factor_phase + 1
            cells.append(
                {
                    'factor': factor_index,
                    'dropped': list(dropped_edge(factor_index, offset)),
                    'reverse': _odd_phase_reverse(
                        policy,
                        round_index,
                        block,
                        factor_index,
                        block_factor_phase,
                        factor_phase,
                    ),
                }
            )
    return {'kind': 'odd_cell_occurrences', 'cells': cells}


def _even_cp_sat_factor_row_candidates(
    factor_count: int,
    players_per_team: int,
    rounds: int,
    *,
    timeout_seconds: float,
    workers: int,
    attempts: int,
) -> tuple[tuple[tuple[int, ...], ...], ...]:
    if timeout_seconds <= 0 or attempts <= 0:
        return ()

    from ortools.sat.python import cp_model

    model = cp_model.CpModel()
    variables: dict[tuple[int, int, int], Any] = {}
    for round_index in range(rounds):
        for slot in range(players_per_team):
            for factor in range(factor_count):
                variables[(round_index, slot, factor)] = model.NewBoolVar(
                    f'x_{round_index}_{slot}_{factor}'
                )

    for round_index in range(rounds):
        for slot in range(players_per_team):
            model.Add(
                sum(
                    variables[(round_index, slot, factor)]
                    for factor in range(factor_count)
                )
                == 1
            )
        for factor in range(factor_count):
            model.Add(
                sum(
                    variables[(round_index, slot, factor)]
                    for slot in range(players_per_team)
                )
                <= 1
            )

    for slot in range(players_per_team):
        for factor in range(factor_count):
            model.Add(
                sum(
                    variables[(round_index, slot, factor)]
                    for round_index in range(rounds)
                )
                <= 1
            )

    total_factor_uses = rounds * players_per_team
    low = total_factor_uses // factor_count
    high = (total_factor_uses + factor_count - 1) // factor_count
    for factor in range(factor_count):
        total = sum(
            variables[(round_index, slot, factor)]
            for round_index in range(rounds)
            for slot in range(players_per_team)
        )
        model.Add(total >= low)
        model.Add(total <= high)

    for prefix in range(1, rounds + 1):
        expected_distinct = min(factor_count, players_per_team * prefix)
        for factor in range(factor_count):
            count = sum(
                variables[(round_index, slot, factor)]
                for round_index in range(prefix)
                for slot in range(players_per_team)
            )
            if expected_distinct == players_per_team * prefix:
                model.Add(count <= 1)
            if expected_distinct == factor_count:
                model.Add(count >= 1)

    out: list[tuple[tuple[int, ...], ...]] = []
    seen: set[tuple[tuple[int, ...], ...]] = set()
    for attempt in range(attempts):
        solver = cp_model.CpSolver()
        solver.parameters.max_time_in_seconds = timeout_seconds
        solver.parameters.num_search_workers = workers
        solver.parameters.random_seed = attempt + 1
        status = solver.Solve(model)
        if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            break

        rows: list[tuple[int, ...]] = []
        chosen_literals = []
        for round_index in range(rounds):
            row: list[int] = []
            for slot in range(players_per_team):
                for factor in range(factor_count):
                    literal = variables[(round_index, slot, factor)]
                    if solver.Value(literal):
                        row.append(factor)
                        chosen_literals.append(literal)
                        break
            rows.append(tuple(row))
        candidate = tuple(rows)
        model.Add(sum(chosen_literals) <= len(chosen_literals) - 1)
        if candidate in seen:
            continue
        seen.add(candidate)
        out.append(candidate)
    return tuple(out)


def _even_integrated_cp_sat_factor_rows(
    team_count: int,
    players_per_team: int,
    rounds: int,
    *,
    timeout_seconds: float,
    workers: int,
    seed: int,
) -> tuple[tuple[int, ...], ...] | None:
    if timeout_seconds <= 0:
        return None

    from ortools.sat.python import cp_model

    factor_count = team_count - 1
    model = cp_model.CpModel()
    variables: dict[tuple[int, int, int], Any] = {}
    by_factor = [list() for _factor in range(factor_count)]
    by_round_factor: dict[tuple[int, int], list[Any]] = {}
    by_slot_factor: dict[tuple[int, int], list[Any]] = {}
    by_prefix_factor: dict[tuple[int, int], list[Any]] = {}
    objective_terms: list[Any] = []

    for round_index in range(rounds):
        for slot in range(players_per_team):
            cell_variables = []
            for factor in range(factor_count):
                variable = model.NewBoolVar(f'e_{round_index}_{slot}_{factor}')
                variables[(round_index, slot, factor)] = variable
                cell_variables.append(variable)
                by_factor[factor].append(variable)
                by_round_factor.setdefault((round_index, factor), []).append(variable)
                by_slot_factor.setdefault((slot, factor), []).append(variable)
                for prefix in range(round_index + 1, rounds + 1):
                    by_prefix_factor.setdefault((prefix, factor), []).append(variable)
                objective_terms.append(
                    (
                        (factor * 65_537)
                        ^ (round_index * 8_191)
                        ^ (slot * 131)
                        ^ (seed * 2_654_435_761)
                    )
                    % 997
                    * variable
                )
            model.Add(sum(cell_variables) == 1)

    for variables_for_key in by_round_factor.values():
        model.Add(sum(variables_for_key) <= 1)
    for variables_for_key in by_slot_factor.values():
        model.Add(sum(variables_for_key) <= 1)

    total_factor_uses = rounds * players_per_team
    factor_totals = []
    for factor, factor_variables in enumerate(by_factor):
        factor_total = model.NewIntVar(0, total_factor_uses, f'e_factor_total_{factor}')
        model.Add(factor_total == sum(factor_variables))
        factor_totals.append(factor_total)
    max_factor_total = model.NewIntVar(0, total_factor_uses, 'e_max_factor_total')
    min_factor_total = model.NewIntVar(0, total_factor_uses, 'e_min_factor_total')
    factor_spread = model.NewIntVar(0, total_factor_uses, 'e_factor_spread')
    model.AddMaxEquality(max_factor_total, factor_totals)
    model.AddMinEquality(min_factor_total, factor_totals)
    model.Add(factor_spread == max_factor_total - min_factor_total)

    prefix_deficits = []
    for prefix in range(1, rounds + 1):
        expected_distinct = min(factor_count, players_per_team * prefix)
        present_variables = []
        for factor in range(factor_count):
            prefix_count = sum(by_prefix_factor.get((prefix, factor), ()))
            present = model.NewBoolVar(f'e_prefix_{prefix}_{factor}')
            model.Add(prefix_count >= 1).OnlyEnforceIf(present)
            model.Add(prefix_count == 0).OnlyEnforceIf(present.Not())
            present_variables.append(present)
        prefix_deficit = model.NewIntVar(
            0, expected_distinct, f'e_prefix_deficit_{prefix}'
        )
        model.Add(prefix_deficit == expected_distinct - sum(present_variables))
        prefix_deficits.append(prefix_deficit)
    max_prefix_deficit = model.NewIntVar(0, factor_count, 'e_max_prefix_deficit')
    model.AddMaxEquality(max_prefix_deficit, prefix_deficits)

    model.Minimize(
        factor_spread * 1_000_000_000
        + max_prefix_deficit * 10_000_000
        + sum(prefix_deficits) * 100_000
        + sum(objective_terms)
    )

    deadline = perf_counter() + timeout_seconds
    solve_index = 0
    while perf_counter() < deadline and solve_index < 64:
        solver = cp_model.CpSolver()
        solver.parameters.max_time_in_seconds = max(0.1, deadline - perf_counter())
        solver.parameters.num_search_workers = workers
        solver.parameters.random_seed = seed + solve_index + 1
        solver.parameters.randomize_search = True
        status = solver.Solve(model)
        if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            return None

        rows: list[tuple[int, ...]] = []
        selected_literals = []
        for round_index in range(rounds):
            row: list[int] = []
            for slot in range(players_per_team):
                for factor in range(factor_count):
                    literal = variables[(round_index, slot, factor)]
                    if solver.Value(literal):
                        row.append(factor)
                        selected_literals.append(literal)
                        break
            rows.append(tuple(row))
        candidate = tuple(rows)
        matches = mg._even_matches_from_factor_rows(team_count, candidate)
        if (
            mg._colour_with_relaxed_team_balance(matches, team_count, players_per_team)
            is not None
        ):
            return candidate

        failed_groups: list[list[Any]] = []
        for first_round in range(0, rounds - 1, 2):
            if (
                mg._pair_flip_colour_relaxed_s5(
                    matches[first_round],
                    matches[first_round + 1],
                    team_count,
                    players_per_team,
                )
                is not None
            ):
                continue
            group = []
            for round_index in (first_round, first_round + 1):
                for slot in range(players_per_team):
                    factor = candidate[round_index][slot]
                    group.append(variables[(round_index, slot, factor)])
            failed_groups.append(group)
        if not failed_groups:
            failed_groups.append(selected_literals)
        for group in failed_groups:
            model.Add(sum(group) <= len(group) - 1)
        solve_index += 1
    return None


def _candidate_specs(
    team_count: int,
    players_per_team: int,
    rounds: int,
    limit: int,
    *,
    odd_phase_policies: tuple[str, ...],
    odd_colour_integrated_timeout_seconds: float,
    odd_colour_integrated_attempts: int,
    odd_colour_integrated_options_per_factor: int,
    odd_integrated_timeout_seconds: float,
    odd_integrated_attempts: int,
    odd_integrated_options_per_factor: int,
    odd_offset_candidate_limit: int,
    odd_offset_max_permutations: int,
    odd_direct_offsets_only: bool,
    odd_row_solver_timeout_seconds: float,
    odd_row_solver_attempts: int,
    even_integrated_timeout_seconds: float,
    even_integrated_attempts: int,
    even_row_solver_timeout_seconds: float,
    even_row_solver_attempts: int,
    workers: int,
) -> list[Candidate]:
    out: list[Candidate] = []
    if team_count % 2 == 1 and players_per_team < team_count - 1:
        factors = mg._one_odd_factorization(team_count)
        if factors is not None:
            block_count = players_per_team // 2
            scored: list[tuple[tuple[Any, ...], Candidate]] = []
            for attempt in range(odd_colour_integrated_attempts):
                result = _odd_colour_integrated_cp_sat_occurrence_schedule(
                    team_count,
                    players_per_team,
                    rounds,
                    factors,
                    timeout_seconds=odd_colour_integrated_timeout_seconds,
                    workers=workers,
                    seed=attempt,
                    options_per_factor=odd_colour_integrated_options_per_factor,
                )
                if result is None:
                    continue
                schedule, coloured, seconds = result
                matches = _materialize_matches(
                    team_count, players_per_team, rounds, schedule
                )
                scored.append(
                    (
                        _raw_priority(matches, team_count, players_per_team),
                        Candidate(
                            f'odd_colour_integrated_cp_seed={attempt}',
                            schedule,
                            matches,
                            coloured=coloured,
                            colour_status='integrated-colour-cp:ok',
                            colour_seconds=seconds,
                        ),
                    )
                )
            for attempt in range(odd_integrated_attempts):
                schedule = _odd_integrated_cp_sat_occurrence_schedule(
                    team_count,
                    players_per_team,
                    rounds,
                    factors,
                    timeout_seconds=odd_integrated_timeout_seconds,
                    workers=workers,
                    seed=attempt,
                    options_per_factor=odd_integrated_options_per_factor,
                )
                if schedule is None:
                    continue
                matches = _materialize_matches(
                    team_count, players_per_team, rounds, schedule
                )
                scored.append(
                    (
                        _raw_priority(matches, team_count, players_per_team),
                        Candidate(
                            f'odd_integrated_cp_seed={attempt}',
                            schedule,
                            matches,
                        ),
                    )
                )
            for row_index, factor_rows in enumerate(
                _odd_cp_sat_factor_row_candidates(
                    (team_count - 1) // 2,
                    block_count,
                    rounds,
                    timeout_seconds=odd_row_solver_timeout_seconds,
                    workers=workers,
                    attempts=odd_row_solver_attempts,
                ),
                start=1,
            ):
                for salt in range(2):
                    schedule = _odd_occurrence_schedule_from_factor_rows(
                        team_count,
                        players_per_team,
                        factor_rows,
                        factors,
                        salt=salt,
                        search_passes=1,
                    )
                    if schedule is None:
                        schedule = _odd_cp_sat_occurrence_schedule_from_factor_rows(
                            team_count,
                            players_per_team,
                            factor_rows,
                            factors,
                            timeout_seconds=odd_row_solver_timeout_seconds,
                            workers=workers,
                            seed=(row_index * 17) + salt,
                        )
                    if schedule is None:
                        continue
                    matches = _materialize_matches(
                        team_count, players_per_team, rounds, schedule
                    )
                    scored.append(
                        (
                            _raw_priority(matches, team_count, players_per_team),
                            Candidate(
                                f'odd_cp_rows_{row_index}_salt={salt}',
                                schedule,
                                matches,
                            ),
                        )
                    )
            for offsets in _one_odd_spread_offset_candidates(
                team_count,
                block_count,
                rounds,
                limit=odd_offset_candidate_limit,
                max_permutations=odd_offset_max_permutations,
            ):
                if odd_direct_offsets_only:
                    for drop_mode in (
                        'affine',
                        'reverse',
                        'first',
                        'first_reverse',
                    ):
                        for policy in odd_phase_policies or ('round_block',):
                            occurrence_schedule = (
                                _odd_direct_offset_occurrence_schedule(
                                    team_count,
                                    players_per_team,
                                    rounds,
                                    offsets,
                                    factors,
                                    policy,
                                    drop_mode,
                                )
                            )
                            occurrence_matches = _materialize_matches(
                                team_count,
                                players_per_team,
                                rounds,
                                occurrence_schedule,
                            )
                            occurrence_label = (
                                'odd_direct_offsets='
                                f'{",".join(str(offset) for offset in offsets)}'
                                f'_drop={drop_mode}_phase={policy}'
                            )
                            scored.append(
                                (
                                    _raw_priority(
                                        occurrence_matches,
                                        team_count,
                                        players_per_team,
                                    ),
                                    Candidate(
                                        occurrence_label,
                                        occurrence_schedule,
                                        occurrence_matches,
                                    ),
                                )
                            )
                    continue
                for optimise in (True, False):
                    raw_matches = mg._one_odd_spread_partial_blocks(
                        team_count,
                        rounds,
                        0,
                        block_count,
                        factors,
                        offsets=offsets,
                        optimise_floaters=optimise,
                        salt=0,
                        search_passes=1,
                    )
                    schedule = _odd_cell_drop_schedule(
                        team_count,
                        players_per_team,
                        rounds,
                        offsets,
                        raw_matches,
                    )
                    matches = _materialize_matches(
                        team_count, players_per_team, rounds, schedule
                    )
                    label = (
                        f'odd_offsets={",".join(str(offset) for offset in offsets)}'
                        f'_floaters={"on" if optimise else "off"}'
                    )
                    scored.append(
                        (
                            _raw_priority(matches, team_count, players_per_team),
                            Candidate(label, schedule, matches),
                        )
                    )
                    for policy in odd_phase_policies:
                        occurrence_schedule = _odd_cell_occurrence_schedule(
                            team_count,
                            players_per_team,
                            rounds,
                            offsets,
                            schedule,
                            policy,
                        )
                        occurrence_matches = _materialize_matches(
                            team_count,
                            players_per_team,
                            rounds,
                            occurrence_schedule,
                        )
                        occurrence_label = f'{label}_phase={policy}'
                        scored.append(
                            (
                                _raw_priority(
                                    occurrence_matches, team_count, players_per_team
                                ),
                                Candidate(
                                    occurrence_label,
                                    occurrence_schedule,
                                    occurrence_matches,
                                ),
                            )
                        )
            scored.sort(key=lambda item: item[0])
            seen: set[tuple[tuple[Match, ...], ...]] = set()
            for _score, candidate in scored:
                key = tuple(tuple(rnd) for rnd in candidate.matches)
                if key in seen:
                    continue
                seen.add(key)
                out.append(candidate)
                if len(out) >= limit:
                    break

    if team_count % 2 == 0:
        factor_count = team_count - 1
        for attempt in range(even_integrated_attempts):
            rows = _even_integrated_cp_sat_factor_rows(
                team_count,
                players_per_team,
                rounds,
                timeout_seconds=even_integrated_timeout_seconds,
                workers=workers,
                seed=attempt,
            )
            if rows is None:
                continue
            schedule = {
                'kind': 'even_factor_rows',
                'rows': [list(row) for row in rows],
            }
            matches = _materialize_matches(
                team_count, players_per_team, rounds, schedule
            )
            out.append(
                Candidate(f'even_integrated_cp_seed={attempt}', schedule, matches)
            )
            if len(out) >= limit:
                break

        for attempt_index, cp_rows in enumerate(
            _even_cp_sat_factor_row_candidates(
                factor_count,
                players_per_team,
                rounds,
                timeout_seconds=even_row_solver_timeout_seconds,
                workers=workers,
                attempts=even_row_solver_attempts,
            ),
            start=1,
        ):
            schedule = {
                'kind': 'even_factor_rows',
                'rows': [list(row) for row in cp_rows],
            }
            matches = _materialize_matches(
                team_count, players_per_team, rounds, schedule
            )
            out.append(
                Candidate(f'even_cp_sat_prefix_i1_{attempt_index}', schedule, matches)
            )
            if len(out) >= limit:
                break

        if len(out) < limit:
            for index, rows in enumerate(
                mg._even_i1_first_factor_row_candidates(
                    factor_count, players_per_team, rounds
                )
            ):
                schedule = {
                    'kind': 'even_factor_rows',
                    'rows': [list(row) for row in rows],
                }
                matches = _materialize_matches(
                    team_count, players_per_team, rounds, schedule
                )
                out.append(
                    Candidate(
                        f'even_i1_first_candidate_{index + 1}',
                        schedule,
                        matches,
                    )
                )
                if len(out) >= limit:
                    break

    return out


def _hint_rounds(matches: list[list[Match]], team_count: int, players_per_team: int):
    try:
        return mg._team_balanced_colour(matches, team_count, players_per_team)
    except Exception:
        return []


def _vars_from_rounds(matches: list[list[Match]], rounds: list[Round]) -> list[bool]:
    values: list[bool] = []
    for match_round, coloured_round in zip(matches, rounds, strict=True):
        oriented = set(coloured_round)
        for first, second in match_round:
            values.append((first, second) in oriented)
    return values


def _colour_with_cp_sat(
    matches: list[list[Match]],
    team_count: int,
    players_per_team: int,
    *,
    exact_s5: bool,
    timeout_seconds: float,
    workers: int,
) -> tuple[list[Round] | None, str, float]:
    from ortools.sat.python import cp_model

    start = perf_counter()
    model = cp_model.CpModel()
    variables: dict[tuple[int, int], Any] = {}
    colours_by_seat: list[list[Any | None]] = [
        [None] * len(matches) for _seat_index in range(team_count * players_per_team)
    ]
    team_white_by_round = [
        [list() for _team in range(team_count)] for _round in range(len(matches))
    ]

    for round_index, rnd in enumerate(matches):
        for match_index, (first, second) in enumerate(rnd):
            var = model.NewBoolVar(f'w_{round_index}_{match_index}')
            not_var = model.NewBoolVar(f'nw_{round_index}_{match_index}')
            model.Add(var + not_var == 1)
            variables[(round_index, match_index)] = var
            first_seat = _seat(first, players_per_team)
            second_seat = _seat(second, players_per_team)
            colours_by_seat[first_seat][round_index] = var
            colours_by_seat[second_seat][round_index] = not_var
            team_white_by_round[round_index][first[0]].append(var)
            team_white_by_round[round_index][second[0]].append(not_var)

    round_count = len(matches)
    for seat_colours in colours_by_seat:
        colours = [colour for colour in seat_colours if colour is not None]
        for round_index in range(round_count - 2):
            triple = (
                colours[round_index]
                + colours[round_index + 1]
                + colours[round_index + 2]
            )
            model.Add(triple >= 1)
            model.Add(triple <= 2)
        for prefix in range(1, round_count + 1):
            whites = sum(colours[index] for index in range(prefix))
            drift = 2 * whites - prefix
            limit = 1 if prefix == round_count else 2
            model.Add(drift <= limit)
            model.Add(drift >= -limit)

    for team in range(team_count):
        drift = 0
        for round_index in range(round_count):
            whites = sum(team_white_by_round[round_index][team])
            round_drift = 2 * whites - players_per_team
            if exact_s5:
                model.Add(round_drift == 0)
            drift += round_drift
            model.Add(drift <= 2)
            model.Add(drift >= -2)
            if (round_index + 1) % 2 == 0 or round_index + 1 == round_count:
                model.Add(drift == 0)

    hinted = _hint_rounds(matches, team_count, players_per_team)
    if hinted:
        hint_values = _vars_from_rounds(matches, hinted)
        cursor = 0
        for round_index, rnd in enumerate(matches):
            for match_index, _match in enumerate(rnd):
                model.AddHint(
                    variables[(round_index, match_index)], int(hint_values[cursor])
                )
                cursor += 1

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = timeout_seconds
    solver.parameters.num_search_workers = workers
    status = solver.Solve(model)
    elapsed = perf_counter() - start
    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return None, solver.StatusName(status), elapsed

    coloured: list[Round] = []
    for round_index, rnd in enumerate(matches):
        out: Round = []
        for match_index, (first, second) in enumerate(rnd):
            first_is_white = bool(solver.Value(variables[(round_index, match_index)]))
            out.append((first, second) if first_is_white else (second, first))
        coloured.append(out)
    return coloured, solver.StatusName(status), elapsed


def _solve_candidate_colours(
    matches: list[list[Match]],
    team_count: int,
    players_per_team: int,
    *,
    direct_colour_only: bool,
    strict_s5_timeout_seconds: float,
    timeout_seconds: float,
    workers: int,
) -> tuple[list[Round] | None, str, float]:
    if team_count % 2 == 0:
        start = perf_counter()
        try:
            direct_rounds = mg._colour_even_matches(
                matches, team_count, players_per_team
            )
        except Exception:
            direct_rounds = None
        if direct_rounds is not None:
            return direct_rounds, 'direct-even:ok', perf_counter() - start

    start = perf_counter()
    try:
        relaxed_fast_rounds = mg._colour_with_relaxed_team_balance(
            matches, team_count, players_per_team
        )
    except Exception:
        relaxed_fast_rounds = None
    if relaxed_fast_rounds is not None:
        return (
            relaxed_fast_rounds,
            'direct-relaxed-team-balance:ok',
            perf_counter() - start,
        )
    if direct_colour_only:
        return None, 'direct-colour:failed', perf_counter() - start

    if strict_s5_timeout_seconds > 0:
        strict_rounds, strict_status, strict_seconds = _colour_with_cp_sat(
            matches,
            team_count,
            players_per_team,
            exact_s5=True,
            timeout_seconds=strict_s5_timeout_seconds,
            workers=workers,
        )
        if strict_rounds is not None:
            return strict_rounds, f'strict-s5:{strict_status}', strict_seconds

    relaxed_rounds, relaxed_status, relaxed_seconds = _colour_with_cp_sat(
        matches,
        team_count,
        players_per_team,
        exact_s5=False,
        timeout_seconds=timeout_seconds,
        workers=workers,
    )
    return relaxed_rounds, f'relaxed-s5:{relaxed_status}', relaxed_seconds


def _build_case_recipe(
    team_count: int,
    players_per_team: int,
    rounds: int,
    *,
    candidate_limit: int,
    odd_phase_policies: tuple[str, ...],
    odd_colour_integrated_timeout_seconds: float,
    odd_colour_integrated_attempts: int,
    odd_colour_integrated_options_per_factor: int,
    odd_integrated_timeout_seconds: float,
    odd_integrated_attempts: int,
    odd_integrated_options_per_factor: int,
    odd_offset_candidate_limit: int,
    odd_offset_max_permutations: int,
    odd_direct_offsets_only: bool,
    odd_row_solver_timeout_seconds: float,
    odd_row_solver_attempts: int,
    direct_colour_only: bool,
    strict_s5_timeout_seconds: float,
    even_integrated_timeout_seconds: float,
    even_integrated_attempts: int,
    even_row_solver_timeout_seconds: float,
    even_row_solver_attempts: int,
    timeout_seconds: float,
    workers: int,
    emit_baseline_recipes: bool,
) -> dict[str, Any] | None:
    current_table = generate_molter_table(team_count, players_per_team, rounds)
    current_metrics = _metrics(current_table)
    best: tuple[Metrics, Candidate, list[Round], str, float] | None = None
    for candidate in _candidate_specs(
        team_count,
        players_per_team,
        rounds,
        candidate_limit,
        odd_phase_policies=odd_phase_policies,
        odd_colour_integrated_timeout_seconds=odd_colour_integrated_timeout_seconds,
        odd_colour_integrated_attempts=odd_colour_integrated_attempts,
        odd_colour_integrated_options_per_factor=(
            odd_colour_integrated_options_per_factor
        ),
        odd_integrated_timeout_seconds=odd_integrated_timeout_seconds,
        odd_integrated_attempts=odd_integrated_attempts,
        odd_integrated_options_per_factor=odd_integrated_options_per_factor,
        odd_offset_candidate_limit=odd_offset_candidate_limit,
        odd_offset_max_permutations=odd_offset_max_permutations,
        odd_direct_offsets_only=odd_direct_offsets_only,
        odd_row_solver_timeout_seconds=odd_row_solver_timeout_seconds,
        odd_row_solver_attempts=odd_row_solver_attempts,
        even_integrated_timeout_seconds=even_integrated_timeout_seconds,
        even_integrated_attempts=even_integrated_attempts,
        even_row_solver_timeout_seconds=even_row_solver_timeout_seconds,
        even_row_solver_attempts=even_row_solver_attempts,
        workers=workers,
    ):
        raw = _raw_priority(candidate.matches, team_count, players_per_team)
        if raw >= _metrics_raw_priority(current_metrics):
            continue
        if candidate.coloured is not None:
            coloured = candidate.coloured
            status = candidate.colour_status
            seconds = candidate.colour_seconds
        else:
            coloured, status, seconds = _solve_candidate_colours(
                candidate.matches,
                team_count,
                players_per_team,
                direct_colour_only=direct_colour_only,
                strict_s5_timeout_seconds=strict_s5_timeout_seconds,
                timeout_seconds=timeout_seconds,
                workers=workers,
            )
        if coloured is None:
            continue
        table = _table_from_rounds(coloured, team_count, players_per_team)
        report = verify_molter_table(table)
        if not report.ok:
            continue
        metrics = _metrics(table)
        if _metric_priority(metrics) >= _metric_priority(current_metrics):
            continue
        if best is None or _metric_priority(metrics) < _metric_priority(best[0]):
            best = (metrics, candidate, coloured, status, seconds)

    if best is None:
        if not emit_baseline_recipes:
            return None
        candidate = _baseline_candidate_from_table(current_table)
        metrics = current_metrics
        coloured = candidate.coloured
        status = candidate.colour_status
        solver_seconds = candidate.colour_seconds
        if coloured is None:
            raise ValueError('Baseline recipe inference did not preserve colours.')
    else:
        metrics, candidate, coloured, status, solver_seconds = best
    bits = _colour_bits(candidate.matches, coloured)
    return {
        'team_count': team_count,
        'players_per_team': players_per_team,
        'rounds': rounds,
        'candidate_label': candidate.label,
        'schedule': candidate.schedule,
        'colour_bit_count': len(bits),
        'colour_bits': _pack_bits(bits),
        'current_metrics': _metric_dict(current_metrics),
        'recipe_metrics': _metric_dict(metrics),
        'solver_status': status,
        'solver_seconds': solver_seconds,
    }


def _build_case_recipe_task(
    task: tuple[
        tuple[int, int, int],
        int,
        tuple[str, ...],
        float,
        int,
        int,
        bool,
        float,
        int,
        int,
        int,
        int,
        float,
        int,
        bool,
        float,
        float,
        int,
        float,
        int,
        float,
        int,
        bool,
    ],
):
    (
        (team_count, players_per_team, rounds),
        candidate_limit,
        odd_phase_policies,
        odd_colour_integrated_timeout_seconds,
        odd_colour_integrated_attempts,
        odd_colour_integrated_options_per_factor,
        odd_integrated_timeout_seconds,
        odd_integrated_attempts,
        odd_integrated_options_per_factor,
        odd_offset_candidate_limit,
        odd_offset_max_permutations,
        odd_direct_offsets_only,
        odd_row_solver_timeout_seconds,
        odd_row_solver_attempts,
        direct_colour_only,
        strict_s5_timeout_seconds,
        even_integrated_timeout_seconds,
        even_integrated_attempts,
        even_row_solver_timeout_seconds,
        even_row_solver_attempts,
        timeout_seconds,
        workers,
        emit_baseline_recipes,
    ) = task
    started = perf_counter()
    recipe = _build_case_recipe(
        team_count,
        players_per_team,
        rounds,
        candidate_limit=candidate_limit,
        odd_phase_policies=odd_phase_policies,
        odd_colour_integrated_timeout_seconds=odd_colour_integrated_timeout_seconds,
        odd_colour_integrated_attempts=odd_colour_integrated_attempts,
        odd_colour_integrated_options_per_factor=(
            odd_colour_integrated_options_per_factor
        ),
        odd_integrated_timeout_seconds=odd_integrated_timeout_seconds,
        odd_integrated_attempts=odd_integrated_attempts,
        odd_integrated_options_per_factor=odd_integrated_options_per_factor,
        odd_offset_candidate_limit=odd_offset_candidate_limit,
        odd_offset_max_permutations=odd_offset_max_permutations,
        odd_direct_offsets_only=odd_direct_offsets_only,
        odd_row_solver_timeout_seconds=odd_row_solver_timeout_seconds,
        odd_row_solver_attempts=odd_row_solver_attempts,
        direct_colour_only=direct_colour_only,
        strict_s5_timeout_seconds=strict_s5_timeout_seconds,
        even_integrated_timeout_seconds=even_integrated_timeout_seconds,
        even_integrated_attempts=even_integrated_attempts,
        even_row_solver_timeout_seconds=even_row_solver_timeout_seconds,
        even_row_solver_attempts=even_row_solver_attempts,
        timeout_seconds=timeout_seconds,
        workers=workers,
        emit_baseline_recipes=emit_baseline_recipes,
    )
    return (team_count, players_per_team, rounds), recipe, perf_counter() - started


def _strict_s5_recolour_recipe(
    case_recipe: dict[str, Any],
    *,
    timeout_seconds: float,
    workers: int,
) -> tuple[dict[str, Any] | None, str, float]:
    start = perf_counter()
    table = materialize_recipe(case_recipe)
    metrics = _metrics(table)
    if metrics.exact_s5:
        return None, 'already-exact-s5', perf_counter() - start

    team_count = int(case_recipe['team_count'])
    players_per_team = int(case_recipe['players_per_team'])
    rounds = int(case_recipe['rounds'])
    matches = _materialize_matches(
        team_count, players_per_team, rounds, case_recipe['schedule']
    )

    fast_rounds = mg._colour_with_relaxed_team_balance(
        matches, team_count, players_per_team
    )
    if fast_rounds is not None:
        fast_table = _table_from_rounds(fast_rounds, team_count, players_per_team)
        fast_metrics = _metrics(fast_table)
        if fast_metrics.exact_s5 and verify_molter_table(fast_table).ok:
            new_recipe = dict(case_recipe)
            bits = _colour_bits(matches, fast_rounds)
            new_recipe.update(
                {
                    'colour_bit_count': len(bits),
                    'colour_bits': _pack_bits(bits),
                    'recipe_metrics': _metric_dict(fast_metrics),
                    'solver_status': 'strict-s5-fast:ok',
                    'solver_seconds': perf_counter() - start,
                }
            )
            return new_recipe, 'strict-s5-fast:ok', perf_counter() - start

    if timeout_seconds <= 0:
        return None, 'strict-s5:skipped', perf_counter() - start
    strict_rounds, strict_status, strict_seconds = _colour_with_cp_sat(
        matches,
        team_count,
        players_per_team,
        exact_s5=True,
        timeout_seconds=timeout_seconds,
        workers=workers,
    )
    if strict_rounds is None:
        return None, f'strict-s5:{strict_status}', perf_counter() - start
    strict_table = _table_from_rounds(strict_rounds, team_count, players_per_team)
    report = verify_molter_table(strict_table)
    if not report.ok:
        return None, f'strict-s5:invalid:{report.errors[0]}', perf_counter() - start
    strict_metrics = _metrics(strict_table)
    if not strict_metrics.exact_s5:
        return None, 'strict-s5:not-exact-after-solve', perf_counter() - start

    new_recipe = dict(case_recipe)
    bits = _colour_bits(matches, strict_rounds)
    new_recipe.update(
        {
            'colour_bit_count': len(bits),
            'colour_bits': _pack_bits(bits),
            'recipe_metrics': _metric_dict(strict_metrics),
            'solver_status': f'strict-s5:{strict_status}',
            'solver_seconds': strict_seconds,
        }
    )
    return new_recipe, f'strict-s5:{strict_status}', perf_counter() - start


def _strict_s5_recolour_task(
    task: tuple[dict[str, Any], float, int],
) -> tuple[tuple[int, int, int], dict[str, Any] | None, str, float]:
    case_recipe, timeout_seconds, workers = task
    recipe, status, elapsed = _strict_s5_recolour_recipe(
        case_recipe,
        timeout_seconds=timeout_seconds,
        workers=workers,
    )
    return (
        (
            int(case_recipe['team_count']),
            int(case_recipe['players_per_team']),
            int(case_recipe['rounds']),
        ),
        recipe,
        status,
        elapsed,
    )


def _parse_case(value: str) -> tuple[int, int, int]:
    parts = tuple(int(part) for part in value.replace('x', ',').split(','))
    if len(parts) != 3:
        raise argparse.ArgumentTypeError('case must be N,P,R or NxPxR')
    return parts


def _load_case_file(path: Path) -> tuple[tuple[int, int, int], ...]:
    raw = json.loads(path.read_text())
    if isinstance(raw, dict):
        if 'cases' in raw:
            raw = raw['cases']
        elif 'worklists' in raw and 'i1_or_prefix' in raw['worklists']:
            raw = raw['worklists']['i1_or_prefix']
    cases = []
    for item in raw:
        if isinstance(item, str):
            cases.append(_parse_case(item))
        else:
            values = tuple(int(value) for value in item)
            if len(values) != 3:
                raise ValueError(f'Bad case entry in {path}: {item!r}')
            cases.append(values)
    return tuple(cases)


def _parse_players(value: str) -> tuple[int, ...]:
    players = tuple(int(part) for part in value.split(',') if part)
    if not players:
        raise argparse.ArgumentTypeError('players must not be empty')
    odd_players = [player_count for player_count in players if player_count % 2]
    if odd_players:
        raise argparse.ArgumentTypeError(f'players must be even; got {odd_players!r}')
    return players


def _parse_odd_phase_policies(value: str) -> tuple[str, ...]:
    allowed = {'factor', 'round_block', 'round', 'block', 'never', 'always'}
    policies = tuple(policy for policy in value.split(',') if policy)
    unknown = [policy for policy in policies if policy not in allowed]
    if unknown:
        raise argparse.ArgumentTypeError(
            f'unknown odd phase policy {unknown!r}; allowed={sorted(allowed)!r}'
        )
    return policies


def _grid_cases(
    min_team_count: int,
    max_team_count: int,
    players: tuple[int, ...],
    max_rounds: int,
    *,
    include_full_tables: bool = DEFAULT_GRID_INCLUDE_FULL_TABLES,
) -> tuple[tuple[int, int, int], ...]:
    cases: list[tuple[int, int, int]] = []
    for team_count in range(min_team_count, max_team_count + 1):
        rounds = set(range(1, min(max_rounds, team_count - 1) + 1))
        if include_full_tables:
            rounds.add(team_count - 1)
        for players_per_team in players:
            for round_count in sorted(rounds):
                cases.append((team_count, players_per_team, round_count))
    return tuple(cases)


def _case_key(case: dict[str, Any]) -> str:
    return f'{case["team_count"]}:{case["players_per_team"]}:{case["rounds"]}'


def _tuple_case_key(case: tuple[int, int, int]) -> str:
    return f'{case[0]}:{case[1]}:{case[2]}'


def _miss_entry(case: tuple[int, int, int], seconds: float) -> list[int | float]:
    return [case[0], case[1], case[2], round(seconds, 6)]


def _miss_key(miss: Any) -> str:
    if isinstance(miss, dict):
        return str(miss['key'])
    return f'{miss[0]}:{miss[1]}:{miss[2]}'


def _normalise_miss(miss: Any) -> list[int | float]:
    if isinstance(miss, dict):
        return [
            int(miss['team_count']),
            int(miss['players_per_team']),
            int(miss['rounds']),
            round(float(miss.get('seconds', 0.0)), 6),
        ]
    return [int(miss[0]), int(miss[1]), int(miss[2]), round(float(miss[3]), 6)]


def _recipe_payload(
    recipes: list[dict[str, Any]], misses: list[dict[str, Any]], args
) -> dict[str, Any]:
    return {
        'version': 1,
        'generated_at_utc': datetime.now(UTC).strftime('%Y-%m-%dT%H:%M:%SZ'),
        'description': (
            'Compact Molter solver recipes: schedule decisions plus one colour '
            'bit per board, not final pairings.'
        ),
        'builder': {
            'candidate_limit': args.candidate_limit,
            'odd_phase_policies': list(args.odd_phase_policies),
            'odd_colour_integrated_timeout_seconds': (
                args.odd_colour_integrated_timeout_seconds
            ),
            'odd_colour_integrated_attempts': args.odd_colour_integrated_attempts,
            'odd_colour_integrated_options_per_factor': (
                args.odd_colour_integrated_options_per_factor
            ),
            'odd_integrated_timeout_seconds': args.odd_integrated_timeout_seconds,
            'odd_integrated_attempts': args.odd_integrated_attempts,
            'odd_integrated_options_per_factor': (
                args.odd_integrated_options_per_factor
            ),
            'odd_offset_candidate_limit': args.odd_offset_candidate_limit,
            'odd_offset_max_permutations': args.odd_offset_max_permutations,
            'odd_direct_offsets_only': args.odd_direct_offsets_only,
            'odd_row_solver_timeout_seconds': args.odd_row_solver_timeout_seconds,
            'odd_row_solver_attempts': args.odd_row_solver_attempts,
            'direct_colour_only': args.direct_colour_only,
            'strict_s5_timeout_seconds': args.strict_s5_timeout_seconds,
            'even_integrated_timeout_seconds': (args.even_integrated_timeout_seconds),
            'even_integrated_attempts': args.even_integrated_attempts,
            'even_row_solver_timeout_seconds': (args.even_row_solver_timeout_seconds),
            'even_row_solver_attempts': args.even_row_solver_attempts,
            'timeout_seconds': args.timeout_seconds,
            'workers': args.workers,
            'case_workers': args.case_workers,
            'emit_baseline_recipes': args.emit_baseline_recipes,
        },
        'cases': recipes,
        'miss_schema': ['team_count', 'players_per_team', 'rounds', 'seconds'],
        'misses': misses,
    }


def _write_recipe_payload(
    output: Path, payload: dict[str, Any], *, pretty_json: bool
) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    tmp = output.with_suffix(output.suffix + '.tmp')
    if pretty_json:
        text = json.dumps(payload, indent=2, sort_keys=True)
    else:
        text = json.dumps(payload, separators=(',', ':'))
    tmp.write_text(text + '\n')
    tmp.replace(output)


def _write_packed_recipe_payload(output: Path, payload: dict[str, Any]) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    tmp = output.with_suffix(output.suffix + '.tmp')
    tmp.write_bytes(_pack_recipe_payload(payload))
    tmp.replace(output)


def _write_recipe_outputs(
    json_output: Path,
    packed_output: Path | None,
    payload: dict[str, Any],
    *,
    pretty_json: bool,
) -> None:
    _write_recipe_payload(json_output, payload, pretty_json=pretty_json)
    if packed_output is not None:
        _write_packed_recipe_payload(packed_output, payload)


def _load_recipe_file(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text())


def _load_recipe_payload(path: Path) -> dict[str, Any]:
    raw = path.read_bytes()
    if raw.startswith(BINARY_MAGIC):
        return _unpack_recipe_payload(raw)
    return json.loads(raw.decode())


def _load_existing_results(
    path: Path,
) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    if not path.exists():
        return {}, {}
    payload = _load_recipe_file(path)
    recipes = {}
    for case in payload.get('cases', []):
        case['recipe_metrics'] = _metric_dict(_metrics(materialize_recipe(case)))
        recipes[_case_key(case)] = case
    misses = {
        _miss_key(miss): _normalise_miss(miss) for miss in payload.get('misses', [])
    }
    return recipes, misses


def _recipe_merge_priority(
    case: dict[str, Any],
) -> tuple[int, int, int, tuple[int, ...], int, int, int, int]:
    table = materialize_recipe(case)
    metrics = _metric_dict(_metrics(table))
    case['recipe_metrics'] = metrics
    return _metric_mapping_priority(metrics)


def _merge_recipe_payload(
    payload: dict[str, Any],
    recipe_by_key: dict[str, dict[str, Any]],
    miss_by_key: dict[str, Any],
) -> tuple[int, int, int]:
    added = 0
    improved = 0
    misses_added = 0
    for case in payload.get('cases', []):
        key = _case_key(case)
        existing = recipe_by_key.get(key)
        if existing is None:
            recipe_by_key[key] = case
            miss_by_key.pop(key, None)
            added += 1
            continue
        if _recipe_merge_priority(case) < _recipe_merge_priority(existing):
            recipe_by_key[key] = case
            improved += 1
    for miss in payload.get('misses', []):
        key = _miss_key(miss)
        if key not in recipe_by_key and key not in miss_by_key:
            miss_by_key[key] = _normalise_miss(miss)
            misses_added += 1
    return added, improved, misses_added


def _store_case_result(
    recipe_by_key: dict[str, dict[str, Any]],
    miss_by_key: dict[str, Any],
    case: tuple[int, int, int],
    recipe: dict[str, Any] | None,
    case_seconds: float,
    *,
    builder_pass: str | None,
) -> None:
    key = _tuple_case_key(case)
    if recipe is None:
        if key not in recipe_by_key:
            miss_by_key[key] = _miss_entry(case, case_seconds)
        return
    if builder_pass:
        recipe['builder_pass'] = builder_pass
    existing = recipe_by_key.get(key)
    if existing is None or _recipe_merge_priority(recipe) < _recipe_merge_priority(
        existing
    ):
        recipe_by_key[key] = recipe
    miss_by_key.pop(key, None)


def _ordered_keys(
    cases: tuple[tuple[int, int, int], ...],
    *maps: dict[str, Any],
) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for case in cases:
        key = _tuple_case_key(case)
        if key not in seen:
            out.append(key)
            seen.add(key)
    for mapping in maps:
        for key in sorted(mapping):
            if key not in seen:
                out.append(key)
                seen.add(key)
    return out


def _ordered_recipes(
    cases: tuple[tuple[int, int, int], ...], recipe_by_key: dict[str, dict[str, Any]]
) -> list[dict[str, Any]]:
    return [
        recipe_by_key[key]
        for key in _ordered_keys(cases, recipe_by_key)
        if key in recipe_by_key
    ]


def _ordered_misses(
    cases: tuple[tuple[int, int, int], ...], miss_by_key: dict[str, Any]
) -> list[Any]:
    return [
        miss_by_key[key]
        for key in _ordered_keys(cases, miss_by_key)
        if key in miss_by_key
    ]


def _strict_s5_recolour_existing(
    cases: tuple[tuple[int, int, int], ...],
    recipe_by_key: dict[str, dict[str, Any]],
    miss_by_key: dict[str, Any],
    *,
    timeout_seconds: float,
    workers: int,
    case_workers: int,
    builder_pass: str | None,
    progress_every: int,
) -> tuple[int, int, int]:
    requested_keys = {_tuple_case_key(case) for case in cases}
    recipes = [
        recipe
        for key, recipe in recipe_by_key.items()
        if not requested_keys or key in requested_keys
    ]
    tasks = [(recipe, timeout_seconds, workers) for recipe in recipes]
    attempted = 0
    improved = 0
    exact_before = 0
    if case_workers <= 1:
        iterator = (_strict_s5_recolour_task(task) for task in tasks)
        for index, (case, recipe, status, elapsed) in enumerate(iterator, start=1):
            if _should_print_progress(index, len(tasks), progress_every):
                print(
                    f'[{index}/{len(tasks)}] strict-S5 {case[0]}x{case[1]} '
                    f'R{case[2]}: {status} ({elapsed:.3f}s)',
                    flush=True,
                )
            if status == 'already-exact-s5':
                exact_before += 1
                continue
            attempted += 1
            if recipe is not None:
                _store_case_result(
                    recipe_by_key,
                    miss_by_key,
                    case,
                    recipe,
                    elapsed,
                    builder_pass=builder_pass,
                )
                improved += 1
    else:
        with ProcessPoolExecutor(max_workers=case_workers) as executor:
            future_by_case = {
                executor.submit(_strict_s5_recolour_task, task): (
                    int(task[0]['team_count']),
                    int(task[0]['players_per_team']),
                    int(task[0]['rounds']),
                )
                for task in tasks
            }
            for index, future in enumerate(as_completed(future_by_case), start=1):
                case, recipe, status, elapsed = future.result()
                if _should_print_progress(index, len(tasks), progress_every):
                    print(
                        f'[{index}/{len(tasks)}] strict-S5 {case[0]}x{case[1]} '
                        f'R{case[2]}: {status} ({elapsed:.3f}s)',
                        flush=True,
                    )
                if status == 'already-exact-s5':
                    exact_before += 1
                    continue
                attempted += 1
                if recipe is not None:
                    _store_case_result(
                        recipe_by_key,
                        miss_by_key,
                        case,
                        recipe,
                        elapsed,
                        builder_pass=builder_pass,
                    )
                    improved += 1
    return len(tasks), exact_before, improved


def _default_packed_output(output: Path) -> Path:
    if output.suffix:
        return output.with_suffix('.mrec')
    return output.with_name(output.name + '.mrec')


def _replay_file(path: Path, *, details: bool) -> None:
    payload = _load_recipe_payload(path)
    total_start = perf_counter()
    for case in payload['cases']:
        start = perf_counter()
        table = materialize_recipe(case)
        replay_seconds = perf_counter() - start
        report = verify_molter_table(table)
        metrics = _metrics(table)
        if details or not report.ok:
            print(
                f'{case["team_count"]}x{case["players_per_team"]} '
                f'R{case["rounds"]}: replay={replay_seconds:.6f}s '
                f'verify={"ok" if report.ok else "FAIL"} '
                f'I1={metrics.i1} I1-prefix={metrics.i1_prefix_deficit}'
            )
        if not report.ok:
            raise SystemExit(report.errors[:3])
    print(
        f'Replayed {len(payload["cases"])} recipes in {perf_counter() - total_start:.6f}s'
    )


def _should_print_progress(index: int, total: int, every: int) -> bool:
    if every <= 0:
        return False
    return index == 1 or index == total or index % every == 0


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output_path', nargs='?', type=Path)
    parser.add_argument('--output', type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument('--case', action='append', type=_parse_case)
    parser.add_argument(
        '--case-file',
        type=Path,
        help='JSON list of N/P/R cases, or an audit JSON with worklists.i1_or_prefix.',
    )
    parser.add_argument(
        '--merge-input',
        action='append',
        type=Path,
        help=(
            'Merge recipes/misses from another JSON or .mrec file before solving. '
            'When duplicate recipes exist, the best recipe_metrics tuple wins.'
        ),
    )
    parser.add_argument(
        '--merge-only',
        action='store_true',
        help='Only merge existing --merge-input files into --output; do not solve cases.',
    )
    parser.add_argument(
        '--ignore-existing-output',
        action='store_true',
        help=(
            'Start from an empty output state before applying --merge-input. '
            'Used by the reproducible suite so stale final artifacts cannot '
            'silently carry recipes forward.'
        ),
    )
    parser.add_argument(
        '--prune-output-to-cases',
        action='store_true',
        help='Drop existing recipes/misses outside the requested case list.',
    )
    parser.add_argument(
        '--quality-grid',
        action='store_true',
        help=(
            'Use the recipe target grid: N=3..25, P=2,4,6,8,10,12, R=1..13 by default.'
        ),
    )
    parser.add_argument(
        '--max-team-count',
        type=int,
        default=DEFAULT_GRID_MAX_TEAM_COUNT,
        help='Maximum N for --quality-grid.',
    )
    parser.add_argument(
        '--min-team-count',
        type=int,
        default=DEFAULT_GRID_MIN_TEAM_COUNT,
        help='Minimum N for --quality-grid.',
    )
    parser.add_argument(
        '--players',
        type=_parse_players,
        default=DEFAULT_GRID_PLAYERS,
        help='Comma-separated even P values for --quality-grid.',
    )
    parser.add_argument(
        '--max-short-rounds',
        type=int,
        default=DEFAULT_GRID_MAX_ROUNDS,
        help='Maximum R for --quality-grid.',
    )
    parser.add_argument(
        '--include-full-tables',
        action='store_true',
        default=DEFAULT_GRID_INCLUDE_FULL_TABLES,
        help='Also include each full table R=N-1 in --quality-grid.',
    )
    parser.add_argument('--candidate-limit', type=int, default=8)
    parser.add_argument(
        '--odd-phase-policies',
        type=_parse_odd_phase_policies,
        default=(),
        help=(
            'Comma-separated explicit odd-cell phase policies to try, e.g. '
            'round_block,factor. Empty by default for the fast baseline path.'
        ),
    )
    parser.add_argument(
        '--direct-colour-only',
        action='store_true',
        help=(
            'Only accept candidates colourable by the direct deterministic '
            'colourers; skip CP-SAT colouring.'
        ),
    )
    parser.add_argument('--strict-s5-timeout-seconds', type=float, default=1.0)
    parser.add_argument(
        '--odd-colour-integrated-timeout-seconds',
        type=float,
        default=0.0,
        help=(
            'Optional CP-SAT time budget for an odd-team search that chooses '
            'schedule and colours in one hard-constraint model.'
        ),
    )
    parser.add_argument(
        '--odd-colour-integrated-attempts',
        type=int,
        default=0,
        help='Number of colour-integrated odd-team searches to try per case.',
    )
    parser.add_argument(
        '--odd-colour-integrated-options-per-factor',
        type=int,
        default=8,
        help=(
            'Dropped-edge/phase options retained per factor in the '
            'colour-integrated odd search.'
        ),
    )
    parser.add_argument(
        '--odd-integrated-timeout-seconds',
        type=float,
        default=0.0,
        help=(
            'Optional CP-SAT time budget for an integrated odd-team search '
            'that chooses factors, dropped edges, and phase bits together.'
        ),
    )
    parser.add_argument(
        '--odd-integrated-attempts',
        type=int,
        default=0,
        help='Number of integrated odd-team searches to try per case.',
    )
    parser.add_argument(
        '--odd-integrated-options-per-factor',
        type=int,
        default=8,
        help='Dropped-edge/phase options retained per factor in integrated odd search.',
    )
    parser.add_argument(
        '--odd-offset-candidate-limit',
        type=int,
        default=0,
        help=(
            'Offline-only override for the number of odd block-offset patterns '
            'to try. 0 keeps the app generator default.'
        ),
    )
    parser.add_argument(
        '--odd-offset-max-permutations',
        type=int,
        default=750_000,
        help=(
            'Maximum offset permutations to enumerate exactly when '
            '--odd-offset-candidate-limit is non-zero.'
        ),
    )
    parser.add_argument(
        '--odd-direct-offsets-only',
        action='store_true',
        help=(
            'For widened odd offset searches, build direct occurrence schedules '
            'from the offset patterns and skip the heavier per-offset floater '
            'local optimizer.'
        ),
    )
    parser.add_argument(
        '--odd-row-solver-timeout-seconds',
        type=float,
        default=0.0,
        help=(
            'Optional CP-SAT time budget for constructing prefix-perfect '
            'odd-team factor rows before dropped-edge repair and colouring.'
        ),
    )
    parser.add_argument(
        '--odd-row-solver-attempts',
        type=int,
        default=0,
        help='Number of no-good-excluded odd-team row candidates to try.',
    )
    parser.add_argument(
        '--even-row-solver-timeout-seconds',
        type=float,
        default=0.0,
        help=(
            'Optional CP-SAT time budget for constructing prefix-perfect '
            'even-team factor rows before colouring.'
        ),
    )
    parser.add_argument(
        '--even-row-solver-attempts',
        type=int,
        default=1,
        help='Number of no-good-excluded even-team row candidates to try.',
    )
    parser.add_argument(
        '--even-integrated-timeout-seconds',
        type=float,
        default=0.0,
        help=(
            'Optional CP-SAT time budget for constructing and colour-testing '
            'even-team factor rows in one no-good loop.'
        ),
    )
    parser.add_argument(
        '--even-integrated-attempts',
        type=int,
        default=0,
        help='Number of integrated even-team searches to try per case.',
    )
    parser.add_argument('--timeout-seconds', type=float, default=20.0)
    parser.add_argument('--workers', type=int, default=8)
    parser.add_argument('--case-workers', type=int, default=1)
    parser.add_argument(
        '--emit-baseline-recipes',
        action='store_true',
        help=(
            'For cases with no better solver recipe, infer and write a compact '
            'recipe for the current validated table so replay remains '
            'generator-free.'
        ),
    )
    parser.add_argument(
        '--strict-s5-recolour-existing',
        action='store_true',
        help=(
            'Do not build new schedules; try to recolour existing recipes with '
            'exact per-round S5 and keep the upgrade only when other metrics '
            'are unchanged or better.'
        ),
    )
    parser.add_argument(
        '--packed-output',
        type=Path,
        help=(
            'Write a compact replay artifact. Defaults to the JSON output path '
            'with .mrec extension.'
        ),
    )
    parser.add_argument(
        '--no-packed-output',
        action='store_true',
        help='Only write the readable JSON recipe file.',
    )
    parser.add_argument(
        '--pretty-json',
        action='store_true',
        help='Write indented JSON for manual inspection instead of compact JSON.',
    )
    parser.add_argument(
        '--builder-pass',
        help='Optional deterministic suite pass name to stamp on newly built recipes.',
    )
    parser.add_argument(
        '--progress-every',
        type=int,
        default=50,
        help='Print one progress line every N completed cases; use 0 to silence.',
    )
    parser.add_argument(
        '--show-misses',
        action='store_true',
        help='Print every no-improvement case in the final summary.',
    )
    parser.add_argument(
        '--replay-details',
        action='store_true',
        help='Print every replayed recipe after verification.',
    )
    parser.add_argument(
        '--force',
        action='store_true',
        help='Recompute requested cases even if they already exist in the output file.',
    )
    parser.add_argument('--replay', type=Path)
    args = parser.parse_args()

    if args.replay is not None:
        _replay_file(args.replay, details=args.replay_details)
        return

    if args.output_path is not None:
        args.output = args.output_path
    packed_output = (
        None
        if args.no_packed_output
        else args.packed_output or _default_packed_output(args.output)
    )

    if args.quality_grid:
        cases = _grid_cases(
            args.min_team_count,
            args.max_team_count,
            args.players,
            args.max_short_rounds,
            include_full_tables=args.include_full_tables,
        )
        if args.case:
            cases = (*cases, *args.case)
        if args.case_file:
            cases = (*cases, *_load_case_file(args.case_file))
    else:
        file_cases = _load_case_file(args.case_file) if args.case_file else ()
        explicit_cases = tuple(args.case) if args.case else ()
        cases = (
            (*file_cases, *explicit_cases)
            if file_cases or explicit_cases
            else DEFAULT_CASES
        )
    if args.ignore_existing_output:
        recipe_by_key, miss_by_key = {}, {}
    else:
        recipe_by_key, miss_by_key = _load_existing_results(args.output)
    if args.merge_input:
        for path in args.merge_input:
            added, improved, misses_added = _merge_recipe_payload(
                _load_recipe_payload(path), recipe_by_key, miss_by_key
            )
            print(
                f'Merged {path}: {added} new, {improved} improved, '
                f'{misses_added} miss(es).'
            )
    if args.prune_output_to_cases:
        requested_keys = {_tuple_case_key(case) for case in cases}
        recipe_by_key = {
            key: recipe
            for key, recipe in recipe_by_key.items()
            if key in requested_keys
        }
        miss_by_key = {
            key: miss for key, miss in miss_by_key.items() if key in requested_keys
        }
    if args.merge_only:
        payload = _recipe_payload(
            _ordered_recipes(cases, recipe_by_key),
            _ordered_misses(cases, miss_by_key),
            args,
        )
        _write_recipe_outputs(
            args.output, packed_output, payload, pretty_json=args.pretty_json
        )
        written = f'Wrote {args.output} ({args.output.stat().st_size} bytes)'
        if packed_output is not None:
            written += (
                f', packed {packed_output} ({packed_output.stat().st_size} bytes)'
            )
        print(f'{written} ({len(payload["cases"])} recipe(s)).')
        _replay_file(packed_output or args.output, details=args.replay_details)
        return
    if args.strict_s5_recolour_existing:
        started = perf_counter()
        total, exact_before, improved = _strict_s5_recolour_existing(
            cases,
            recipe_by_key,
            miss_by_key,
            timeout_seconds=args.strict_s5_timeout_seconds,
            workers=args.workers,
            case_workers=args.case_workers,
            builder_pass=args.builder_pass,
            progress_every=args.progress_every,
        )
        payload = _recipe_payload(
            _ordered_recipes(cases, recipe_by_key),
            _ordered_misses(cases, miss_by_key),
            args,
        )
        _write_recipe_outputs(
            args.output, packed_output, payload, pretty_json=args.pretty_json
        )
        written = f'Wrote {args.output} ({args.output.stat().st_size} bytes)'
        if packed_output is not None:
            written += (
                f', packed {packed_output} ({packed_output.stat().st_size} bytes)'
            )
        print(
            f'{written} in {perf_counter() - started:.3f}s '
            f'({total} recipe(s), {exact_before} already exact-S5, '
            f'{improved} strict-S5 upgrade(s)).'
        )
        _replay_file(packed_output or args.output, details=args.replay_details)
        return
    started = perf_counter()
    pending_cases = [
        case
        for case in cases
        if args.force
        or (
            _tuple_case_key(case) not in recipe_by_key
            and _tuple_case_key(case) not in miss_by_key
        )
    ]
    skipped = len(cases) - len(pending_cases)
    if skipped:
        print(f'Skipping {skipped} completed case(s); use --force to recompute.')

    tasks = [
        (
            case,
            args.candidate_limit,
            args.odd_phase_policies,
            args.odd_colour_integrated_timeout_seconds,
            args.odd_colour_integrated_attempts,
            args.odd_colour_integrated_options_per_factor,
            args.odd_integrated_timeout_seconds,
            args.odd_integrated_attempts,
            args.odd_integrated_options_per_factor,
            args.odd_offset_candidate_limit,
            args.odd_offset_max_permutations,
            args.odd_direct_offsets_only,
            args.odd_row_solver_timeout_seconds,
            args.odd_row_solver_attempts,
            args.direct_colour_only,
            args.strict_s5_timeout_seconds,
            args.even_integrated_timeout_seconds,
            args.even_integrated_attempts,
            args.even_row_solver_timeout_seconds,
            args.even_row_solver_attempts,
            args.timeout_seconds,
            args.workers,
            args.emit_baseline_recipes,
        )
        for case in pending_cases
    ]
    results: list[tuple[tuple[int, int, int], dict[str, Any] | None, float]] = []
    if args.case_workers <= 1:
        for index, task in enumerate(tasks, start=1):
            team_count, players_per_team, rounds = task[0]
            if _should_print_progress(index, len(tasks), args.progress_every):
                print(
                    f'[{index}/{len(tasks)}] {team_count}x{players_per_team} R{rounds}',
                    flush=True,
                )
            case, recipe, case_seconds = _build_case_recipe_task(task)
            results.append((case, recipe, case_seconds))
            _store_case_result(
                recipe_by_key,
                miss_by_key,
                case,
                recipe,
                case_seconds,
                builder_pass=args.builder_pass,
            )
            _write_recipe_outputs(
                args.output,
                packed_output,
                _recipe_payload(
                    _ordered_recipes(cases, recipe_by_key),
                    _ordered_misses(cases, miss_by_key),
                    args,
                ),
                pretty_json=args.pretty_json,
            )
    else:
        with ProcessPoolExecutor(max_workers=args.case_workers) as executor:
            future_by_case = {
                executor.submit(_build_case_recipe_task, task): task[0]
                for task in tasks
            }
            for index, future in enumerate(as_completed(future_by_case), start=1):
                case = future_by_case[future]
                if _should_print_progress(index, len(tasks), args.progress_every):
                    print(
                        f'[{index}/{len(tasks)}] finished '
                        f'{case[0]}x{case[1]} R{case[2]}',
                        flush=True,
                    )
                result_case, recipe, case_seconds = future.result()
                results.append((result_case, recipe, case_seconds))
                _store_case_result(
                    recipe_by_key,
                    miss_by_key,
                    result_case,
                    recipe,
                    case_seconds,
                    builder_pass=args.builder_pass,
                )
                _write_recipe_outputs(
                    args.output,
                    packed_output,
                    _recipe_payload(
                        _ordered_recipes(cases, recipe_by_key),
                        _ordered_misses(cases, miss_by_key),
                        args,
                    ),
                    pretty_json=args.pretty_json,
                )

    result_by_case = {case: (recipe, seconds) for case, recipe, seconds in results}
    for team_count, players_per_team, rounds in pending_cases:
        recipe, case_seconds = result_by_case[(team_count, players_per_team, rounds)]
        if recipe is None:
            if args.show_misses:
                print(
                    f'  {team_count}x{players_per_team} R{rounds}: '
                    f'no recipe improvement found ({case_seconds:.3f}s)',
                    flush=True,
                )
            continue
        print(
            f'  {team_count}x{players_per_team} R{rounds}: recipe '
            f'I1 {recipe["current_metrics"]["i1"]}->{recipe["recipe_metrics"]["i1"]}, '
            f'I1-prefix '
            f'{recipe["current_metrics"]["i1_prefix_deficit"]}->'
            f'{recipe["recipe_metrics"]["i1_prefix_deficit"]}, '
            f'bits={recipe["colour_bit_count"]}, '
            f'solver={recipe["solver_seconds"]:.3f}s, '
            f'case={case_seconds:.3f}s',
            flush=True,
        )

    recipes = _ordered_recipes(cases, recipe_by_key)
    misses = _ordered_misses(cases, miss_by_key)
    payload = _recipe_payload(recipes, misses, args)
    _write_recipe_outputs(
        args.output, packed_output, payload, pretty_json=args.pretty_json
    )
    written = f'Wrote {args.output} ({args.output.stat().st_size} bytes)'
    if packed_output is not None:
        written += f', packed {packed_output} ({packed_output.stat().st_size} bytes)'
    print(
        f'{written} '
        f'in {perf_counter() - started:.3f}s '
        f'({len(recipes)} recipe(s), {len(misses)} miss(es)).'
    )
    _replay_file(packed_output or args.output, details=args.replay_details)


if __name__ == '__main__':
    main()
