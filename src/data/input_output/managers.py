from typing import override, TYPE_CHECKING
from data.input_output import tournament_exporters, player_exporters
from data.input_output.data_source import (
    FideDataSource,
    OnlineDataSource,
    DataSource,
)
from data.input_output.player_exporters import PlayerExporter
from data.input_output.tournament_exporters import TournamentExporter
from data.input_output.tournament_importers import TournamentImporter
from data.input_output.trf.trf_importer import TrfTournamentImporter
from plugins.manager import plugin_manager
from utils.entity import EntityManager, EventBoundEntityManager

if TYPE_CHECKING:
    from data.input_output.data_source import LocalDataSource


class DataSourceManager(EntityManager[DataSource]):
    @override
    def entity_types(self) -> list[type[DataSource]]:
        from data.input_output.national_data_sources import (
            NATIONAL_DATA_SOURCE_TYPES,
        )

        data_sources: list[type[DataSource]] = [
            FideDataSource,
            *NATIONAL_DATA_SOURCE_TYPES,
        ]
        plugin_manager.hook.insert_data_sources(data_sources=data_sources)
        return data_sources

    def active_objects(self) -> list[DataSource]:
        return [data_source for data_source in self.objects() if data_source.is_active]

    def national_source(self, national_source_id: str) -> DataSource | None:
        """A data source providing the national identifiers of the given
        source key, the active one when there is one."""
        data_sources = [
            data_source
            for data_source in self.objects()
            if data_source.national_source_id == national_source_id
        ]
        return next(
            (data_source for data_source in data_sources if data_source.is_active),
            data_sources[0] if data_sources else None,
        )

    def national_source_for_federation(self, federation: str) -> DataSource | None:
        """The data source providing the national identifiers of a
        federation, the active one when there is one."""
        data_sources = [
            data_source
            for data_source in self.objects()
            if data_source.federation == federation and data_source.national_source_id
        ]
        return next(
            (data_source for data_source in data_sources if data_source.is_active),
            data_sources[0] if data_sources else None,
        )

    def installed_and_online_sources(
        self, national_source_id: str
    ) -> tuple['LocalDataSource | None', 'OnlineDataSource | None']:
        """The installed copy and the online source of a national list,
        those that are available."""
        from data.input_output.data_source import LocalDataSource

        installed: LocalDataSource | None = None
        online: OnlineDataSource | None = None
        for data_source in self.active_objects():
            if (
                data_source.national_source_id != national_source_id
                or not data_source.is_available
            ):
                continue
            if isinstance(data_source, LocalDataSource) and installed is None:
                installed = data_source
            elif isinstance(data_source, OnlineDataSource) and online is None:
                online = data_source
        return installed, online

    def reads_online(self, national_source_id: str) -> bool:
        """Whether a national list is read from its online source rather
        than from its installed copy, as the user set it on the copy."""
        installed, online = self.installed_and_online_sources(national_source_id)
        if online is None:
            return False
        if installed is None:
            return True
        return installed.database.stored_source_database.read_online

    def list_source(
        self, national_source_id: str, installed_only: bool = False
    ) -> DataSource | None:
        """The source a national list is read from when players are added
        and their ratings checked: its installed copy, which can be told
        current and needs no connection, unless the user chose its online
        source; the other one when only one is available. With
        *installed_only*, never the online one."""
        installed, online = self.installed_and_online_sources(national_source_id)
        if installed_only:
            return installed
        if online is not None and (
            installed is None or self.reads_online(national_source_id)
        ):
            return online
        return installed

    def activate_for_federation(self, federation: str) -> None:
        for data_source in self.objects():
            data_source.activate_for_federation(federation)


class OnlineDataSourceManager(EntityManager[OnlineDataSource]):
    @override
    def entity_types(self) -> list[type[OnlineDataSource]]:
        return [
            data_source
            for data_source in DataSourceManager().entity_types()
            if issubclass(data_source, OnlineDataSource)
        ]

    def active_objects(self) -> list[OnlineDataSource]:
        return [data_source for data_source in self.objects() if data_source.is_active]

    def inactive_objects(self) -> list[OnlineDataSource]:
        return [
            data_source for data_source in self.objects() if not data_source.is_active
        ]


class TournamentExporterManager(EventBoundEntityManager[TournamentExporter]):
    @override
    def entity_types(self) -> list[type[TournamentExporter]]:
        exporters: list[type[TournamentExporter]] = [
            tournament_exporters.Trf26TournamentExporter,
            tournament_exporters.PgnTournamentExporter,
        ]
        plugin_manager.hook_for_event(self.event, 'insert_tournament_exporters')(
            exporters=exporters
        )
        if self.event is not None:
            exporters = [
                exporter
                for exporter in exporters
                if exporter.supports_event_type(self.event.event_type)
            ]
        return exporters


class TournamentImporterManager(EventBoundEntityManager[TournamentImporter]):
    @override
    def entity_types(self) -> list[type[TournamentImporter]]:
        importers: list[type[TournamentImporter]] = [TrfTournamentImporter]
        plugin_manager.hook_for_event(self.event, 'insert_tournament_importers')(
            importers=importers
        )
        if self.event is not None:
            importers = [
                importer
                for importer in importers
                if importer.supports_event_type(self.event.event_type)
            ]
        return importers


class PlayerExporterManager(EntityManager[PlayerExporter]):
    def entity_types(self) -> list[type[PlayerExporter]]:
        return [
            player_exporters.CsvPlayerExporter,
            player_exporters.OdsPlayerExporter,
            player_exporters.XlsxPlayerExporter,
            player_exporters.VcfPlayerExporter,
        ]
