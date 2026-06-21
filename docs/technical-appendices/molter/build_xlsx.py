#!/usr/bin/env python3
"""Build an Excel workbook of the Molter tables from the standalone script
(``molter_standalone.py``), so the workbook reflects exactly what the script
produces (deterministic generation).

By default the workbook has one sheet per team count with the complete tables
(all rounds = teams − 1). With ``--summary`` it instead produces a criteria
analysis: one tab per regular-round count (4, 6, … 50) giving the actual I1–I5
measures for every shape that genuinely runs that many rounds — a shape is only
listed once it can play that round count (``teams − 1 ≥ rounds``), so a table is
never repeated past its complete form.

Dependency: xlsxwriter (``pip install xlsxwriter``). For a dependency-free
output, use ``molter_standalone.py --grid --csv`` instead.

Usage:
    python3 build_xlsx.py [output.xlsx] [--summary]
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import xlsxwriter

import molter_standalone as ms

TEAM_COUNTS = range(3, 16)
PLAYER_COUNTS = (4, 6, 8, 10, 12, 14)
# Criteria analysis: one tab per round count (odd counts included, now that odd
# rounds are generated directly) up to the largest full table (N − 1 = 50 for
# N = 51), over teams 3–15 plus the large odd sizes.
ROUND_TABS = tuple(range(1, 51))
ANALYSIS_TEAMS = tuple(range(3, 16)) + tuple(range(17, 52, 2))


def _measures(table, team_count: int) -> tuple[int, int, int, int, int]:
    """Actual I1–I5 measures for a generated table (all are spreads/maxima;
    0 or 1 is best). I1: cumulative opponent-count spread per team. I2:
    descending-floater spread across teams. I3: max |ascending − descending|
    per team. I4: worst per-round opponent spread. I5: max floaters of one
    direction per team per round-pair (0 = no floaters, 1 = single layer)."""
    index = {ms._letter(i): i for i in range(team_count)}
    rounds = table.rounds
    round_pairs = (len(rounds) + 1) // 2
    down = [0] * team_count
    up = [0] * team_count
    pair = [[0] * team_count for _ in range(team_count)]
    rp_down = [[0] * team_count for _ in range(round_pairs)]
    rp_up = [[0] * team_count for _ in range(round_pairs)]
    i4 = 0
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
                i4 = max(i4, max(counts) - min(counts))
    i1 = 0
    for team in range(team_count):
        counts = [pair[team][o] for o in range(team_count) if pair[team][o]]
        if counts:
            i1 = max(i1, max(counts) - min(counts))
    i2 = max(down) - min(down)
    i3 = max(abs(up[t] - down[t]) for t in range(team_count))
    i5 = max(
        (
            max(rp_down[rp][t], rp_up[rp][t])
            for rp in range(round_pairs)
            for t in range(team_count)
        ),
        default=0,
    )
    return i1, i2, i3, i4, i5


_TRUNCATED_ROUNDS = 3


def _write_board_sheets(wb, title, sub, hdr, bd, cf) -> None:
    """One sheet per team count. For each shape it shows the full table and,
    when the full table is longer, the table generated directly for 3 rounds —
    which for odd team counts is re-optimised and need not be a prefix of the
    full table."""
    for n in TEAM_COUNTS:
        sh = wb.add_worksheet(f'{n} teams')
        sh.set_column(0, 0, 6)
        sh.set_column(1, 13, 16)
        r0 = 0
        for p in PLAYER_COUNTS:
            full = n - 1
            try:
                table = ms.generate_molter_table(n, p, full)
            except ms.MolterGenerationError:
                continue
            boards = n * p // 2
            all_rounds = list(table.rounds)

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
                for b in range(boards):
                    sh.write(r0, 0, b + 1, bd)
                    for c, rnd in enumerate(rounds, start=1):
                        sh.write(r0, c, str(rnd[b]), cf)
                    r0 += 1
                return r0 + 2

            r0 = block(r0, 'full table', all_rounds)
            if full > _TRUNCATED_ROUNDS:
                short = ms.generate_molter_table(n, p, _TRUNCATED_ROUNDS)
                r0 = block(
                    r0,
                    f'{_TRUNCATED_ROUNDS} rounds (generated)',
                    list(short.rounds),
                )


def _write_analysis_tabs(wb, title, sub, hdr, cf, good, warn) -> None:
    """One tab per round count with the actual I1–I5 measures.

    A shape appears on tab R only when it can run R rounds (teams − 1 ≥ R), so
    each shape is shown for every round count up to its complete table and never
    repeated once capped.
    """

    def fmt(value: int):
        return good if value == 0 else (cf if value == 1 else warn)

    cols = ['Teams', 'Players', 'Rounds', 'Valid', 'I1', 'I2', 'I3', 'I4', 'I5']
    for target in ROUND_TABS:
        ws = wb.add_worksheet(f'{target} rounds')
        ws.set_column(0, 8, 9)
        ws.write(0, 0, f'Criteria at {target} regular rounds — actual I1–I5', title)
        ws.write(
            1,
            0,
            'Spreads / maxima (0–1 best). I1 cumulative opponent spread · '
            'I2 descending-floater spread · I3 |asc − desc| · I4 per-round '
            'opponent spread · I5 floaters per team per round-pair (1 = single '
            'layer).',
            sub,
        )
        for c, name in enumerate(cols):
            ws.write(3, c, name, hdr)
        row = 4
        first_block = True
        for n in ANALYSIS_TEAMS:
            if n - 1 < target:
                continue
            if not first_block:
                row += 1  # blank separator row between team-count blocks
            first_block = False
            for p in PLAYER_COUNTS:
                try:
                    table = ms.generate_molter_table(n, p, target)
                except ms.MolterGenerationError:
                    continue
                ok = ms.verify_molter_table(table).ok
                i1, i2, i3, i4, i5 = _measures(table, n)
                ws.write(row, 0, n, cf)
                ws.write(row, 1, p, cf)
                ws.write(row, 2, target, cf)
                ws.write(row, 3, 'yes' if ok else 'NO', good if ok else warn)
                ws.write(row, 4, i1, fmt(i1))
                ws.write(row, 5, i2, fmt(i2))
                ws.write(row, 6, i3, fmt(i3))
                ws.write(row, 7, i4, fmt(i4))
                ws.write(row, 8, i5, cf)
                row += 1
        ws.freeze_panes(4, 0)


def build(path: str, summary: bool = False) -> None:
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
    good = wb.add_format({'border': 1, 'align': 'center', 'bg_color': '#E7F6EC'})
    warn = wb.add_format({'border': 1, 'align': 'center', 'bg_color': '#FDF3E0'})

    if summary:
        _write_analysis_tabs(wb, title, sub, hdr, cf, good, warn)
    else:
        _write_board_sheets(wb, title, sub, hdr, bd, cf)
    wb.close()


if __name__ == '__main__':
    args = [a for a in sys.argv[1:] if a != '--summary']
    summary = '--summary' in sys.argv[1:]
    out = (
        args[0] if args else str(Path(__file__).resolve().parent / 'molter-tables.xlsx')
    )
    build(out, summary=summary)
    print(f'Written: {out}')
