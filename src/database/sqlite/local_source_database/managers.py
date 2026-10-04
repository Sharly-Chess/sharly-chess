from threading import Event, Thread
from typing import override

from database.sqlite.local_source_database import delays, actions
from database.sqlite.local_source_database.actions import OutdatedAction
from database.sqlite.local_source_database.databases import LocalSourceDatabase
from database.sqlite.local_source_database.delays import OutdatedDelay
from plugins.manager import plugin_manager
from utils.entity import EntityManager

#: How often the active databases are checked against their outdate delay,
#: the shortest of which is a day.
_CHECK_INTERVAL = 60 * 60
#: Set to ask for a check before the interval is over.
_check_now = Event()


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

    @override
    def objects(self) -> list[LocalSourceDatabase]:
        """The databases as they are offered and listed: the FIDE list,
        then the others by name."""
        return sorted(super().objects(), key=lambda database: database.sort_key)

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

    def check_active(self) -> None:
        for database in self.active_objects():
            database.check()

    def start_checking(self) -> None:
        """Installs what is missing and checks the active databases in the
        background, once at the start of the server and then at every
        interval, so that a delay expiring while the application runs is
        seen the same day and what a lost connection prevented is caught up
        on."""

        def check() -> None:
            while True:
                manager = LocalSourceDatabaseManager()
                manager.install_missing()
                manager.check_active()
                _check_now.wait(_CHECK_INTERVAL)
                _check_now.clear()

        Thread(target=check, daemon=True).start()

    @staticmethod
    def check_soon() -> None:
        """Asks the background thread for a pass without waiting for its
        next one, the connection having just come back."""
        _check_now.set()


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
