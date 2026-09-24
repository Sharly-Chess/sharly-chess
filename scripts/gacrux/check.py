"""Run the Gacrux checkers on the tournaments of an event, a TRF file or
a JSON test fixture, and print what they found.

    TEST_ENV=true PYTHONPATH=src:. ./venv/bin/python scripts/gacrux/check.py examples/events/minimal.sce
    TEST_ENV=true PYTHONPATH=src:. ./venv/bin/python scripts/gacrux/check.py tests/trf/example_trf26.trf
    TEST_ENV=true PYTHONPATH=src:. ./venv/bin/python scripts/gacrux/check.py tec-swiss --keep-trf out/

Every tournament is exported as TRF26 the way the application exports
it, then handed to both checkers; ``--keep-trf`` keeps the exports for
a run of Gacrux by hand (``-v`` on a checker prints its traceback).
"""

import argparse
import sys
import tempfile
from pathlib import Path

from tests.gacrux.harness import (
    check_individual_tie_breaks,
    check_pairings,
    check_team_tie_breaks,
    export_trf,
    gacrux_report_header,
    trf_export_unavailable,
)
from tests.gacrux.sources import (
    LoadedTournament,
    TournamentSource,
    example_sources,
    json_sources,
    trf_sources,
)


def sources_for(target: str) -> list[TournamentSource]:
    """The tournaments a command-line target names: a path to an event
    file, a TRF file, or the stem of a fixture in ``tests/json``."""
    path = Path(target)
    if path.suffix == '.sce':
        resolved = path.resolve()
        return [
            source
            for source in example_sources()
            if source.id.startswith(f'example/{resolved.stem}/')
            or source.id.startswith(f'example/other/{resolved.stem}/')
        ] or _adhoc_event_sources(resolved)
    if path.suffix == '.trf':
        return [s for s in trf_sources() if s.id.endswith(f'/{path.stem}')] or [
            _adhoc_trf_source(path.resolve())
        ]
    return [s for s in json_sources() if s.id == f'json/{target}']


def _adhoc_event_sources(sce_path: Path) -> list[TournamentSource]:
    from tests.gacrux.sources import _example_source, _example_tournaments

    return [
        _example_source(sce_path, tournament_id, name)
        for tournament_id, name in _example_tournaments(sce_path)
    ]


def _adhoc_trf_source(trf_path: Path) -> TournamentSource:
    from tests.gacrux.sources import _trf_source

    return _trf_source(trf_path)


def check(source: TournamentSource, directory: Path) -> bool:
    print(f'== {source.id}')
    loaded = LoadedTournament(source)
    try:
        tournament = loaded.tournament
        if message := trf_export_unavailable(tournament):
            print(f'   skipped: {message}')
            return True
        if tournament.current_round == 0:
            print('   skipped: no round paired')
            return True
        trf = export_trf(tournament, directory, loaded.uniq_id)
        print(f'   TRF: {trf}')
        ok = True
        pairings = check_pairings(trf)
        print(f'   pairings: {"ok" if pairings.ok else "MISMATCH"}')
        if not pairings.ok:
            ok = False
            print(_indent(pairings.describe()))
        tie_breaks = tournament.tie_breaks
        if tournament.is_team_tournament:
            standings = check_team_tie_breaks(tournament, trf, tie_breaks)
        else:
            standings = check_individual_tie_breaks(tournament, trf, tie_breaks)
        print(f'   tie-breaks: {"ok" if standings.ok else "MISMATCH"}')
        if not standings.ok:
            ok = False
            print(_indent(standings.describe()))
        return ok
    finally:
        loaded.delete()


def _indent(text: str) -> str:
    return '\n'.join(f'      {line}' for line in text.splitlines())


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    parser.add_argument('targets', nargs='+', help='.sce, .trf or tests/json stem')
    parser.add_argument(
        '--keep-trf', metavar='DIR', help='write the TRF exports to DIR'
    )
    args = parser.parse_args()
    print(gacrux_report_header())
    directory = (
        Path(args.keep_trf) if args.keep_trf else Path(tempfile.mkdtemp('gacrux'))
    )
    failures = 0
    for target in args.targets:
        sources = sources_for(target)
        if not sources:
            print(f'== {target}: nothing found')
            failures += 1
        for source in sources:
            if not check(source, directory):
                failures += 1
    return 1 if failures else 0


if __name__ == '__main__':
    sys.exit(main())
