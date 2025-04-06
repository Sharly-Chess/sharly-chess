from data.input_output import (
    player_updaters,
    PlayerUpdater,
    tournament_exporters,
    TournamentExporter,
)
from plugins.manager import plugin_manager
from utils.entity import EntityManager


class PlayerUpdaterManager(EntityManager[PlayerUpdater]):
    @staticmethod
    def entity_types() -> list[type[PlayerUpdater]]:
        updaters: list[type[PlayerUpdater]] = [player_updaters.FidePlayerUpdater]
        plugin_manager.hook.insert_player_updater_types(updater_types=updaters)
        return updaters


class TournamentExporterManager(EntityManager[TournamentExporter]):
    @staticmethod
    def entity_types() -> list[type[TournamentExporter]]:
        return [
            tournament_exporters.Trf16TournamentExporter,
            tournament_exporters.TrfBxTournamentExporter,
        ]
