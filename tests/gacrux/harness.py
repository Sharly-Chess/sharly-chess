"""Gacrux, an independent pairing and tie-break checker, run as an oracle
over the TRF26 export of a tournament.

Gacrux is fetched at a pinned commit into ``tools/gacrux/<commit>`` and
run as a subprocess (``python -m gacrux.pairingchecker`` and
``python -m gacrux.tiebreakchecker``) on the interpreter running the
tests; nothing of it is imported, so a change to its data model only
shows up here as a parsing failure, never as an import error.

Each checker writes a JSON document on stdout whose ``status.code`` is 0
when the file agrees with what Gacrux computes, 1 on a mismatch and 4xx
or 5xx on an error. That code, not the process exit status, is what a
run reports: the exit status is the file-reading status and is 0 even
on a mismatch.
"""

import io
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
from collections.abc import Callable
from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path
from typing import Any, SupportsFloat

import requests

from common import BASE_DIR, REQUEST_TIMEOUT
from common.i18n.utils import unicode_normalize
from data.board import Board
from data.input_output.tournament_exporters import Trf26TournamentExporter
from data.input_output.trf.trf_export import TrfExport
from data.input_output.trf.trf_serializer import TrfSerializer
from data.tie_breaks.options import LegacyMarch2026TieBreakOption
from data.tie_breaks.tie_breaks import TieBreak
from data.tournament import Tournament

GACRUX_REPOSITORY = 'https://github.com/OttoMilvang/TieBreakServer'
GACRUX_COMMIT = '6419149ede24fa76639a956b1a52ccac0ded730d'
GACRUX_DIR = BASE_DIR / 'tools' / 'gacrux'

# The tie-break names Gacrux's ``tiebreak.tiebreaklist`` computes at the
# pinned commit. A tie-break whose TRF acronym is not built on one of these
# is left out of the comparison rather than sent, since an unknown name
# crashes the checker.
GACRUX_TIE_BREAKS = frozenset(
    {
        'PTS',
        'MPTS',
        'GPTS',
        'SNO',
        'TPN',
        'RANK',
        'WIN',
        'WON',
        'BPG',
        'BWG',
        'GE',
        'REP',
        'RIP',
        'VUR',
        'NUM',
        'RTG',
        'MPVGP',
        'DE',
        'EDE',
        'EDEC',
        'EDET',
        'EDEB',
        'EDEBT',
        'EDEBB',
        'PS',
        'KS',
        'BH',
        'FB',
        'SB',
        'ABH',
        'AFB',
        'AOB',
        'RTNG',
        'ARO',
        'TPR',
        'PTP',
        'RSES',
        'APRO',
        'APPO',
        'ESB',
        'EMMSB',
        'EMGSB',
        'EGMSB',
        'EGGSB',
        'BC',
        'TBR',
        'BBE',
        'SSSC',
        'STD',
        'ACC',
        'FLT',
        'RFP',
        'TOP',
        'RND',
    }
)

# Tie-breaks computed from the ratings.
RATING_TIE_BREAKS = frozenset({'RTNG', 'ARO', 'TPR', 'PTP', 'RSES', 'APRO', 'APPO'})

# Tie-breaks whose value only encodes a rank change among tied
# competitors (Gacrux reports a placeholder for them): compared on the
# order they produce, never on the value.
ORDER_ONLY_TIE_BREAKS = frozenset(
    {'DE', 'EDE', 'EDEC', 'EDET', 'EDEB', 'EDEBT', 'EDEBB', 'TBR', 'BBE'}
)


# ---------------------------------------------------------------------------
# Installation
# ---------------------------------------------------------------------------


def gacrux_source_dir() -> Path:
    """The directory holding the ``gacrux`` package at the pinned commit,
    fetched from GitHub on first use."""
    source_dir = GACRUX_DIR / GACRUX_COMMIT
    if (source_dir / 'gacrux' / '__init__.py').exists():
        return source_dir
    archive_url = f'{GACRUX_REPOSITORY}/archive/{GACRUX_COMMIT}.tar.gz'
    response = requests.get(archive_url, timeout=REQUEST_TIMEOUT)
    response.raise_for_status()
    staging = GACRUX_DIR / f'{GACRUX_COMMIT}.{os.getpid()}.tmp'
    shutil.rmtree(staging, ignore_errors=True)
    staging.mkdir(parents=True)
    with tarfile.open(fileobj=io.BytesIO(response.content), mode='r:gz') as archive:
        prefix = f'TieBreakServer-{GACRUX_COMMIT}/gacrux/'
        members = [
            member
            for member in archive.getmembers()
            if member.name.startswith(prefix) and member.isfile()
        ]
        for member in members:
            member.name = member.name.removeprefix(f'TieBreakServer-{GACRUX_COMMIT}/')
        archive.extractall(staging, members=members, filter='data')
    # Several workers may fetch at once: the first rename wins, the others
    # find the package in place and drop their copy.
    try:
        staging.rename(source_dir)
    except OSError:
        shutil.rmtree(staging, ignore_errors=True)
    return source_dir


def gacrux_version() -> str:
    """The version string Gacrux declares at the pinned commit."""
    version_file = gacrux_source_dir() / 'gacrux' / 'version.py'
    match = re.search(r'__version__\s*=\s*"([^"]+)"', version_file.read_text())
    return match.group(1) if match else 'unknown'


def gacrux_report_header() -> str:
    return (
        f'Gacrux {gacrux_version()} at {GACRUX_REPOSITORY}/commit/{GACRUX_COMMIT[:12]}'
    )


# ---------------------------------------------------------------------------
# Known Gacrux issues
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class KnownIssue:
    """A defect of the pinned Gacrux, recognised from its traceback, with
    the reconciliation entry that documents it and, when there is one, a
    way to edit the TRF around it so the rest of the check still runs."""

    id: str
    summary: str
    signature: str
    #: An edit of the TRF text that sidesteps the issue.
    workaround: Callable[[str], str] | None = None
    #: Or an export stopped at the last finished round.
    finished_rounds_only: bool = False

    def applies_to(self, run: 'CheckerRun') -> bool:
        return run.failed and re.search(self.signature, run.traceback) is not None

    def work_around(
        self, trf_path: Path, tournament: Tournament
    ) -> tuple[Path, int] | None:
        """The TRF made around the issue and the round it stops at, or
        None when there is no way around it here."""
        patched = trf_path.with_name(f'{trf_path.stem}.{self.id}{trf_path.suffix}')
        if self.finished_rounds_only:
            finished = last_finished_round(tournament)
            if finished == tournament.rounds:
                return None
            return export_trf(
                tournament, patched.parent, patched.stem, finished
            ), finished
        if self.workaround is None:
            return None
        text = trf_path.read_text(encoding='latin-1')
        edited = self.workaround(text)
        if edited == text:
            return None
        patched.write_text(edited, encoding='latin-1')
        return patched, tournament.rounds


def _read_other_as_fidon(text: str) -> str:
    return re.sub(r'^(172 \w{3} )OTHER', r'\1FIDON', text, flags=re.MULTILINE)


KNOWN_ISSUES = (
    KnownIssue(
        id='G3',
        summary='crashes on a 172 record whose method is OTHER',
        signature=r"in prepare_competitors[\s\S]*'int' object is not subscriptable",
        workaround=_read_other_as_fidon,
    ),
    KnownIssue(
        id='G4',
        summary='crashes on a team file whose next round is paired but unplayed',
        signature=r'in post_parse_line[\s\S]*IndexError: list index out of range',
        finished_rounds_only=True,
    ),
)


def known_issue(run: 'CheckerRun') -> KnownIssue | None:
    return next((issue for issue in KNOWN_ISSUES if issue.applies_to(run)), None)


@dataclass(frozen=True)
class ReadableTrf:
    """The TRF to hand the checkers: the export itself, or one made around
    the known issue that stops Gacrux reading it, and the round it stops
    at."""

    path: Path
    after_round: int
    issue: KnownIssue | None = None


def readable_trf(trf_path: Path, tournament: Tournament) -> ReadableTrf:
    probe = run_checker('tiebreakchecker', trf_path, '-t', 'PTS')
    issue = known_issue(probe)
    if issue is None:
        return ReadableTrf(trf_path, tournament.rounds)
    patched = issue.work_around(trf_path, tournament)
    if patched is None:
        return ReadableTrf(trf_path, tournament.rounds, issue)
    return ReadableTrf(patched[0], patched[1], issue)


# ---------------------------------------------------------------------------
# Running a checker
# ---------------------------------------------------------------------------


@dataclass
class CheckerRun:
    """One invocation of a Gacrux checker on a TRF file."""

    checker: str
    command: list[str]
    exit_code: int
    stdout: str
    stderr: str
    status_code: int
    errors: list[str]
    result: dict[str, Any] | None
    #: The traceback of a program error, from a second, verbose run.
    traceback: str = ''

    @property
    def ok(self) -> bool:
        return self.status_code == 0

    @property
    def failed(self) -> bool:
        """An error, as opposed to a mismatch: Gacrux could not check."""
        return self.status_code >= 400

    def describe(self) -> str:
        lines = [
            f'$ {" ".join(self.command)}',
            f'exit {self.exit_code}, status {self.status_code}',
        ]
        lines.extend(self.errors)
        if self.traceback:
            lines.append(self.traceback)
        elif self.result is None:
            lines.append(self.stdout.strip())
        if self.stderr.strip():
            lines.append(self.stderr.strip())
        return '\n'.join(lines)


def run_checker(checker: str, trf_path: Path, *args: str) -> CheckerRun:
    """Run ``python -m gacrux.<checker> -i <trf> -c <args>`` and parse
    its JSON output."""
    command = [
        sys.executable,
        '-m',
        f'gacrux.{checker}',
        '-i',
        str(trf_path),
        '-c',
        *args,
    ]
    env = os.environ | {'PYTHONPATH': str(gacrux_source_dir())}
    completed = subprocess.run(
        command,
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )
    result: dict[str, Any] | None = None
    status_code = 500
    errors: list[str] = []
    traceback = ''
    try:
        document = json.loads(completed.stdout)
    except json.JSONDecodeError:
        # A crash on the way to the JSON output leaves a text error report
        # (``### Error <code>`` and one line per message) or a traceback.
        match = re.search(r'### Error (\d+)', completed.stdout)
        if match:
            status_code = int(match.group(1))
        errors = [
            line.strip() for line in completed.stdout.splitlines()[1:] if line.strip()
        ]
    else:
        status = document.get('status', {})
        status_code = int(status.get('code', 500))
        errors = [str(error) for error in status.get('error', [])]
        for key, value in document.items():
            if key.endswith('Result') and isinstance(value, dict):
                result = value
    if status_code >= 500:
        # A program error hides its traceback unless the checker runs
        # verbose, in which case it re-raises instead of reporting.
        verbose = subprocess.run(
            [*command, '-v'], capture_output=True, text=True, env=env, check=False
        )
        traceback = verbose.stderr.strip()
    return CheckerRun(
        checker=checker,
        command=command,
        exit_code=completed.returncode,
        stdout=completed.stdout,
        stderr=completed.stderr,
        status_code=status_code,
        errors=errors,
        result=result,
        traceback=traceback,
    )


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------


def export_trf(
    tournament: Tournament,
    directory: Path,
    stem: str,
    after_round: int | None = None,
) -> Path:
    """Export ``tournament`` as TRF26 into ``directory`` and return the
    file, the same way the application's export does — every round, or
    those up to ``after_round``."""
    directory.mkdir(parents=True, exist_ok=True)
    exporter = Trf26TournamentExporter()
    trf_path = directory / f'{stem}.{exporter.file_extension}'
    with open(trf_path, 'w', encoding=exporter.file_encoding) as file:
        if after_round is None:
            exporter.dump_to_file(file, tournament)
        else:
            trf_tournament = tournament.to_trf(after_round=after_round)
            file.write(unicode_normalize(TrfSerializer.dumps(trf_tournament)))
    return trf_path


def last_finished_round(tournament: Tournament) -> int:
    """The last round every result of which is in."""
    finished = 0
    for round_ in range(1, tournament.rounds + 1):
        if not tournament.round_has_pairings(round_) or not (
            tournament.is_round_finished(round_)
        ):
            break
        finished = round_
    return finished


def trf_export_unavailable(tournament: Tournament) -> str | None:
    return Trf26TournamentExporter().is_unavailable_message(tournament)


# ---------------------------------------------------------------------------
# Pairings
# ---------------------------------------------------------------------------


@dataclass
class RoundDiff:
    round_: int
    ours: list[tuple[int, int]]
    gacrux: list[tuple[int, int]]

    def describe(self) -> str:
        lines = [f'Round {self.round_}: ours vs Gacrux (white-black by TRF number)']
        width = max(len(self.ours), len(self.gacrux))
        for index in range(width):
            ours = self.ours[index] if index < len(self.ours) else None
            theirs = self.gacrux[index] if index < len(self.gacrux) else None
            marker = ' ' if ours == theirs else '*'
            lines.append(f'  {marker} {_pair(ours):>12}    {_pair(theirs):>12}')
        return '\n'.join(lines)


def _pair(pair: tuple[int, int] | None) -> str:
    return '-' if pair is None else f'{pair[0]} - {pair[1]}'


@dataclass
class PairingCheck:
    run: CheckerRun
    rounds: list[RoundDiff] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.run.ok

    def describe(self) -> str:
        parts = [self.run.describe()]
        parts.extend(diff.describe() for diff in self.rounds)
        return '\n'.join(parts)


def check_pairings(trf_path: Path, *args: str) -> PairingCheck:
    """Have Gacrux re-pair every round of the TRF and compare with the
    pairings it records."""
    run = run_checker('pairingchecker', trf_path, *args)
    check = PairingCheck(run)
    if run.result is None:
        return check
    for round_pairing in run.result.get('roundpairing', []):
        if round_pairing.get('check', True):
            continue
        check.rounds.append(
            RoundDiff(
                round_=int(round_pairing['round']),
                ours=[tuple(pair) for pair in round_pairing.get('current', [])],
                gacrux=[tuple(pair) for pair in round_pairing.get('pairs', [])],
            )
        )
    return check


def _board_pair(board: 'Board | None') -> str:
    if board is None:
        return '-'
    white = board.white_tournament_player.pairing_number
    black = getattr(board.black_tournament_player, 'pairing_number', 0)
    return f'{white} - {black}'


def engine_departures(tournament: Tournament, round_: int) -> list[str]:
    """The boards on which our own engine, re-pairing ``round_`` from the
    same position, departs from the pairings stored for it. Empty when it
    reproduces them: a stored pairing it does not reproduce was made by
    something else (an import, a hand) and says nothing about it."""
    engine = tournament.pairing_variation.engine
    return [
        f'{_board_pair(stored)} stored, {_board_pair(expected)} re-paired'
        for stored, expected in engine.pairings_diff(
            tournament, round_, ignore_order=True
        )
    ]


# ---------------------------------------------------------------------------
# Tie-breaks
# ---------------------------------------------------------------------------


def gacrux_spec(tie_break: TieBreak) -> str | None:
    """The rank-order specifier Gacrux computes ``tie_break`` under, or
    None when Gacrux has no equivalent."""
    if not tie_break.is_fide:
        return None
    acronym = tie_break.trf_acronym.upper()
    name = re.split(r'[/:]', acronym, maxsplit=1)[0]
    if name not in GACRUX_TIE_BREAKS:
        return None
    try:
        legacy = bool(tie_break._get_option(LegacyMarch2026TieBreakOption).value)
    except KeyError:
        legacy = False
    if legacy:
        acronym += '/V1'
    return acronym


def _decimal(value: SupportsFloat | str | None) -> Decimal | None:
    if value is None:
        return None
    if isinstance(value, Decimal):
        return value
    if isinstance(value, int | str):
        return Decimal(value)
    return Decimal(repr(float(value)))


@dataclass
class ValueDiff:
    spec: str
    competitor: int
    name: str
    ours: Decimal | None
    gacrux: Decimal | None


@dataclass
class TieBreakCheck:
    """Our values and standings against Gacrux's, tie-break by tie-break."""

    run: CheckerRun
    #: The specifiers sent, in order, and the tie-break each stands for.
    specs: list[tuple[str, TieBreak]]
    #: Tie-breaks left out of the comparison, each with the reason.
    left_out: list[tuple[TieBreak, str]]
    value_diffs: list[ValueDiff] = field(default_factory=list)
    #: Competitors (TRF number, name) whose order in our standings
    #: contradicts Gacrux's rank, as consecutive pairs.
    order_diffs: list[tuple[tuple[int, str, int], tuple[int, str, int]]] = field(
        default_factory=list
    )

    @property
    def ok(self) -> bool:
        return (
            not self.run.failed
            and not self.value_diffs
            and not self.order_diffs
            and self.ranks_agree
        )

    @property
    def ranks_agree(self) -> bool:
        """Gacrux's own verdict — the rank field of the file against the
        ranks it computes — where it applies: when every criterion the
        file ranks on was sent."""
        return bool(self.left_out) or self.run.ok

    def describe(self) -> str:
        lines = [self.run.describe()]
        lines.extend(
            f'Not compared: {tie_break.trf_acronym} ({reason})'
            for tie_break, reason in self.left_out
        )
        by_spec: dict[str, list[ValueDiff]] = {}
        for diff in self.value_diffs:
            by_spec.setdefault(diff.spec, []).append(diff)
        for spec, diffs in by_spec.items():
            lines.append(f'{spec}: {len(diffs)} value(s) differ (ours / Gacrux)')
            lines.extend(
                f'  #{diff.competitor} {diff.name}: {diff.ours} / {diff.gacrux}'
                for diff in diffs
            )
        for (number, name, rank), (
            next_number,
            next_name,
            next_rank,
        ) in self.order_diffs:
            lines.append(
                f'Order: we place #{number} {name} (Gacrux rank {rank}) '
                f'above #{next_number} {next_name} (Gacrux rank {next_rank})'
            )
        return '\n'.join(lines)


def _split_specs(
    tie_breaks: list[TieBreak],
) -> tuple[list[tuple[str, TieBreak]], list[TieBreak]]:
    specs: list[tuple[str, TieBreak]] = []
    unsupported: list[TieBreak] = []
    for tie_break in tie_breaks:
        spec = gacrux_spec(tie_break)
        if spec is None:
            unsupported.append(tie_break)
        else:
            specs.append((spec, tie_break))
    return specs, unsupported


def _gacrux_scores(run: CheckerRun) -> dict[int, tuple[int, list[Decimal | None]]]:
    """TRF number → (Gacrux rank, its tie-break values in spec order)."""
    scores: dict[int, tuple[int, list[Decimal | None]]] = {}
    if run.result is None:
        return scores
    for competitor in run.result.get('competitors', []):
        scores[int(competitor['cid'])] = (
            int(competitor['rank']),
            [_decimal(value) for value in competitor.get('tiebreakScore', [])],
        )
    return scores


def _gacrux_precisions(run: CheckerRun) -> list[int]:
    """The number of decimals Gacrux reports each tie-break with."""
    if run.result is None:
        return []
    return [int(tb.get('precision', 0)) for tb in run.result.get('tiebreaks', [])]


def _same_value(ours: Decimal | None, theirs: Decimal | None, precision: int) -> bool:
    """Whether a value of ours is the one Gacrux reports.

    Gacrux reports an average (AOB, say) to the decimals it needs, ours
    is exact: ours is compared once rounded to as many, half up. A
    tie-break Gacrux leaves undefined (an ARO with nothing left after
    the cut) is None where ours is 0: both rank the participant last.
    """
    if theirs is None:
        return ours is None or ours == 0
    if ours is None:
        return False
    quantum = Decimal(1).scaleb(-precision)
    return ours.quantize(quantum, rounding=ROUND_HALF_UP) == theirs


def _compare(
    check: TieBreakCheck,
    ours: list[tuple[int, str, list[Decimal | None]]],
) -> None:
    """Fill ``check`` from our competitors, given in our standings order as
    (TRF number, name, values in spec order)."""
    theirs = _gacrux_scores(check.run)
    if not theirs:
        return
    precisions = _gacrux_precisions(check.run)
    previous: tuple[int, str, int] | None = None
    for number, name, values in ours:
        rank, gacrux_values = theirs[number]
        for index, (spec, _tie_break) in enumerate(check.specs):
            base = spec.split('/')[0].split(':')[0]
            if base in ORDER_ONLY_TIE_BREAKS:
                continue
            our_value = values[index] if index < len(values) else None
            their_value = gacrux_values[index] if index < len(gacrux_values) else None
            precision = precisions[index] if index < len(precisions) else 0
            if not _same_value(our_value, their_value, precision):
                check.value_diffs.append(
                    ValueDiff(spec, number, name, our_value, their_value)
                )
        current = (number, name, rank)
        if previous is not None and previous[2] > rank:
            check.order_diffs.append((previous, current))
        previous = current


def _prepare(
    tournament: Tournament, tie_breaks: list[TieBreak]
) -> tuple[list[tuple[str, TieBreak]], list[tuple[TieBreak, str]]]:
    """Set ``tie_breaks`` on the tournament and return the specifiers to
    send Gacrux, with the tie-breaks left out and why: no Gacrux
    equivalent, or invalid on this tournament (a rating tie-break with
    unrated players, say), which the ranking drops on its own."""
    specs, unsupported = _split_specs(tie_breaks)
    left_out = [(tie_break, 'no Gacrux equivalent') for tie_break in unsupported]
    if TrfExport(tournament)._starting_rank_method() == 'OTHER':
        # The ratings the tournament ranked on (estimates among them) are
        # not in the file, so nothing computed from ratings can be.
        rating_based = [
            (spec, tie_break)
            for spec, tie_break in specs
            if spec.split('/')[0] in RATING_TIE_BREAKS
        ]
        left_out.extend(
            (tie_break, 'ranked by ratings the TRF cannot carry (172 OTHER)')
            for _, tie_break in rating_based
        )
        specs = [pair for pair in specs if pair not in rating_based]
    rank_on(tournament, [tie_break for _, tie_break in specs])
    configuration = tournament.tie_break_configuration
    invalid = configuration.invalid_messages
    retained: list[tuple[str, TieBreak]] = []
    for stored_id, (spec, tie_break) in enumerate(specs, start=1):
        if stored_id in invalid:
            left_out.append((tie_break, invalid[stored_id]))
        else:
            retained.append((spec, tie_break))
    rank_on(tournament, [tie_break for _, tie_break in retained])
    return retained, left_out


def check_individual_tie_breaks(
    tournament: Tournament,
    trf_path: Path,
    tie_breaks: list[TieBreak],
    *args: str,
    after_round: int | None = None,
) -> TieBreakCheck:
    """Compare our values for ``tie_breaks`` on every player with
    Gacrux's, computed from the TRF, and our standings order with
    Gacrux's ranks.

    ``tie_breaks`` are set on the tournament in memory for the
    computation, so the standings compared are those they define.
    """
    if after_round is None:
        after_round = tournament.rounds
    specs, left_out = _prepare(tournament, tie_breaks)
    run = run_checker(
        'tiebreakchecker',
        trf_path,
        '-t',
        *[spec for spec, _ in specs],
        *_round_args(tournament, after_round),
        *args,
    )
    check = TieBreakCheck(run, specs, left_out)
    if run.result is None:
        return check
    tournament.compute_tournament_player_ranks(after_round=after_round)
    ours = [
        (
            player.pairing_number or 0,
            player.last_name,
            [_decimal(value.value) for value in player.tie_break_values],
        )
        for player in tournament.tournament_players_by_rank.values()
    ]
    _compare(check, ours)
    return check


def check_team_tie_breaks(
    tournament: Tournament,
    trf_path: Path,
    tie_breaks: list[TieBreak],
    *args: str,
    after_round: int | None = None,
) -> TieBreakCheck:
    """The team counterpart of :func:`check_individual_tie_breaks`: our
    team standings against Gacrux's, team by team."""
    if after_round is None:
        after_round = tournament.rounds
    specs, left_out = _prepare(tournament, tie_breaks)
    run = run_checker(
        'tiebreakchecker',
        trf_path,
        '-t',
        *[spec for spec, _ in specs],
        *_round_args(tournament, after_round),
        *args,
    )
    check = TieBreakCheck(run, specs, left_out)
    if run.result is None:
        return check
    tpn_by_team_id = TrfExport(tournament)._team_tpn_map()
    ours = [
        (
            tpn_by_team_id[row.team.id],
            row.team.name,
            [_decimal(value.value) for value in row.tie_break_values],
        )
        for row in tournament.team_standings(after_round=after_round)
    ]
    _compare(check, ours)
    return check


def _round_args(tournament: Tournament, after_round: int) -> list[str]:
    """The checker's current-round option, when the standings compared
    stop short of the tournament's last round, and the kind of pairing
    the unplayed rounds are evaluated under: said outright, since Gacrux
    guesses a round robin from the field and round counts of a file
    whose 192 code it does not know (FIDE_DUTCH_2026 among them)."""
    args = ['-p' if tournament.pairing_system.predetermined_pairings else '-s']
    if after_round < tournament.rounds:
        args += ['-n', str(after_round)]
    return args


def rank_on(tournament: Tournament, tie_breaks: list[TieBreak]) -> None:
    """Rank ``tournament`` on ``tie_breaks`` for the rest of its life in
    memory, whatever it stores: its exports and standings follow."""
    tournament.tie_break_configuration.__dict__['by_id'] = dict(
        enumerate(tie_breaks, start=1)
    )
