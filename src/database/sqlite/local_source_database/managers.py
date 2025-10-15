from typing import override
from database.sqlite.local_source_database import delays, actions
from database.sqlite.local_source_database.actions import OutdatedAction
from database.sqlite.local_source_database.databases import LocalSourceDatabase
from database.sqlite.local_source_database.delays import OutdatedDelay
from plugins.manager import plugin_manager
from utils.entity import EntityManager


class LocalSourceDatabaseManager(EntityManager[LocalSourceDatabase]):
    @override
    def entity_types(self) -> list[type[LocalSourceDatabase]]:
        from database.sqlite.fide.fide_database import FideDatabase

        databases: list[type[LocalSourceDatabase]] = [FideDatabase]
        plugin_manager.hook.insert_local_source_databases(databases=databases)
        return databases


class OutdatedDelayManager(EntityManager[OutdatedDelay]):
    @override
    def entity_types(self) -> list[type[OutdatedDelay]]:
        return [
            delays.DisabledOutdatedDelay,
            delays.DailyOutdatedDelay,
            delays.Days2OutdatedDelay,
            delays.Days3OutdatedDelay,
            delays.WeeklyOutdatedDelay,
            delays.MonthFirstDayOutdatedDelay,
        ]


class OutdatedActionManager(EntityManager[OutdatedAction]):
    @override
    def entity_types(self) -> list[type[OutdatedAction]]:
        return [
            actions.NotifOutdatedAction,
            actions.AutoUpdateOutdatedAction,
        ]
