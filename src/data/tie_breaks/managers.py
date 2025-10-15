from typing import override
from common import experimental_features_enabled
from data.tie_breaks import tie_breaks, options
from data.tie_breaks.options import TieBreakOption
from data.tie_breaks.tie_breaks import TieBreak
from plugins.manager import plugin_manager
from utils.entity import EntityManager, EventBoundEntityManager


class TieBreakManager(EventBoundEntityManager[TieBreak]):
    @override
    def entity_types(self) -> list[type[TieBreak]]:
        # Include all the tie-breaks available in Papi
        tie_break_types = [
            tie_breaks.ProgressiveScoresTieBreak,
            tie_breaks.WinsTieBreak,
            tie_breaks.SonnebornBergerTieBreak,
            tie_breaks.KoyaTieBreak,
            tie_breaks.ManualTieBreak,
        ]
        # Include all the others as experimental
        if experimental_features_enabled():
            tie_break_types += [
                tie_breaks.GamesWonTieBreak,
                tie_breaks.GamesPlayedWithBlackTieBreak,
                tie_breaks.GamesWonWithBlackTieBreak,
                tie_breaks.RoundsElectedToPlayTieBreak,
                tie_breaks.StandardBuchholzTieBreak,
                tie_breaks.ForeBuchholzTieBreak,
                tie_breaks.SumOfBuchholzTieBreak,
                tie_breaks.AverageOfBuchholzTieBreak,
                tie_breaks.KashdanTieBreak,
                tie_breaks.AverageRatingOpponentsTieBreak,
                tie_breaks.TournamentPerformanceRatingTieBreak,
                tie_breaks.AveragePerformanceRatingOpponentsTieBreak,
                tie_breaks.PerfectTournamentPerformanceTieBreak,
                tie_breaks.AveragePerfectPerformanceTieBreak,
                tie_breaks.DirectEncounterTieBreak,
            ]
        plugin_manager.hook_for_event(self.event, 'insert_tie_break_types')(
            tie_break_types=tie_break_types
        )
        return tie_break_types


class TieBreakOptionManager(EntityManager[TieBreakOption]):
    @override
    def entity_types(self) -> list[type[TieBreakOption]]:
        return [
            options.CutTieBreakOption,
            options.CutTopTieBreakOption,
            options.CutBottomTieBreakOption,
            options.PlayedModifierTieBreakOption,
            options.ForeModifierTieBreakOption,
            options.LimitTieBreakOption,
        ]
