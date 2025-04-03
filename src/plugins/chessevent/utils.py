from functools import partial
from data.tournament import Tournament
from plugins.chessevent import PLUGIN_NAME
from plugins.utils import PluginUtils

get_data = partial(PluginUtils.get_plugin_data, PLUGIN_NAME)


class ChessEventUtils:
    @staticmethod
    def resolve_user_id(tournament: Tournament) -> str | None:
        if chessevent_user_id := get_data(tournament.plugin_data, 'chessevent_user_id'):
            return chessevent_user_id
        return get_data(tournament.event.plugin_data, 'chessevent_user_id')

    @staticmethod
    def resolve_password(tournament: Tournament) -> str | None:
        if chessevent_password := get_data(
            tournament.plugin_data, 'chessevent_password'
        ):
            return chessevent_password
        return get_data(tournament.event.plugin_data, 'chessevent_password')

    @staticmethod
    def resolve_event_id(tournament: Tournament) -> str | None:
        if chessevent_event_id := get_data(
            tournament.plugin_data, 'chessevent_event_id'
        ):
            return chessevent_event_id
        return get_data(tournament.event.plugin_data, 'chessevent_event_id')

    @staticmethod
    def resolve_tournament_name(tournament: Tournament) -> str | None:
        return get_data(tournament.plugin_data, 'chessevent_tournament_name')
