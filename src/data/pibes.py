from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import TYPE_CHECKING

from common.i18n import _
from utils.date_time import format_datetime
from utils.enum import Result

if TYPE_CHECKING:
    from data.board import Board
    from data.tournament import Tournament


class PibeType(StrEnum):
    """The events logged in the TRF, named as in their comments: the pairing
    integrity breaching events, and the changes to the tournament settings
    that the regulations fix before it starts."""

    MPA = 'MPA'
    IMPORT = 'Import'
    REGENERATION = 'Regeneration'
    CORRECTION = 'Correction'
    ADJOURNMENT = 'Adjournment'
    EXCHANGE = 'Exchange'
    CONFIGURATION = 'Configuration'
    ROUNDS = 'Rounds'
    TIE_BREAKS = 'Tie-breaks'

    @property
    def label(self) -> str:
        match self:
            case PibeType.MPA:
                return _('Manual pairing')
            case PibeType.IMPORT:
                return _('Import')
            case PibeType.REGENERATION:
                return _('Renumbering')
            case PibeType.CORRECTION:
                return _('Correction')
            case PibeType.ADJOURNMENT:
                return _('Adjourned game')
            case PibeType.EXCHANGE:
                return _('Pairing numbers exchanged')
            case PibeType.CONFIGURATION:
                return _('Configuration')
            case PibeType.ROUNDS:
                return _('Number of rounds')
            case PibeType.TIE_BREAKS:
                return _('Tie-breaks')


@dataclass(frozen=True)
class Pibe:
    type: PibeType
    round_: int
    description: str
    date: datetime | None = field(default=None, compare=False)
    members: dict[int, int] = field(default_factory=dict, compare=False)
    """The player (or team) each pairing number of the description stood
    for when the event was logged; empty for the current numbering."""

    def summary(self, tournament: 'Tournament', locale: str | None = None) -> str:
        return pibe_summary(self, tournament, locale)

    def trf_comment_for(self, tournament: 'Tournament') -> str:
        """The TRF comment, in the pairing numbers of today."""
        return (
            f'{self.type} @ Round {self.round_}: '
            f'{pibe_trf_description(self, tournament)}'
        )

    @property
    def date_str(self) -> str:
        return format_datetime(self.date) if self.date else ''

    @property
    def trf_comment(self) -> str:
        return f'{self.type} @ Round {self.round_}: {self.description}'


def fide_mode_exit_trf_comment(round_: int) -> str:
    return f'FIDE mode exited @ Round {round_}'


_BYE_LABELS: dict[Result, str] = {
    Result.PAIRING_ALLOCATED_BYE: 'PAB',
    Result.HALF_POINT_BYE: 'HPB',
    Result.FULL_POINT_BYE: 'FPB',
    Result.ZERO_POINT_BYE: 'ZPB',
}


def round_snapshot(tournament: 'Tournament', round_: int) -> dict[str, str]:
    """The pairings of *round_* by pairing number, each with its result:
    ``'6-17'`` → ``'1-0'`` for a game, ``'44=PAB'`` → ``''`` for a bye."""
    if tournament.is_team_tournament and tournament.pairing_system.paired_by_team:
        return _team_round_snapshot(tournament, round_)
    snapshot: dict[str, str] = {}
    for board in tournament.get_round_boards(round_):
        white = board.optional_white_tournament_player
        black = board.black_tournament_player
        if white is not None and black is None and board.result.is_bye:
            snapshot[_bye_token(white.pairing_number, board.result)] = ''
            continue
        white_number = white.pairing_number if white else 0
        black_number = black.pairing_number if black else 0
        snapshot[f'{white_number}-{black_number}'] = _board_result(board)
    for player in tournament.tournament_players_by_pairing_number.values():
        pairing = player.pairings_by_round.get(round_)
        if pairing is None or pairing.board is not None:
            continue
        if pairing.result in _BYE_LABELS:
            snapshot[_bye_token(player.pairing_number, pairing.result)] = ''
    return snapshot


def _board_result(board: 'Board') -> str:
    """The result of a game in TRF codes, white's then black's: ``'1-0'``,
    ``'=-='``, ``'+--'``, ``'*'`` while unplayed. TRF files are ASCII."""
    codes = [
        pairing.result.to_trf.strip() or '*'
        for pairing in (board.optional_white_pairing, board.optional_black_pairing)
        if pairing is not None
    ]
    return '*' if set(codes) <= {'*'} else '-'.join(codes)


def _bye_token(pairing_number: int | None, result: Result) -> str:
    return f'{pairing_number or 0}={_BYE_LABELS.get(result, result.to_trf)}'


def _team_round_snapshot(tournament: 'Tournament', round_: int) -> dict[str, str]:
    snapshot: dict[str, str] = {}
    for team_board in tournament.get_round_team_boards(round_):
        team_a_number = team_board.team_a.pairing_number or 0
        if (team_b := team_board.team_b) is None:
            snapshot[f'{team_a_number}={team_board.bye_type}'] = ''
            continue
        snapshot[f'{team_a_number}-{team_b.pairing_number or 0}'] = ' '.join(
            _board_result(board) for board in team_board.boards
        )
    return snapshot


def describe_round_changes(before: dict[str, str], after: dict[str, str]) -> str:
    """What changed between two snapshots of a round, in the notation of the
    TRF comments: ``'19-7 44=PAB => 19-44 7=PAB'`` for the pairings,
    ``'6-17: 1-0 => 0-1'`` for a result. Empty when nothing changed."""
    removed = [token for token in before if token not in after]
    added = [token for token in after if token not in before]
    parts: list[str] = []
    if removed or added:
        parts.append(f'{" ".join(removed)} => {" ".join(added)}'.strip())
    parts.extend(
        f'{token}: {before[token]} => {after[token]}'
        for token in before
        if token in after and before[token] != after[token]
    )
    return ', '.join(parts)


_READABLE_RESULTS = {
    '1': '1',
    '0': '0',
    '=': '½',
    '+': '1F',
    '-': '0F',
    'W': '1',
    'L': '0',
    'D': '½',
    'H': '½',
    'F': '1',
    'U': '1',
    'Z': '0',
    '*': '…',
}
_PAIR_LIST_LIMIT = 3


def pibe_summary(
    pibe: Pibe, tournament: 'Tournament', locale: str | None = None
) -> str:
    """*pibe* as a sentence an arbiter reads: names rather than pairing
    numbers, a count rather than a long list of pairings."""
    name = _member_namer(pibe, tournament)
    match pibe.type:
        case PibeType.ROUNDS:
            before, _arrow, after = pibe.description.partition(' => ')
            return _(
                'Number of rounds changed from {before} to {after}.', locale
            ).format(before=before, after=after)
        case PibeType.TIE_BREAKS:
            before, _arrow, after = pibe.description.partition(' => ')
            return _('Tie-breaks changed from {before} to {after}.', locale).format(
                before=_tie_break_list(before, tournament),
                after=_tie_break_list(after, tournament),
            )
        case PibeType.REGENERATION:
            before, _arrow, _after = pibe.description.partition(' => ')
            count = len(before.split())
            return _(
                'The pairing numbers of {count} players were changed, after an '
                'update to the players.',
                locale,
            ).format(count=count)
        case PibeType.CORRECTION:
            return ' '.join(
                _correction_summary(part, name, locale)
                for part in pibe.description.split(', ')
            )
        case PibeType.MPA | PibeType.IMPORT | PibeType.CONFIGURATION:
            engine, _arrow, actual = pibe.description.partition(' => ')
            intro = {
                PibeType.MPA: _(
                    'Pairings edited by hand and validated although they differ '
                    'from those of the pairing engine',
                    locale,
                ),
                PibeType.IMPORT: _(
                    'Imported pairings that differ from those of the pairing engine',
                    locale,
                ),
                PibeType.CONFIGURATION: _(
                    'After the change to the number of rounds, pairings that differ '
                    'from those of the pairing engine',
                    locale,
                ),
            }[pibe.type]
            return _('{what}: {pairings}', locale).format(
                what=intro, pairings=_pairs_summary(engine, actual, name, locale)
            )
    return pibe.description


def pibe_trf_description(pibe: Pibe, tournament: 'Tournament') -> str:
    """The description of *pibe* in the pairing numbers of today: the
    players keep their place in it however the numbering has moved since."""

    def current_number(number: str) -> str:
        member_id = pibe.members.get(int(number))
        if member_id is None:
            return number
        current = _member_pairing_number(tournament, member_id)
        return str(current) if current is not None else number

    return rewrite_member_numbers(pibe.type, pibe.description, current_number)


def rewrite_member_numbers(
    type_: PibeType, description: str, rewrite: Callable[[str], str]
) -> str:
    """*description* with each pairing number of a player (or team) passed
    through *rewrite*; results and counts are left as they are."""

    def number(value: str) -> str:
        return rewrite(value) if value.isdigit() and value != '0' else value

    def token(value: str) -> str:
        if '=' in value:
            first, _equals, bye = value.partition('=')
            return f'{number(first)}={bye}'
        first, dash, second = value.partition('-')
        return f'{number(first)}-{number(second)}' if dash else number(value)

    def tokens(side: str) -> str:
        return ' '.join(token(value) for value in side.split())

    def sides(part: str) -> str:
        return ' => '.join(tokens(side) for side in part.split(' => '))

    match type_:
        case PibeType.REGENERATION:
            return ' => '.join(
                ' '.join(number(value) for value in side.split())
                for side in description.split(' => ')
            )
        case PibeType.CORRECTION:
            parts: list[str] = []
            for part in description.split(', '):
                pair, colon, results = part.partition(': ')
                parts.append(f'{token(pair)}: {results}' if colon else sides(part))
            return ', '.join(parts)
        case PibeType.MPA | PibeType.IMPORT | PibeType.CONFIGURATION:
            return sides(description)
    return description


def _member_pairing_number(tournament: 'Tournament', member_id: int) -> int | None:
    if tournament.is_team_tournament and tournament.pairing_system.paired_by_team:
        team = tournament.event.teams_by_id.get(member_id)
        return team.pairing_number if team is not None else None
    player = tournament.tournament_players_by_id.get(member_id)
    return player.pairing_number if player is not None else None


def _member_namer(pibe: Pibe, tournament: 'Tournament') -> Callable[[str], str]:
    """Who a pairing number of *pibe* stood for when it was logged, by name."""
    team_paired = (
        tournament.is_team_tournament and tournament.pairing_system.paired_by_team
    )

    def name(number: str) -> str:
        if not number.isdigit():
            return number
        member_id = pibe.members.get(int(number))
        if team_paired:
            team = (
                tournament.event.teams_by_id.get(member_id)
                if member_id is not None
                else tournament.teams_by_pairing_number.get(int(number))
            )
            return team.name if team is not None else f'#{number}'
        player = (
            tournament.tournament_players_by_id.get(member_id)
            if member_id is not None
            else tournament.tournament_players_by_pairing_number.get(int(number))
        )
        return player.full_name if player is not None else f'#{number}'

    return name


def _tie_break_list(acronyms: str, tournament: 'Tournament') -> str:
    """Tie-breaks listed by their TRF acronyms, by name where known."""
    from data.tie_breaks import TieBreakManager

    name_by_acronym = {
        tie_break.trf_acronym: tie_break.name
        for tie_break in TieBreakManager(tournament.event).objects()
    }
    return ', '.join(
        name_by_acronym.get(acronym, acronym.removeprefix('OTHER_'))
        for acronym in acronyms.split()
    )


def _correction_summary(
    part: str, name: Callable[[str], str], locale: str | None
) -> str:
    pairs, colon, results = part.partition(': ')
    if colon and '=>' in results and '=>' not in pairs:
        before, _arrow, after = results.partition(' => ')
        return _('Result of {pair} changed from {before} to {after}.', locale).format(
            pair=_pair_name(pairs, name),
            before=_readable_result(before),
            after=_readable_result(after),
        )
    engine, _arrow, actual = part.partition(' => ')
    return _('{what}: {pairings}', locale).format(
        what=_('Pairings of the round changed', locale),
        pairings=_pairs_summary(engine, actual, name, locale),
    )


def _pairs_summary(
    before: str, after: str, name: Callable[[str], str], locale: str | None
) -> str:
    before_pairs, after_pairs = before.split(), after.split()
    if max(len(before_pairs), len(after_pairs)) > _PAIR_LIST_LIMIT:
        return _('{count} boards differ.', locale).format(
            count=max(len(before_pairs), len(after_pairs))
        )
    return _('{after} instead of {before}.', locale).format(
        after=', '.join(_pair_name(pair, name) for pair in after_pairs) or '-',
        before=', '.join(_pair_name(pair, name) for pair in before_pairs) or '-',
    )


def _readable_result(result: str) -> str:
    if result == '*':
        return '…'
    return '-'.join(_READABLE_RESULTS.get(code, code) for code in result.split('-', 1))


def _pair_name(token: str, name: Callable[[str], str]) -> str:
    """A pair in pairing numbers, ``'6-17'`` or ``'44=PAB'``, by name."""
    if '=' in token:
        number, _equals, bye = token.partition('=')
        return f'{name(number)} ({bye})'
    white, _dash, black = token.partition('-')
    return f'{name(white)} – {name(black)}'
