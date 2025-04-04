import itertools

from data import tie_break, print
from data.input_output import PlayerUpdater, FidePlayerUpdater
from data.print import PrintDocument
from data.tie_break import TieBreak, TieBreakOption
from utils.entity import EntityManager, Option
from database.sqlite import local_source_database as database
from database.sqlite.local_source_database import OutdateDelay, OutdateAction, LocalSourceDatabase
from plugins.manager import plugin_manager


class TieBreakManager(EntityManager[TieBreak]):
    @staticmethod
    def entity_types() -> list[type[TieBreak]]:
        return [
            tie_break.WinsTieBreak,
            tie_break.GamesWonTieBreak,
            tie_break.GamesPlayedWithBlackTieBreak,
            tie_break.GamesWonWithBlackTieBreak,
            tie_break.ProgressiveScoresTieBreak,
            tie_break.RoundsElectedToPlayTieBreak,
            tie_break.BuchholzTieBreak,
            tie_break.ForeBuchholzTieBreak,
            tie_break.SumOfBuchholzTieBreak,
            tie_break.AverageOfBuchholzTieBreak,
            tie_break.SonnebornBergerTieBreak,
            tie_break.KoyaTieBreak,
            tie_break.KashdanTieBreak,
            tie_break.AverageRatingOpponentsTieBreak,
            tie_break.TournamentPerformanceRatingTieBreak,
            tie_break.AveragePerformanceRatingOpponentsTieBreak,
            tie_break.PerfectTournamentPerformanceTieBreak,
            tie_break.AveragePerfectPerformanceTieBreak,
            tie_break.DirectEncounterTieBreak,
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
            tie_break.CutTieBreakOption,
            tie_break.CutTopTieBreakOption,
            tie_break.CutBottomTieBreakOption,
            tie_break.PlayedModifierTieBreakOption,
            tie_break.ForeModifierTieBreakOption,
            tie_break.LimitTieBreakOption,
            tie_break.ExcludeIdsTieBreakOption,
        ]


class PlayerUpdaterManager(EntityManager[PlayerUpdater]):
    @staticmethod
    def entity_types() -> list[type[PlayerUpdater]]:
        player_updaters = [FidePlayerUpdater]
        plugin_manager.hook.insert_player_updater_types(updater_types=player_updaters)
        return player_updaters


class PrintDocumentManager(EntityManager[PrintDocument]):
    @staticmethod
    def entity_types() -> list[type[PrintDocument]]:
        return [
            print.PlayerListPrintDocument,
            print.PairingPrintDocument,
            print.ResultPrintDocument,
            print.PlayerRankingPrintDocument,
            print.PlayerCrosstablePrintDocument,
        ]


class PrintDocumentOptionManager(EntityManager[Option]):
    @staticmethod
    def entity_types() -> list[type[Option]]:
        return [
            print.RoundPrintOption,
            print.PlayerSplitPrintOption,
        ]


class LocalSourceDatabaseManager(EntityManager[LocalSourceDatabase]):
    @staticmethod
    def entity_types() -> list[type[LocalSourceDatabase]]:
        from database.sqlite.fide.fide_database import FideDatabase

        database_types: list[type[LocalSourceDatabase]] = [FideDatabase]
        plugin_manager.hook.insert_local_source_database_types(
            database_types=database_types
        )
        return database_types


class OutdateDelayManager(EntityManager[OutdateDelay]):
    @staticmethod
    def entity_types() -> list[type[OutdateDelay]]:
        return [
            database.DisabledOutdateDelay,
            database.DailyOutdateDelay,
            database.Days2OutdateDelay,
            database.Days3OutdateDelay,
            database.WeeklyOutdateDelay,
            database.MonthFirstDayOutdateDelay,
        ]


class OutdateActionManager(EntityManager[OutdateAction]):
    @staticmethod
    def entity_types() -> list[type[OutdateAction]]:
        return [
            database.NotifOutdateAction,
            database.AutoUpdateOutdateAction,
        ]
