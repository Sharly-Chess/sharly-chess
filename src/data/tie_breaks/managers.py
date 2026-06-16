from typing import override

from cryptography.utils import cached_property

from data.tie_breaks import cutters, options, tie_breaks
from data.tie_breaks.cutters import TieBreakCutter
from data.tie_breaks.options import TieBreakOption
from data.tie_breaks.tie_breaks import TieBreak
from plugins.manager import plugin_manager
from utils.entity import EntityManager, EventBoundEntityManager


class TieBreakManager(EventBoundEntityManager[TieBreak]):
    @override
    def entity_types(self) -> list[type[TieBreak]]:
        tie_break_types = [
            tie_breaks.WinsTieBreak,
            tie_breaks.GamesWonTieBreak,
            tie_breaks.GamesPlayedWithBlackTieBreak,
            tie_breaks.GamesWonWithBlackTieBreak,
            tie_breaks.ProgressiveScoresTieBreak,
            tie_breaks.RoundsElectedToPlayTieBreak,
            tie_breaks.StandardPointsTieBreak,
            tie_breaks.PairingNumberTieBreak,
            tie_breaks.StandardBuchholzTieBreak,
            tie_breaks.ForeBuchholzTieBreak,
            tie_breaks.SumOfBuchholzTieBreak,
            tie_breaks.AverageOfBuchholzTieBreak,
            tie_breaks.SonnebornBergerTieBreak,
            tie_breaks.KoyaTieBreak,
            tie_breaks.KashdanTieBreak,
            tie_breaks.AverageRatingOpponentsTieBreak,
            tie_breaks.TournamentPerformanceRatingTieBreak,
            tie_breaks.AveragePerformanceRatingOpponentsTieBreak,
            tie_breaks.PerfectTournamentPerformanceTieBreak,
            tie_breaks.AveragePerfectPerformanceTieBreak,
            tie_breaks.PlayerRatingTieBreak,
            tie_breaks.DirectEncounterTieBreak,
            tie_breaks.ManualTieBreak,
        ]
        plugin_manager.hook_for_event(self.event, 'insert_tie_break_types')(
            tie_break_types=tie_break_types
        )
        return tie_break_types

    @cached_property
    def _manual_trf_acronym_mapping(self) -> dict[str, TieBreak]:
        """Manual mapping of tie-break per acronym.
        Required when the base acronym depends on options."""
        tie_break_by_acronym: dict[str, TieBreak] = {}
        plugin_manager.hook_for_event(
            self.event, 'add_tie_breaks_to_trf_acronym_mapping'
        )(tie_break_by_acronym=tie_break_by_acronym)
        return {
            acronym.upper(): tie_break
            for acronym, tie_break in tie_break_by_acronym.items()
        }

    def tie_break_from_trf_acronym(self, acronym: str) -> TieBreak | None:
        acronym = acronym.upper()
        tie_break = self._manual_trf_acronym_mapping.get(acronym)
        if tie_break:
            return tie_break
        acronym = acronym.split('OTHER_', maxsplit=1)[-1]
        base_acronym = acronym.split('/')[0]
        tie_break = next(
            (
                tie_break
                for tie_break in self.objects()
                if tie_break.base_acronym.upper() == base_acronym
            ),
            None,
        )
        if not tie_break:
            return None
        for variation_acronym in acronym.split('/')[1:]:
            if not any(
                option.set_value_from_variation_acronym(variation_acronym)
                for option in tie_break.options
            ):
                return None
        return tie_break


class TieBreakOptionManager(EventBoundEntityManager[TieBreakOption]):
    @override
    def entity_types(self) -> list[type[TieBreakOption]]:
        tie_break_option_types = [
            options.CutterTieBreakOption,
            options.CutterWithMedianTieBreakOption,
            options.PlayedModifierTieBreakOption,
            options.ForeModifierTieBreakOption,
            options.KoyaLimitTieBreakOption,
            options.ReversedTieBreakOption,
            options.EstimatedRatingsTieBreakOption,
            options.LegacyMarch2026TieBreakOption,
        ]
        plugin_manager.hook_for_event(self.event, 'insert_tie_break_option_types')(
            tie_break_option_types=tie_break_option_types
        )
        return tie_break_option_types


class TieBreakCutterManager(EntityManager[TieBreakCutter]):
    def __init__(self, include_median: bool = False):
        self.include_median = include_median

    def entity_types(self) -> list[type[TieBreakCutter]]:
        cutter_types = [
            cutters.NoCutTieBreakCutter,
            cutters.Cut1TieBreakCutter,
            cutters.Cut2TieBreakCutter,
        ]
        if self.include_median:
            cutter_types += [
                cutters.Median1TieBreakCutter,
                cutters.Median2TieBreakCutter,
            ]
        return cutter_types
