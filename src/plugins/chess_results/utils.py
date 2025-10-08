from datetime import datetime
from functools import partial

from data.event import Event
from data.tournament import Tournament
from plugins.chess_results import PLUGIN_NAME
from plugins.utils import PluginUtils

get_data = partial(PluginUtils.get_plugin_data, PLUGIN_NAME)

CHESS_RESULTS_MIN_UPLOAD_DELAY = 3
CHESS_RESULTS_DEFAULT_UPLOAD_DELAY = 3
CHESS_RESULTS_EPOCH = datetime(2000, 1, 1)


class ChessResultsUtils:
    @staticmethod
    def resolve_auto_upload(tournament: Tournament) -> bool:
        if (auto_upload := get_data(tournament.plugin_data, 'auto_upload')) is not None:
            return auto_upload
        return get_data(tournament.event.plugin_data, 'auto_upload')

    @staticmethod
    def resolve_auto_upload_delay(event: Event) -> int:
        if (
            auto_upload_delay := get_data(event.plugin_data, 'auto_upload_delay')
        ) is not None:
            return auto_upload_delay
        return CHESS_RESULTS_DEFAULT_UPLOAD_DELAY
