#!/usr/bin/env python3
"""Run reproducible Molter solver-recipe build passes.

This script is the reproducibility layer above ``build_solver_recipes.py``. Each
pass writes its own resumable recipe file, then the pass outputs are merged by
metric priority into one compact replay artifact. The merged artifact is still a
generated output: the source of truth is this deterministic pass list plus the
builder source.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Callable

import build_solver_recipes as recipes
from molter_recipe_generator import generate_molter_table

ROOT = Path(__file__).resolve().parents[3]
BUILDER = Path(__file__).with_name('build_solver_recipes.py')
DEFAULT_OUTPUT = ROOT / '.context' / 'quality_grid_all_recipes.json'
DEFAULT_WORK_DIR = ROOT / '.context' / 'solver_recipe_suite'
GRID_CASES = recipes._grid_cases(
    recipes.DEFAULT_GRID_MIN_TEAM_COUNT,
    recipes.DEFAULT_GRID_MAX_TEAM_COUNT,
    recipes.DEFAULT_GRID_PLAYERS,
    recipes.DEFAULT_GRID_MAX_ROUNDS,
    include_full_tables=recipes.DEFAULT_GRID_INCLUDE_FULL_TABLES,
)

Case = tuple[int, int, int]
Selector = Callable[[dict[str, dict]], tuple[Case, ...]]


@dataclass(frozen=True)
class PassSpec:
    name: str
    selector: Selector
    candidate_limit: int
    strict_s5_timeout_seconds: float
    timeout_seconds: float
    workers: int
    case_workers: int
    odd_phase_policies: tuple[str, ...] = ()
    odd_colour_integrated_timeout_seconds: float = 0.0
    odd_colour_integrated_attempts: int = 0
    odd_colour_integrated_options_per_factor: int = 8
    odd_integrated_timeout_seconds: float = 0.0
    odd_integrated_attempts: int = 0
    odd_integrated_options_per_factor: int = 8
    odd_offset_candidate_limit: int = 0
    odd_offset_max_permutations: int = 750_000
    odd_direct_offsets_only: bool = False
    odd_row_solver_timeout_seconds: float = 0.0
    odd_row_solver_attempts: int = 0
    direct_colour_only: bool = False
    even_integrated_timeout_seconds: float = 0.0
    even_integrated_attempts: int = 0
    even_row_solver_timeout_seconds: float = 0.0
    even_row_solver_attempts: int = 1
    emit_baseline_recipes: bool = False
    strict_s5_recolour_existing: bool = False


def _builder_hash() -> str:
    digest = hashlib.sha256()
    for path in (BUILDER, Path(__file__)):
        digest.update(path.read_bytes())
    return digest.hexdigest()


def _case_key(case: Case) -> str:
    return f'{case[0]}:{case[1]}:{case[2]}'


def _i1_lower_bound(team_count: int, players_per_team: int, rounds: int) -> int:
    return 0 if (players_per_team * rounds) % (team_count - 1) == 0 else 1


def _load_recipes(path: Path) -> dict[str, dict]:
    if not path.exists():
        return {}
    payload = recipes._load_recipe_payload(path)
    return {recipes._case_key(case): case for case in payload.get('cases', [])}


def _metrics_for_case(case: Case, recipe_by_key: dict[str, dict]) -> recipes.Metrics:
    recipe = recipe_by_key.get(_case_key(case))
    if recipe is not None:
        return recipes._metrics(recipes.materialize_recipe(recipe))
    team_count, players_per_team, rounds = case
    return recipes._metrics(generate_molter_table(team_count, players_per_team, rounds))


def _quality_gaps(
    recipe_by_key: dict[str, dict],
    *,
    parity: str | None = None,
) -> tuple[Case, ...]:
    out: list[Case] = []
    for case in GRID_CASES:
        team_count, players_per_team, rounds = case
        if parity == 'odd' and team_count % 2 == 0:
            continue
        if parity == 'even' and team_count % 2 == 1:
            continue
        metrics = _metrics_for_case(case, recipe_by_key)
        if (
            metrics.i1 > _i1_lower_bound(team_count, players_per_team, rounds)
            or metrics.i1_prefix_deficit > 0
        ):
            out.append(case)
    return tuple(out)


def _severe_quality_gaps(
    recipe_by_key: dict[str, dict],
    *,
    parity: str | None = None,
) -> tuple[Case, ...]:
    out: list[Case] = []
    for case in GRID_CASES:
        team_count, _players_per_team, _rounds = case
        if parity == 'odd' and team_count % 2 == 0:
            continue
        if parity == 'even' and team_count % 2 == 1:
            continue
        metrics = _metrics_for_case(case, recipe_by_key)
        if metrics.i1 > 1 or metrics.i1_prefix_deficit > 0:
            out.append(case)
    return tuple(out)


def _all_grid(_recipe_by_key: dict[str, dict]) -> tuple[Case, ...]:
    return GRID_CASES


def _odd_quality_gaps(recipe_by_key: dict[str, dict]) -> tuple[Case, ...]:
    return _quality_gaps(recipe_by_key, parity='odd')


def _odd_short_quality_gaps(recipe_by_key: dict[str, dict]) -> tuple[Case, ...]:
    return tuple(case for case in _odd_quality_gaps(recipe_by_key) if case[2] <= 9)


def _odd_severe_quality_gaps(recipe_by_key: dict[str, dict]) -> tuple[Case, ...]:
    return _severe_quality_gaps(recipe_by_key, parity='odd')


def _odd_worst_quality_gaps(recipe_by_key: dict[str, dict]) -> tuple[Case, ...]:
    scored: list[tuple[tuple[int, int, int, int, int], Case]] = []
    for case in _severe_quality_gaps(recipe_by_key, parity='odd'):
        team_count, _players_per_team, _rounds = case
        metrics = _metrics_for_case(case, recipe_by_key)
        score = (
            20 * max(0, metrics.i1 - 1) + 10 * metrics.i1_prefix_deficit,
            metrics.i1,
            metrics.i1_prefix_deficit,
            team_count,
            case[2],
        )
        scored.append((score, case))
    scored.sort(reverse=True)
    return tuple(case for _score, case in scored[:24])


def _even_quality_gaps(recipe_by_key: dict[str, dict]) -> tuple[Case, ...]:
    return _quality_gaps(recipe_by_key, parity='even')


def _relaxed_s5_cases(recipe_by_key: dict[str, dict]) -> tuple[Case, ...]:
    out: list[Case] = []
    for case in GRID_CASES:
        recipe = recipe_by_key.get(_case_key(case))
        if recipe is None:
            continue
        if not recipes._metrics(recipes.materialize_recipe(recipe)).exact_s5:
            out.append(case)
    return tuple(out)


ODD_ROW_CP_TARGETS: tuple[Case, ...] = (
    (15, 10, 12),
    (15, 12, 8),
    (15, 12, 10),
)


def _odd_row_cp_targets(recipe_by_key: dict[str, dict]) -> tuple[Case, ...]:
    gap_cases = set(_quality_gaps(recipe_by_key, parity='odd'))
    return tuple(case for case in ODD_ROW_CP_TARGETS if case in gap_cases)


PASSES: tuple[PassSpec, ...] = (
    PassSpec(
        name='grid_baseline',
        selector=_all_grid,
        candidate_limit=0,
        strict_s5_timeout_seconds=0.0,
        timeout_seconds=0.0,
        workers=8,
        case_workers=1,
        emit_baseline_recipes=True,
    ),
    PassSpec(
        name='odd_i1_prefix',
        selector=_odd_quality_gaps,
        candidate_limit=200,
        strict_s5_timeout_seconds=0.5,
        timeout_seconds=12.0,
        workers=2,
        case_workers=8,
    ),
    PassSpec(
        name='odd_phase_direct_i1_prefix',
        selector=_odd_quality_gaps,
        candidate_limit=12,
        strict_s5_timeout_seconds=0.0,
        timeout_seconds=0.0,
        workers=8,
        case_workers=8,
        odd_phase_policies=('round_block', 'factor', 'round', 'block'),
        direct_colour_only=True,
    ),
    PassSpec(
        name='odd_integrated_i1_prefix',
        selector=_odd_quality_gaps,
        candidate_limit=16,
        strict_s5_timeout_seconds=0.0,
        timeout_seconds=0.0,
        workers=8,
        case_workers=4,
        odd_integrated_timeout_seconds=15.0,
        odd_integrated_attempts=1,
        odd_integrated_options_per_factor=8,
        direct_colour_only=True,
    ),
    PassSpec(
        name='odd_colour_integrated_i1_prefix_short',
        selector=_odd_short_quality_gaps,
        candidate_limit=8,
        strict_s5_timeout_seconds=0.0,
        timeout_seconds=0.0,
        workers=4,
        case_workers=2,
        odd_colour_integrated_timeout_seconds=45.0,
        odd_colour_integrated_attempts=1,
        odd_colour_integrated_options_per_factor=8,
        direct_colour_only=True,
    ),
    PassSpec(
        name='odd_phase_i1_prefix',
        selector=_odd_quality_gaps,
        candidate_limit=3,
        strict_s5_timeout_seconds=0.5,
        timeout_seconds=10.0,
        workers=8,
        case_workers=4,
        odd_phase_policies=('round_block', 'factor', 'round'),
    ),
    PassSpec(
        name='odd_wide_offsets_i1_prefix',
        selector=_odd_severe_quality_gaps,
        candidate_limit=16,
        strict_s5_timeout_seconds=0.5,
        timeout_seconds=2.0,
        workers=8,
        case_workers=4,
        odd_phase_policies=('round_block', 'factor', 'round', 'block'),
        odd_offset_candidate_limit=80,
        odd_offset_max_permutations=750_000,
        odd_direct_offsets_only=True,
    ),
    PassSpec(
        name='odd_direct_offsets_worst_high_budget',
        selector=_odd_worst_quality_gaps,
        candidate_limit=128,
        strict_s5_timeout_seconds=0.2,
        timeout_seconds=0.8,
        workers=8,
        case_workers=4,
        odd_phase_policies=('round_block', 'factor', 'round', 'block'),
        odd_offset_candidate_limit=80,
        odd_offset_max_permutations=750_000,
        odd_direct_offsets_only=True,
    ),
    PassSpec(
        name='odd_row_cp_i1_prefix',
        selector=_odd_worst_quality_gaps,
        candidate_limit=24,
        strict_s5_timeout_seconds=0.0,
        timeout_seconds=0.0,
        workers=8,
        case_workers=2,
        odd_row_solver_timeout_seconds=45.0,
        odd_row_solver_attempts=8,
        direct_colour_only=True,
    ),
    PassSpec(
        name='even_i1_prefix',
        selector=_even_quality_gaps,
        candidate_limit=8,
        strict_s5_timeout_seconds=0.5,
        even_row_solver_timeout_seconds=5.0,
        even_row_solver_attempts=8,
        timeout_seconds=5.0,
        workers=8,
        case_workers=4,
    ),
    PassSpec(
        name='even_integrated_i1_prefix_parallel',
        selector=_even_quality_gaps,
        candidate_limit=16,
        strict_s5_timeout_seconds=0.0,
        timeout_seconds=0.0,
        workers=4,
        case_workers=2,
        direct_colour_only=True,
        even_integrated_timeout_seconds=20.0,
        even_integrated_attempts=2,
    ),
    PassSpec(
        name='even_integrated_i1_prefix_serial',
        selector=_even_quality_gaps,
        candidate_limit=16,
        strict_s5_timeout_seconds=0.0,
        timeout_seconds=0.0,
        workers=8,
        case_workers=1,
        direct_colour_only=True,
        even_integrated_timeout_seconds=35.0,
        even_integrated_attempts=1,
    ),
    PassSpec(
        name='even_integrated_i1_prefix_high_budget',
        selector=_even_quality_gaps,
        candidate_limit=16,
        strict_s5_timeout_seconds=0.0,
        timeout_seconds=0.0,
        workers=8,
        case_workers=1,
        direct_colour_only=True,
        even_integrated_timeout_seconds=75.0,
        even_integrated_attempts=1,
    ),
    PassSpec(
        name='strict_s5_recolour',
        selector=_relaxed_s5_cases,
        candidate_limit=0,
        strict_s5_timeout_seconds=0.25,
        timeout_seconds=0.0,
        workers=4,
        case_workers=8,
        strict_s5_recolour_existing=True,
    ),
)


def _write_case_file(path: Path, cases: tuple[Case, ...]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(cases, separators=(',', ':')) + '\n')


def _run(command: list[str], *, dry_run: bool) -> None:
    print(' '.join(command), flush=True)
    if not dry_run:
        subprocess.run(command, check=True)


def _run_pass(
    spec: PassSpec,
    output: Path,
    work_dir: Path,
    *,
    dry_run: bool,
    max_cases: int | None,
    force: bool,
) -> Path:
    if dry_run and not output.exists():
        cases = GRID_CASES
    else:
        recipe_by_key = _load_recipes(output)
        cases = spec.selector(recipe_by_key)
    if max_cases is not None:
        cases = cases[:max_cases]
    case_file = work_dir / f'{spec.name}_cases.json'
    pass_output = work_dir / f'{spec.name}.json'
    _write_case_file(case_file, cases)
    print(f'{spec.name}: {len(cases)} case(s)', flush=True)
    if not cases:
        return pass_output

    _run(
        [
            sys.executable,
            str(BUILDER),
            '--output',
            str(pass_output),
            *(
                ['--merge-input', str(output)]
                if spec.strict_s5_recolour_existing
                else []
            ),
            '--case-file',
            str(case_file),
            '--candidate-limit',
            str(spec.candidate_limit),
            '--odd-phase-policies',
            ','.join(spec.odd_phase_policies),
            '--odd-colour-integrated-timeout-seconds',
            str(spec.odd_colour_integrated_timeout_seconds),
            '--odd-colour-integrated-attempts',
            str(spec.odd_colour_integrated_attempts),
            '--odd-colour-integrated-options-per-factor',
            str(spec.odd_colour_integrated_options_per_factor),
            '--odd-integrated-timeout-seconds',
            str(spec.odd_integrated_timeout_seconds),
            '--odd-integrated-attempts',
            str(spec.odd_integrated_attempts),
            '--odd-integrated-options-per-factor',
            str(spec.odd_integrated_options_per_factor),
            '--odd-offset-candidate-limit',
            str(spec.odd_offset_candidate_limit),
            '--odd-offset-max-permutations',
            str(spec.odd_offset_max_permutations),
            *(['--odd-direct-offsets-only'] if spec.odd_direct_offsets_only else []),
            '--odd-row-solver-timeout-seconds',
            str(spec.odd_row_solver_timeout_seconds),
            '--odd-row-solver-attempts',
            str(spec.odd_row_solver_attempts),
            *(['--direct-colour-only'] if spec.direct_colour_only else []),
            '--strict-s5-timeout-seconds',
            str(spec.strict_s5_timeout_seconds),
            '--even-integrated-timeout-seconds',
            str(spec.even_integrated_timeout_seconds),
            '--even-integrated-attempts',
            str(spec.even_integrated_attempts),
            '--even-row-solver-timeout-seconds',
            str(spec.even_row_solver_timeout_seconds),
            '--even-row-solver-attempts',
            str(spec.even_row_solver_attempts),
            '--timeout-seconds',
            str(spec.timeout_seconds),
            '--workers',
            str(spec.workers),
            '--case-workers',
            str(spec.case_workers),
            *(['--emit-baseline-recipes'] if spec.emit_baseline_recipes else []),
            *(['--force'] if force else []),
            *(
                ['--strict-s5-recolour-existing']
                if spec.strict_s5_recolour_existing
                else []
            ),
            '--builder-pass',
            spec.name,
        ],
        dry_run=dry_run,
    )
    return pass_output


def _merge(output: Path, pass_outputs: list[Path], *, dry_run: bool) -> None:
    existing = [path for path in pass_outputs if path.exists()]
    if not existing:
        return
    command = [
        sys.executable,
        str(BUILDER),
        '--quality-grid',
        '--output',
        str(output),
        '--merge-only',
        '--ignore-existing-output',
        '--prune-output-to-cases',
        '--progress-every',
        '0',
    ]
    for path in existing:
        command.extend(['--merge-input', str(path)])
    _run(command, dry_run=dry_run)


def _write_manifest(output: Path, work_dir: Path, pass_outputs: list[Path]) -> None:
    manifest = {
        'generated_at_utc': datetime.now(UTC).strftime('%Y-%m-%dT%H:%M:%SZ'),
        'builder_sha256': _builder_hash(),
        'output': str(output),
        'passes': [
            {
                'name': spec.name,
                'candidate_limit': spec.candidate_limit,
                'odd_phase_policies': list(spec.odd_phase_policies),
                'odd_colour_integrated_timeout_seconds': (
                    spec.odd_colour_integrated_timeout_seconds
                ),
                'odd_colour_integrated_attempts': (spec.odd_colour_integrated_attempts),
                'odd_colour_integrated_options_per_factor': (
                    spec.odd_colour_integrated_options_per_factor
                ),
                'odd_integrated_timeout_seconds': (spec.odd_integrated_timeout_seconds),
                'odd_integrated_attempts': spec.odd_integrated_attempts,
                'odd_integrated_options_per_factor': (
                    spec.odd_integrated_options_per_factor
                ),
                'odd_offset_candidate_limit': spec.odd_offset_candidate_limit,
                'odd_offset_max_permutations': spec.odd_offset_max_permutations,
                'odd_direct_offsets_only': spec.odd_direct_offsets_only,
                'odd_row_solver_timeout_seconds': (spec.odd_row_solver_timeout_seconds),
                'odd_row_solver_attempts': spec.odd_row_solver_attempts,
                'direct_colour_only': spec.direct_colour_only,
                'strict_s5_timeout_seconds': spec.strict_s5_timeout_seconds,
                'even_integrated_timeout_seconds': (
                    spec.even_integrated_timeout_seconds
                ),
                'even_integrated_attempts': spec.even_integrated_attempts,
                'even_row_solver_timeout_seconds': (
                    spec.even_row_solver_timeout_seconds
                ),
                'even_row_solver_attempts': spec.even_row_solver_attempts,
                'timeout_seconds': spec.timeout_seconds,
                'workers': spec.workers,
                'case_workers': spec.case_workers,
                'emit_baseline_recipes': spec.emit_baseline_recipes,
                'strict_s5_recolour_existing': spec.strict_s5_recolour_existing,
                'output': str(pass_outputs[index]),
            }
            for index, spec in enumerate(PASSES[: len(pass_outputs)])
        ],
    }
    work_dir.mkdir(parents=True, exist_ok=True)
    (work_dir / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument('--work-dir', type=Path, default=DEFAULT_WORK_DIR)
    parser.add_argument(
        '--start-pass',
        choices=[spec.name for spec in PASSES],
        help='Skip deterministic passes before this pass.',
    )
    parser.add_argument(
        '--stop-after-pass',
        choices=[spec.name for spec in PASSES],
        help='Stop after this pass has been built and merged.',
    )
    parser.add_argument(
        '--max-cases-per-pass',
        type=int,
        help='Debug/smoke-test limit; omit for the real reproducible suite.',
    )
    parser.add_argument(
        '--force-pass-outputs',
        action='store_true',
        help='Recompute pass output files instead of resuming completed cases.',
    )
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()

    args.work_dir.mkdir(parents=True, exist_ok=True)
    pass_outputs: list[Path] = []
    started = args.start_pass is None
    for spec in PASSES:
        if spec.name == args.start_pass:
            started = True
        if not started:
            continue
        pass_output = _run_pass(
            spec,
            args.output,
            args.work_dir,
            dry_run=args.dry_run,
            max_cases=args.max_cases_per_pass,
            force=args.force_pass_outputs,
        )
        pass_outputs.append(pass_output)
        _merge(args.output, pass_outputs, dry_run=args.dry_run)
        _write_manifest(args.output, args.work_dir, pass_outputs)
        if spec.name == args.stop_after_pass:
            break


if __name__ == '__main__':
    main()
