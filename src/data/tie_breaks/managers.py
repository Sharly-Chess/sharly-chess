import itertools

from data.tie_breaks import tie_breaks, options
from data.tie_breaks.options import TieBreakOption
from data.tie_breaks.tie_breaks import TieBreak
from plugins.manager import plugin_manager
from utils.entity import EntityManager


class TieBreakManager(EntityManager[TieBreak]):
    @staticmethod
    def entity_types() -> list[type[TieBreak]]:
        return [
            tie_breaks.WinsTieBreak,
            tie_breaks.GamesWonTieBreak,
            tie_breaks.GamesPlayedWithBlackTieBreak,
            tie_breaks.GamesWonWithBlackTieBreak,
            tie_breaks.ProgressiveScoresTieBreak,
            tie_breaks.RoundsElectedToPlayTieBreak,
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
            tie_breaks.DirectEncounterTieBreak,
        ] + list(
            itertools.chain.from_iterable(
                plugin_manager.hook.get_extra_tie_break_classes()
            )
        )


class PapiTieBreakManager(EntityManager[TieBreak]):
    @staticmethod
    def entity_types() -> list[type[TieBreak]]:
        return [
            tie_break_type
            for tie_break_type in TieBreakManager.entity_types()
            if tie_break_type().papi_id is not None
        ]

    @classmethod
    def type_by_papi_id(cls) -> dict[str, type[TieBreak]]:
        return {
            str(entity_type.static_papi_id()): entity_type
            for entity_type in cls.entity_types()
            if entity_type.static_papi_id() is not None
        }


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
