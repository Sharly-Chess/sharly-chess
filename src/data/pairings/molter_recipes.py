"""Runtime replay for packed Molter recipe tables.

The expensive search lives in the technical-appendix builder. The app loads the
packed recipe artifact produced by that builder and replays it into a
``FixedPairingTable``. Missing shapes deliberately return ``None`` so the fixed
table engine can reject unsupported tournaments instead of falling back to live
Molter search.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

from data.pairings.fixed_table import FixedPairingTable
from data.pairings.molter_recipe_replay import (
    _emit,
    _even_matches_from_factor_rows,
    _one_odd_cell_matches,
    _one_odd_factorization,
    _small_one_odd_factorization,
)

_BINARY_MAGIC_V1 = b'MLTRCP\x01'
_BINARY_MAGIC_V2 = b'MLTRCP\x02'
MAX_APP_MOLTER_TEAM_COUNT = 20
_SCHEDULE_KINDS_BY_ID = {
    1: 'odd_cell_drops',
    2: 'even_factor_rows',
    3: 'odd_cell_occurrences',
}
_DEFAULT_RECIPE_FILE = Path(__file__).with_name('resources') / 'molter_recipes.mrec'

_Player = tuple[int, int]
_Match = tuple[_Player, _Player]
_Round = list[tuple[_Player, _Player]]


class MolterRecipeError(Exception):
    """Raised when the packed Molter recipe artifact cannot be replayed."""


@dataclass(frozen=True)
class _RecipeCase:
    team_count: int
    players_per_team: int
    rounds: int
    schedule: dict[str, Any]
    colour_bit_count: int
    colour_bytes: bytes


def _read_varint(raw: bytes, offset: int) -> tuple[int, int]:
    shift = 0
    value = 0
    while True:
        if offset >= len(raw):
            raise MolterRecipeError('Unexpected end of packed Molter recipe data.')
        byte = raw[offset]
        offset += 1
        value |= (byte & 0x7F) << shift
        if byte < 0x80:
            return value, offset
        shift += 7
        if shift > 63:
            raise MolterRecipeError('Packed Molter recipe varint is too large.')


def _read_schedule(
    raw: bytes, offset: int, *, packed_version: int
) -> tuple[dict[str, Any], int]:
    kind_id, offset = _read_varint(raw, offset)
    kind = _SCHEDULE_KINDS_BY_ID.get(kind_id)
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
                    'dropped': (dropped_first, dropped_second),
                }
            )
        return {
            'kind': kind,
            'offsets': tuple(offsets),
            'cell_drops': cell_drops,
        }, offset
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
                    'dropped': (dropped_first, dropped_second),
                    'reverse': bool(reverse),
                    'team_shift': team_shift,
                }
            )
        return {'kind': kind, 'cells': cells}, offset
    if kind == 'even_factor_rows':
        row_count, offset = _read_varint(raw, offset)
        row_width, offset = _read_varint(raw, offset)
        rows: list[tuple[int, ...]] = []
        for _row_index in range(row_count):
            row: list[int] = []
            for _column in range(row_width):
                factor_index, offset = _read_varint(raw, offset)
                row.append(factor_index)
            rows.append(tuple(row))
        return {'kind': kind, 'rows': tuple(rows)}, offset
    raise MolterRecipeError(
        f'Unsupported packed Molter recipe schedule kind {kind_id}.'
    )


def _read_colour_payload(raw: bytes, offset: int) -> tuple[int, bytes, int]:
    bit_count, offset = _read_varint(raw, offset)
    byte_count = (bit_count + 7) // 8
    end = offset + byte_count
    if end > len(raw):
        raise MolterRecipeError('Packed Molter recipe colour payload is truncated.')
    return bit_count, raw[offset:end], end


def _unpack_recipe_cases(raw: bytes) -> tuple[_RecipeCase, ...]:
    if raw.startswith(_BINARY_MAGIC_V2):
        packed_version = 2
        offset = len(_BINARY_MAGIC_V2)
    elif raw.startswith(_BINARY_MAGIC_V1):
        packed_version = 1
        offset = len(_BINARY_MAGIC_V1)
    else:
        raise MolterRecipeError('Not a packed Molter recipe file.')

    case_count, offset = _read_varint(raw, offset)
    cases: list[_RecipeCase] = []
    for _case_index in range(case_count):
        team_count, offset = _read_varint(raw, offset)
        players_per_team, offset = _read_varint(raw, offset)
        rounds, offset = _read_varint(raw, offset)
        schedule, offset = _read_schedule(raw, offset, packed_version=packed_version)
        colour_bit_count, colour_bytes, offset = _read_colour_payload(raw, offset)
        cases.append(
            _RecipeCase(
                team_count=team_count,
                players_per_team=players_per_team,
                rounds=rounds,
                schedule=schedule,
                colour_bit_count=colour_bit_count,
                colour_bytes=colour_bytes,
            )
        )
    if offset != len(raw):
        raise MolterRecipeError('Packed Molter recipe file has trailing bytes.')
    return tuple(cases)


@lru_cache(maxsize=1)
def _recipe_cases() -> dict[tuple[int, int, int], _RecipeCase]:
    try:
        cases = _unpack_recipe_cases(_DEFAULT_RECIPE_FILE.read_bytes())
    except OSError as exc:
        raise MolterRecipeError(
            f'Molter recipe resource not found: {_DEFAULT_RECIPE_FILE}'
        ) from exc
    return {
        (case.team_count, case.players_per_team, case.rounds): case for case in cases
    }


def _case_for(
    team_count: int, players_per_team: int, rounds: int | None
) -> _RecipeCase | None:
    if team_count > MAX_APP_MOLTER_TEAM_COUNT:
        return None
    cases = _recipe_cases()
    if rounds is not None:
        exact = cases.get((team_count, players_per_team, rounds))
        if exact is not None:
            return exact
    available = [
        case
        for case in cases.values()
        if case.team_count == team_count and case.players_per_team == players_per_team
    ]
    if not available:
        return None
    return max(available, key=lambda case: case.rounds)


def supported_molter_recipe_team_counts() -> tuple[int, ...]:
    """Team counts exposed by the app-quality Molter recipe gate."""
    try:
        return tuple(
            sorted(
                {
                    team_count
                    for team_count, _players, _rounds in _recipe_cases()
                    if team_count <= MAX_APP_MOLTER_TEAM_COUNT
                }
            )
        )
    except MolterRecipeError:
        return ()


def available_molter_recipe_rounds(
    team_count: int, players_per_team: int
) -> tuple[int, ...]:
    """Round counts covered for an exact ``(N, P)`` recipe shape."""
    if team_count > MAX_APP_MOLTER_TEAM_COUNT:
        return ()
    return tuple(
        sorted(
            rounds
            for n, p, rounds in _recipe_cases()
            if n == team_count and p == players_per_team
        )
    )


def _colour_bits(case: _RecipeCase) -> list[bool]:
    return [
        bool(case.colour_bytes[index // 8] & (1 << (index % 8)))
        for index in range(case.colour_bit_count)
    ]


def _shift_match(match: _Match, team_count: int, shift: int) -> _Match:
    if shift % team_count == 0:
        return match
    return (
        ((match[0][0] + shift) % team_count, match[0][1]),
        ((match[1][0] + shift) % team_count, match[1][1]),
    )


def _shift_matches(matches: list[_Match], team_count: int, shift: int) -> list[_Match]:
    return [_shift_match(match, team_count, shift) for match in matches]


def _one_odd_factors(team_count: int) -> tuple[tuple[tuple[int, int], ...], ...]:
    factors = _one_odd_factorization(team_count) or _small_one_odd_factorization(
        team_count
    )
    if factors is None:
        raise MolterRecipeError(f'No one-odd factorization for {team_count} teams.')
    return factors


def _materialize_matches(case: _RecipeCase) -> list[list[_Match]]:
    schedule = case.schedule
    kind = schedule['kind']
    team_count = case.team_count
    if kind == 'odd_cell_drops':
        factors = _one_odd_factors(team_count)
        offsets = tuple(schedule['offsets'])
        drops = {
            (entry['block'], entry['factor']): tuple(entry['dropped'])
            for entry in schedule['cell_drops']
        }
        seen: dict[tuple[int, int], int] = {}
        out: list[list[_Match]] = []
        half = (team_count - 1) // 2
        for round_index in range(case.rounds):
            rnd: list[_Match] = []
            for block, offset in enumerate(offsets):
                factor_index = (round_index + offset) % half
                key = (block, factor_index)
                phase = seen.get(key, 0)
                seen[key] = phase + 1
                rnd.extend(
                    _one_odd_cell_matches(
                        team_count,
                        factors[factor_index],
                        drops[key],
                        2 * block,
                        2 * block + 1,
                        phase % 2 == 1,
                    )
                )
            out.append(rnd)
        return out
    if kind == 'odd_cell_occurrences':
        factors = _one_odd_factors(team_count)
        block_count = case.players_per_team // 2
        cells = schedule['cells']
        expected_cells = case.rounds * block_count
        if len(cells) != expected_cells:
            raise MolterRecipeError(
                f'Odd occurrence recipe has {len(cells)} cells, '
                f'expected {expected_cells}.'
            )
        out: list[list[_Match]] = []
        cursor = 0
        for _round_index in range(case.rounds):
            rnd: list[_Match] = []
            for block in range(block_count):
                entry = cells[cursor]
                cursor += 1
                cell_matches = _one_odd_cell_matches(
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
        return _even_matches_from_factor_rows(team_count, tuple(schedule['rows']))
    raise MolterRecipeError(f'Unsupported Molter recipe schedule kind: {kind}')


def _apply_colour_bits(matches: list[list[_Match]], bits: list[bool]) -> list[_Round]:
    out: list[_Round] = []
    cursor = 0
    for rnd in matches:
        coloured: _Round = []
        for first, second in rnd:
            if cursor >= len(bits):
                raise MolterRecipeError('Molter recipe colour payload is too short.')
            coloured.append((first, second) if bits[cursor] else (second, first))
            cursor += 1
        out.append(coloured)
    if cursor != len(bits):
        raise MolterRecipeError('Molter recipe colour payload has unused bits.')
    return out


def _table_from_rounds(
    rounds: list[_Round], team_count: int, players_per_team: int
) -> FixedPairingTable:
    return FixedPairingTable(
        team_count=team_count,
        players_per_team=players_per_team,
        rounds=tuple(_emit(rnd) for rnd in rounds),
    )


def get_molter_recipe_table(
    team_count: int, players_per_team: int, rounds: int | None = None
) -> FixedPairingTable | None:
    """Return the exact recipe table when present, otherwise the max table.

    The max-table fallback lets caller validation report the available round
    limit for a covered ``(N, P)`` shape. If ``(N, P)`` itself is missing, this
    returns ``None``.
    """
    case = _case_for(team_count, players_per_team, rounds)
    if case is None:
        return None
    matches = _materialize_matches(case)
    coloured = _apply_colour_bits(matches, _colour_bits(case))
    return _table_from_rounds(coloured, team_count, players_per_team)


def iter_molter_recipe_tables() -> tuple[FixedPairingTable, ...]:
    """Materialize every app-exposed recipe table, primarily for validation tests."""
    return tuple(
        _table_from_rounds(
            _apply_colour_bits(_materialize_matches(case), _colour_bits(case)),
            case.team_count,
            case.players_per_team,
        )
        for case in _recipe_cases().values()
        if case.team_count <= MAX_APP_MOLTER_TEAM_COUNT
    )
