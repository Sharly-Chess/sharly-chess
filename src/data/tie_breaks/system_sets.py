"""System tie-break sets — code-defined named lists of tie-breaks.

Add entries to `SYSTEM_TIE_BREAK_SETS` to expose new sets in the picker.
Each entry is bound to one pairing system; create one entry per pairing
system the set targets.
"""

from dataclasses import dataclass
from typing import TYPE_CHECKING

from common.i18n import _
from data.pairings.scheveningen import ScheveningenPairingSystem
from data.pairings.systems import (
    SwissPairingSystem,
    RoundRobinPairingSystem,
    TeamSwissPairingSystem,
    TeamRoundRobinPairingSystem,
)
from data.tie_breaks import tie_breaks
from data.tie_breaks import team_tie_breaks
from data.tie_breaks.cutters import Cut1TieBreakCutter
from data.tie_breaks.options import (
    CutterWithMedianTieBreakOption,
    EstimatedRatingsTieBreakOption,
)
from data.tie_breaks.team_tie_breaks import (
    EDEKnockoutTieBreakOption,
    EDEKnockoutVariant,
    ESBVariantTieBreakOption,
    ESBVariant,
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
                tie_breaks.PointsTieBreak(),
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
                tie_breaks.PointsTieBreak(),
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
                tie_breaks.PointsTieBreak(),
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
                tie_breaks.PointsTieBreak(),
                tie_breaks.DirectEncounterTieBreak(),
                tie_breaks.WinsTieBreak(),
                tie_breaks.SonnebornBergerTieBreak(),
                tie_breaks.KoyaTieBreak(),
            ],
        ),
    ]
    return system_sets


def _team_swiss_system_sets(event: 'Event') -> list['SystemTieBreakSet']:
    """
    Sharly Chess recommandations for team Swiss tournaments are:
    1. PTS
    2. EDEBT (EDE + BC + TBR)
    3. MPvGP
    4. BH
    Notes:
        - this set is OK whatever the primary score is (MP or GP)
        - this set is not the one used by FFE, but an FFE-specific EDE must be implemented based on FFE team tie-breaks
    """
    system_sets: list[SystemTieBreakSet] = [
        SystemTieBreakSet(
            key='team-swiss-sc-recommendation',
            name=_('Sharly Chess recommendation'),
            tie_breaks=[
                tie_breaks.PointsTieBreak(),
                team_tie_breaks.ExtendedDirectEncounterTieBreak(
                    [
                        EDEKnockoutTieBreakOption(EDEKnockoutVariant.EDEBT),
                    ]
                ),
                team_tie_breaks.MatchPointsVsGamePointsTieBreak(),
                tie_breaks.StandardBuchholzTieBreak(),
            ],
        ),
    ]
    plugin_manager.hook_for_event(event, 'insert_team_swiss_system_tie_break_sets')(
        system_sets=system_sets
    )
    return system_sets


def _team_round_robin_system_sets(event: 'Event') -> list['SystemTieBreakSet']:
    """
    Sharly Chess recommandations for team RR tournaments are:
    - when the primary score is MP
        1. PTS
        2. MPvGP
        3. EDEBT (EDE + BC + TBR)
        4. EMGSB
        5. EGMSB
    - when the primary score is GP
        1. PTS
        2. MPvGP
        3. EDEBT (EDE + BC + TBR)
        4. EGMSB
        5. EMGSB
    Note: this set is not the one used by FFE, but an FFE-specific EDE must be implemented based on FFE team tie-breaks
    """
    system_sets: list[SystemTieBreakSet] = [
        SystemTieBreakSet(
            key='team-rr-sc-recommendation-priamry-score-mp',
            name=_('Sharly Chess recommendation (MP as primary score)'),
            tie_breaks=[
                tie_breaks.PointsTieBreak(),
                team_tie_breaks.MatchPointsVsGamePointsTieBreak(),
                team_tie_breaks.ExtendedDirectEncounterTieBreak(
                    [
                        EDEKnockoutTieBreakOption(EDEKnockoutVariant.EDEBT),
                    ]
                ),
                team_tie_breaks.ExtendedSonnebornBergerTeamTieBreak(
                    [
                        ESBVariantTieBreakOption(ESBVariant.EMGSB),
                    ]
                ),
                team_tie_breaks.ExtendedSonnebornBergerTeamTieBreak(
                    [
                        ESBVariantTieBreakOption(ESBVariant.EGMSB),
                    ]
                ),
            ],
        ),
        SystemTieBreakSet(
            key='team-rr-sc-recommendation-priamry-score-gp',
            name=_('Sharly Chess recommendation (GP as primary score)'),
            tie_breaks=[
                tie_breaks.PointsTieBreak(),
                team_tie_breaks.MatchPointsVsGamePointsTieBreak(),
                team_tie_breaks.ExtendedDirectEncounterTieBreak(
                    [
                        EDEKnockoutTieBreakOption(EDEKnockoutVariant.EDEBT),
                    ]
                ),
                team_tie_breaks.ExtendedSonnebornBergerTeamTieBreak(
                    [
                        ESBVariantTieBreakOption(ESBVariant.EGMSB),
                    ]
                ),
                team_tie_breaks.ExtendedSonnebornBergerTeamTieBreak(
                    [
                        ESBVariantTieBreakOption(ESBVariant.EMGSB),
                    ]
                ),
            ],
        ),
    ]
    plugin_manager.hook_for_event(
        event, 'insert_team_round_robin_system_tie_break_sets'
    )(system_sets=system_sets)
    return system_sets


def _team_scheveningen_system_sets() -> list['SystemTieBreakSet']:
    """
    Sharly Chess recommandations for Scheveningen tournaments are:
    1. PTS
    2. MPvGP
    3. BC
    4. TBR
    """
    system_sets: list[SystemTieBreakSet] = [
        SystemTieBreakSet(
            key='team-scheveningen-sc-recommendation',
            name=_('Sharly Chess recommendation'),
            tie_breaks=[
                tie_breaks.PointsTieBreak(),
                team_tie_breaks.MatchPointsVsGamePointsTieBreak(),
                team_tie_breaks.BoardCountTieBreak(),
                team_tie_breaks.TopBoardResultsTieBreak(),
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
    elif system_id == TeamSwissPairingSystem().id:
        system_sets = _team_swiss_system_sets(event)
    elif system_id == TeamRoundRobinPairingSystem().id:
        system_sets = _team_round_robin_system_sets(event)
    elif system_id == ScheveningenPairingSystem().id:
        system_sets = _team_scheveningen_system_sets()
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
