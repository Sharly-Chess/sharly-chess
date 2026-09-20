from typing import override
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
