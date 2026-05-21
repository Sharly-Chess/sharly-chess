from pathlib import Path
from typing import IO

from common.i18n import _
from data.input_output import TournamentExporter
from data.tournament import Tournament
from plugins.ffe import PLUGIN_NAME
from plugins.ffe.papi_converter import PapiConverter


class PapiTournamentExporter(TournamentExporter):
    @staticmethod
    def static_id() -> str:
        return f'{PLUGIN_NAME}-papi'

    @staticmethod
    def static_name() -> str:
        return _('PAPI')

    def is_unavailable_message(self, tournament: Tournament) -> str | None:
        return PapiConverter.papi_export_unavailable_message(tournament)

    def warning_message(self, tournament: Tournament) -> str | None:
        return PapiConverter.papi_export_warning(tournament)

    @property
    def file_extension(self) -> str:
        return 'papi'

    def dump_to_file(self, file: IO, tournament: Tournament):
        file.close()
        PapiConverter().write_papi_file(tournament, Path(file.name))
