from data.tournament import Tournament
from plugins.custom_upload import PLUGIN_NAME


class CustomUploadUtils:
    @staticmethod
    def get_tournament_plugin_data(
        tournament: Tournament,
    ) -> 'CustomUploadTournamentData':
        plugin_data = tournament.plugin_data[PLUGIN_NAME]
        # TODO: make sure plugin data is in the correct format
        return plugin_data

    @staticmethod
    def ffe_actions_unavailable_message(tournament: Tournament) -> str | None:
        from plugins.ffe.papi_converter import PapiConverter

        plugin_data = CustomUploadUtils.get_tournament_plugin_data(tournament)
        # TODO: verify FTP settings are properly configured for given tournament
        return PapiConverter.papi_export_unavailable_message(tournament)
