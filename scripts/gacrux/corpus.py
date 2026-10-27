"""Re-pair a corpus of TRF tournaments round by round and compare.

The corpus published at gacrux.no holds ~123 000 tournaments generated
and paired by Gacrux, from 7 players over 5 rounds to 2 400 over 21,
with byes, forfeits and accelerated rounds. Every round of every file is
a pairing our engine can be asked to reproduce: import the file, replay
it round by round, pair each round from the position before it, and
compare with what the file records.

A difference is our engine against Gacrux's, on a position neither of
them chose — which is the check the endorsement asks for, and the one
`tests/gacrux` cannot make, since the tournaments there are our own.

    PYTHONPATH=src:. ./venv/bin/python scripts/gacrux/corpus.py ~/Downloads/tournaments
    ... --dirs 't_n9*' --limit 2000 --jobs 8 --report out/

Each worker runs in a data directory of its own under ``tests/tmp``, so
several can import at once — but do not start a test run while this is
going: pytest empties ``tests/tmp`` whole and would pull the ground from
under the workers. Findings are written to the report directory: one
JSON line per tournament that differs, beside a copy of its TRF.
"""

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
import time
from collections import Counter
from contextlib import suppress
from collections.abc import Iterator
from pathlib import Path

#: 001 positions 58-68, the FIDE number. The generator derives it from
#: the starting rating, so every player of a tournament whose rating step
#: is zero is given the same one — which is not a tournament any reader
#: should accept. Those files are imported with the field blanked.
FIDE_ID_SLICE = slice(57, 68)


def tournament_files(
    root: Path, dirs: str | None, limit: int | None, max_players: int
) -> list[Path]:
    """The TRF files of the corpus, at most ``limit`` per directory.

    The corpus names each directory after the tournaments in it —
    ``t_n21_p2400`` is 21 rounds of 2 400 players — so the size is known
    without opening a file.
    """
    files: list[Path] = []
    for directory in sorted(p for p in root.iterdir() if p.is_dir()):
        if dirs and not directory.match(dirs):
            continue
        if max_players:
            match = re.search(r'_p(\d+)', directory.name)
            if match and int(match.group(1)) > max_players:
                continue
        found = sorted(directory.glob('*.trf'))
        files.extend(found[:limit] if limit else found)
    return files


def duplicate_fide_ids(text: str) -> bool:
    seen: set[str] = set()
    for line in text.splitlines():
        if not line.startswith('001'):
            continue
        fide_id = line[FIDE_ID_SLICE].strip()
        if fide_id and fide_id in seen:
            return True
        seen.add(fide_id)
    return False


def blank_fide_ids(text: str) -> str:
    lines = []
    for line in text.splitlines():
        if line.startswith('001') and len(line) > FIDE_ID_SLICE.start:
            line = (
                line[: FIDE_ID_SLICE.start].ljust(FIDE_ID_SLICE.start)
                + ' ' * (FIDE_ID_SLICE.stop - FIDE_ID_SLICE.start)
                + line[FIDE_ID_SLICE.stop :]
            )
        lines.append(line)
    return '\n'.join(lines) + '\n'


def check_file(path: Path, uniq_id: str) -> dict:
    """Import one tournament and re-pair each of its rounds.

    Returns the finding for that file: its verdict, and for a mismatch
    the rounds that differ with the boards that differ on them.
    """
    from data.input_output.tournament_importer_options import FileOption
    from data.input_output.trf.trf_importer import TrfTournamentImporter
    from data.loader import EventLoader
    from database.sqlite.event.event_database import EventDatabase

    result: dict = {'file': str(path), 'verdict': 'match', 'rounds': {}}
    text = path.read_text(encoding='latin-1')
    source = path
    temporary: Path | None = None
    if duplicate_fide_ids(text):
        result['normalised'] = 'blanked duplicate FIDE ids'
        handle = tempfile.NamedTemporaryFile(
            'w', suffix='.trf', delete=False, encoding='latin-1'
        )
        handle.write(blank_fide_ids(text))
        handle.close()
        source = temporary = Path(handle.name)
    started = time.perf_counter()
    try:
        EventDatabase(uniq_id).file.unlink(missing_ok=True)
        create_event(uniq_id)
        tournament_id = TrfTournamentImporter([FileOption(source)]).load_tournament(
            EventLoader().load_event(uniq_id)
        )
        EventLoader.unload_event(uniq_id)
        # The event has to outlive the tournament, which holds it weakly.
        event = EventLoader().load_event(uniq_id)
        tournament = event.tournaments_by_id[tournament_id]
        result['players'] = len(tournament.tournament_players_by_id)
        result['rounds_played'] = tournament.current_round
        engine = tournament.pairing_variation.engine
        for round_ in range(1, tournament.current_round + 1):
            if not tournament.round_has_pairings(round_):
                continue
            diff = engine.pairings_diff(tournament, round_, ignore_order=True)
            if diff:
                result['rounds'][round_] = [
                    {
                        'stored': _board(stored),
                        'repaired': _board(expected),
                    }
                    for stored, expected in diff
                ]
        if result['rounds']:
            result['verdict'] = _verdict_against_gacrux(source, result['rounds'])
    except Exception as error:
        result['verdict'] = 'error'
        result['error'] = f'{type(error).__name__}: {error}'
    finally:
        # A tournament that failed to import may have left no database.
        with suppress(Exception):
            EventDatabase(uniq_id).delete()
        if temporary:
            temporary.unlink(missing_ok=True)
    result['seconds'] = round(time.perf_counter() - started, 3)
    return result


def _verdict_against_gacrux(path: Path, rounds: dict) -> str:
    """What a difference from the file means, once Gacrux has been asked.

    The corpus is paired by Gacrux, so a round we pair differently is
    normally ours to answer for. Its ``misc`` directory, though, is
    published as "some correct, some With errors": where Gacrux's own
    checker rejects the same rounds, the file is the wrong one and our
    engine has agreed with the checker, not departed from it.
    """
    from tests.gacrux.harness import check_pairings

    check = check_pairings(path)
    if check.run.failed:
        return 'differs'
    rejected = {str(diff.round_) for diff in check.rounds}
    if rejected and rejected.issuperset(str(round_) for round_ in rounds):
        return 'file-rejected-by-gacrux'
    return 'differs'


def create_event(uniq_id: str) -> None:
    """An empty event to import into.

    ``TestUtils`` copies an event database it builds once and remembers,
    under the data directory this worker owns. A pytest run started
    alongside empties ``tests/tmp`` whole, taking that file with it, so a
    copy that finds it gone builds it again rather than ending the worker
    — see the warning this script prints on the way in.
    """
    from tests.test_config import TestUtils

    try:
        TestUtils.create_event(uniq_id)
    except FileNotFoundError:
        TestUtils._event_template_path = None
        TestUtils.create_event(uniq_id)


def _board(board) -> str | None:
    if board is None:
        return None
    white = board.white_tournament_player.pairing_number
    black = getattr(board.black_tournament_player, 'pairing_number', 0)
    return f'{white}-{black}'


def already_checked(out_path: Path) -> set[str]:
    """The files this worker has a verdict for.

    A run interrupted mid-write leaves a partial last line, which is not a
    verdict and is passed over: the file it belongs to is checked again.
    """
    done: set[str] = set()
    if not out_path.exists():
        return done
    for line in out_path.read_text().splitlines():
        if not line.strip():
            continue
        try:
            done.add(json.loads(line)['file'])
        except (json.JSONDecodeError, KeyError):
            continue
    return done


def run_worker(slice_path: Path, out_path: Path, resume: bool = False) -> int:
    files = [Path(line) for line in slice_path.read_text().splitlines() if line]
    # Any worker's verdicts count: a run resumed with another number of
    # workers slices the files differently.
    done: set[str] = set()
    if resume:
        for findings in out_path.parent.glob('findings-*.jsonl'):
            done |= already_checked(findings)
    with open(out_path, 'a' if resume else 'w') as out:
        if resume and done:
            # A partial line from the interrupted write would otherwise be
            # continued by the next one.
            out.write('\n')
        for index, path in enumerate(files):
            if str(path) in done:
                continue
            finding = check_file(path, f'corpus-{os.getpid()}-{index % 4}')
            out.write(json.dumps(finding) + '\n')
            out.flush()
    return 0


def run_coordinator(args: argparse.Namespace) -> int:
    root = Path(args.root).expanduser()
    files = tournament_files(root, args.dirs, args.limit, args.max_players)
    if not files:
        print(f'No .trf found under {root}', file=sys.stderr)
        return 1
    report = Path(args.report).expanduser()
    report.mkdir(parents=True, exist_ok=True)
    print(f'{len(files)} tournaments, {args.jobs} workers, report in {report}')
    if args.resume:
        kept = sum(
            len(already_checked(path)) for path in report.glob('findings-*.jsonl')
        )
        print(f'- resuming: {kept} already checked')
    print('Do not run the test suite until this finishes: it empties tests/tmp,')
    print('which is where these workers keep their data.')

    jobs = max(1, args.jobs)
    slices = [files[index::jobs] for index in range(jobs)]
    processes = []
    started = time.perf_counter()
    for index, chunk in enumerate(slices):
        if not chunk:
            continue
        slice_path = report / f'slice-{index}.txt'
        slice_path.write_text('\n'.join(str(p) for p in chunk))
        out_path = report / f'findings-{index}.jsonl'
        processes.append(
            subprocess.Popen(
                [
                    sys.executable,
                    __file__,
                    '--worker',
                    str(slice_path),
                    '--out',
                    str(out_path),
                    *(['--resume'] if args.resume else []),
                ],
                env=os.environ
                | {
                    'TEST_ENV': 'true',
                    # Each worker empties and owns its own data directory.
                    'PYTEST_XDIST_WORKER': f'corpus{index}',
                    'PYTHONPATH': 'src:.',
                },
            )
        )
    for process in processes:
        process.wait()
    elapsed = time.perf_counter() - started
    return summarise(report, len(files), elapsed)


def findings(report: Path) -> Iterator[dict]:
    for path in sorted(report.glob('findings-*.jsonl')):
        for line in path.read_text().splitlines():
            if line.strip():
                yield json.loads(line)


def summarise(report: Path, total: int, elapsed: float) -> int:
    verdicts: Counter[str] = Counter()
    errors: Counter[str] = Counter()
    differing: list[dict] = []
    checked = 0
    for finding in findings(report):
        checked += 1
        verdicts[finding['verdict']] += 1
        if finding['verdict'] == 'error':
            errors[finding['error'].split(':')[0]] += 1
        elif finding['verdict'] == 'differs':
            differing.append(finding)

    lines = [
        '',
        f'{checked}/{total} tournaments checked in {elapsed:.0f}s',
        f'  match            {verdicts["match"]}',
        f'  differs          {verdicts["differs"]}',
        '  file rejected by',
        f'    Gacrux too     {verdicts["file-rejected-by-gacrux"]}',
        f'  error            {verdicts["error"]}',
    ]
    for name, count in errors.most_common():
        lines.append(f'    {name}: {count}')
    if differing:
        lines.append('')
        lines.append('Differing tournaments (first 20):')
        for finding in differing[:20]:
            rounds = ', '.join(str(r) for r in finding['rounds'])
            lines.append(f'  {finding["file"]}  rounds {rounds}')
        copied = report / 'differing'
        copied.mkdir(exist_ok=True)
        for finding in differing:
            source = Path(finding['file'])
            (copied / f'{source.parent.name}-{source.name}').write_text(
                source.read_text(encoding='latin-1'), encoding='latin-1'
            )
        lines.append(f'  TRFs copied to {copied}')
    text = '\n'.join(lines)
    print(text)
    (report / 'summary.txt').write_text(text + '\n')
    return 1 if differing or verdicts['error'] else 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    parser.add_argument('root', nargs='?', help='corpus directory')
    parser.add_argument(
        '--dirs', help="glob over the corpus subdirectories, e.g. 't_n9*'"
    )
    parser.add_argument('--limit', type=int, help='at most N tournaments per directory')
    parser.add_argument(
        '--max-players',
        type=int,
        default=700,
        help='skip tournaments above this size (0 for no limit); the largest '
        'take minutes each',
    )
    parser.add_argument('--jobs', type=int, default=os.cpu_count() or 4)
    parser.add_argument('--report', default='gacrux-corpus', help='output directory')
    parser.add_argument(
        '--resume',
        action='store_true',
        help='keep the verdicts already in the report and check what is left',
    )
    parser.add_argument('--worker', help=argparse.SUPPRESS)
    parser.add_argument('--out', help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.worker:
        return run_worker(Path(args.worker), Path(args.out), args.resume)
    if not args.root:
        parser.error('the corpus directory is required')
    return run_coordinator(args)


if __name__ == '__main__':
    sys.exit(main())
