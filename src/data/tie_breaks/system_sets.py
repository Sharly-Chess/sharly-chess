"""System tie-break sets — code-defined named lists of tie-breaks.

Add entries to `SYSTEM_TIE_BREAK_SETS` to expose new sets in the picker.
Each entry is bound to one pairing system; create one entry per pairing
system the set targets.
"""

from dataclasses import dataclass
from typing import TYPE_CHECKING

from common.i18n import _
from data.pairings.systems import SwissPairingSystem, RoundRobinPairingSystem
from data.tie_breaks import tie_breaks
from data.tie_breaks.cutters import Cut1TieBreakCutter
from data.tie_breaks.options import (
    CutterWithMedianTieBreakOption,
    EstimatedRatingsTieBreakOption,
)
from data.tournament import Tournament
from plugins.manager import plugin_manager

if TYPE_CHECKING:
    from data.event import Event
    from data.tie_breaks.sets import TieBreakSet
    from data.tie_breaks.tie_breaks import TieBreak


@dataclass
class SystemTieBreakSet:
    key: str
    name: str
    tie_breaks: list['TieBreak']


def _swiss_system_sets(event: 'Event') -> list['SystemTieBreakSet']:
    system_sets: list[SystemTieBreakSet] = [
        SystemTieBreakSet(
            key='swiss-sc-recommendation',
            name=_('Sharly Chess recommendation'),
            tie_breaks=[
                tie_breaks.StandardBuchholzTieBreak(
                    [CutterWithMedianTieBreakOption(Cut1TieBreakCutter().id)]
                ),
                tie_breaks.DirectEncounterTieBreak(),
                tie_breaks.StandardBuchholzTieBreak(),
                tie_breaks.SonnebornBergerTieBreak(),
                tie_breaks.WinsTieBreak(),
            ],
        ),
        SystemTieBreakSet(
            key='swiss-fide-recommendation-2019',
            name=_('FIDE recommendation (2019)'),
            tie_breaks=[
                tie_breaks.StandardBuchholzTieBreak(
                    [CutterWithMedianTieBreakOption(Cut1TieBreakCutter().id)]
                ),
                tie_breaks.StandardBuchholzTieBreak(),
                tie_breaks.SonnebornBergerTieBreak(),
                tie_breaks.ProgressiveScoresTieBreak(),
                tie_breaks.DirectEncounterTieBreak(),
                tie_breaks.WinsTieBreak(),
                tie_breaks.GamesWonWithBlackTieBreak(),
            ],
        ),
        SystemTieBreakSet(
            key='swiss-fide-recommendation-2019-unrated',
            name=_('FIDE recommendation - Unrated (2019)'),
            tie_breaks=[
                tie_breaks.StandardBuchholzTieBreak(
                    [CutterWithMedianTieBreakOption(Cut1TieBreakCutter().id)]
                ),
                tie_breaks.StandardBuchholzTieBreak(),
                tie_breaks.DirectEncounterTieBreak(),
                tie_breaks.AverageRatingOpponentsTieBreak(
                    [EstimatedRatingsTieBreakOption(True)]
                ),
                tie_breaks.WinsTieBreak(),
                tie_breaks.GamesWonWithBlackTieBreak(),
                tie_breaks.GamesPlayedWithBlackTieBreak(),
                tie_breaks.SonnebornBergerTieBreak(),
            ],
        ),
    ]
    plugin_manager.hook_for_event(event, 'insert_swiss_system_tie_break_sets')(
        system_sets=system_sets
    )
    return system_sets


def _round_robin_system_sets() -> list['SystemTieBreakSet']:
    system_sets: list[SystemTieBreakSet] = [
        SystemTieBreakSet(
            key='rr-fide-recommendation-2019',
            name=_('FIDE recommendation (2019)'),
            tie_breaks=[
                tie_breaks.DirectEncounterTieBreak(),
                tie_breaks.WinsTieBreak(),
                tie_breaks.SonnebornBergerTieBreak(),
                tie_breaks.KoyaTieBreak(),
            ],
        ),
    ]
    return system_sets


def build_system_tie_break_sets(tournament: 'Tournament') -> list['TieBreakSet']:
    """Materialize all system tie-break set definitions into TieBreakSet objects."""
    from data.tie_breaks.sets import TieBreakSet, TieBreakSetSource

    event = tournament.event
    system_sets: list[SystemTieBreakSet] = []
    system_id = tournament.pairing_system.id
    if system_id == SwissPairingSystem().id:
        system_sets = _swiss_system_sets(event)
    elif system_id == RoundRobinPairingSystem().id:
        system_sets = _round_robin_system_sets()
    return [
        TieBreakSet(
            key=system_set.key,
            name=system_set.name,
            source=TieBreakSetSource.SYSTEM,
            pairing_system_id=system_id,
            stored_tie_breaks=[
                tie_break.to_stored_value() for tie_break in system_set.tie_breaks
            ],
        )
        for system_set in system_sets
    ]
