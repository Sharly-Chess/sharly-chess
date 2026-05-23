"""FIDE title-norm evaluation (B.01, effective 1 January 2024).

Entry point: `TitleNormEvaluator(tournament_player).evaluate()` returns a
`dict[TitleNorm, NormCheckResult]` covering all four norms (GM, IM, WGM, WIM).

Spec mapping is annotated inline; section numbers refer to FIDE Handbook B.01
as summarised in `docs/technical-appendices/fide-title-norms.md`.

Public API:
- `NormInputs` — snapshot of pairings-derived data used by the per-rule checks.
- `TitleNormEvaluator` — the per-applicant evaluator.
- `TitleNormSubsetSearcher` — wraps the evaluator with 1.4.1e/f subset search.
- `TitleNormForecaster` / `ForecastRequirement` — what-if engine for future rounds.
- `compute_big_tournament_exemption` / `compute_high_level_tournament` —
  tournament-wide checks (1.4.3d, 1.5.6a) that `Tournament` delegates to.
"""

from data.norms.evaluator import TitleNormEvaluator
from data.norms.forecaster import ForecastRequirement, TitleNormForecaster
from data.norms.inputs import NormInputs
from data.norms.searcher import TitleNormSubsetSearcher
from data.norms.tournament_checks import (
    BigTournamentRoundCounts,
    HighLevelRoundCounts,
    apply_143abc_exemption,
    compute_big_tournament_exemption,
    compute_big_tournament_exemption_trail,
    compute_high_level_tournament,
    compute_high_level_tournament_trail,
)

__all__ = [
    'BigTournamentRoundCounts',
    'ForecastRequirement',
    'HighLevelRoundCounts',
    'NormInputs',
    'TitleNormEvaluator',
    'TitleNormForecaster',
    'TitleNormSubsetSearcher',
    'apply_143abc_exemption',
    'compute_big_tournament_exemption',
    'compute_big_tournament_exemption_trail',
    'compute_high_level_tournament',
    'compute_high_level_tournament_trail',
]
