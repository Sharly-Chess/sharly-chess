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
        from database.sqlite.national.cfc_database import CfcDatabase
        from database.sqlite.national.chessa_database import ChessaDatabase
        from database.sqlite.national.cfr_database import CfrDatabase
        from database.sqlite.national.dsb_database import DsbDatabase
        from database.sqlite.national.dsu_database import DsuDatabase
        from database.sqlite.national.ecf_database import EcfDatabase
        from database.sqlite.national.fsi_database import FsiDatabase
        from database.sqlite.national.jcf_database import JcfDatabase
        from database.sqlite.national.knsb_database import KnsbDatabase
        from database.sqlite.national.lok_database import LokDatabase
        from database.sqlite.national.mcf_database import McfDatabase
        from database.sqlite.national.nzcf_database import NzcfDatabase
        from database.sqlite.national.percasi_database import PercasiDatabase
        from database.sqlite.national.ssl_database import SslDatabase
        from database.sqlite.national.ucf_database import UcfDatabase

        databases: list[type[LocalSourceDatabase]] = [
            FideDatabase,
            KnsbDatabase,
            FsiDatabase,
            CfrDatabase,
            SslDatabase,
            CfcDatabase,
            DsbDatabase,
            EcfDatabase,
            ChessaDatabase,
            LokDatabase,
            UcfDatabase,
            JcfDatabase,
            NzcfDatabase,
            DsuDatabase,
            McfDatabase,
            PercasiDatabase,
        ]
        plugin_manager.hook.insert_local_source_databases(databases=databases)
        return databases

    def active_objects(self) -> list[LocalSourceDatabase]:
        return [database for database in self.objects() if database.is_active]

    def inactive_objects(self) -> list[LocalSourceDatabase]:
        return [database for database in self.objects() if not database.is_active]

    def activate_for_federation(self, federation: str) -> None:
        for database in self.objects():
            database.activate_for_federation(federation)

    def install_missing(self) -> None:
        for database in self.objects():
            database.install_if_missing()


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
