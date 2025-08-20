from common import experimental_features_enabled
from data.tie_breaks import tie_breaks, options
from data.tie_breaks.options import TieBreakOption
from data.tie_breaks.tie_breaks import TieBreak
from plugins.manager import plugin_manager
from utils.entity import EntityManager


class TieBreakManager(EntityManager[TieBreak]):
    @staticmethod
    def entity_types() -> list[type[TieBreak]]:
        # Include all the tie-breaks available in Papi
        tie_break_types = [
            tie_breaks.ProgressiveScoresTieBreak,
            tie_breaks.WinsTieBreak,
            tie_breaks.SonnebornBergerTieBreak,
            tie_breaks.KoyaTieBreak,
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
        plugin_manager.hook.insert_tie_break_types(tie_break_types=tie_break_types)
        return tie_break_types


class TieBreakOptionManager(EntityManager[TieBreakOption]):
    @staticmethod
    def entity_types() -> list[type[TieBreakOption]]:
        return [
            options.CutTieBreakOption,
            options.CutTopTieBreakOption,
            options.CutBottomTieBreakOption,
            options.PlayedModifierTieBreakOption,
            options.ForeModifierTieBreakOption,
            options.LimitTieBreakOption,
            options.ExcludeIdsTieBreakOption,
        ]
