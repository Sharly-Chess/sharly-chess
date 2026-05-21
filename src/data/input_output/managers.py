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
        data_sources: list[type[DataSource]] = [FideDataSource]
        plugin_manager.hook.insert_data_sources(data_sources=data_sources)
        return data_sources


class OnlineDataSourceManager(EntityManager[OnlineDataSource]):
    @override
    def entity_types(self) -> list[type[OnlineDataSource]]:
        return [
            data_source
            for data_source in DataSourceManager().entity_types()
            if issubclass(data_source, OnlineDataSource)
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
        return exporters


class TournamentImporterManager(EventBoundEntityManager[TournamentImporter]):
    @override
    def entity_types(self) -> list[type[TournamentImporter]]:
        importers: list[type[TournamentImporter]] = [TrfTournamentImporter]
        plugin_manager.hook_for_event(self.event, 'insert_tournament_importers')(
            importers=importers
        )
        return importers


class PlayerExporterManager(EntityManager[PlayerExporter]):
    def entity_types(self) -> list[type[PlayerExporter]]:
        return [
            player_exporters.CsvPlayerExporter,
            player_exporters.OdsPlayerExporter,
            player_exporters.XlsxPlayerExporter,
            player_exporters.VcfPlayerExporter,
        ]
