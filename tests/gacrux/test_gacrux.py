"""Every test tournament, checked by Gacrux.

Gacrux is an open-source pairing checker, tie-break checker and
tournament generator by Otto Milvang (MIT, copyright FIDE), presented at
the 2026 FIDE TEC Congress meeting. It is not named in the endorsement
check-list, which asks instead (Q33) that our engines be tested against
"another publicly available pairing and tie-break engine". Gacrux is one
of those, and the only one we know of that checks tie-breaks as well as
pairings -- which matters, because our tie-break engine is our own and no
pairing-only checker can verify it.

These tests run it over the TRF26
export of every tournament the suite and the examples hold: the pairing
checker re-pairs every round and compares, and the tie-break checker
recomputes the standings, compared value by value with our own tie-break
engine.

A disagreement is a finding, not necessarily a bug on our side: each one
is settled in ``.context/tec/gacrux-reconciliation.md`` with the rule it
turns on, and the entries that turned out to be Gacrux's are the known
issues the harness recognises. Gacrux itself is the version pinned in
``tests/gacrux/harness`` and named in the report header.
"""

from collections.abc import Iterator
from pathlib import Path

import pytest

from data.tie_breaks import tie_breaks as individual
from data.tie_breaks.cutters import (
    Cut1TieBreakCutter,
    Cut2TieBreakCutter,
    Median1TieBreakCutter,
    TieBreakCutter,
)
from data.tie_breaks.options import (
    CutterTieBreakOption,
    CutterWithMedianTieBreakOption,
    ForeModifierTieBreakOption,
    KoyaLimitTieBreakOption,
    LegacyMarch2026TieBreakOption,
    PlayedModifierTieBreakOption,
    TieBreakOption,
)
from data.tie_breaks.tie_breaks import TieBreak
from tests.gacrux.harness import (
    TieBreakCheck,
    check_individual_tie_breaks,
    check_team_tie_breaks,
    export_trf,
    gacrux_spec,
    last_finished_round,
    rank_on,
    readable_trf,
)
from tests.gacrux.sources import LoadedTournament, json_sources

# Disagreements settled in the reconciliation as not ours to fix, by the
# id of the tournament they show on. A test that finds one gone fails,
# so the entry is retired with the disagreement.
EXPECTED_TIE_BREAK_DISAGREEMENTS = {
    'trf/tournament_importers/trf-team-import-test': (
        'T-CAP: Art. 16.4.2 cap on the dummy score, mid-tournament: Gacrux '
        'multiplies by the rounds played so far, we by the rounds scheduled'
    ),
}


def _settled(ok: bool, reason: str | None) -> None:
    """Apply the verdict of an expected disagreement: it is expected to
    show, and no longer expected once it stops showing."""
    if reason is None:
        return
    if ok:
        pytest.fail(f'expected disagreement no longer shows: {reason}')
    pytest.xfail(reason)


def _cut(cutter: type[TieBreakCutter]) -> CutterTieBreakOption:
    return CutterTieBreakOption(cutter.static_id())


def _median_cut(cutter: type[TieBreakCutter]) -> CutterWithMedianTieBreakOption:
    return CutterWithMedianTieBreakOption(cutter.static_id())


def _legacy() -> LegacyMarch2026TieBreakOption:
    return LegacyMarch2026TieBreakOption(True)


def _catalogue() -> list[TieBreak]:
    """Every individual tie-break Gacrux implements, in the variants the
    tie-break tests cover: with and without cuts, played-only, fore, and
    the pre-March-2026 legacy computation."""
    variants: list[tuple[type[TieBreak], list[TieBreakOption]]] = [
        (individual.PointsTieBreak, []),
        (individual.WinsTieBreak, []),
        (individual.GamesWonTieBreak, []),
        (individual.GamesPlayedWithBlackTieBreak, []),
        (individual.GamesWonWithBlackTieBreak, []),
        (individual.RoundsElectedToPlayTieBreak, []),
        (individual.StandardPointsTieBreak, []),
        (individual.ProgressiveScoresTieBreak, []),
        (individual.ProgressiveScoresTieBreak, [_cut(Cut1TieBreakCutter)]),
        (individual.StandardBuchholzTieBreak, []),
        (individual.StandardBuchholzTieBreak, [_median_cut(Cut1TieBreakCutter)]),
        (individual.StandardBuchholzTieBreak, [_median_cut(Cut2TieBreakCutter)]),
        (individual.StandardBuchholzTieBreak, [_median_cut(Median1TieBreakCutter)]),
        (individual.StandardBuchholzTieBreak, [PlayedModifierTieBreakOption(True)]),
        (individual.StandardBuchholzTieBreak, [_legacy()]),
        (
            individual.StandardBuchholzTieBreak,
            [_median_cut(Cut1TieBreakCutter), _legacy()],
        ),
        (
            individual.StandardBuchholzTieBreak,
            [_median_cut(Median1TieBreakCutter), _legacy()],
        ),
        (individual.ForeBuchholzTieBreak, []),
        (individual.ForeBuchholzTieBreak, [_median_cut(Cut1TieBreakCutter)]),
        (individual.ForeBuchholzTieBreak, [_legacy()]),
        (individual.AverageOfBuchholzTieBreak, []),
        (individual.AverageOfBuchholzTieBreak, [ForeModifierTieBreakOption(True)]),
        (individual.AverageOfBuchholzTieBreak, [_legacy()]),
        (individual.SonnebornBergerTieBreak, []),
        (individual.SonnebornBergerTieBreak, [_cut(Cut1TieBreakCutter)]),
        (individual.SonnebornBergerTieBreak, [PlayedModifierTieBreakOption(True)]),
        (individual.SonnebornBergerTieBreak, [_legacy()]),
        (individual.SonnebornBergerTieBreak, [_cut(Cut1TieBreakCutter), _legacy()]),
        (individual.KoyaTieBreak, []),
        (individual.KoyaTieBreak, [KoyaLimitTieBreakOption(1)]),
        (individual.KoyaTieBreak, [KoyaLimitTieBreakOption(-1)]),
        (individual.AverageRatingOpponentsTieBreak, []),
        (
            individual.AverageRatingOpponentsTieBreak,
            [_median_cut(Cut1TieBreakCutter)],
        ),
        (individual.TournamentPerformanceRatingTieBreak, []),
        (individual.AveragePerformanceRatingOpponentsTieBreak, []),
        (individual.PerfectTournamentPerformanceTieBreak, []),
        (individual.AveragePerfectPerformanceTieBreak, []),
        (individual.PlayerRatingTieBreak, []),
    ]
    return [tie_break_type(options) for tie_break_type, options in variants]


CATALOGUE = _catalogue()

# Ordered criteria whose effect is a rank change rather than a value
# (direct encounter), checked on the standings they produce.
ORDERED_SETS: list[list[TieBreak]] = [
    [individual.PointsTieBreak(), individual.DirectEncounterTieBreak()],
    [
        individual.PointsTieBreak(),
        individual.StandardBuchholzTieBreak([_median_cut(Cut1TieBreakCutter)]),
        individual.DirectEncounterTieBreak(),
    ],
    [
        individual.PointsTieBreak(),
        individual.DirectEncounterTieBreak([PlayedModifierTieBreakOption(True)]),
        individual.SonnebornBergerTieBreak(),
    ],
]

# The tie-break exercises: every round played, every kind of unplayed
# round represented.
TIE_BREAK_FIXTURES = [
    source
    for source in json_sources()
    if source.id
    in (
        'json/tec-swiss',
        'json/tec-swiss-direct-encounter',
        'json/tec-round-robin',
        'json/pl-swiss',
        'json/manual-koya',
    )
]


def _fixture(source_id: str) -> LoadedTournament:
    return LoadedTournament(next(s for s in TIE_BREAK_FIXTURES if s.id == source_id))


# ---------------------------------------------------------------------------
# Every tournament, as configured
# ---------------------------------------------------------------------------


@pytest.mark.gacrux
def test_tie_breaks(loaded: LoadedTournament, trf_path: Path) -> None:
    tournament = loaded.tournament
    tie_breaks = tournament.tie_breaks
    if not any(gacrux_spec(tie_break) for tie_break in tie_breaks):
        pytest.skip(
            'no Gacrux equivalent for '
            + ', '.join(tie_break.trf_acronym for tie_break in tie_breaks)
        )
    readable = readable_trf(trf_path, tournament)
    # Standings are compared after the last round every result is in: a
    # paired round still in play is in the export, not in the standings.
    after_round = min(readable.after_round, last_finished_round(tournament))
    if after_round == 0:
        pytest.skip('no round finished')
    check = (
        check_team_tie_breaks
        if tournament.is_team_tournament
        else check_individual_tie_breaks
    )(tournament, readable.path, tie_breaks, after_round=after_round)
    if not check.specs:
        pytest.skip(check.describe())
    _settled(check.ok, EXPECTED_TIE_BREAK_DISAGREEMENTS.get(loaded.source.id))
    assert check.ok, check.describe()


# ---------------------------------------------------------------------------
# The tie-break catalogue on the tie-break fixtures
# ---------------------------------------------------------------------------


class _CatalogueRuns:
    """One Gacrux run per fixture with the whole catalogue, shared by the
    tests that each look at one tie-break of it."""

    def __init__(self, tmp_path: Path) -> None:
        self.tmp_path = tmp_path
        self.loaded: dict[str, LoadedTournament] = {}
        self.checks: dict[str, TieBreakCheck] = {}

    def check(self, source_id: str) -> TieBreakCheck:
        if source_id not in self.checks:
            loaded = _fixture(source_id)
            self.loaded[source_id] = loaded
            trf = export_trf(loaded.tournament, self.tmp_path, loaded.uniq_id)
            self.checks[source_id] = check_individual_tie_breaks(
                loaded.tournament, trf, CATALOGUE
            )
        return self.checks[source_id]

    def delete(self) -> None:
        for loaded in self.loaded.values():
            loaded.delete()


@pytest.fixture(scope='module')
def catalogue_runs(
    tmp_path_factory: pytest.TempPathFactory,
) -> Iterator[_CatalogueRuns]:
    runs = _CatalogueRuns(tmp_path_factory.mktemp('gacrux'))
    yield runs
    runs.delete()


@pytest.mark.gacrux
@pytest.mark.parametrize('source', TIE_BREAK_FIXTURES, ids=str)
@pytest.mark.parametrize('tie_break', CATALOGUE, ids=gacrux_spec)
def test_tie_break_values(
    catalogue_runs: _CatalogueRuns, source: str, tie_break: TieBreak
) -> None:
    spec = gacrux_spec(tie_break)
    assert spec is not None
    check = catalogue_runs.check(str(source))
    assert not check.run.failed, check.run.describe()
    for left_out, reason in check.left_out:
        if left_out is tie_break:
            pytest.skip(reason)
    diffs = [diff for diff in check.value_diffs if diff.spec == spec]
    assert not diffs, '\n'.join(
        f'{spec} #{diff.competitor} {diff.name}: ours {diff.ours}, Gacrux {diff.gacrux}'
        for diff in diffs
    )


@pytest.mark.gacrux
@pytest.mark.parametrize('source', TIE_BREAK_FIXTURES, ids=str)
@pytest.mark.parametrize(
    'tie_breaks',
    ORDERED_SETS,
    ids=lambda tie_breaks: ','.join(t.trf_acronym for t in tie_breaks),
)
def test_standings_order(
    source: str, tie_breaks: list[TieBreak], tmp_path: Path
) -> None:
    loaded = LoadedTournament(
        next(s for s in TIE_BREAK_FIXTURES if s.id == str(source)), suffix='-order'
    )
    try:
        rank_on(loaded.tournament, tie_breaks)
        trf = export_trf(loaded.tournament, tmp_path, 'tournament')
        check = check_individual_tie_breaks(loaded.tournament, trf, tie_breaks)
        assert check.ok, check.describe()
    finally:
        loaded.delete()
