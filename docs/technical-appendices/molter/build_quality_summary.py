#!/usr/bin/env python3
"""Build one Molter recipe validation, timing, and quality workbook.

By default this audits the checked-in recipe artifact, filtered to:
    N <= 50
    P = even values 2..12
    R <= 14

The workbook is intentionally decision-oriented: it keeps the full row-level
data, but also adds matrix views and rollups so weak ideals and slow cases are
visible without manually filtering thousands of rows.
"""

from __future__ import annotations

import argparse
import multiprocessing
import os
import sys
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from time import perf_counter
from typing import Iterable

ROOT = Path(__file__).resolve().parents[3]
SRC_DIR = ROOT / 'src'
THIS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SRC_DIR))
sys.path.insert(0, str(THIS_DIR))

import xlsxwriter  # noqa: E402

import build_solver_recipes as recipes  # noqa: E402
from data.pairings.fixed_table import FixedPairingTable  # noqa: E402
from data.pairings.molter_verifier import verify_molter_table  # noqa: E402


DEFAULT_OUTPUT = Path(__file__).resolve().parent / 'molter_quality_summary.xlsx'
DEFAULT_RECIPE_FILE = (
    SRC_DIR / 'data' / 'pairings' / 'resources' / 'molter_recipes.mrec'
)
DEFAULT_PLAYERS = tuple(range(2, 13, 2))
DEFAULT_SHORT_ROUNDS = 14
_RECIPE_BY_KEY: dict[tuple[int, int, int], dict] = {}
_RECIPE_FILE: Path | None = None


@dataclass(frozen=True)
class QualityMetrics:
    board_count: int
    i1: int
    i1_prefix_deficit: int
    i2_l1: int
    i3: int
    i4: int
    i5: int
    exact_s5: bool
    max_team_colour_drift: int
    max_player_colour_drift: int
    max_same_colour_run: int


@dataclass(frozen=True)
class CaseResult:
    team_count: int
    players_per_team: int
    rounds: int
    generated: bool
    valid: bool
    generation_seconds: float
    verification_seconds: float
    total_seconds: float
    metrics: QualityMetrics | None
    verifier_notes: tuple[str, ...]
    error: str


@dataclass(frozen=True)
class ScoredCase:
    case: CaseResult
    i1_lower_bound: int | None
    i1_gap_to_bound: int | None
    quality_score: int
    quality_grade: str
    worst_signal: str
    i2_band: str
    i4_target_applies: bool


def _letter(team_index: int) -> str:
    return chr(ord('A') + team_index)


def _load_recipe_file(path: Path | None) -> None:
    global _RECIPE_FILE
    recipe_path = path if path is not None else DEFAULT_RECIPE_FILE
    if not recipe_path.exists():
        raise FileNotFoundError(f'Molter recipe artifact not found: {recipe_path}')
    payload = recipes._load_recipe_payload(recipe_path)
    _RECIPE_BY_KEY.clear()
    for case in payload.get('cases', []):
        _RECIPE_BY_KEY[
            (
                int(case['team_count']),
                int(case['players_per_team']),
                int(case['rounds']),
            )
        ] = case
    _RECIPE_FILE = recipe_path


def _recipe_cases(
    *, max_team_count: int, players: Iterable[int], max_short_rounds: int
) -> list[tuple[int, int, int]]:
    player_set = set(players)
    return [
        key
        for key in sorted(_RECIPE_BY_KEY)
        if key[0] <= max_team_count
        and key[1] in player_set
        and key[2] <= max_short_rounds
    ]


def _initialise_recipe_worker(recipe_file: Path | None) -> None:
    if recipe_file is not None:
        _load_recipe_file(recipe_file)


def _generate_table(team_count: int, players_per_team: int, rounds: int):
    recipe = _RECIPE_BY_KEY.get((team_count, players_per_team, rounds))
    if recipe is None:
        raise ValueError(
            f'No recipe for {team_count} teams, {players_per_team} players, '
            f'{rounds} rounds.'
        )
    return recipes.materialize_recipe(recipe)


def _quality_metrics(table: FixedPairingTable) -> QualityMetrics:
    team_count = table.team_count
    players_per_team = table.players_per_team
    rounds = table.rounds
    index = {_letter(team): team for team in range(team_count)}
    round_pairs = (len(rounds) + 1) // 2
    down = [0] * team_count
    up = [0] * team_count
    pair = [[0] * team_count for _team in range(team_count)]
    prefix_mask = [0] * team_count
    rp_down = [[0] * team_count for _round_pair in range(round_pairs)]
    rp_up = [[0] * team_count for _round_pair in range(round_pairs)]
    player_white_counts = [0] * (team_count * players_per_team)
    player_colour_runs = [0] * (team_count * players_per_team)
    previous_colour = [-1] * (team_count * players_per_team)
    team_colour_drift = [0] * team_count
    i5 = 0
    prefix_deficit = 0
    exact_s5 = True
    max_team_colour_drift = 0
    max_player_colour_drift = 0
    max_same_colour_run = 0

    for r_index, round_ in enumerate(rounds):
        round_pair = r_index // 2
        opponents = [[0] * team_count for _team in range(team_count)]
        round_team_white = [0] * team_count
        round_team_black = [0] * team_count
        for pairing in round_:
            white = index[pairing.white_team]
            black = index[pairing.black_team]
            pair[white][black] += 1
            pair[black][white] += 1
            opponents[white][black] += 1
            opponents[black][white] += 1
            prefix_mask[white] |= 1 << black
            prefix_mask[black] |= 1 << white
            round_team_white[white] += 1
            round_team_black[black] += 1

            white_seat = white * players_per_team + pairing.white_index - 1
            black_seat = black * players_per_team + pairing.black_index - 1
            player_white_counts[white_seat] += 1
            for seat, colour in ((white_seat, 1), (black_seat, 0)):
                if previous_colour[seat] == colour:
                    player_colour_runs[seat] += 1
                else:
                    player_colour_runs[seat] = 1
                previous_colour[seat] = colour
                max_same_colour_run = max(max_same_colour_run, player_colour_runs[seat])

            if pairing.white_index != pairing.black_index:
                if pairing.white_index < pairing.black_index:
                    descend, ascend = white, black
                else:
                    descend, ascend = black, white
                down[descend] += 1
                up[ascend] += 1
                rp_down[round_pair][descend] += 1
                rp_up[round_pair][ascend] += 1

        for team in range(team_count):
            counts = [
                opponents[team][opponent]
                for opponent in range(team_count)
                if opponents[team][opponent]
            ]
            if counts:
                i5 = max(i5, max(counts) - min(counts))

        expected_distinct = min(team_count - 1, players_per_team * (r_index + 1))
        for team in range(team_count):
            prefix_deficit = max(
                prefix_deficit, expected_distinct - prefix_mask[team].bit_count()
            )

        target_team_white = players_per_team // 2
        for team in range(team_count):
            if (
                round_team_white[team] != target_team_white
                or round_team_black[team] != target_team_white
            ):
                exact_s5 = False
            team_colour_drift[team] += round_team_white[team] - round_team_black[team]
            max_team_colour_drift = max(
                max_team_colour_drift, abs(team_colour_drift[team])
            )

        for seat, whites in enumerate(player_white_counts):
            played = r_index + 1
            blacks = played - whites
            max_player_colour_drift = max(max_player_colour_drift, abs(whites - blacks))

    i1 = 0
    for team in range(team_count):
        counts = [
            pair[team][opponent]
            for opponent in range(team_count)
            if pair[team][opponent]
        ]
        if counts:
            i1 = max(i1, max(counts) - min(counts))
    i3 = max(down) - min(down)
    i2_l1 = sum(abs(up[team] - down[team]) for team in range(team_count))
    i4 = max(
        (
            max(rp_down[round_pair][team], rp_up[round_pair][team])
            for round_pair in range(round_pairs)
            for team in range(team_count)
        ),
        default=0,
    )
    board_count = len(rounds[0]) if rounds else 0
    return QualityMetrics(
        board_count=board_count,
        i1=i1,
        i1_prefix_deficit=prefix_deficit,
        i2_l1=i2_l1,
        i3=i3,
        i4=i4,
        i5=i5,
        exact_s5=exact_s5,
        max_team_colour_drift=max_team_colour_drift,
        max_player_colour_drift=max_player_colour_drift,
        max_same_colour_run=max_same_colour_run,
    )


def _case_result(case: tuple[int, int, int]) -> CaseResult:
    team_count, players_per_team, rounds = case
    start = perf_counter()
    table: FixedPairingTable
    try:
        table = _generate_table(team_count, players_per_team, rounds)
    except Exception as exc:
        elapsed = perf_counter() - start
        return CaseResult(
            team_count=team_count,
            players_per_team=players_per_team,
            rounds=rounds,
            generated=False,
            valid=False,
            generation_seconds=elapsed,
            verification_seconds=0.0,
            total_seconds=elapsed,
            metrics=None,
            verifier_notes=(),
            error=f'{type(exc).__name__}: {exc}',
        )

    generated_at = perf_counter()
    notes: tuple[str, ...] = ()
    try:
        report = verify_molter_table(table)
        valid = report.ok
        notes = tuple(report.notes)
        error = '' if report.ok else '; '.join(report.errors[:3])
    except Exception as exc:
        valid = False
        error = f'{type(exc).__name__}: {exc}'
    verified_at = perf_counter()

    metrics = _quality_metrics(table) if valid else None
    return CaseResult(
        team_count=team_count,
        players_per_team=players_per_team,
        rounds=rounds,
        generated=True,
        valid=valid,
        generation_seconds=generated_at - start,
        verification_seconds=verified_at - generated_at,
        total_seconds=verified_at - start,
        metrics=metrics,
        verifier_notes=notes,
        error=error,
    )


def _parallel_results(
    cases: list[tuple[int, int, int]], *, workers: int, chunksize: int
) -> list[CaseResult]:
    if workers == 1:
        return [_case_result(case) for case in cases]
    context_name = 'fork' if 'fork' in multiprocessing.get_all_start_methods() else None
    mp_context = (
        multiprocessing.get_context(context_name) if context_name is not None else None
    )
    kwargs = {}
    if _RECIPE_FILE is not None:
        kwargs['initializer'] = _initialise_recipe_worker
        kwargs['initargs'] = (_RECIPE_FILE,)
    with ProcessPoolExecutor(
        max_workers=workers, mp_context=mp_context, **kwargs
    ) as executor:
        return list(executor.map(_case_result, cases, chunksize=chunksize))


def _i1_lower_bound(team_count: int, players_per_team: int, rounds: int) -> int:
    opponent_count = team_count - 1
    load = players_per_team * rounds
    if load <= opponent_count:
        return 0
    return 0 if load % opponent_count == 0 else 1


def _i2_band(i2_l1: int | None, team_count: int) -> str:
    if i2_l1 is None:
        return ''
    if i2_l1 == 0:
        return 'perfect'
    if i2_l1 <= team_count - 1:
        return 'good'
    if i2_l1 < 2 * (team_count - 1):
        return 'watch'
    return 'avoid'


def _score_case(result: CaseResult) -> ScoredCase:
    if not result.valid or result.metrics is None:
        return ScoredCase(
            case=result,
            i1_lower_bound=None,
            i1_gap_to_bound=None,
            quality_score=999,
            quality_grade='FAIL',
            worst_signal=result.error or 'invalid',
            i2_band='',
            i4_target_applies=False,
        )
    metrics = result.metrics
    i1_lower_bound = _i1_lower_bound(
        result.team_count, result.players_per_team, result.rounds
    )
    i1_gap_to_bound = max(0, metrics.i1 - i1_lower_bound)
    i4_target_applies = (
        result.team_count % 2 == 1
        and 0 < result.players_per_team <= result.team_count - 1
    )

    if metrics.i1 <= 1:
        i1_penalty = 0 if i1_gap_to_bound == 0 else 2
    else:
        i1_penalty = 20 * (metrics.i1 - 1)
    i2_band = _i2_band(metrics.i2_l1, result.team_count)
    i2_penalty = {'perfect': 0, 'good': 1, 'watch': 4, 'avoid': 8}[i2_band]
    score = (
        i1_penalty
        + 10 * metrics.i1_prefix_deficit
        + i2_penalty
        + 2 * max(0, metrics.i3 - 1)
        + (2 * max(0, metrics.i4 - 1) if i4_target_applies else 0)
        + 2 * max(0, metrics.i5 - 1)
        + (0 if metrics.exact_s5 else 1)
    )

    if score == 0:
        grade = 'A'
    elif score <= 6:
        grade = 'B'
    elif score <= 20:
        grade = 'C'
    else:
        grade = 'D'

    worst_signal = 'none'
    if metrics.i1 > 1:
        worst_signal = 'I1 > 1'
    elif metrics.i1_prefix_deficit > 0:
        worst_signal = 'I1 prefix deficit'
    elif i1_gap_to_bound > 0:
        worst_signal = 'I1 above lower bound'
    elif i2_band == 'avoid':
        worst_signal = 'I2 avoid band'
    elif i2_band == 'watch':
        worst_signal = 'I2 watch band'
    elif metrics.i3 > 1:
        worst_signal = 'I3 spread'
    elif metrics.i4 > 1:
        worst_signal = 'I4 round-pair floaters'
    elif metrics.i5 > 1:
        worst_signal = 'I5 spread'
    elif not metrics.exact_s5:
        worst_signal = 'S5 relaxed'

    return ScoredCase(
        case=result,
        i1_lower_bound=i1_lower_bound,
        i1_gap_to_bound=i1_gap_to_bound,
        quality_score=score,
        quality_grade=grade,
        worst_signal=worst_signal,
        i2_band=i2_band,
        i4_target_applies=i4_target_applies,
    )


def _round_labels(max_short_rounds: int, *, include_full: bool = True) -> list[str]:
    labels = [f'R{rounds}' for rounds in range(1, max_short_rounds + 1)]
    if include_full:
        labels.append('Full')
    return labels


def _result_for_label(
    lookup: dict[tuple[int, int, int], ScoredCase], n: int, p: int, label: str
) -> ScoredCase | None:
    if label == 'Full':
        return lookup.get((n, p, n - 1))
    rounds = int(label[1:])
    if rounds > n - 1:
        return None
    return lookup.get((n, p, rounds))


def _write_dashboard(
    workbook: xlsxwriter.Workbook,
    rows: list[ScoredCase],
    *,
    elapsed_seconds: float,
    workers: int,
    players: tuple[int, ...],
    max_team_count: int,
    max_short_rounds: int,
    round_scope: str,
    formats: dict[str, xlsxwriter.format.Format],
) -> None:
    ws = workbook.add_worksheet('Dashboard')
    ws.set_column(0, 0, 34)
    ws.set_column(1, 1, 18)
    ws.set_column(3, 7, 14)
    ws.write(0, 0, 'Molter quality summary', formats['title'])
    ws.write(
        1,
        0,
        'Validation, timing, and ideal-quality audit for every requested table.',
        formats['subtitle'],
    )
    generated = [row for row in rows if row.case.generated]
    valid = [row for row in generated if row.case.valid]
    invalid = [row for row in generated if not row.case.valid]
    failed_generation = [row for row in rows if not row.case.generated]
    summary_rows = [
        ('Team counts', f'3-{max_team_count}'),
        ('Player counts', ', '.join(str(player) for player in players)),
        ('Round scope', round_scope),
        ('Workers', workers),
        ('Wall time seconds', elapsed_seconds),
        ('Unique generated cases', len(rows)),
        ('Generated', len(generated)),
        ('Valid', len(valid)),
        ('Generated but invalid', len(invalid)),
        ('Generation failures', len(failed_generation)),
        (
            'Max generation seconds',
            max((row.case.generation_seconds for row in rows), default=0.0),
        ),
        (
            'Average generation seconds',
            (
                sum(row.case.generation_seconds for row in rows) / len(rows)
                if rows
                else 0.0
            ),
        ),
        ('Cases over 1 second', sum(1 for row in rows if row.case.total_seconds > 1)),
        ('Cases over 5 seconds', sum(1 for row in rows if row.case.total_seconds > 5)),
    ]
    for row_index, (label, value) in enumerate(summary_rows, start=3):
        ws.write(row_index, 0, label, formats['cell'])
        ws.write(
            row_index,
            1,
            value,
            formats['number'] if isinstance(value, float) else formats['cell'],
        )

    grade_counts = {grade: 0 for grade in ('A', 'B', 'C', 'D', 'FAIL')}
    for row in rows:
        grade_counts[row.quality_grade] += 1
    ws.write(3, 3, 'Grade', formats['header'])
    ws.write(3, 4, 'Cases', formats['header'])
    for out_row, grade in enumerate(('A', 'B', 'C', 'D', 'FAIL'), start=4):
        ws.write(out_row, 3, grade, formats[f'grade_{grade}'])
        ws.write(out_row, 4, grade_counts[grade], formats['integer'])

    signal_counts: dict[str, int] = {}
    for row in rows:
        signal_counts[row.worst_signal] = signal_counts.get(row.worst_signal, 0) + 1
    ws.write(11, 3, 'Worst signal', formats['header'])
    ws.write(11, 4, 'Cases', formats['header'])
    for out_row, (signal, count) in enumerate(
        sorted(signal_counts.items(), key=lambda item: (-item[1], item[0]))[:12],
        start=12,
    ):
        ws.write(out_row, 3, signal, formats['cell'])
        ws.write(out_row, 4, count, formats['integer'])

    legend_row = 20
    ws.write(legend_row, 0, 'Quality grade legend', formats['header'])
    legend = [
        ('A', 'valid; no quality-score penalty'),
        ('B', 'valid; only small ideal misses'),
        ('C', 'valid; visible ideal miss, usually prefix/floater/S5'),
        ('D', 'valid; serious ideal miss, especially I1 > 1'),
        ('FAIL', 'generation or verifier failure'),
    ]
    for offset, (grade, meaning) in enumerate(legend, start=1):
        ws.write(legend_row + offset, 0, grade, formats[f'grade_{grade}'])
        ws.write(legend_row + offset, 1, meaning, formats['cell'])

    ws.write(legend_row, 3, 'Metric notes', formats['header'])
    metric_notes = [
        'I1: cumulative opponent-count spread; 0 ideal, <=1 target.',
        'I1 prefix deficit: missing distinct opponents in any prefix; 0 ideal.',
        'I2: L1 sum of |descending - ascending| per team; lower is better.',
        'I3: descending-floater spread across teams; lower is better.',
        'I4: repeated floater roles inside round-pairs; lower is better.',
        'I5: worst per-round opponent spread; lower is better.',
        'Exact S5: per-round team colour balance; bounded cumulative drift is hard.',
    ]
    for offset, note in enumerate(metric_notes, start=1):
        ws.write(legend_row + offset, 3, note, formats['cell'])


def _write_matrix(
    workbook: xlsxwriter.Workbook,
    sheet_name: str,
    rows: list[ScoredCase],
    *,
    players: tuple[int, ...],
    max_team_count: int,
    max_short_rounds: int,
    include_full: bool,
    formats: dict[str, xlsxwriter.format.Format],
    value_getter,
    title: str,
    subtitle: str,
    number_format: str = 'matrix',
) -> None:
    lookup = {
        (row.case.team_count, row.case.players_per_team, row.case.rounds): row
        for row in rows
    }
    labels = _round_labels(max_short_rounds, include_full=include_full)
    ws = workbook.add_worksheet(sheet_name)
    ws.set_column(0, 1, 8)
    ws.set_column(2, 2 + len(labels) - 1, 9)
    ws.write(0, 0, title, formats['title'])
    ws.write(1, 0, subtitle, formats['subtitle'])
    headers = ['N', 'P', *labels, 'Worst', 'Max sec']
    for column, header in enumerate(headers):
        ws.write(3, column, header, formats['header'])
    row_index = 4
    for n in range(3, max_team_count + 1):
        for p in players:
            ws.write(row_index, 0, n, formats['integer'])
            ws.write(row_index, 1, p, formats['integer'])
            row_values: list[ScoredCase] = []
            for column, label in enumerate(labels, start=2):
                scored = _result_for_label(lookup, n, p, label)
                if scored is None:
                    ws.write(row_index, column, '', formats['blank'])
                    continue
                row_values.append(scored)
                value = value_getter(scored)
                if sheet_name == 'Quality matrix':
                    ws.write(row_index, column, value, formats[f'grade_{value}'])
                else:
                    fmt = formats[number_format]
                    ws.write(row_index, column, value if value is not None else '', fmt)
            worst = max(row_values, key=lambda item: item.quality_score, default=None)
            max_seconds = max(
                (row.case.total_seconds for row in row_values),
                default=0.0,
            )
            ws.write(
                row_index,
                2 + len(labels),
                worst.quality_grade if worst else '',
                formats[f'grade_{worst.quality_grade}'] if worst else formats['blank'],
            )
            ws.write(row_index, 3 + len(labels), max_seconds, formats['number'])
            row_index += 1
        row_index += 1
    ws.freeze_panes(4, 2)
    ws.autofilter(3, 0, row_index - 1, len(headers) - 1)
    if sheet_name != 'Quality matrix':
        first_data_row = 4
        last_data_row = row_index - 1
        first_value_col = 2
        last_value_col = 2 + len(labels) - 1
        if sheet_name == 'Timing matrix':
            ws.conditional_format(
                first_data_row,
                first_value_col,
                last_data_row,
                last_value_col,
                {
                    'type': '3_color_scale',
                    'min_color': '#E7F6EC',
                    'mid_color': '#FDF3E0',
                    'max_color': '#FFC7CE',
                },
            )
        else:
            ws.conditional_format(
                first_data_row,
                first_value_col,
                last_data_row,
                last_value_col,
                {
                    'type': 'cell',
                    'criteria': '==',
                    'value': 0,
                    'format': formats['good'],
                },
            )
            ws.conditional_format(
                first_data_row,
                first_value_col,
                last_data_row,
                last_value_col,
                {'type': 'cell', 'criteria': '==', 'value': 1, 'format': formats['ok']},
            )
            ws.conditional_format(
                first_data_row,
                first_value_col,
                last_data_row,
                last_value_col,
                {
                    'type': 'cell',
                    'criteria': '>',
                    'value': 1,
                    'format': formats['warn'],
                },
            )


def _row_values(row: ScoredCase) -> list[object]:
    case = row.case
    metrics = case.metrics
    notes = ' | '.join(case.verifier_notes[:3])
    if metrics is None:
        return [
            case.team_count,
            case.players_per_team,
            case.rounds,
            'Full' if case.rounds == case.team_count - 1 else 'Short',
            'yes' if case.generated else 'no',
            'yes' if case.valid else 'no',
            row.quality_grade,
            row.quality_score,
            row.worst_signal,
            case.generation_seconds,
            case.verification_seconds,
            case.total_seconds,
            '',
            '',
            '',
            '',
            '',
            '',
            '',
            '',
            '',
            '',
            '',
            '',
            '',
            '',
            '',
            notes,
            case.error,
        ]
    return [
        case.team_count,
        case.players_per_team,
        case.rounds,
        'Full' if case.rounds == case.team_count - 1 else 'Short',
        'yes' if case.generated else 'no',
        'yes' if case.valid else 'no',
        row.quality_grade,
        row.quality_score,
        row.worst_signal,
        case.generation_seconds,
        case.verification_seconds,
        case.total_seconds,
        metrics.board_count,
        metrics.i1,
        row.i1_lower_bound,
        row.i1_gap_to_bound,
        max(0, metrics.i1 - 1),
        metrics.i1_prefix_deficit,
        metrics.i2_l1,
        row.i2_band,
        metrics.i3,
        metrics.i4,
        'yes' if row.i4_target_applies else 'no',
        metrics.i5,
        'yes' if metrics.exact_s5 else 'no',
        metrics.max_team_colour_drift,
        metrics.max_player_colour_drift,
        notes,
        case.error,
    ]


def _write_all_cases(
    workbook: xlsxwriter.Workbook,
    rows: list[ScoredCase],
    formats: dict[str, xlsxwriter.format.Format],
) -> None:
    ws = workbook.add_worksheet('All cases')
    columns = [
        'N',
        'P',
        'R',
        'Kind',
        'Generated',
        'Validated',
        'Grade',
        'Quality score',
        'Worst signal',
        'Generation seconds',
        'Verification seconds',
        'Total seconds',
        'Boards',
        'I1',
        'I1 lower bound',
        'I1 gap',
        'I1 > 1 gap',
        'I1 prefix deficit',
        'I2 L1',
        'I2 band',
        'I3',
        'I4',
        'I4 target applies',
        'I5',
        'Exact S5 per round',
        'Max team colour drift',
        'Max player colour drift',
        'Verifier notes',
        'Error',
    ]
    widths = [
        6,
        6,
        6,
        8,
        10,
        10,
        8,
        13,
        22,
        16,
        18,
        13,
        8,
        7,
        14,
        9,
        10,
        14,
        7,
        8,
        10,
        7,
        7,
        16,
        17,
        20,
        20,
        70,
        70,
    ]
    for column, width in enumerate(widths):
        ws.set_column(column, column, width)
    data = [_row_values(row) for row in rows]
    if data:
        ws.add_table(
            0,
            0,
            len(data),
            len(columns) - 1,
            {
                'name': 'MolterQualityCases',
                'style': 'Table Style Medium 2',
                'columns': [{'header': header} for header in columns],
                'data': data,
            },
        )
        grade_col = columns.index('Grade')
        for grade in ('A', 'B', 'C', 'D', 'FAIL'):
            ws.conditional_format(
                1,
                grade_col,
                len(data),
                grade_col,
                {
                    'type': 'cell',
                    'criteria': '==',
                    'value': f'"{grade}"',
                    'format': formats[f'grade_{grade}'],
                },
            )
        for column_name in ('Generation seconds', 'Total seconds'):
            column = columns.index(column_name)
            ws.conditional_format(
                1,
                column,
                len(data),
                column,
                {
                    'type': '3_color_scale',
                    'min_color': '#E7F6EC',
                    'mid_color': '#FDF3E0',
                    'max_color': '#FFC7CE',
                },
            )
        for column_name in ('I1 > 1 gap', 'I1 prefix deficit'):
            column = columns.index(column_name)
            ws.conditional_format(
                1,
                column,
                len(data),
                column,
                {
                    'type': 'cell',
                    'criteria': '>',
                    'value': 0,
                    'format': formats['warn'],
                },
            )
    else:
        for column, header in enumerate(columns):
            ws.write(0, column, header, formats['header'])
    ws.freeze_panes(1, 0)


def _write_problem_cases(
    workbook: xlsxwriter.Workbook,
    rows: list[ScoredCase],
    formats: dict[str, xlsxwriter.format.Format],
) -> None:
    ws = workbook.add_worksheet('Cases to inspect')
    selected = sorted(
        [row for row in rows if row.quality_score > 0],
        key=lambda item: (
            item.quality_grade == 'FAIL',
            item.quality_score,
            item.case.total_seconds,
        ),
        reverse=True,
    )
    columns = [
        'N',
        'P',
        'R',
        'Kind',
        'Grade',
        'Quality score',
        'Worst signal',
        'Generation seconds',
        'I1',
        'I1 prefix deficit',
        'I2 L1',
        'I3',
        'I4',
        'I5',
        'Exact S5 per round',
        'Notes/Error',
    ]
    for column, width in enumerate([6, 6, 6, 8, 8, 13, 22, 16, 7, 14, 8, 7, 7, 17, 80]):
        ws.set_column(column, column, width)
    for column, header in enumerate(columns):
        ws.write(0, column, header, formats['header'])
    for row_index, scored in enumerate(selected[:500], start=1):
        case = scored.case
        metrics = case.metrics
        values = [
            case.team_count,
            case.players_per_team,
            case.rounds,
            'Full' if case.rounds == case.team_count - 1 else 'Short',
            scored.quality_grade,
            scored.quality_score,
            scored.worst_signal,
            case.generation_seconds,
            metrics.i1 if metrics else '',
            metrics.i1_prefix_deficit if metrics else '',
            metrics.i2_l1 if metrics else '',
            metrics.i3 if metrics else '',
            metrics.i4 if metrics else '',
            metrics.i5 if metrics else '',
            ('yes' if metrics.exact_s5 else 'no') if metrics else '',
            case.error or ' | '.join(case.verifier_notes[:2]),
        ]
        for column, value in enumerate(values):
            if column == 4:
                fmt = formats[f'grade_{value}']
            elif column == 7:
                fmt = formats['number']
            else:
                fmt = formats['cell']
            ws.write(row_index, column, value, fmt)
    ws.freeze_panes(1, 0)
    if selected:
        ws.autofilter(0, 0, min(len(selected), 500), len(columns) - 1)


def _write_rollups(
    workbook: xlsxwriter.Workbook,
    rows: list[ScoredCase],
    *,
    max_short_rounds: int,
    include_full: bool,
    formats: dict[str, xlsxwriter.format.Format],
) -> None:
    ws = workbook.add_worksheet('Rollups')
    ws.set_column(0, 10, 14)
    ws.write(0, 0, 'Quality by round view', formats['title'])
    columns = [
        'Round view',
        'Cases',
        'Valid',
        'A',
        'B',
        'C',
        'D',
        'FAIL',
        'Max seconds',
        'Max I1',
        'Max I1 prefix deficit',
    ]
    for column, header in enumerate(columns):
        ws.write(2, column, header, formats['header'])
    labels = _round_labels(max_short_rounds, include_full=include_full)
    for row_index, label in enumerate(labels, start=3):
        if label == 'Full':
            subset = [row for row in rows if row.case.rounds == row.case.team_count - 1]
        else:
            rounds = int(label[1:])
            subset = [row for row in rows if row.case.rounds == rounds]
        valid = [
            row for row in subset if row.case.valid and row.case.metrics is not None
        ]
        values = [
            label,
            len(subset),
            len(valid),
            sum(1 for row in subset if row.quality_grade == 'A'),
            sum(1 for row in subset if row.quality_grade == 'B'),
            sum(1 for row in subset if row.quality_grade == 'C'),
            sum(1 for row in subset if row.quality_grade == 'D'),
            sum(1 for row in subset if row.quality_grade == 'FAIL'),
            max((row.case.total_seconds for row in subset), default=0.0),
            max((row.case.metrics.i1 for row in valid), default=''),
            max((row.case.metrics.i1_prefix_deficit for row in valid), default=''),
        ]
        for column, value in enumerate(values):
            ws.write(
                row_index,
                column,
                value,
                formats['number'] if isinstance(value, float) else formats['cell'],
            )
    ws.freeze_panes(3, 0)


def _write_workbook(
    path: Path,
    rows: list[ScoredCase],
    *,
    elapsed_seconds: float,
    workers: int,
    players: tuple[int, ...],
    max_team_count: int,
    max_short_rounds: int,
    include_full: bool,
    round_scope: str,
) -> None:
    workbook = xlsxwriter.Workbook(path)
    formats = {
        'title': workbook.add_format({'bold': True, 'font_size': 13}),
        'subtitle': workbook.add_format({'italic': True, 'font_color': '#555555'}),
        'header': workbook.add_format(
            {
                'bold': True,
                'bg_color': '#1F3864',
                'font_color': 'white',
                'border': 1,
                'align': 'center',
                'text_wrap': True,
            }
        ),
        'cell': workbook.add_format({'border': 1}),
        'blank': workbook.add_format({'border': 1, 'bg_color': '#F2F2F2'}),
        'integer': workbook.add_format({'border': 1, 'align': 'center'}),
        'number': workbook.add_format(
            {'border': 1, 'align': 'center', 'num_format': '#,##0.000'}
        ),
        'matrix': workbook.add_format({'border': 1, 'align': 'center'}),
        'good': workbook.add_format(
            {'border': 1, 'align': 'center', 'bg_color': '#E7F6EC'}
        ),
        'ok': workbook.add_format(
            {'border': 1, 'align': 'center', 'bg_color': '#FDF3E0'}
        ),
        'warn': workbook.add_format(
            {
                'border': 1,
                'align': 'center',
                'bg_color': '#FFC7CE',
                'font_color': '#9C0006',
            }
        ),
        'grade_A': workbook.add_format(
            {'border': 1, 'align': 'center', 'bg_color': '#63BE7B'}
        ),
        'grade_B': workbook.add_format(
            {'border': 1, 'align': 'center', 'bg_color': '#C6EFCE'}
        ),
        'grade_C': workbook.add_format(
            {'border': 1, 'align': 'center', 'bg_color': '#FFEB9C'}
        ),
        'grade_D': workbook.add_format(
            {
                'border': 1,
                'align': 'center',
                'bg_color': '#F4B183',
                'font_color': '#7F3F00',
            }
        ),
        'grade_FAIL': workbook.add_format(
            {
                'border': 1,
                'align': 'center',
                'bg_color': '#C00000',
                'font_color': 'white',
            }
        ),
    }

    _write_dashboard(
        workbook,
        rows,
        elapsed_seconds=elapsed_seconds,
        workers=workers,
        players=players,
        max_team_count=max_team_count,
        max_short_rounds=max_short_rounds,
        round_scope=round_scope,
        formats=formats,
    )
    _write_matrix(
        workbook,
        'Quality matrix',
        rows,
        players=players,
        max_team_count=max_team_count,
        max_short_rounds=max_short_rounds,
        include_full=include_full,
        formats=formats,
        value_getter=lambda row: row.quality_grade,
        title='Quality grade by N/P/R',
        subtitle='A/B/C/D/FAIL grade. Full uses R=N-1 even when that is also shown under an early R column.',
    )
    _write_matrix(
        workbook,
        'Timing matrix',
        rows,
        players=players,
        max_team_count=max_team_count,
        max_short_rounds=max_short_rounds,
        include_full=include_full,
        formats=formats,
        value_getter=lambda row: row.case.total_seconds,
        title='Generation + verification seconds by N/P/R',
        subtitle='Heatmap: green is fastest, red is slowest.',
        number_format='number',
    )
    _write_matrix(
        workbook,
        'I1 matrix',
        rows,
        players=players,
        max_team_count=max_team_count,
        max_short_rounds=max_short_rounds,
        include_full=include_full,
        formats=formats,
        value_getter=lambda row: row.case.metrics.i1 if row.case.metrics else None,
        title='I1 by N/P/R',
        subtitle='I1 = cumulative opponent-count spread. 0 ideal, <=1 target.',
    )
    _write_matrix(
        workbook,
        'I1 prefix matrix',
        rows,
        players=players,
        max_team_count=max_team_count,
        max_short_rounds=max_short_rounds,
        include_full=include_full,
        formats=formats,
        value_getter=lambda row: (
            row.case.metrics.i1_prefix_deficit if row.case.metrics else None
        ),
        title='I1 prefix distinct-opponent deficit by N/P/R',
        subtitle='0 ideal. Positive values show missing distinct opponents in at least one prefix.',
    )
    _write_rollups(
        workbook,
        rows,
        max_short_rounds=max_short_rounds,
        include_full=include_full,
        formats=formats,
    )
    _write_problem_cases(workbook, rows, formats)
    _write_all_cases(workbook, rows, formats)
    workbook.close()


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        'output',
        nargs='?',
        type=Path,
        default=DEFAULT_OUTPUT,
        help=f'Output .xlsx path (default: {DEFAULT_OUTPUT})',
    )
    parser.add_argument(
        '--max-n',
        type=int,
        default=50,
        help='Maximum team count, inclusive (default: 50).',
    )
    parser.add_argument(
        '--max-short-rounds',
        type=int,
        default=DEFAULT_SHORT_ROUNDS,
        help='Highest non-full round count to include (default: 14).',
    )
    parser.add_argument(
        '--players',
        type=int,
        nargs='+',
        default=list(DEFAULT_PLAYERS),
        help='Players per team to test. Defaults to even values 2..12.',
    )
    parser.add_argument(
        '--workers',
        type=int,
        default=min(8, os.cpu_count() or 1),
        help='Worker process count (default: min(8, CPU count)).',
    )
    parser.add_argument(
        '--chunksize',
        type=int,
        default=4,
        help='ProcessPoolExecutor map chunksize (default: 4).',
    )
    parser.add_argument(
        '--recipe-file',
        type=Path,
        help=(
            'JSON or .mrec recipe artifact to replay. Defaults to the app recipe '
            f'artifact at {DEFAULT_RECIPE_FILE}.'
        ),
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    players = tuple(
        player for player in args.players if player % 2 == 0 and player >= 2
    )
    if len(players) != len(args.players):
        skipped = sorted(set(args.players) - set(players))
        print(
            'Skipping P values outside the quality grid: '
            f'{", ".join(str(item) for item in skipped)}'
        )
    if not players:
        raise SystemExit('At least one even player count >= 2 is required.')
    if args.max_n < 3:
        raise SystemExit('--max-n must be at least 3.')
    if args.max_short_rounds < 1:
        raise SystemExit('--max-short-rounds must be at least 1.')
    if args.workers < 1:
        raise SystemExit('--workers must be at least 1.')
    if args.chunksize < 1:
        raise SystemExit('--chunksize must be at least 1.')

    _load_recipe_file(args.recipe_file)
    tasks = _recipe_cases(
        max_team_count=args.max_n,
        players=players,
        max_short_rounds=args.max_short_rounds,
    )
    if not tasks:
        raise SystemExit('The recipe file contains no cases matching the filters.')
    players = tuple(sorted({players_per_team for _n, players_per_team, _r in tasks}))
    max_team_count = max(n for n, _p, _r in tasks)
    max_short_rounds = max(r for _n, _p, r in tasks)
    include_full = False
    recipe_name = _RECIPE_FILE.name if _RECIPE_FILE is not None else 'recipe artifact'
    round_scope = (
        f'Recipe artifact cases from {recipe_name}; '
        f'R1..R{max_short_rounds} where present'
    )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    start = perf_counter()
    results = _parallel_results(tasks, workers=args.workers, chunksize=args.chunksize)
    elapsed_seconds = perf_counter() - start
    scored = [_score_case(result) for result in results]
    scored.sort(
        key=lambda row: (
            row.case.team_count,
            row.case.players_per_team,
            row.case.rounds,
        )
    )
    _write_workbook(
        args.output,
        scored,
        elapsed_seconds=elapsed_seconds,
        workers=args.workers,
        players=players,
        max_team_count=max_team_count,
        max_short_rounds=max_short_rounds,
        include_full=include_full,
        round_scope=round_scope,
    )
    valid = sum(1 for row in scored if row.case.valid)
    grade_counts = {
        grade: sum(1 for row in scored if row.quality_grade == grade)
        for grade in ('A', 'B', 'C', 'D', 'FAIL')
    }
    print(f'Written: {args.output}')
    print(
        f'Cases={len(scored)} valid={valid} elapsed={elapsed_seconds:.3f}s '
        f'grades={grade_counts}'
    )
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
