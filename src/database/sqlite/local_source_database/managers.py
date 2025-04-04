from database.sqlite.local_source_database import delays, actions
from database.sqlite.local_source_database.actions import OutdatedAction
from database.sqlite.local_source_database.databases import LocalSourceDatabase
from database.sqlite.local_source_database.delays import OutdatedDelay
from plugins.manager import plugin_manager
from utils.entity import EntityManager


class LocalSourceDatabaseManager(EntityManager[LocalSourceDatabase]):
    @staticmethod
    def entity_types() -> list[type[LocalSourceDatabase]]:
        from database.sqlite.fide.fide_database import FideDatabase

        database_types: list[type[LocalSourceDatabase]] = [FideDatabase]
        plugin_manager.hook.insert_local_source_database_types(
            database_types=database_types
        )
        return database_types


class OutdatedDelayManager(EntityManager[OutdatedDelay]):
    @staticmethod
    def entity_types() -> list[type[OutdatedDelay]]:
        return [
            delays.DisabledOutdatedDelay,
            delays.DailyOutdatedDelay,
            delays.Days2OutdatedDelay,
            delays.Days3OutdatedDelay,
            delays.WeeklyOutdatedDelay,
            delays.MonthFirstDayOutdatedDelay,
        ]


class OutdatedActionManager(EntityManager[OutdatedAction]):
    @staticmethod
    def entity_types() -> list[type[OutdatedAction]]:
        return [
            actions.NotifOutdatedAction,
            actions.AutoUpdateOutdatedAction,
        ]
