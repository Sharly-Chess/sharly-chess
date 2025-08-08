from data.input_output import tournament_exporters
from data.input_output.data_source import (
    FideDataSource,
    OnlineDataSource,
    DataSource,
)
from data.input_output.tournament_exporters import TournamentExporter
from plugins.manager import plugin_manager
from utils.entity import EntityManager


class DataSourceManager(EntityManager[DataSource]):
    @staticmethod
    def entity_types() -> list[type[DataSource]]:
        data_sources: list[type[DataSource]] = [FideDataSource]
        plugin_manager.hook.insert_data_sources(data_sources=data_sources)
        return data_sources


class OnlineDataSourceManager(EntityManager[OnlineDataSource]):
    @staticmethod
    def entity_types() -> list[type[OnlineDataSource]]:
        return [
            data_source
            for data_source in DataSourceManager.entity_types()
            if issubclass(data_source, OnlineDataSource)
        ]


class TournamentExporterManager(EntityManager[TournamentExporter]):
    @staticmethod
    def entity_types() -> list[type[TournamentExporter]]:
        exporters: list[type[TournamentExporter]] = [
            tournament_exporters.Trf16TournamentExporter,
            tournament_exporters.TrfBxTournamentExporter,
            tournament_exporters.PgnTournamentExporter,
        ]
        plugin_manager.hook.insert_tournament_exporters(exporters=exporters)
        return exporters
