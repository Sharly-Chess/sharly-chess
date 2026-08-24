#!/usr/bin/env python3
"""Build the DNA Molter reference workbook.

By default this workbook contains the public reference range requested for
software reuse:

    N = 3..15 teams
    P = 2, 4, 6, 8, 10, 12 players per team
    R = 2..N-1 rounds

That written range contains 546 tables.

Pass ``--all-recipes`` to write every recipe present in the selected artifact.
This is useful for comparing complete old and new artifacts while retaining the
README, filterable quality index, hyperlinks, and one sheet per team count.
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SRC_DIR = ROOT / 'src'
THIS_DIR = Path(__file__).resolve().parent
DEFAULT_OUTPUT = THIS_DIR / 'molter_dna_tables.xlsx'
DEFAULT_RECIPE_FILE = (
    SRC_DIR / 'data' / 'pairings' / 'resources' / 'molter_recipes.mrec'
)

sys.path.insert(0, str(SRC_DIR))
sys.path.insert(0, str(THIS_DIR))

import xlsxwriter  # noqa: E402
from xlsxwriter.utility import xl_rowcol_to_cell  # noqa: E402

import build_xlsx as molter_xlsx  # noqa: E402
from data.pairings.molter_verifier import verify_molter_table  # noqa: E402


DNA_TEAM_COUNTS = tuple(range(3, 16))
PLAYER_COUNTS = (2, 4, 6, 8, 10, 12)


@dataclass(frozen=True)
class CaseIndexRow:
    team_count: int
    players_per_team: int
    rounds: int
    sheet_name: str
    anchor_cell: str
    board_count: int
    i1: int
    i1_prefix_deficit: int
    i2: int
    i3: int
    i4: int
    i5: int


def _iter_dna_cases() -> list[tuple[int, int, int]]:
    return [
        (team_count, players_per_team, rounds)
        for team_count in DNA_TEAM_COUNTS
        for players_per_team in PLAYER_COUNTS
        for rounds in range(2, team_count)
    ]


def _iter_all_recipe_cases() -> list[tuple[int, int, int]]:
    return sorted(molter_xlsx._RECIPE_BY_KEY)


def _scope_text(cases: list[tuple[int, int, int]], *, all_recipes: bool) -> str:
    if not all_recipes:
        return (
            'N = 3 a 15 equipes; P = 2, 4, 6, 8, 10, 12 joueurs par equipe; '
            'R = 2 a N-1 rondes.'
        )
    team_counts = sorted({team_count for team_count, _players, _rounds in cases})
    players = sorted({players for _team_count, players, _rounds in cases})
    rounds = sorted({rounds for _team_count, _players, rounds in cases})
    return (
        "Toutes les recettes presentes dans l'artefact: "
        f'N = {team_counts[0]} a {team_counts[-1]} equipes; '
        f'P = {", ".join(str(player) for player in players)} joueurs par equipe; '
        f'R = {rounds[0]} a {rounds[-1]} rondes selon N.'
    )


def _format_url_sheet(sheet_name: str, anchor_cell: str) -> str:
    escaped = sheet_name.replace("'", "''")
    return f"internal:'{escaped}'!{anchor_cell}"


def _make_formats(wb) -> dict[str, object]:
    return {
        'title': wb.add_format({'bold': True, 'font_size': 14}),
        'section': wb.add_format({'bold': True, 'font_size': 12}),
        'sub': wb.add_format({'italic': True, 'font_color': '#555555'}),
        'header': wb.add_format(
            {
                'bold': True,
                'bg_color': '#1F3864',
                'font_color': 'white',
                'border': 1,
                'align': 'center',
                'text_wrap': True,
            }
        ),
        'board': wb.add_format({'border': 1, 'align': 'center', 'bg_color': '#F2F2F2'}),
        'cell': wb.add_format({'border': 1, 'align': 'center'}),
        'text': wb.add_format({'border': 1, 'valign': 'top', 'text_wrap': True}),
        'input': wb.add_format({'border': 1, 'align': 'center', 'bg_color': '#FFF2CC'}),
        'floater': wb.add_format({'font_color': '#C00000'}),
        'team': wb.add_format({'bg_color': '#FFF2CC'}),
        'good': wb.add_format({'border': 1, 'align': 'center', 'bg_color': '#E7F6EC'}),
        'warn': wb.add_format({'border': 1, 'align': 'center', 'bg_color': '#FDF3E0'}),
        'link': wb.add_format(
            {'border': 1, 'font_color': '#0563C1', 'underline': True}
        ),
    }


def _write_readme_sheet(
    wb,
    formats: dict[str, object],
    cases: list[tuple[int, int, int]],
    *,
    all_recipes: bool,
) -> None:
    ws = wb.add_worksheet('README')
    ws.set_column(0, 0, 24)
    ws.set_column(1, 1, 100)
    ws.write(0, 0, 'Tableaux Molter DNA', formats['title'])
    rows = [
        (
            'Perimetre',
            _scope_text(cases, all_recipes=all_recipes),
        ),
        ('Nombre de tableaux', str(len(cases))),
        (
            'Reutilisation',
            "Les concepteurs de logiciels d'appariements par equipe sont "
            'autorises a reutiliser ces tableaux et a les integrer dans leurs '
            'logiciels.',
        ),
        (
            'Convention de couleur',
            'Dans chaque case, le premier joueur nomme a les blancs.',
        ),
        (
            'Convention flotteur',
            'Pour un flotteur entre les echiquiers i et i+1, avec i impair, '
            "l'echiquier i descend. Le sens descendant/ascendant ne depend ni "
            'de la couleur ni de la position gauche/droite dans la case.',
        ),
        (
            'Validation',
            'Chaque tableau est reconstruit depuis les recettes Molter compactes '
            'et valide par le verificateur avant ecriture du classeur.',
        ),
        (
            'Navigation',
            "L'onglet Index pointe vers chaque tableau. Chaque onglet N possede "
            "un selecteur d'equipe en B1 et une case E1 pour colorer les "
            'matchs flotteurs en rouge.',
        ),
    ]
    for row, (label, value) in enumerate(rows, start=2):
        ws.write(row, 0, label, formats['header'])
        ws.write(row, 1, value, formats['text'])


def _write_index_sheet(
    ws, formats: dict[str, object], index_rows: list[CaseIndexRow]
) -> None:
    headers = [
        'Tableau',
        'N',
        'P',
        'R',
        'Onglet',
        'Cellule',
        'Echiquiers',
        'I1',
        'I1 prefixe',
        'I2',
        'I3',
        'I4',
        'I5',
    ]
    ws.set_column(0, 0, 22)
    ws.set_column(1, 6, 10)
    ws.set_column(4, 5, None, None, {'hidden': True})
    ws.set_column(7, 12, 11)
    for col, header in enumerate(headers):
        ws.write(0, col, header, formats['header'])
    for row, item in enumerate(index_rows, start=1):
        label = f'N={item.team_count} P={item.players_per_team} R={item.rounds}'
        ws.write_url(
            row,
            0,
            _format_url_sheet(item.sheet_name, item.anchor_cell),
            formats['link'],
            label,
        )
        values = [
            item.team_count,
            item.players_per_team,
            item.rounds,
            item.sheet_name,
            item.anchor_cell,
            item.board_count,
            item.i1,
            item.i1_prefix_deficit,
            item.i2,
            item.i3,
            item.i4,
            item.i5,
        ]
        for col, value in enumerate(values, start=1):
            ws.write(row, col, value, formats['cell'])
    ws.autofilter(0, 0, len(index_rows), len(headers) - 1)
    ws.freeze_panes(1, 1)


def _write_case_block(
    ws,
    *,
    row: int,
    team_count: int,
    players_per_team: int,
    rounds: int,
    table,
    formats: dict[str, object],
    marker_start_col: int,
) -> tuple[int, str]:
    anchor_cell = xl_rowcol_to_cell(row, 0)
    board_count = team_count * players_per_team // 2
    ws.write(
        row,
        0,
        f'{team_count} equipes x {players_per_team} joueurs - {rounds} rondes',
        formats['title'],
    )
    row += 1
    ws.write(
        row,
        0,
        f'{board_count} echiquiers - {rounds} rondes - premier nomme = blancs',
        formats['sub'],
    )
    row += 1
    ws.write(row, 0, 'Ech.', formats['header'])
    for col in range(1, rounds + 1):
        ws.write(row, col, f'Ronde {col}', formats['header'])
    row += 1
    first_pairing_row = row
    for board in range(board_count):
        ws.write(row, 0, board + 1, formats['board'])
        for col, round_ in enumerate(table.rounds, start=1):
            pairing = round_[board]
            ws.write(row, col, molter_xlsx._pairing_text(pairing), formats['cell'])
            ws.write_boolean(
                row,
                marker_start_col + col - 1,
                pairing.white_index != pairing.black_index,
            )
        row += 1
    molter_xlsx._apply_floater_highlight(
        ws,
        first_pairing_row,
        row - 1,
        1,
        rounds,
        marker_start_col,
        formats['floater'],
    )
    molter_xlsx._apply_team_highlight(
        ws,
        first_pairing_row,
        row - 1,
        1,
        rounds,
        formats['team'],
    )
    return row + 2, anchor_cell


def _write_team_sheet(
    wb,
    formats: dict[str, object],
    team_count: int,
    cases: list[tuple[int, int, int]],
) -> list[CaseIndexRow]:
    sheet_name = f'N={team_count}'
    ws = wb.add_worksheet(sheet_name)
    max_rounds = max(rounds for _team_count, _players, rounds in cases)
    marker_start_col = max_rounds + 3
    ws.set_column(0, 0, 10)
    ws.set_column(1, max_rounds, 18)
    ws.set_column(
        marker_start_col,
        marker_start_col + max_rounds - 1,
        None,
        None,
        {'hidden': True},
    )
    molter_xlsx._write_table_controls(
        ws,
        team_count,
        formats['title'],
        formats['sub'],
        formats['input'],
        highlight_floaters=True,
    )
    row = 3
    index_rows: list[CaseIndexRow] = []
    for _team_count, players_per_team, rounds in cases:
        table = molter_xlsx._generate_table(team_count, players_per_team, rounds)
        report = verify_molter_table(table)
        if not report.ok:
            details = '; '.join(report.errors)
            raise ValueError(
                f'Invalid Molter table N={team_count} P={players_per_team} '
                f'R={rounds}: {details}'
            )
        row, anchor_cell = _write_case_block(
            ws,
            row=row,
            team_count=team_count,
            players_per_team=players_per_team,
            rounds=rounds,
            table=table,
            formats=formats,
            marker_start_col=marker_start_col,
        )
        i1, i1_prefix_deficit, i2, i3, i4, i5 = molter_xlsx._measures(table, team_count)
        index_rows.append(
            CaseIndexRow(
                team_count=team_count,
                players_per_team=players_per_team,
                rounds=rounds,
                sheet_name=sheet_name,
                anchor_cell=anchor_cell,
                board_count=team_count * players_per_team // 2,
                i1=i1,
                i1_prefix_deficit=i1_prefix_deficit,
                i2=i2,
                i3=i3,
                i4=i4,
                i5=i5,
            )
        )
    ws.freeze_panes(3, 1)
    return index_rows


def build(
    output: Path,
    recipe_file: Path | None = None,
    *,
    all_recipes: bool = False,
) -> int:
    recipe_source = recipe_file or DEFAULT_RECIPE_FILE
    molter_xlsx._load_recipe_file(str(recipe_source))
    expected_cases = _iter_all_recipe_cases() if all_recipes else _iter_dna_cases()
    if not expected_cases:
        raise ValueError(f'No supported recipes found in {recipe_source}.')
    missing = [
        case for case in expected_cases if case not in molter_xlsx._RECIPE_BY_KEY
    ]
    if missing:
        sample = ', '.join(f'N={n} P={p} R={r}' for n, p, r in missing[:10])
        raise ValueError(f'Missing {len(missing)} requested recipes: {sample}')

    output.parent.mkdir(parents=True, exist_ok=True)
    wb = xlsxwriter.Workbook(str(output))
    formats = _make_formats(wb)
    _write_readme_sheet(
        wb,
        formats,
        expected_cases,
        all_recipes=all_recipes,
    )
    index_sheet = wb.add_worksheet('Index')
    all_index_rows: list[CaseIndexRow] = []
    team_counts = sorted(
        {team_count for team_count, _players, _rounds in expected_cases}
    )
    for team_count in team_counts:
        team_cases = [case for case in expected_cases if case[0] == team_count]
        all_index_rows.extend(_write_team_sheet(wb, formats, team_count, team_cases))
    _write_index_sheet(index_sheet, formats, all_index_rows)
    wb.close()
    return len(all_index_rows)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        'output',
        nargs='?',
        type=Path,
        default=DEFAULT_OUTPUT,
        help=f'Output .xlsx path (default: {DEFAULT_OUTPUT}).',
    )
    parser.add_argument(
        '--recipe-file',
        type=Path,
        default=DEFAULT_RECIPE_FILE,
        help=f'Recipe artifact to replay (default: {DEFAULT_RECIPE_FILE}).',
    )
    parser.add_argument(
        '--all-recipes',
        action='store_true',
        help=(
            'Write every supported recipe in the selected artifact instead of '
            'the fixed N=3..15, R=2..N-1 DNA reference range.'
        ),
    )
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    count = build(
        args.output,
        args.recipe_file,
        all_recipes=args.all_recipes,
    )
    print(f'Written: {args.output}')
    print(f'Tables: {count}')


if __name__ == '__main__':
    main()
