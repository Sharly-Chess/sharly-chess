#!/usr/bin/env python3
"""Build Excel workbooks for Molter recipe tables.

By default the workbook has one sheet per team count with the complete tables
(all rounds = teams − 1). With ``--summary`` it instead produces a criteria
analysis: one tab per regular-round count (4, 6, … 50) giving the actual I1–I5
measures for every shape that genuinely runs that many rounds — a shape is only
listed once it can play that round count (``teams − 1 ≥ rounds``), so a table is
never repeated past its complete form.

Dependency: xlsxwriter (``pip install xlsxwriter``).

Usage:
    python3 build_xlsx.py [output.xlsx] [--summary] [--workers N]
                          [--recipe-file PATH]

Table workbooks include per-sheet controls: a "Highlight team" selector and a
"Highlight floaters" checkbox. Change the team letter in the selector cell to
highlight every pairing involving that team's players on the sheet; tick the
checkbox to colour floater pairings red.
"""

import argparse
import multiprocessing
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SRC_DIR = ROOT / 'src'
THIS_DIR = Path(__file__).resolve().parent
DEFAULT_RECIPE_FILE = (
    SRC_DIR / 'data' / 'pairings' / 'resources' / 'molter_recipes.mrec'
)
sys.path.insert(0, str(SRC_DIR))
sys.path.insert(0, str(THIS_DIR))

import xlsxwriter  # noqa: E402
from xlsxwriter.utility import xl_rowcol_to_cell  # noqa: E402

import build_solver_recipes as recipes  # noqa: E402
from data.pairings.molter_verifier import verify_molter_table  # noqa: E402

TEAM_COUNTS = range(3, 16)
PLAYER_COUNTS = (2, 4, 6, 8, 10, 12)
# Criteria analysis: one tab per round count (odd counts included, now that odd
# rounds are generated directly) up to the largest full table (N − 1 = 50 for
# N = 51), over teams 3–15 plus the large odd sizes.
ROUND_TABS = tuple(range(1, 51))
ANALYSIS_TEAMS = tuple(range(3, 16)) + tuple(range(17, 52, 2))
_Measures = tuple[int, int, int, int, int, int]
_SummaryRows = dict[tuple[int, int, int], tuple[bool, _Measures | None]]
_RECIPE_BY_KEY: dict[tuple[int, int, int], dict] = {}


class RecipeTableError(Exception):
    """Raised when a requested table is absent from the recipe artifact."""


def _letter(team_index: int) -> str:
    return chr(ord('A') + team_index)


def _recipe_key(n: int, p: int, r: int) -> tuple[int, int, int]:
    return n, p, r


def _load_recipe_file(path: str | None) -> None:
    recipe_path = Path(path) if path is not None else DEFAULT_RECIPE_FILE
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


def _generate_table(n: int, p: int, r: int):
    recipe = _RECIPE_BY_KEY.get(_recipe_key(n, p, r))
    if recipe is None:
        raise RecipeTableError(f'No recipe for {n}x{p} R{r}.')
    return recipes.materialize_recipe(recipe)


def _verify_table(table) -> bool:
    return verify_molter_table(table).ok


def _pairing_text(pairing) -> str:
    return (
        f'{pairing.white_team}{pairing.white_index} - '
        f'{pairing.black_team}{pairing.black_index}'
    )


def _measures(table, team_count: int) -> _Measures:
    """Actual I1–I5 measures for a generated table (0 is ideal; lower is
    better). I1: cumulative opponent-count spread and prefix distinct-opponent
    deficit. I2: sum |ascending - descending| per team. I3:
    descending-floater spread across teams. I4: max floaters of one direction
    per team per round-pair (0 = no floaters, 1 = single layer). I5: worst
    per-round opponent spread."""
    index = {_letter(i): i for i in range(team_count)}
    rounds = table.rounds
    players_per_team = table.players_per_team
    round_pairs = (len(rounds) + 1) // 2
    down = [0] * team_count
    up = [0] * team_count
    pair = [[0] * team_count for _ in range(team_count)]
    prefix_mask = [0] * team_count
    rp_down = [[0] * team_count for _ in range(round_pairs)]
    rp_up = [[0] * team_count for _ in range(round_pairs)]
    i5 = 0
    i1_prefix_deficit = 0
    for r_index, rnd in enumerate(rounds):
        round_pair = r_index // 2
        opp = [[0] * team_count for _ in range(team_count)]
        for p in rnd:
            white = index[p.white_team]
            black = index[p.black_team]
            pair[white][black] += 1
            pair[black][white] += 1
            opp[white][black] += 1
            opp[black][white] += 1
            prefix_mask[white] |= 1 << black
            prefix_mask[black] |= 1 << white
            if p.white_index != p.black_index:
                if p.white_index < p.black_index:
                    descend, ascend = white, black
                else:
                    descend, ascend = black, white
                down[descend] += 1
                up[ascend] += 1
                rp_down[round_pair][descend] += 1
                rp_up[round_pair][ascend] += 1
        for team in range(team_count):
            counts = [opp[team][o] for o in range(team_count) if opp[team][o]]
            if counts:
                i5 = max(i5, max(counts) - min(counts))
        expected_distinct = min(team_count - 1, players_per_team * (r_index + 1))
        for team in range(team_count):
            i1_prefix_deficit = max(
                i1_prefix_deficit, expected_distinct - prefix_mask[team].bit_count()
            )
    i1 = 0
    for team in range(team_count):
        counts = [pair[team][o] for o in range(team_count) if pair[team][o]]
        if counts:
            i1 = max(i1, max(counts) - min(counts))
    i3 = max(down) - min(down)
    i2 = sum(abs(up[t] - down[t]) for t in range(team_count))
    i4 = max(
        (
            max(rp_down[rp][t], rp_up[rp][t])
            for rp in range(round_pairs)
            for t in range(team_count)
        ),
        default=0,
    )
    return i1, i1_prefix_deficit, i2, i3, i4, i5


def _summary_case(
    case: tuple[int, int, int],
) -> tuple[int, int, int, bool, _Measures | None]:
    n, p, r = case
    try:
        table = _generate_table(n, p, r)
    except RecipeTableError:
        return n, p, r, False, None
    return n, p, r, _verify_table(table), _measures(table, n)


def _summary_tasks() -> list[tuple[int, int, int]]:
    if _RECIPE_BY_KEY:
        return sorted(_RECIPE_BY_KEY)
    return [
        (n, p, r) for n in ANALYSIS_TEAMS for p in PLAYER_COUNTS for r in range(1, n)
    ]


def _analysis_teams() -> tuple[int, ...]:
    if _RECIPE_BY_KEY:
        return tuple(sorted({n for n, _p, _r in _RECIPE_BY_KEY}))
    return ANALYSIS_TEAMS


def _round_tabs() -> tuple[int, ...]:
    if _RECIPE_BY_KEY:
        return tuple(sorted({r for _n, _p, r in _RECIPE_BY_KEY}))
    return ROUND_TABS


def _overview_rounds() -> tuple[int, ...]:
    if _RECIPE_BY_KEY:
        return tuple(round_ for round_ in _round_tabs() if round_ >= 2)
    return OVERVIEW_ROUNDS


def _parallel_summary_rows(workers: int) -> _SummaryRows:
    context_name = 'fork' if 'fork' in multiprocessing.get_all_start_methods() else None
    mp_context = (
        multiprocessing.get_context(context_name) if context_name is not None else None
    )
    rows: _SummaryRows = {}
    with ProcessPoolExecutor(max_workers=workers, mp_context=mp_context) as executor:
        for n, p, r, ok, measures in executor.map(
            _summary_case, _summary_tasks(), chunksize=8
        ):
            rows[(n, p, r)] = (ok, measures)
    return rows


_TRUNCATED_ROUND_COUNTS = (3, 5)


def _table_variants(n: int, p: int):
    if _RECIPE_BY_KEY:
        available_rounds = sorted(
            r for tn, tp, r in _RECIPE_BY_KEY if tn == n and tp == p
        )
        if not available_rounds:
            raise RecipeTableError(f'No recipe for {n}x{p}.')
        full = available_rounds[-1]
        heading = 'full table' if full == n - 1 else f'{full} rounds (max recipe)'
    else:
        full = n - 1
        heading = 'full table'
    table = _generate_table(n, p, full)
    yield heading, table
    for truncated_rounds in _TRUNCATED_ROUND_COUNTS:
        if full <= truncated_rounds:
            continue
        if _RECIPE_BY_KEY and _recipe_key(n, p, truncated_rounds) not in _RECIPE_BY_KEY:
            continue
        yield (
            f'{truncated_rounds} rounds (generated)',
            _generate_table(n, p, truncated_rounds),
        )


def _write_table_controls(
    ws, n: int, title, sub, input_cf, *, highlight_floaters: bool
) -> None:
    letters = [_letter(team) for team in range(n)]
    ws.write(0, 0, 'Highlight team', title)
    ws.write(0, 1, '', input_cf)
    ws.data_validation(
        0,
        1,
        0,
        1,
        {
            'validate': 'list',
            'source': letters,
            'input_title': 'Team to highlight',
            'input_message': 'Choose a team letter to highlight its pairings.',
        },
    )
    ws.write(0, 3, 'Highlight floaters', title)
    ws.insert_checkbox(0, 4, highlight_floaters, input_cf)
    ws.write(
        1,
        0,
        'Choose a team letter in B1 to highlight pairings for that team; tick '
        'E1 to colour floater pairings red.',
        sub,
    )


def _apply_team_highlight(
    ws, first_row: int, last_row: int, first_col: int, last_col: int, fmt
) -> None:
    if first_row > last_row or first_col > last_col:
        return
    first_cell = xl_rowcol_to_cell(first_row, first_col, row_abs=False, col_abs=False)
    formula = (
        f'=AND($B$1<>"",OR(LEFT({first_cell},LEN($B$1))=$B$1,'
        f'ISNUMBER(SEARCH(" - "&$B$1,{first_cell}))))'
    )
    ws.conditional_format(
        first_row,
        first_col,
        last_row,
        last_col,
        {'type': 'formula', 'criteria': formula, 'format': fmt},
    )


def _apply_floater_highlight(
    ws,
    first_row: int,
    last_row: int,
    first_col: int,
    last_col: int,
    marker_start_col: int,
    fmt,
) -> None:
    if first_row > last_row or first_col > last_col:
        return
    first_marker_cell = xl_rowcol_to_cell(
        first_row, marker_start_col, row_abs=False, col_abs=False
    )
    formula = f'=AND($E$1=TRUE,{first_marker_cell}=TRUE)'
    ws.conditional_format(
        first_row,
        first_col,
        last_row,
        last_col,
        {'type': 'formula', 'criteria': formula, 'format': fmt},
    )


def _write_board_sheets(wb, title, sub, hdr, bd, cf, floater_cf) -> None:
    """One sheet per team count. For each shape it shows the full table and,
    when the full table is longer, tables generated directly for 3 and 5 rounds —
    which for odd team counts is re-optimised and need not be a prefix of the
    full table."""
    input_cf = wb.add_format({'border': 1, 'align': 'center', 'bg_color': '#FFF2CC'})
    team_cf = wb.add_format({'bg_color': '#FFF2CC'})
    for n in TEAM_COUNTS:
        sh = wb.add_worksheet(f'{n} teams')
        max_visible_col = max(13, n - 1)
        marker_start_col = max_visible_col + 2
        sh.set_column(0, 0, 14)
        sh.set_column(1, max_visible_col, 16)
        sh.set_column(
            marker_start_col,
            marker_start_col + max_visible_col - 1,
            None,
            None,
            {'hidden': True},
        )
        _write_table_controls(sh, n, title, sub, input_cf, highlight_floaters=False)
        r0 = 3
        for p in PLAYER_COUNTS:
            try:
                variants = list(_table_variants(n, p))
            except RecipeTableError:
                continue
            boards = n * p // 2

            def block(r0: int, heading: str, rounds: list) -> int:
                sh.write(r0, 0, f'{n} teams x {p} players — {heading}', title)
                r0 += 1
                sh.write(
                    r0,
                    0,
                    f'{boards} boards — {len(rounds)} rounds — first named = white',
                    sub,
                )
                r0 += 1
                sh.write(r0, 0, 'Bd.', hdr)
                for c in range(1, len(rounds) + 1):
                    sh.write(r0, c, f'Round {c}', hdr)
                r0 += 1
                first_pairing_row = r0
                for b in range(boards):
                    sh.write(r0, 0, b + 1, bd)
                    for c, rnd in enumerate(rounds, start=1):
                        pairing = rnd[b]
                        sh.write(r0, c, _pairing_text(pairing), cf)
                        sh.write_boolean(
                            r0,
                            marker_start_col + c - 1,
                            pairing.white_index != pairing.black_index,
                        )
                    r0 += 1
                _apply_floater_highlight(
                    sh,
                    first_pairing_row,
                    r0 - 1,
                    1,
                    len(rounds),
                    marker_start_col,
                    floater_cf,
                )
                _apply_team_highlight(
                    sh,
                    first_pairing_row,
                    r0 - 1,
                    1,
                    len(rounds),
                    team_cf,
                )
                return r0 + 2

            for heading, table in variants:
                r0 = block(r0, heading, list(table.rounds))


def _colour_sequences(table) -> dict[tuple[str, int], list[str]]:
    sequences = {
        (_letter(team), player): []
        for team in range(table.team_count)
        for player in range(1, table.players_per_team + 1)
    }
    for rnd in table.rounds:
        for pairing in rnd:
            sequences[(pairing.white_team, pairing.white_index)].append('W')
            sequences[(pairing.black_team, pairing.black_index)].append('B')
    return sequences


def _write_colour_transition_sheet(wb, title, sub, hdr, cf, good, warn) -> None:
    ws = wb.add_worksheet('Colour transitions')
    max_rounds = max(n - 1 for n in TEAM_COUNTS)
    ws.set_column(0, 2, 9)
    ws.set_column(3, 3, 8)
    ws.set_column(4, 3 + max_rounds, 5)
    ws.set_column(4 + max_rounds, 5 + max_rounds, 10)

    white_cf = wb.add_format({'border': 1, 'align': 'center'})
    black_cf = wb.add_format({'border': 1, 'align': 'center', 'bg_color': '#F2F2F2'})
    double_cf = wb.add_format({'border': 1, 'align': 'center', 'bg_color': '#FCE4D6'})
    triple_cf = wb.add_format(
        {
            'border': 1,
            'align': 'center',
            'bg_color': '#FFC7CE',
            'font_color': '#9C0006',
        }
    )

    ws.write(0, 0, 'Colour transitions by player', title)
    ws.write(
        1,
        0,
        'W/B by round. Amber marks a repeated colour from the previous round; '
        'red would mark three identical colours in a row.',
        sub,
    )
    cols = (
        ['Teams', 'Players', 'Table', 'Player']
        + [f'R{r}' for r in range(1, max_rounds + 1)]
        + ['Final W-B', 'Max drift']
    )
    for c, name in enumerate(cols):
        ws.write(3, c, name, hdr)

    row = 4
    for n in TEAM_COUNTS:
        for p in PLAYER_COUNTS:
            try:
                variants = list(_table_variants(n, p))
            except RecipeTableError:
                continue
            for heading, table in variants:
                sequences = _colour_sequences(table)
                for team in range(n):
                    letter = _letter(team)
                    for player in range(1, p + 1):
                        sequence = sequences[(letter, player)]
                        whites = sequence.count('W')
                        final_drift = whites - (len(sequence) - whites)
                        prefix_whites = 0
                        max_drift = 0
                        ws.write(row, 0, n, cf)
                        ws.write(row, 1, p, cf)
                        ws.write(row, 2, heading, cf)
                        ws.write(row, 3, f'{letter}{player}', cf)
                        for index, colour in enumerate(sequence):
                            prefix_whites += 1 if colour == 'W' else 0
                            played = index + 1
                            max_drift = max(
                                max_drift, abs(prefix_whites - (played - prefix_whites))
                            )
                            if (
                                index >= 2
                                and colour == sequence[index - 1] == sequence[index - 2]
                            ):
                                fmt = triple_cf
                            elif index >= 1 and colour == sequence[index - 1]:
                                fmt = double_cf
                            elif colour == 'B':
                                fmt = black_cf
                            else:
                                fmt = white_cf
                            ws.write(row, 4 + index, colour, fmt)
                        for c in range(len(sequence), max_rounds):
                            ws.write(row, 4 + c, '', cf)
                        ws.write(
                            row,
                            4 + max_rounds,
                            final_drift,
                            good if abs(final_drift) <= 1 else warn,
                        )
                        ws.write(
                            row,
                            5 + max_rounds,
                            max_drift,
                            good if max_drift <= 2 else warn,
                        )
                        row += 1
                row += 1
    ws.freeze_panes(4, 4)


def _write_analysis_tabs(
    wb, title, sub, hdr, cf, good, warn, rows: _SummaryRows | None = None
) -> None:
    """One tab per round count with the actual I1–I5 measures.

    A shape appears on tab R only when it can run R rounds (teams − 1 ≥ R), so
    each shape is shown for every round count up to its complete table and never
    repeated once capped.
    """

    def spread_fmt(value: int):
        return good if value == 0 else (cf if value == 1 else warn)

    def i2_fmt(value: int, team_count: int):
        if value <= team_count - 1:
            return good
        if value < 2 * (team_count - 1):
            return cf
        return warn

    cols = [
        'Teams',
        'Players',
        'Rounds',
        'Valid',
        'I1',
        'I1 prefix deficit',
        'I2 L1',
        'I3',
        'I4',
        'I5',
    ]
    for target in _round_tabs():
        ws = wb.add_worksheet(f'{target} rounds')
        ws.set_column(0, 9, 9)
        ws.write(
            0,
            0,
            f'Criteria at {target} regular rounds — actual I1–I5',
            title,
        )
        ws.write(
            1,
            0,
            'Spreads / maxima (0 best; lower is better). '
            'I1 cumulative opponent spread and prefix distinct-opponent deficit · '
            'I2 sum |asc − desc| per team (≤ N−1 good, ≥ 2(N−1) avoid) · '
            'I3 descending-floater spread · I4 floaters per team per round-pair '
            '(1 = single layer) · I5 per-round opponent spread.',
            sub,
        )
        for c, name in enumerate(cols):
            ws.write(3, c, name, hdr)
        row = 4
        first_block = True
        for n in _analysis_teams():
            if n - 1 < target:
                continue
            if not first_block:
                row += 1  # blank separator row between team-count blocks
            first_block = False
            for p in PLAYER_COUNTS:
                if rows is None:
                    try:
                        table = _generate_table(n, p, target)
                    except RecipeTableError:
                        continue
                    ok = _verify_table(table)
                    measures = _measures(table, n)
                else:
                    ok, measures = rows.get((n, p, target), (False, None))
                    if measures is None:
                        continue
                i1, i1_prefix_deficit, i2, i3, i4, i5 = measures
                ws.write(row, 0, n, cf)
                ws.write(row, 1, p, cf)
                ws.write(row, 2, target, cf)
                ws.write(row, 3, 'yes' if ok else 'NO', good if ok else warn)
                ws.write(row, 4, i1, spread_fmt(i1))
                ws.write(row, 5, i1_prefix_deficit, spread_fmt(i1_prefix_deficit))
                ws.write(row, 6, i2, i2_fmt(i2, n))
                ws.write(row, 7, i3, spread_fmt(i3))
                ws.write(row, 8, i4, cf)
                ws.write(row, 9, i5, spread_fmt(i5))
                row += 1
        ws.freeze_panes(4, 0)


# Round counts shown in the opponent-spread overview (the truncation-relevant
# early range; a shape is blank past its complete table).
OVERVIEW_ROUNDS = tuple(range(2, 15))


def _write_i1_overview(
    wb, title, sub, hdr, cf, good, warn, rows: _SummaryRows | None = None
) -> None:
    """Single overview sheet: opponent spread (I1) by round count, one row per
    shape. Shows at a glance how quickly a table balances opponents — i.e. how
    early it can be safely truncated. 0 = every opponent met equally."""

    def fmt(value):
        if value == '':
            return cf
        return good if value == 0 else (cf if value == 1 else warn)

    ws = wb.add_worksheet('I1 by round')
    ws.set_column(0, 1, 9)
    overview_rounds = _overview_rounds()
    ws.set_column(2, 1 + len(overview_rounds), 6)
    ws.write(0, 0, 'Opponent spread (I1) by round count', title)
    ws.write(
        1,
        0,
        'I1 = max−min of how many times a team meets each opponent so far '
        '(0 ideal). A low value early means the table can be truncated and '
        'still gives a fair opponent spread. Blank = beyond the complete table.',
        sub,
    )
    cols = ['Teams', 'Players'] + [f'R{r}' for r in overview_rounds]
    for c, name in enumerate(cols):
        ws.write(3, c, name, hdr)
    row = 4
    first_block = True
    for n in _analysis_teams():
        if not first_block:
            row += 1
        first_block = False
        for p in PLAYER_COUNTS:
            ws.write(row, 0, n, cf)
            ws.write(row, 1, p, cf)
            for c, r in enumerate(overview_rounds, start=2):
                if r > n - 1:
                    ws.write(row, c, '', cf)
                    continue
                if rows is None:
                    try:
                        table = _generate_table(n, p, r)
                    except RecipeTableError:
                        ws.write(row, c, '', cf)
                        continue
                    measures = _measures(table, n)
                else:
                    _ok, measures = rows.get((n, p, r), (False, None))
                    if measures is None:
                        ws.write(row, c, '', cf)
                        continue
                i1 = measures[0]
                ws.write(row, c, i1, fmt(i1))
            row += 1
    ws.freeze_panes(4, 2)


def _write_prefix_overview(
    wb, title, sub, hdr, cf, good, warn, rows: _SummaryRows | None = None
) -> None:
    """Single overview sheet: distinct-opponent prefix coverage by round count.

    0 means every prefix reaches min(N − 1, P × rounds) distinct opposing teams
    for every team. Positive values are the worst missing-opponent deficit.
    """

    def fmt(value):
        if value == '':
            return cf
        return good if value == 0 else warn

    ws = wb.add_worksheet('I1 prefix coverage')
    ws.set_column(0, 1, 9)
    overview_rounds = _overview_rounds()
    ws.set_column(2, 1 + len(overview_rounds), 6)
    ws.write(0, 0, 'I1 prefix distinct-opponent coverage by round count', title)
    ws.write(
        1,
        0,
        'Value = worst missing distinct opponent count over all teams and all '
        'prefixes up to that round count. 0 ideal: every prefix meets '
        'min(N−1, P×r) distinct opposing teams when arithmetic permits. '
        'Blank = beyond the complete table.',
        sub,
    )
    cols = ['Teams', 'Players'] + [f'R{r}' for r in overview_rounds]
    for c, name in enumerate(cols):
        ws.write(3, c, name, hdr)
    row = 4
    first_block = True
    for n in _analysis_teams():
        if not first_block:
            row += 1
        first_block = False
        for p in PLAYER_COUNTS:
            ws.write(row, 0, n, cf)
            ws.write(row, 1, p, cf)
            for c, r in enumerate(overview_rounds, start=2):
                if r > n - 1:
                    ws.write(row, c, '', cf)
                    continue
                if rows is None:
                    try:
                        table = _generate_table(n, p, r)
                    except RecipeTableError:
                        ws.write(row, c, '', cf)
                        continue
                    measures = _measures(table, n)
                else:
                    _ok, measures = rows.get((n, p, r), (False, None))
                    if measures is None:
                        ws.write(row, c, '', cf)
                        continue
                i1_prefix_deficit = measures[1]
                ws.write(row, c, i1_prefix_deficit, fmt(i1_prefix_deficit))
            row += 1
    ws.freeze_panes(4, 2)


def build(
    path: str,
    summary: bool = False,
    workers: int = 1,
) -> None:
    wb = xlsxwriter.Workbook(path)
    title = wb.add_format({'bold': True, 'font_size': 13})
    sub = wb.add_format({'italic': True, 'font_color': '#555555'})
    hdr = wb.add_format(
        {
            'bold': True,
            'bg_color': '#1F3864',
            'font_color': 'white',
            'border': 1,
            'align': 'center',
            'text_wrap': True,
        }
    )
    bd = wb.add_format({'border': 1, 'align': 'center', 'bg_color': '#F2F2F2'})
    cf = wb.add_format({'border': 1, 'align': 'center'})
    floater_cf = wb.add_format({'font_color': '#C00000'})
    good = wb.add_format({'border': 1, 'align': 'center', 'bg_color': '#E7F6EC'})
    warn = wb.add_format({'border': 1, 'align': 'center', 'bg_color': '#FDF3E0'})

    if summary:
        rows = _parallel_summary_rows(workers) if workers > 1 else None
        _write_i1_overview(wb, title, sub, hdr, cf, good, warn, rows)
        _write_prefix_overview(wb, title, sub, hdr, cf, good, warn, rows)
        _write_analysis_tabs(wb, title, sub, hdr, cf, good, warn, rows)
    else:
        _write_board_sheets(
            wb,
            title,
            sub,
            hdr,
            bd,
            cf,
            floater_cf,
        )
        _write_colour_transition_sheet(wb, title, sub, hdr, cf, good, warn)
    wb.close()


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        'output',
        nargs='?',
        default=str(Path(__file__).resolve().parent / 'molter-tables.xlsx'),
        help='Output .xlsx path.',
    )
    parser.add_argument(
        '--summary',
        action='store_true',
        help='Build the criteria summary workbook instead of the table workbook.',
    )
    parser.add_argument(
        '--workers',
        type=int,
        default=1,
        help='Worker process count for --summary (default: serial).',
    )
    parser.add_argument(
        '--recipe-file',
        help=(
            'JSON or .mrec recipe artifact to replay. Defaults to the app recipe '
            f'artifact at {DEFAULT_RECIPE_FILE}.'
        ),
    )
    return parser.parse_args()


if __name__ == '__main__':
    args = _parse_args()
    if args.workers < 1:
        raise SystemExit('--workers must be at least 1.')
    _load_recipe_file(args.recipe_file)
    build(
        args.output,
        summary=args.summary,
        workers=args.workers,
    )
    print(f'Written: {args.output}')
