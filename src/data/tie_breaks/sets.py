"""Tie-break sets — named ordered collections of tie-breaks (with full
parameters) that can be applied to a tournament that has no tie-breaks yet.

Sets come from four sources:
  - SYSTEM: SC recommendation, FIDE 2019, plugins
  - CUSTOM: stored in the global `.scc` config DB, shared by all users of
    the server instance
  - TOURNAMENT: snapshot of another tournament in the same event
"""

import copy
from dataclasses import dataclass, field
from enum import StrEnum
from logging import Logger
from typing import TYPE_CHECKING, Optional

from common.i18n import _
from common.logger import get_logger
from data.tie_breaks.managers import TieBreakManager, TieBreakOptionManager
from database.sqlite.event.event_store import StoredTieBreak

if TYPE_CHECKING:
    from data.event import Event
    from data.tie_breaks.tie_breaks import TieBreak
    from data.tournament import Tournament

logger: Logger = get_logger()


class TieBreakSetSource(StrEnum):
    TOURNAMENT = 'tournament'
    CUSTOM = 'custom'
    SYSTEM = 'system'

    @property
    def label(self) -> str:
        match self:
            case self.SYSTEM:
                return _('System')
            case self.CUSTOM:
                return _('Custom')
            case self.TOURNAMENT:
                return _('Event tournaments')
            case _:
                raise ValueError(self)


@dataclass
class TieBreakSet:
    """In-memory representation of a tie-break set."""

    key: str
    name: str
    source: TieBreakSetSource
    pairing_system_id: str
    stored_tie_breaks: list[StoredTieBreak]
    disabled: bool = False
    disabled_reason: str | None = None
    custom_set_id: int | None = None
    tie_break_acronyms: list[str] = field(default_factory=list)

    def instantiate_tie_breaks(
        self, event: Optional['Event']
    ) -> list['TieBreak | None']:
        """Materialize fresh TieBreak instances from the stored payload."""
        return [
            instantiate_tie_break(stored_tb, event)
            for stored_tb in self.stored_tie_breaks
        ]

    def tooltip_message(self, event: Optional['Event'] = None) -> str:
        return ''.join(
            [
                f'<div class="text-start">{index}. {tie_break.full_name}</div>'
                for index, tie_break in enumerate(
                    self.instantiate_tie_breaks(event),
                    start=1,
                )
                if tie_break is not None
            ]
        )


def instantiate_tie_break(
    stored_tie_break: StoredTieBreak, event: Optional['Event']
) -> 'TieBreak | None':
    """Materialize a single TieBreak from its stored value.
    Returns None if the type is unknown for this event (e.g. plugin disabled)."""
    try:
        tie_break_type = TieBreakManager(event).get_type(stored_tie_break.type)
    except KeyError:
        logger.warning('Tie-break type [%s] unknown.', stored_tie_break.type)
        return None
    option_manager = TieBreakOptionManager(event)
    options = []
    for option_id, option_value in stored_tie_break.options.items():
        try:
            option_type = option_manager.get_type(option_id)
            options.append(option_type(option_value))
        except KeyError:
            logger.warning(
                'Unknown tie-break option [%s] for tie-break [%s].',
                option_id,
                stored_tie_break.type,
            )
    return tie_break_type(options)


def _all_tie_break_subclasses() -> 'list[type[TieBreak]]':
    """Collect every concrete TieBreak subclass loaded in the process,
    ignoring abstract intermediates."""
    from data.tie_breaks.tie_breaks import TieBreak

    seen: 'set[type[TieBreak]]' = set()
    stack: 'list[type[TieBreak]]' = list(TieBreak.__subclasses__())
    result: 'list[type[TieBreak]]' = []
    while stack:
        cls = stack.pop()
        if cls in seen:
            continue
        seen.add(cls)
        stack.extend(cls.__subclasses__())
        try:
            cls.static_id()
        except (NotImplementedError, TypeError):
            continue
        result.append(cls)
    return result


def friendly_name_for_tie_break_type(type_id: str) -> str:
    """Look up a TB type's friendly name across all loaded TieBreak classes.
    Falls back to the type id if no class matches."""
    for cls in _all_tie_break_subclasses():
        try:
            if cls.static_id() == type_id:
                return cls.static_name()
        except (NotImplementedError, TypeError):
            continue
    return type_id


def stored_tie_break_to_dict(stored_tie_break: StoredTieBreak) -> dict[str, object]:
    """Serializable representation for storage in `tie_break_set.stored_tie_breaks`."""
    return {
        'type': stored_tie_break.type,
        'options': stored_tie_break.options,
    }


def evaluate_set_against_tournament(
    tie_break_set: TieBreakSet, tournament: 'Tournament'
) -> tuple[bool, str | None]:
    """Return (disabled, reason). A set is disabled if any TB returns an
    invalid message, or if the set contains an internal duplicate."""
    tie_breaks = tie_break_set.instantiate_tie_breaks(tournament.event)
    for stored_tb, tie_break in zip(tie_break_set.stored_tie_breaks, tie_breaks):
        if tie_break is None:
            return True, _('Tie-break [{name}] is not available in this event.').format(
                name=friendly_name_for_tie_break_type(stored_tb.type)
            )
        if message := tournament.tie_break_invalid_message(tie_break):
            tooltip = (
                f'<div class="fw-bold">'
                f'  {tie_break.full_name} ({tie_break.acronym})'
                f'</div>{message}'
            )
            return True, tooltip
    last_id: str | None = None
    for tie_break in tie_breaks:
        assert tie_break is not None
        if tie_break.allow_multiple and tie_break.id == last_id:
            return True, _('This set contains [{name}] twice in a row.').format(
                name=tie_break.full_name
            )
        last_id = tie_break.id
    return False, None


def fill_acronyms(tie_break_set: TieBreakSet, event: 'Event | None') -> None:
    """Populate `tie_break_acronyms` on the set for UI display."""
    acronyms: list[str] = []
    for tie_break in tie_break_set.instantiate_tie_breaks(event):
        if tie_break is None:
            continue
        acronyms.append(tie_break.acronym)
    tie_break_set.tie_break_acronyms = acronyms


def sibling_tournaments_with_tie_breaks(
    tournament: 'Tournament',
) -> list['Tournament']:
    """Return tournaments of the same event with the same pairing system
    and at least one tie-break (excluding the current tournament)."""
    return [
        sibling
        for sibling in tournament.event.tournaments
        if sibling.id != tournament.id
        and sibling.pairing_system == tournament.pairing_system
        and sibling.tie_breaks_by_id
    ]


def tie_break_set_from_tournament(source_tournament: 'Tournament') -> TieBreakSet:
    """Build a snapshot TieBreakSet from a tournament's current tie-breaks."""
    stored_tie_breaks = [
        StoredTieBreak(
            id=None,
            tournament_id=0,
            type=stored_tb.type,
            options=copy.deepcopy(stored_tb.options),
            index=index,
        )
        for index, stored_tb in enumerate(
            source_tournament.stored_tournament.stored_tie_breaks
        )
    ]
    return TieBreakSet(
        key=f'tournament:{source_tournament.id}',
        name=source_tournament.name,
        source=TieBreakSetSource.TOURNAMENT,
        pairing_system_id=source_tournament.pairing_system.id,
        stored_tie_breaks=stored_tie_breaks,
    )


def available_tie_break_sets(
    tournament: 'Tournament',
) -> dict[TieBreakSetSource, list[TieBreakSet]]:
    """Return all tie-break sets available for the tournament, grouped by source.
    Each set's `disabled` and `disabled_reason` are evaluated against the tournament."""
    from common.sharly_chess_config import SharlyChessConfig
    from data.tie_breaks.system_sets import build_system_tie_break_sets

    pairing_system_id = tournament.pairing_system.id
    grouped: dict[TieBreakSetSource, list[TieBreakSet]] = {
        source: [] for source in TieBreakSetSource
    }

    grouped[TieBreakSetSource.SYSTEM] = build_system_tie_break_sets(tournament)

    for tie_break_set in SharlyChessConfig().custom_tie_break_sets:
        if tie_break_set.pairing_system_id == pairing_system_id:
            grouped[TieBreakSetSource.CUSTOM].append(tie_break_set)

    for sibling in sibling_tournaments_with_tie_breaks(tournament):
        grouped[TieBreakSetSource.TOURNAMENT].append(
            tie_break_set_from_tournament(sibling)
        )

    for sets in grouped.values():
        for tie_break_set in sets:
            disabled, reason = evaluate_set_against_tournament(
                tie_break_set, tournament
            )
            tie_break_set.disabled = disabled
            tie_break_set.disabled_reason = reason
            fill_acronyms(tie_break_set, tournament.event)

    return grouped


def get_tie_break_set(
    tournament: 'Tournament', source: str, key: str
) -> TieBreakSet | None:
    """Look up a single tie-break set by source + key."""
    try:
        source_enum = TieBreakSetSource(source)
    except ValueError:
        return None
    grouped = available_tie_break_sets(tournament)
    for tie_break_set in grouped.get(source_enum, []):
        if tie_break_set.key == key:
            return tie_break_set
    return None
