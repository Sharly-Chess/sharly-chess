"""The journal of an event: what was done to it, when and by whom.

An entry is written by the code doing the action, with everything its
sentence needs copied into it: the players, teams and tournaments it names
may be renamed or deleted afterwards, and the entry still reads the way it
did. The sentence itself is put together when it is shown, in the language
of the reader.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
import json
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import TYPE_CHECKING, Any

from common import DEVEL_ENV, TEST_ENV
from common.exception import SharlyChessException
from common.i18n import _
from common.logger import get_logger
from database.sqlite.event.event_store import StoredJournalEntry
from utils.date_time import format_datetime
from utils.enum import Result

if TYPE_CHECKING:
    from data.tournament import Tournament

logger = get_logger()


class AuthorKind(StrEnum):
    """Who acted: a person, known through the account they act from."""

    ADMINISTRATOR = 'administrator'
    ACCOUNT = 'account'


class SourceKind(StrEnum):
    """Where an action came from."""

    COMPUTER = 'computer'
    NETWORK = 'network'
    SCREEN = 'screen'
    PLUGIN = 'plugin'
    APPLICATION = 'application'


@dataclass(frozen=True)
class Author:
    """A person, by the account they act from: its name is looked up when the
    journal is shown, so that a renamed account reads as it is called now."""

    kind: AuthorKind
    account_id: int | None = None


@dataclass(frozen=True)
class Source:
    kind: SourceKind
    name: str | None = None
    host: str | None = None

    @classmethod
    def plugin(cls, name: str) -> Source:
        """A plugin bringing in what was done on another application."""
        return cls(SourceKind.PLUGIN, name)


@dataclass(frozen=True)
class Actor:
    """Who did what an entry records, if anybody, and where it came from."""

    author: Author | None
    source: Source

    @classmethod
    def application(cls) -> Actor:
        return cls(None, Source(SourceKind.APPLICATION))


_actor_provider: ContextVar[Callable[[], Actor] | None] = ContextVar(
    'sharly_chess_journal_actor', default=None
)
_not_journaled_reason: ContextVar[str | None] = ContextVar(
    'sharly_chess_not_journaled_reason', default=None
)


def current_actor() -> Actor:
    provider = _actor_provider.get()
    if provider is None:
        return Actor.application()
    try:
        return provider()
    except Exception:
        logger.exception('The author of a journal entry could not be found')
        return Actor.application()


def set_actor_provider(provider: Callable[[], Actor]) -> None:
    """Names who acts for the rest of the current context: the request being
    answered, typically. The provider is called when an entry is written, so
    that nothing is looked up for a request that writes nothing."""
    _actor_provider.set(provider)


@contextmanager
def acting_as(actor: Actor) -> Iterator[None]:
    token = _actor_provider.set(lambda: actor)
    try:
        yield
    finally:
        _actor_provider.reset(token)


@contextmanager
def coming_from(source: Source) -> Iterator[None]:
    """What is done within comes from *source*, on behalf of whoever started
    it, if anybody: a synchronisation started by an arbiter, or run in the
    background."""
    provider = _actor_provider.get()

    def actor() -> Actor:
        author = provider().author if provider is not None else None
        return Actor(author, source)

    token = _actor_provider.set(actor)
    try:
        yield
    finally:
        _actor_provider.reset(token)


@contextmanager
def not_journaled(reason: str) -> Iterator[None]:
    """Leaves out of the journal what is written within, for *reason*: what
    is written follows from an action journaled on its own (the steps of an
    import, journaled as one), or is no decision of anyone (a setting
    defaulted on the way, a draft, data made up for testing). Nothing is
    journaled within, and what is written is not held against the
    operation."""
    token = _not_journaled_reason.set(reason)
    try:
        yield
    finally:
        _not_journaled_reason.reset(token)


#: The tables written for what is not the arbitration of the event, and why:
#: a write anywhere else is journaled, or said not to be (:func:`not_journaled`).
#: A new table is journaled until it is listed here.
UNJOURNALED_TABLES: dict[str, str] = {
    'journal': 'the journal itself',
    'metadata': 'the version of the file',
    'plugin_metadata': 'the versions of the plugins in the file',
    'sqlite_sequence': 'the counters of SQLite',
    'screen': 'the screens show the event, they are not part of it',
    'screen_set': 'the screens show the event, they are not part of it',
    'family': 'the screens show the event, they are not part of it',
    'rotator': 'the screens show the event, they are not part of it',
    'rotating_screen': 'the screens show the event, they are not part of it',
    'menu': 'the screens show the event, they are not part of it',
    'menu_item': 'the screens show the event, they are not part of it',
    'display_controller': 'the screens show the event, they are not part of it',
    'display_controller_item': 'the screens show the event, they are not part of it',
    'display_controller_rotator': 'the screens show the event, they are not part of it',
    'display_controller_screen': 'the screens show the event, they are not part of it',
    'display_controller_family': 'the screens show the event, they are not part of it',
    'display_controller_menu': 'the screens show the event, they are not part of it',
    'timer': 'the timers are shown on the screens',
    'timer_hour': 'the timers are shown on the screens',
    'prize': 'the prizes are handed out after the arbitration',
    'prize_group': 'the prizes are handed out after the arbitration',
    'prize_category': 'the prizes are handed out after the arbitration',
    'prize_criterion': 'the prizes are handed out after the arbitration',
}

#: The columns written along with the data, or for bookkeeping, and why.
UNJOURNALED_COLUMNS: dict[tuple[str, str], str] = {
    ('tournament', 'last_update'): 'follows the data it dates',
    ('tournament', 'last_player_update'): 'follows the data it dates',
    ('tournament', 'last_pairing_update'): 'follows the data it dates',
    ('tournament', 'dirty'): 'follows the data it flags',
    ('board', 'last_result_update'): 'follows the result it dates',
    ('team_board', 'last_result_update'): 'follows the result it dates',
    ('info', 'plugin_data'): 'what the plugins remember of their connections',
    ('tournament', 'plugin_data'): 'what the plugins remember of their connections',
    ('player', 'plugin_data'): 'what the plugins remember of their connections',
    (
        'tournament_period',
        'plugin_data',
    ): 'what the plugins remember of their connections',
    ('tournament_player', 'pairing_number'): (
        'follows the starting rank; a renumbering is journaled as such'
    ),
    ('team', 'pairing_number'): (
        'follows the starting rank; a renumbering is journaled as such'
    ),
    ('player', 'team_index'): ('follows the roster changes, journaled as such'),
    ('tournament', 'index'): 'the order the tournaments are listed in',
    ('info', 'origin'): 'where the file came from, said by the entry that made it',
    ('info', 'origin_date'): 'where the file came from, said by the entry that made it',
    ('info', 'ratings_check_dismissed'): 'a warning dismissed',
    ('info', 'screens_fake_data'): 'a preview of the screens, nothing played',
    ('info', 'tag_ids'): 'the tags of this installation, not of the event',
}


def journaled_writes(
    written: set[tuple[str, str | None]],
) -> set[tuple[str, str | None]]:
    """What of *written* has to be journaled."""
    return {
        (table, column)
        for table, column in written
        if table not in UNJOURNALED_TABLES
        and not table.startswith('sqlite_')
        and (column is None or (table, column) not in UNJOURNALED_COLUMNS)
    }


class UnjournaledWriteError(SharlyChessException):
    pass


@dataclass
class JournalScope:
    """An operation (a request): what it wrote to the events, and whether it
    journaled it or said why not."""

    operation: str
    written: dict[str, set[tuple[str, str | None]]] = field(default_factory=dict)
    journaled: bool = False

    def unjournaled_writes(self) -> dict[str, set[tuple[str, str | None]]]:
        if self.journaled:
            return {}
        return {
            uniq_id: writes
            for uniq_id, written in self.written.items()
            if (writes := journaled_writes(written))
        }


_scope: ContextVar[JournalScope | None] = ContextVar(
    'sharly_chess_journal_scope', default=None
)


#: Whether the writes are followed, to complain about those not journaled:
#: while the application is developed and tested only.
WATCH_WRITES = TEST_ENV or DEVEL_ENV


def watches_writes() -> bool:
    """Whether what is written now is to be noted: within an operation, and
    outside of what is said not to be journaled."""
    return (
        WATCH_WRITES
        and _scope.get() is not None
        and _not_journaled_reason.get() is None
    )


def start_journal_scope(operation: str) -> JournalScope:
    scope = JournalScope(operation)
    _scope.set(scope)
    return scope


def current_journal_scope() -> JournalScope | None:
    return _scope.get()


def end_journal_scope() -> None:
    _scope.set(None)


def note_writes(event_uniq_id: str, written: set[tuple[str, str | None]]) -> None:
    """Called by the database once a write to the event is committed."""
    if _not_journaled_reason.get() is not None:
        return
    if (scope := _scope.get()) is not None:
        scope.written.setdefault(event_uniq_id, set()).update(written)


def check_journal_scope(scope: JournalScope) -> None:
    """Complains about an operation that wrote to an event without
    journaling it or saying why: an error in the logs, and a failure in the
    tests, so that a new operation is not left out of the journal."""
    if not (unjournaled := scope.unjournaled_writes()):
        return
    message = (
        f'[{scope.operation}] wrote to the event without journaling it nor saying '
        f'why not: '
        + '; '.join(
            f'[{uniq_id}] '
            + ', '.join(
                sorted(
                    f'{table}.{column}' if column else table for table, column in writes
                )
            )
            for uniq_id, writes in unjournaled.items()
        )
    )
    if TEST_ENV:
        raise UnjournaledWriteError(message)
    logger.error(message)


class JournalCategory(StrEnum):
    RESULTS = 'results'
    PAIRINGS = 'pairings'
    PLAYERS = 'players'
    TEAMS = 'teams'
    TOURNAMENTS = 'tournaments'
    EVENT = 'event'
    NOTES = 'notes'

    @property
    def label(self) -> str:
        match self:
            case JournalCategory.RESULTS:
                return _('Results')
            case JournalCategory.PAIRINGS:
                return _('Pairings')
            case JournalCategory.PLAYERS:
                return _('Players')
            case JournalCategory.TEAMS:
                return _('Teams')
            case JournalCategory.TOURNAMENTS:
                return _('Tournaments')
            case JournalCategory.EVENT:
                return _('Event')
            case JournalCategory.NOTES:
                return _('Notes')

    @property
    def icon_class(self) -> str:
        match self:
            case JournalCategory.RESULTS:
                return 'bi-1-square'
            case JournalCategory.PAIRINGS:
                return 'bi-arrow-left-right'
            case JournalCategory.PLAYERS:
                return 'bi-people'
            case JournalCategory.TEAMS:
                return 'bi-flag'
            case JournalCategory.TOURNAMENTS:
                return 'bi-diagram-3'
            case JournalCategory.EVENT:
                return 'bi-calendar-event'
            case JournalCategory.NOTES:
                return 'bi-sticky'


class JournalAction(StrEnum):
    """What an entry records. The value is a stable key written into the
    event, never a translated string."""

    RESULT_ENTERED = 'result_entered'
    RESULT_CHANGED = 'result_changed'
    RESULT_CLEARED = 'result_cleared'
    KNOCKOUT_WINNER = 'knockout_winner'
    POINT_ADJUSTMENT = 'point_adjustment'
    TEAM_POINT_ADJUSTMENT = 'team_point_adjustment'
    ILLEGAL_MOVE_ADDED = 'illegal_move_added'
    ILLEGAL_MOVE_REMOVED = 'illegal_move_removed'
    RATING_CORRECTION_SET = 'rating_correction_set'
    RATING_CORRECTION_REMOVED = 'rating_correction_removed'
    MANUAL_TIE_BREAKS_SET = 'manual_tie_breaks_set'
    MANUAL_TIE_BREAKS_RESET = 'manual_tie_breaks_reset'

    ROUND_PAIRED = 'round_paired'
    ROUND_UNPAIRED = 'round_unpaired'
    BOARDS_UNPAIRED = 'boards_unpaired'
    BOARD_PAIRED = 'board_paired'
    MANUAL_PAIRING_STARTED = 'manual_pairing_started'
    MANUAL_PAIRING_ENDED = 'manual_pairing_ended'
    MANUAL_PAIRING_CANCELLED = 'manual_pairing_cancelled'
    COLOURS_SWAPPED = 'colours_swapped'
    BYE_SET = 'bye_set'
    BYE_REMOVED = 'bye_removed'
    ROUND_PUBLISHED = 'round_published'
    ROUND_UNPUBLISHED = 'round_unpublished'
    PAIRING_SETTINGS_CHANGED = 'pairing_settings_changed'
    PROHIBITED_PAIRINGS_CHANGED = 'prohibited_pairings_changed'
    ROUND_ROBIN_SCHEDULE_SAVED = 'round_robin_schedule_saved'

    PLAYER_ADDED = 'player_added'
    PLAYER_DELETED = 'player_deleted'
    PLAYER_RENAMED = 'player_renamed'
    PLAYER_EDITED = 'player_edited'
    PLAYER_CHECKED_IN = 'player_checked_in'
    PLAYER_CHECKED_OUT = 'player_checked_out'
    PLAYERS_CHECKED_IN = 'players_checked_in'
    PLAYERS_CHECKED_OUT = 'players_checked_out'
    PLAYER_WITHDRAWN = 'player_withdrawn'
    PLAYER_RETURNED = 'player_returned'
    PLAYER_MOVED = 'player_moved'
    PLAYER_REPLACED = 'player_replaced'
    REPLACEMENT_WITHDRAWN = 'replacement_withdrawn'
    PLAYERS_IMPORTED = 'players_imported'
    PLAYERS_RENUMBERED = 'players_renumbered'
    PLAYERS_DISTRIBUTED = 'players_distributed'
    PLAYERS_UPDATED = 'players_updated'

    TEAM_ADDED = 'team_added'
    TEAM_DELETED = 'team_deleted'
    TEAM_RENAMED = 'team_renamed'
    TEAM_EDITED = 'team_edited'
    LINEUP_CHANGED = 'lineup_changed'
    TEAM_CHECKED_IN = 'team_checked_in'
    TEAM_CHECKED_OUT = 'team_checked_out'
    TEAMS_CHECKED_IN = 'teams_checked_in'
    TEAMS_CHECKED_OUT = 'teams_checked_out'
    TEAM_PLAYER_ADDED = 'team_player_added'
    TEAM_PLAYER_REMOVED = 'team_player_removed'
    TEAM_ORDER_CHANGED = 'team_order_changed'
    TEAM_MOVED = 'team_moved'
    TEAMS_RENUMBERED = 'teams_renumbered'
    TEAM_AFFILIATIONS_CHANGED = 'team_affiliations_changed'

    TOURNAMENT_CREATED = 'tournament_created'
    TOURNAMENT_DELETED = 'tournament_deleted'
    TOURNAMENT_IMPORTED = 'tournament_imported'
    TOURNAMENT_RENAMED = 'tournament_renamed'
    ROUNDS_CHANGED = 'rounds_changed'
    TIE_BREAKS_CHANGED = 'tie_breaks_changed'
    PAIRING_SYSTEM_CHANGED = 'pairing_system_changed'
    CHECK_IN_OPENED = 'check_in_opened'
    CHECK_IN_CLOSED = 'check_in_closed'
    TOURNAMENT_SETTINGS_CHANGED = 'tournament_settings_changed'
    FIDE_MODE_LEFT = 'fide_mode_left'

    SNAPSHOT_RESTORED = 'snapshot_restored'
    EVENT_CREATED = 'event_created'
    EVENT_IMPORTED = 'event_imported'
    EVENT_SETTINGS_CHANGED = 'event_settings_changed'
    ACCOUNT_CREATED = 'account_created'
    ACCOUNT_UPDATED = 'account_updated'
    ACCOUNT_DELETED = 'account_deleted'
    PERMISSION_GRANTED = 'permission_granted'
    PERMISSION_CHANGED = 'permission_changed'
    PERMISSION_REVOKED = 'permission_revoked'
    NOTE = 'note'

    @property
    def category(self) -> JournalCategory:
        return _ACTION_CATEGORIES[self]

    def sentence(self, data: dict[str, Any]) -> str:
        """What the entry says, from the values it was written with."""
        d = _SafeData(data)
        match self:
            case JournalAction.RESULT_ENTERED:
                return _('Board {board}: {white} – {black}, result {new}').format(
                    board=d['board'],
                    white=d['white'],
                    black=d['black'],
                    new=_result(data.get('new')),
                )
            case JournalAction.RESULT_CHANGED:
                return _(
                    'Board {board}: {white} – {black}, result changed from '
                    '{old} to {new}'
                ).format(
                    board=d['board'],
                    white=d['white'],
                    black=d['black'],
                    old=_result(data.get('old')),
                    new=_result(data.get('new')),
                )
            case JournalAction.RESULT_CLEARED:
                return _(
                    'Board {board}: {white} – {black}, result {old} cleared'
                ).format(
                    board=d['board'],
                    white=d['white'],
                    black=d['black'],
                    old=_result(data.get('old')),
                )
            case JournalAction.KNOCKOUT_WINNER:
                if not data.get('winner'):
                    return _('Board {board}: winner no longer designated').format(
                        board=d['board']
                    )
                return _('Board {board}: {winner} designated as the winner').format(
                    board=d['board'], winner=d['winner']
                )
            case JournalAction.POINT_ADJUSTMENT:
                return _(
                    '{player}: bonus or penalty changed from {old} to {new}'
                ).format(
                    player=d['player'],
                    old=_points(data.get('old')),
                    new=_points(data.get('new')),
                )
            case JournalAction.TEAM_POINT_ADJUSTMENT:
                return _(
                    '{team}: bonus or penalty changed from {old_mp} MP / {old_gp} GP '
                    'to {new_mp} MP / {new_gp} GP'
                ).format(
                    team=d['team'],
                    old_mp=_points(data.get('old_mp')),
                    old_gp=_points(data.get('old_gp')),
                    new_mp=_points(data.get('new_mp')),
                    new_gp=_points(data.get('new_gp')),
                )
            case JournalAction.ROUND_PAIRED:
                if data.get('partial'):
                    return _('Players left out of the round paired')
                return _('Round paired')
            case JournalAction.ROUND_UNPAIRED:
                if data.get('all'):
                    return _('All the rounds unpaired')
                return _('Round unpaired')
            case JournalAction.BOARDS_UNPAIRED:
                return _('Unpaired: {boards}').format(boards=_games(data))
            case JournalAction.BOARD_PAIRED:
                return _('Paired by hand: {boards}').format(boards=_games(data))
            case JournalAction.MANUAL_PAIRING_STARTED:
                return _('Editing of the pairings started')
            case JournalAction.MANUAL_PAIRING_ENDED:
                return _('Editing of the pairings validated')
            case JournalAction.MANUAL_PAIRING_CANCELLED:
                return _(
                    'Editing of the pairings cancelled, the round put back as it was'
                )
            case JournalAction.COLOURS_SWAPPED:
                return _(
                    'Board {board}: colours swapped, now {white} – {black}'
                ).format(board=d['board'], white=d['white'], black=d['black'])
            case JournalAction.BYE_SET:
                return _('{player}: {bye}').format(
                    player=d['player'], bye=_bye(data.get('bye'))
                )
            case JournalAction.BYE_REMOVED:
                return _('{player}: {bye} removed').format(
                    player=d['player'], bye=_bye(data.get('bye'))
                )
            case JournalAction.ROUND_PUBLISHED:
                return _('Round published')
            case JournalAction.ROUND_UNPUBLISHED:
                return _('Round unpublished')
            case JournalAction.PLAYER_ADDED:
                return _('{player} added').format(player=d['player'])
            case JournalAction.PLAYER_DELETED:
                return _('{player} deleted').format(player=d['player'])
            case JournalAction.PLAYER_RENAMED:
                return _('{old} renamed {new}').format(old=d['old'], new=d['new'])
            case JournalAction.PLAYER_EDITED:
                return _('{player} modified').format(player=d['player'])
            case JournalAction.PLAYER_CHECKED_IN:
                return _('{player} checked in').format(player=d['player'])
            case JournalAction.PLAYER_CHECKED_OUT:
                return _('{player} checked out').format(player=d['player'])
            case JournalAction.PLAYERS_CHECKED_IN:
                return _('{count} players checked in at once').format(count=d['count'])
            case JournalAction.PLAYERS_CHECKED_OUT:
                return _('{count} players checked out at once').format(count=d['count'])
            case JournalAction.PLAYER_WITHDRAWN:
                return _('{player} withdrawn from the tournament').format(
                    player=d['player']
                )
            case JournalAction.PLAYER_RETURNED:
                return _('{player} back in the tournament').format(player=d['player'])
            case JournalAction.PLAYER_REPLACED:
                return _('{player} replaces {replaced}').format(
                    player=d['player'], replaced=d['replaced']
                )
            case JournalAction.REPLACEMENT_WITHDRAWN:
                return _(
                    '{player} no longer replaces {replaced}, who takes the seat back'
                ).format(player=d['player'], replaced=d['replaced'])
            case JournalAction.PLAYER_MOVED:
                return _('{player} moved from [{old}] to [{new}]').format(
                    player=d['player'], old=d['old'], new=d['new']
                )
            case JournalAction.PLAYERS_IMPORTED:
                if data.get('replaced'):
                    return _(
                        '{count} players imported, replacing the players there were'
                    ).format(count=d['count'])
                return _('{count} players imported').format(count=d['count'])
            case JournalAction.PLAYERS_RENUMBERED:
                return _('Players renumbered')
            case JournalAction.PLAYERS_DISTRIBUTED:
                return _('{count} players distributed between the tournaments').format(
                    count=d['count']
                )
            case JournalAction.TEAM_ADDED:
                return _('Team {team} added').format(team=d['team'])
            case JournalAction.TEAM_DELETED:
                return _('Team {team} deleted').format(team=d['team'])
            case JournalAction.TEAM_RENAMED:
                return _('Team {old} renamed {new}').format(old=d['old'], new=d['new'])
            case JournalAction.LINEUP_CHANGED:
                return _('Line-up of {team} changed').format(team=d['team'])
            case JournalAction.TOURNAMENT_CREATED:
                return _('Tournament created')
            case JournalAction.TOURNAMENT_DELETED:
                return _('Tournament deleted')
            case JournalAction.TOURNAMENT_IMPORTED:
                if data.get('source'):
                    return _('Tournament imported from {source}').format(
                        source=d['source']
                    )
                return _('Tournament imported with {count} players').format(
                    count=d['count']
                )
            case JournalAction.TOURNAMENT_RENAMED:
                return _('Tournament [{old}] renamed [{new}]').format(
                    old=d['old'], new=d['new']
                )
            case JournalAction.ROUNDS_CHANGED:
                return _('Number of rounds changed from {old} to {new}').format(
                    old=d['old'], new=d['new']
                )
            case JournalAction.TIE_BREAKS_CHANGED:
                if data.get('old') and data.get('new'):
                    return _('Tie-breaks changed from {old} to {new}').format(
                        old=d['old'], new=d['new']
                    )
                return _('Tie-breaks changed')
            case JournalAction.PAIRING_SYSTEM_CHANGED:
                return _('Pairing system changed from {old} to {new}').format(
                    old=d['old'], new=d['new']
                )
            case JournalAction.CHECK_IN_OPENED:
                return _('Check-in opened')
            case JournalAction.CHECK_IN_CLOSED:
                return _('Check-in closed')
            case JournalAction.SNAPSHOT_RESTORED:
                return _('Backup of {date} restored').format(date=d['snapshot'])
            case JournalAction.ILLEGAL_MOVE_ADDED:
                return _('{player}: illegal move ({count})').format(
                    player=d['player'], count=d['count']
                )
            case JournalAction.ILLEGAL_MOVE_REMOVED:
                return _('{player}: illegal move removed ({count} left)').format(
                    player=d['player'], count=d['count']
                )
            case JournalAction.RATING_CORRECTION_SET:
                return _('For the rating report: {white} – {black} {result}').format(
                    white=d['white'],
                    black=d['black'],
                    result=_result(data.get('result')),
                )
            case JournalAction.RATING_CORRECTION_REMOVED:
                return _(
                    'Correction for the rating report removed: {white} – {black}'
                ).format(white=d['white'], black=d['black'])
            case JournalAction.MANUAL_TIE_BREAKS_SET:
                return _('Manual tie-break set for {players}').format(
                    players=', '.join(data.get('players') or [])
                )
            case JournalAction.MANUAL_TIE_BREAKS_RESET:
                return _('Manual tie-breaks reset')
            case JournalAction.PAIRING_SETTINGS_CHANGED:
                return _('Pairing settings changed')
            case JournalAction.PROHIBITED_PAIRINGS_CHANGED:
                return _('Prohibited pairings changed')
            case JournalAction.ROUND_ROBIN_SCHEDULE_SAVED:
                return _('Round-robin schedule saved')
            case JournalAction.PLAYERS_UPDATED:
                if data.get('source'):
                    return _('{count} players updated from {source}').format(
                        count=d['count'], source=d['source']
                    )
                return _('{count} players updated').format(count=d['count'])
            case JournalAction.TEAM_CHECKED_IN:
                return _('Team {team} checked in').format(team=d['team'])
            case JournalAction.TEAM_CHECKED_OUT:
                return _('Team {team} checked out').format(team=d['team'])
            case JournalAction.TEAMS_CHECKED_IN:
                return _('{count} teams checked in at once').format(count=d['count'])
            case JournalAction.TEAMS_CHECKED_OUT:
                return _('{count} teams checked out at once').format(count=d['count'])
            case JournalAction.TEAM_PLAYER_ADDED:
                return _('{player} added to team {team}').format(
                    player=d['player'], team=d['team']
                )
            case JournalAction.TEAM_PLAYER_REMOVED:
                return _('{player} removed from team {team}').format(
                    player=d['player'], team=d['team']
                )
            case JournalAction.TEAM_EDITED:
                return _('Team {team} modified').format(team=d['team'])
            case JournalAction.TEAM_ORDER_CHANGED:
                return _('Board order of team {team} changed').format(team=d['team'])
            case JournalAction.TEAM_MOVED:
                if not data.get('old'):
                    return _('Team {team} entered in [{new}]').format(
                        team=d['team'], new=d['new']
                    )
                if not data.get('new'):
                    return _('Team {team} taken out of [{old}]').format(
                        team=d['team'], old=d['old']
                    )
                return _('Team {team} moved from [{old}] to [{new}]').format(
                    team=d['team'], old=d['old'], new=d['new']
                )
            case JournalAction.TEAMS_RENUMBERED:
                return _('Teams renumbered')
            case JournalAction.TEAM_AFFILIATIONS_CHANGED:
                return _('Team affiliations changed')
            case JournalAction.TOURNAMENT_SETTINGS_CHANGED:
                return _('Tournament settings changed')
            case JournalAction.FIDE_MODE_LEFT:
                return _('FIDE mode left')
            case JournalAction.EVENT_CREATED:
                if data.get('copy_of'):
                    return _('Event created as a copy of [{event}]').format(
                        event=d['copy_of']
                    )
                return _('Event created')
            case JournalAction.EVENT_IMPORTED:
                return _('Event imported')
            case JournalAction.EVENT_SETTINGS_CHANGED:
                return _('Event settings changed')
            case JournalAction.ACCOUNT_CREATED:
                return _('Staff account {account} created').format(account=d['account'])
            case JournalAction.ACCOUNT_UPDATED:
                return _('Staff account {account} modified').format(
                    account=d['account']
                )
            case JournalAction.ACCOUNT_DELETED:
                return _('Staff account {account} deleted').format(account=d['account'])
            case JournalAction.PERMISSION_GRANTED:
                return _('{account}: access level {level} granted').format(
                    account=d['account'], level=d['level']
                )
            case JournalAction.PERMISSION_CHANGED:
                return _('{account}: access level {level} modified').format(
                    account=d['account'], level=d['level']
                )
            case JournalAction.PERMISSION_REVOKED:
                return _('{account}: access level {level} revoked').format(
                    account=d['account'], level=d['level']
                )
            case JournalAction.NOTE:
                return ''


_ACTION_CATEGORIES: dict[JournalAction, JournalCategory] = {
    JournalAction.RESULT_ENTERED: JournalCategory.RESULTS,
    JournalAction.RESULT_CHANGED: JournalCategory.RESULTS,
    JournalAction.RESULT_CLEARED: JournalCategory.RESULTS,
    JournalAction.KNOCKOUT_WINNER: JournalCategory.RESULTS,
    JournalAction.POINT_ADJUSTMENT: JournalCategory.RESULTS,
    JournalAction.TEAM_POINT_ADJUSTMENT: JournalCategory.RESULTS,
    JournalAction.ILLEGAL_MOVE_ADDED: JournalCategory.RESULTS,
    JournalAction.ILLEGAL_MOVE_REMOVED: JournalCategory.RESULTS,
    JournalAction.RATING_CORRECTION_SET: JournalCategory.RESULTS,
    JournalAction.RATING_CORRECTION_REMOVED: JournalCategory.RESULTS,
    JournalAction.MANUAL_TIE_BREAKS_SET: JournalCategory.RESULTS,
    JournalAction.MANUAL_TIE_BREAKS_RESET: JournalCategory.RESULTS,
    JournalAction.ROUND_PAIRED: JournalCategory.PAIRINGS,
    JournalAction.ROUND_UNPAIRED: JournalCategory.PAIRINGS,
    JournalAction.BOARDS_UNPAIRED: JournalCategory.PAIRINGS,
    JournalAction.BOARD_PAIRED: JournalCategory.PAIRINGS,
    JournalAction.MANUAL_PAIRING_STARTED: JournalCategory.PAIRINGS,
    JournalAction.MANUAL_PAIRING_ENDED: JournalCategory.PAIRINGS,
    JournalAction.MANUAL_PAIRING_CANCELLED: JournalCategory.PAIRINGS,
    JournalAction.COLOURS_SWAPPED: JournalCategory.PAIRINGS,
    JournalAction.BYE_SET: JournalCategory.PAIRINGS,
    JournalAction.BYE_REMOVED: JournalCategory.PAIRINGS,
    JournalAction.ROUND_PUBLISHED: JournalCategory.PAIRINGS,
    JournalAction.ROUND_UNPUBLISHED: JournalCategory.PAIRINGS,
    JournalAction.PAIRING_SETTINGS_CHANGED: JournalCategory.PAIRINGS,
    JournalAction.PROHIBITED_PAIRINGS_CHANGED: JournalCategory.PAIRINGS,
    JournalAction.ROUND_ROBIN_SCHEDULE_SAVED: JournalCategory.PAIRINGS,
    JournalAction.PLAYER_ADDED: JournalCategory.PLAYERS,
    JournalAction.PLAYER_DELETED: JournalCategory.PLAYERS,
    JournalAction.PLAYER_RENAMED: JournalCategory.PLAYERS,
    JournalAction.PLAYER_EDITED: JournalCategory.PLAYERS,
    JournalAction.PLAYER_CHECKED_IN: JournalCategory.PLAYERS,
    JournalAction.PLAYER_CHECKED_OUT: JournalCategory.PLAYERS,
    JournalAction.PLAYERS_CHECKED_IN: JournalCategory.PLAYERS,
    JournalAction.PLAYERS_CHECKED_OUT: JournalCategory.PLAYERS,
    JournalAction.PLAYER_WITHDRAWN: JournalCategory.PLAYERS,
    JournalAction.PLAYER_RETURNED: JournalCategory.PLAYERS,
    JournalAction.PLAYER_MOVED: JournalCategory.PLAYERS,
    JournalAction.PLAYER_REPLACED: JournalCategory.PLAYERS,
    JournalAction.REPLACEMENT_WITHDRAWN: JournalCategory.PLAYERS,
    JournalAction.PLAYERS_IMPORTED: JournalCategory.PLAYERS,
    JournalAction.PLAYERS_RENUMBERED: JournalCategory.PLAYERS,
    JournalAction.PLAYERS_DISTRIBUTED: JournalCategory.PLAYERS,
    JournalAction.PLAYERS_UPDATED: JournalCategory.PLAYERS,
    JournalAction.TEAM_ADDED: JournalCategory.TEAMS,
    JournalAction.TEAM_DELETED: JournalCategory.TEAMS,
    JournalAction.TEAM_RENAMED: JournalCategory.TEAMS,
    JournalAction.TEAM_EDITED: JournalCategory.TEAMS,
    JournalAction.LINEUP_CHANGED: JournalCategory.TEAMS,
    JournalAction.TEAM_CHECKED_IN: JournalCategory.TEAMS,
    JournalAction.TEAM_CHECKED_OUT: JournalCategory.TEAMS,
    JournalAction.TEAMS_CHECKED_IN: JournalCategory.TEAMS,
    JournalAction.TEAMS_CHECKED_OUT: JournalCategory.TEAMS,
    JournalAction.TEAM_PLAYER_ADDED: JournalCategory.TEAMS,
    JournalAction.TEAM_PLAYER_REMOVED: JournalCategory.TEAMS,
    JournalAction.TEAM_ORDER_CHANGED: JournalCategory.TEAMS,
    JournalAction.TEAM_MOVED: JournalCategory.TEAMS,
    JournalAction.TEAMS_RENUMBERED: JournalCategory.TEAMS,
    JournalAction.TEAM_AFFILIATIONS_CHANGED: JournalCategory.TEAMS,
    JournalAction.TOURNAMENT_CREATED: JournalCategory.TOURNAMENTS,
    JournalAction.TOURNAMENT_DELETED: JournalCategory.TOURNAMENTS,
    JournalAction.TOURNAMENT_IMPORTED: JournalCategory.TOURNAMENTS,
    JournalAction.TOURNAMENT_RENAMED: JournalCategory.TOURNAMENTS,
    JournalAction.ROUNDS_CHANGED: JournalCategory.TOURNAMENTS,
    JournalAction.TIE_BREAKS_CHANGED: JournalCategory.TOURNAMENTS,
    JournalAction.PAIRING_SYSTEM_CHANGED: JournalCategory.TOURNAMENTS,
    JournalAction.CHECK_IN_OPENED: JournalCategory.TOURNAMENTS,
    JournalAction.CHECK_IN_CLOSED: JournalCategory.TOURNAMENTS,
    JournalAction.TOURNAMENT_SETTINGS_CHANGED: JournalCategory.TOURNAMENTS,
    JournalAction.FIDE_MODE_LEFT: JournalCategory.TOURNAMENTS,
    JournalAction.SNAPSHOT_RESTORED: JournalCategory.EVENT,
    JournalAction.EVENT_CREATED: JournalCategory.EVENT,
    JournalAction.EVENT_IMPORTED: JournalCategory.EVENT,
    JournalAction.EVENT_SETTINGS_CHANGED: JournalCategory.EVENT,
    JournalAction.ACCOUNT_CREATED: JournalCategory.EVENT,
    JournalAction.ACCOUNT_UPDATED: JournalCategory.EVENT,
    JournalAction.ACCOUNT_DELETED: JournalCategory.EVENT,
    JournalAction.PERMISSION_GRANTED: JournalCategory.EVENT,
    JournalAction.PERMISSION_CHANGED: JournalCategory.EVENT,
    JournalAction.PERMISSION_REVOKED: JournalCategory.EVENT,
    JournalAction.NOTE: JournalCategory.NOTES,
}


class _SafeData(dict[str, Any]):
    """The values of an entry, a missing one reading as a question mark
    rather than failing the whole journal."""

    def __missing__(self, key: str) -> str:
        return '?'


def _points(value: Any) -> str:
    """A number of points, signed: +1, -0.5, 0."""
    try:
        number = float(value)
    except TypeError, ValueError:
        return '?'
    text = f'{number:g}'
    return f'+{text}' if number > 0 else text


def _result(value: Any) -> str:
    try:
        return str(Result(value)) or '—'
    except ValueError:
        return '?'


def _bye(value: Any) -> str:
    try:
        result = Result(value)
    except ValueError:
        return '?'
    match result:
        case Result.ZERO_POINT_BYE:
            return _('zero-point bye')
        case Result.HALF_POINT_BYE:
            return _('half-point bye')
        case Result.FULL_POINT_BYE:
            return _('full-point bye')
        case Result.PAIRING_ALLOCATED_BYE:
            return _('pairing-allocated bye')
        case _:
            return str(result)


def _games(data: dict[str, Any]) -> str:
    games: list[list[str | None]] = data.get('games') or []
    return ', '.join(
        f'{white} – {black}' if black else str(white) for white, black in games
    )


@dataclass(frozen=True)
class JournalEntry:
    """An entry of the journal, as shown."""

    stored: StoredJournalEntry

    @property
    def id(self) -> int:
        assert self.stored.id is not None
        return self.stored.id

    @property
    def at(self) -> datetime:
        return self.stored.at

    @property
    def at_str(self) -> str:
        return format_datetime(self.stored.at)

    @property
    def action(self) -> JournalAction | None:
        try:
            return JournalAction(self.stored.action)
        except ValueError:
            return None

    @property
    def category(self) -> JournalCategory | None:
        return self.action.category if self.action else None

    @property
    def is_note(self) -> bool:
        return self.action == JournalAction.NOTE

    @property
    def sentence(self) -> str:
        """What was done; the text of the entry stands alone when the action
        is not known to this version (a plugin's, or a later version's)."""
        if self.action is None:
            return self.stored.text or self.stored.action
        try:
            return self.action.sentence(self.stored.data)
        except Exception:
            logger.exception('Journal entry [%s] could not be read', self.stored.id)
            return self.stored.action

    @property
    def text(self) -> str | None:
        """The free text written with the entry, the note of an arbiter."""
        if self.action is None:
            return None
        return self.stored.text

    @property
    def tournament_id(self) -> int | None:
        return self.stored.tournament_id

    @property
    def tournament_name(self) -> str | None:
        return self.stored.data.get('tournament')

    @property
    def round(self) -> int | None:
        return self.stored.round_

    @property
    def player_id(self) -> int | None:
        return self.stored.player_id

    @property
    def board_id(self) -> int | None:
        return self.stored.board_id

    @property
    def author(self) -> Author | None:
        """Who acted, if anybody: an action may come from no one, such as one
        brought by a synchronisation running on its own."""
        if self.stored.author_kind is None:
            return None
        try:
            kind = AuthorKind(self.stored.author_kind)
        except ValueError:
            return None
        return Author(kind, self.stored.account_id)

    @property
    def source(self) -> Source:
        try:
            kind = SourceKind(self.stored.source_kind)
        except ValueError:
            kind = SourceKind.APPLICATION
        return Source(kind, self.stored.source_name, self.stored.host)

    @property
    def host(self) -> str | None:
        return self.stored.host

    @property
    def author_key(self) -> str:
        return identity_key(author_identity(self.author))

    @property
    def source_key(self) -> str:
        return identity_key(source_identity(self.source))


def author_label(author: Author | None, name: str | None = None) -> str:
    """Who acted: the administrator, or the staff account named *name*,
    which is that of a deleted account unless it is given."""
    if author is None:
        return '—'
    if author.kind == AuthorKind.ADMINISTRATOR:
        return _('Administrator')
    if name is not None:
        return name
    return _('{account} (deleted account)').format(account='?')


def source_label(source: Source) -> str:
    match source.kind:
        case SourceKind.COMPUTER:
            return _('This computer')
        case SourceKind.NETWORK:
            return _('Another device')
        case SourceKind.SCREEN:
            return _('Screen [{screen}]').format(screen=source.name or '?')
        case SourceKind.PLUGIN:
            return source.name or '?'
        case _:
            return _('Sharly Chess')


Identity = tuple[str | None, int | str | None, str | None]
"""An author (kind, account id, name) or a source (kind, name, address of a
device of the network) as the filters of the journal tell them apart."""


def author_identity(author: Author | None) -> Identity:
    """An author as the filters tell them apart: by their account, whatever
    the name it had when it acted."""
    if author is None:
        return (None, None, None)
    return (author.kind.value, author.account_id, None)


def source_identity(source: Source) -> Identity:
    return (
        source.kind.value,
        source.name,
        source.host if source.kind == SourceKind.NETWORK else None,
    )


def identity_key(identity: Identity) -> str:
    return json.dumps(identity)


def parse_identity_key(key: str | None) -> Identity | None:
    if not key:
        return None
    try:
        kind, middle, name = json.loads(key)
    except ValueError, TypeError:
        return None
    if not isinstance(kind, str | None):
        return None
    return (
        kind,
        middle if isinstance(middle, int | str) else None,
        name if isinstance(name, str) else None,
    )


def record(
    event_uniq_id: str,
    action: JournalAction | str,
    *,
    tournament: Tournament | None = None,
    round_: int | None = None,
    board_id: int | None = None,
    player_id: int | None = None,
    team_id: int | None = None,
    data: dict[str, Any] | None = None,
    text: str | None = None,
) -> None:
    """Write an entry to the journal of the event.

    Inside a write to the event, the entry goes with it and is committed or
    rolled back with it. Writing the journal never fails the action it
    records: the failure is logged and the action goes on.
    """
    if _not_journaled_reason.get() is not None:
        return
    if (scope := _scope.get()) is not None:
        scope.journaled = True
    from database.sqlite.event.event_database import EventDatabase

    actor = current_actor()
    entry_data = dict(data or {})
    if tournament is not None:
        entry_data.setdefault('tournament', tournament.name)
    stored_entry = StoredJournalEntry(
        id=None,
        at=datetime.now(),
        action=str(action),
        author_kind=actor.author.kind if actor.author else None,
        account_id=actor.author.account_id if actor.author else None,
        source_kind=actor.source.kind,
        source_name=actor.source.name,
        host=actor.source.host,
        tournament_id=tournament.id if tournament is not None else None,
        round_=round_,
        board_id=board_id,
        player_id=player_id,
        team_id=team_id,
        data=entry_data,
        text=text,
    )
    try:
        if (database := EventDatabase.open_writer(event_uniq_id)) is not None:
            database.add_stored_journal_entry(stored_entry)
        else:
            with EventDatabase(event_uniq_id, write=True) as database:
                database.add_stored_journal_entry(stored_entry)
    except Exception:
        logger.exception(
            'The journal of event [%s] could not record [%s]', event_uniq_id, action
        )


def load_journal(
    event_uniq_id: str,
    *,
    tournament_id: int | None = None,
    category: JournalCategory | None = None,
    author: Identity | None = None,
    source: Identity | None = None,
    limit: int | None = None,
    after_id: int | None = None,
    before_id: int | None = None,
) -> list[JournalEntry]:
    """The entries of the journal of the event matching the filters, the most
    recent first: the journal is only ever read here, never with the event."""
    from database.sqlite.event.event_database import EventDatabase

    actions = (
        [action.value for action in JournalAction if action.category == category]
        if category is not None
        else None
    )
    with EventDatabase(event_uniq_id) as database:
        return [
            JournalEntry(stored)
            for stored in database.load_stored_journal_entries(
                tournament_id=tournament_id,
                actions=actions,
                author=author,
                source=source,
                limit=limit,
                after_id=after_id,
                before_id=before_id,
            )
        ]


def load_journal_entry(event_uniq_id: str, entry_id: int) -> JournalEntry | None:
    from database.sqlite.event.event_database import EventDatabase

    with EventDatabase(event_uniq_id) as database:
        stored = database.load_stored_journal_entry(entry_id)
    return JournalEntry(stored) if stored else None


@dataclass(frozen=True)
class JournalFilterOptions:
    """What the filters of the journal offer: only what it holds."""

    has_entries: bool
    tournament_names: dict[int, str | None]
    categories: list[JournalCategory]
    authors: list[Identity]
    sources: list[Identity]


def load_journal_filter_options(event_uniq_id: str) -> JournalFilterOptions:
    from database.sqlite.event.event_database import EventDatabase

    with EventDatabase(event_uniq_id) as database:
        if not database.has_journal_entries():
            return JournalFilterOptions(False, {}, [], [], [])
        tournament_names = database.load_journal_tournament_names()
        actions = database.load_journal_actions()
        authors = database.load_journal_authors()
        sources = database.load_journal_sources()
    categories = {
        JournalAction(action).category
        for action in actions
        if action in JournalAction._value2member_map_
    }
    return JournalFilterOptions(
        True,
        tournament_names,
        [category for category in JournalCategory if category in categories],
        authors,
        sources,
    )
