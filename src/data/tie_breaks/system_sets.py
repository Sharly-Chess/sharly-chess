"""System tie-break sets — code-defined named lists of tie-breaks.

Add entries to `SYSTEM_TIE_BREAK_SETS` to expose new sets in the picker.
Each entry is bound to one pairing system; create one entry per pairing
system the set targets.
"""

from dataclasses import dataclass
from typing import TYPE_CHECKING, Callable

from common.i18n import _
from data.pairings.systems import SwissPairingSystem, RoundRobinPairingSystem

if TYPE_CHECKING:
    from data.event import Event
    from data.tie_breaks.sets import TieBreakSet
    from data.tie_breaks.tie_breaks import TieBreak


@dataclass
class SystemTieBreakSetDefinition:
    key: str
    name_factory: Callable[[], str]
    pairing_system_id: str
    tie_break_factory: Callable[[], list['TieBreak']]


def _sc_recommendation_swiss() -> list['TieBreak']:
    from data.pairings.systems import SwissPairingSystem

    return SwissPairingSystem().recommended_tie_breaks


def _sc_recommendation_round_robin() -> list['TieBreak']:
    from data.pairings.systems import RoundRobinPairingSystem

    return RoundRobinPairingSystem().recommended_tie_breaks


SYSTEM_TIE_BREAK_SETS: list[SystemTieBreakSetDefinition] = [
    SystemTieBreakSetDefinition(
        key='sc-recommendation-swiss',
        name_factory=lambda: _('SC Recommendation'),
        pairing_system_id=SwissPairingSystem.static_id(),
        tie_break_factory=_sc_recommendation_swiss,
    ),
    SystemTieBreakSetDefinition(
        key='sc-recommendation-round-robin',
        name_factory=lambda: _('SC Recommendation'),
        pairing_system_id=RoundRobinPairingSystem.static_id(),
        tie_break_factory=_sc_recommendation_round_robin,
    ),
]


def build_system_tie_break_sets(event: 'Event') -> list['TieBreakSet']:
    """Materialize all system tie-break set definitions into TieBreakSet objects."""
    from data.tie_breaks.sets import TieBreakSet, TieBreakSetSource

    sets: list['TieBreakSet'] = []
    for definition in SYSTEM_TIE_BREAK_SETS:
        tie_breaks = definition.tie_break_factory()
        sets.append(
            TieBreakSet(
                key=definition.key,
                name=definition.name_factory(),
                source=TieBreakSetSource.SYSTEM,
                pairing_system_id=definition.pairing_system_id,
                stored_tie_breaks=[tb.to_stored_value() for tb in tie_breaks],
            )
        )
    return sets
